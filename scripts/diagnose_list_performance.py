"""Read-only diagnostics for job/application list query performance."""

import asyncio
import json
import sys
from pathlib import Path
from pprint import pprint
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


async def main() -> None:
    client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        readPreference="secondaryPreferred",
        serverSelectionTimeoutMS=8000,
    )
    db = client[settings.MONGO_DB_NAME]

    for name in ["jobs", "applications"]:
        print(f"\n## {name}")
        indexes = await db[name].index_information()
        print("count:", await db[name].estimated_document_count())
        print("indexes:")
        print(json.dumps({key: value.get("key") for key, value in indexes.items()}, indent=2, default=str))

    profile_id = await db.applications.find_one(
        {"profile_id": {"$type": "string"}},
        projection={"profile_id": 1, "org_id": 1},
        sort=[("updated_at", -1)],
    )
    if not profile_id:
        print("\nNo profile-scoped applications found for explain samples.")
        client.close()
        return

    org_id = profile_id["org_id"]
    active_profile_id = profile_id["profile_id"]

    print("\n## sample profile")
    print({"org_id": org_id, "profile_id": active_profile_id})

    print("\n## applications list explain")
    apps_explain = await db.command({
        "explain": {
            "find": "applications",
            "filter": {"org_id": org_id, "profile_id": active_profile_id},
            "sort": {"updated_at": -1, "_id": -1},
            "limit": 31,
        },
        "verbosity": "executionStats",
    })
    pprint(_summarize_explain(apps_explain))

    print("\n## recent applied jobs helper explain")
    recent_explain = await db.command({
        "explain": {
            "find": "applications",
            "filter": {"profile_id": active_profile_id},
            "projection": {"job_id": 1},
            "sort": {"created_at": -1},
        },
        "verbosity": "executionStats",
    })
    pprint(_summarize_explain(recent_explain))

    print("\n## jobs list explain")
    jobs_explain = await db.command({
        "explain": {
            "find": "jobs",
            "filter": {},
            "sort": {"created_at": -1, "_id": -1},
            "limit": 31,
        },
        "verbosity": "executionStats",
    })
    pprint(_summarize_explain(jobs_explain))

    client.close()


def _summarize_explain(explain: dict[str, Any]) -> dict[str, Any]:
    stats = explain.get("executionStats", {})
    return {
        "executionTimeMillis": stats.get("executionTimeMillis"),
        "nReturned": stats.get("nReturned"),
        "totalDocsExamined": stats.get("totalDocsExamined"),
        "totalKeysExamined": stats.get("totalKeysExamined"),
        "winningPlan": _plan_summary(explain.get("queryPlanner", {}).get("winningPlan", {})),
    }


def _plan_summary(plan: dict[str, Any]) -> Any:
    if not plan:
        return {}
    stage = plan.get("stage")
    input_stage = plan.get("inputStage")
    if stage == "FETCH" and isinstance(input_stage, dict):
        return {"stage": stage, "input": _plan_summary(input_stage)}
    if stage == "SORT" and isinstance(input_stage, dict):
        return {"stage": stage, "input": _plan_summary(input_stage)}
    if stage == "LIMIT" and isinstance(input_stage, dict):
        return {"stage": stage, "input": _plan_summary(input_stage)}
    if stage == "IXSCAN":
        return {
            "stage": stage,
            "indexName": plan.get("indexName"),
            "direction": plan.get("direction"),
            "indexBounds": plan.get("indexBounds"),
        }
    if stage == "COLLSCAN":
        return {"stage": stage, "direction": plan.get("direction")}
    return {
        "stage": stage,
        "input": _plan_summary(input_stage) if isinstance(input_stage, dict) else None,
    }


if __name__ == "__main__":
    asyncio.run(main())
