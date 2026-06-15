/**
 * Shared chart theming (Phase 12).
 *
 * Colors come from the OKLCH `--chart-*` CSS variables defined in globals.css
 * (they retune for dark mode automatically), mapped to the project's status
 * semantics: auto=emerald, flagged=amber, review=blue, danger=red.
 */
import type { CSSProperties } from "react";

export const MODE_META: Record<string, { label: string; color: string }> = {
  AUTO_ROUTE: { label: "Auto-routed", color: "var(--chart-2)" }, // emerald
  AUTO_ROUTE_FLAGGED: { label: "Flagged", color: "var(--chart-3)" }, // amber
  HUMAN_REVIEW: { label: "Human review", color: "var(--chart-1)" }, // blue
};

export const FLOW_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-5)",
  "var(--chart-4)",
];

export const AXIS_TICK = { fill: "var(--muted-foreground)", fontSize: 11 } as const;
export const AXIS_STROKE = "var(--border)";
export const GRID_STROKE = "var(--border)";

export const TOOLTIP_STYLE: CSSProperties = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "8px",
  color: "var(--popover-foreground)",
  fontSize: "12px",
  boxShadow: "var(--shadow-md)",
  padding: "8px 10px",
  lineHeight: 1.5,
};
export const TOOLTIP_LABEL_STYLE: CSSProperties = {
  color: "var(--muted-foreground)",
  marginBottom: "2px",
  fontSize: "11px",
};
export const TOOLTIP_ITEM_STYLE: CSSProperties = {
  color: "var(--popover-foreground)",
  padding: 0,
};

/** High reroute = the predicted department was often wrong → warn in red. */
export function rerouteColor(rate: number): string {
  if (rate >= 0.5) return "var(--chart-4)"; // red
  if (rate >= 0.25) return "var(--chart-3)"; // amber
  return "var(--chart-2)"; // emerald
}

export function prettify(value: string): string {
  return value.replaceAll("_", " ");
}

export function ChartEmpty({
  message,
  height = 280,
}: {
  message: string;
  height?: number;
}) {
  return (
    <div
      className="flex items-center justify-center text-center text-sm text-muted-foreground"
      style={{ height }}
    >
      {message}
    </div>
  );
}
