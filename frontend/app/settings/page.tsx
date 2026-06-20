"use client";

import * as React from "react";
import { Bot, Loader2, PlugZap } from "lucide-react";
import { useTheme } from "next-themes";
import { toast } from "sonner";

import { getAiHealth, getApiUrl, getHealth } from "@/lib/api";
import type { AiHealth } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const emptySubscribe = () => () => {};

function AiStatusCard() {
  const [health, setHealth] = React.useState<AiHealth | null>(null);
  const [state, setState] = React.useState<"loading" | "ready" | "offline">(
    "loading",
  );

  React.useEffect(() => {
    let cancelled = false;
    getAiHealth()
      .then((h) => {
        if (cancelled) return;
        setHealth(h);
        setState("ready");
      })
      .catch(() => !cancelled && setState("offline"));
    return () => {
      cancelled = true;
    };
  }, []);

  const llm = (health?.llm ?? {}) as {
    primary?: string;
    providers?: Record<string, { model?: string; available?: boolean }>;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Bot className="size-4 text-violet-500" aria-hidden />
          AI assistance
        </CardTitle>
        <CardDescription>
          Provider-agnostic gateway. Grok for development, Gemini for
          production — a configuration change only.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {state === "loading" ? (
          <p className="text-sm text-muted-foreground">Checking…</p>
        ) : state === "offline" ? (
          <p className="text-sm text-muted-foreground">
            AI service unavailable (backend offline).
          </p>
        ) : (
          <>
            <div className="text-sm">
              <span className="text-muted-foreground">Active provider: </span>
              <span className="font-medium">{llm.primary ?? "—"}</span>
              <span className="ml-2 text-muted-foreground">
                · retrieval grounding{" "}
                {health?.rag_available ? "enabled" : "unavailable"}
              </span>
            </div>
            <ul className="space-y-1.5">
              {Object.entries(llm.providers ?? {}).map(([name, info]) => (
                <li
                  key={name}
                  className="flex items-center gap-2 text-sm"
                >
                  <span
                    className={cn(
                      "size-2 rounded-full",
                      info.available ? "bg-emerald-500" : "bg-muted-foreground/40",
                    )}
                    aria-hidden
                  />
                  <span className="font-medium">{name}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {info.model}
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {info.available ? "available" : "no key"}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  // Hydration-safe client detection without setState-in-effect.
  const mounted = React.useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
  const [apiUrl] = React.useState(() => getApiUrl());
  const [checking, setChecking] = React.useState(false);

  async function testConnection() {
    setChecking(true);
    try {
      const health = await getHealth();
      toast.success(
        `Connected — v${health.version}, ${health.duplicate_index_size.toLocaleString()} tickets indexed, ${health.tags} tags, ${health.departments} departments.`,
      );
    } catch {
      toast.error(`No backend at ${getApiUrl()}. Is uvicorn running?`);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backend connection</CardTitle>
          <CardDescription>
            Where the FastAPI service runs. Default is{" "}
            <code className="font-mono text-xs">http://localhost:8000</code>{" "}
            (override stored in this browser).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="api-url">API base URL</Label>
            {mounted ? (
              <Input
                id="api-url"
                value={apiUrl}
                readOnly
                aria-readonly
                className="font-mono text-sm text-muted-foreground"
              />
            ) : (
              <div className="h-9 w-full rounded-md border bg-muted/40" />
            )}
            <p className="text-xs text-muted-foreground">
              Configured on the server; read-only here.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void testConnection()}
            disabled={checking}
            className="gap-1.5"
          >
            {checking ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <PlugZap className="size-4" aria-hidden />
            )}
            Test connection
          </Button>
        </CardContent>
      </Card>

      <AiStatusCard />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Appearance</CardTitle>
          <CardDescription>Theme preference for this browser.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="theme-select">Theme</Label>
            {mounted ? (
              <Select value={theme ?? "system"} onValueChange={setTheme}>
                <SelectTrigger id="theme-select" className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="dark">Dark</SelectItem>
                  <SelectItem value="system">System</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <div className="h-9 w-44 rounded-md border bg-muted/40" />
            )}
          </div>
        </CardContent>
      </Card>

    </div>
  );
}
