"use client";

import * as React from "react";
import { ArrowRight, Check, MessageSquareText } from "lucide-react";

import { getFeedback, getFeedbackStats } from "@/lib/api";
import type { FeedbackStats } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { PriorityBadge } from "@/components/status-badges";
import { getAnalyses, onStoreChange } from "@/lib/session-store";
import { StatTilesSkeleton, TableRowsSkeleton } from "@/components/skeletons";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const ACTION_META: Record<string, { label: string; cls: string }> = {
  approved: { label: "Approved", cls: "text-emerald-700 dark:text-emerald-400" },
  overridden: { label: "Overridden", cls: "text-amber-700 dark:text-amber-400" },
  escalated: { label: "Escalated", cls: "text-red-600 dark:text-red-400" },
};

const REASON_LABELS: Record<string, string> = {
  wrong_department: "Wrong department",
  wrong_priority: "Wrong priority",
  ambiguous_ticket: "Ambiguous ticket",
  missing_context: "Missing context",
  model_error: "Model error",
  other: "Other",
};

type FeedbackRow = {
  ticket_id: string;
  original_text: string | null;
  predicted_department: string | null;
  final_department: string | null;
  predicted_priority: string | null;
  final_priority: string | null;
  review_action: string;
  correction_reason: string | null;
  review_notes: string | null;
};

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 font-mono text-xl font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}

/** Predicted → final department, highlighting what the reviewer changed. */
function DeptDiff({
  predicted,
  final,
  action,
}: {
  predicted: string | null;
  final: string | null;
  action: string;
}) {
  const p = (predicted ?? "—").replaceAll("_", " ");
  const f = (final ?? predicted ?? "—").replaceAll("_", " ");
  const changed = Boolean(final && predicted && final !== predicted);
  if (!changed) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm">
        <Check
          className="size-3.5 text-emerald-600 dark:text-emerald-400"
          aria-hidden
        />
        {f}
      </span>
    );
  }
  const escalated = action === "escalated" || final === "Escalation";
  return (
    <span
      className="inline-flex animate-rise items-center gap-1.5 text-sm"
      title={`Changed from ${p} to ${f}`}
    >
      <span className="text-muted-foreground line-through decoration-muted-foreground/40">
        {p}
      </span>
      <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span
        className={cn(
          "font-medium",
          escalated
            ? "text-red-600 dark:text-red-400"
            : "text-amber-700 dark:text-amber-400",
        )}
      >
        {f}
      </span>
    </span>
  );
}

/** Predicted → final priority, shown only when the reviewer changed it. */
function PriorityDiff({
  predicted,
  final,
}: {
  predicted: string | null;
  final: string | null;
}) {
  const changed = Boolean(predicted && final && predicted !== final);
  if (!changed) {
    return <PriorityBadge priority={final ?? predicted ?? "medium"} />;
  }
  return (
    <span className="inline-flex animate-rise items-center gap-1.5">
      <span className="font-mono text-[11px] uppercase text-muted-foreground line-through">
        {predicted}
      </span>
      <ArrowRight className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      <PriorityBadge priority={final ?? "medium"} />
    </span>
  );
}

export default function FeedbackPage() {
  const [rows, setRows] = React.useState<FeedbackRow[]>([]);
  const [stats, setStats] = React.useState<FeedbackStats | null>(null);
  const [serverMode, setServerMode] = React.useState(true);
  const [loading, setLoading] = React.useState(true);

  const loadFromSession = React.useCallback(() => {
    setRows(
      getAnalyses()
        .filter((e) => e.review_action)
        .map((e) => ({
          ticket_id: e.ticket_id,
          original_text: e.original_text,
          predicted_department: e.department,
          final_department: e.final_department ?? e.department,
          predicted_priority: e.priority,
          final_priority: e.priority,
          review_action: e.review_action as string,
          correction_reason: null,
          review_notes: e.review_notes ?? null,
        })),
    );
  }, []);

  const load = React.useCallback(() => {
    getFeedback()
      .then((data) => {
        setServerMode(true);
        setRows(
          data.map((f) => ({
            ticket_id: f.ticket_id,
            original_text: f.original_text,
            predicted_department: f.predicted_department,
            final_department: f.final_department,
            predicted_priority: f.predicted_priority,
            final_priority: f.final_priority,
            review_action: f.review_action,
            correction_reason: f.correction_reason ?? null,
            review_notes: f.review_notes,
          })),
        );
        getFeedbackStats()
          .then(setStats)
          .catch(() => setStats(null));
      })
      .catch(() => {
        setServerMode(false);
        setStats(null);
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

  const topReasons = stats
    ? Object.entries(stats.reason_counts).sort((a, b) => b[1] - a[1]).slice(0, 3)
    : [];

  const showStats = stats !== null || (loading && serverMode);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Human corrections captured from review — predicted vs final department and
        priority, with reasons. Overrides also feed the RAG retrieval layer, so
        the model&apos;s neighbours improve as reviewers work.
        {serverMode ? null : " Backend offline — showing this browser session."}
      </p>

      {showStats ? (
        <section
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
          aria-label="Feedback summary"
        >
          {stats ? (
            <>
              <StatTile label="Decisions" value={String(stats.total)} />
              <StatTile
                label="Override rate"
                value={`${Math.round(stats.override_rate * 100)}%`}
              />
              <StatTile
                label="Dept changes"
                value={String(stats.department_changes)}
              />
              <StatTile label="Escalations" value={String(stats.escalations)} />
            </>
          ) : (
            <StatTilesSkeleton count={4} />
          )}
        </section>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Captured feedback{loading ? "" : ` (${rows.length})`}
          </CardTitle>
          <CardDescription>
            {serverMode ? "Persisted decision log." : "This browser session."}
            {topReasons.length > 0
              ? ` · Top reasons: ${topReasons
                  .map(([k, n]) => `${REASON_LABELS[k] ?? k} (${n})`)
                  .join(", ")}`
              : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!loading && rows.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <MessageSquareText
                className="size-8 text-muted-foreground"
                aria-hidden
              />
              <p className="max-w-sm text-sm text-muted-foreground">
                No review decisions yet. Approve, override, or escalate tickets in
                the Human Review queue and they will appear here.
              </p>
            </div>
          ) : (
            <Table aria-label="Captured feedback">
              <TableHeader>
                <TableRow>
                  <TableHead>Ticket</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              {loading ? (
                <TableRowsSkeleton rows={6} cols={6} />
              ) : (
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.ticket_id}>
                      <TableCell className="max-w-[200px]">
                        <div className="truncate text-sm">
                          {row.original_text}
                        </div>
                        <div className="font-mono text-[11px] text-muted-foreground">
                          {row.ticket_id}
                        </div>
                      </TableCell>
                      <TableCell>
                        <DeptDiff
                          predicted={row.predicted_department}
                          final={row.final_department}
                          action={row.review_action}
                        />
                      </TableCell>
                      <TableCell>
                        <PriorityDiff
                          predicted={row.predicted_priority}
                          final={row.final_priority}
                        />
                      </TableCell>
                      <TableCell>
                        <span
                          className={cn(
                            "text-sm font-medium",
                            ACTION_META[row.review_action]?.cls,
                          )}
                        >
                          {ACTION_META[row.review_action]?.label ??
                            row.review_action}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.correction_reason
                          ? REASON_LABELS[row.correction_reason] ??
                            row.correction_reason
                          : "—"}
                      </TableCell>
                      <TableCell className="max-w-[180px] truncate text-sm text-muted-foreground">
                        {row.review_notes ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              )}
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
