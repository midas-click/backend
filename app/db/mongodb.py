"""MongoDB connection management (Motor + Beanie ODM)."""

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.models.application import ApplicationDocument
from app.models.job import JobDocument
from app.models.profile import ProfileDocument
from app.models.resume import ResumeDocument
from app.models.resume_chunk import ResumeChunkDocument

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _db = _client[settings.MONGO_DB_NAME]

    await init_beanie(
        database=_db,
        document_models=[
            ApplicationDocument,
            ResumeDocument,
            ResumeChunkDocument,
            JobDocument,
            ProfileDocument,
        ],
    )


async def close_mongo_connection() -> None:
    global _client
    if _client:
        _client.close()
