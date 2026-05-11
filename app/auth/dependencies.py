"""FastAPI dependencies that extract authenticated user context from Clerk JWT."""

from typing import Dict, Optional

from fastapi import Depends, Header, HTTPException, status

from .jwt_verifier import verify_clerk_token


# ── Bearer token extraction & verification ──

async def _extract_token(authorization: str = Header(...)) -> str:
    """Extract the raw JWT from the Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer '",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is empty",
        )
    return token


async def get_current_user(token: str = Depends(_extract_token)) -> Dict:
    """Verify the Clerk JWT and return all claims.

    Use as:  user: dict = Depends(get_current_user)

    The returned dict contains at minimum:
        - sub:        Clerk user ID
        - org_id:     active organization ID (if user has selected an org)
        - org_role:   user's role in the org (e.g. "org:admin", "org:member")
        - org_slug:   organization slug
        - sid:        session ID
    """
    try:
        claims = await verify_clerk_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    return claims


# ── Scoped extractors ──

async def get_current_user_id(user: Dict = Depends(get_current_user)) -> str:
    """Extract the Clerk user ID (sub claim)."""
    sub = user.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    return sub


async def get_current_org(user: Dict = Depends(get_current_user)) -> str:
    """Extract the active Clerk organization ID (org_id claim).

    Raises 400 if the user hasn't selected an active organization.

    Supports both JWT v1 (top-level org_id) and v2 (nested under 'o' claim).
    """
    org_claims = user.get("o", {})
    if isinstance(org_claims, dict):
        org_id = org_claims.get("id")
    else:
        org_id = user.get("id")  # JWT v1 fallback

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No active organization — select an org in the app. "
                "Make sure your Clerk SDK version supports JWT v2 with Organization claims."
            ),
        )
    return org_id


async def get_current_org_role(user: Dict = Depends(get_current_user)) -> str:
    """Extract the user's role in the active organization (v2: o.role, v1: org_role)."""
    org_claims = user.get("o", {})
    if isinstance(org_claims, dict) and "rol" in org_claims:
        return org_claims["rol"]
    return user.get("org_role", "org:member")


async def get_current_profile_id(
    x_profile_id: Optional[str] = Header(None),
) -> Optional[str]:
    """Extract the active profile ID from X-Profile-Id header."""
    return x_profile_id


# ── Composite context ──

async def get_auth_context(
    user_id: str = Depends(get_current_user_id),
    org_id: str = Depends(get_current_org),
    org_role: str = Depends(get_current_org_role),
    profile_id: Optional[str] = Depends(get_current_profile_id),
) -> Dict:
    """Full auth context packed into a dict for endpoint handlers.

    Use as:  ctx: dict = Depends(get_auth_context)

    Returns:
        {
            "user_id":    str,         # Clerk user ID (sub claim)
            "org_id":     str,         # active organization ID
            "org_role":   str,         # e.g. "org:admin", "org:member"
            "profile_id": str | None,  # from X-Profile-Id header
        }
    """
    return {
        "user_id": user_id,
        "org_id": org_id,
        "org_role": org_role,
        "profile_id": profile_id,
    }