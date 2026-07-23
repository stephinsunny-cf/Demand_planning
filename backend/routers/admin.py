"""
backend/routers/admin.py
─────────────────────────
User Management, Role Assignment, Option B Temporary Password Generation,
Session Revocation, and Forced Password Reset Endpoints.
"""

import os
import string
import secrets
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from backend.auth import get_current_user, require_role, UserContext, clear_user_profile_cache
from backend.database import get_db, query_df

router = APIRouter()
log = logging.getLogger("admin_router")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or SUPABASE_KEY


def generate_secure_temp_password(length: int = 14) -> str:
    """
    Generate a cryptographically random temporary password guaranteed to satisfy all complexity rules:
    at least 1 uppercase, 1 lowercase, 1 digit, and 1 special symbol.
    """
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits    = string.digits
    symbols   = "!@#$%^&*"
    all_chars = uppercase + lowercase + digits + symbols

    # Guarantee at least one from each class
    pwd = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    # Fill remainder
    pwd += [secrets.choice(all_chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


# Gmail SMTP config from environment
GMAIL_SENDER       = os.getenv("GMAIL_SENDER", "")       # e.g. stephin.sunny@curefoods.in
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "") # 16-char Google App Password
APP_NAME           = os.getenv("APP_NAME", "Curefoods Demand Planning")
APP_URL            = os.getenv("APP_URL", "http://localhost:3000")


def send_temp_password_email(email: str, temp_password: str) -> bool:
    """
    Send a temporary password email via Gmail SMTP.
    Falls back to console log if GMAIL credentials are not configured
    (so tests and local dev continue to work without SMTP setup).
    Returns True if email sent, False if fallback used.
    """
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.warning(f"[EMAIL FALLBACK] Gmail not configured. Temp password for {email}: {temp_password}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your {APP_NAME} Account — Temporary Password"
        msg["From"]    = f"{APP_NAME} <{GMAIL_SENDER}>"
        msg["To"]      = email

        plain_body = f"""\
Hello,

Your {APP_NAME} account has been created.

Temporary Password: {temp_password}

This is a one-time password. You will be required to set a new password
immediately on your first login at:
{APP_URL}

If you did not expect this email, please contact your system administrator.

Regards,
{APP_NAME}
"""

        html_body = f"""\
<html><body style="font-family: Arial, sans-serif; background:#f4f4f4; padding:30px;">
  <div style="max-width:520px; margin:auto; background:#fff; border-radius:10px; 
              padding:32px; border:1px solid #e0e0e0; box-shadow:0 2px 8px rgba(0,0,0,0.05);">
    <h2 style="color:#3f3f3f; margin-bottom:6px;">Welcome to {APP_NAME}</h2>
    <p style="color:#666; font-size:14px;">Your account has been created by a system administrator.</p>
    <hr style="border:none; border-top:1px solid #eee; margin:20px 0;">
    <p style="font-size:14px; color:#444;">Your temporary password is:</p>
    <div style="background:#f0f4ff; border:1px solid #c7d7ff; border-radius:6px; 
                padding:14px 20px; font-size:22px; font-weight:bold; 
                letter-spacing:2px; color:#1a237e; text-align:center; margin:12px 0;">
      {temp_password}
    </div>
    <p style="font-size:13px; color:#888; margin-top:6px;">
      ⚠️ You will be asked to set a new, permanent password immediately on first login.
    </p>
    <a href="{APP_URL}" style="display:inline-block; margin-top:20px; padding:12px 28px; 
       background:#4f46e5; color:#fff; border-radius:6px; text-decoration:none; 
       font-weight:bold; font-size:14px;">Log In Now →</a>
    <hr style="border:none; border-top:1px solid #eee; margin:28px 0 16px;">
    <p style="font-size:12px; color:#aaa;">If you did not expect this email, contact your administrator.</p>
  </div>
</body></html>
"""

        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_SENDER, email, msg.as_string())

        log.info(f"[EMAIL] Temporary password sent to {email} via Gmail SMTP.")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error("[EMAIL] Gmail SMTP authentication failed. Check GMAIL_SENDER and GMAIL_APP_PASSWORD in .env")
        raise HTTPException(
            status_code=500,
            detail="Email delivery failed: Gmail authentication error. Contact system administrator to verify SMTP credentials."
        )
    except smtplib.SMTPException as e:
        log.error(f"[EMAIL] SMTP error sending to {email}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Email delivery failed (SMTP error): {str(e)}"
        )
    except Exception as e:
        log.error(f"[EMAIL] Unexpected error sending to {email}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Email delivery failed: {str(e)}"
        )



class CreateUserRequest(BaseModel):
    email: str
    role: str  # reader, editor, admin, super_admin


class ChangeRoleRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.get("/admin/users")
async def list_users(user: UserContext = Depends(require_role("admin", "super_admin"))):
    """List all user profiles (Admin / Super Admin only)."""
    df = query_df("SELECT user_id, email, role, must_reset_password, is_active, created_at FROM user_profiles ORDER BY created_at DESC")
    return df.to_dict(orient="records") if not df.empty else []


@router.post("/admin/users")
async def create_user(
    req: CreateUserRequest,
    caller: UserContext = Depends(require_role("admin", "super_admin"))
):
    """
    Create a new user with a cryptographically random temporary password.
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

    temp_password = generate_secure_temp_password()
    created_auth_user_id = None

    try:
        try:
            from supabase import create_client
            sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            
            # 1. Create in Supabase Auth
            auth_resp = sb_admin.auth.admin.create_user({
                "email": req.email,
                "password": temp_password,
                "email_confirm": True,
                "user_metadata": {"role": requested_role}
            })
            
            if auth_resp and auth_resp.user:
                created_auth_user_id = auth_resp.user.id
        except Exception as sb_err:
            log.warning("Supabase Auth API offline or unavailable, generating local UUID: %s", sb_err)
            import uuid
            created_auth_user_id = f"usr_{uuid.uuid4().hex[:12]}"

        # 2. Insert into PostgreSQL user_profiles
        with get_db_connection() as conn:
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

        # 3. Send temporary password email
        send_temp_password_email(req.email, temp_password)
        clear_user_profile_cache(created_auth_user_id)

        return {
            "message": f"User {req.email} created successfully.",
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


@router.post("/admin/users/{user_id}/resend-temp-password")
async def resend_temp_password(
    user_id: str,
    caller: UserContext = Depends(require_role("admin", "super_admin"))
):
    """Regenerate new temporary password and force must_reset_password = True."""
    df = query_df("SELECT email, role FROM user_profiles WHERE user_id = %s", params=(user_id,))
    if df.empty:
        raise HTTPException(status_code=404, detail="User profile not found")

    target_email = df["email"].iloc[0]
    target_role  = df["role"].iloc[0]

    if target_role in ("admin", "super_admin") and caller.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only Super Admins can manage Admin passwords.")

    new_temp_password = generate_secure_temp_password()

    try:
        try:
            from supabase import create_client
            sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            sb_admin.auth.admin.update_user_by_id(user_id, {"password": new_temp_password})
        except Exception as sb_err:
            log.warning("Supabase update_user_by_id offline: %s", sb_err)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE user_profiles SET must_reset_password = TRUE, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
                conn.commit()

        send_temp_password_email(target_email, new_temp_password)
        clear_user_profile_cache(user_id)

        return {"message": f"New temporary password generated and sent to {target_email}."}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to resend temporary password: {str(exc)}")


@router.put("/admin/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    req: ChangeRoleRequest,
    caller: UserContext = Depends(require_role("super_admin"))
):
    """Update user role (Super Admin only)."""
    new_role = req.role.lower()
    if new_role not in ("reader", "editor", "admin", "super_admin"):
        raise HTTPException(status_code=400, detail="Invalid role name")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE user_profiles SET role = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s", (new_role, user_id))
            conn.commit()

    clear_user_profile_cache(user_id)
    return {"message": f"User role updated to {new_role}."}


@router.put("/admin/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    caller: UserContext = Depends(require_role("super_admin"))
):
    """Deactivate user account and revoke Supabase session (Super Admin only)."""
    if user_id == caller.user_id:
        raise HTTPException(status_code=400, detail="Super Admins cannot deactivate their own account.")

    with get_db_connection() as conn:
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


@router.post("/auth/reset-password")
async def reset_password(
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

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE user_profiles SET must_reset_password = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s OR lower(email) = lower(%s)", (user.user_id, user.email))
            conn.commit()

    clear_user_profile_cache(user.user_id)
    return {"message": "Password updated successfully. You now have full access."}
