"""Analytics API — dashboard KPIs, resume performance, industry trends."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_auth_context
from app.services.analytics_service import (
    get_industry_trends,
    get_overview_metrics,
    get_resume_performance,
)

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/overview")
async def overview(ctx: dict = Depends(get_auth_context)):
    """High-level dashboard KPIs."""
    return await get_overview_metrics(team_id=ctx["org_id"], profile_id=ctx["profile_id"])


@router.get("/analytics/resumes")
async def resume_performance(ctx: dict = Depends(get_auth_context)):
    """Resume version performance stats."""
    return await get_resume_performance(team_id=ctx["org_id"], profile_id=ctx["profile_id"])


@router.get("/analytics/trends")
async def industry_trends(ctx: dict = Depends(get_auth_context)):
    """Tag-based success rate breakdown."""
    return await get_industry_trends(team_id=ctx["org_id"], profile_id=ctx["profile_id"])
