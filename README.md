# MidasClick Backend

FastAPI API for job capture, resume parsing, application tracking, analytics, and resume/job matching.

## Tech Stack

- Python 3.12+
- FastAPI + Uvicorn
- MongoDB with Beanie/Motor
- Amazon SQS + Celery for background embedding jobs
- AWS S3 for resume file storage
- Clerk JWT verification
- OpenAI-compatible LLM client for job extraction
- FastEmbed BGE embeddings for match scoring

## Environment

The backend reads settings from this directory's `.env` file via `app/config.py`.

```powershell
Copy-Item .env.example .env
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

For background embeddings, SQS/Celery use:

```env
AWS_REGION=us-east-2
CELERY_BROKER_URL=sqs://
CELERY_TASK_DEFAULT_QUEUE=midas-celery
SQS_QUEUE_URL=https://sqs.us-east-2.amazonaws.com/123456789012/midas-celery
SQS_VISIBILITY_TIMEOUT=3600
SQS_WAIT_TIME_SECONDS=20
SQS_POLLING_INTERVAL=1
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

Create an SQS queue named `midas-celery`, then set `SQS_QUEUE_URL` for both the API and worker environments.

Run Celery from `backend/`:

```powershell
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info --pool=solo
```

On Linux/macOS, this also works:

```bash
celery -A app.worker.celery_app:celery_app worker --loglevel=info --concurrency=1
```

In ECS, grant the task role SQS permissions for the queue:

```text
sqs:GetQueueUrl
sqs:GetQueueAttributes
sqs:SendMessage
sqs:ReceiveMessage
sqs:DeleteMessage
sqs:ChangeMessageVisibility
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
