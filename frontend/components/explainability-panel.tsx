"use client";

import { ChevronDown, Copy, Languages, Microscope, ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import type { TicketExplanation } from "@/lib/schemas";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const GATE_RULE_LABELS: Record<string, string> = {
  margin_pass: "Margin clearance",
  entropy_pass: "Low entropy",
  flagged_band: "Flagged band",
  stage_1_floor: "Stage-1 floor",
  controlled_review: "Controlled review",
  auto_route: "Auto-route",
  human_review: "Human review",
};

function MiniBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full bg-primary", className)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
        {pct}%
      </span>
    </div>
  );
}

function ForensicsBlock({ data }: { data: Record<string, unknown> }) {
  return (
    <ScrollArea className="h-56 rounded-md border">
      <pre className="p-3 font-mono text-[11px] leading-relaxed">
        {JSON.stringify(data, null, 2)}
      </pre>
    </ScrollArea>
  );
}

function RoutingEvidence({ evidence }: { evidence: Record<string, unknown> }) {
  const tagVotes = (evidence.tag_votes as Array<{ tag: string; score: number; department: string }>) ?? [];
  const gateRule = String(evidence.gate_rule ?? "auto_route");
  const classifier = Number(evidence.classifier_confidence ?? 0);
  const semantic = Number(evidence.semantic_similarity ?? 0);
  const escalation = Boolean(evidence.escalation_applied);
  const recommended = evidence.recommended_department as string | undefined;
  const department = evidence.department as string | undefined;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="secondary" className="font-mono">
          gate: {GATE_RULE_LABELS[gateRule] ?? gateRule}
        </Badge>
        {escalation && recommended && department ? (
          <Badge
            variant="outline"
            className="border-amber-500/40 text-amber-700 dark:text-amber-400"
          >
            Escalation override · {recommended.replaceAll("_", " ")} → {department.replaceAll("_", " ")}
          </Badge>
        ) : null}
      </div>

      <div>
        <h4 className="mb-2 text-xs font-medium text-muted-foreground">
          Tag votes (top 3)
        </h4>
        {tagVotes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tags above threshold.</p>
        ) : (
          <ul className="space-y-2">
            {tagVotes.map((vote) => (
              <li
                key={vote.tag}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs">{vote.tag}</div>
                  <div className="text-[11px] text-muted-foreground">
                    → {vote.department.replaceAll("_", " ")}
                  </div>
                </div>
                <MiniBar value={vote.score} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <Separator />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted-foreground">
            Classifier confidence
          </h4>
          <MiniBar value={classifier} className="bg-blue-500" />
        </div>
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted-foreground">
            Semantic similarity
          </h4>
          <MiniBar value={semantic} className="bg-violet-500" />
        </div>
      </div>
    </div>
  );
}

function DuplicateEvidence({ evidence }: { evidence: Record<string, unknown> }) {
  const matchedText = evidence.matched_text_original as string | null;
  const matchedId = evidence.matched_id as string | null;
  const similarity = Number(evidence.similarity ?? 0);
  const threshold = Number(evidence.threshold ?? 0);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-xs">
        <Badge variant="secondary" className="font-mono">
          cos {similarity.toFixed(3)} / thr {threshold.toFixed(3)}
        </Badge>
        {matchedId ? (
          <span className="font-mono text-[11px] text-muted-foreground">
            id {matchedId}
          </span>
        ) : null}
      </div>
      {matchedText ? (
        <div>
          <h4 className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Copy className="size-3.5" aria-hidden />
            Matched ticket (original text)
          </h4>
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            {matchedText}
          </div>
        </div>
      ) : null}
      <MiniBar value={Math.min(similarity, 1)} className="bg-violet-500" />
    </div>
  );
}

function PriorityEvidence({ evidence }: { evidence: Record<string, unknown> }) {
  const urgency = (evidence.urgency_words as string[]) ?? [];
  const negation = (evidence.negation_words as string[]) ?? [];
  const confidence =
    typeof evidence.confidence === "number"
      ? (evidence.confidence as number)
      : null;
  const wordCount = Number(evidence.word_count ?? 0);
  return (
    <div className="space-y-3">
      <div>
        <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">
          Urgency cues
        </h4>
        {urgency.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            None detected — based on embedding signal only.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {urgency.map((word) => (
              <Badge
                key={`u-${word}`}
                variant="outline"
                className="border-orange-500/40 text-orange-700 dark:text-orange-400 font-mono"
              >
                {word}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div>
        <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">
          Negation cues
        </h4>
        {negation.length === 0 ? (
          <p className="text-sm text-muted-foreground">None detected.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {negation.map((word) => (
              <Badge
                key={`n-${word}`}
                variant="outline"
                className="border-slate-500/40 font-mono"
              >
                {word}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span>{wordCount} words</span>
        {confidence !== null ? (
          <span>
            Confidence:{" "}
            <span className="font-mono tabular-nums">
              {(confidence * 100).toFixed(0)}%
            </span>
          </span>
        ) : (
          <span>Confidence: N/A</span>
        )}
      </div>
    </div>
  );
}

export function ExplainabilityPanel({
  explanation,
}: {
  explanation: TicketExplanation;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <div className="rounded-md border bg-muted/30 p-3">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden /> Routing
          </div>
          <p className="text-sm leading-relaxed">{explanation.routing.plain}</p>
        </div>
        {explanation.duplicate ? (
          <div className="rounded-md border bg-muted/30 p-3">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Copy className="size-3.5" aria-hidden /> Duplicate
            </div>
            <p className="text-sm leading-relaxed">
              {explanation.duplicate.plain}
            </p>
          </div>
        ) : null}
        <div className="rounded-md border bg-muted/30 p-3">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Languages className="size-3.5" aria-hidden /> Priority
          </div>
          <p className="text-sm leading-relaxed">{explanation.priority.plain}</p>
        </div>
      </div>

      <Collapsible>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="group flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown
              className="size-3.5 transition-transform group-data-[state=open]:rotate-180"
              aria-hidden
            />
            Evidence &amp; forensics
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          <Tabs defaultValue="evidence">
            <TabsList>
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="forensics">
                <Microscope className="mr-1 size-3.5" aria-hidden />
                Forensics
              </TabsTrigger>
            </TabsList>

            <TabsContent value="evidence" className="space-y-5 pt-3">
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Routing
                </h3>
                <RoutingEvidence evidence={explanation.routing.evidence} />
              </section>
              {explanation.duplicate ? (
                <section>
                  <Separator className="mb-3" />
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Duplicate
                  </h3>
                  <DuplicateEvidence evidence={explanation.duplicate.evidence} />
                </section>
              ) : null}
              <section>
                <Separator className="mb-3" />
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Priority
                </h3>
                <PriorityEvidence evidence={explanation.priority.evidence} />
              </section>
            </TabsContent>

            <TabsContent value="forensics" className="space-y-3 pt-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Routing
              </h3>
              <ForensicsBlock data={explanation.routing.forensics} />
              {explanation.duplicate ? (
                <>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Duplicate
                  </h3>
                  <ForensicsBlock data={explanation.duplicate.forensics} />
                </>
              ) : null}
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Priority
              </h3>
              <ForensicsBlock data={explanation.priority.forensics} />
            </TabsContent>
          </Tabs>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
