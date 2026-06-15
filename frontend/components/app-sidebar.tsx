"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FileSearch,
  Info,
  LayoutDashboard,
  MessageSquareText,
  Route,
  Settings,
  UserCheck,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  Icon: typeof LayoutDashboard;
};

type NavGroup = { heading: string; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    heading: "operations",
    items: [
      { href: "/", label: "Dashboard", Icon: LayoutDashboard },
      { href: "/analyze", label: "Ticket Analysis", Icon: FileSearch },
      { href: "/review", label: "Human Review", Icon: UserCheck },
    ],
  },
  {
    heading: "insights",
    items: [
      { href: "/analytics", label: "Analytics", Icon: BarChart3 },
      { href: "/feedback", label: "Feedback", Icon: MessageSquareText },
    ],
  },
  {
    heading: "system",
    items: [
      { href: "/about", label: "About", Icon: Info },
      { href: "/settings", label: "Settings", Icon: Settings },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex flex-col gap-5 px-3">
      {NAV_GROUPS.map((group) => (
        <div key={group.heading} className="flex flex-col gap-1">
          <div className="px-3 pb-1 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground/70">
            {group.heading}
          </div>
          {group.items.map(({ href, label, Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  "transition-[color,background-color,transform] duration-200",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:translate-x-0.5 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
                )}
              >
                {active ? (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                  />
                ) : null}
                <Icon
                  className={cn(
                    "size-4 shrink-0 transition-colors",
                    active
                      ? "text-foreground"
                      : "text-muted-foreground group-hover:text-foreground",
                  )}
                  aria-hidden
                />
                {label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function Wordmark() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-sm">
        <Route className="size-4" aria-hidden />
      </span>
      <span className="min-w-0 leading-tight">
        <span className="block text-sm font-semibold tracking-tight">ITARS</span>
        <span
          className="block text-[10.5px] font-medium leading-snug text-muted-foreground"
          title="Intelligent Ticket Auto Routing System"
        >
          Intelligent Ticket Auto Routing System
        </span>
      </span>
    </Link>
  );
}

export function AppSidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
      <div className="flex h-16 items-center px-4">
        <Wordmark />
      </div>
      <div className="flex-1 overflow-y-auto pb-4 pt-2">
        <SidebarNav />
      </div>
      <div className="border-t border-sidebar-border px-5 py-3">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
          ITARS v2.0 · phase 13
        </div>
      </div>
    </aside>
  );
}
