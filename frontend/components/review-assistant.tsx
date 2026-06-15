"use client";

import * as React from "react";
import { AlertCircle, Loader2, Sparkles } from "lucide-react";

import { aiRecommendation } from "@/lib/api";
import type { AiRecommendationResponse } from "@/lib/schemas";
import { CitationList } from "@/components/citation-list";
import { Button } from "@/components/ui/button";

type State = "idle" | "loading" | "done" | "unavailable";

/** On-demand advisory recommendation for a human-review ticket. Requires
 * retrieval grounding — shows "insufficient evidence" rather than guessing. */
export function ReviewAssistant({ ticketId }: { ticketId: string }) {
  const [state, setState] = React.useState<State>("idle");
  const [rec, setRec] = React.useState<AiRecommendationResponse | null>(null);

  async function run() {
    setState("loading");
    try {
      setRec(await aiRecommendation(ticketId));
      setState("done");
    } catch {
      setState("unavailable");
    }
  }

  return (
    <div className="rounded-md border border-violet-500/20 bg-violet-500/[0.03] p-3">
      <div className="mb-2 flex items-center gap-2">
        <Sparkles className="size-4 text-violet-500" aria-hidden />
        <span className="text-sm font-medium">Review assistant</span>
        <span className="ml-auto text-[11px] uppercase tracking-wide text-muted-foreground">
          advisory
        </span>
      </div>

      {state === "idle" ? (
        <Button
          variant="outline"
          size="sm"
          onClick={() => void run()}
          className="gap-1.5"
        >
          <Sparkles className="size-4" aria-hidden />
          Get AI recommendation
        </Button>
      ) : state === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Analyzing similar tickets…
        </div>
      ) : state === "unavailable" ? (
        <p className="text-sm text-muted-foreground">
          AI assistance is unavailable right now.
        </p>
      ) : rec && rec.status === "ok" ? (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed">{rec.recommendation}</p>
          <CitationList citations={rec.citations} />
          <p className="text-[11px] text-muted-foreground">
            AI-assisted{rec.provider ? ` · ${rec.provider}` : ""} · advisory only;
            the reviewer makes the decision.
          </p>
        </div>
      ) : (
        <div className="flex items-start gap-2 text-sm text-muted-foreground">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            {rec?.message ??
              "Insufficient evidence — no recommendation generated."}
          </span>
        </div>
      )}
    </div>
  );
}
