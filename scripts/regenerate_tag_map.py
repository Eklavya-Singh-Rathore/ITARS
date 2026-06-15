"""Regenerate the tag->department mapping from data (audit defect #7).

`routing_label_policy.pkl` self-reports ~12/28 majority-mismatched mappings (the
hand-written map contradicts the data). This script recomputes the mapping from the
observed (queue, tags) distribution using the analysis/rebuild functions already in
`backend.services.routing`, reports every mismatch, validates the result, and writes
a regenerated policy.

By default it writes a *.regenerated.pkl alongside the original and does NOT
overwrite (preserves parity). Pass --apply to overwrite routing_label_policy.pkl.
Pass --with-semantics to also load the routing SBERT for the rare-tag semantic step.

Usage (from the main/ directory):
    python -m scripts.regenerate_tag_map
    python -m scripts.regenerate_tag_map --apply
    python -m scripts.regenerate_tag_map --dataset /path/to/Domain-A_Dataset_Clean.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib

# Make `backend` importable when run as a module or a script.
MAIN_DIR = Path(__file__).resolve().parents[1]
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))

from backend.core.config import SETTINGS  # noqa: E402
from backend.services.routing import (  # noqa: E402
    analyze_routing_label_policy,
    assert_valid_routing_label_policy,
    load_routing_label_policy,
    rebuild_routing_label_policy,
)


def _find_dataset(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")
        return path
    candidates = [
        SETTINGS.data_dir / "Domain-A_Dataset_Clean.csv",
        SETTINGS.model_dir.parent / "Data" / "Domain-A_Dataset_Clean.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Could not locate Domain-A_Dataset_Clean.csv. Checked: {candidates}. "
        "Pass --dataset explicitly."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate tag->department mapping.")
    parser.add_argument("--dataset", default=None, help="Path to Domain-A clean CSV.")
    parser.add_argument("--apply", action="store_true", help="Overwrite the policy.")
    parser.add_argument(
        "--with-semantics",
        action="store_true",
        help="Load routing SBERT for rare-tag semantic scoring.",
    )
    args = parser.parse_args()

    model_dir = Path(SETTINGS.model_dir)
    policy_path = model_dir / "routing_label_policy.pkl"
    dataset_path = _find_dataset(args.dataset)

    tag_binarizer = joblib.load(model_dir / "mlb_tag_binarizer.pkl")
    tag_classes = list(tag_binarizer.classes_)
    dept_prototypes = joblib.load(model_dir / "department_prototypes.pkl")
    valid_departments = list(dept_prototypes.keys())

    existing_policy = load_routing_label_policy(
        policy_path,
        valid_tags=tag_classes,
        valid_departments=valid_departments,
    )
    existing_mapping = existing_policy.get("tag_to_department", {})

    print(f"Dataset:        {dataset_path}")
    print(f"Tags:           {len(tag_classes)}   Departments: {len(valid_departments)}")
    print("Analyzing observed (queue, tags) distribution...")
    analysis = analyze_routing_label_policy(
        [dataset_path],
        tag_classes=tag_classes,
        valid_departments=valid_departments,
        existing_mapping=existing_mapping,
    )

    mismatches = analysis.get("majority_mismatch_tags", [])
    print(f"\nRows: {analysis['row_count']:,}  used: {analysis['used_row_count']:,}")
    print(f"Majority-mismatched tags: {len(mismatches)} / {len(tag_classes)}")
    for tag in mismatches:
        stats = analysis["tag_statistics"][tag]
        print(
            f"  - {tag}: current={stats['current_department']} -> "
            f"majority={stats['majority_department']} "
            f"(share={stats['majority_share']:.2f}, n={stats['total_examples']})"
        )
    if analysis.get("missing_mappings"):
        print(f"Missing mappings: {analysis['missing_mappings']}")
    if analysis.get("unused_tags"):
        print(f"Unused tags (0 examples): {analysis['unused_tags']}")
    if analysis.get("redundant_mappings"):
        print(f"Stale/redundant mappings: {analysis['redundant_mappings']}")

    embed_text_fn = None
    if args.with_semantics:
        from sentence_transformers import SentenceTransformer

        from backend.core.runtime_paths import load_model_config, resolve_model_reference

        ref = resolve_model_reference(
            load_model_config(model_dir.parent).get("sbert_model", SETTINGS.routing_sbert),
            base_dir=model_dir.parent,
            model_dir=model_dir,
        )
        encoder = SentenceTransformer(ref)
        embed_text_fn = lambda t: encoder.encode(t)  # noqa: E731

    print("\nRebuilding policy from data...")
    rebuilt = rebuild_routing_label_policy(
        analysis,
        existing_mapping=existing_mapping,
        valid_departments=valid_departments,
        dept_prototypes=dept_prototypes,
        embed_text_fn=embed_text_fn,
    )
    assert_valid_routing_label_policy(
        rebuilt, valid_tags=tag_classes, valid_departments=valid_departments
    )

    changed = {
        tag: (existing_mapping.get(tag), dept)
        for tag, dept in rebuilt["tag_to_department"].items()
        if existing_mapping.get(tag) != dept
    }
    print(f"Mappings changed by regeneration: {len(changed)}")
    for tag, (old, new) in sorted(changed.items()):
        print(f"  * {tag}: {old} -> {new}")

    out_path = policy_path if args.apply else policy_path.with_suffix(".regenerated.pkl")
    joblib.dump(rebuilt, out_path)
    print(f"\nWrote regenerated policy -> {out_path}")
    if not args.apply:
        print("(dry run: original policy unchanged; pass --apply to overwrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
