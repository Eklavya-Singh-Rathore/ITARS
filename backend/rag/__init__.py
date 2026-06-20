"""RAG layer (Phase 7 / 15B) — BGE-small + Supabase pgvector, retrieval-only.

Deliberately separate from the routing stack: routing keeps all-mpnet + FAISS;
this module only powers similar-ticket retrieval and grounded generation. Vectors
are stored in pgvector (same Supabase Postgres as the relational data).
"""
