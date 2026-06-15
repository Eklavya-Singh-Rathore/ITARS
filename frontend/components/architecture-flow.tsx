"use client";

import * as React from "react";
import {
  Building2,
  CheckCircle2,
  Copy,
  Gauge,
  Inbox,
  Route,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface FlowNode {
  id: string;
  label: string;
  Icon: typeof Inbox;
}

const NODES: FlowNode[] = [
  { id: "input", label: "Ticket Input", Icon: Inbox },
  { id: "duplicate", label: "Duplicate Detection", Icon: Copy },
  { id: "routing", label: "Routing Engine", Icon: Route },
  { id: "priority", label: "Priority Prediction", Icon: Gauge },
  { id: "department", label: "Department Assignment", Icon: Building2 },
  { id: "decision", label: "Final Decision", Icon: CheckCircle2 },
];

const PERIOD_S = 6; // total loop duration — 1s active per node

/**
 * Animated vertical pipeline of the routing workflow, for the About page.
 *
 * - SVG-free: each node is a real DOM element so it stays accessible and
 *   responsive without measurement math.
 * - The "active" pulse cycles via per-node `animation-delay`, so the work
 *   happens once in CSS and there are no React re-renders per frame.
 * - Connectors run a dashed gradient downward; the marching-ant offset gives
 *   a clear sense of flow without needing real packets.
 * - Honours `prefers-reduced-motion`: the page reduces to a static diagram.
 */
export function ArchitectureFlow() {
  return (
    <div
      className="architecture-flow relative isolate flex flex-col items-stretch gap-0 py-2"
      role="img"
      aria-label="ITARS routing pipeline: ticket input flows through duplicate detection, routing engine, priority prediction, department assignment, and final decision"
    >
      {NODES.map((node, idx) => (
        <React.Fragment key={node.id}>
          <FlowCard node={node} index={idx} />
          {idx < NODES.length - 1 ? <FlowConnector index={idx} /> : null}
        </React.Fragment>
      ))}
    </div>
  );
}

function FlowCard({ node, index }: { node: FlowNode; index: number }) {
  const { Icon } = node;
  return (
    <div
      className={cn(
        "arch-node group relative z-10 flex items-center gap-3 rounded-xl border bg-card/80 px-4 py-3 shadow-sm backdrop-blur-sm",
        "transition-shadow",
      )}
      style={
        {
          animationDelay: `${index}s`,
          ["--arch-node-delay" as string]: `${index}s`,
        } as React.CSSProperties
      }
    >
      <span
        className="arch-node-icon flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
        aria-hidden
      >
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          Stage {index + 1}
        </div>
        <div className="truncate text-sm font-medium text-foreground">
          {node.label}
        </div>
      </div>
    </div>
  );
}

function FlowConnector({ index }: { index: number }) {
  return (
    <div
      className="arch-connector relative my-1 ml-[18px] h-7 w-0.5 overflow-hidden rounded-full bg-border"
      style={
        {
          animationDelay: `${index + 0.5}s`,
          ["--arch-conn-delay" as string]: `${index + 0.5}s`,
        } as React.CSSProperties
      }
      aria-hidden
    >
      <span className="arch-connector-pulse absolute inset-x-0 top-0 h-full" />
    </div>
  );
}

// Keyframes + reduced-motion handling live in globals.css so the styling stays
// theme-aware (OKLCH primary). See `.arch-node` / `.arch-connector` blocks.
export const _ARCH_PERIOD_S = PERIOD_S;
