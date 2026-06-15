"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AXIS_STROKE,
  AXIS_TICK,
  ChartEmpty,
  FLOW_PALETTE,
  prettify,
  TOOLTIP_ITEM_STYLE,
  TOOLTIP_LABEL_STYLE,
  TOOLTIP_STYLE,
} from "./chart-kit";

/** How often each *named* gate rule fired (margin_pass, stage_1_floor, ...). */
export function GateRuleBreakdown({
  counts,
}: {
  counts: Record<string, number>;
}) {
  const data = Object.entries(counts)
    .map(([rule, count]) => ({ rule, label: prettify(rule), count }))
    .sort((a, b) => b.count - a.count);

  if (data.length === 0) {
    return (
      <ChartEmpty message="No routing decisions recorded yet." height={220} />
    );
  }

  const height = Math.max(180, data.length * 42 + 24);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        layout="vertical"
        data={data}
        margin={{ top: 4, right: 20, bottom: 4, left: 8 }}
      >
        <XAxis
          type="number"
          allowDecimals={false}
          tick={AXIS_TICK}
          stroke={AXIS_STROKE}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={116}
          tick={AXIS_TICK}
          stroke={AXIS_STROKE}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.35 }}
          contentStyle={TOOLTIP_STYLE}
          labelStyle={TOOLTIP_LABEL_STYLE}
          itemStyle={TOOLTIP_ITEM_STYLE}
        />
        <Bar dataKey="count" name="tickets" radius={[0, 3, 3, 0]}>
          {data.map((d, i) => (
            <Cell key={d.rule} fill={FLOW_PALETTE[i % FLOW_PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
