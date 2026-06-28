"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, Inbox, Languages, Loader2, Search } from "lucide-react";

import { getRecentTickets, translateText } from "@/lib/api";
import type { RecentTicket } from "@/lib/schemas";
import { getAnalyses, onStoreChange, type StoredAnalysis } from "@/lib/session-store";
import {
  DuplicateBadge,
  PriorityBadge,
  RouteBadge,
} from "@/components/status-badges";
import { TableRowsSkeleton } from "@/components/skeletons";
import { TicketRefMenu } from "@/components/ticket-ref-menu";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type Row = {
  ticket_id: string;
  text: string;
  department: string;
  priority: string;
  route: string;
  confidence: number;
  language: string | null;
  translated: boolean;
  is_duplicate: boolean;
  created_at: string | null;
  review_action: string | null;
};

const PAGE_SIZE = 12;
const COLS = 11;
const PRIORITY_RANK: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function fromServer(t: RecentTicket): Row {
  const lang = t.detected_language;
  return {
    ticket_id: t.ticket_id,
    text: t.original_text,
    department: t.department,
    priority: t.priority,
    route: t.route,
    confidence: t.confidence,
    language: lang,
    translated: Boolean(lang && lang.toLowerCase() !== "en"),
    is_duplicate: t.is_duplicate,
    created_at: t.created_at,
    review_action: t.review_action,
  };
}

function fromSession(a: StoredAnalysis): Row {
  return {
    ticket_id: a.ticket_id,
    text: a.original_text ?? "",
    department: a.department,
    priority: a.priority,
    route: a.route,
    confidence: a.confidence,
    language: a.detected_language,
    translated: a.translation_applied,
    is_duplicate: a.is_duplicate,
    created_at: a.analyzed_at,
    review_action: a.review_action ?? null,
  };
}

function sortRows(rows: Row[], sort: string): Row[] {
  const out = [...rows];
  switch (sort) {
    case "oldest":
      return out.sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
    case "conf-desc":
      return out.sort((a, b) => b.confidence - a.confidence);
    case "conf-asc":
      return out.sort((a, b) => a.confidence - b.confidence);
    case "priority":
      return out.sort(
        (a, b) =>
          (PRIORITY_RANK[a.priority?.toLowerCase()] ?? 9) -
          (PRIORITY_RANK[b.priority?.toLowerCase()] ?? 9),
      );
    case "newest":
    default:
      return out.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  }
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function uniqueSorted(values: (string | null | undefined)[]): string[] {
  return Array.from(new Set(values.filter((v): v is string => Boolean(v)))).sort();
}

function AllTicketsInner({ highlight }: { highlight: string | null }) {
  const [rows, setRows] = React.useState<Row[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [serverMode, setServerMode] = React.useState(true);

  const [query, setQuery] = React.useState("");
  const [dept, setDept] = React.useState("all");
  const [priority, setPriority] = React.useState("all");
  const [route, setRoute] = React.useState("all");
  const [sort, setSort] = React.useState("newest");
  const [page, setPage] = React.useState(1);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [highlightId, setHighlightId] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    // setState here runs inside async callbacks (then/catch/store-change), never
    // synchronously in the effect body. Once the data is loaded we know which
    // page the deep-linked ticket is on, so we jump, expand, and highlight it.
    const apply = (mapped: Row[], server: boolean) => {
      if (cancelled) return;
      setServerMode(server);
      setRows(mapped);
      if (highlight) {
        const idx = sortRows(mapped, "newest").findIndex(
          (r) => r.ticket_id === highlight,
        );
        if (idx >= 0) {
          setPage(Math.floor(idx / PAGE_SIZE) + 1);
          setExpanded(highlight);
          setHighlightId(highlight);
        }
      }
    };
    const loadSession = () => apply(getAnalyses().map(fromSession), false);
    getRecentTickets(200)
      .then((data) => apply(data.map(fromServer), true))
      .catch(loadSession)
      .finally(() => !cancelled && setLoading(false));
    const unsubscribe = onStoreChange(() => {
      if (!serverMode) loadSession();
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [serverMode, highlight]);

  const setFilter = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
    setHighlightId(null); // any filter interaction dismisses the deep-link highlight
  };

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = rows.filter((r) => {
      if (dept !== "all" && r.department !== dept) return false;
      if (priority !== "all" && r.priority?.toLowerCase() !== priority) return false;
      if (route !== "all" && r.route !== route) return false;
      if (
        q &&
        !r.ticket_id.toLowerCase().includes(q) &&
        !r.text.toLowerCase().includes(q) &&
        !r.department.toLowerCase().includes(q)
      )
        return false;
      return true;
    });
    return sortRows(matched, sort);
  }, [rows, query, dept, priority, route, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paged = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const departments = React.useMemo(() => uniqueSorted(rows.map((r) => r.department)), [rows]);
  const routes = React.useMemo(() => uniqueSorted(rows.map((r) => r.route)), [rows]);

  // Scroll the deep-linked row into view once it's rendered. The highlight
  // persists until the user clicks a row or changes a filter (see setFilter and
  // the row onClick) — no timer, so no setState-in-effect.
  React.useEffect(() => {
    if (!highlightId || loading) return;
    const el = document.querySelector(`tr[data-ticket-id="${highlightId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightId, safePage, loading]);

  return (
    <div className="space-y-4">
      {!serverMode ? (
        <Alert>
          <Inbox className="size-4" aria-hidden />
          <AlertTitle>Backend offline</AlertTitle>
          <AlertDescription>
            Showing tickets from this browser session. Start the API for the
            persisted decision log.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Toolbar: search + filters + sort */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(e) => setFilter(setQuery)(e.target.value)}
            placeholder="Search text, ID, or department…"
            className="pl-8"
            aria-label="Search tickets"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={dept} onValueChange={setFilter(setDept)}>
            <SelectTrigger className="w-[170px]" aria-label="Filter by department">
              <SelectValue placeholder="Department" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All departments</SelectItem>
              {departments.map((d) => (
                <SelectItem key={d} value={d}>
                  {d.replaceAll("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={priority} onValueChange={setFilter(setPriority)}>
            <SelectTrigger className="w-[130px]" aria-label="Filter by priority">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All priorities</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
          <Select value={route} onValueChange={setFilter(setRoute)}>
            <SelectTrigger className="w-[150px]" aria-label="Filter by routing mode">
              <SelectValue placeholder="Routing" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All routing</SelectItem>
              {routes.map((r) => (
                <SelectItem key={r} value={r}>
                  {r.replaceAll("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={setFilter(setSort)}>
            <SelectTrigger className="w-[150px]" aria-label="Sort tickets">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest first</SelectItem>
              <SelectItem value="oldest">Oldest first</SelectItem>
              <SelectItem value="conf-desc">Confidence ↓</SelectItem>
              <SelectItem value="conf-asc">Confidence ↑</SelectItem>
              <SelectItem value="priority">Priority</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardContent className="px-0 py-0">
          <div className="overflow-x-auto">
            <Table aria-label="All tickets">
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[260px]">Ticket</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Routing</TableHead>
                  <TableHead className="text-right">Conf.</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead>Translation</TableHead>
                  <TableHead>Duplicate</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Review</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              {loading ? (
                <TableRowsSkeleton rows={8} cols={COLS} />
              ) : paged.length === 0 ? (
                <TableBody>
                  <TableRow>
                    <TableCell colSpan={COLS} className="py-12 text-center">
                      <div className="flex flex-col items-center gap-2 text-muted-foreground">
                        <Inbox className="size-7" aria-hidden />
                        <span className="text-sm">
                          {rows.length === 0
                            ? "No tickets yet."
                            : "No tickets match these filters."}
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                </TableBody>
              ) : (
                <TableBody>
                  {paged.map((r) => (
                    <React.Fragment key={r.ticket_id}>
                      <TableRow
                        data-ticket-id={r.ticket_id}
                        onClick={() => {
                          setExpanded((cur) =>
                            cur === r.ticket_id ? null : r.ticket_id,
                          );
                          setHighlightId(null);
                        }}
                        className={cn(
                          "cursor-pointer scroll-mt-24 transition-colors",
                          highlightId === r.ticket_id &&
                            "bg-primary/10 ring-2 ring-primary/40",
                        )}
                      >
                        <TableCell className="max-w-[320px]">
                          <div className="truncate text-sm">{r.text || "—"}</div>
                          <div className="font-mono text-[11px] text-muted-foreground">
                            {r.ticket_id}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm">
                          {r.department.replaceAll("_", " ")}
                        </TableCell>
                        <TableCell>
                          <PriorityBadge priority={r.priority} />
                        </TableCell>
                        <TableCell>
                          <RouteBadge route={r.route} />
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm tabular-nums">
                          {Math.round(r.confidence * 100)}%
                        </TableCell>
                        <TableCell className="text-sm uppercase">
                          {r.language ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {r.translated ? (
                            <span className="inline-flex items-center gap-1 text-sky-600 dark:text-sky-400">
                              <Languages className="size-3.5" aria-hidden /> Translated
                            </span>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell>
                          {r.is_duplicate ? <DuplicateBadge /> : <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {fmtDate(r.created_at)}
                        </TableCell>
                        <TableCell className="text-sm capitalize text-muted-foreground">
                          {r.review_action ?? "—"}
                        </TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <TicketRefMenu ticketId={r.ticket_id} />
                        </TableCell>
                      </TableRow>
                      {expanded === r.ticket_id ? (
                        <TableRow className="bg-muted/30 hover:bg-muted/30">
                          <TableCell colSpan={COLS} className="py-3">
                            <ExpandedTicketDetail row={r} />
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </React.Fragment>
                  ))}
                </TableBody>
              )}
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Pagination */}
      {!loading && filtered.length > 0 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {(safePage - 1) * PAGE_SIZE + 1}–
            {Math.min(safePage * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              className="gap-1"
            >
              <ChevronLeft className="size-4" aria-hidden /> Prev
            </Button>
            <span className="tabular-nums">
              Page {safePage} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
              className="gap-1"
            >
              Next <ChevronRight className="size-4" aria-hidden />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// Module-scoped cache: keyed by ticket id, persists across remounts within a
// browser-session (cleared on full reload). Avoids duplicate /translate calls
// when the user collapses and re-expands a non-English ticket.
const translationCache = new Map<string, string>();

type TranslationState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; text: string }
  | { kind: "error"; message: string };

function ExpandedTicketDetail({ row: r }: { row: Row }) {
  const isNonEnglish = Boolean(r.language && r.language.toLowerCase() !== "en");
  const cached = isNonEnglish ? translationCache.get(r.ticket_id) : undefined;

  const [state, setState] = React.useState<TranslationState>(
    cached ? { kind: "ready", text: cached } : { kind: "idle" },
  );
  const [visible, setVisible] = React.useState<boolean>(Boolean(cached));

  async function handleClick() {
    if (state.kind === "ready") {
      setVisible((v) => !v);
      return;
    }
    if (state.kind === "loading") return;
    setState({ kind: "loading" });
    try {
      const result = await translateText(r.text);
      translationCache.set(r.ticket_id, result.translated_text);
      setState({ kind: "ready", text: result.translated_text });
      setVisible(true);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Translation failed";
      setState({ kind: "error", message });
    }
  }

  const isShowing = visible && state.kind === "ready";
  const buttonLabel =
    state.kind === "loading"
      ? "Translating…"
      : isShowing
        ? "Hide Translation"
        : "Translate";

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Original text
        </div>
        {isNonEnglish ? (
          <Button
            size="sm"
            variant="outline"
            onClick={handleClick}
            disabled={state.kind === "loading"}
            className="h-7 gap-1.5 px-2.5 text-xs"
          >
            {state.kind === "loading" ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <Languages className="size-3.5" aria-hidden />
            )}
            {buttonLabel}
          </Button>
        ) : null}
      </div>
      <p className="max-w-3xl text-sm leading-relaxed">{r.text || "—"}</p>
      <div className="flex flex-wrap gap-x-6 gap-y-1 pt-1 text-xs text-muted-foreground">
        <span>
          Confidence:{" "}
          <span className="font-mono text-foreground">
            {Math.round(r.confidence * 100)}%
          </span>
        </span>
        <span>
          Language:{" "}
          <span className="text-foreground">{r.language?.toUpperCase() ?? "—"}</span>
        </span>
        <span>
          Created: <span className="text-foreground">{fmtDate(r.created_at)}</span>
        </span>
        <span>
          Review:{" "}
          <span className="text-foreground capitalize">{r.review_action ?? "—"}</span>
        </span>
      </div>
      {state.kind === "error" ? (
        <p className="text-xs text-destructive">{state.message}</p>
      ) : null}
      {isShowing ? (
        <div className="mt-2 max-w-3xl space-y-1.5 rounded-md border border-border/60 bg-muted/40 p-3">
          <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            <Languages className="size-3" aria-hidden />
            English Translation
          </div>
          <p className="text-sm leading-relaxed">
            {(state as { kind: "ready"; text: string }).text}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function AllTicketsRouted() {
  const highlight = useSearchParams().get("highlight");
  // Remount on highlight change so deep-link state initializes from the param
  // (no setState-in-effect resets).
  return <AllTicketsInner key={highlight ?? ""} highlight={highlight} />;
}

export default function AllTicketsPage() {
  // useSearchParams must be inside a Suspense boundary for static rendering.
  return (
    <React.Suspense fallback={<div className="h-40" />}>
      <AllTicketsRouted />
    </React.Suspense>
  );
}
