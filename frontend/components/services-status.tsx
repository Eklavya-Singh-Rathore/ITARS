"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";

import { getHealth, getLlmHealth } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** A single service's runtime state. `unknown` covers the first-load window. */
type State = "online" | "offline" | "degraded" | "unknown";

interface Service {
  id: string;
  name: string;
  state: State;
  detail?: string;
}

const DOT_STYLES: Record<State, { dot: string; label: string; text: string }> = {
  online: {
    dot: "bg-emerald-500 shadow-[0_0_0_3px] shadow-emerald-500/15",
    label: "Online",
    text: "text-emerald-700 dark:text-emerald-400",
  },
  degraded: {
    dot: "bg-amber-500 shadow-[0_0_0_3px] shadow-amber-500/15",
    label: "Degraded",
    text: "text-amber-700 dark:text-amber-400",
  },
  offline: {
    dot: "bg-red-500 shadow-[0_0_0_3px] shadow-red-500/15",
    label: "Offline",
    text: "text-red-600 dark:text-red-400",
  },
  unknown: {
    dot: "bg-muted-foreground/50",
    label: "Checking",
    text: "text-muted-foreground",
  },
};

/**
 * Aggregate trigger state.
 *
 * The Backend is the critical dependency: if it's down, everything is down.
 * Auxiliary services (Gemini, RAG) being unavailable is "degraded" — the
 * deterministic routing still works, only the advisory AI layer is reduced.
 */
function aggregate(services: Service[]): State {
  const backend = services.find((s) => s.id === "backend");
  if (backend?.state === "unknown") return "unknown";
  if (backend?.state === "offline") return "offline";
  const anyDown = services.some(
    (s) => s.state === "offline" || s.state === "degraded",
  );
  return anyDown ? "degraded" : "online";
}

function ServiceRow({ service }: { service: Service }) {
  const style = DOT_STYLES[service.state];
  return (
    <div className="flex items-start gap-3 px-2 py-2">
      <span
        className={cn("mt-1.5 size-2 shrink-0 rounded-full", style.dot)}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate text-sm font-medium text-foreground">
            {service.name}
          </span>
          <span
            className={cn("text-[11px] font-medium tabular-nums", style.text)}
          >
            {style.label}
          </span>
        </div>
        {service.detail ? (
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {service.detail}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function ServicesStatus({ intervalMs = 30_000 }: { intervalMs?: number }) {
  const [services, setServices] = React.useState<Service[]>(() => [
    { id: "backend", name: "Backend", state: "unknown" },
    { id: "routing", name: "Routing Engine", state: "unknown" },
    { id: "duplicates", name: "Duplicate Detection Engine", state: "unknown" },
    { id: "database", name: "Database", state: "unknown" },
    { id: "gemini", name: "Gemini API", state: "unknown" },
    { id: "rag", name: "RAG Retrieval", state: "unknown" },
  ]);

  const refresh = React.useCallback(async () => {
    // Probe both endpoints in parallel; each failure is independent and falls
    // back to "offline" for its row rather than blanking the whole panel.
    const [healthRes, llmRes] = await Promise.allSettled([
      getHealth(),
      getLlmHealth(),
    ]);
    const next: Service[] = [];
    if (healthRes.status === "fulfilled") {
      const h = healthRes.value;
      const ok = h.status === "ok";
      next.push({
        id: "backend",
        name: "Backend",
        state: ok ? "online" : "degraded",
        detail: `v${h.version}`,
      });
      next.push({
        id: "routing",
        name: "Routing Engine",
        state: h.encoders_loaded && h.tags > 0 ? "online" : "offline",
        detail: `${h.tags} tags · ${h.departments} departments`,
      });
      next.push({
        id: "duplicates",
        name: "Duplicate Detection Engine",
        state: h.duplicate_index_size > 0 ? "online" : "offline",
        detail: `index ${h.duplicate_index_size.toLocaleString()}`,
      });
      // The DB is created on backend boot — its liveness mirrors the backend.
      next.push({
        id: "database",
        name: "Database",
        state: ok ? "online" : "offline",
      });
    } else {
      for (const id of ["backend", "routing", "duplicates", "database"] as const) {
        next.push({
          id,
          name: id === "backend" ? "Backend" : id === "routing" ? "Routing Engine" : id === "duplicates" ? "Duplicate Detection Engine" : "Database",
          state: "offline",
        });
      }
    }
    if (llmRes.status === "fulfilled") {
      const l = llmRes.value;
      const gemini = l.providers["gemini"];
      const isPrimary = l.primary === "gemini";
      next.push({
        id: "gemini",
        name: "Gemini API",
        state: gemini?.available
          ? "online"
          : isPrimary
            ? "offline"
            : "degraded",
        detail: gemini?.model ?? "not configured",
      });
      next.push({
        id: "rag",
        name: "RAG Retrieval",
        // /llm/health doesn't carry RAG state directly; if the gateway answered
        // and we previously saw the backend, the RAG layer is at least mounted.
        state: healthRes.status === "fulfilled" ? "online" : "offline",
      });
    } else {
      next.push({ id: "gemini", name: "Gemini API", state: "offline" });
      next.push({
        id: "rag",
        name: "RAG Retrieval",
        state: healthRes.status === "fulfilled" ? "online" : "offline",
      });
    }
    setServices(next);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      refresh();
    };
    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [intervalMs, refresh]);

  const overall = aggregate(services);
  const aria = `Services status: ${DOT_STYLES[overall].label.toLowerCase()}`;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-auto gap-2 rounded-full border bg-card/60 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-card"
          aria-label={aria}
        >
          <span
            className={cn("size-2 rounded-full", DOT_STYLES[overall].dot)}
            aria-hidden
          />
          <span>Services</span>
          <ChevronDown
            className="size-3 text-muted-foreground/70"
            aria-hidden
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        className="w-72 p-1"
      >
        <DropdownMenuLabel className="flex items-center justify-between gap-2 px-2 py-1.5 text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
          <span>System Status</span>
          <span
            className={cn(
              "text-[10px] font-medium tabular-nums",
              DOT_STYLES[overall].text,
            )}
          >
            {DOT_STYLES[overall].label}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="max-h-[60vh] overflow-y-auto">
          {services.map((s) => (
            <ServiceRow key={s.id} service={s} />
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
