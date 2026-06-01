"""Backfill existing job and resume vectors into Pinecone."""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.models.application import ApplicationDocument
from app.models.job import JobDocument
from app.models.profile import ProfileDocument
from app.models.resume import ResumeDocument
from app.services.vector_store_service import (
    chunk_job,
    chunk_resume_sections,
    upsert_job_chunks,
    upsert_resume_chunks,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Pinecone vectors for jobs and resumes.")
    parser.add_argument("--dry-run", action="store_true", help="Count chunks without writing to Pinecone or MongoDB.")
    args = parser.parse_args()

    client = AsyncIOMotorClient(settings.MONGODB_URI)
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

    job_docs = await db.jobs.find({}).to_list(length=None)
    job_count = 0
    job_chunk_count = 0
    for raw_doc in job_docs:
        job = await JobDocument.get(str(raw_doc["_id"]))
        if not job:
            continue
        source_text = raw_doc.get("description")
        if args.dry_run:
            chunks = chunk_job(job, source_text)
        else:
            chunks = await upsert_job_chunks(job, source_text)
            job.vector_store = settings.VECTOR_STORE
            job.vector_chunk_count = len(chunks)
            job.embedding_status = "completed"
            job.embedding_error = None
            job.embedded_at = datetime.now(UTC)
            await job.save()
            await db.jobs.update_one(
                {"_id": raw_doc["_id"]},
                {"$unset": {"description": "", "user_id": "", "org_id": "", "org_name": ""}},
            )
        job_count += 1
        job_chunk_count += len(chunks)
        print(f"{'Would embed' if args.dry_run else 'Embedded'} job {job.id}: {len(chunks)} chunks")

    resumes = await ResumeDocument.find_all().to_list()
    resume_count = 0
    resume_chunk_count = 0
    for resume in resumes:
        if args.dry_run:
            chunks = chunk_resume_sections(resume.sections)
        else:
            chunks = await upsert_resume_chunks(resume, resume.sections)
            resume.vector_store = settings.VECTOR_STORE
            resume.vector_chunk_count = len(chunks)
            resume.embedding_status = "completed"
            resume.embedding_error = None
            resume.embedded_at = datetime.now(UTC)
            await resume.save()
        resume_count += 1
        resume_chunk_count += len(chunks)
        print(f"{'Would embed' if args.dry_run else 'Embedded'} resume {resume.id}: {len(chunks)} chunks")

    print(
        "Backfill summary: "
        f"jobs={job_count} job_chunks={job_chunk_count} "
        f"resumes={resume_count} resume_chunks={resume_chunk_count} dry_run={args.dry_run}"
    )
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
