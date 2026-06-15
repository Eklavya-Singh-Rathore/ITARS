import Link from "next/link";
import { ArrowRight, ExternalLink, Sparkles } from "lucide-react";

import { ArchitectureFlow } from "@/components/architecture-flow";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = {
  title: "About",
  description:
    "ITARS is an intelligent ticket auto-routing platform that combines a deterministic ML pipeline with grounded AI assistance.",
};

export default function AboutPage() {
  return (
    <div className="animate-rise space-y-8">
      <header className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
          <Sparkles className="size-3" aria-hidden />
          About the project
        </div>
        <h2 className="text-balance text-3xl font-semibold tracking-tight">
          A new standard for support-ticket triage.
        </h2>
        <p className="max-w-2xl text-balance text-base text-muted-foreground">
          ITARS — the Intelligent Ticket Auto-Routing System — turns the
          familiar customer-support inbox into an instrumented, explainable,
          continuously-improving pipeline.
        </p>
      </header>

      <div className="grid items-start gap-8 lg:grid-cols-12">
        {/* Left — narrative (≈65%) */}
        <section className="space-y-6 lg:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">What ITARS does</CardTitle>
              <CardDescription>
                The big picture, without the jargon.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-[15px] leading-relaxed text-muted-foreground">
              <p>
                Every help-desk team faces the same quiet tax: tickets get
                misrouted, duplicates pile up, urgent issues sit behind routine
                ones, and agents lose minutes to triage that a machine could do
                in an instant.{" "}
                <span className="text-foreground">
                  ITARS replaces that friction with a single, deterministic
                  pipeline.
                </span>{" "}
                A ticket comes in, the system identifies near-duplicates, infers
                the topic, predicts the priority, and routes to the right
                department — typically in milliseconds, and always with an
                explanation a human can read.
              </p>
              <p>
                The system is designed around a clear principle:{" "}
                <span className="text-foreground">
                  the routing decision stays deterministic
                </span>
                . Large language models help summarise, recommend and explain,
                but they never decide where a ticket goes. When the model is
                unsure, the ticket lands in a human-review queue ordered by
                uncertainty, so the time reviewers spend is the time that buys
                the most learning. Every override they make feeds back into the
                retrieval layer, sharpening the system as it runs.
              </p>
              <p>
                ITARS is the V2 evolution of a Master&apos;s research build by{" "}
                <span className="text-foreground">Eklavya Singh Rathore</span>
                . Where V1 was a single-screen demo, V2 is a portfolio-grade
                platform: a modular FastAPI backend, a typed Next.js workspace,
                a layered explainability engine, and an analytics suite that
                makes the model&apos;s confidence — and its blind spots —
                visible at a glance. The motivation is straightforward: AI
                should make support teams faster and clearer-eyed, not opaque
                and brittle.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Project vision</CardTitle>
              <CardDescription>
                What this platform is built for.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-[15px] leading-relaxed text-muted-foreground">
              <p>
                A reliable AI system has to be three things at once:{" "}
                <span className="text-foreground">predictable</span>{" "}
                in the path it takes,{" "}
                <span className="text-foreground">honest</span>{" "}
                about the evidence it has, and{" "}
                <span className="text-foreground">improvable</span>{" "}
                through everyday human feedback. ITARS keeps those three
                properties in tension on purpose — and uses the tension to
                produce a platform reviewers actually trust.
              </p>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-3">
            <Button asChild variant="default">
              <Link href="/analyze">
                Try the analyzer
                <ArrowRight className="ml-1 size-3.5" aria-hidden />
              </Link>
            </Button>
            <Button asChild variant="outline">
              <a
                href="https://github.com/Eklavya-Singh-Rathore/ITARS"
                target="_blank"
                rel="noreferrer"
              >
                View on GitHub
                <ExternalLink className="ml-1 size-3.5" aria-hidden />
              </a>
            </Button>
          </div>
        </section>

        {/* Right — animated architecture diagram (≈35%) */}
        <aside
          className="lg:col-span-4 lg:sticky lg:top-20"
          aria-labelledby="architecture-heading"
        >
          <Card>
            <CardHeader>
              <CardTitle id="architecture-heading" className="text-base">
                How a ticket flows
              </CardTitle>
              <CardDescription>
                Each stage lights up as the pipeline carries a ticket through.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ArchitectureFlow />
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
