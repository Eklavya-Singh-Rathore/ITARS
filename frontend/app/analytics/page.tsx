"use client";

import * as React from "react";
import { Activity, BarChart3 } from "lucide-react";

import { getAnalyticsSummary, getMonitoringSummary } from "@/lib/api";
import type { MonitoringSummary } from "@/lib/schemas";
import { getAnalyses, onStoreChange } from "@/lib/session-store";
import { ConfidenceHistogramChart } from "@/components/charts/confidence-histogram";
import { DepartmentRerouteRates } from "@/components/charts/department-reroute-rates";
import { GateRuleBreakdown } from "@/components/charts/gate-rule-breakdown";
import { PredictedFinalFlow } from "@/components/charts/predicted-final-flow";
import {
  BarRowsSkeleton,
  ChartSkeleton,
  StatTilesSkeleton,
} from "@/components/skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const MODE_LABELS: Record<string, { label: string; barClass: string }> = {
  AUTO_ROUTE: { label: "Auto-routed", barClass: "bg-emerald-500" },
  AUTO_ROUTE_FLAGGED: { label: "Flagged", barClass: "bg-amber-500" },
  HUMAN_REVIEW: { label: "Human review", barClass: "bg-blue-500" },
};

type Item = { key: string; label: string; count: number; barClass: string };

function DistributionList({
  items,
  loading,
}: {
  items: Item[];
  loading?: boolean;
}) {
  if (loading) {
    return <BarRowsSkeleton rows={3} height={120} />;
  }
  const total = items.reduce((sum, item) => sum + item.count, 0);
  if (total === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No data yet — analyze some tickets first.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const pct = Math.round((item.count / total) * 100);
        return (
          <li key={item.key}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span>{item.label}</span>
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {item.count} · {pct}%
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${item.barClass}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function KpiTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="font-mono text-2xl tabular-nums">{value}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

type Summary = {
  route: Record<string, number>;
  department: Record<string, number>;
  priority: Record<string, number>;
  language: Record<string, number>;
  overrideRate: number | null;
  avgLatency: number | null;
};

const EMPTY: Summary = {
  route: {},
  department: {},
  priority: {},
  language: {},
  overrideRate: null,
  avgLatency: null,
};

export default function AnalyticsPage() {
  const [summary, setSummary] = React.useState<Summary>(EMPTY);
  const [monitoring, setMonitoring] = React.useState<MonitoringSummary | null>(
    null,
  );
  const [serverMode, setServerMode] = React.useState(true);
  const [summaryLoading, setSummaryLoading] = React.useState(true);
  const [monitoringLoading, setMonitoringLoading] = React.useState(true);

  const loadFromSession = React.useCallback(() => {
    const analyses = getAnalyses();
    const tally = (pick: (e: (typeof analyses)[number]) => string | null) => {
      const map: Record<string, number> = {};
      for (const e of analyses) {
        const k = pick(e);
        if (k) map[k] = (map[k] ?? 0) + 1;
      }
      return map;
    };
    setSummary({
      route: tally((e) => e.route),
      department: tally((e) => e.department),
      priority: tally((e) => e.priority),
      language: tally((e) => e.detected_language ?? "unknown"),
      overrideRate: null,
      avgLatency: null,
    });
  }, []);

  const load = React.useCallback(() => {
    getAnalyticsSummary()
      .then((s) => {
        setServerMode(true);
        setSummary({
          route: s.route_mode_counts,
          department: s.department_counts,
          priority: s.priority_counts,
          language: s.language_counts,
          overrideRate: s.override_rate,
          avgLatency: s.avg_latency_ms,
        });
      })
      .catch(() => {
        setServerMode(false);
        setMonitoring(null);
        loadFromSession();
      })
      .finally(() => setSummaryLoading(false));
    // Monitoring is server-only (needs persisted confidence + feedback).
    getMonitoringSummary()
      .then(setMonitoring)
      .catch(() => setMonitoring(null))
      .finally(() => setMonitoringLoading(false));
  }, [loadFromSession]);

  React.useEffect(() => {
    load();
    return onStoreChange(() => {
      if (!serverMode) loadFromSession();
    });
  }, [load, loadFromSession, serverMode]);

  const modeItems: Item[] = Object.entries(MODE_LABELS).map(([key, meta]) => ({
    key,
    label: meta.label,
    count: summary.route[key] ?? 0,
    barClass: meta.barClass,
  }));
  const toItems = (map: Record<string, number>, barClass: string): Item[] =>
    Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .map(([key, count]) => ({
        key,
        label: key.replaceAll("_", " "),
        count,
        barClass,
      }));

  const accuracy = monitoring?.routing_accuracy;

  return (
    <div className="space-y-6">
      {serverMode ? null : (
        <Alert>
          <BarChart3 className="size-4" aria-hidden />
          <AlertTitle>Backend offline</AlertTitle>
          <AlertDescription>
            Showing aggregates from this browser session. Start the API for the
            persisted decision-log analytics.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Routing modes</CardTitle>
            <CardDescription>
              {serverMode
                ? "Persisted across all tickets."
                : "This browser session."}
              {summary.overrideRate !== null
                ? ` · override rate ${Math.round(summary.overrideRate * 100)}%`
                : ""}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DistributionList items={modeItems} loading={summaryLoading} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Departments</CardTitle>
            <CardDescription>Where tickets were routed.</CardDescription>
          </CardHeader>
          <CardContent>
            <DistributionList
              items={toItems(summary.department, "bg-primary")}
              loading={summaryLoading}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Priorities</CardTitle>
            <CardDescription>Predicted severity mix.</CardDescription>
          </CardHeader>
          <CardContent>
            <DistributionList
              items={toItems(summary.priority, "bg-orange-500")}
              loading={summaryLoading}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Detected languages</CardTitle>
            <CardDescription>Translation coverage.</CardDescription>
          </CardHeader>
          <CardContent>
            <DistributionList
              items={toItems(summary.language, "bg-sky-500")}
              loading={summaryLoading}
            />
          </CardContent>
        </Card>
      </div>

      {/* Monitoring (Phase 12) — server-only diagnostics. */}
      <div className="flex items-center gap-2 pt-2">
        <Activity className="size-4 text-muted-foreground" aria-hidden />
        <h2 className="text-sm font-medium tracking-tight">Monitoring</h2>
        <span className="text-xs text-muted-foreground">
          Gate health, tag-map drift, and the human-correction flow
        </span>
      </div>

      {!serverMode ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Monitoring diagnostics need the backend — they read persisted
            confidence scores and reviewer feedback, which aren&apos;t available
            in offline session mode.
          </CardContent>
        </Card>
      ) : monitoringLoading ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTilesSkeleton count={3} />
          </div>
          <Card>
            <CardContent className="pt-6">
              <ChartSkeleton />
            </CardContent>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardContent className="pt-6">
                <BarRowsSkeleton />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <BarRowsSkeleton />
              </CardContent>
            </Card>
          </div>
        </div>
      ) : !monitoring ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Couldn&apos;t load monitoring diagnostics. Refresh to retry.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <KpiTile
              label="Model–reviewer agreement"
              value={
                accuracy && accuracy.total_reviewed > 0
                  ? `${Math.round(accuracy.agreement_rate * 100)}%`
                  : "—"
              }
              hint={
                accuracy && accuracy.total_reviewed > 0
                  ? "Final department matched the prediction"
                  : "No reviews captured yet"
              }
            />
            <KpiTile
              label="Tickets reviewed"
              value={String(accuracy?.total_reviewed ?? 0)}
              hint="Human decisions feeding the loop"
            />
            <KpiTile
              label="Rerouted"
              value={String(accuracy?.changes ?? 0)}
              hint="Sent to a different department"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Confidence distribution by routing mode
              </CardTitle>
              <CardDescription>
                Hybrid-confidence histogram. The dashed line is the Stage-1 gate
                floor — every bar sits to its right, so the floor never fires
                (the audit&apos;s &ldquo;inert gate&rdquo;).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ConfidenceHistogramChart
                histogram={monitoring.confidence_histogram}
              />
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Gate rules fired</CardTitle>
                <CardDescription>
                  Which named rule produced each routing decision.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <GateRuleBreakdown counts={monitoring.gate_rule_counts} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Reroute rate by predicted department
                </CardTitle>
                <CardDescription>
                  How often review sent the ticket elsewhere — a live tag-map
                  health monitor.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DepartmentRerouteRates
                  rows={monitoring.department_reroute_rates}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Predicted → final override flow
              </CardTitle>
              <CardDescription>
                Where human reviewers rerouted tickets. Ribbon width is
                proportional to ticket count.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PredictedFinalFlow links={monitoring.predicted_vs_final} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
