/**
 * Browser-local session store for analyzed tickets and review decisions.
 *
 * Deliberately temporary: Phase 6 adds backend persistence (SQLite tables) and
 * Phases 10–11 move the review queue + feedback capture server-side. Until then
 * this keeps the Dashboard / Review / Feedback pages functional with real data
 * from the current browser session.
 */
import type { AnalyzeResponse } from "./schemas";

const ANALYSES_KEY = "itars_analyses";
const CHANGED_EVENT = "itars-store-changed";
const MAX_ENTRIES = 200;

export type ReviewAction = "approved" | "overridden" | "escalated";

export interface StoredAnalysis extends AnalyzeResponse {
  analyzed_at: string;
  review_action?: ReviewAction;
  final_department?: string;
  review_notes?: string;
  reviewed_at?: string;
}

function read(): StoredAnalysis[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(ANALYSES_KEY);
    return raw ? (JSON.parse(raw) as StoredAnalysis[]) : [];
  } catch {
    return [];
  }
}

function write(entries: StoredAnalysis[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    ANALYSES_KEY,
    JSON.stringify(entries.slice(0, MAX_ENTRIES)),
  );
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

export function getAnalyses(): StoredAnalysis[] {
  return read();
}

export function addAnalysis(result: AnalyzeResponse): void {
  const entry: StoredAnalysis = {
    ...result,
    analyzed_at: new Date().toISOString(),
  };
  write([entry, ...read()]);
}

export function updateReview(
  ticketId: string,
  update: {
    review_action: ReviewAction;
    final_department?: string;
    review_notes?: string;
  },
): void {
  write(
    read().map((entry) =>
      entry.ticket_id === ticketId
        ? { ...entry, ...update, reviewed_at: new Date().toISOString() }
        : entry,
    ),
  );
}

export function clearAnalyses(): void {
  write([]);
}

/** Subscribe to store changes (same-tab custom event + cross-tab storage). */
export function onStoreChange(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(CHANGED_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(CHANGED_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}
