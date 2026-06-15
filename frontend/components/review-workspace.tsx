"use client";

import * as React from "react";
import { ArrowUpRight, Check, Pencil, Sparkles } from "lucide-react";

import { aiSummary } from "@/lib/api";
import type { AiResponse, TicketExplanation } from "@/lib/schemas";
import { CitationList } from "@/components/citation-list";
import { ConfidenceBar } from "@/components/confidence-bar";
import { ExplainabilityPanel } from "@/components/explainability-panel";
import { ReviewAssistant } from "@/components/review-assistant";
import { SimilarTickets } from "@/components/similar-tickets";
import { PriorityBadge, RouteBadge } from "@/components/status-badges";
import { SuggestedActions } from "@/components/suggested-actions";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";

const DEPARTMENTS = [
  "Technical_Support",
  "IT_Support",
  "Customer_Service",
  "Billing_And_Payments",
  "Product_Support",
  "Returns_And_Exchanges",
  "Service_Outages_And_Maintenance",
  "Sales_And_Presales",
  "Human_Resources",
  "Marketing",
  "Escalation",
];

export type ReviewAction = "approved" | "overridden" | "escalated";

export type ReviewSubmission = {
  finalDepartment: string;
  finalPriority: string;
  correctionReason?: string;
  notes: string;
};

const PRIORITIES = ["low", "medium", "high", "critical"];

const CORRECTION_REASONS: { value: string; label: string }[] = [
  { value: "wrong_department", label: "Wrong department" },
  { value: "wrong_priority", label: "Wrong priority" },
  { value: "ambiguous_ticket", label: "Ambiguous ticket" },
  { value: "missing_context", label: "Missing context" },
  { value: "model_error", label: "Model error" },
  { value: "other", label: "Other" },
];

export type WorkspaceEntry = {
  ticket_id: string;
  original_text: string;
  route: string;
  department: string;
  priority: string;
  confidence: number;
  explanation_layers?: TicketExplanation | null;
};

function AiSummarySection({ ticketId, text }: { ticketId: string; text: string }) {
  const [state, setState] = React.useState<"loading" | "ready" | "unavailable">(
    "loading",
  );
  const [data, setData] = React.useState<AiResponse | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    aiSummary(text, ticketId)
      .then((r) => {
        if (cancelled) return;
        setData(r);
        setState("ready");
      })
      .catch(() => !cancelled && setState("unavailable"));
    return () => {
      cancelled = true;
    };
  }, [ticketId, text]);

  if (state === "unavailable") return null;

  return (
    <div className="rounded-md border border-violet-500/20 bg-violet-500/[0.03] p-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Sparkles className="size-3.5 text-violet-500" aria-hidden />
        AI summary{data?.provider ? ` · ${data.provider}` : ""}
      </h3>
      {state === "loading" ? (
        <p className="text-sm text-muted-foreground">Generating…</p>
      ) : (
        <p className="text-sm leading-relaxed">{data?.text}</p>
      )}
      {data && data.citations.length > 0 ? (
        <div className="mt-2">
          <CitationList citations={data.citations} />
        </div>
      ) : null}
    </div>
  );
}

/** The complete human-review screen (Feature Report §Human Review): ticket
 * details, AI summary, explainability, similar tickets, AI recommendation,
 * suggested actions, and the feedback form. Remounted per ticket via a key. */
export function ReviewWorkspace({
  entry,
  onSubmit,
}: {
  entry: WorkspaceEntry;
  onSubmit: (action: ReviewAction, submission: ReviewSubmission) => void;
}) {
  const [department, setDepartment] = React.useState(entry.department);
  const [priority, setPriority] = React.useState(entry.priority.toLowerCase());
  const [reason, setReason] = React.useState("");
  const [notes, setNotes] = React.useState("");

  const submit = (action: ReviewAction) => {
    const finalDepartment =
      action === "escalated"
        ? "Escalation"
        : action === "overridden"
          ? department
          : entry.department;
    onSubmit(action, {
      finalDepartment,
      finalPriority: priority,
      correctionReason: action === "approved" ? undefined : reason || undefined,
      notes,
    });
  };

  return (
    <Card className="animate-rise">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <RouteBadge route={entry.route} />
          <PriorityBadge priority={entry.priority} />
          <span className="ml-auto font-mono text-xs text-muted-foreground">
            {entry.ticket_id}
          </span>
        </div>
        <CardTitle className="text-base">Review workspace</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div>
          <h3 className="mb-1 text-xs font-medium text-muted-foreground">
            Ticket
          </h3>
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            {entry.original_text}
          </div>
        </div>

        <ConfidenceBar value={entry.confidence} />

        <AiSummarySection ticketId={entry.ticket_id} text={entry.original_text} />

        {entry.explanation_layers ? (
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted-foreground">
              Why this routing
            </h3>
            <ExplainabilityPanel explanation={entry.explanation_layers} />
          </div>
        ) : null}

        <SimilarTickets ticketId={entry.ticket_id} />
        <ReviewAssistant ticketId={entry.ticket_id} />
        <SuggestedActions ticketId={entry.ticket_id} />

        <Separator />

        <div className="text-sm">
          <span className="text-muted-foreground">Model suggestion: </span>
          <span className="font-medium">
            {entry.department.replaceAll("_", " ")}
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="review-dept">Department</Label>
            <Select value={department} onValueChange={setDepartment}>
              <SelectTrigger id="review-dept" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEPARTMENTS.map((dept) => (
                  <SelectItem key={dept} value={dept}>
                    {dept.replaceAll("_", " ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="review-priority">Priority</Label>
            <Select value={priority} onValueChange={setPriority}>
              <SelectTrigger id="review-priority" className="w-full capitalize">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITIES.map((p) => (
                  <SelectItem key={p} value={p} className="capitalize">
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="review-reason">Correction reason</Label>
          <Select value={reason} onValueChange={setReason}>
            <SelectTrigger id="review-reason" className="w-full">
              <SelectValue placeholder="Select a reason (for overrides)…" />
            </SelectTrigger>
            <SelectContent>
              {CORRECTION_REASONS.map((r) => (
                <SelectItem key={r.value} value={r.value}>
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="review-notes">Review notes (optional)</Label>
          <Textarea
            id="review-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Add any context for this decision…"
            rows={3}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => submit("approved")} className="gap-1.5">
            <Check className="size-4" aria-hidden /> Approve
          </Button>
          <Button
            variant="secondary"
            onClick={() => submit("overridden")}
            disabled={department === entry.department}
            className="gap-1.5"
          >
            <Pencil className="size-4" aria-hidden /> Override
          </Button>
          <Button
            variant="outline"
            onClick={() => submit("escalated")}
            className="gap-1.5"
          >
            <ArrowUpRight className="size-4" aria-hidden /> Escalate
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
