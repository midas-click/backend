"""Create current Beanie indexes and drop obsolete high-write collection indexes."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.models.application import ApplicationDocument
from app.models.job import JobDocument
from app.models.profile import ProfileDocument
from app.models.resume import ResumeDocument

OBSOLETE_INDEXES = {
    "jobs": {
        "user_id_1",
        "org_id_1",
        "company_1",
        "created_at_1",
        "created_at_1_company_1",
    },
    "applications": {
        "user_id_1",
        "stage_1",
        "company_1",
        "tags_1",
        "updated_at_1",
        "user_id_1_stage_1",
        "org_id_1_profile_id_1_stage_1_updated_at_1",
    },
}


async def main() -> None:
    client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        connectTimeoutMS=10000,
        serverSelectionTimeoutMS=10000,
    )
    db = client[settings.MONGO_DB_NAME]

    await init_beanie(
        database=db,
        document_models=[
            ApplicationDocument,
            ResumeDocument,
            JobDocument,
            ProfileDocument,
        ],
    )

    for collection_name, index_names in OBSOLETE_INDEXES.items():
        collection = db[collection_name]
        existing = await collection.index_information()
        for index_name in sorted(index_names & existing.keys()):
            print(f"Dropping {collection_name}.{index_name}")
            await collection.drop_index(index_name)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
