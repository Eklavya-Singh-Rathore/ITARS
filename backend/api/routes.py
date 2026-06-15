"""API routes — thin wrappers over the Phase-1 services (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import __version__
from ..repositories import tickets as ticket_repo
from ..services import feedback_service
from ..schemas.api import (
    AiExplanationRequest,
    AiHealth,
    AiRecommendationRequest,
    AiRecommendationResponse,
    AiResponse,
    AiSummaryRequest,
    AnalyticsSummary,
    AnalyzeResponse,
    DuplicateCheckResponse,
    ErrorResponse,
    FeedbackEntry,
    FeedbackStats,
    HealthResponse,
    LLMHealth,
    MetricsResponse,
    MonitoringSummary,
    RagHealth,
    RagResult,
    RagSearchRequest,
    RecentTicket,
    ReviewQueueEntry,
    ReviewRequest,
    ReviewResult,
    RouteResponse,
    TagVote,
    TextRequest,
    TicketRequest,
    TranslateRequest,
    TranslateResponse,
)
from .deps import (
    Metrics,
    get_assistant,
    get_llm,
    get_metrics,
    get_optional_rag,
    get_optional_session,
    get_pipeline,
    get_rag,
    get_session,
    get_translation,
)
from .serialization import json_safe, safe_float

router = APIRouter()


def _tag_votes(votes) -> list[TagVote]:
    return [
        TagVote(tag=str(v["tag"]), score=float(v["score"]), department=str(v["department"]))
        for v in (votes or [])
    ]


@router.post("/analyze-ticket", response_model=AnalyzeResponse, tags=["routing"])
def analyze_ticket(
    req: TicketRequest,
    pipeline=Depends(get_pipeline),
    metrics: Metrics = Depends(get_metrics),
    session=Depends(get_optional_session),
) -> AnalyzeResponse:
    """Full pipeline: duplicate check -> tags -> priority -> hybrid routing -> gate."""
    result = pipeline.process_ticket(
        req.text, register=req.add_to_index, translate=req.translate
    )
    metrics.record(result["route"], result["latency"], result["is_duplicate"])
    if session is not None:
        ticket_repo.save_analysis(session, result)
    routing = result.get("routing", {}) or {}
    return AnalyzeResponse(
        ticket_id=result["ticket_id"],
        status=result["status"],
        route=result["route"],
        department=result["department"],
        priority=result["priority"],
        priority_confidence=safe_float(result.get("priority_confidence")),
        confidence=float(result["confidence"]),
        review=bool(result["review"]),
        tags=result["tags"],
        tag_votes=_tag_votes(routing.get("top_tag_votes")),
        is_duplicate=bool(result["is_duplicate"]),
        duplicate_score=float(result["duplicate_score"]),
        duplicate_text=result.get("duplicate_text"),
        explanation=result["explanation"],
        message=result["message"],
        latency_ms=float(result["latency"]),
        original_text=result.get("original_text"),
        detected_language=result.get("detected_language"),
        translated_text=result.get("translated_text"),
        translation_applied=bool(result.get("translation_applied", False)),
        routing=json_safe(routing),
        explanation_layers=json_safe(result.get("explanation_struct")),
    )


@router.post("/route", response_model=RouteResponse, tags=["routing"])
def route(req: TextRequest, pipeline=Depends(get_pipeline)) -> RouteResponse:
    """Routing decision only (no duplicate detection or index registration)."""
    r = pipeline.route_only(req.text)
    return RouteResponse(
        mode=r["mode"],
        department=r["department"],
        recommended_department=r.get("recommended_department"),
        priority=r["priority"],
        priority_confidence=safe_float(r.get("priority_confidence")),
        hybrid_confidence=float(r["hybrid_confidence"]),
        review=bool(r["review"]),
        margin=float(r["margin"]),
        entropy=float(r["entropy"]),
        top_tag_votes=_tag_votes(r.get("top_tag_votes")),
        note=r["note"],
    )


@router.post("/duplicate-check", response_model=DuplicateCheckResponse, tags=["duplicates"])
def duplicate_check(req: TextRequest, pipeline=Depends(get_pipeline)) -> DuplicateCheckResponse:
    """Duplicate lookup only — best match + threshold verdict."""
    return DuplicateCheckResponse(**pipeline.check_duplicate(req.text))


@router.post(
    "/translate",
    response_model=TranslateResponse,
    tags=["translation"],
    responses={400: {"model": ErrorResponse}},
)
def translate(req: TranslateRequest, translation=Depends(get_translation)) -> TranslateResponse:
    """Detect language and translate to English (lang-detect -> MarianMT)."""
    if req.target_lang.lower() != "en":
        raise HTTPException(
            status_code=400,
            detail="Only target_lang='en' is supported (MarianMT *-en models).",
        )
    result = translation.translate(req.text)
    return TranslateResponse(
        detected_language=result["detected_language"],
        translated_text=result["translated_text"],
        original_text=result["original_text"],
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    """Liveness/readiness — never 503s; reports whether the pipeline is loaded."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        return HealthResponse(
            status="starting",
            version=__version__,
            tags=0,
            departments=0,
            duplicate_index_size=0,
            duplicate_threshold=0.0,
            encoders_loaded=False,
        )
    a = pipeline.artifacts
    engine = pipeline.duplicate_engine
    return HealthResponse(
        status="ok",
        version=__version__,
        tags=len(a.tag_list),
        departments=len(a.dept_prototypes),
        duplicate_index_size=int(engine.index_size) if engine is not None else 0,
        duplicate_threshold=(
            float(engine.duplicate_threshold) if engine is not None else 0.0
        ),
        encoders_loaded=pipeline.routing_sbert is not None,
    )


@router.get("/metrics", response_model=MetricsResponse, tags=["system"])
def metrics_endpoint(
    request: Request, metrics: Metrics = Depends(get_metrics)
) -> MetricsResponse:
    pipeline = getattr(request.app.state, "pipeline", None)
    index_size = (
        int(pipeline.duplicate_engine.index_size)
        if pipeline is not None and pipeline.duplicate_engine is not None
        else 0
    )
    return MetricsResponse(
        requests_total=metrics.requests_total,
        route_mode_counts=metrics.route_mode_counts,
        duplicate_flagged_total=metrics.duplicate_flagged_total,
        avg_latency_ms=round(metrics.avg_latency_ms, 2),
        duplicate_index_size=index_size,
    )


# --------------------------------------------------------------- persistence
@router.get("/tickets/recent", response_model=list[RecentTicket], tags=["tickets"])
def recent_tickets(
    limit: int = 20, session=Depends(get_session)
) -> list[RecentTicket]:
    rows = ticket_repo.list_recent(session, limit=max(1, min(int(limit), 200)))
    return [RecentTicket(**json_safe(row)) for row in rows]


@router.get("/tickets/{ticket_id}", tags=["tickets"], responses={404: {"model": ErrorResponse}})
def ticket_detail(ticket_id: str, session=Depends(get_session)) -> dict:
    row = ticket_repo.get_by_id(session, ticket_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    return json_safe(row)


@router.get("/review-queue", response_model=list[ReviewQueueEntry], tags=["review"])
def review_queue(session=Depends(get_session)) -> list[ReviewQueueEntry]:
    return [
        ReviewQueueEntry(**json_safe(row))
        for row in ticket_repo.list_review_queue(session)
    ]


@router.post(
    "/tickets/{ticket_id}/review",
    response_model=ReviewResult,
    tags=["review"],
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def submit_review(
    ticket_id: str,
    req: ReviewRequest,
    session=Depends(get_session),
    rag=Depends(get_optional_rag),
) -> ReviewResult:
    if req.action not in {"approved", "overridden", "escalated"}:
        raise HTTPException(
            status_code=400,
            detail="action must be approved, overridden, or escalated.",
        )
    try:
        result = feedback_service.record_review(
            session,
            ticket_id,
            action=req.action,
            final_department=req.final_department,
            final_priority=req.final_priority,
            notes=req.notes,
            correction_reason=req.correction_reason,
            reviewer=req.reviewer,
            rag=rag,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    return ReviewResult(**result)


@router.get("/feedback", response_model=list[FeedbackEntry], tags=["review"])
def feedback_list(session=Depends(get_session)) -> list[FeedbackEntry]:
    return [FeedbackEntry(**json_safe(row)) for row in ticket_repo.list_feedback(session)]


@router.get("/feedback/stats", response_model=FeedbackStats, tags=["review"])
def feedback_stats(session=Depends(get_session)) -> FeedbackStats:
    return FeedbackStats(**json_safe(ticket_repo.feedback_stats(session)))


@router.get("/analytics/summary", response_model=AnalyticsSummary, tags=["system"])
def analytics_summary(session=Depends(get_session)) -> AnalyticsSummary:
    return AnalyticsSummary(**json_safe(ticket_repo.aggregate_metrics(session)))


@router.get("/analytics/monitoring", response_model=MonitoringSummary, tags=["system"])
def analytics_monitoring(session=Depends(get_session)) -> MonitoringSummary:
    """Phase-12 monitoring: confidence histogram (inert-gate visual), named
    gate-rule counts, per-department reroute rates, predicted→final override
    flow, and model-vs-reviewer agreement."""
    return MonitoringSummary(**json_safe(ticket_repo.monitoring_metrics(session)))


# ----------------------------------------------------------------------- RAG
@router.post("/rag/search", response_model=list[RagResult], tags=["rag"])
def rag_search(req: RagSearchRequest, rag=Depends(get_rag)) -> list[RagResult]:
    """Semantic retrieval over a RAG collection, with citations and score floor."""
    filters = {}
    if req.department:
        filters["department"] = req.department
    if req.priority:
        filters["priority"] = req.priority
    results = rag.search(
        req.query,
        collection=req.collection,
        top_k=req.top_k,
        filters=filters or None,
    )
    return [RagResult(**json_safe(r)) for r in results]


@router.get(
    "/tickets/{ticket_id}/similar",
    response_model=list[RagResult],
    tags=["rag"],
    responses={404: {"model": ErrorResponse}},
)
def similar_tickets(
    ticket_id: str, rag=Depends(get_rag), session=Depends(get_session)
) -> list[RagResult]:
    """Historical tickets most similar to the given one (cited; empty when the
    best match is below the retrieval-confidence floor)."""
    ticket = ticket_repo.get_by_id(session, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found.")
    text = ticket.get("original_text") or ""
    results = rag.similar_tickets(text, exclude_ticket_id=ticket_id)
    return [RagResult(**json_safe(r)) for r in results]


@router.get("/rag/health", response_model=RagHealth, tags=["rag"])
def rag_health(rag=Depends(get_rag)) -> RagHealth:
    return RagHealth(**json_safe(rag.health()))


# ----------------------------------------------------------------------- LLM
@router.get("/llm/health", response_model=LLMHealth, tags=["llm"])
def llm_health(llm=Depends(get_llm)) -> LLMHealth:
    """Configured provider, fallback order, provider availability, budget usage."""
    return LLMHealth(**json_safe(llm.health()))


# --------------------------------------------------- AI assistance (Phase 9)
@router.post("/ai/summary", response_model=AiResponse, tags=["ai"])
def ai_summary(req: AiSummaryRequest, assistant=Depends(get_assistant)) -> AiResponse:
    """Grounded AI summary of a ticket (advisory; cites retrieved history)."""
    return AiResponse(**json_safe(assistant.summary(req.text, ticket_id=req.ticket_id)))


@router.post("/ai/explanation", response_model=AiResponse, tags=["ai"])
def ai_explanation(
    req: AiExplanationRequest, assistant=Depends(get_assistant)
) -> AiResponse:
    """Human-readable prose of the routing decision, from the structured
    explainability fields only (no invented scores/tags/departments)."""
    return AiResponse(
        **json_safe(
            assistant.explanation(
                department=req.department, route=req.route, explanation=req.explanation
            )
        )
    )


def _resolve_ai_input(req: AiRecommendationRequest, session):
    """Resolve (ticket_text, routing, ticket_id) from a ticket_id (decision log)
    or inline text+routing."""
    if req.ticket_id:
        if session is None:
            raise HTTPException(status_code=503, detail="Database is not configured.")
        ticket = ticket_repo.get_by_id(session, req.ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"Ticket {req.ticket_id} not found.")
        routing = {
            "department": ticket.get("department"),
            "route": ticket.get("route"),
            "priority": ticket.get("priority"),
            "confidence": ticket.get("confidence"),
        }
        return ticket.get("original_text") or "", routing, req.ticket_id
    if req.text:
        return req.text, req.routing or {}, None
    raise HTTPException(status_code=400, detail="Provide ticket_id or text.")


@router.post(
    "/ai/recommendation",
    response_model=AiRecommendationResponse,
    tags=["ai"],
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def ai_recommendation(
    req: AiRecommendationRequest,
    assistant=Depends(get_assistant),
    session=Depends(get_optional_session),
) -> AiRecommendationResponse:
    """Review assistant — advisory recommendation for a human-review ticket."""
    text, routing, ticket_id = _resolve_ai_input(req, session)
    result = assistant.recommendation(
        ticket_text=text, routing=routing, ticket_id=ticket_id
    )
    return AiRecommendationResponse(**json_safe(result))


@router.post(
    "/ai/actions",
    response_model=AiResponse,
    tags=["ai"],
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def ai_actions(
    req: AiRecommendationRequest,
    assistant=Depends(get_assistant),
    session=Depends(get_optional_session),
) -> AiResponse:
    """Advisory suggested next actions for the agent handling the ticket."""
    text, routing, _ = _resolve_ai_input(req, session)
    return AiResponse(**json_safe(assistant.actions(ticket_text=text, routing=routing)))


@router.get("/ai/health", response_model=AiHealth, tags=["ai"])
def ai_health(assistant=Depends(get_assistant)) -> AiHealth:
    return AiHealth(**json_safe(assistant.health()))
