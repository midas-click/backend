"""MongoDB connection management (Motor + Beanie ODM)."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie

from app.config import settings
from app.models.application import ApplicationDocument
from app.models.resume import ResumeDocument
from app.models.job import JobDocument
from app.models.profile import ProfileDocument

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
            JobDocument,
            ProfileDocument,
        ],
    )


async def close_mongo_connection() -> None:
    global _client
    if _client:
        _client.close()


def get_db() -> AsyncIOMotorDatabase:
    assert _db is not None, "Database not initialised"
    return _db
