"""RAG embedder — BGE-small-en-v1.5 (Phase 7).

Lazy-loads the sentence-transformers model on first use (heavy + network), so
this module imports cheaply. A `RagEmbedder` can also be constructed with an
injected `embed_fn` for tests — deterministic fake vectors, no model download.

BGE retrieval convention: queries are prefixed with the BGE instruction; passages
are embedded as-is. Vectors are L2-normalized so dot-product == cosine.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from ..core.config import SETTINGS, Settings

# BGE-small query instruction (improves retrieval per the model card).
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _normalize(vectors: np.ndarray) -> np.ndarray:
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return arr / norms


class RagEmbedder:
    def __init__(
        self,
        settings: Settings = SETTINGS,
        *,
        embed_fn: Callable[[Sequence[str]], np.ndarray] | None = None,
    ):
        self.settings = settings
        self._embed_fn = embed_fn
        self._model = None

    @property
    def dim(self) -> int:
        return int(self.settings.rag_embedding_dim)

    def _model_encode(self, texts: Sequence[str]) -> np.ndarray:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.settings.rag_embedding_model)
        return np.asarray(
            self._model.encode(list(texts), normalize_embeddings=False),
            dtype="float32",
        )

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        raw = (
            self._embed_fn(list(texts))
            if self._embed_fn is not None
            else self._model_encode(texts)
        )
        return _normalize(raw)

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        return self._encode(list(texts))

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode([BGE_QUERY_PREFIX + str(text)])[0]
