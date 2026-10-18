# Expense Tracker ML service

A FastAPI service that hosts the app's machine-learning features. It reads each user's data through Supabase **with that user's own token**, so Postgres row level security still applies, and it never holds an admin key.

Design notes and interview-style explanations live in [`docs/ai-ml/`](../docs/ai-ml/README.md).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness check, version and loaded model versions |
| GET | `/v1/me` | bearer token | Echoes the signed-in user, for an end-to-end token check |
| POST | `/v1/categorize` | bearer token | Suggests a category for `{title, amount?, type?}`: the user's history first, then the model |
| GET | `/v1/insights?today=YYYY-MM-DD` | bearer token | Unusual spending, recurring payments and the month-end forecast |
| POST | `/v1/parse` | bearer token | One line of text (`{text, today}`) to a transaction draft with a category suggestion; `llm_filled` lists fields the LLM fallback filled |
| GET | `/v1/insights/summary?today=YYYY-MM-DD` | bearer token | The month in two or three sentences (`source`: `llm` or `template`) |
| POST | `/v1/help` | bearer token | Answers `{question}` from the help center (`knowledge/`), with citations; declines off-topic questions |
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

## Evaluate the insight detectors

```bash
python -m training.evaluate_insights --gate   # what CI runs; about 2 minutes
```

It simulates two groups of users with known answers, tunes every threshold on one and scores on the other, then writes [`reports/insights/report.md`](reports/insights/report.md). The methods are explained in [docs/ai-ml/04-insights.md](../docs/ai-ml/04-insights.md).

## Evaluate the quick-add parser

```bash
python -m training.evaluate_quickadd --gate
```

It scores every field on hand-labelled dev and test sentences against a naive baseline, and lists every test failure in [`reports/quickadd/report.md`](reports/quickadd/report.md). Details are in [docs/ai-ml/05-quickadd.md](../docs/ai-ml/05-quickadd.md).

## Evaluate help-center search

```bash
python -m training.evaluate_rag --gate   # downloads the ~70 MB embedding model on first run
```

It compares keyword, embedding and hybrid search on two chunkings, using hand-labelled dev and test questions, and writes [`reports/rag/report.md`](reports/rag/report.md). Details are in [docs/ai-ml/07-rag.md](../docs/ai-ml/07-rag.md).

## Optional: an LLM

Everything works without one. To let an LLM help with quick add and write the monthly summary, run a free local model with [Ollama](https://ollama.com):

```bash
ollama pull qwen2.5:3b
# in .env: LLM_PROVIDER=ollama and LLM_MODEL=qwen2.5:3b
python -m training.evaluate_llm      # measures it on the quick-add test set and simulated months
```

Any OpenAI-compatible endpoint works too (`LLM_PROVIDER=openai`, `LLM_BASE_URL`, `LLM_API_KEY`). How the output is checked is explained in [docs/ai-ml/06-llm.md](../docs/ai-ml/06-llm.md).

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
| `USER_CONTEXT_CACHE_SECONDS` | `60` | How long a user's history, categories and insights are reused between requests |
| `MODEL_DIR` | `ml-service/models` | Where trained model files are read from |
| `LLM_PROVIDER` | `none` | `none`, `ollama` or `openai` (any OpenAI-compatible endpoint) |
| `LLM_MODEL` | `qwen2.5:3b` | Model name for the provider |
| `LLM_BASE_URL` | Ollama's default | Endpoint URL (for `openai`, the `/v1` base) |
| `LLM_API_KEY` | — | Only for hosted endpoints; never commit it |
| `LLM_TIMEOUT_SECONDS` | `20` | After this, the rules or the template are used |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Help-center embeddings; empty for keyword search only |
| `EMBEDDING_CACHE_DIR` | `ml-service/models/embeddings` | Where the embedding model is stored |
| `KNOWLEDGE_DIR` | `ml-service/knowledge` | The help articles |
