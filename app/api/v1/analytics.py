"""Analytics API — dashboard KPIs, resume performance, industry trends."""

from fastapi import APIRouter

from app.services.analytics_service import (
    get_industry_trends,
    get_overview_metrics,
    get_resume_performance,
)

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/overview")
async def overview(user_id: str = "default"):
    """High-level dashboard KPIs."""
    return await get_overview_metrics(user_id)


@router.get("/analytics/resumes")
async def resume_performance(user_id: str = "default"):
    """Resume version performance stats."""
    return await get_resume_performance(user_id)


@router.get("/analytics/trends")
async def industry_trends(user_id: str = "default"):
    """Tag-based success rate breakdown."""
    return await get_industry_trends(user_id)
