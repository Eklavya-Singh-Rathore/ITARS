"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ConfidenceHistogram } from "@/lib/schemas";
import {
  AXIS_STROKE,
  AXIS_TICK,
  ChartEmpty,
  GRID_STROKE,
  MODE_META,
  TOOLTIP_ITEM_STYLE,
  TOOLTIP_LABEL_STYLE,
  TOOLTIP_STYLE,
} from "./chart-kit";

const MODES = ["AUTO_ROUTE", "AUTO_ROUTE_FLAGGED", "HUMAN_REVIEW"] as const;

/**
 * Hybrid-confidence distribution, stacked by routing mode, with a reference
 * line at the Stage-1 gate floor. The "inert gate" reads at a glance: every
 * bar sits to the right of the floor, so it never fires.
 */
export function ConfidenceHistogramChart({
  histogram,
}: {
  histogram: ConfidenceHistogram;
}) {
  const { bins, series, thresholds } = histogram;
  const data = bins.map((bin, i) => {
    const row: Record<string, number | string> = { label: bin.label };
    for (const mode of MODES) row[mode] = series[mode]?.[i] ?? 0;
    return row;
  });
  const total = data.reduce(
    (sum, row) => sum + MODES.reduce((s, m) => s + (row[m] as number), 0),
    0,
  );
  if (total === 0) {
    return <ChartEmpty message="Analyze tickets to populate the distribution." />;
  }

  const floor = thresholds.hybrid_floor;
  const floorBin = bins.find((b) => floor >= b.lower && floor < b.upper);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 12, right: 8, bottom: 4, left: -18 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
        <XAxis
          dataKey="label"
          tick={AXIS_TICK}
          stroke={AXIS_STROKE}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={AXIS_TICK}
          stroke={AXIS_STROKE}
          tickLine={false}
          width={44}
        />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.35 }}
          contentStyle={TOOLTIP_STYLE}
          labelStyle={TOOLTIP_LABEL_STYLE}
          itemStyle={TOOLTIP_ITEM_STYLE}
          labelFormatter={(l) => `confidence ≥ ${l}`}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 4 }} iconType="circle" />
        {floorBin ? (
          <ReferenceLine
            x={floorBin.label}
            stroke="var(--chart-4)"
            strokeDasharray="5 4"
            label={{
              value: `gate floor ${floor}`,
              fill: "var(--chart-4)",
              fontSize: 11,
              position: "top",
            }}
          />
        ) : null}
        {MODES.map((mode, idx) => (
          <Bar
            key={mode}
            dataKey={mode}
            name={MODE_META[mode].label}
            stackId="confidence"
            fill={MODE_META[mode].color}
            radius={idx === MODES.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
