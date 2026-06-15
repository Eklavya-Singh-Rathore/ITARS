import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  CheckCircle2,
  Copy,
  Flag,
  UserCheck,
} from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Color is reserved for meaning (audit/UX rule), and never the only carrier of
 * it — every badge pairs color with an icon + label.
 *   auto-route = green · flagged = amber · human review = blue
 *   priority low→critical = slate→red
 */

const ROUTE_STYLES: Record<string, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  AUTO_ROUTE: {
    label: "Auto-Routed",
    className:
      "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400",
    Icon: CheckCircle2,
  },
  AUTO_ROUTE_FLAGGED: {
    label: "Auto-Routed + Flagged",
    className:
      "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
    Icon: Flag,
  },
  HUMAN_REVIEW: {
    label: "Human Review",
    className:
      "bg-blue-500/10 text-blue-700 border-blue-500/30 dark:text-blue-400",
    Icon: UserCheck,
  },
};

export function RouteBadge({ route, className }: { route: string; className?: string }) {
  const style = ROUTE_STYLES[route] ?? ROUTE_STYLES.HUMAN_REVIEW;
  const Icon = style.Icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        style.className,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {style.label}
    </span>
  );
}

const PRIORITY_STYLES: Record<string, { className: string; Icon: typeof ArrowUp }> = {
  low: {
    className: "bg-slate-500/10 text-slate-600 border-slate-500/30 dark:text-slate-400",
    Icon: ArrowDown,
  },
  medium: {
    className: "bg-yellow-500/10 text-yellow-700 border-yellow-500/30 dark:text-yellow-400",
    Icon: ArrowRight,
  },
  high: {
    className: "bg-orange-500/10 text-orange-700 border-orange-500/30 dark:text-orange-400",
    Icon: ArrowUp,
  },
  critical: {
    className: "bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-400",
    Icon: AlertTriangle,
  },
};

export function PriorityBadge({ priority, className }: { priority: string; className?: string }) {
  const key = priority.toLowerCase();
  const style = PRIORITY_STYLES[key] ?? PRIORITY_STYLES.medium;
  const Icon = style.Icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium capitalize",
        style.className,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {key}
    </span>
  );
}

export function DuplicateBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-400",
        className,
      )}
    >
      <Copy className="size-3.5" aria-hidden />
      Duplicate
    </span>
  );
}
