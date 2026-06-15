/**
 * Zod schemas mirroring backend/schemas/api.py — the single typed contract
 * between the Next.js frontend and the FastAPI backend.
 */
import { z } from "zod";

export const TagVote = z.object({
  tag: z.string(),
  score: z.number(),
  department: z.string(),
});
export type TagVote = z.infer<typeof TagVote>;

export const ExplanationLayer = z.object({
  plain: z.string(),
  evidence: z.record(z.string(), z.unknown()),
  forensics: z.record(z.string(), z.unknown()),
});
export type ExplanationLayer = z.infer<typeof ExplanationLayer>;

export const TicketExplanation = z.object({
  routing: ExplanationLayer,
  duplicate: ExplanationLayer.nullable(),
  priority: ExplanationLayer,
});
export type TicketExplanation = z.infer<typeof TicketExplanation>;

export const AnalyzeResponse = z.object({
  ticket_id: z.string(),
  status: z.string(),
  route: z.enum(["AUTO_ROUTE", "AUTO_ROUTE_FLAGGED", "HUMAN_REVIEW"]),
  department: z.string(),
  priority: z.string(),
  priority_confidence: z.number().nullable(),
  confidence: z.number(),
  review: z.boolean(),
  tags: z.string(),
  tag_votes: z.array(TagVote),
  is_duplicate: z.boolean(),
  duplicate_score: z.number(),
  duplicate_text: z.string().nullable(),
  explanation: z.string(),
  message: z.string(),
  latency_ms: z.number(),
  original_text: z.string().nullable(),
  detected_language: z.string().nullable(),
  translated_text: z.string().nullable(),
  translation_applied: z.boolean(),
  routing: z.record(z.string(), z.unknown()).nullable(),
  explanation_layers: TicketExplanation.nullable().optional(),
});
export type AnalyzeResponse = z.infer<typeof AnalyzeResponse>;

export const RouteResponse = z.object({
  mode: z.string(),
  department: z.string(),
  recommended_department: z.string().nullable(),
  priority: z.string(),
  priority_confidence: z.number().nullable(),
  hybrid_confidence: z.number(),
  review: z.boolean(),
  margin: z.number(),
  entropy: z.number(),
  top_tag_votes: z.array(TagVote),
  note: z.string(),
});
export type RouteResponse = z.infer<typeof RouteResponse>;

export const DuplicateCheckResponse = z.object({
  is_duplicate: z.boolean(),
  duplicate_score: z.number(),
  matched_text: z.string().nullable(),
  matched_id: z.string().nullable(),
  threshold: z.number(),
});
export type DuplicateCheckResponse = z.infer<typeof DuplicateCheckResponse>;

export const TranslateResponse = z.object({
  detected_language: z.string(),
  translated_text: z.string(),
  original_text: z.string(),
});
export type TranslateResponse = z.infer<typeof TranslateResponse>;

export const HealthResponse = z.object({
  status: z.string(),
  version: z.string(),
  tags: z.number(),
  departments: z.number(),
  duplicate_index_size: z.number(),
  duplicate_threshold: z.number(),
  encoders_loaded: z.boolean(),
});
export type HealthResponse = z.infer<typeof HealthResponse>;

export const MetricsResponse = z.object({
  requests_total: z.number(),
  route_mode_counts: z.record(z.string(), z.number()),
  duplicate_flagged_total: z.number(),
  avg_latency_ms: z.number(),
  duplicate_index_size: z.number(),
});
export type MetricsResponse = z.infer<typeof MetricsResponse>;

export const LLMProviderInfo = z.object({
  model: z.string(),
  available: z.boolean(),
});
export const LLMHealth = z.object({
  primary: z.string(),
  fallback: z.array(z.string()),
  providers: z.record(z.string(), LLMProviderInfo),
  budget: z.record(z.string(), z.unknown()),
});
export type LLMHealth = z.infer<typeof LLMHealth>;

// --- persistence (Phase 6) ---
export const RecentTicket = z.object({
  ticket_id: z.string(),
  original_text: z.string(),
  detected_language: z.string().nullable(),
  created_at: z.string().nullable(),
  route: z.string(),
  department: z.string(),
  priority: z.string(),
  confidence: z.number(),
  is_duplicate: z.boolean(),
  review_action: z.string().nullable(),
  final_department: z.string().nullable(),
});
export type RecentTicket = z.infer<typeof RecentTicket>;

export const ReviewQueueEntry = z.object({
  ticket_id: z.string(),
  original_text: z.string(),
  route: z.string(),
  department: z.string(),
  priority: z.string(),
  confidence: z.number(),
  enqueued_at: z.string().nullable(),
  explanation_layers: TicketExplanation.nullable(),
});
export type ReviewQueueEntry = z.infer<typeof ReviewQueueEntry>;

export const ReviewResult = z.object({
  ticket_id: z.string(),
  action: z.string(),
  final_department: z.string(),
  final_priority: z.string(),
});
export type ReviewResult = z.infer<typeof ReviewResult>;

export const FeedbackEntry = z.object({
  ticket_id: z.string(),
  original_text: z.string().nullable(),
  predicted_department: z.string().nullable(),
  final_department: z.string().nullable(),
  predicted_priority: z.string().nullable(),
  final_priority: z.string().nullable(),
  review_action: z.string(),
  correction_reason: z.string().nullable().optional(),
  review_notes: z.string().nullable(),
  created_at: z.string().nullable(),
});
export type FeedbackEntry = z.infer<typeof FeedbackEntry>;

export const FeedbackStats = z.object({
  total: z.number(),
  overrides: z.number(),
  escalations: z.number(),
  department_changes: z.number(),
  override_rate: z.number(),
  reason_counts: z.record(z.string(), z.number()),
});
export type FeedbackStats = z.infer<typeof FeedbackStats>;

export const RagResult = z.object({
  ticket_id: z.string().nullable(),
  text: z.string().nullable(),
  department: z.string().nullable(),
  priority: z.string().nullable(),
  tags: z.string().nullable(),
  language: z.string().nullable(),
  score: z.number(),
});
export type RagResult = z.infer<typeof RagResult>;

// --- AI assistance (Phase 9) ---
export const AiResponse = z.object({
  ai_assisted: z.boolean(),
  advisory: z.boolean(),
  text: z.string(),
  citations: z.array(RagResult),
  provider: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  cost_usd: z.number().nullable().optional(),
  fallback_used: z.boolean().optional(),
  tokens: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
});
export type AiResponse = z.infer<typeof AiResponse>;

export const AiRecommendationResponse = z.object({
  status: z.string(),
  advisory: z.boolean(),
  ai_assisted: z.boolean(),
  recommendation: z.string().nullable(),
  citations: z.array(RagResult),
  message: z.string().nullable().optional(),
  provider: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  cost_usd: z.number().nullable().optional(),
  fallback_used: z.boolean().optional(),
  tokens: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
});
export type AiRecommendationResponse = z.infer<typeof AiRecommendationResponse>;

export const AiHealth = z.object({
  llm: z.record(z.string(), z.unknown()),
  rag_available: z.boolean(),
  retrieval_floor: z.number(),
});
export type AiHealth = z.infer<typeof AiHealth>;

export const AnalyticsSummary = z.object({
  total_tickets: z.number(),
  route_mode_counts: z.record(z.string(), z.number()),
  department_counts: z.record(z.string(), z.number()),
  priority_counts: z.record(z.string(), z.number()),
  language_counts: z.record(z.string(), z.number()),
  avg_latency_ms: z.number(),
  duplicate_total: z.number(),
  feedback_total: z.number(),
  override_rate: z.number(),
});
export type AnalyticsSummary = z.infer<typeof AnalyticsSummary>;

// --- monitoring (Phase 12) ---
export const HistogramBin = z.object({
  lower: z.number(),
  upper: z.number(),
  label: z.string(),
});
export type HistogramBin = z.infer<typeof HistogramBin>;

export const ConfidenceHistogram = z.object({
  bins: z.array(HistogramBin),
  series: z.record(z.string(), z.array(z.number())),
  thresholds: z.record(z.string(), z.number()),
});
export type ConfidenceHistogram = z.infer<typeof ConfidenceHistogram>;

export const DepartmentReroute = z.object({
  department: z.string(),
  total: z.number(),
  overrides: z.number(),
  escalations: z.number(),
  changes: z.number(),
  reroute_rate: z.number(),
});
export type DepartmentReroute = z.infer<typeof DepartmentReroute>;

export const FlowLink = z.object({
  predicted: z.string(),
  final: z.string(),
  count: z.number(),
});
export type FlowLink = z.infer<typeof FlowLink>;

export const RoutingAccuracy = z.object({
  total_reviewed: z.number(),
  agreements: z.number(),
  changes: z.number(),
  agreement_rate: z.number(),
});
export type RoutingAccuracy = z.infer<typeof RoutingAccuracy>;

export const MonitoringSummary = z.object({
  total_tickets: z.number(),
  confidence_histogram: ConfidenceHistogram,
  gate_rule_counts: z.record(z.string(), z.number()),
  department_reroute_rates: z.array(DepartmentReroute),
  predicted_vs_final: z.array(FlowLink),
  routing_accuracy: RoutingAccuracy,
});
export type MonitoringSummary = z.infer<typeof MonitoringSummary>;
