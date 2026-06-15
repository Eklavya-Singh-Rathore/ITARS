# ITARS V2 — Deployment Guide (Phase 14)

Concrete runbook for taking the local build to a public deployment. The codebase
is deployment-ready: env-driven config, gitignored secrets, a backend
`Dockerfile`, `docker-compose.yml`, CI, and env-configurable CORS + optional API
token.

## Target topology

| Tier | Service | Notes |
|---|---|---|
| Frontend | **Vercel** | Next.js 16; root directory = `main/frontend` |
| Backend | **Railway / Fly / HF Spaces (Docker)** | FastAPI + uvicorn; needs the model volume |
| Vector DB | **Qdrant Cloud** (free tier) | or self-hosted via `docker-compose.yml` |
| Database | **Postgres** (Railway/Neon addon) | SQLite is fine for a demo |
| Models | **HF Hub** (public encoders) + mounted artifact volume | the 14 `.pkl` are not baked into the image |
| LLM | **Gemini 2.5 Flash** | verified working; key in `main/.env` |

## Prerequisites

- A host account for the backend (Railway / Fly / HF Spaces), Vercel for the
  frontend, and optionally Qdrant Cloud + Postgres.
- The model artifacts (`hf_deploy/Models`, `hf_deploy/Data`) available to mount —
  these are large and live outside the image.
- The pre-deploy ML steps below run in the author's Python 3.11 ML env (this
  repo's dev host lacks `pandas`/`faiss`/`torch`).

## 1. Backend (Docker)

```bash
# From the repo root.
# Build (add --build-arg INSTALL_POSTGRES=true for a Postgres deploy).
docker build -t itars-backend .

docker run -p 8000:8000 \
  -e GEMINI_API_KEY=...                         # never committed \
  -e ITARS_LLM_PROVIDER=gemini \
  -e ITARS_CORS_ORIGINS=https://itars.vercel.app \
  -e ITARS_API_TOKEN=$(openssl rand -hex 24)    # optional shared gate \
  -e ITARS_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/itars \
  -e ITARS_QDRANT_URL=https://xyz.qdrant.cloud -e ITARS_QDRANT_API_KEY=... \
  -v /path/to/hf_deploy/Models:/models:ro \
  -v /path/to/hf_deploy/Data:/data:ro \
  itars-backend
```

`/health` is the readiness probe (never 503s). Encoders warm at boot; the SBERT
weights download from the public HF Hub on first run.

### Full stack locally

```bash
# From the repo root.
export ITARS_MODELS_PATH=/abs/path/to/Models
export ITARS_DATA_PATH=/abs/path/to/Data
GEMINI_API_KEY=... docker compose up --build      # backend + Qdrant + Postgres
```

## 2. Frontend (Vercel)

- **Root Directory:** `frontend` (the app is in a subdirectory of the repo).
- **Env vars:** `NEXT_PUBLIC_API_URL=https://<backend-host>` and, if the backend
  sets `ITARS_API_TOKEN`, `NEXT_PUBLIC_API_KEY=<same token>` (basic gating only —
  it is bundled into the browser).
- Framework preset auto-detects Next.js; build = `npm run build`.

## 3. Security lock-down (do before going public)

- [ ] **CORS** — set `ITARS_CORS_ORIGINS` to the exact Vercel origin (defaults to
      `*`, which the code turns off `allow_credentials` for).
- [ ] **API token** — set `ITARS_API_TOKEN` (and the matching `NEXT_PUBLIC_API_KEY`)
      to gate the API. `/health` + `/docs` stay public. Real per-user auth (RBAC /
      Auth.js) is the production follow-up.
- [ ] **Secrets** — set keys via the platform's secret manager, never in source.

## 4. ML pre-deploy (author's env) — free accuracy

- [ ] `python -m scripts.regenerate_tag_map --apply` — fix the 12/28 majority-mismatched tag→dept mappings.
- [ ] `python -m scripts.recalibrate_gate --apply` — refit the Stage-1 floor so it actually fires.
- [ ] `pytest tests/test_pipeline_smoke.py` — confirm V2 routing parity with V1.

## 5. CI

`.github/workflows/ci.yml` runs on push/PR: backend `pytest` (py3.11, full deps,
excluding the artifact-dependent smoke test) + frontend `lint` & `build` (node 20).
Wire preview/prod deploys via the Vercel GitHub integration and the host's deploy
hook on merge to `main`.

## Still open (post-launch)

- Alembic migrations + data backfill from `itars.db` to Postgres (today the schema
  is `create_all`-ed on first boot, which also works on Postgres).
- Persist the in-process `BudgetTracker` / `Metrics` to SQL so they survive restarts.
- Rate limiting + request-id correlation in structured logs.
