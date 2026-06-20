"""Ingest historical tickets into the RAG vector store (Phase 7 / 15B).

Sources:
  * the decision log (`tickets` + latest `routing_results`) — every ticket
    ITARS has already routed; and/or
  * the Domain-A dataset CSV (`text` column, optional `queue`/`priority`/`tags`).

Embeds with BGE-small and upserts into the `historical_tickets` collection
(idempotent). The target store follows config: Supabase pgvector when
`ITARS_DATABASE_URL` is Postgres, else the in-memory fallback. Run from `main/`:

    python -m scripts.ingest_rag                 # from the decision-log DB
    python -m scripts.ingest_rag --dataset ../hf_deploy/Data/Domain-A_Dataset_Clean.csv --limit 5000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

MAIN_DIR = Path(__file__).resolve().parents[1]
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))

from backend.core.config import SETTINGS  # noqa: E402
from backend.rag.schema import HISTORICAL_TICKETS  # noqa: E402
from backend.rag.service import RagService  # noqa: E402


def _records_from_db() -> list[dict]:
    from sqlalchemy import select

    from backend.repositories.database import make_engine, make_session_factory
    from backend.repositories.models import RoutingResult, Ticket

    engine = make_engine(SETTINGS.database_url)
    factory = make_session_factory(engine)
    records: list[dict] = []
    with factory() as session:
        tickets = session.execute(select(Ticket)).scalars().all()
        for ticket in tickets:
            routing = session.execute(
                select(RoutingResult)
                .where(RoutingResult.ticket_id == ticket.ticket_id)
                .order_by(RoutingResult.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            records.append(
                {
                    "ticket_id": ticket.ticket_id,
                    "text": ticket.original_text,
                    "department": routing.department if routing else None,
                    "priority": routing.priority if routing else None,
                    "tags": routing.tags if routing else None,
                    "language": ticket.detected_language,
                    "date": ticket.created_at.isoformat() if ticket.created_at else None,
                }
            )
    return records


def _records_from_dataset(path: Path, limit: int | None) -> list[dict]:
    import pandas as pd

    frame = pd.read_csv(path)
    if "text" not in frame.columns:
        raise SystemExit(f"{path} has no 'text' column.")
    if limit:
        frame = frame.head(int(limit))
    records = []
    for i, row in frame.iterrows():
        records.append(
            {
                "ticket_id": str(row.get("ticket_id", f"ds-{i}")),
                "text": str(row["text"]),
                "department": row.get("queue") if "queue" in frame.columns else None,
                "priority": row.get("priority") if "priority" in frame.columns else None,
                "tags": str(row.get("tags")) if "tags" in frame.columns else None,
                "language": "en",
                "date": None,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest tickets into the RAG vector store.")
    parser.add_argument("--dataset", default=None, help="CSV to ingest instead of the DB.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch", type=int, default=512)
    args = parser.parse_args()

    if args.dataset:
        records = _records_from_dataset(Path(args.dataset), args.limit)
        print(f"Loaded {len(records)} records from {args.dataset}")
    else:
        records = _records_from_db()
        print(f"Loaded {len(records)} records from the decision log ({SETTINGS.database_url})")

    if not records:
        print("Nothing to ingest.")
        return 0

    service = RagService()
    total = 0
    for start in range(0, len(records), args.batch):
        batch = records[start : start + args.batch]
        total += service.ingest(batch, collection=HISTORICAL_TICKETS)
        print(f"  ingested {total}/{len(records)}")

    health = service.health()
    print(f"\nDone. {HISTORICAL_TICKETS}: {health['collections'][HISTORICAL_TICKETS]} points")
    print(f"Vector store: {health['vector_store_mode']} · model: {SETTINGS.rag_embedding_model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
