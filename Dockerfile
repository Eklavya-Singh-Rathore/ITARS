# ITARS V2 backend container.  Build context = the main/ directory:
#     docker build -t itars-backend .
#     docker build -t itars-backend --build-arg INSTALL_POSTGRES=true .   # for Postgres
#
# Model artifacts (the 14 .pkl + db_embeddings.npy + faiss meta, ~560 MB) are NOT
# baked into the image. Mount them at /models and the fine-tuned SBERT encoders
# download from the public HF Hub on first boot (cached in the hf volume).
#
# Note: the ML stack (torch + faiss + transformers) makes this a large image.
# For a slimmer build, install the CPU-only torch wheel
# (`--index-url https://download.pytorch.org/whl/cpu`) before requirements.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/hf \
    ITARS_MODEL_DIR=/models \
    ITARS_DATA_DIR=/data

WORKDIR /app

# Runtime libs some wheels need (libgomp for xgboost/faiss/torch); curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# psycopg[binary] is now a regular dependency (Phase 15A) — Supabase / Postgres
# is the production target. SQLite still works locally without extra setup.
RUN pip install -r requirements.txt

COPY backend ./backend
COPY config ./config

EXPOSE 8000

# /health never 503s and reports readiness; generous start period for model warm-up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Each uvicorn worker holds its own warm encoders + FAISS index (per-worker memory cost).
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
