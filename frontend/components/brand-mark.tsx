import { cn } from "@/lib/utils";

/**
 * ITARS brand mark — a routing-decision engine glyph.
 *
 * An input signal enters a rounded "core" (the intelligent decision engine) and
 * is routed out to three classified destinations. Reads as: AI · routing ·
 * automation · decision intelligence. Strokes use `currentColor` so it inherits
 * the surrounding text colour (e.g. primary-foreground inside the sidebar chip).
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-5", className)}
      aria-hidden
    >
      {/* input signal */}
      <circle cx="3.25" cy="12" r="1.35" fill="currentColor" stroke="none" />
      <path d="M4.6 12 H8.4" />
      {/* the intelligent core */}
      <rect x="8.5" y="8.5" width="7" height="7" rx="2.2" />
      {/* routed outputs */}
      <path d="M15.5 10.2 H18.4" />
      <path d="M15.5 12 H18.4" />
      <path d="M15.5 13.8 H18.4" />
      <circle cx="19.9" cy="10.2" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="19.9" cy="12" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="19.9" cy="13.8" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}
