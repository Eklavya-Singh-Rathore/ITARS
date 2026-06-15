"use client";

import * as React from "react";
import {
  Languages,
  Loader2,
  SendHorizonal,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { analyzeTicket, ApiError } from "@/lib/api";
import type { AnalyzeResponse } from "@/lib/schemas";
import { addAnalysis } from "@/lib/session-store";
import { AiAssistantCard } from "@/components/ai-assistant-card";
import { ConfidenceBar } from "@/components/confidence-bar";
import { ExplainabilityPanel } from "@/components/explainability-panel";
import { SimilarTickets } from "@/components/similar-tickets";
import {
  DuplicateBadge,
  PriorityBadge,
  RouteBadge,
} from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

const EXAMPLES = [
  "The email server has been down since this morning. No one can send or receive emails. This is critical!",
  "I was charged twice for my last month's subscription. Please process a refund for the duplicate charge.",
  "I cannot access the company VPN from my home network. It keeps showing authentication failed.",
  "Can you provide training materials for the new CRM software deployed last week?",
];

function ResultCard({ result }: { result: AnalyzeResponse }) {
  return (
    <Card className="animate-rise">
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <RouteBadge route={result.route} />
          <PriorityBadge priority={result.priority} />
          {result.is_duplicate ? <DuplicateBadge /> : null}
          <span className="ml-auto font-mono text-xs text-muted-foreground">
            {result.ticket_id} · {Math.round(result.latency_ms)} ms
          </span>
        </div>
        <CardTitle className="text-xl">
          {result.department.replaceAll("_", " ")}
        </CardTitle>
        <CardDescription>{result.message}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <ConfidenceBar value={result.confidence} />

        <div>
          <h3 className="mb-2 text-xs font-medium text-muted-foreground">
            Predicted tags
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {result.tag_votes.length > 0 ? (
              result.tag_votes.map((vote) => (
                <Badge key={vote.tag} variant="secondary" className="font-mono">
                  {vote.tag} · {vote.score.toFixed(2)}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">
                No tags above threshold.
              </span>
            )}
          </div>
        </div>

        {result.translation_applied ? (
          <>
            <Separator />
            <div className="space-y-2">
              <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Languages className="size-3.5" aria-hidden />
                Translated from {result.detected_language?.toUpperCase()} —
                routed on the English text
              </h3>
              <div className="grid gap-2 md:grid-cols-2">
                <div className="rounded-md border bg-muted/40 p-3 text-sm">
                  <div className="mb-1 text-[11px] font-medium text-muted-foreground">
                    Original
                  </div>
                  {result.original_text}
                </div>
                <div className="rounded-md border bg-muted/40 p-3 text-sm">
                  <div className="mb-1 text-[11px] font-medium text-muted-foreground">
                    English
                  </div>
                  {result.translated_text}
                </div>
              </div>
            </div>
          </>
        ) : null}

        <Separator />
        {result.explanation_layers ? (
          <ExplainabilityPanel explanation={result.explanation_layers} />
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {result.explanation}
          </p>
        )}

        <Separator />
        <SimilarTickets key={result.ticket_id} ticketId={result.ticket_id} />
      </CardContent>
    </Card>
  );
}

export default function AnalyzePage() {
  const [text, setText] = React.useState("");
  const [translate, setTranslate] = React.useState(true);
  const [register, setRegister] = React.useState(true);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<AnalyzeResponse | null>(null);

  async function submit() {
    const trimmed = text.trim();
    if (!trimmed) {
      toast.error("Enter ticket text first.");
      return;
    }
    setLoading(true);
    try {
      const response = await analyzeTicket({
        text: trimmed,
        translate,
        register,
      });
      setResult(response);
      addAnalysis(response);
      toast.success(
        `Routed to ${response.department.replaceAll("_", " ")} (${response.route.replaceAll("_", " ").toLowerCase()})`,
      );
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Analysis failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Submit a ticket</CardTitle>
          <CardDescription>
            Full pipeline: translation → duplicate check → tags → priority →
            hybrid routing → confidence gate.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ticket-text">Ticket description</Label>
            <Textarea
              id="ticket-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder="Describe the support issue in detail…"
              rows={7}
              disabled={loading}
            />
            <p className="text-xs text-muted-foreground">
              Ctrl/Cmd + Enter to submit
            </p>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="opt-translate" className="text-sm font-normal">
              Detect language &amp; translate
            </Label>
            <Switch
              id="opt-translate"
              checked={translate}
              onCheckedChange={setTranslate}
              disabled={loading}
            />
          </div>
          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="opt-register" className="text-sm font-normal">
              Add to duplicate index
            </Label>
            <Switch
              id="opt-register"
              checked={register}
              onCheckedChange={setRegister}
              disabled={loading}
            />
          </div>

          <Button onClick={() => void submit()} disabled={loading} className="w-full">
            {loading ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <SendHorizonal className="size-4" aria-hidden />
            )}
            {loading ? "Analyzing…" : "Process ticket"}
          </Button>

          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">
              Try an example
            </p>
            {EXAMPLES.map((example) => (
              <button
                key={example.slice(0, 24)}
                type="button"
                onClick={() => setText(example)}
                disabled={loading}
                className="block w-full cursor-pointer truncate rounded-md border px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {example}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {result ? (
        <div className="space-y-6">
          <ResultCard result={result} />
          <AiAssistantCard result={result} />
        </div>
      ) : (
        <Card className="flex min-h-[420px] items-center justify-center border-dashed">
          <CardContent className="flex flex-col items-center gap-3 text-center">
            <Sparkles className="size-8 text-muted-foreground" aria-hidden />
            <p className="max-w-xs text-sm text-muted-foreground">
              The routing decision — department, priority, tags, duplicate
              match, and explanation — appears here.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
