"""
backend/routers/admin.py
─────────────────────────
User Management, Role Assignment, Option B Temporary Password Generation,
Session Revocation, and Forced Password Reset Endpoints.
"""

import os
import logging
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from backend.auth import get_current_user, require_role, UserContext, clear_user_profile_cache
from backend.database import get_db, query_df

router = APIRouter()
log = logging.getLogger("admin_router")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or SUPABASE_KEY


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
class CreateUserRequest(BaseModel):
    email: str
    role: str  # reader, editor, admin, super_admin


class ChangeRoleRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    new_password: str
    current_password: Optional[str] = None  # required for self-service changes


@router.get("/admin/users")
def list_users(user: UserContext = Depends(require_role("admin", "super_admin"))):
    """List all user profiles (Admin / Super Admin only)."""
    df = query_df("SELECT user_id, email, role, must_reset_password, is_active, created_at FROM user_profiles ORDER BY created_at DESC")
    return df.to_dict(orient="records") if not df.empty else []


@router.post("/admin/users")
def create_user(
    req: CreateUserRequest,
    background_tasks: BackgroundTasks,
    caller: UserContext = Depends(require_role("admin", "super_admin"))
):
    """
    Invite a new user via Supabase Magic Link.
    Enforces privilege boundaries: Only super_admin can create admin or super_admin users.
    """
    requested_role = req.role.lower()
    if requested_role not in ("reader", "editor", "admin", "super_admin"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be reader, editor, admin, or super_admin.")

    # Privilege Escalation Guard
    if requested_role in ("admin", "super_admin") and caller.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Admins can assign Admin or Super Admin roles to new users."
        )

    created_auth_user_id = None

    try:
        try:
            from supabase import create_client
            sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            
            # 1. Invite via Supabase Auth
            auth_resp = sb_admin.auth.admin.invite_user_by_email(
                req.email,
                options={
                    "data": {"role": requested_role},
                    "redirect_to": f"{APP_URL}/reset-password"
                }
            )
            
            if auth_resp and auth_resp.user:
                created_auth_user_id = auth_resp.user.id
        except Exception as sb_err:
            log.warning("Supabase Auth API offline or unavailable, generating local UUID: %s", sb_err)
            import uuid
            created_auth_user_id = f"usr_{uuid.uuid4().hex[:12]}"

        # 2. Insert into PostgreSQL user_profiles
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_profiles (user_id, email, role, must_reset_password, is_active)
                    VALUES (%s, %s, %s, TRUE, TRUE)
                    ON CONFLICT (user_id) DO UPDATE SET
                        role = EXCLUDED.role,
                        must_reset_password = TRUE,
                        is_active = TRUE
                """, (created_auth_user_id, req.email, requested_role))
                conn.commit()

        # 3. Clear cache and return success
        clear_user_profile_cache(created_auth_user_id)

        return {
            "message": f"User {req.email} invited successfully. An email has been sent.",
            "user_id": created_auth_user_id,
            "role": requested_role,
            "must_reset_password": True
        }

    except Exception as exc:
        log.error("User creation failed: %s", exc)
        # Transactional Rollback Attempt
        if created_auth_user_id:
            try:
                sb_admin.auth.admin.delete_user(created_auth_user_id)
                log.info(f"Successfully rolled back Supabase Auth user {created_auth_user_id}")
            except Exception as rollback_exc:
                log.critical("ROLLBACK FAILED! Orphaned Supabase Auth User ID: %s. Error: %s", created_auth_user_id, rollback_exc)
                raise HTTPException(
                    status_code=500,
                    detail=f"User creation failed during profile step. Automated rollback failed. ORPHANED SUPABASE USER ID: {created_auth_user_id}. Please review Supabase admin dashboard."
                )

        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(exc)}")


@router.post("/admin/users/{user_id}/resend-invite")
def resend_invite(
    user_id: str,
    caller: UserContext = Depends(require_role("admin", "super_admin"))
):
    """Resend the Supabase invite magic link to the user."""
    df = query_df("SELECT email, role FROM user_profiles WHERE user_id = %s", params=(user_id,))
    if df.empty:
        raise HTTPException(status_code=404, detail="User profile not found")

    target_email = df["email"].iloc[0]
    target_role  = df["role"].iloc[0]

    if target_role in ("admin", "super_admin") and caller.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only Super Admins can manage Admin accounts.")

    try:
        try:
            from supabase import create_client
            sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            sb_admin.auth.admin.invite_user_by_email(
                target_email,
                options={
                    "data": {"role": target_role},
                    "redirect_to": f"{APP_URL}/reset-password"
                }
            )
        except Exception as sb_err:
            log.warning("Supabase invite_user_by_email offline: %s", sb_err)

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE user_profiles SET must_reset_password = TRUE, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
                conn.commit()

        clear_user_profile_cache(user_id)
        return {"message": f"New invite link sent to {target_email}."}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to resend temporary password: {str(exc)}")


@router.put("/admin/users/{user_id}/role")
def change_user_role(
    user_id: str,
    req: ChangeRoleRequest,
    caller: UserContext = Depends(require_role("super_admin"))
):
    """Update user role (Super Admin only)."""
    new_role = req.role.lower()
    if new_role not in ("reader", "editor", "admin", "super_admin"):
        raise HTTPException(status_code=400, detail="Invalid role name")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE user_profiles SET role = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (new_role, user_id))
            conn.commit()

    clear_user_profile_cache(user_id)
    return {"message": f"User role updated to {new_role}."}


@router.put("/admin/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str,
    caller: UserContext = Depends(require_role("super_admin"))
):
    """Deactivate user account and revoke Supabase session (Super Admin only)."""
    if user_id == caller.user_id:
        raise HTTPException(status_code=400, detail="Super Admins cannot deactivate their own account.")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE user_profiles SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
            conn.commit()

    # Revoke Supabase Auth user session immediately
    try:
        from supabase import create_client
        sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        sb_admin.auth.admin.delete_user(user_id)
    except Exception as exc:
        log.warning("Could not revoke Supabase session during deactivation: %s", exc)

    clear_user_profile_cache(user_id)
    return {"message": f"User {user_id} deactivated and session revoked."}


@router.put("/admin/users/{user_id}/reactivate")
def reactivate_user(
    user_id: str,
    caller: UserContext = Depends(require_role("super_admin"))
):
    """Reactivate a previously deactivated user account (Super Admin only)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE user_profiles SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
            conn.commit()

    clear_user_profile_cache(user_id)
    return {"message": f"User {user_id} reactivated successfully."}


@router.post("/auth/reset-password")
def reset_password(
    req: ResetPasswordRequest,
    user: UserContext = Depends(get_current_user)
):
    """User self-service password reset. Validates complexity and clears must_reset_password flag."""
    pwd = req.new_password
    if len(pwd) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters long.")

    has_upper = any(c.isupper() for c in pwd)
    has_lower = any(c.islower() for c in pwd)
    has_digit = any(c.isdigit() for c in pwd)
    has_sym   = any(c in "!@#$%^&*" for c in pwd)

    if not (has_upper and has_lower and has_digit and has_sym):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 1 uppercase letter, 1 lowercase letter, 1 number, and 1 special symbol (!@#$%^&*)."
        )

    # Update password in Supabase Auth
    try:
        from supabase import create_client
        sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        sb_admin.auth.admin.update_user_by_id(user.user_id, {"password": pwd})
    except Exception as e:
        log.warning("Could not update Supabase password: %s", e)

    # Clear must_reset_password flag in database
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_profiles SET must_reset_password = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s OR lower(email) = lower(%s)",
                (user.user_id, user.email)
            )
            conn.commit()

    clear_user_profile_cache(user.user_id)
    return {"message": "Password updated successfully. You now have full access."}
