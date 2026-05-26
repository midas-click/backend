# MidasClick Backend

FastAPI API for job capture, resume parsing, application tracking, analytics, and resume/job matching.

## Tech Stack

- Python 3.12+
- FastAPI + Uvicorn
- MongoDB with Beanie/Motor
- Redis + Celery for background embedding jobs
- AWS S3 for resume file storage
- Clerk JWT verification
- OpenAI-compatible LLM client for job extraction
- FastEmbed BGE embeddings for match scoring

## Environment

The backend reads settings from the repository root `.env` file via `backend/app/config.py`.

```powershell
Copy-Item .env.example.backend .env
```

Required for normal local development:

```env
MONGODB_URI=
MONGO_DB_NAME=
CLERK_JWKS_URL=
CLERK_ISSUER=
LLM_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET_NAME=
CORS_ORIGINS=http://localhost:5173
```

For background embeddings, Redis/Celery use:

```env
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
EMBEDDINGS_ENABLED=true
EMBEDDINGS_ASYNC_ENABLED=true
```

## Run Locally

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs:

```text
http://localhost:8000/docs
```

Health check:

```text
http://localhost:8000/health
```

## Background Worker

Start Redis from the repository root:

```powershell
docker compose up -d redis
```

Run Celery from `backend/`:

```powershell
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info --pool=solo
```

On Linux/macOS, this also works:

```bash
celery -A app.worker.celery_app:celery_app worker --loglevel=info --concurrency=1
```

## Database Indexes

After changing indexes or setting up a new database:

```powershell
python scripts/sync_indexes.py
```

Atlas Vector Search indexes are documented in:

- `scripts/resume_chunks_vector_index.json`
- `scripts/job_chunks_vector_index.json`

Create those manually in MongoDB Atlas when vector search is enabled.

## Tests

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Key Modules

- `app/api/v1/` - FastAPI routers
- `app/models/` - Beanie documents and request/response models
- `app/services/llm_service.py` - job field extraction
- `app/services/embedding_service.py` - local embedding generation
- `app/services/match_score_service.py` - resume/job scoring
- `app/worker/embedding_tasks.py` - Celery embedding tasks
- `scripts/sync_indexes.py` - MongoDB index sync
