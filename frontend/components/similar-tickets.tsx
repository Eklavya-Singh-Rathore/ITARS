"use client";

import * as React from "react";
import { Layers } from "lucide-react";

import { getSimilarTickets } from "@/lib/api";
import type { RagResult } from "@/lib/schemas";
import { Skeleton } from "@/components/ui/skeleton";

type State = "loading" | "ready" | "unavailable";

/**
 * Cited similar-ticket retrieval (Phase 7 RAG). Hidden entirely when the RAG
 * service is unavailable (503/offline) so the panel never shows a broken state.
 * Shows "no similar resolved ticket found" rather than a weak match below the
 * retrieval-confidence floor.
 */
export function SimilarTickets({ ticketId }: { ticketId: string }) {
  const [state, setState] = React.useState<State>("loading");
  const [items, setItems] = React.useState<RagResult[]>([]);

  React.useEffect(() => {
    // Mounted fresh per ticket via a React key (see usage), so no synchronous
    // reset-to-loading is needed here.
    let cancelled = false;
    getSimilarTickets(ticketId)
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
        setState("ready");
      })
      .catch(() => !cancelled && setState("unavailable"));
    return () => {
      cancelled = true;
    };
  }, [ticketId]);

  if (state === "unavailable") return null;

  return (
    <div className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Layers className="size-3.5" aria-hidden />
        Similar tickets
      </h3>
      {state === "loading" ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No similar resolved ticket found.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li
              key={`${item.ticket_id ?? "x"}-${index}`}
              className="rounded-md border bg-muted/30 p-3"
            >
              <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                <span className="font-mono">{item.ticket_id ?? "—"}</span>
                {item.department ? (
                  <span>· {item.department.replaceAll("_", " ")}</span>
                ) : null}
                <span className="ml-auto font-mono tabular-nums">
                  {Math.round(item.score * 100)}% match
                </span>
              </div>
              <p className="line-clamp-2 text-sm">{item.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
