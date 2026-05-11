"""Clerk JWT verification via JWKS endpoint."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

import httpx
from jose import jwk, jwt
from jose.exceptions import ExpiredSignatureError, JOSEError, JWTClaimsError, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

_jwks_lock = asyncio.Lock()
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cached_at: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour


async def _fetch_jwks() -> Dict[str, Any]:
    """Fetch Clerk JWKS and return the parsed dict. Handles caching."""
    global _jwks_cache, _jwks_cached_at

    now = datetime.now(timezone.utc)
    if (
        _jwks_cache is not None
        and _jwks_cached_at is not None
        and (now - _jwks_cached_at).total_seconds() < JWKS_CACHE_TTL_SECONDS
    ):
        return _jwks_cache

    async with _jwks_lock:
        # Double-check after acquiring lock
        if _jwks_cache is not None and _jwks_cached_at is not None:
            if (now - _jwks_cached_at).total_seconds() < JWKS_CACHE_TTL_SECONDS:
                return _jwks_cache

        clerk_jwks_url = settings.CLERK_JWKS_URL
        if not clerk_jwks_url:
            raise ValueError("CLERK_JWKS_URL is not configured")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(clerk_jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_cached_at = now
            logger.info("Clerk JWKS refreshed (keys: %d)", len(_jwks_cache.get("keys", [])))

    return _jwks_cache


def _invalidate_jwks_cache() -> None:
    """Clear the JWKS cache (call on key-not-found to force refresh)."""
    global _jwks_cache, _jwks_cached_at
    _jwks_cache = None
    _jwks_cached_at = None


async def verify_clerk_token(token: str) -> Dict[str, Any]:
    """Verify a Clerk-signed JWT and return the decoded claims.

    Raises:
        ValueError: If the token is invalid, expired, or untrusted.
    """
    if not token or not token.strip():
        raise ValueError("Token is empty")

    # 1. Extract kid from token header (unverified)
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JOSEError as e:
        raise ValueError(f"Invalid JWT header: {e}")

    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("JWT header missing 'kid'")

    # 2. Find the matching key in Clerk's JWKS
    jwks = await _fetch_jwks()
    matching_key = _find_key(jwks, kid)

    if matching_key is None:
        # Possibly key rotated — invalidate cache, re-fetch, retry once
        _invalidate_jwks_cache()
        jwks = await _fetch_jwks()
        matching_key = _find_key(jwks, kid)

    if matching_key is None:
        raise ValueError(f"No matching JWKS key for kid: {kid}")

    # 3. Construct public key and verify
    try:
        public_key = jwk.construct(matching_key)
    except JOSEError as e:
        raise ValueError(f"Failed to construct public key: {e}")

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk doesn't always set audience
        )
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTClaimsError as e:
        raise ValueError(f"Invalid JWT claims: {e}")
    except JWTError as e:
        raise ValueError(f"JWT verification failed: {e}")

    # 4. Validate issuer (optional but recommended)
    if settings.CLERK_ISSUER:
        expected_iss = settings.CLERK_ISSUER.rstrip("/")
        actual_iss = claims.get("iss", "").rstrip("/")
        if expected_iss != actual_iss:
            raise ValueError(
                f"Issuer mismatch: expected '{expected_iss}', got '{actual_iss}'"
            )

    return claims


def _find_key(jwks: Dict[str, Any], kid: str) -> Optional[Dict[str, Any]]:
    """Find a JWKS key by kid."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None
