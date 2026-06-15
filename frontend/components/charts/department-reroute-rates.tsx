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

import type { DepartmentReroute } from "@/lib/schemas";
import {
  AXIS_STROKE,
  AXIS_TICK,
  ChartEmpty,
  prettify,
  rerouteColor,
  TOOLTIP_STYLE,
} from "./chart-kit";

type Row = DepartmentReroute & { label: string };

function RerouteTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Row }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={TOOLTIP_STYLE}>
      <div className="font-medium text-foreground">{d.label}</div>
      <div className="text-muted-foreground">
        {Math.round(d.reroute_rate * 100)}% rerouted · {d.changes}/{d.total}{" "}
        reviews
      </div>
      <div className="text-muted-foreground">
        {d.overrides} overrides · {d.escalations} escalations
      </div>
    </div>
  );
}

/** Per predicted-department, how often human review sent the ticket elsewhere. */
export function DepartmentRerouteRates({
  rows,
}: {
  rows: DepartmentReroute[];
}) {
  if (!rows.length) {
    return (
      <ChartEmpty message="No reviewer feedback captured yet." height={220} />
    );
  }
  const data: Row[] = rows.map((r) => ({ ...r, label: prettify(r.department) }));
  const height = Math.max(180, data.length * 42 + 24);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        layout="vertical"
        data={data}
        margin={{ top: 4, right: 28, bottom: 4, left: 8 }}
      >
        <XAxis
          type="number"
          domain={[0, 1]}
          tickFormatter={(v) => `${Math.round(v * 100)}%`}
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
          content={<RerouteTooltip />}
        />
        <Bar dataKey="reroute_rate" name="reroute rate" radius={[0, 3, 3, 0]}>
          {data.map((d) => (
            <Cell key={d.department} fill={rerouteColor(d.reroute_rate)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
