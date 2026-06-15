"""RAG layer (Phase 7) — BGE-small + Qdrant, retrieval-only.

Deliberately separate from the routing stack: routing keeps all-mpnet + FAISS;
this module only powers similar-ticket retrieval and (later) grounded generation.
"""
