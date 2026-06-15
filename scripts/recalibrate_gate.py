"""Recalibrate the routing confidence gate (audit defect #8).

`routing_review_policy.pkl` self-reports `percentile_threshold ≈ 0.95003` against
a held-out hybrid-confidence distribution with mean 0.96, std 0.015, **min 0.74**.
That means the Stage-1 floor (0.45) and Stage-2 flagged floor (0.30) can never
fire — the gate is statistically inert (audit Phase 2 finding).

The Feature Report + Revamp Plan keep the **architecture** of the two-stage gate;
this script **recalibrates the parameters** so the floors actually separate easy
from hard tickets, without changing the gate's shape.

Two recalibration modes:

  1. Distribution-only (default, no labels required):
       Run the pipeline over a held-out sample of cleaned tickets, capture
       `hybrid_confidence` for every prediction, then:
         * report mean/std/min/max — confirm or refute the audit's "inert" finding,
         * set `hybrid_floor`        := percentile(P_floor)         of the distribution,
         * set `flagged_hybrid_floor`:= percentile(P_flagged)       of the distribution,
         * refit the review policy via `fit_review_policy` against the same scores
           at the target review fraction.

       Defaults: --p-floor 1.0  --p-flagged 5.0  --review-fraction 0.10
       So the Stage-1 floor lands at the 1st percentile (truly catastrophic
       confidence drops), the flagged floor at the 5th, and the review queue is
       sized at ~10% rather than the inert 15%.

  2. Risk-coverage (passes --labels CSV with a `correct` column):
       Sort by hybrid_confidence, compute cumulative error rate, and pick the
       smallest `hybrid_floor` such that mis-route rate among AUTO_ROUTE ≤ target.
       This is the audit's "evidence-sized review queue" idea, restricted to the
       retained two-stage gate.

By default the script is a DRY RUN — it prints the diagnosis and the proposed
new policy without touching disk. Pass `--apply` to overwrite
`routing_review_policy.pkl` (the original is backed up to `.bak`).

Run from `main/`:
    python -m scripts.recalibrate_gate --sample 1500
    python -m scripts.recalibrate_gate --sample 1500 --apply
    python -m scripts.recalibrate_gate --labels feedback.csv --target-error 0.02 --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np

MAIN_DIR = Path(__file__).resolve().parents[1]
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))

from backend.core.config import SETTINGS  # noqa: E402
from backend.services.review import fit_review_policy  # noqa: E402


def _load_texts(dataset_path: Path, sample: int, seed: int) -> list[str]:
    import pandas as pd

    df = pd.read_csv(dataset_path, usecols=["text"]).dropna(subset=["text"])
    if sample and sample < len(df):
        df = df.sample(n=int(sample), random_state=seed)
    return df["text"].astype(str).tolist()


def _find_dataset(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = [
        SETTINGS.data_dir / "Domain-A_Dataset_Clean.csv",
        SETTINGS.model_dir.parent / "Data" / "Domain-A_Dataset_Clean.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not find Domain-A_Dataset_Clean.csv; pass --dataset. Checked: {candidates}"
    )


def _collect_hybrid_scores(texts: list[str]) -> np.ndarray:
    """Run the routing pipeline over `texts` and return the hybrid_confidence array.

    Translation and duplicate registration are disabled (we want pure routing
    confidence; we don't want to mutate the duplicate index).
    """
    from backend.services.pipeline import RoutingPipeline, encode_ticket_embedding

    pipeline = RoutingPipeline()  # loads encoders
    scores: list[float] = []
    for text in texts:
        emb = encode_ticket_embedding(text, pipeline.routing_sbert)
        routing = pipeline.route_ticket(emb, text)
        scores.append(float(routing["hybrid_confidence"]))
    return np.asarray(scores, dtype=float)


def _summarize(scores: np.ndarray) -> dict:
    return {
        "n": int(scores.size),
        "mean": float(scores.mean()),
        "std": float(scores.std()),
        "min": float(scores.min()),
        "p01": float(np.percentile(scores, 1)),
        "p05": float(np.percentile(scores, 5)),
        "p10": float(np.percentile(scores, 10)),
        "p25": float(np.percentile(scores, 25)),
        "p50": float(np.percentile(scores, 50)),
        "p95": float(np.percentile(scores, 95)),
        "max": float(scores.max()),
    }


def _print_summary(label: str, summary: dict) -> None:
    print(f"\n{label}:")
    for key, value in summary.items():
        print(f"  {key:>5}: {value:.4f}" if isinstance(value, float) else f"  {key:>5}: {value}")


def _verdict(summary: dict, current_floor: float, current_flagged: float) -> None:
    inert_floor = summary["min"] > current_floor
    inert_flagged = summary["min"] > current_flagged
    print("\nDiagnosis:")
    print(
        f"  current hybrid_floor         = {current_floor:.4f}  "
        f"{'INERT (min > floor)' if inert_floor else 'fires occasionally'}"
    )
    print(
        f"  current flagged_hybrid_floor = {current_flagged:.4f}  "
        f"{'INERT (min > floor)' if inert_flagged else 'fires occasionally'}"
    )


def _risk_coverage(
    scores: np.ndarray,
    correct: np.ndarray,
    target_error_rate: float,
) -> dict:
    """Return the smallest `hybrid_floor` such that error rate above it ≤ target."""
    order = np.argsort(-scores)  # descending
    s_sorted = scores[order]
    c_sorted = correct[order].astype(float)
    cum_errors = np.cumsum(1.0 - c_sorted)
    cum_count = np.arange(1, len(scores) + 1)
    cum_error_rate = cum_errors / cum_count
    # Smallest index where rate exceeds target — everything strictly above the
    # next threshold is safe to auto-route.
    above = cum_error_rate <= target_error_rate
    if not bool(above.any()):
        # nothing is safe; recommend pushing the floor above the max
        return {"hybrid_floor": float(s_sorted[0]) + 1e-3, "coverage": 0.0}
    safe_count = int(above.sum())
    floor = float(s_sorted[safe_count - 1])
    coverage = float(safe_count / len(scores))
    return {
        "hybrid_floor": floor,
        "coverage": coverage,
        "achieved_error_rate": float(cum_error_rate[safe_count - 1]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recalibrate the routing confidence gate.")
    parser.add_argument("--dataset", default=None, help="CSV with a 'text' column.")
    parser.add_argument("--sample", type=int, default=1500, help="Sample size from dataset.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--p-floor", type=float, default=1.0, help="Stage-1 floor percentile.")
    parser.add_argument("--p-flagged", type=float, default=5.0, help="Flagged-band percentile.")
    parser.add_argument(
        "--review-fraction",
        type=float,
        default=0.10,
        help="Target review queue size (replaces 0.15 in routing_review_policy.pkl).",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help=(
            "Optional CSV with columns text,correct (0/1). Switches to risk-coverage "
            "mode: picks hybrid_floor so auto-route error rate ≤ --target-error."
        ),
    )
    parser.add_argument("--target-error", type=float, default=0.02)
    parser.add_argument("--apply", action="store_true", help="Overwrite the review policy.")
    args = parser.parse_args()

    print(f"Model dir: {SETTINGS.model_dir}")
    print(f"Current   hybrid_floor         = {SETTINGS.hybrid_floor}")
    print(f"Current   flagged_hybrid_floor = {SETTINGS.flagged_hybrid_floor}")

    if args.labels:
        import pandas as pd

        df = pd.read_csv(args.labels)
        if not {"text", "correct"}.issubset(df.columns):
            raise SystemExit("Labels CSV must have columns: text, correct (0/1).")
        texts = df["text"].astype(str).tolist()
        scores = _collect_hybrid_scores(texts)
        correct = df["correct"].astype(int).to_numpy()
        summary = _summarize(scores)
        _print_summary("Confidence distribution", summary)
        _verdict(summary, SETTINGS.hybrid_floor, SETTINGS.flagged_hybrid_floor)
        rc = _risk_coverage(scores, correct, args.target_error)
        new_floor = float(rc["hybrid_floor"])
        new_flagged = float(min(new_floor, summary["p05"]))
        print(
            "\nRisk-coverage recommendation: "
            f"hybrid_floor={new_floor:.4f}  (coverage={rc['coverage']:.2%}, "
            f"achieved_error_rate={rc.get('achieved_error_rate', 0.0):.4f})"
        )
    else:
        dataset = _find_dataset(args.dataset)
        print(f"Dataset:  {dataset} (sample={args.sample})")
        texts = _load_texts(dataset, args.sample, args.seed)
        scores = _collect_hybrid_scores(texts)
        summary = _summarize(scores)
        _print_summary("Confidence distribution", summary)
        _verdict(summary, SETTINGS.hybrid_floor, SETTINGS.flagged_hybrid_floor)
        new_floor = float(np.percentile(scores, args.p_floor))
        new_flagged = float(np.percentile(scores, args.p_flagged))

    print("\nProposed recalibrated parameters:")
    print(f"  hybrid_floor         = {new_floor:.4f}  (was {SETTINGS.hybrid_floor})")
    print(f"  flagged_hybrid_floor = {new_flagged:.4f}  (was {SETTINGS.flagged_hybrid_floor})")
    print(f"  target_review_fraction = {args.review_fraction:.2f}")

    new_policy = fit_review_policy(
        scores,
        target_review_fraction=args.review_fraction,
        fallback_threshold=new_floor,
    )
    new_policy["recalibration"] = {
        "method": "risk_coverage" if args.labels else "distribution_percentile",
        "summary": summary,
        "hybrid_floor": new_floor,
        "flagged_hybrid_floor": new_flagged,
        "review_fraction": args.review_fraction,
        "p_floor": args.p_floor if not args.labels else None,
        "p_flagged": args.p_flagged if not args.labels else None,
    }
    print(
        "\nRecalibrated review policy:\n"
        f"  percentile_threshold = {new_policy['percentile_threshold']:.4f}\n"
        f"  fallback_threshold   = {new_policy['fallback_threshold']:.4f}\n"
        f"  effective_threshold  = {new_policy['effective_threshold']:.4f}\n"
        f"  effective_review_fraction = {new_policy['effective_review_fraction']:.4f}"
    )

    policy_path = SETTINGS.model_dir / "routing_review_policy.pkl"
    if args.apply:
        if policy_path.exists():
            shutil.copy(policy_path, policy_path.with_suffix(".pkl.bak"))
            print(f"\nBacked up original to {policy_path}.bak")
        joblib.dump(new_policy, policy_path)
        print(f"Wrote recalibrated policy -> {policy_path}")
        print(
            "\nNext: set the new floor in env (or update config.py defaults):\n"
            f"  ITARS_HYBRID_FLOOR={new_floor:.4f}\n"
            f"  ITARS_FLAGGED_HYBRID_FLOOR={new_flagged:.4f}"
        )
    else:
        print("\n(dry run — pass --apply to overwrite the review policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
