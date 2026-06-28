# ITARS — Deployment Guide

A concrete runbook for taking ITARS from a local build to a production
deployment. The codebase is deployment-ready: env-driven config, gitignored
secrets, a backend `Dockerfile`, `docker-compose.yml`, CI, an env-configurable
CORS allowlist, and an optional shared-token API gate.

---

## Overview

| Tier | Service | Notes |
|---|---|---|
| Frontend | **Vercel** | Next.js 16; root `package.json` declares `next` so Vercel detects the framework |
| Backend | **Hugging Face Spaces (Docker)** | FastAPI + uvicorn; model artifacts shipped via Git LFS |
| Database | **Supabase Postgres** | Relational tables (decision log, feedback, queue, analytics) |
| Vector Store | **Supabase pgvector** | Same Postgres as the app DB — no separate service |
| LLM | **Gemini 2.5 Flash** | Verified live; provider swap is config-only |
| Translation | **MarianMT** (Helsinki-NLP) | Lazy-loaded per language family on first use |

---

## Prerequisites

- A host account for the backend (Hugging Face Spaces is the reference target;
  Railway / Fly / a self-hosted Docker host all work).
- A Vercel project for the frontend.
- A Supabase project (free tier is enough) for Postgres + pgvector.
- A Gemini API key for live AI assistance. Without one, the system falls back
  to the deterministic offline `echo` provider.
- The 14 routing artifacts (`*.pkl` + `db_embeddings.npy` + FAISS meta) — in
  this repo they're tracked under `models/` via Git LFS and copied into the
  backend image by the `Dockerfile`.

---

## Environment Variables

Copy `.env.example` to `.env` (the file is gitignored) and fill in:

```env
# Persistence
ITARS_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<pw>@aws-1-<region>.pooler.supabase.com:5432/postgres

# LLM
ITARS_LLM_PROVIDER=gemini
GEMINI_API_KEY=...

# Security (recommended before going public)
ITARS_CORS_ORIGINS=https://itars.vercel.app
ITARS_API_TOKEN=<random-32-byte-hex>      # generate with: python -c "import secrets; print(secrets.token_hex(32))"
```

The frontend reads its API base from `NEXT_PUBLIC_API_URL` and, when the
backend has a token gate, forwards `NEXT_PUBLIC_API_KEY` as `X-API-Key`. Both
are configured in the Vercel project settings.

---

## Database Configuration — Supabase Postgres

Production persistence lives on Supabase Postgres. SQLite still works for
local dev (the default when `ITARS_DATABASE_URL` is unset).

### Pick a connection string

| Mode | Host:Port | Best for | Notes |
|---|---|---|---|
| **Shared pooler — session** | `aws-1-<region>.pooler.supabase.com:5432` | Persistent backend on IPv4 hosts (Hugging Face Spaces, Railway, Fly) | **Recommended** |
| Direct | `db.<ref>.supabase.co:5432` | Backend on an IPv6-capable host | Free tier is IPv6-only |
| Shared pooler — transaction | `aws-1-<region>.pooler.supabase.com:6543` | Serverless / edge functions | Auto-wired with `NullPool` + no prepared statements |

Format the URL like:

```
ITARS_DATABASE_URL=postgresql+psycopg://postgres.<PROJECT-REF>:<DB-PASSWORD>@aws-1-<REGION>.pooler.supabase.com:5432/postgres
```

The driver scheme (`+psycopg`) is normalised automatically — bare
`postgresql://` and the legacy `postgres://` schemes also work. Grab the exact
string + DB password from your Supabase dashboard → **Connect**.

### Schema bootstrapping

The initial schema is provisioned via a tracked Supabase migration
(`initial_itars_schema`). On a fresh project, either:

- run that migration via the Supabase dashboard or `supabase db push`, or
- let the app run `init_db()` on first boot — it's idempotent
  (`CREATE TABLE IF NOT EXISTS`-style) and produces the exact same schema.

---

## Vector Database Configuration — Supabase pgvector

RAG retrieval uses **Supabase pgvector** — the *same* Postgres as the
relational data, so there is **no separate vector database**. The
deterministic routing path still uses FAISS in-process and is unaffected.
With SQLite (local dev), an in-memory fallback is used automatically.

### How it's selected

The store follows `ITARS_DATABASE_URL`. No extra config is required:

| `ITARS_VECTOR_STORE` | Behaviour |
|---|---|
| `auto` (default) | pgvector when the DB is Postgres, else in-memory |
| `pgvector` | Force Supabase pgvector |
| `memory` | Force the in-process fallback (dev / tests) |

```env
# Vectors ride on the same Supabase connection:
ITARS_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<pw>@aws-1-<region>.pooler.supabase.com:5432/postgres

# Optional — defaults are good:
# ITARS_VECTOR_STORE=auto
# ITARS_RAG_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
# ITARS_RAG_EMBEDDING_DIM=384
# ITARS_RAG_SCORE_FLOOR=0.5
```

### Schema

Provisioned via the tracked Supabase migration `pgvector_rag_schema`
(5 collection tables, `vector(384)`, HNSW cosine indexes, RLS enabled). The
app also self-heals via `init_collections()` on boot (idempotent
`CREATE TABLE IF NOT EXISTS`). The `vector` extension must be enabled
(Supabase: Dashboard → Database → Extensions → enable `vector`).

| Collection table | Source | Populated by |
|---|---|---|
| `historical_tickets` | Domain-A corpus / decision log | `python -m scripts.ingest_rag` |
| `feedback_records` | Reviewer overrides | `feedback_service.record_review` |
| `routing_history` | Per-decision log | `scripts.ingest_rag` (optional mirror) |
| `duplicate_clusters` | Pre-clustered nearest-neighbours | Reserved |
| `routing_policies` | Tag→department policy text | Reserved |

---

## Backend Deployment

### Hugging Face Spaces (reference target)

The repo doubles as a Docker-SDK Hugging Face Space — the YAML frontmatter at
the top of `README.md` (`sdk: docker`, `app_port: 8000`) makes it deployable
as-is to a Space. Add the second remote once and push from then on:

```bash
git remote add hf https://huggingface.co/spaces/<user>/<space>
git push hf main
```

Set secrets in the Space's **Settings → Variables and secrets** UI:
`ITARS_DATABASE_URL`, `GEMINI_API_KEY`, `ITARS_CORS_ORIGINS`,
`ITARS_API_TOKEN`. The image is rebuilt automatically on each push; the SBERT
encoders download from the public Hugging Face Hub on the first boot.

### Docker (any host)

```bash
# From the repo root.
docker build -t itars-backend .

docker run -p 8000:8000 \
  -e GEMINI_API_KEY=... \
  -e ITARS_LLM_PROVIDER=gemini \
  -e ITARS_CORS_ORIGINS=https://itars.vercel.app \
  -e ITARS_API_TOKEN=$(openssl rand -hex 24) \
  -e ITARS_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/itars \
  itars-backend
```

`/health` is the readiness probe (never 503s). Encoders warm at boot. The
container runs a single uvicorn worker to avoid a known cold-start race in
the lazy SBERT download from the Hub — bump the worker count only after
pre-baking the encoder weights into the image.

### Full stack locally

```bash
# Backend + Postgres (pgvector) + RAG, from the repo root.
docker compose up --build
```

---

## Frontend Deployment — Vercel

- **Root Directory:** repo root. The Vercel build config (`vercel.json` +
  root `package.json`) drives `cd frontend && npm install && npm run build`.
- **Environment variables (Production):**
  - `NEXT_PUBLIC_API_URL=https://<backend-host>`
  - `NEXT_PUBLIC_API_KEY=<same as backend ITARS_API_TOKEN>` — only when the
    token gate is enabled.
- Framework preset is `nextjs` (declared in `vercel.json`).
- `NEXT_PUBLIC_*` env vars are baked in at build time, so changing one
  requires a redeploy.

---

## Security Lock-down (do before going public)

- [ ] **CORS** — set `ITARS_CORS_ORIGINS` to the exact Vercel origin (the
  default `*` causes the backend to also turn off `allow_credentials`).
- [ ] **API token** — set `ITARS_API_TOKEN` (and the matching
  `NEXT_PUBLIC_API_KEY`) to gate the API. Constant-time compared.
  `/health` + `/docs` stay public; CORS preflight is exempt. Real per-user
  auth (RBAC / Auth.js / Clerk) is the production follow-up.
- [ ] **Supabase RLS** — every table in this project has RLS enabled with
  explicit deny-all-to-anon policies; the backend's service-role bypasses
  RLS. Verify with the Supabase advisor.
- [ ] **Secrets** — set keys via the platform's secret manager (Vercel env,
  HF Space secrets, etc.), never inline in source.

---

## Model Calibration (offline, before launch)

The deterministic routing models keep improving as you tune them on the
deployed traffic distribution. Run these in a Python 3.11 ML env that has
`pandas`, `faiss`, `torch`, and `sentence-transformers >= 5.2.3`:

- [ ] `python -m scripts.regenerate_tag_map --apply` — refit the tag → department
      map against the dataset (closes any majority-mismatched mappings).
- [ ] `python -m scripts.recalibrate_gate --apply` — refit the two-stage
      confidence-gate floors against the live hybrid-confidence distribution.
- [ ] `pytest tests/test_pipeline_smoke.py` — confirm end-to-end routing
      parity after recalibration.

---

## Production Verification

After deploying, verify with these curl probes:

```bash
# Liveness — public, no auth needed
curl https://<backend-host>/health
# {"status":"ok", "encoders_loaded":true, "database_mode":"postgresql", "vector_store_mode":"pgvector", ...}

# RAG store state
curl -H "X-API-Key: $TOKEN" https://<backend-host>/rag/health
# {"vector_store_mode":"pgvector", "collections":{"historical_tickets":N, ...}}

# LLM provider
curl -H "X-API-Key: $TOKEN" https://<backend-host>/llm/health
# {"primary":"gemini", "providers":{"gemini":{"available":true}, ...}}

# Token gate
curl -o /dev/null -w "%{http_code}\n" https://<backend-host>/tickets/recent     # → 401
curl -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $TOKEN" https://<backend-host>/tickets/recent  # → 200

# Frontend
curl -o /dev/null -w "%{http_code}\n" https://itars.vercel.app/                  # → 200
curl -o /dev/null -w "%{http_code}\n" https://itars.vercel.app/all-tickets       # → 200
```

---

## CI / CD

`.github/workflows/ci.yml` runs on every push and PR: backend `pytest`
(Python 3.11, full deps, excluding the artifact-dependent smoke test) +
frontend `lint` and `build` (Node 20) + a Docker image build. Wire
preview / production deploys via Vercel's GitHub integration and the
backend host's deploy hook on merge to `main`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| HF Space worker crashes on boot with `RuntimeError: unable to open file …/model.safetensors … No such file or directory` | Multiple workers racing the lazy HF Hub SBERT download | Keep `--workers 1` in the `Dockerfile` (default), or pre-download the encoders in a `RUN` step before bumping workers up. |
| Vercel build fails with `No Next.js version detected` | `installCommand` didn't install at the Root Directory before Vercel's framework probe | `vercel.json` declares `framework: "nextjs"` and runs `npm install` at root before the frontend install — keep it that way. |
| `/analyze-ticket` returns HTTP 500 `ForeignKeyViolation … duplicate_results_ticket_id_fkey` | The parent ticket row hasn't flushed before child INSERTs | `save_analysis` issues `session.flush()` after the Ticket merge — verify the fix is present if you've refactored persistence. |
| Supabase pooler returns `Could not connect to server` | Wrong AWS host suffix for the region | ap-southeast-2 (Sydney) is served by `aws-1-*.pooler.supabase.com`, not `aws-0-*`. The engine auto-remediates this if a stale URL slips in. |
| Translation requests return `There was an error parsing the body` | Local terminal mangled the UTF-8 payload | Send the request body as a UTF-8 file: `curl --data-binary @body.json -H "Content-Type: application/json; charset=utf-8"`. |
| Frontend Services dropdown shows everything as 401 | `NEXT_PUBLIC_API_KEY` env var missing or stale (changed after the last build) | Set it in Vercel **Production** env vars and trigger a redeploy — `NEXT_PUBLIC_*` is baked in at build time. |

---

## Open Improvements (post-launch)

- Alembic-driven schema migrations + data backfill, replacing the
  idempotent `init_db()` bootstrap.
- Persist the in-process `BudgetTracker` and `Metrics` counters to SQL so
  they survive a worker restart.
- Rate limiting + request-id correlation in structured logs.
