/**
 * Typed API client for the ITARS FastAPI backend.
 *
 * Base URL resolution: localStorage override ("itars_api_url", set on the
 * Settings page) → NEXT_PUBLIC_API_URL → http://localhost:8000.
 */
import { z } from "zod";

import {
  AiHealth,
  AiRecommendationResponse,
  AiResponse,
  AnalyticsSummary,
  AnalyzeResponse,
  DuplicateCheckResponse,
  FeedbackEntry,
  FeedbackStats,
  HealthResponse,
  LLMHealth,
  MetricsResponse,
  MonitoringSummary,
  RagResult,
  RecentTicket,
  ReviewQueueEntry,
  ReviewResult,
  RouteResponse,
  TranslateResponse,
} from "./schemas";

export const API_URL_STORAGE_KEY = "itars_api_url";
const DEFAULT_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Optional shared token for a token-gated backend (ITARS_API_TOKEN). Bundled
// into the client, so it is basic gating only — not a secret.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

export function getApiUrl(): string {
  if (typeof window !== "undefined") {
    const override = window.localStorage.getItem(API_URL_STORAGE_KEY);
    if (override && override.trim()) return override.trim().replace(/\/+$/, "");
  }
  return DEFAULT_API_URL;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  schema: { parse: (data: unknown) => T },
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `Backend unreachable at ${getApiUrl()} — is uvicorn running?`,
    );
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON error body */
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed (${response.status})`,
      response.status,
      detail,
    );
  }
  return schema.parse(body);
}

export function analyzeTicket(opts: {
  text: string;
  register?: boolean;
  translate?: boolean;
}): Promise<AnalyzeResponse> {
  return request("/analyze-ticket", AnalyzeResponse, {
    method: "POST",
    body: JSON.stringify({
      text: opts.text,
      register: opts.register ?? true,
      translate: opts.translate ?? true,
    }),
  });
}

export function routeOnly(text: string): Promise<RouteResponse> {
  return request("/route", RouteResponse, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function duplicateCheck(text: string): Promise<DuplicateCheckResponse> {
  return request("/duplicate-check", DuplicateCheckResponse, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function translateText(text: string): Promise<TranslateResponse> {
  return request("/translate", TranslateResponse, {
    method: "POST",
    body: JSON.stringify({ text, target_lang: "en" }),
  });
}

export function getHealth(): Promise<HealthResponse> {
  return request("/health", HealthResponse, { method: "GET" });
}

export function getMetrics(): Promise<MetricsResponse> {
  return request("/metrics", MetricsResponse, { method: "GET" });
}

export function getLlmHealth(): Promise<LLMHealth> {
  return request("/llm/health", LLMHealth, { method: "GET" });
}

// --- persistence (Phase 6) ---
export function getRecentTickets(limit = 20): Promise<RecentTicket[]> {
  return request(`/tickets/recent?limit=${limit}`, z.array(RecentTicket), {
    method: "GET",
  });
}

export function getReviewQueue(): Promise<ReviewQueueEntry[]> {
  return request("/review-queue", z.array(ReviewQueueEntry), { method: "GET" });
}

export function submitReview(
  ticketId: string,
  body: {
    action: "approved" | "overridden" | "escalated";
    final_department?: string;
    final_priority?: string;
    correction_reason?: string;
    notes?: string;
  },
): Promise<ReviewResult> {
  return request(`/tickets/${ticketId}/review`, ReviewResult, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getFeedback(): Promise<FeedbackEntry[]> {
  return request("/feedback", z.array(FeedbackEntry), { method: "GET" });
}

export function getFeedbackStats(): Promise<FeedbackStats> {
  return request("/feedback/stats", FeedbackStats, { method: "GET" });
}

export function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return request("/analytics/summary", AnalyticsSummary, { method: "GET" });
}

export function getMonitoringSummary(): Promise<MonitoringSummary> {
  return request("/analytics/monitoring", MonitoringSummary, { method: "GET" });
}

// --- RAG (Phase 7) ---
export function getSimilarTickets(ticketId: string): Promise<RagResult[]> {
  return request(`/tickets/${ticketId}/similar`, z.array(RagResult), {
    method: "GET",
  });
}

export function ragSearch(body: {
  query: string;
  collection?: string;
  top_k?: number;
  department?: string;
  priority?: string;
}): Promise<RagResult[]> {
  return request("/rag/search", z.array(RagResult), {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- AI assistance (Phase 9) ---
export function aiSummary(text: string, ticketId?: string): Promise<AiResponse> {
  return request("/ai/summary", AiResponse, {
    method: "POST",
    body: JSON.stringify({ text, ticket_id: ticketId ?? null }),
  });
}

export function aiExplanation(body: {
  department: string;
  route: string;
  explanation: Record<string, unknown>;
}): Promise<AiResponse> {
  return request("/ai/explanation", AiResponse, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function aiRecommendation(
  ticketId: string,
): Promise<AiRecommendationResponse> {
  return request("/ai/recommendation", AiRecommendationResponse, {
    method: "POST",
    body: JSON.stringify({ ticket_id: ticketId }),
  });
}

export function aiActions(ticketId: string): Promise<AiResponse> {
  return request("/ai/actions", AiResponse, {
    method: "POST",
    body: JSON.stringify({ ticket_id: ticketId }),
  });
}

export function getAiHealth(): Promise<AiHealth> {
  return request("/ai/health", AiHealth, { method: "GET" });
}
