"""Qdrant vector store wrapper (Phase 7).

Supports in-memory (`:memory:`, default — zero-setup and used in tests), a remote
server URL, or a local persistent path. Cosine distance over L2-normalized
vectors. Ticket ids (hex strings) are mapped to deterministic UUID point ids;
the real ticket id lives in the payload.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from ..core.config import SETTINGS, Settings


def point_id(ticket_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"itars:{ticket_id}"))


class QdrantStore:
    def __init__(self, settings: Settings = SETTINGS):
        from qdrant_client import QdrantClient

        self.settings = settings
        self.dim = int(settings.rag_embedding_dim)
        url = settings.qdrant_url
        if url == ":memory:":
            self.client = QdrantClient(":memory:")
        elif url.startswith(("http://", "https://")):
            self.client = QdrantClient(url=url, api_key=settings.qdrant_api_key)
        else:
            self.client = QdrantClient(path=url)

    def ensure_collection(self, name: str) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )

    def upsert(self, collection: str, items: Sequence[dict]) -> int:
        from qdrant_client.models import PointStruct

        self.ensure_collection(collection)
        points = [
            PointStruct(
                id=point_id(item["id"]),
                vector=[float(x) for x in item["vector"]],
                payload=item["payload"],
            )
            for item in items
        ]
        if points:
            self.client.upsert(collection_name=collection, points=points)
        return len(points)

    def _build_filter(self, filters: dict | None):
        if not filters:
            return None
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
                if value is not None
            ]
        )

    def search(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int,
        score_floor: float = 0.0,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        if not self.client.collection_exists(collection):
            return []
        response = self.client.query_points(
            collection_name=collection,
            query=[float(x) for x in vector],
            limit=int(top_k),
            query_filter=self._build_filter(filters),
            score_threshold=float(score_floor) if score_floor else None,
            with_payload=True,
        )
        return [
            {"score": float(p.score), "payload": p.payload or {}}
            for p in response.points
        ]

    def count(self, collection: str) -> int:
        if not self.client.collection_exists(collection):
            return 0
        return int(self.client.count(collection_name=collection).count)
