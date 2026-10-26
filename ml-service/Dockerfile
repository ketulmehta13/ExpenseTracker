FROM python:3.13-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY training ./training
COPY knowledge ./knowledge
# Bake the help-center embedding model into the image, so a new server never downloads it
RUN python -c "from app.config import Settings; from app.rag.embeddings import load_embedder; s = Settings(); assert load_embedder(s.embedding_model, s.embedding_cache_dir)"
# ...and the copilot's knowledge-base embedding model (gte-small, ~34 MB)
RUN python -c "from app.config import DEFAULT_MODEL_DIR as d; from app.rag.embeddings import GTE_SMALL, load_embedder; assert load_embedder(GTE_SMALL, d / 'embeddings')"
# ...and a snapshot of the embedded knowledge base: the copilot's fallback while Supabase is unreachable
RUN python -m training.ingest_kb --snapshot models/kb_snapshot.npz
# The same for the bill-scanning OCR models: reading a blank page once downloads them
RUN python -c "import numpy as np; from app.receipts.ocr import load_engine; load_engine()(np.full((64, 64, 3), 255, np.uint8))"
# Train during the build: fixed seeds make it reproducible, the model always matches the
# installed scikit-learn, and the evaluation gate keeps a weak model out of every image
RUN python -m training.train_categorizer --min-holdout-f1 0.80

# Run as an unprivileged user
RUN useradd --create-home appuser && chown -R appuser /srv/models
USER appuser

EXPOSE 8000
# Hosts such as Render, Railway and Cloud Run set PORT; default to 8000 locally
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
