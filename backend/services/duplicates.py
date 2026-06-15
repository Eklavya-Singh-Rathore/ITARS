from __future__ import annotations

import time
from pathlib import Path

import faiss
from huggingface_hub import hf_hub_download
import joblib
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from ..core.runtime_paths import (
    load_duplicate_threshold,
    load_model_config,
    resolve_model_dir,
    resolve_model_reference,
)


_ASSETS_REPO = "Eklavya73/ticket-duplicate-assets"


def _resolve_local_or_hub(
    local_candidates: list[Path],
    *,
    repo_id: str,
    filename: str,
) -> str:
    """Return the first existing local copy of an asset, else download from the Hub.

    Local-first avoids a hard dependency on the (private) duplicate-asset repo when
    the files are already bundled under hf_deploy/Models or hf_deploy/Data.
    """
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return hf_hub_download(repo_id=repo_id, filename=filename)


class CachedDuplicateDetectionEngine:
    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = (
            Path(base_dir).resolve()
            if base_dir is not None
            else Path(__file__).resolve().parent
        )
        self.model_dir = resolve_model_dir(self.base_dir)
        self.model_config = load_model_config(self.base_dir)
        self.duplicate_threshold = load_duplicate_threshold(self.base_dir)

        dataset_path = _resolve_local_or_hub(
            [
                self.base_dir / "Data" / "Domain-A_Dataset_Clean.csv",
                self.model_dir / "Domain-A_Dataset_Clean.csv",
                self.base_dir.parent / "Datasets" / "Processed" / "Domain-A_Dataset_Clean.csv",
            ],
            repo_id=_ASSETS_REPO,
            filename="Domain-A_Dataset_Clean.csv",
        )
        self.dataset = pd.read_csv(dataset_path)

        if "text" not in self.dataset.columns:
            raise ValueError("Duplicate dataset must contain a 'text' column.")

        self.db_texts = self.dataset["text"].astype(str).tolist()

        ticket_id_path = _resolve_local_or_hub(
            [self.model_dir / "ticket_ids.pkl"],
            repo_id=_ASSETS_REPO,
            filename="ticket_ids.pkl",
        )
        loaded_ids = joblib.load(ticket_id_path)
        self.db_ids = [str(ticket_id) for ticket_id in loaded_ids]

        if len(self.db_ids) != len(self.db_texts):
            if "ticket_id" in self.dataset.columns:
                self.db_ids = self.dataset["ticket_id"].astype(str).tolist()
            else:
                self.db_ids = [str(i) for i in range(len(self.db_texts))]

        embeddings_path = _resolve_local_or_hub(
            [self.model_dir / "db_embeddings.npy"],
            repo_id=_ASSETS_REPO,
            filename="db_embeddings.npy",
        )
        self.db_embeddings = np.load(embeddings_path).astype("float32")

        if self.db_embeddings.ndim != 2:
            raise ValueError(
                f"Expected 2D duplicate embedding matrix, got shape={self.db_embeddings.shape}"
            )

        if self.db_embeddings.shape[0] != len(self.db_texts):
            raise ValueError(
                "Embedding count does not match dataset rows: "
                f"{self.db_embeddings.shape[0]} embeddings vs {len(self.db_texts)} texts"
            )

        faiss.normalize_L2(self.db_embeddings)

        self.embedding_dim = int(self.db_embeddings.shape[1])
        self.faiss_meta = self._load_faiss_meta()
        self.index = self._build_index(self.db_embeddings)
        self.index.add(self.db_embeddings)
        self.initial_index_size = int(self.index.ntotal)
        self._encoder: SentenceTransformer | None = None

    def _load_faiss_meta(self) -> dict:
        meta_path = self.model_dir / "faiss_index_meta.pkl"
        if meta_path.exists():
            loaded = joblib.load(meta_path)
            if isinstance(loaded, dict):
                return loaded
        return {
            "dimension": self.embedding_dim,
            "index_type": "flat",
            "size": len(self.db_texts),
        }

    def _build_index(self, embeddings: np.ndarray):
        index_type = str(self.faiss_meta.get("index_type", "flat")).lower()
        nlist = max(1, int(self.faiss_meta.get("nlist", 256)))
        nprobe = max(1, int(self.faiss_meta.get("nprobe", 48)))

        if index_type == "ivf" and len(embeddings) >= max(64, nlist):
            quantizer = faiss.IndexFlatIP(self.embedding_dim)
            index = faiss.IndexIVFFlat(
                quantizer,
                self.embedding_dim,
                nlist,
                faiss.METRIC_INNER_PRODUCT,
            )
            index.train(embeddings)
            index.nprobe = min(nprobe, nlist)
            return index

        return faiss.IndexFlatIP(self.embedding_dim)

    @property
    def index_size(self) -> int:
        return int(self.index.ntotal)

    def _get_encoder(self) -> SentenceTransformer:
        if self._encoder is None:
            model_ref = resolve_model_reference(
                self.model_config.get(
                    "duplicate_sbert_model",
                    "Eklavya73/duplicate_sbert",
                ),
                base_dir=self.base_dir,
                model_dir=self.model_dir,
                default="all-mpnet-base-v2",
            )
            self._encoder = SentenceTransformer(model_ref)
        return self._encoder

    def _encode(
        self,
        texts,
        *,
        batch_size: int = 64,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        encoder = self._get_encoder()
        embeddings = encoder.encode(
            list(texts),
            batch_size=batch_size,
            show_progress_bar=show_progress_bar,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype="float32")

    def _normalize_query(self, embedding) -> np.ndarray:
        query = np.asarray(embedding, dtype="float32").reshape(1, -1).copy()
        faiss.normalize_L2(query)
        return query

    def _search(self, embedding, *, k: int = 20):
        if self.index_size == 0:
            return np.empty((1, 0), dtype="float32"), np.empty((1, 0), dtype=int)

        query = self._normalize_query(embedding)
        return self.index.search(query, min(max(1, int(k)), self.index_size))

    def find_best_match(
        self,
        embedding,
        *,
        k: int = 20,
        exclude_indices=None,
        include_baseline: bool = False,
    ) -> dict | None:
        if include_baseline:
            effective_k = k
        else:
            effective_k = min(int(k) + self.initial_index_size, self.index_size)
        scores, indices = self._search(embedding, k=effective_k)
        excluded = set(int(idx) for idx in (exclude_indices or []))

        for score, idx in zip(scores[0], indices[0]):
            idx = int(idx)
            if idx < 0 or idx in excluded:
                continue
            if not include_baseline and idx < self.initial_index_size:
                continue

            return {
                "index": idx,
                "ticket_id": self.db_ids[idx] if idx < len(self.db_ids) else None,
                "duplicate_of": self.db_ids[idx] if idx < len(self.db_ids) else None,
                "matched_text": self.db_texts[idx] if idx < len(self.db_texts) else None,
                "similarity": float(score),
            }

        return None

    def detect_duplicate(
        self,
        text: str | None = None,
        *,
        embedding=None,
        k: int = 20,
        exclude_indices=None,
        include_baseline: bool = False,
    ) -> dict | None:
        if embedding is None:
            if text is None:
                raise ValueError("Either text or embedding must be provided.")
            embedding = self._encode([str(text)])[0]

        match = self.find_best_match(
            embedding,
            k=k,
            exclude_indices=exclude_indices,
            include_baseline=include_baseline,
        )
        if match is None:
            return None
        if float(match["similarity"]) < float(self.duplicate_threshold):
            return None
        return match

    def add_ticket(
        self,
        ticket_id: str,
        text: str,
        *,
        embedding=None,
    ) -> None:
        if embedding is None:
            embedding = self._encode([str(text)])[0]

        query = self._normalize_query(embedding)
        self.index.add(query)
        self.db_ids.append(str(ticket_id))
        self.db_texts.append(str(text))
        self.db_embeddings = np.vstack([self.db_embeddings, query]).astype("float32")
        self.faiss_meta["size"] = int(self.index.ntotal)

    def benchmark_duplicate_detection(self, *, num_queries: int = 200, k: int = 5) -> dict:
        if self.index_size <= 1:
            return {
                "exact_latency_ms": 0.0,
                "faiss_latency_ms": 0.0,
                "speedup_vs_exact": 0.0,
                "recall_at_k": 0.0,
                "duplicate_precision": 0.0,
                "duplicate_recall": 0.0,
                "duplicate_f1": 0.0,
                "duplicate_eval_pairs": 0,
            }

        k = max(1, int(k))
        rng = np.random.default_rng(42)
        query_count = min(int(num_queries), self.index_size)
        sampled_indices = rng.choice(self.index_size, size=query_count, replace=False)

        exact_hits = 0
        tp = 0
        fp = 0
        fn = 0
        exact_latencies = []
        faiss_latencies = []

        for query_idx in sampled_indices:
            query_embedding = self.db_embeddings[query_idx]

            exact_start = time.perf_counter()
            similarities = self.db_embeddings @ query_embedding
            similarities[int(query_idx)] = -np.inf
            exact_top = np.argsort(-similarities)[:k]
            exact_score = float(similarities[int(exact_top[0])]) if exact_top.size else 0.0
            exact_is_duplicate = exact_score >= float(self.duplicate_threshold)
            exact_latencies.append((time.perf_counter() - exact_start) * 1000.0)

            faiss_start = time.perf_counter()
            distances, neighbors = self._search(query_embedding, k=k + 1)
            faiss_latencies.append((time.perf_counter() - faiss_start) * 1000.0)

            faiss_candidates = []
            faiss_best_score = 0.0
            for score, neighbor_idx in zip(distances[0], neighbors[0]):
                neighbor_idx = int(neighbor_idx)
                if neighbor_idx < 0 or neighbor_idx == int(query_idx):
                    continue
                faiss_candidates.append(neighbor_idx)
                if len(faiss_candidates) == 1:
                    faiss_best_score = float(score)
                if len(faiss_candidates) >= k:
                    break

            if exact_top.size and int(exact_top[0]) in set(faiss_candidates):
                exact_hits += 1

            pred_is_duplicate = bool(faiss_candidates) and faiss_best_score >= float(self.duplicate_threshold)
            if pred_is_duplicate and exact_is_duplicate:
                tp += 1
            elif pred_is_duplicate and not exact_is_duplicate:
                fp += 1
            elif exact_is_duplicate and not pred_is_duplicate:
                fn += 1

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 0.0 if (precision + recall) == 0.0 else (2.0 * precision * recall) / (precision + recall)

        exact_latency_ms = float(np.mean(exact_latencies)) if exact_latencies else 0.0
        faiss_latency_ms = float(np.mean(faiss_latencies)) if faiss_latencies else 0.0

        return {
            "exact_latency_ms": exact_latency_ms,
            "faiss_latency_ms": faiss_latency_ms,
            "speedup_vs_exact": (
                float(exact_latency_ms / faiss_latency_ms)
                if faiss_latency_ms > 0.0
                else 0.0
            ),
            "recall_at_k": float(exact_hits / max(query_count, 1)),
            "duplicate_precision": float(precision),
            "duplicate_recall": float(recall),
            "duplicate_f1": float(f1),
            "duplicate_eval_pairs": int(query_count),
        }

    def get_duplicate_metrics(self) -> dict:
        return {
            "duplicate_threshold": float(self.duplicate_threshold),
            "faiss_meta": {
                "dimension": int(self.embedding_dim),
                "index_type": str(self.faiss_meta.get("index_type", "flat")),
                "nlist": int(self.faiss_meta.get("nlist", 0)),
                "nprobe": int(self.faiss_meta.get("nprobe", 0)),
                "size": int(self.index_size),
            },
        }