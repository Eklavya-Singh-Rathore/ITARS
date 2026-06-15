"use client";

import * as React from "react";
import { Loader2, MessageSquareText, Sparkles } from "lucide-react";

import { aiExplanation, aiSummary } from "@/lib/api";
import type { AiResponse, AnalyzeResponse } from "@/lib/schemas";
import { CitationList } from "@/components/citation-list";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

type State = "loading" | "ready" | "unavailable";

function AiBadge({ provider }: { provider?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[11px] font-medium text-violet-700 dark:text-violet-400">
      <Sparkles className="size-3" aria-hidden />
      AI-assisted{provider ? ` · ${provider}` : ""}
    </span>
  );
}

/** AI assistance for an analyzed ticket: grounded summary + on-demand routing
 * explanation. Hidden entirely when the AI service is unavailable. Clearly
 * labeled advisory — the routing decision stays with the deterministic engine. */
export function AiAssistantCard({ result }: { result: AnalyzeResponse }) {
  const [state, setState] = React.useState<State>("loading");
  const [summary, setSummary] = React.useState<AiResponse | null>(null);
  const [explanation, setExplanation] = React.useState<AiResponse | null>(null);
  const [explaining, setExplaining] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    aiSummary(result.original_text ?? "", result.ticket_id)
      .then((r) => {
        if (cancelled) return;
        setSummary(r);
        setState("ready");
      })
      .catch(() => !cancelled && setState("unavailable"));
    return () => {
      cancelled = true;
    };
  }, [result.ticket_id, result.original_text]);

  async function explain() {
    setExplaining(true);
    try {
      setExplanation(
        await aiExplanation({
          department: result.department,
          route: result.route,
          explanation: (result.explanation_layers?.routing ?? {}) as Record<
            string,
            unknown
          >,
        }),
      );
    } catch {
      /* leave the button; degrade silently */
    } finally {
      setExplaining(false);
    }
  }

  if (state === "unavailable") return null;

  return (
    <Card className="animate-rise border-violet-500/20">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4 text-violet-500" aria-hidden />
          AI assistant
        </CardTitle>
        {summary ? <AiBadge provider={summary.provider} /> : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h3 className="mb-1 text-xs font-medium text-muted-foreground">
            Summary
          </h3>
          {state === "loading" ? (
            <div className="space-y-1.5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : (
            <p className="text-sm leading-relaxed">{summary?.text}</p>
          )}
        </div>

        {summary && summary.citations.length > 0 ? (
          <CitationList citations={summary.citations} />
        ) : null}

        <Separator />

        {explanation ? (
          <div>
            <h3 className="mb-1 text-xs font-medium text-muted-foreground">
              AI explanation
            </h3>
            <p className="text-sm leading-relaxed">{explanation.text}</p>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void explain()}
            disabled={explaining}
            className="gap-1.5"
          >
            {explaining ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <MessageSquareText className="size-4" aria-hidden />
            )}
            Explain decision with AI
          </Button>
        )}

        <p className="text-[11px] leading-relaxed text-muted-foreground">
          AI assistance is advisory and grounded in retrieved tickets. The
          routing decision is made by the deterministic engine, not the AI.
        </p>
      </CardContent>
    </Card>
  );
}
