"use client";

import * as React from "react";
import { Loader2, PlugZap, Sparkles, Trash2 } from "lucide-react";
import { useTheme } from "next-themes";
import { toast } from "sonner";

import { API_URL_STORAGE_KEY, getAiHealth, getApiUrl, getHealth } from "@/lib/api";
import type { AiHealth } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { clearAnalyses } from "@/lib/session-store";
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
          <Sparkles className="size-4 text-violet-500" aria-hidden />
          AI assistance
        </CardTitle>
        <CardDescription>
          Provider-agnostic gateway (Phase 8). Grok for development, Gemini for
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
  const [apiUrl, setApiUrl] = React.useState(() => getApiUrl());
  const [checking, setChecking] = React.useState(false);

  function saveApiUrl() {
    const trimmed = apiUrl.trim().replace(/\/+$/, "");
    if (!trimmed) {
      window.localStorage.removeItem(API_URL_STORAGE_KEY);
      setApiUrl(getApiUrl());
      toast.success("API URL reset to default.");
      return;
    }
    try {
      new URL(trimmed);
    } catch {
      toast.error("Enter a valid URL, e.g. http://localhost:8000");
      return;
    }
    window.localStorage.setItem(API_URL_STORAGE_KEY, trimmed);
    toast.success(`API URL set to ${trimmed}`);
  }

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

  function clearSession() {
    clearAnalyses();
    toast.success("Session history cleared.");
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
              <div className="flex gap-2">
                <Input
                  id="api-url"
                  value={apiUrl}
                  onChange={(event) => setApiUrl(event.target.value)}
                  placeholder="http://localhost:8000"
                  className="font-mono text-sm"
                />
                <Button variant="secondary" onClick={saveApiUrl}>
                  Save
                </Button>
              </div>
            ) : (
              <div className="h-9 w-full rounded-md border bg-muted/40" />
            )}
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Session data</CardTitle>
          <CardDescription>
            Analyses and review decisions are stored in this browser until
            Phase 6 adds server-side persistence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            onClick={clearSession}
            className="gap-1.5 text-destructive hover:text-destructive"
          >
            <Trash2 className="size-4" aria-hidden />
            Clear session history
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
