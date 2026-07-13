"""
backend/auth.py
────────────────
Supabase JWT verification and role extraction.
"""

import os
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

security = HTTPBearer()


class UserContext:
    def __init__(self, user_id: str, email: str, role: str):
        self.user_id = user_id
        self.email   = email
        self.role    = role

    def has_role(self, *allowed_roles: str) -> bool:
        return self.role in allowed_roles or self.role == "super_admin"

# Role access map — which roles can access which resources
ROLE_ACCESS = {
    "super_admin": {"*"},
    "editor":      {"dashboard", "sales", "forecast", "supply", "warehouse", "procurement", "alerts", "reports", "recipes"},
    "viewer":      {"dashboard", "reports", "alerts"},
}

FIRST_ADMIN_EMAIL = os.getenv("FIRST_ADMIN_EMAIL", "")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserContext:
    """Verify Supabase JWT and return UserContext."""

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials

    try:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        user_resp = sb.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        # Role stored in user_metadata or app_metadata
        role = (
            user.user_metadata.get("role")
            or user.app_metadata.get("role")
            or "viewer"  # default role
        )
        
        # Bootstrap: Auto-promote the first admin based on email
        if FIRST_ADMIN_EMAIL and user.email and user.email.lower() == FIRST_ADMIN_EMAIL.lower():
            role = "super_admin"
        return UserContext(user.id, user.email, role)

    except HTTPException:
        raise
    except Exception as exc:
        log.error("Auth error: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


def require_role(*roles: str):
    """FastAPI dependency factory that checks if user has one of the required roles."""
    async def checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role == "super_admin":
            return user
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' does not have access. Required: {list(roles)}",
            )
        return user
    return checker
