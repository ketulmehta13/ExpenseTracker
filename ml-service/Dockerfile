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
# Train during the build: fixed seeds make it reproducible, the model always matches the
# installed scikit-learn, and the evaluation gate keeps a weak model out of every image
RUN python -m training.train_categorizer --min-holdout-f1 0.80

# Run as an unprivileged user
RUN useradd --create-home appuser && chown -R appuser /srv/models
USER appuser

EXPOSE 8000
# Hosts such as Render, Railway and Cloud Run set PORT; default to 8000 locally
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
