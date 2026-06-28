# Contributing to ITARS

Thanks for your interest. ITARS is a portfolio-grade project, so contributions
are welcome — please follow the conventions below so changes stay safe and the
deterministic routing guarantees are preserved.

## Ground rules

These are **non-negotiable** invariants of the system. They come from the
project's spec and reflect the audit's recommendations:

1. **Routing is deterministic.** LLMs assist; they never decide. Do not let LLM
   output enter the routing path or write to the decision log.
2. **AI outputs must cite sources** and must refuse to generate when retrieval
   is below the configured floor (`insufficient_evidence`).
3. **Original ticket text is preserved.** Never display the lemmatized form.
4. **Status colours carry meaning.** auto = emerald, flagged = amber, review =
   blue; priority slate → red. Always pair colour with an icon.
5. **No agentic / multi-agent / incident-correlation / root-cause /
   auto-resolution** features — explicitly excluded by the spec.
6. **Keep the stack:** all-mpnet for routing, MarianMT for translation, FAISS
   for duplicates; Supabase pgvector is RAG-only.

## Setup

### Backend (Python 3.11)

```bash
python3.11 -m venv .venv
. .venv/Scripts/activate    # Windows; or `source .venv/bin/activate` on Unix
pip install -r requirements.txt
cp .env.example .env        # set GEMINI_API_KEY etc. (never commit .env)
```

### Frontend (Node 20+)

```bash
cd frontend
npm install
cp .env.example .env.local
```

## Running

```bash
# terminal 1 — backend
uvicorn backend.app:app --port 8000 --reload

# terminal 2 — frontend
cd frontend && npm run dev    # http://localhost:3000
```

## Tests

```bash
pytest -q                                       # full backend suite
pytest -q --ignore=tests/test_pipeline_smoke.py # skip artifact-dependent smoke

cd frontend && npm run lint && npm run build
```

CI runs the same commands on every PR (see `.github/workflows/ci.yml`).

## Branching & PRs

- Branch from `main`, naming `feature/<short-desc>` or `fix/<short-desc>`.
- Keep changes scoped — bug fixes don't need surrounding refactors.
- Add tests for new behaviour; the suite must stay green.
- Run lint + build before pushing.
- Open a PR with a brief summary and a test-plan checklist.

## Code style

- **Python**: 3.11 type hints, `from __future__ import annotations`. Pure
  functions where possible; services own state, callers don't. Don't add docstrings/comments
  that just describe what the next line does — only explain non-obvious *why*.
- **TypeScript**: Zod schemas in `frontend/lib/schemas.ts` mirror the backend
  Pydantic models — keep them in sync. The API client (`frontend/lib/api.ts`)
  is the only place that touches `fetch`. **Next.js 16 conventions changed** —
  see `frontend/AGENTS.md`; avoid the `set-state-in-effect` lint rule by
  remounting via a React `key` on the parent.

## Security

- Never commit secrets. `.env`/`.env.local` are gitignored; if you accidentally
  commit one, rotate the key and force-push a removal.
- Don't echo secrets in logs.
- Prompt-injection hygiene is in place (`backend/core/llm/prompts.py`) — if you
  add a new LLM-facing field, fence it with `fence()` and keep the system
  prompt pinned.

## Reporting issues

Open a GitHub issue with steps to reproduce, expected vs actual behaviour, and
relevant log lines. If it's a security issue, prefer email.
