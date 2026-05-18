"""Analytics service — MongoDB aggregation pipelines for dashboard insights."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.models.application import ApplicationDocument
from app.models.job import JobDocument
from app.models.resume import ResumeDocument


def _scope_filter(org_id: str, profile_id: Optional[str]) -> dict:
    """Build a base match filter for the given scope."""
    f: dict = {"org_id": org_id}
    if profile_id:
        f["profile_id"] = profile_id
    return f


async def get_overview_metrics(
    org_id: str,
    profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return high-level KPIs: totals, conversion rates, stage distribution."""
    base_filter = _scope_filter(org_id, profile_id)

    # Compute date boundaries for this-month filter
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_month = datetime(now.year, now.month, 1)

    pipeline = [
        {"$match": {**base_filter, "created_at": {"$gte": since_month}}},
        {
            "$facet": {
                "by_stage": [
                    {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
                ],
                "total": [
                    {"$count": "count"},
                ],
                "with_interview": [
                    {"$match": {"stage": {"$in": [
                        "phone_screen",
                        "technical",
                        "team_interview",
                        "offer",
                    ]}}},
                    {"$count": "count"},
                ],
                "offers": [
                    {"$match": {"stage": "offer"}},
                    {"$count": "count"},
                ],
                "rejections": [
                    {"$match": {"stage": "rejected"}},
                    {"$count": "count"},
                ],
            },
        },
    ]

    results = await ApplicationDocument.aggregate(pipeline).to_list(1)
    if not results:
        return _empty_overview()

    facet = results[0]
    total = facet["total"][0]["count"] if facet["total"] else 0
    interview_count = facet["with_interview"][0]["count"] if facet["with_interview"] else 0
    offer_count = facet["offers"][0]["count"] if facet["offers"] else 0
    rejection_count = facet["rejections"][0]["count"] if facet["rejections"] else 0

    # Count jobs added in the last 24 hours (all users)
    jobs_last_24h = await JobDocument.find({"created_at": {"$gte": since_24h}}).count()

    # Count jobs added this month (all users)
    jobs_this_month = await JobDocument.find({"created_at": {"$gte": since_month}}).count()

    # Count applications created in the last 24 hours (scoped to org+profile)
    apps_last_24h = await ApplicationDocument.find(
        {**base_filter, "created_at": {"$gte": since_24h}}
    ).count()

    return {
        "total_applications": total,
        "interview_rate": round(interview_count / total * 100, 1) if total else 0,
        "offer_rate": round(offer_count / interview_count * 100, 1) if interview_count else 0,
        "rejection_rate": round(rejection_count / total * 100, 1) if total else 0,
        "by_stage": {item["_id"]: item["count"] for item in facet["by_stage"]},
        "jobs_last_24h": jobs_last_24h,
        "jobs_this_month": jobs_this_month,
        "applications_last_24h": apps_last_24h,
        "applications_this_month": total,
    }


async def get_resume_performance(
    org_id: str,
    profile_id: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """Return how each resume version has performed (app count, interview count)."""
    resume_filter = {"org_id": org_id}
    if profile_id:
        resume_filter["profile_id"] = profile_id

    resumes = await ResumeDocument.find(resume_filter).to_list()

    if not resumes:
        return []

    resume_ids = [str(r.id) for r in resumes]

    # Count applications linked to each resume
    pipeline = [
        {"$match": {"resume_id": {"$in": resume_ids}}},
        {"$group": {
            "_id": "$resume_id",
            "applications": {"$sum": 1},
            "interviews": {
                "$sum": {
                    "$cond": [{"$in": ["$stage", [
                        "phone_screen",
                        "technical",
                        "team_interview",
                        "offer",
                    ]]}, 1, 0],
                },
            },
            "offers": {
                "$sum": {"$cond": [{"$eq": ["$stage", "offer"]}, 1, 0]},
            },
        }},
    ]

    stats = await ApplicationDocument.aggregate(pipeline).to_list(None)
    stats_map = {s["_id"]: s for s in stats}

    return [
        {
            "id": str(r.id),
            "filename": r.original_filename,
            "applications": stats_map.get(str(r.id), {}).get("applications", 0),
            "interviews": stats_map.get(str(r.id), {}).get("interviews", 0),
            "offers": stats_map.get(str(r.id), {}).get("offers", 0),
        }
        for r in resumes
    ]


async def get_industry_trends(
    org_id: str,
    profile_id: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """Group by tag (industry/tech stack) and show success rates."""
    base_filter = _scope_filter(org_id, profile_id)

    pipeline = [
        {"$match": base_filter},
        {"$unwind": "$tags"},
        {"$group": {
            "_id": "$tags",
            "total": {"$sum": 1},
            "interviews": {
                "$sum": {
                    "$cond": [{"$in": ["$stage", [
                        "phone_screen",
                        "technical",
                        "team_interview",
                        "offer",
                    ]]}, 1, 0],
                },
            },
            "offers": {
                "$sum": {"$cond": [{"$eq": ["$stage", "offer"]}, 1, 0]},
            },
        }},
        {"$sort": {"total": -1}},
        {"$limit": 20},
    ]

    rows = await ApplicationDocument.aggregate(pipeline).to_list(None)
    return [
        {
            "tag": r["_id"],
            "total": r["total"],
            "interview_rate": round(r["interviews"] / r["total"] * 100, 1) if r["total"] else 0,
            "offer_rate": round(r["offers"] / r["total"] * 100, 1) if r["total"] else 0,
        }
        for r in rows
    ]


def _empty_overview() -> Dict[str, Any]:
    return {
        "total_applications": 0,
        "interview_rate": 0,
        "offer_rate": 0,
        "rejection_rate": 0,
        "by_stage": {},
        "jobs_last_24h": 0,
        "jobs_this_month": 0,
        "applications_last_24h": 0,
        "applications_this_month": 0,
    }
