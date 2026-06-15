import Link from "next/link";
import { ArrowLeft, Route } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <span className="mb-6 flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-md">
        <Route className="size-6" aria-hidden />
      </span>
      <p className="font-mono text-sm uppercase tracking-[0.2em] text-muted-foreground">
        404 — no route
      </p>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight">
        This ticket has no destination
      </h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        The page you were looking for could not be found. It may have been moved
        or never existed.
      </p>
      <Button asChild className="mt-6">
        <Link href="/">
          <ArrowLeft className="size-4" aria-hidden />
          Back to dashboard
        </Link>
      </Button>
    </div>
  );
}
