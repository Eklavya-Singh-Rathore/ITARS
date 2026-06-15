"use client";

import type { FlowLink } from "@/lib/schemas";
import { ChartEmpty, FLOW_PALETTE, prettify } from "./chart-kit";

const W = 760;
const SIDE = 140; // horizontal room reserved for node labels each side
const NODE_W = 12;
const GAP = 12; // vertical gap between stacked nodes
const PAD = 18; // top/bottom padding
const LABEL_GAP = 6;
const MIN_NODE = 7;

type Node = { name: string; total: number; y: number; h: number };

function layout(
  ordered: Array<[string, number]>,
  unit: number,
): { nodes: Node[]; byName: Map<string, Node> } {
  const nodes: Node[] = [];
  const byName = new Map<string, Node>();
  let y = PAD;
  for (const [name, total] of ordered) {
    const h = Math.max(MIN_NODE, total * unit);
    const node: Node = { name, total, y, h };
    nodes.push(node);
    byName.set(name, node);
    y += h + GAP;
  }
  return { nodes, byName };
}

/**
 * A dependency-free bipartite "Sankey" of the override flow: predicted
 * departments on the left, final (reviewer-chosen) departments on the right,
 * with ribbon widths proportional to ticket count. Strictly two columns, so
 * there are no cycles even when a department appears on both sides.
 */
export function PredictedFinalFlow({
  links,
  maxLinks = 10,
}: {
  links: FlowLink[];
  maxLinks?: number;
}) {
  if (!links.length) {
    return (
      <ChartEmpty
        message="No reroutes yet — overrides and escalations will flow here."
        height={240}
      />
    );
  }

  const shown = links.slice(0, maxLinks);
  const hidden = links.length - shown.length;
  const total = shown.reduce((s, l) => s + l.count, 0);

  const leftTotals = new Map<string, number>();
  const rightTotals = new Map<string, number>();
  for (const l of shown) {
    leftTotals.set(l.predicted, (leftTotals.get(l.predicted) ?? 0) + l.count);
    rightTotals.set(l.final, (rightTotals.get(l.final) ?? 0) + l.count);
  }
  const leftOrdered = [...leftTotals.entries()].sort((a, b) => b[1] - a[1]);
  const rightOrdered = [...rightTotals.entries()].sort((a, b) => b[1] - a[1]);

  const rows = Math.max(leftOrdered.length, rightOrdered.length);
  const H = Math.max(220, PAD * 2 + rows * 30 + (rows - 1) * GAP);
  const usable = H - PAD * 2 - GAP * (rows - 1);
  const unit = total > 0 ? usable / total : 0;

  const left = layout(leftOrdered, unit);
  const right = layout(rightOrdered, unit);

  const colorOf = new Map<string, string>();
  leftOrdered.forEach(([name], i) =>
    colorOf.set(name, FLOW_PALETTE[i % FLOW_PALETTE.length]),
  );

  const x0 = SIDE + NODE_W; // ribbons start at the right edge of left nodes
  const x1 = W - SIDE - NODE_W; // ribbons end at the left edge of right nodes
  const cx = (x0 + x1) / 2;

  const leftOff = new Map<string, number>();
  const rightOff = new Map<string, number>();
  const ribbons = shown
    .slice()
    .sort((a, b) => b.count - a.count)
    .map((l, idx) => {
      const ln = left.byName.get(l.predicted);
      const rn = right.byName.get(l.final);
      if (!ln || !rn) return null;
      const t = l.count * unit;
      const lo = leftOff.get(l.predicted) ?? 0;
      const ro = rightOff.get(l.final) ?? 0;
      leftOff.set(l.predicted, lo + t);
      rightOff.set(l.final, ro + t);
      const ay0 = ln.y + lo;
      const ay1 = ay0 + t;
      const by0 = rn.y + ro;
      const by1 = by0 + t;
      const d = `M ${x0} ${ay0} C ${cx} ${ay0}, ${cx} ${by0}, ${x1} ${by0} L ${x1} ${by1} C ${cx} ${by1}, ${cx} ${ay1}, ${x0} ${ay1} Z`;
      return {
        d,
        color: colorOf.get(l.predicted) ?? FLOW_PALETTE[0],
        key: `${l.predicted}->${l.final}-${idx}`,
      };
    })
    .filter((r): r is { d: string; color: string; key: string } => r !== null);

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ minWidth: 560 }}
        role="img"
        aria-label="Predicted to final department override flow"
      >
        {ribbons.map((r) => (
          <path
            key={r.key}
            d={r.d}
            fill={r.color}
            fillOpacity={0.3}
            stroke={r.color}
            strokeOpacity={0.16}
          />
        ))}
        {left.nodes.map((n) => (
          <g key={`l-${n.name}`}>
            <rect
              x={SIDE}
              y={n.y}
              width={NODE_W}
              height={n.h}
              rx={2}
              fill={colorOf.get(n.name) ?? FLOW_PALETTE[0]}
            />
            <text
              x={SIDE - LABEL_GAP}
              y={n.y + n.h / 2}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--foreground)"
            >
              {prettify(n.name)}
            </text>
          </g>
        ))}
        {right.nodes.map((n) => (
          <g key={`r-${n.name}`}>
            <rect
              x={W - SIDE - NODE_W}
              y={n.y}
              width={NODE_W}
              height={n.h}
              rx={2}
              fill="var(--muted-foreground)"
            />
            <text
              x={W - SIDE + LABEL_GAP}
              y={n.y + n.h / 2}
              textAnchor="start"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--foreground)"
            >
              {prettify(n.name)}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-1 flex justify-between px-1 text-[11px] text-muted-foreground">
        <span>Predicted</span>
        {hidden > 0 ? <span>+{hidden} smaller flows</span> : <span />}
        <span>Final</span>
      </div>
    </div>
  );
}
