"use client";

import * as React from "react";
import Link from "next/link";
import { Inbox } from "lucide-react";
import { toast } from "sonner";

import { ApiError, getReviewQueue, submitReview } from "@/lib/api";
import { RouteBadge } from "@/components/status-badges";
import {
  ReviewWorkspace,
  type ReviewAction,
  type ReviewSubmission,
  type WorkspaceEntry,
} from "@/components/review-workspace";
import {
  getAnalyses,
  onStoreChange,
  updateReview,
} from "@/lib/session-store";
import { QueueSkeleton } from "@/components/skeletons";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ReviewPage() {
  const [queue, setQueue] = React.useState<WorkspaceEntry[]>([]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [serverMode, setServerMode] = React.useState(true);
  const [loading, setLoading] = React.useState(true);

  const loadFromSession = React.useCallback(() => {
    setQueue(
      getAnalyses()
        .filter((e) => e.route !== "AUTO_ROUTE" && !e.review_action)
        .map((e) => ({
          ticket_id: e.ticket_id,
          original_text: e.original_text ?? "",
          route: e.route,
          department: e.department,
          priority: e.priority,
          confidence: e.confidence,
          explanation_layers: e.explanation_layers ?? null,
        })),
    );
  }, []);

  const load = React.useCallback(() => {
    getReviewQueue()
      .then((rows) => {
        setServerMode(true);
        setQueue(
          rows.map((r) => ({
            ticket_id: r.ticket_id,
            original_text: r.original_text,
            route: r.route,
            department: r.department,
            priority: r.priority,
            confidence: r.confidence,
            explanation_layers: r.explanation_layers ?? null,
          })),
        );
      })
      .catch(() => {
        setServerMode(false);
        loadFromSession();
      })
      .finally(() => setLoading(false));
  }, [loadFromSession]);

  React.useEffect(() => {
    load();
    return onStoreChange(() => {
      if (!serverMode) loadFromSession();
    });
  }, [load, loadFromSession, serverMode]);

  const selected = queue.find((e) => e.ticket_id === selectedId);

  async function handleSubmit(action: ReviewAction, sub: ReviewSubmission) {
    if (!selected) return;
    const ticketId = selected.ticket_id;
    try {
      if (serverMode) {
        const result = await submitReview(ticketId, {
          action,
          final_department: sub.finalDepartment,
          final_priority: sub.finalPriority,
          correction_reason: sub.correctionReason,
          notes: sub.notes || undefined,
        });
        toast.success(
          `Ticket ${ticketId} ${action} → ${result.final_department.replaceAll("_", " ")}`,
        );
        load();
      } else {
        updateReview(ticketId, {
          review_action: action,
          final_department: sub.finalDepartment,
          review_notes: sub.notes || undefined,
        });
        toast.success(`Ticket ${ticketId} ${action} (saved locally)`);
        loadFromSession();
      }
      setSelectedId(null);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Could not save review.",
      );
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Flagged and human-review tickets, ordered by uncertainty (most
        ambiguous first).
        {serverMode ? null : " Backend offline — showing this browser session."}
      </p>

      {loading ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Queue</CardTitle>
              <CardDescription>Loading the review queue…</CardDescription>
            </CardHeader>
            <CardContent>
              <QueueSkeleton rows={5} />
            </CardContent>
          </Card>
          <Card className="hidden min-h-[300px] items-center justify-center border-dashed lg:flex">
            <p className="text-sm text-muted-foreground">Loading…</p>
          </Card>
        </div>
      ) : queue.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Inbox className="size-8 text-muted-foreground" aria-hidden />
            <p className="text-sm text-muted-foreground">
              Nothing waiting for review. Flagged and low-confidence tickets land
              here automatically.
            </p>
            <Button asChild size="sm" variant="outline">
              <Link href="/analyze">Analyze a ticket</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Queue ({queue.length})</CardTitle>
              <CardDescription>Most uncertain first.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {queue.map((entry) => (
                <button
                  key={entry.ticket_id}
                  type="button"
                  onClick={() => setSelectedId(entry.ticket_id)}
                  aria-pressed={entry.ticket_id === selectedId}
                  className={`w-full cursor-pointer rounded-md border p-3 text-left transition-colors hover:bg-accent ${
                    entry.ticket_id === selectedId ? "border-ring bg-accent" : ""
                  }`}
                >
                  <div className="mb-1.5 flex items-center gap-2">
                    <RouteBadge route={entry.route} />
                    <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                      {Math.round(entry.confidence * 100)}%
                    </span>
                  </div>
                  <div className="truncate text-sm">{entry.original_text}</div>
                </button>
              ))}
            </CardContent>
          </Card>

          {selected ? (
            <ReviewWorkspace
              key={selected.ticket_id}
              entry={selected}
              onSubmit={handleSubmit}
            />
          ) : (
            <Card className="flex min-h-[300px] items-center justify-center border-dashed">
              <p className="text-sm text-muted-foreground">
                Select a ticket from the queue.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
