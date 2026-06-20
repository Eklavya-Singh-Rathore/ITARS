"""Vector store backends (Phase 15B — Supabase pgvector).

Two interchangeable stores behind one duck-typed interface
(`upsert` / `search` / `count` / `init_collections` / `mode`):

  * ``PgVectorStore`` — production. Stores 384-dim embeddings in the *same*
    Supabase Postgres as the relational data, one table per logical collection,
    cosine similarity via pgvector's ``<=>`` operator over an HNSW index. Vectors
    are durable, so retrieval survives an HF Space / container restart.

  * ``InMemoryVectorStore`` — dev/test fallback (pure Python, brute-force
    cosine). Used automatically when the database is SQLite, so the suite runs
    with no Postgres and no network. *Not* used in production.

Ticket ids map to deterministic UUID5 point ids so re-ingesting the same ticket
upserts in place (parity with the previous Qdrant behaviour).
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from ..core.config import SETTINGS, Settings
from .schema import (
    ALL_COLLECTIONS,
    P_DATE,
    P_DEPARTMENT,
    P_LANGUAGE,
    P_PRIORITY,
    P_TAGS,
    P_TEXT,
    P_TICKET_ID,
)


def point_id(ticket_id: str) -> str:
    """Deterministic point id for a ticket (stable across re-ingestion)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"itars:{ticket_id}"))


# Columns the search filter is allowed to constrain (whitelist → no injection).
_FILTERABLE = (P_DEPARTMENT, P_PRIORITY, P_LANGUAGE, P_TAGS, P_TICKET_ID)
# Payload columns selected back from a row, in order.
_PAYLOAD_COLUMNS = (
    P_TICKET_ID,
    P_TEXT,
    P_DEPARTMENT,
    P_PRIORITY,
    P_TAGS,
    P_LANGUAGE,
    P_DATE,
)


def _cosine(a, b) -> float:
    """Cosine similarity in [-1, 1] (works on plain Python/NumPy sequences)."""
    import numpy as np

    av = np.asarray(a, dtype="float32")
    bv = np.asarray(b, dtype="float32")
    na = float(np.linalg.norm(av)) or 1.0
    nb = float(np.linalg.norm(bv)) or 1.0
    return float(np.dot(av, bv) / (na * nb))


# ---------------------------------------------------------------------------
# In-memory store (dev / tests)
# ---------------------------------------------------------------------------
class InMemoryVectorStore:
    """Brute-force cosine store kept entirely in process memory.

    Semantics match pgvector/Qdrant cosine: same ranking, same score floor,
    same metadata filtering. Ephemeral by design — production uses pgvector.
    """

    mode = "memory"

    def __init__(self, settings: Settings = SETTINGS):
        self.settings = settings
        self.dim = int(settings.rag_embedding_dim)
        self._data: dict[str, dict[str, dict[str, Any]]] = {}

    def init_collections(self) -> None:
        for name in ALL_COLLECTIONS:
            self._data.setdefault(name, {})

    def upsert(self, collection: str, items: Sequence[dict]) -> int:
        bucket = self._data.setdefault(collection, {})
        for item in items:
            bucket[point_id(item["id"])] = {
                "vector": list(item["vector"]),
                "payload": item["payload"],
            }
        return len(items)

    def search(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int,
        score_floor: float = 0.0,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        bucket = self._data.get(collection)
        if not bucket:
            return []
        active = {k: v for k, v in (filters or {}).items() if v is not None}
        rows: list[dict[str, Any]] = []
        for entry in bucket.values():
            payload = entry["payload"]
            if any(payload.get(k) != v for k, v in active.items()):
                continue
            score = _cosine(vector, entry["vector"])
            if score_floor and score < score_floor:
                continue
            rows.append({"score": score, "payload": payload})
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows[: int(top_k)]

    def count(self, collection: str) -> int:
        return len(self._data.get(collection, {}))


# ---------------------------------------------------------------------------
# pgvector store (production)
# ---------------------------------------------------------------------------
# Collection name == table name. The dict is a strict whitelist: only these
# names are ever interpolated into SQL (their values are constants, never user
# input), so dynamic table names cannot be an injection vector.
_TABLE_FOR = {name: name for name in ALL_COLLECTIONS}


def _vector_literal(vector: Sequence[float]) -> str:
    """pgvector text representation: '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class PgVectorStore:
    """Durable vector store over Supabase Postgres + pgvector.

    Uses the same database URL as the relational layer (`ITARS_DATABASE_URL`) —
    one Supabase project is both the relational and the vector database. The
    engine is created lazily; no connection is opened until the first query, so
    construction can't block app startup.
    """

    mode = "pgvector"

    def __init__(self, settings: Settings = SETTINGS, *, engine=None):
        from ..repositories.database import make_engine

        self.settings = settings
        self.dim = int(settings.rag_embedding_dim)
        self._engine = engine if engine is not None else make_engine(settings.database_url)

    def _table(self, collection: str) -> str:
        table = _TABLE_FOR.get(collection)
        if table is None:
            raise ValueError(f"Unknown RAG collection: {collection!r}")
        return table

    def init_collections(self) -> None:
        """Idempotently ensure the extension + 5 collection tables exist.

        Authoritative provisioning is the tracked Supabase migration
        (`phase15b_pgvector_rag_schema`); this is a self-heal for fresh deploys
        and exactly mirrors that DDL.
        """
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            for table in _TABLE_FOR.values():
                conn.execute(
                    text(
                        f"CREATE TABLE IF NOT EXISTS {table} ("
                        "point_id text PRIMARY KEY, ticket_id text, text text, "
                        "department text, priority text, tags text, language text, "
                        "date text, embedding vector(:dim), "
                        "created_at timestamptz NOT NULL DEFAULT now())".replace(
                            ":dim", str(self.dim)
                        )
                    )
                )
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding "
                        f"ON {table} USING hnsw (embedding vector_cosine_ops)"
                    )
                )

    def upsert(self, collection: str, items: Sequence[dict]) -> int:
        from sqlalchemy import text

        table = self._table(collection)
        stmt = text(
            f"INSERT INTO {table} "
            "(point_id, ticket_id, text, department, priority, tags, language, date, embedding) "
            "VALUES (:pid, :ticket_id, :text, :department, :priority, :tags, :language, :date, "
            "CAST(:embedding AS vector)) "
            "ON CONFLICT (point_id) DO UPDATE SET "
            "ticket_id=EXCLUDED.ticket_id, text=EXCLUDED.text, department=EXCLUDED.department, "
            "priority=EXCLUDED.priority, tags=EXCLUDED.tags, language=EXCLUDED.language, "
            "date=EXCLUDED.date, embedding=EXCLUDED.embedding"
        )
        count = 0
        with self._engine.begin() as conn:
            for item in items:
                payload = item["payload"]
                conn.execute(
                    stmt,
                    {
                        "pid": point_id(item["id"]),
                        "ticket_id": payload.get(P_TICKET_ID),
                        "text": payload.get(P_TEXT),
                        "department": payload.get(P_DEPARTMENT),
                        "priority": payload.get(P_PRIORITY),
                        "tags": payload.get(P_TAGS),
                        "language": payload.get(P_LANGUAGE),
                        "date": payload.get(P_DATE),
                        "embedding": _vector_literal(item["vector"]),
                    },
                )
                count += 1
        return count

    def search(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int,
        score_floor: float = 0.0,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import text

        table = self._table(collection)
        params: dict[str, Any] = {"embedding": _vector_literal(vector), "k": int(top_k)}
        clauses: list[str] = []
        for i, (key, value) in enumerate((filters or {}).items()):
            if value is None or key not in _FILTERABLE:
                continue
            clauses.append(f"{key} = :f{i}")
            params[f"f{i}"] = value
        if score_floor:
            # cosine_distance <= 1 - floor  ⟺  similarity >= floor
            clauses.append("(embedding <=> CAST(:embedding AS vector)) <= :max_dist")
            params["max_dist"] = 1.0 - float(score_floor)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        cols = ", ".join(_PAYLOAD_COLUMNS)
        stmt = text(
            f"SELECT {cols}, 1 - (embedding <=> CAST(:embedding AS vector)) AS score "
            f"FROM {table} {where} "
            "ORDER BY embedding <=> CAST(:embedding AS vector) "
            "LIMIT :k"
        )
        with self._engine.connect() as conn:
            result = conn.execute(stmt, params)
            rows = result.mappings().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = {col: row[col] for col in _PAYLOAD_COLUMNS}
            out.append({"score": float(row["score"]), "payload": payload})
        return out

    def count(self, collection: str) -> int:
        from sqlalchemy import text

        table = self._table(collection)
        try:
            with self._engine.connect() as conn:
                return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
        except Exception:
            # Table not yet created (fresh project before init_collections).
            return 0
