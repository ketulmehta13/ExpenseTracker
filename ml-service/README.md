# Expense Tracker ML service

A FastAPI service that hosts the app's machine-learning features. It reads each user's data through Supabase **with that user's own token**, so Postgres row level security still applies, and it never holds an admin key.

Design notes and interview-style explanations live in [`docs/ai-ml/`](../docs/ai-ml/README.md).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness check, version and loaded model versions |
| GET | `/v1/me` | bearer token | Echoes the signed-in user, for an end-to-end token check |
| POST | `/v1/categorize` | bearer token | Suggests a category for `{title, amount?, type?}`: the user's history first, then the model |
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

Open http://localhost:8000/docs. To use it from the app, set `VITE_ML_API_URL=http://localhost:8000` in `frontend/.env.local`.

To call an authenticated endpoint, copy your access token from the browser (DevTools → Application → Local Storage → `sb-…-auth-token` → `access_token`):

```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/v1/me
```

## Train the categorizer

```bash
python -m training.train_categorizer                       # writes models/categorizer.joblib
python -m training.train_categorizer --min-holdout-f1 0.80 # what CI and the Docker build run
```

Training takes under a minute on a laptop. It writes [`reports/categorizer/model_card.md`](reports/categorizer/model_card.md) (metrics, ablation, confusion matrix, worst mistakes) and `metrics.json`. Without a model file the service still starts, and `/v1/categorize` falls back to history matching only. How the model is built and evaluated is explained in [docs/ai-ml/03-categorizer.md](../docs/ai-ml/03-categorizer.md).

## Test and lint

```bash
pytest
ruff check .
```

The tests run with no network access: `tests/conftest.py` fakes Supabase Auth and PostgREST through an httpx `MockTransport`, and trains a small categorizer once per run.

## Docker

```bash
docker build -t expense-ml-service .
docker run -p 8000:8000 --env-file .env expense-ml-service
```

The build trains the categorizer inside the image, behind the same evaluation gate as CI, so every image ships a model that matches its scikit-learn version. CI builds the image on every push.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SUPABASE_URL` | — | Project URL, e.g. `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | — | Public anon/publishable key |
| `ALLOWED_ORIGINS` | localhost + production URL | CORS origins, comma-separated |
| `AUTH_CACHE_SECONDS` | `60` | How long a validated token is trusted without re-checking |
| `USER_CONTEXT_CACHE_SECONDS` | `60` | How long a user's history and categories are reused between suggestions |
| `MODEL_DIR` | `ml-service/models` | Where trained model files are read from |
