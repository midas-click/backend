"""Backfill job_chunks for existing jobs."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.models.application import ApplicationDocument
from app.models.job import JobDocument
from app.models.job_chunk import JobChunkDocument
from app.models.profile import ProfileDocument
from app.models.resume import ResumeDocument
from app.models.resume_chunk import ResumeChunkDocument
from app.services.job_chunk_service import replace_job_chunks


async def main() -> None:
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGO_DB_NAME]
    await init_beanie(
        database=db,
        document_models=[
            ApplicationDocument,
            ResumeDocument,
            ResumeChunkDocument,
            JobDocument,
            JobChunkDocument,
            ProfileDocument,
        ],
    )

    jobs = await JobDocument.find_all().to_list()
    for job in jobs:
        await replace_job_chunks(job)
        print(f"Embedded job {job.id}: {job.title}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
