# Expense Tracker ML service

A FastAPI service that hosts the app's machine-learning features. It reads each user's data through Supabase **with that user's own token**, so Postgres row level security still applies, and it never holds an admin key.

Design notes and interview-style explanations live in [`docs/ai-ml/`](../docs/ai-ml/README.md).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness check and version |
| GET | `/v1/me` | bearer token | Echoes the signed-in user, for an end-to-end token check |
| GET | `/docs` | none | Interactive OpenAPI docs |

## Run locally

```bash
cd ml-service
python -m venv venv
venv/Scripts/activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env             # then fill in SUPABASE_URL and SUPABASE_ANON_KEY
uvicorn app.main:app --reload --env-file .env
```

Open http://localhost:8000/docs.

To call an authenticated endpoint, copy your access token from the browser (DevTools → Application → Local Storage → `sb-…-auth-token` → `access_token`):

```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/v1/me
```

## Test and lint

```bash
pytest
ruff check .
```

The tests run with no network access: `tests/conftest.py` fakes Supabase Auth and PostgREST through an httpx `MockTransport`.

## Docker

```bash
docker build -t expense-ml-service .
docker run -p 8000:8000 --env-file .env expense-ml-service
```

CI builds the image on every push.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SUPABASE_URL` | — | Project URL, e.g. `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | — | Public anon/publishable key |
| `ALLOWED_ORIGINS` | localhost + production URL | CORS origins, comma-separated |
| `AUTH_CACHE_SECONDS` | `60` | How long a validated token is trusted without re-checking |
| `MODEL_DIR` | `ml-service/models` | Where trained model files are read from |
