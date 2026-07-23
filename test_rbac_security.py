"""
test_rbac_security.py
─────────────────────
Automated security test suite validating 4-tier RBAC boundaries,
Option B temporary password generation, password complexity compliance,
privilege escalation guards, and 30-second TTL user profile caching.
"""

import sys
import unittest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import UserContext, get_current_user, clear_user_profile_cache, _PROFILE_CACHE
from backend.routers.admin import generate_secure_temp_password, send_temp_password_email
from backend.database import get_db, query_df

client = TestClient(app)


class TestRBACSecurity(unittest.TestCase):

    def test_temp_password_complexity(self):
        """Verify Option B temporary passwords strictly satisfy all complexity rules."""
        for _ in range(50):
            pwd = generate_secure_temp_password(14)
            self.assertEqual(len(pwd), 14)
            self.assertTrue(any(c.isupper() for c in pwd), f"Missing uppercase in {pwd}")
            self.assertTrue(any(c.islower() for c in pwd), f"Missing lowercase in {pwd}")
            self.assertTrue(any(c.isdigit() for c in pwd), f"Missing digit in {pwd}")
            self.assertTrue(any(c in "!@#$%^&*" for c in pwd), f"Missing symbol in {pwd}")

    def test_reader_cannot_edit_recipes(self):
        """Verify Readers cannot perform PUT edits on recipes."""
        def mock_reader():
            return UserContext(user_id="u_reader", email="reader@curefoods.in", role="reader")

        app.dependency_overrides[get_current_user] = mock_reader
        try:
            res = client.put("/api/recipes/TestDish", json=[{"ingredient": "Salt", "qty_per_portion": 1.0, "unit": "g"}])
            self.assertEqual(res.status_code, 403, f"Expected 403 Forbidden for reader, got {res.status_code}")
        finally:
            app.dependency_overrides.clear()

    def test_editor_cannot_access_admin(self):
        """Verify Editors cannot list or create users in Admin panel."""
        def mock_editor():
            return UserContext(user_id="u_editor", email="editor@curefoods.in", role="editor")

        app.dependency_overrides[get_current_user] = mock_editor
        try:
            res = client.get("/api/admin/users")
            self.assertEqual(res.status_code, 403, f"Expected 403 Forbidden for editor listing users, got {res.status_code}")

            res2 = client.post("/api/admin/users", json={"email": "new@curefoods.in", "role": "reader"})
            self.assertEqual(res2.status_code, 403, f"Expected 403 Forbidden for editor creating user, got {res2.status_code}")
        finally:
            app.dependency_overrides.clear()

    def test_admin_privilege_escalation_guard(self):
        """Verify Admins cannot create Admin or Super Admin accounts."""
        def mock_admin():
            return UserContext(user_id="u_admin", email="admin@curefoods.in", role="admin")

        app.dependency_overrides[get_current_user] = mock_admin
        try:
            res = client.post("/api/admin/users", json={"email": "hacker_admin@curefoods.in", "role": "admin"})
            self.assertEqual(res.status_code, 403)
            self.assertIn("Only Super Admins can assign Admin or Super Admin roles", res.json()["detail"])
        finally:
            app.dependency_overrides.clear()

    def test_super_admin_user_creation_and_resend(self):
        """Verify Super Admin can create user, sets must_reset_password = True, and resend resets flag."""
        def mock_super_admin():
            return UserContext(user_id="u_super", email="super@curefoods.in", role="super_admin")

        app.dependency_overrides[get_current_user] = mock_super_admin
        import time
        test_email = f"new_hire_{int(time.time())}@curefoods.in"

        try:
            # Create user
            res = client.post("/api/admin/users", json={"email": test_email, "role": "reader"})
            self.assertEqual(res.status_code, 200, f"Failed user creation: {res.text}")
            data = res.json()
            self.assertTrue(data["must_reset_password"])
            user_id = data["user_id"]

            # Check DB
            df = query_df("SELECT must_reset_password, role FROM user_profiles WHERE user_id = %s", params=(user_id,))
            self.assertFalse(df.empty)
            self.assertTrue(df["must_reset_password"].iloc[0])
            self.assertEqual(df["role"].iloc[0], "reader")

            # Simulate user changing password
            with get_db() as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute("UPDATE user_profiles SET must_reset_password = FALSE WHERE user_id = %s", (user_id,))
                    conn.commit()

            # Resend temp password should force must_reset_password back to True
            resend_res = client.post(f"/api/admin/users/{user_id}/resend-temp-password")
            self.assertEqual(resend_res.status_code, 200)

            df_after = query_df("SELECT must_reset_password FROM user_profiles WHERE user_id = %s", params=(user_id,))
            self.assertTrue(df_after["must_reset_password"].iloc[0], "Resend temp password MUST force must_reset_password = True!")

        finally:
            app.dependency_overrides.clear()


    def test_cache_ttl_deactivation(self):
        """
        Verify that 30-second TTL cache behaves correctly on deactivation:
          - Immediately after deactivation: active requests still pass (cache window in effect)
          - After TTL expiry (simulated by backdate): requests are blocked

        Uses monkeypatching of cache timestamp rather than sleeping 30 real seconds.
        """
        import time
        from backend.auth import _PROFILE_CACHE, CACHE_TTL_SECONDS

        user_id = f"usr_ttl_test_{int(time.time())}"
        email   = f"ttl_test_{int(time.time())}@curefoods.in"

        # Write an ACTIVE user profile into the DB
        with get_db() as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_profiles (user_id, email, role, must_reset_password, is_active)
                    VALUES (%s, %s, 'reader', FALSE, TRUE)
                    ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE
                """, (user_id, email))
                conn.commit()

        # Seed a fresh cache entry for this user at current time (simulates a cached active session)
        _PROFILE_CACHE[user_id] = (
            {"user_id": user_id, "email": email, "role": "reader", "must_reset_password": False, "is_active": True},
            time.time()
        )

        # Deactivate in DB (simulates admin deactivation)
        with get_db() as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("UPDATE user_profiles SET is_active = FALSE WHERE user_id = %s", (user_id,))
                conn.commit()

        # IMMEDIATELY after deactivation: cache is still warm.
        # Auth function should return the CACHED active profile (this is acceptable under the 30s SLA)
        from backend.auth import _fetch_user_profile_from_db
        profile_in_cache = _fetch_user_profile_from_db(user_id, email)
        self.assertTrue(
            profile_in_cache["is_active"],
            "Within cache window: stale 'active' profile expected from in-memory cache, not DB"
        )

        # SIMULATE TTL expiry by backdating the cache entry by CACHE_TTL_SECONDS + 1 second
        cached_profile, _ = _PROFILE_CACHE[user_id]
        _PROFILE_CACHE[user_id] = (cached_profile, time.time() - CACHE_TTL_SECONDS - 1)

        # AFTER TTL expiry: cache is cold, DB should be queried and return is_active=False
        profile_after_expiry = _fetch_user_profile_from_db(user_id, email)
        self.assertFalse(
            profile_after_expiry["is_active"],
            "After cache TTL expiry: is_active should be read from DB as FALSE"
        )

        # Cleanup
        with get_db() as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_profiles WHERE user_id = %s", (user_id,))
                conn.commit()

    def test_rollback_failure_returns_visible_error(self):
        """
        Verify that if user creation fails and rollback also fails,
        the 500 response body explicitly contains the orphaned user ID
        so the Admin UI can surface a visible, actionable error banner.
        """
        def mock_super_admin():
            return UserContext(user_id="u_super", email="super@curefoods.in", role="super_admin")

        app.dependency_overrides[get_current_user] = mock_super_admin

        # Patch send_temp_password_email to simulate SMTP failure AFTER Supabase auth user is created
        # Since Supabase is offline in test env, user creation falls back to local UUID
        # We simulate the rollback-failure path by using an email that ALREADY exists in the DB
        # creating a duplicate key error on profile insert, followed by a rollback attempt that
        # fails on the local `usr_xxx` id format (not a valid Supabase UUID)

        import time
        existing_email = f"duplicate_test_{int(time.time())}@curefoods.in"
        fake_user_id   = f"usr_duptest_{int(time.time())}"

        # Pre-seed the email so the ON CONFLICT path is NOT triggered — we need the INSERT to fail cleanly
        # We do this by inserting a row with the SAME user_id so the INSERT hits the unique email constraint
        with get_db() as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_profiles (user_id, email, role, must_reset_password, is_active)
                    VALUES (%s, %s, 'reader', TRUE, TRUE)
                """, (fake_user_id, existing_email))
                conn.commit()

        try:
            res = client.post("/api/admin/users", json={"email": existing_email, "role": "reader"})

            # Should return 500 (not a silent 200 swallowing the error)
            self.assertEqual(res.status_code, 500)
            body = res.json()

            # The response body must contain the orphaned user ID for admin visibility
            self.assertIn("ORPHANED SUPABASE USER ID", body["detail"],
                "Rollback failure MUST surface orphaned user ID in response for admin visibility")

        finally:
            app.dependency_overrides.clear()
            with get_db() as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM user_profiles WHERE user_id = %s", (fake_user_id,))
                    conn.commit()


if __name__ == "__main__":
    unittest.main()
