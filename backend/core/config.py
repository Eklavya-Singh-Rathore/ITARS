"""Single configuration source for the ITARS serving system.

Every constant that was previously hardcoded across `app.py` / `runtime_utils.py`
lives here exactly once. Values may be overridden via environment variables so no
filesystem path or tuning constant is baked into the code (audit defects: three
divergent duplicate thresholds, hardcoded `E:\\`/`D:\\` roots, scattered weights).

Resolution order for paths:
  1. explicit environment variable
  2. `main/Models` or `main/Datasets` if present (self-contained deployment)
  3. the existing `hf_deploy/` bundle (so 560 MB of artifacts are referenced,
     not duplicated into `main/`)
  4. repo-root `Models` / `Datasets`
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# core/ -> backend/ -> main/ -> <repo root>
_CORE_DIR = Path(__file__).resolve().parent
MAIN_DIR = _CORE_DIR.parents[1]
REPO_ROOT = _CORE_DIR.parents[2]


def _first_existing(candidates: list[Path], *, default: Path) -> Path:
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return default


def _resolve_model_dir() -> Path:
    env = os.environ.get("ITARS_MODEL_DIR")
    if env:
        return Path(env).resolve()
    return _first_existing(
        [
            MAIN_DIR / "Models",
            REPO_ROOT / "hf_deploy" / "Models",
            REPO_ROOT / "Models",
        ],
        default=MAIN_DIR / "Models",
    )


def _resolve_data_dir() -> Path:
    env = os.environ.get("ITARS_DATA_DIR")
    if env:
        return Path(env).resolve()
    return _first_existing(
        [
            MAIN_DIR / "Datasets",
            REPO_ROOT / "hf_deploy" / "Data",
            REPO_ROOT / "Datasets" / "Processed",
            REPO_ROOT / "Datasets",
        ],
        default=MAIN_DIR / "Datasets",
    )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else int(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Paths (no hardcoded absolute paths) ---
    model_dir: Path = field(default_factory=_resolve_model_dir)
    data_dir: Path = field(default_factory=_resolve_data_dir)
    routing_config_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "ITARS_ROUTING_CONFIG",
                str(MAIN_DIR / "config" / "routing_config.yaml"),
            )
        )
    )

    # --- Database (Phase 6): SQLite now, Postgres later ---
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "ITARS_DATABASE_URL", f"sqlite:///{(MAIN_DIR / 'itars.db').as_posix()}"
        )
    )

    # --- Deployment / security (Phase 14) ---
    # Comma-separated allowed CORS origins ("*" = allow all; the dev default).
    # In production set e.g. "https://itars.vercel.app".
    cors_allow_origins: str = field(
        default_factory=lambda: os.environ.get("ITARS_CORS_ORIGINS", "*")
    )
    # Optional shared API token. When set, every non-public endpoint requires it
    # (sent as `X-API-Key` or `Authorization: Bearer`). Unset = open (dev).
    api_token: str | None = field(
        default_factory=lambda: os.environ.get("ITARS_API_TOKEN") or None
    )

    # --- RAG (Phase 7 / 15B): BGE-small + Supabase pgvector, retrieval-only ---
    rag_enabled: bool = field(
        default_factory=lambda: _env_bool("ITARS_RAG_ENABLED", True)
    )
    # Vector store backend: "auto" (default) uses pgvector when the database is
    # Postgres (Supabase), else an in-memory fallback for SQLite dev/tests.
    # Force with "pgvector" or "memory".
    vector_store_mode: str = field(
        default_factory=lambda: os.environ.get("ITARS_VECTOR_STORE", "auto")
    )
    rag_embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "ITARS_RAG_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
        )
    )
    rag_embedding_dim: int = field(
        default_factory=lambda: _env_int("ITARS_RAG_EMBEDDING_DIM", 384)
    )
    rag_top_k: int = field(default_factory=lambda: _env_int("ITARS_RAG_TOP_K", 5))
    # Retrieval-confidence floor — below this cosine score, say "no similar found"
    # rather than surfacing a weak match (audit guardrail).
    rag_score_floor: float = field(
        default_factory=lambda: _env_float("ITARS_RAG_SCORE_FLOOR", 0.5)
    )

    # --- Embedding model references (resolved as HF Hub repo ids or local dirs) ---
    routing_sbert: str = field(
        default_factory=lambda: os.environ.get(
            "ITARS_ROUTING_SBERT", "Eklavya73/sbert_finetuned"
        )
    )
    duplicate_sbert: str = field(
        default_factory=lambda: os.environ.get(
            "ITARS_DUPLICATE_SBERT", "Eklavya73/duplicate_sbert"
        )
    )
    sbert_fallback: str = "all-mpnet-base-v2"

    # --- Hybrid routing weights (app.py HYBRID_*_WEIGHT) ---
    hybrid_classifier_weight: float = field(
        default_factory=lambda: _env_float("ITARS_HYBRID_CLASSIFIER_WEIGHT", 0.7)
    )
    hybrid_similarity_weight: float = field(
        default_factory=lambda: _env_float("ITARS_HYBRID_SIMILARITY_WEIGHT", 0.3)
    )

    # --- Two-stage gate thresholds (app.py constants) ---
    # Defaults recalibrated from the held-out hybrid-confidence distribution
    # (n=1500, mean=0.963, std=0.009, min=0.878). The old 0.45 / 0.30 floors
    # were below the observed minimum, so the gate never fired (audit defect
    # K2). 0.94 = 1st percentile; 0.95 = 5th percentile. See
    # scripts/recalibrate_gate.py; override via the env vars if you re-fit.
    hybrid_floor: float = field(
        default_factory=lambda: _env_float("ITARS_HYBRID_FLOOR", 0.94)
    )
    flagged_hybrid_floor: float = field(
        default_factory=lambda: _env_float("ITARS_FLAGGED_HYBRID_FLOOR", 0.95)
    )
    margin_threshold: float = field(
        default_factory=lambda: _env_float("ITARS_MARGIN_THRESHOLD", 0.15)
    )
    entropy_threshold: float = field(
        default_factory=lambda: _env_float("ITARS_ENTROPY_THRESHOLD", 1.8)
    )

    # --- Tag / duplicate retrieval ---
    top_tags_k: int = field(default_factory=lambda: _env_int("ITARS_TOP_TAGS_K", 5))
    duplicate_top_k: int = field(
        default_factory=lambda: _env_int("ITARS_DUPLICATE_TOP_K", 20)
    )

    # --- Controlled-review demo cap (app.py DEMO_REVIEW_THRESHOLD_CAP) ---
    # Preserved for behavioral parity with the deployed Space. Disable to use the
    # raw fitted review-policy thresholds instead.
    apply_demo_review_cap: bool = field(
        default_factory=lambda: _env_bool("ITARS_APPLY_DEMO_REVIEW_CAP", True)
    )
    demo_review_threshold_cap: float = field(
        default_factory=lambda: _env_float("ITARS_DEMO_REVIEW_THRESHOLD_CAP", 0.30)
    )

    # --- Translation (Phase 3) ---
    translation_enabled: bool = field(
        default_factory=lambda: _env_bool("ITARS_TRANSLATION_ENABLED", True)
    )
    translation_model_de: str = field(
        default_factory=lambda: os.environ.get(
            "ITARS_TRANSLATION_MODEL_DE", "Helsinki-NLP/opus-mt-de-en"
        )
    )
    translation_model_romance: str = field(
        default_factory=lambda: os.environ.get(
            "ITARS_TRANSLATION_MODEL_ROMANCE", "Helsinki-NLP/opus-mt-ROMANCE-en"
        )
    )
    translation_romance_langs: tuple[str, ...] = ("es", "fr", "pt")
    translation_max_words: int = field(
        default_factory=lambda: _env_int("ITARS_TRANSLATION_MAX_WORDS", 400)
    )
    translation_max_length: int = field(
        default_factory=lambda: _env_int("ITARS_TRANSLATION_MAX_LENGTH", 512)
    )
    translation_cache_size: int = field(
        default_factory=lambda: _env_int("ITARS_TRANSLATION_CACHE_SIZE", 1024)
    )

    # --- LLM gateway (Phase 8): provider-agnostic; Gemini/Grok, Echo offline ---
    # Dev default is Grok (avoids Gemini free-tier limits during iteration);
    # switch to "gemini" before deployment — a config change only (Phase 9 plan).
    llm_provider: str = field(
        default_factory=lambda: os.environ.get("ITARS_LLM_PROVIDER", "grok")
    )
    # Comma-separated fallback order tried if the primary fails (e.g. "gemini,echo").
    llm_fallback: str = field(
        default_factory=lambda: os.environ.get("ITARS_LLM_FALLBACK", "echo")
    )
    gemini_api_key: str | None = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY") or None
    )
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("ITARS_GEMINI_MODEL", "gemini-2.5-flash")
    )
    grok_api_key: str | None = field(
        default_factory=lambda: os.environ.get("GROK_API_KEY")
        or os.environ.get("XAI_API_KEY")
        or None
    )
    grok_model: str = field(
        default_factory=lambda: os.environ.get("ITARS_GROK_MODEL", "grok-3-mini")
    )
    llm_max_output_tokens: int = field(
        default_factory=lambda: _env_int("ITARS_LLM_MAX_OUTPUT_TOKENS", 512)
    )
    llm_temperature: float = field(
        default_factory=lambda: _env_float("ITARS_LLM_TEMPERATURE", 0.3)
    )
    llm_timeout_s: float = field(
        default_factory=lambda: _env_float("ITARS_LLM_TIMEOUT_S", 30.0)
    )
    # Per-feature output-token budget per process (0 = unlimited). Guards against
    # runaway spend; enforced before each call.
    llm_feature_token_budget: int = field(
        default_factory=lambda: _env_int("ITARS_LLM_FEATURE_TOKEN_BUDGET", 200_000)
    )

    # --- Artifact filenames required by the serving pipeline (fatal if missing) ---
    required_artifacts: tuple[str, ...] = (
        "sbert_classifier.pkl",
        "tag_calibrators.pkl",
        "tag_temperature_scaler.pkl",
        "mlb_tag_binarizer.pkl",
        "tuned_priority_model.pkl",
        "priority_encoder.pkl",
        "hf_scaler.pkl",
        "department_prototypes.pkl",
        "routing_label_policy.pkl",
        "routing_review_policy.pkl",
        "duplicate_thresholds.pkl",
        "faiss_index_meta.pkl",
        "db_embeddings.npy",
        "ticket_ids.pkl",
    )


def _load_dotenv(path: Path) -> None:
    """Minimal, dependency-free .env loader. Sets vars that aren't already in the
    environment (real env vars always win). Lets `main/.env` hold secrets like
    API keys without committing them (the file is gitignored)."""
    try:
        if not path.exists():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


_load_dotenv(MAIN_DIR / ".env")
SETTINGS = Settings()
