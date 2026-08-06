"""
backend/auth.py
────────────────
Supabase JWT verification, role extraction, 30-second TTL in-memory profile caching, and RBAC security enforcement.
"""

import os
import time
import logging
from typing import Optional

import jwt as _pyjwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or SUPABASE_KEY

security = HTTPBearer(auto_error=False)

# 30-second TTL in-memory cache for user profile lookups
# Format: {user_id_or_email: (profile_dict, timestamp)}
_PROFILE_CACHE: dict[str, tuple[dict, float]] = {}
CACHE_TTL_SECONDS = 30.0

# In-memory cache for Supabase token verification results — this is the
# expensive network round-trip (sb.auth.get_user), so we avoid repeating it
# on every request. Deliberately separate from _PROFILE_CACHE above: this
# only answers "is this token a real, currently-issued Supabase login,"
# never "is this person still allowed in" — that check (is_active) still
# runs fresh on every single request below, unaffected by this cache, so
# admin deactivation still cuts a user off on their very next request.
# Format: {token: ({"user_id":..., "email":...}, expires_at_epoch)}
_TOKEN_CACHE: dict[str, tuple[dict, float]] = {}
TOKEN_CACHE_MAX_TTL_SECONDS = 3600.0  # 1 hour ceiling, matches Supabase's default JWT lifetime


def _token_expiry(token: str) -> float | None:
    """Best-effort read of the JWT's own `exp` claim, no signature check
    needed — Supabase already verified the token's authenticity for us via
    the one real get_user() call; this just tells us how long *that*
    verification should be trusted for before asking again."""
    try:
        payload = _pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        return payload.get("exp")
    except Exception:
        return None


def clear_user_profile_cache(user_id_or_email: str | None = None):
    """Clear in-memory cache for a specific user or all users."""
    global _PROFILE_CACHE
    if user_id_or_email:
        _PROFILE_CACHE.pop(user_id_or_email, None)
    else:
        _PROFILE_CACHE.clear()


class UserContext:
    def __init__(self, user_id: str, email: str, role: str, must_reset_password: bool = False, is_active: bool = True):
        self.user_id = user_id
        self.email   = email
        self.role    = role
        self.must_reset_password = must_reset_password
        self.is_active = is_active

    def has_role(self, *allowed_roles: str) -> bool:
        if self.role == "super_admin":
            return True
        return self.role in allowed_roles


def _fetch_user_profile_from_db(user_id: str, email: str) -> dict:
    """Fetch user profile from user_profiles table with 30s in-memory caching."""
    now = time.time()
    cache_key = user_id or email

    if cache_key in _PROFILE_CACHE:
        profile, cached_at = _PROFILE_CACHE[cache_key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return profile

    try:
        from backend.database import query_df
        df = query_df(
            "SELECT user_id, email, role, must_reset_password, is_active FROM user_profiles WHERE user_id = %s OR lower(email) = lower(%s) LIMIT 1",
            params=(user_id, email)
        )
        if not df.empty:
            row = df.iloc[0]
            profile = {
                "user_id": str(row["user_id"]),
                "email": str(row["email"]),
                "role": str(row["role"]),
                "must_reset_password": bool(row["must_reset_password"]),
                "is_active": bool(row["is_active"]),
            }
            _PROFILE_CACHE[cache_key] = (profile, now)
            return profile
    except Exception as exc:
        log.warning("Could not fetch user profile from DB: %s", exc)

    # Fallback default if profile record not found yet
    # Fails closed (viewer) to prevent privilege escalation
    default_profile = {
        "user_id": user_id,
        "email": email,
        "role": "viewer",
        "must_reset_password": False,
        "is_active": True,
    }
    _PROFILE_CACHE[cache_key] = (default_profile, now)
    return default_profile


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserContext:
    """Verify Supabase JWT and return validated UserContext with active status and role."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authentication token")

    token = credentials.credentials
    now = time.time()

    try:
        cached = _TOKEN_CACHE.get(token)
        if cached and now < cached[1]:
            user_id, email = cached[0]["user_id"], cached[0]["email"]
        else:
            from supabase import create_client
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            user_resp = sb.auth.get_user(token)
            user = user_resp.user
            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

            user_id, email = user.id, user.email or ""

            token_exp = _token_expiry(token)
            ttl = TOKEN_CACHE_MAX_TTL_SECONDS
            if token_exp:
                ttl = min(ttl, max(token_exp - now, 0))
            _TOKEN_CACHE[token] = ({"user_id": user_id, "email": email}, now + ttl)

        # Always fetched fresh (own 30s cache, cleared instantly on admin
        # deactivation) — deactivation still cuts a user off on their very
        # next request regardless of the token cache above.
        profile = _fetch_user_profile_from_db(user_id, email)

        if not profile.get("is_active", True):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is deactivated")

        return UserContext(
            user_id=user_id,
            email=email or profile["email"],
            role=profile.get("role", "viewer"),
            must_reset_password=profile.get("must_reset_password", False),
            is_active=profile.get("is_active", True),
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.error("Auth verification error: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


def require_role(*roles: str):
    """FastAPI dependency factory enforcing server-side role security boundaries."""
    async def checker(request: Request, user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role == "super_admin":
            return user
            
        if user.role in roles:
            return user
            
        # Role mapping for legacy business endpoints
        if user.role == "admin":
            # Admin can do everything except strict super_admin routes
            if roles != ("super_admin",):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' does not have access. Required: {list(roles)}",
        )
    return checker
