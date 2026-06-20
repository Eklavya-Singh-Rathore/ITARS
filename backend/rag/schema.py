"""RAG collection names and payload conventions (Phase 7 / 15B).

Collections mirror the Feature Report's RAG knowledge sources. In production each
collection is a pgvector table of the same name in Supabase Postgres; each row
always carries the ORIGINAL text (never preprocessed/lemmatized) plus filterable
metadata.
"""

from __future__ import annotations

# Collection names == pgvector table names (Feature Report §RAG knowledge sources).
HISTORICAL_TICKETS = "historical_tickets"
DUPLICATE_CLUSTERS = "duplicate_clusters"
ROUTING_HISTORY = "routing_history"
FEEDBACK_RECORDS = "feedback_records"
ROUTING_POLICIES = "routing_policies"

ALL_COLLECTIONS = (
    HISTORICAL_TICKETS,
    DUPLICATE_CLUSTERS,
    ROUTING_HISTORY,
    FEEDBACK_RECORDS,
    ROUTING_POLICIES,
)

# Payload keys.
P_TICKET_ID = "ticket_id"
P_TEXT = "text"  # ORIGINAL text, shown to users
P_DEPARTMENT = "department"
P_PRIORITY = "priority"
P_TAGS = "tags"
P_LANGUAGE = "language"
P_DATE = "date"
