/**
 * Shared loading skeletons (Phase 13).
 *
 * Presentational only (no hooks) — render while a list view's first fetch is in
 * flight, so pages reveal their final layout immediately instead of flashing an
 * empty state. Deterministic bar heights avoid hydration mismatch.
 */
import { Skeleton } from "@/components/ui/skeleton";
import { TableBody, TableCell, TableRow } from "@/components/ui/table";

export function TableRowsSkeleton({
  rows = 5,
  cols = 5,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <TableBody>
      {Array.from({ length: rows }).map((_, r) => (
        <TableRow key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <TableCell key={c}>
              <Skeleton
                className="h-4"
                style={{ width: c === 0 ? "85%" : `${50 + ((r + c) % 3) * 12}%` }}
              />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </TableBody>
  );
}

export function StatTilesSkeleton({ count = 4 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-md border bg-muted/20 px-4 py-3">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-2 h-6 w-12" />
        </div>
      ))}
    </>
  );
}

const BAR_HEIGHTS = [58, 84, 46, 96, 70, 52, 80, 40, 66, 90];

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div
      className="flex flex-col justify-end gap-3"
      style={{ height }}
      aria-hidden
    >
      <div
        className="flex items-end gap-2"
        style={{ height: height - 28 }}
      >
        {BAR_HEIGHTS.map((h, i) => (
          <Skeleton key={i} className="flex-1" style={{ height: `${h}%` }} />
        ))}
      </div>
      <Skeleton className="h-3 w-28" />
    </div>
  );
}

export function BarRowsSkeleton({
  rows = 5,
  height = 180,
}: {
  rows?: number;
  height?: number;
}) {
  return (
    <div
      className="flex flex-col justify-center gap-3"
      style={{ height }}
      aria-hidden
    >
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-3 w-24 shrink-0" />
          <Skeleton
            className="h-5"
            style={{ width: `${40 + ((i * 17) % 50)}%` }}
          />
        </div>
      ))}
    </div>
  );
}

export function QueueSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-md border p-3">
          <div className="mb-2 flex items-center justify-between">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-4 w-9" />
          </div>
          <Skeleton className="h-4 w-full" />
        </div>
      ))}
    </div>
  );
}
