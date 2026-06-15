"use client";

import * as React from "react";
import { ListChecks, Loader2 } from "lucide-react";

import { aiActions } from "@/lib/api";
import type { AiResponse } from "@/lib/schemas";
import { Button } from "@/components/ui/button";

type State = "idle" | "loading" | "done" | "unavailable";

/** On-demand advisory next-actions for the agent. */
export function SuggestedActions({ ticketId }: { ticketId: string }) {
  const [state, setState] = React.useState<State>("idle");
  const [data, setData] = React.useState<AiResponse | null>(null);

  async function run() {
    setState("loading");
    try {
      setData(await aiActions(ticketId));
      setState("done");
    } catch {
      setState("unavailable");
    }
  }

  return (
    <div>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <ListChecks className="size-3.5" aria-hidden />
        Suggested actions
      </h3>
      {state === "idle" ? (
        <Button
          variant="outline"
          size="sm"
          onClick={() => void run()}
          className="gap-1.5"
        >
          <ListChecks className="size-4" aria-hidden />
          Suggest next actions
        </Button>
      ) : state === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Thinking…
        </div>
      ) : state === "unavailable" ? (
        <p className="text-sm text-muted-foreground">
          Suggested actions are unavailable right now.
        </p>
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{data?.text}</p>
      )}
    </div>
  );
}
