"use client";

import * as React from "react";
import Link from "next/link";
import {
  Activity,
  Clock,
  Copy,
  Database,
  FileSearch,
  Inbox,
} from "lucide-react";

import { getHealth, getMetrics, getRecentTickets } from "@/lib/api";
import type {
  HealthResponse,
  MetricsResponse,
  RecentTicket,
} from "@/lib/schemas";
import {
  getAnalyses,
  onStoreChange,
  type StoredAnalysis,
} from "@/lib/session-store";

type RecentRow = {
  key: string;
  ticket_id: string;
  original_text: string | null;
  route: string;
  department: string;
  priority: string;
  confidence: number;
  is_duplicate: boolean;
};

const fromServer = (t: RecentTicket): RecentRow => ({
  key: `${t.ticket_id}-${t.created_at ?? ""}`,
  ticket_id: t.ticket_id,
  original_text: t.original_text,
  route: t.route,
  department: t.department,
  priority: t.priority,
  confidence: t.confidence,
  is_duplicate: t.is_duplicate,
});

const fromSession = (a: StoredAnalysis): RecentRow => ({
  key: `${a.ticket_id}-${a.analyzed_at}`,
  ticket_id: a.ticket_id,
  original_text: a.original_text,
  route: a.route,
  department: a.department,
  priority: a.priority,
  confidence: a.confidence,
  is_duplicate: a.is_duplicate,
});
import { PriorityBadge, RouteBadge } from "@/components/status-badges";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TableRowsSkeleton } from "@/components/skeletons";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function KpiCard({
  title,
  value,
  hint,
  Icon,
  loading,
  index = 0,
}: {
  title: string;
  value: string;
  hint?: string;
  Icon: typeof Activity;
  loading?: boolean;
  index?: number;
}) {
  return (
    <Card
      className="animate-rise gap-3 border-border/60 py-5 transition-shadow duration-200 hover:shadow-md"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 px-5">
        <CardTitle className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
          {title}
        </CardTitle>
        <span
          className="flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground"
          aria-hidden
        >
          <Icon className="size-4" />
        </span>
      </CardHeader>
      <CardContent className="px-5">
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <div className="font-mono text-[28px] font-semibold leading-none tracking-tight tabular-nums">
            {value}
          </div>
        )}
        {hint ? (
          <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const [metrics, setMetrics] = React.useState<MetricsResponse | null>(null);
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [offline, setOffline] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [recent, setRecent] = React.useState<RecentRow[]>([]);
  const [recentLoading, setRecentLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    const load = () =>
      getRecentTickets(8)
        .then((rows) => !cancelled && setRecent(rows.map(fromServer)))
        .catch(
          () =>
            !cancelled &&
            setRecent(getAnalyses().slice(0, 8).map(fromSession)),
        )
        .finally(() => !cancelled && setRecentLoading(false));
    load();
    const unsubscribe = onStoreChange(load);
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    Promise.all([getMetrics(), getHealth()])
      .then(([m, h]) => {
        if (cancelled) return;
        setMetrics(m);
        setHealth(h);
        setOffline(false);
      })
      .catch(() => !cancelled && setOffline(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const total = metrics?.requests_total ?? 0;
  const autoCount = metrics?.route_mode_counts?.AUTO_ROUTE ?? 0;
  const reviewCount = metrics?.route_mode_counts?.HUMAN_REVIEW ?? 0;
  const pct = (n: number) =>
    total > 0 ? `${Math.round((n / total) * 100)}%` : "—";

  return (
    <div className="space-y-6">
      {offline ? (
        <Alert>
          <Activity className="size-4" aria-hidden />
          <AlertTitle>Backend offline</AlertTitle>
          <AlertDescription>
            Start the API with{" "}
            <code className="font-mono text-xs">
              uvicorn backend.app:app
            </code>{" "}
            from <code className="font-mono text-xs">main/</code>, then refresh.
            Session history below still works.
          </AlertDescription>
        </Alert>
      ) : null}

      <section
        aria-label="Key metrics"
        className="grid grid-cols-2 gap-3 xl:grid-cols-5"
      >
        <KpiCard
          index={0}
          title="Requests (session)"
          value={offline ? "—" : String(total)}
          hint="Since backend start"
          Icon={Activity}
          loading={loading}
        />
        <KpiCard
          index={1}
          title="Auto-route rate"
          value={offline ? "—" : pct(autoCount)}
          hint={total ? `${autoCount} of ${total}` : undefined}
          Icon={FileSearch}
          loading={loading}
        />
        <KpiCard
          index={2}
          title="Review rate"
          value={offline ? "—" : pct(reviewCount)}
          hint={total ? `${reviewCount} of ${total}` : undefined}
          Icon={Inbox}
          loading={loading}
        />
        <KpiCard
          index={3}
          title="Avg latency"
          value={
            offline || !metrics ? "—" : `${Math.round(metrics.avg_latency_ms)} ms`
          }
          Icon={Clock}
          loading={loading}
        />
        <KpiCard
          index={4}
          title="Indexed tickets"
          value={
            offline || !health
              ? "—"
              : health.duplicate_index_size.toLocaleString()
          }
          hint={
            health
              ? `${health.tags} tags · ${health.departments} departments`
              : undefined
          }
          Icon={Database}
          loading={loading}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent analyses</CardTitle>
          <CardDescription>
            {offline
              ? "Latest tickets from this browser session."
              : "Latest routing decisions from the persisted decision log."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!recentLoading && recent.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <Inbox className="size-8 text-muted-foreground" aria-hidden />
              <p className="text-sm text-muted-foreground">
                No tickets analyzed yet.
              </p>
              <Button asChild size="sm">
                <Link href="/analyze">Analyze a ticket</Link>
              </Button>
            </div>
          ) : (
            <Table aria-label="Recent analyses">
              <TableHeader>
                <TableRow>
                  <TableHead>Ticket</TableHead>
                  <TableHead>Routing</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead className="text-right">Confidence</TableHead>
                </TableRow>
              </TableHeader>
              {recentLoading ? (
                <TableRowsSkeleton rows={6} cols={5} />
              ) : (
              <TableBody>
                {recent.map((entry) => (
                  <TableRow key={entry.key}>
                    <TableCell className="max-w-[280px]">
                      <div className="truncate text-sm">
                        {entry.original_text ?? "—"}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                        {entry.ticket_id}
                        {entry.is_duplicate ? (
                          <span className="inline-flex items-center gap-1 text-violet-600 dark:text-violet-400">
                            <Copy className="size-3" aria-hidden /> dup
                          </span>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <RouteBadge route={entry.route} />
                    </TableCell>
                    <TableCell className="text-sm">
                      {entry.department.replaceAll("_", " ")}
                    </TableCell>
                    <TableCell>
                      <PriorityBadge priority={entry.priority} />
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm tabular-nums">
                      {Math.round(entry.confidence * 100)}%
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
