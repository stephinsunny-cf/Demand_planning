"""
backend/auth.py
────────────────
Supabase JWT verification and role extraction.

In DEMO_MODE (env DEMO_MODE=true), auth is bypassed and a super_admin
user is injected for local development without Supabase.
"""

import os
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger(__name__)

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

security = HTTPBearer(auto_error=not DEMO_MODE)


class UserContext:
    def __init__(self, user_id: str, email: str, role: str):
        self.user_id = user_id
        self.email   = email
        self.role    = role

    def has_role(self, *allowed_roles: str) -> bool:
        return self.role in allowed_roles or self.role == "super_admin"


DEMO_USER = UserContext("demo-user-id", "demo@curefoods.com", "super_admin")

# Role access map — which roles can access which resources
ROLE_ACCESS = {
    "super_admin":      {"*"},
    "planning_manager": {"dashboard", "sales", "forecast", "supply", "warehouse", "procurement", "alerts", "reports"},
    "demand_planner":   {"dashboard", "sales", "forecast", "supply", "alerts", "reports"},
    "procurement":      {"dashboard", "warehouse", "procurement", "alerts"},
    "kitchen_ops":      {"dashboard", "supply", "warehouse"},
    "culinary_team":    {"dashboard", "recipes"},
    "leadership":       {"dashboard", "reports"},
}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserContext:
    """Verify Supabase JWT and return UserContext. Bypassed in DEMO_MODE."""
    if DEMO_MODE:
        return DEMO_USER

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
            or "demand_planner"  # default role
        )
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
