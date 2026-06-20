"use client";

import { useRouter } from "next/navigation";
import { Copy, ExternalLink, Eye, Inbox, MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Actions available from any ticket reference. Open / View details / Go to
 * All Tickets all deep-link to the All Tickets page, which scrolls to and
 * highlights (and expands) the ticket. */
export function ticketDeepLink(ticketId: string): string {
  return `/all-tickets?highlight=${encodeURIComponent(ticketId)}`;
}

export function TicketRefMenu({ ticketId }: { ticketId: string }) {
  const router = useRouter();
  const go = () => router.push(ticketDeepLink(ticketId));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Ticket actions"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="size-4" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
        <DropdownMenuItem onClick={go} className="gap-2">
          <Eye className="size-4" aria-hidden /> Open ticket
        </DropdownMenuItem>
        <DropdownMenuItem onClick={go} className="gap-2">
          <ExternalLink className="size-4" aria-hidden /> View details
        </DropdownMenuItem>
        <DropdownMenuItem onClick={go} className="gap-2">
          <Inbox className="size-4" aria-hidden /> Go to All Tickets
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => {
            navigator.clipboard?.writeText(ticketId);
            toast.success("Ticket ID copied");
          }}
          className="gap-2"
        >
          <Copy className="size-4" aria-hidden /> Copy ID
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
