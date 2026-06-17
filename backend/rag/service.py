"""RagService — ingest + retrieve over Qdrant with citations and a score floor.

Retrieval-only (Phase 7): powers the similar-tickets panel and is the substrate
for later grounded generation. Every result carries its source ticket id
(citation) and cosine score; results below the configured floor are dropped, so
a weak match surfaces as "no similar ticket found" rather than a misleading one.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..core.config import SETTINGS, Settings
from .embeddings import RagEmbedder
from .schema import (
    ALL_COLLECTIONS,
    HISTORICAL_TICKETS,
    P_DATE,
    P_DEPARTMENT,
    P_LANGUAGE,
    P_PRIORITY,
    P_TAGS,
    P_TEXT,
    P_TICKET_ID,
)
from .store import QdrantStore, host_for_logging


def _payload(record: dict) -> dict:
    return {
        P_TICKET_ID: record["ticket_id"],
        P_TEXT: record["text"],  # ORIGINAL text
        P_DEPARTMENT: record.get("department"),
        P_PRIORITY: record.get("priority"),
        P_TAGS: record.get("tags"),
        P_LANGUAGE: record.get("language"),
        P_DATE: record.get("date"),
    }


class RagService:
    def __init__(
        self,
        settings: Settings = SETTINGS,
        *,
        embedder: RagEmbedder | None = None,
        store: QdrantStore | None = None,
    ):
        self.settings = settings
        self.embedder = embedder if embedder is not None else RagEmbedder(settings)
        self.store = store if store is not None else QdrantStore(settings)

    # ------------------------------------------------------------- ingest
    def ingest(self, records: Sequence[dict], *, collection: str = HISTORICAL_TICKETS) -> int:
        """Records: {ticket_id, text, [department, priority, tags, language, date]}."""
        records = [r for r in records if str(r.get("text", "")).strip()]
        if not records:
            return 0
        vectors = self.embedder.embed_passages([r["text"] for r in records])
        items = [
            {"id": r["ticket_id"], "vector": vectors[i], "payload": _payload(r)}
            for i, r in enumerate(records)
        ]
        return self.store.upsert(collection, items)

    # ------------------------------------------------------------- search
    def search(
        self,
        query: str,
        *,
        collection: str = HISTORICAL_TICKETS,
        top_k: int | None = None,
        filters: dict | None = None,
        score_floor: float | None = None,
    ) -> list[dict[str, Any]]:
        vector = self.embedder.embed_query(query)
        floor = self.settings.rag_score_floor if score_floor is None else score_floor
        rows = self.store.search(
            collection,
            vector,
            top_k=top_k or self.settings.rag_top_k,
            score_floor=floor,
            filters=filters,
        )
        return [self._result(row) for row in rows]

    def similar_tickets(
        self,
        text: str,
        *,
        exclude_ticket_id: str | None = None,
        collection: str = HISTORICAL_TICKETS,
        top_k: int | None = None,
        filters: dict | None = None,
        score_floor: float | None = None,
    ) -> list[dict[str, Any]]:
        # Fetch one extra so excluding self still returns top_k.
        wanted = top_k or self.settings.rag_top_k
        results = self.search(
            text,
            collection=collection,
            top_k=wanted + 1,
            filters=filters,
            score_floor=score_floor,
        )
        if exclude_ticket_id:
            results = [r for r in results if r["ticket_id"] != exclude_ticket_id]
        return results[:wanted]

    @staticmethod
    def _result(row: dict) -> dict[str, Any]:
        payload = row.get("payload", {})
        return {
            "ticket_id": payload.get(P_TICKET_ID),
            "text": payload.get(P_TEXT),
            "department": payload.get(P_DEPARTMENT),
            "priority": payload.get(P_PRIORITY),
            "tags": payload.get(P_TAGS),
            "language": payload.get(P_LANGUAGE),
            "score": round(float(row.get("score", 0.0)), 4),
        }

    # ------------------------------------------------------------- health
    def health(self) -> dict[str, Any]:
        counts = {name: self.store.count(name) for name in ALL_COLLECTIONS}
        return {
            "embedding_model": self.settings.rag_embedding_model,
            "embedding_dim": self.settings.rag_embedding_dim,
            "score_floor": self.settings.rag_score_floor,
            "store": host_for_logging(self.settings.qdrant_url),
            "collections": counts,
        }
