"""Qdrant vector store wrapper (Phase 7 / 15B).

Supports in-memory (`:memory:`, default — zero-setup and used in tests), a remote
server URL (Qdrant Cloud or self-hosted), or a local persistent path. Cosine
distance over L2-normalized vectors. Ticket ids (hex strings) are mapped to
deterministic UUID point ids; the real ticket id lives in the payload.

Phase 15B adds:
  * URL normalization — Qdrant Cloud often dispenses bare `xyz.cloud.qdrant.io`
    hostnames; we add `https://` automatically for any non-local host so the
    HTTP client doesn't try gRPC by accident.
  * `host_for_logging()` — never includes credentials, safe for `/rag/health`
    payloads or stdout.
  * `init_collections()` — pre-creates the 5 known collections on first boot
    so cold-start diagnostics are clearer.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence
from urllib.parse import urlsplit

from ..core.config import SETTINGS, Settings
from .schema import ALL_COLLECTIONS


def point_id(ticket_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"itars:{ticket_id}"))


# Hostnames we treat as local (allowed to fall back to http://).
_LOCAL_HOST_PREFIXES = ("localhost", "127.", "0.0.0.0", "::1")


def normalize_qdrant_url(url: str) -> str:
    """Coerce raw Qdrant URLs into something the HTTP client can consume.

    Cases handled:
      * `:memory:` and local file paths — returned unchanged.
      * Bare host (e.g. `xyz-eastus.cloud.qdrant.io:6333`) → `https://...`.
      * Bare host without port → `https://...:6333`.
      * Localhost-style hosts default to `http://` (since Qdrant Cloud uses
        HTTPS but a local dev container usually does not).
    """
    if not url or url == ":memory:" or url.startswith(":"):
        return url
    # Already a URL — leave it alone (preserve port and path).
    if url.startswith(("http://", "https://")):
        return url
    # Local file paths (RocksDB embedded mode) — start with `.` or `/` or a
    # drive letter, and have no `:port` pattern matching a TCP port.
    if url.startswith(("./", "../", "/")) or (len(url) > 2 and url[1] == ":" and url[2] in "/\\"):
        return url
    # At this point we have a bare host (optionally with :port).
    host = url
    if ":" not in host:
        host = f"{host}:6333"
    is_local = any(host.startswith(p) for p in _LOCAL_HOST_PREFIXES)
    scheme = "http" if is_local else "https"
    return f"{scheme}://{host}"


def host_for_logging(url: str) -> str:
    """Credential-safe host string for `/rag/health` and stdout."""
    if not url or url.startswith(":"):
        return url
    if "://" not in url:
        url = normalize_qdrant_url(url)
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    if parts.scheme not in ("http", "https"):
        return url  # local path — no creds to redact
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    return f"{parts.scheme}://{parts.hostname or ''}{port}"


class QdrantStore:
    def __init__(self, settings: Settings = SETTINGS):
        from qdrant_client import QdrantClient

        self.settings = settings
        self.dim = int(settings.rag_embedding_dim)
        url = settings.qdrant_url
        if url == ":memory:":
            self.client = QdrantClient(":memory:")
        else:
            normalized = normalize_qdrant_url(url)
            if normalized.startswith(("http://", "https://")):
                self.client = QdrantClient(
                    url=normalized, api_key=settings.qdrant_api_key
                )
            else:
                self.client = QdrantClient(path=normalized)

    def ensure_collection(self, name: str) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )

    def init_collections(self) -> None:
        """Idempotently create every known ITARS collection.

        Useful at app boot when pointing at a fresh Qdrant Cloud instance: the
        `/rag/health` response then shows the 5 collections explicitly (empty
        but present), instead of nothing.
        """
        for name in ALL_COLLECTIONS:
            self.ensure_collection(name)

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
