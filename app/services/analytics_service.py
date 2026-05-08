"""Analytics service — MongoDB aggregation pipelines for dashboard insights."""

from typing import Any, Dict, List

from app.models.application import ApplicationDocument
from app.models.resume import ResumeDocument


async def get_overview_metrics(user_id: str = "default") -> Dict[str, Any]:
    """Return high-level KPIs: totals, conversion rates, stage distribution."""
    pipeline = [
        {"$match": {"user_id": user_id}},
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
    return {
        "total_applications": total,
        "interview_rate": round(interview_count / total * 100, 1) if total else 0,
        "offer_rate": round(offer_count / total * 100, 1) if total else 0,
        "rejection_rate": round(rejection_count / total * 100, 1) if total else 0,
        "by_stage": {item["_id"]: item["count"] for item in facet["by_stage"]},
    }


async def get_resume_performance(user_id: str = "default") -> list[Dict[str, Any]]:
    """Return how each resume version has performed (app count, interview count)."""
    resumes = await ResumeDocument.find(
        ResumeDocument.user_id == user_id,
    ).to_list()

    if not resumes:
        return []

    resume_ids = [str(r.id) for r in resumes]

    # Count applications linked to each resume
    pipeline = [
        {"$match": {"resume_ids": {"$in": resume_ids}}},
        {"$unwind": "$resume_ids"},
        {"$group": {
            "_id": "$resume_ids",
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
            "version": r.version,
            "applications": stats_map.get(str(r.id), {}).get("applications", 0),
            "interviews": stats_map.get(str(r.id), {}).get("interviews", 0),
            "offers": stats_map.get(str(r.id), {}).get("offers", 0),
        }
        for r in resumes
    ]


async def get_industry_trends(user_id: str = "default") -> list[Dict[str, Any]]:
    """Group by tag (industry/tech stack) and show success rates."""
    pipeline = [
        {"$match": {"user_id": user_id}},
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
    }
