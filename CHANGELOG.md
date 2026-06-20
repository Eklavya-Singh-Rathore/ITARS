# Changelog

## [Unreleased]

### Phase 15B — Supabase pgvector (vector store)
- Replaced the ephemeral in-memory Qdrant vector layer with **Supabase
  pgvector** — RAG vectors now live in the same Postgres as the relational data,
  so retrieval survives a container/HF-Space restart.
- New `PgVectorStore` (cosine `<=>` over HNSW indexes) + an `InMemoryVectorStore`
  dev/test fallback; selection is automatic from the database URL
  (`ITARS_VECTOR_STORE=auto`).
- 5 collection tables (`historical_tickets`, `duplicate_clusters`,
  `routing_history`, `feedback_records`, `routing_policies`) with `vector(384)`,
  HNSW cosine indexes, and RLS enabled — provisioned via the tracked migration
  `phase15b_pgvector_rag_schema`.
- `/health` now reports `database_mode` + `vector_store_mode`; `/rag/health`
  reports `vector_store_mode`. **No Qdrant dependency remains.**
- All existing RAG APIs/contracts preserved (Similar Tickets, AI citations,
  recommendations, retrieval floor, metadata filtering).

### Phase 15A — Supabase Postgres (relational)
- Replaced SQLite-only persistence with Supabase Postgres
  (`ITARS_DATABASE_URL`); SQLite remains the local-dev default. psycopg driver,
  pooler-aware engine, tracked `phase15a_initial_itars_schema` migration.

All notable changes are documented here. The project follows semantic
versioning loosely (it's a single-stream platform, not a published library);
each phase from the original 14-phase plan corresponds to one notable
release-equivalent.

## [1.0.0] — 2026-06-15 — Initial public release

The 14-phase build is complete. This is the first commit pushed to GitHub.
Everything described below is in this release.

### Backend (Python 3.11 / FastAPI 0.115 / SQLAlchemy 2.0)
- Modular package under `backend/` — pipeline, services, repositories, schemas,
  RAG, LLM gateway.
- Deterministic routing: fine-tuned SBERT (all-mpnet) + XGBoost (tags) +
  XGBoost (priority) + tag-vote × prototype-cosine hybrid scoring + two-stage
  confidence gate + controlled-review override.
- Six handcrafted priority features, whole-word matching (fixes the V1
  "down"→"download" substring bug, verified by 7 parity tests).
- FAISS-based duplicate engine (local-first asset loading).
- Multilingual ingestion: `langdetect` + MarianMT (de + romance) with an LRU
  cache; original text always preserved.
- Layered explainability (plain / evidence / forensics) on every ticket, with
  the named gate-rule (`margin_pass` / `entropy_pass` / `flagged_band` /
  `stage_1_floor` / `controlled_review`).
- Persistence: six-table SQLite schema (Postgres-ready via SQLAlchemy URL),
  every routing decision logged with `priority_confidence`, plus
  `analytics_events` and a review queue ordered by uncertainty.
- RAG layer (retrieval-only): BGE-small + Qdrant, five collections, citations
  + score floor, score-floor refusal.
- LLM gateway: provider-agnostic (Echo / Gemini 2.5 Flash / Grok 3-mini),
  budget tracker, prompt-injection fencing, fallback chain.
- Grounded AI assistance: `/ai/summary`, `/ai/explanation`,
  `/ai/recommendation` (returns `insufficient_evidence` below the floor),
  `/ai/actions`. Strictly advisory; never writes to the DB.
- Human-feedback loop: `correction_reason`, `feedback_stats`, plus
  overrides/escalations ingested into the RAG `feedback_records` collection.
- Analytics & monitoring: `/analytics/summary` and
  `/analytics/monitoring` (confidence histogram with gate-floor reference
  line, gate-rule breakdown, reroute rates by department, predicted→final
  override flow, model-vs-reviewer agreement KPI).
- **Deployment hardening**: env-driven CORS lockdown (`ITARS_CORS_ORIGINS`),
  optional shared-token gate (`ITARS_API_TOKEN` via `X-API-Key` /
  `Bearer`), constant-time compare, public `/health` + `/docs`, exempt CORS
  preflight.
- 109 backend tests passing (2 env-skipped — pandas/langdetect-gated).

### Frontend (Next.js 16 / Tailwind v4 / shadcn/ui / Recharts)
- App-router pages: Dashboard, Ticket Analysis, Human Review, Analytics,
  Feedback, Settings, branded 404.
- Zod-typed REST client (`lib/api.ts`) with localStorage backend-URL override
  and optional `NEXT_PUBLIC_API_KEY` for the token gate.
- Layered explainability panel; cited similar-tickets retrieval; review
  workspace with AI summary + recommendation + suggested actions + feedback
  form.
- Analytics: distributions + the Phase-12 monitoring suite (Recharts +
  a dependency-free custom SVG bipartite Sankey for the predicted→final
  override flow).
- UI polish: skeleton loaders on every list view; **"what changed"
  predicted→final diff** on Feedback (semantic colour fade-in); a11y sweep
  (mobile-nav Sheet description, table labels); tinted OKLCH-slate palette
  with status colours reserved for meaning; dark mode; Geist + JetBrains Mono.

### Infrastructure (Phase 14)
- `Dockerfile` (py3.11-slim, libgomp, healthcheck on `/health`, 2 uvicorn
  workers, models via mounted `/models` volume, `INSTALL_POSTGRES` build arg).
- `docker-compose.yml` (backend + Qdrant + Postgres) with configurable model
  volumes.
- `.github/workflows/ci.yml` — backend pytest + frontend lint/build + Docker
  build.
- `DEPLOYMENT.md` runbook covering Docker, Vercel, security, ML pre-deploy.

### Verified live
- Gemini 2.5 Flash end-to-end (`served_by=gemini`).
- Phase-12 charts rendering against a seeded backend.
- Phase-13 polish: Feedback diff DOM-confirmed; mobile-nav Sheet description
  added (Radix `DialogContent` aria warning gone).
