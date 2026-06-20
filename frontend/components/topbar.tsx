"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { Menu, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { BrandMark } from "@/components/brand-mark";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { SidebarNav } from "@/components/app-sidebar";
import { ServicesStatus } from "@/components/services-status";

const PAGE_META: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Dashboard", subtitle: "Routing health at a glance" },
  "/analyze": {
    title: "Ticket Analysis",
    subtitle: "Submit a ticket and inspect the routing decision",
  },
  "/all-tickets": {
    title: "All Tickets",
    subtitle: "Browse, search, and filter every analyzed ticket",
  },
  "/review": {
    title: "Human Review",
    subtitle: "Flagged and low-confidence tickets",
  },
  "/analytics": {
    title: "Analytics",
    subtitle: "Distributions across routing, priority, and language",
  },
  "/feedback": {
    title: "Feedback",
    subtitle: "Human corrections captured from review",
  },
  "/about": { title: "About", subtitle: "Project overview and vision" },
  "/settings": { title: "Settings", subtitle: "Backend connection and appearance" },
};

function ThemeToggle() {
  const { setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Toggle theme"
          className="transition-transform active:scale-95"
        >
          <Sun className="size-4 dark:hidden" aria-hidden />
          <Moon className="hidden size-4 dark:block" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>Light</DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>Dark</DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>System</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const meta = PAGE_META[pathname] ?? { title: "ITARS", subtitle: "" };

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md lg:px-8">
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Open navigation"
          >
            <Menu className="size-5" aria-hidden />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="h-16 justify-center border-b px-5">
            <SheetTitle className="flex items-center gap-2 text-sm">
              <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <BrandMark className="size-4" />
              </span>
              ITARS
            </SheetTitle>
            <SheetDescription className="sr-only">
              Primary navigation
            </SheetDescription>
          </SheetHeader>
          <div className="py-4">
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="min-w-0">
        <h1 className="truncate text-[15px] font-semibold leading-tight tracking-tight">
          {meta.title}
        </h1>
        {meta.subtitle ? (
          <p className="hidden truncate text-xs text-muted-foreground sm:block">
            {meta.subtitle}
          </p>
        ) : null}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <ServicesStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
