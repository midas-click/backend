"""Profiles API — CRUD for user-created sub-accounts within a team."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_auth_context
from app.models.profile import ProfileCreate, ProfileDocument, ProfileUpdate

router = APIRouter(tags=["Profiles"])


# ── LIST ──────────────────────────────────────────
@router.get("/profiles", response_model=List[ProfileDocument])
async def list_profiles(ctx: dict = Depends(get_auth_context)):
    """List all profiles for the current user in the active organization."""
    return (
        await ProfileDocument.find(
            ProfileDocument.user_id == ctx["user_id"],
            ProfileDocument.org_id == ctx["org_id"],
        )
        .sort("-created_at")
        .to_list()
    )


# ── GET ───────────────────────────────────────────
@router.get("/profiles/{profile_id}", response_model=ProfileDocument)
async def get_profile(profile_id: str, ctx: dict = Depends(get_auth_context)):
    profile = await ProfileDocument.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.org_id != ctx["org_id"]:
        raise HTTPException(status_code=403, detail="Profile does not belong to this organization")
    return profile


# ── CREATE ────────────────────────────────────────
@router.post(
    "/profiles",
    response_model=ProfileDocument,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    payload: ProfileCreate,
    ctx: dict = Depends(get_auth_context),
):
    profile = ProfileDocument(
        user_id=ctx["user_id"],
        org_id=ctx["org_id"],
        name=payload.name,
        email=payload.email,
        headline=payload.headline,
    )
    return await profile.insert()


# ── UPDATE ────────────────────────────────────────
@router.patch("/profiles/{profile_id}", response_model=ProfileDocument)
async def update_profile(
    profile_id: str,
    payload: ProfileUpdate,
    ctx: dict = Depends(get_auth_context),
):
    profile = await ProfileDocument.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.org_id != ctx["org_id"]:
        raise HTTPException(status_code=403, detail="Profile does not belong to this organization")
    if profile.user_id != ctx["user_id"] and ctx["org_role"] not in ("org:admin", "org:manager"):
        raise HTTPException(status_code=403, detail="Cannot edit another user's profile")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    return await profile.save()


# ── DELETE ────────────────────────────────────────
@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, ctx: dict = Depends(get_auth_context)):
    profile = await ProfileDocument.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.org_id != ctx["org_id"]:
        raise HTTPException(status_code=403, detail="Profile does not belong to this organization")
    if profile.user_id != ctx["user_id"] and ctx["org_role"] not in ("org:admin", "org:manager"):
        raise HTTPException(status_code=403, detail="Cannot delete another user's profile")
    await profile.delete()
