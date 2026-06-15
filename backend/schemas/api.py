"""Pydantic request/response schemas for the ITARS API (Phase 2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------- requests
class TicketRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw ticket text to analyze.")
    add_to_index: bool = Field(
        True,
        alias="register",
        description="Add the ticket to the duplicate index after analysis.",
    )
    translate: bool = Field(
        True,
        description="Detect language and translate to English before routing.",
    )
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "text": "The email server has been down since this morning. This is critical!",
                "register": True,
            }
        },
    }


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw ticket text.")
    model_config = {
        "json_schema_extra": {
            "example": {"text": "I was charged twice for my subscription. Please refund."}
        }
    }


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    target_lang: str = Field("en", description="Target language code.")


# --------------------------------------------------------------------- pieces
class TagVote(BaseModel):
    tag: str
    score: float
    department: str


class ExplanationLayer(BaseModel):
    plain: str
    evidence: dict[str, Any]
    forensics: dict[str, Any]


class TicketExplanation(BaseModel):
    routing: ExplanationLayer
    duplicate: ExplanationLayer | None = None
    priority: ExplanationLayer


# --------------------------------------------------------------------- responses
class AnalyzeResponse(BaseModel):
    ticket_id: str
    status: str = Field(..., description="DUPLICATE or NOT DUPLICATE.")
    route: str = Field(..., description="AUTO_ROUTE | AUTO_ROUTE_FLAGGED | HUMAN_REVIEW.")
    department: str
    priority: str
    priority_confidence: float | None = None
    confidence: float = Field(..., description="Hybrid routing confidence.")
    review: bool
    tags: str = Field(..., description="Top tag summary string.")
    tag_votes: list[TagVote] = Field(default_factory=list)
    is_duplicate: bool
    duplicate_score: float
    duplicate_text: str | None = None
    explanation: str
    message: str
    latency_ms: float
    # --- translation (Phase 3) ---
    original_text: str | None = None
    detected_language: str | None = None
    translated_text: str | None = None
    translation_applied: bool = False
    routing: dict[str, Any] | None = Field(
        default=None, description="Full structured routing detail (forensics)."
    )
    # --- layered explanation (Phase 5) ---
    explanation_layers: TicketExplanation | None = Field(
        default=None,
        description="Three-layer explanation: plain prose, evidence, forensics.",
    )


class RouteResponse(BaseModel):
    mode: str
    department: str
    recommended_department: str | None = None
    priority: str
    priority_confidence: float | None = None
    hybrid_confidence: float
    review: bool
    margin: float
    entropy: float
    top_tag_votes: list[TagVote] = Field(default_factory=list)
    note: str


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    duplicate_score: float
    matched_text: str | None = None
    matched_id: str | None = None
    threshold: float


class HealthResponse(BaseModel):
    status: str = Field(..., description="ok | starting")
    version: str
    tags: int
    departments: int
    duplicate_index_size: int
    duplicate_threshold: float
    encoders_loaded: bool


class MetricsResponse(BaseModel):
    requests_total: int
    route_mode_counts: dict[str, int]
    duplicate_flagged_total: int
    avg_latency_ms: float
    duplicate_index_size: int


class TranslateResponse(BaseModel):
    detected_language: str
    translated_text: str
    original_text: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# --- persistence (Phase 6) ---
class RecentTicket(BaseModel):
    ticket_id: str
    original_text: str
    detected_language: str | None = None
    created_at: str | None = None
    route: str
    department: str
    priority: str
    confidence: float
    is_duplicate: bool = False
    review_action: str | None = None
    final_department: str | None = None


class ReviewQueueEntry(BaseModel):
    ticket_id: str
    original_text: str
    route: str
    department: str
    priority: str
    confidence: float
    enqueued_at: str | None = None
    explanation_layers: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    action: str = Field(..., description="approved | overridden | escalated")
    final_department: str | None = None
    final_priority: str | None = None
    correction_reason: str | None = None
    notes: str | None = None
    reviewer: str | None = None


class ReviewResult(BaseModel):
    ticket_id: str
    action: str
    final_department: str
    final_priority: str


class FeedbackEntry(BaseModel):
    ticket_id: str
    original_text: str | None = None
    predicted_department: str | None = None
    final_department: str | None = None
    predicted_priority: str | None = None
    final_priority: str | None = None
    review_action: str
    correction_reason: str | None = None
    review_notes: str | None = None
    created_at: str | None = None


class FeedbackStats(BaseModel):
    total: int
    overrides: int
    escalations: int
    department_changes: int
    override_rate: float
    reason_counts: dict[str, int]


class AnalyticsSummary(BaseModel):
    total_tickets: int
    route_mode_counts: dict[str, int]
    department_counts: dict[str, int]
    priority_counts: dict[str, int]
    language_counts: dict[str, int]
    avg_latency_ms: float
    duplicate_total: int
    feedback_total: int
    override_rate: float


# --- monitoring (Phase 12) ---
class HistogramBin(BaseModel):
    lower: float
    upper: float
    label: str


class ConfidenceHistogram(BaseModel):
    bins: list[HistogramBin]
    series: dict[str, list[int]] = Field(
        ..., description="Per routing-mode counts, aligned to `bins`."
    )
    thresholds: dict[str, float] = Field(
        ..., description="Gate thresholds for reference lines (hybrid_floor, ...)."
    )


class DepartmentReroute(BaseModel):
    department: str = Field(..., description="The model's predicted department.")
    total: int
    overrides: int
    escalations: int
    changes: int = Field(..., description="Reviews where the final department differed.")
    reroute_rate: float


class FlowLink(BaseModel):
    predicted: str
    final: str
    count: int


class RoutingAccuracy(BaseModel):
    total_reviewed: int
    agreements: int = Field(..., description="Final department matched the prediction.")
    changes: int
    agreement_rate: float


class MonitoringSummary(BaseModel):
    total_tickets: int
    confidence_histogram: ConfidenceHistogram
    gate_rule_counts: dict[str, int]
    department_reroute_rates: list[DepartmentReroute]
    predicted_vs_final: list[FlowLink]
    routing_accuracy: RoutingAccuracy


# --- RAG (Phase 7) ---
class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    collection: str = "historical_tickets"
    top_k: int = 5
    department: str | None = None
    priority: str | None = None


class RagResult(BaseModel):
    ticket_id: str | None = None
    text: str | None = None
    department: str | None = None
    priority: str | None = None
    tags: str | None = None
    language: str | None = None
    score: float


class RagHealth(BaseModel):
    embedding_model: str
    embedding_dim: int
    score_floor: float
    collections: dict[str, int]


# --- LLM gateway (Phase 8) ---
class LLMHealth(BaseModel):
    primary: str
    fallback: list[str]
    providers: dict[str, dict[str, Any]]
    budget: dict[str, Any]


# --- AI assistance (Phase 9) ---
class AiSummaryRequest(BaseModel):
    text: str = Field(..., min_length=1)
    ticket_id: str | None = None


class AiExplanationRequest(BaseModel):
    department: str
    route: str
    explanation: dict[str, Any]


class AiRecommendationRequest(BaseModel):
    ticket_id: str | None = None
    text: str | None = None
    routing: dict[str, Any] | None = None


class AiResponse(BaseModel):
    ai_assisted: bool
    advisory: bool = True
    text: str
    citations: list[RagResult] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    cost_usd: float | None = None
    fallback_used: bool = False
    tokens: int | None = None
    error: str | None = None


class AiRecommendationResponse(BaseModel):
    status: str  # ok | insufficient_evidence | unavailable
    advisory: bool = True
    ai_assisted: bool = False
    recommendation: str | None = None
    citations: list[RagResult] = Field(default_factory=list)
    message: str | None = None
    provider: str | None = None
    model: str | None = None
    cost_usd: float | None = None
    fallback_used: bool = False
    tokens: int | None = None
    error: str | None = None


class AiHealth(BaseModel):
    llm: dict[str, Any]
    rag_available: bool
    retrieval_floor: float
