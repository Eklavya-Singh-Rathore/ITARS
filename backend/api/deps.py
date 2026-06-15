"""FastAPI dependencies and in-process metrics (Phase 2).

The pipeline is loaded once and stored on `app.state.pipeline`; tests inject a fake
via `create_app(pipeline=...)`. Metrics are in-memory for now — Phase 6 moves them to
the Postgres decision log.
"""

from __future__ import annotations

from fastapi import HTTPException, Request


class Metrics:
    def __init__(self) -> None:
        self.requests_total = 0
        self.route_mode_counts: dict[str, int] = {}
        self.duplicate_flagged_total = 0
        self.latency_sum_ms = 0.0

    def record(self, route_mode: str, latency_ms: float, is_duplicate: bool) -> None:
        self.requests_total += 1
        self.route_mode_counts[route_mode] = (
            self.route_mode_counts.get(route_mode, 0) + 1
        )
        self.latency_sum_ms += float(latency_ms)
        if is_duplicate:
            self.duplicate_flagged_total += 1

    @property
    def avg_latency_ms(self) -> float:
        if self.requests_total == 0:
            return 0.0
        return self.latency_sum_ms / self.requests_total


def get_pipeline(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline is not loaded yet.")
    return pipeline


def get_metrics(request: Request) -> Metrics:
    return request.app.state.metrics


def get_translation(request: Request):
    translation = getattr(request.app.state, "translation", None)
    if translation is None:
        raise HTTPException(status_code=503, detail="Translation service not loaded.")
    return translation


def get_session(request: Request):
    """Yield a DB session; 503 if persistence isn't configured."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_rag(request: Request):
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG retrieval is not available (Qdrant/embedder not loaded).",
        )
    return rag


def get_optional_rag(request: Request):
    """RAG service or None — for best-effort use (e.g. the feedback loop)."""
    return getattr(request.app.state, "rag", None)


def get_llm(request: Request):
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM gateway is not available.")
    return llm


def get_assistant(request: Request):
    """Compose the AI-assistance service from the LLM gateway (required) and the
    RAG service (optional — assistance degrades gracefully without grounding)."""
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="AI assistance is not available.")
    from ..services.assistant import AssistantService

    return AssistantService(llm=llm, rag=getattr(request.app.state, "rag", None))


def get_optional_session(request: Request):
    """Yield a DB session, or None when persistence isn't configured (so the
    analyze path still works without a database)."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        yield None
        return
    session = factory()
    try:
        yield session
    finally:
        session.close()
