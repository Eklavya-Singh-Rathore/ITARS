import type { RagResult } from "@/lib/schemas";

/** Source citations for AI output — ticket id, department, match %, snippet. */
export function CitationList({ citations }: { citations: RagResult[] }) {
  if (!citations.length) return null;
  return (
    <div className="space-y-1.5">
      <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Citations
      </h4>
      <ul className="space-y-1.5">
        {citations.map((c, i) => (
          <li
            key={`${c.ticket_id ?? "x"}-${i}`}
            className="rounded-md border bg-muted/30 p-2.5"
          >
            <div className="mb-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="font-mono">{c.ticket_id ?? "—"}</span>
              {c.department ? (
                <span>· {c.department.replaceAll("_", " ")}</span>
              ) : null}
              <span className="ml-auto font-mono tabular-nums">
                {Math.round(c.score * 100)}% match
              </span>
            </div>
            <p className="line-clamp-2 text-xs">{c.text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
