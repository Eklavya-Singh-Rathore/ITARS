from __future__ import annotations

import ast
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping

import joblib
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


DEFAULT_TAG_TO_DEPARTMENT = {
    "technical_issue": "Technical_Support",
    "hardware_issue": "Technical_Support",
    "software_issue": "Technical_Support",
    "network_issue": "Technical_Support",
    "performance_issue": "Technical_Support",
    "system_issue": "Technical_Support",
    "configuration_issue": "Technical_Support",
    "compatibility_issue": "Technical_Support",
    "maintenance_issue": "Technical_Support",
    "update_request": "Technical_Support",
    "scalability_issue": "Technical_Support",
    "synchronization_issue": "Technical_Support",
    "access_issue": "IT_Support",
    "authentication_issue": "IT_Support",
    "security_issue": "IT_Support",
    "api_issue": "IT_Support",
    "data_issue": "IT_Support",
    "integration_issue": "IT_Support",
    "incident": "Service_Outages_And_Maintenance",
    "service_request": "Customer_Service",
    "general_inquiry": "Customer_Service",
    "billing_issue": "Billing_And_Payments",
    "refund_request": "Billing_And_Payments",
    "order_issue": "Returns_And_Exchanges",
    "feature_request": "Product_Support",
    "training_request": "Human_Resources",
    "sales_inquiry": "Sales_And_Presales",
    "digital_marketing": "Marketing",
    "digital_strategy": "Marketing",
}

KNOWN_DEPARTMENT_ALIASES = {
    "technical_support": "Technical_Support",
    "it_support": "IT_Support",
    "service_outages_and_maintenance": "Service_Outages_And_Maintenance",
    "customer_service": "Customer_Service",
    "billing_and_payments": "Billing_And_Payments",
    "returns_and_exchanges": "Returns_And_Exchanges",
    "product_support": "Product_Support",
    "human_resources": "Human_Resources",
    "sales_and_presales": "Sales_And_Presales",
    "marketing": "Marketing",
    "general_inquiry": "Customer_Service",
}


def _normalize_mapping(mapping) -> dict[str, str]:
    if not isinstance(mapping, Mapping):
        return {}
    return {
        str(tag): str(department)
        for tag, department in mapping.items()
    }


def _extract_tag_mapping(policy_or_mapping) -> dict[str, str]:
    if isinstance(policy_or_mapping, Mapping) and "tag_to_department" in policy_or_mapping:
        return _normalize_mapping(policy_or_mapping.get("tag_to_department", {}))
    return _normalize_mapping(policy_or_mapping)


def _normalize_department_key(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("&", "and")
        .replace("-", "_")
        .replace(" ", "_")
    )


def canonicalize_department_name(name, *, valid_departments=None):
    if name is None:
        return None

    text = str(name).strip()
    if not text or text.lower() == "nan":
        return None

    valid_departments = [str(department) for department in (valid_departments or [])]
    normalized_valid = {
        _normalize_department_key(department): department
        for department in valid_departments
    }
    normalized_name = _normalize_department_key(text)

    if normalized_name in normalized_valid:
        return normalized_valid[normalized_name]

    aliased = KNOWN_DEPARTMENT_ALIASES.get(normalized_name)
    if aliased is not None:
        return aliased

    return text if not valid_departments else None


def parse_tag_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(tag) for tag in value]

    if value is None:
        return []

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = ast.literal_eval(stripped)
            if isinstance(parsed, list):
                return [str(tag) for tag in parsed]
        except Exception:
            return []

    return []


def validate_routing_label_mapping(
    tag_to_department,
    *,
    valid_tags=None,
    valid_departments=None,
):
    normalized_mapping = _normalize_mapping(tag_to_department)
    valid_tag_list = (
        [str(tag) for tag in valid_tags]
        if valid_tags is not None
        else None
    )
    valid_department_set = (
        {str(department) for department in valid_departments}
        if valid_departments is not None
        else None
    )

    stale_tags = []
    if valid_tag_list is not None:
        stale_tags = [
            tag for tag in normalized_mapping
            if tag not in valid_tag_list
        ]

    invalid_departments = {}
    if valid_department_set is not None:
        invalid_departments = {
            tag: department
            for tag, department in normalized_mapping.items()
            if department not in valid_department_set
        }

    cleaned_mapping = {
        tag: department
        for tag, department in normalized_mapping.items()
        if tag not in stale_tags and tag not in invalid_departments
    }

    missing_tags = []
    if valid_tag_list is not None:
        missing_tags = [
            tag for tag in valid_tag_list
            if tag not in cleaned_mapping
        ]

    return cleaned_mapping, missing_tags, stale_tags, invalid_departments


def build_routing_label_policy(
    *,
    valid_tags,
    valid_departments,
    base_mapping=None,
    fallback_tag_to_department=None,
    default_department="Human_Review",
):
    merged_mapping = _normalize_mapping(fallback_tag_to_department)
    merged_mapping.update(_normalize_mapping(base_mapping))

    cleaned_mapping, missing_tags, stale_tags, invalid_departments = (
        validate_routing_label_mapping(
            merged_mapping,
            valid_tags=valid_tags,
            valid_departments=valid_departments,
        )
    )

    return {
        "tag_to_department": cleaned_mapping,
        "valid_tags": [str(tag) for tag in valid_tags],
        "valid_departments": [str(department) for department in valid_departments],
        "default_department": str(default_department),
        "missing_tags": missing_tags,
        "stale_tags": stale_tags,
        "invalid_departments": invalid_departments,
        "mapping_count": len(cleaned_mapping),
    }


def assert_valid_routing_label_policy(
    policy_or_mapping,
    *,
    valid_tags,
    valid_departments,
):
    cleaned_mapping, missing_tags, stale_tags, invalid_departments = (
        validate_routing_label_mapping(
            _extract_tag_mapping(policy_or_mapping),
            valid_tags=valid_tags,
            valid_departments=valid_departments,
        )
    )

    if missing_tags or stale_tags or invalid_departments:
        raise ValueError(
            "Routing label policy validation failed: "
            f"missing_tags={missing_tags}, "
            f"stale_tags={stale_tags}, "
            f"invalid_departments={invalid_departments}"
        )

    return cleaned_mapping


def assert_predicted_tags_mapped(
    predicted_tags,
    policy_or_mapping,
    *,
    valid_departments,
):
    tag_to_department = _extract_tag_mapping(policy_or_mapping)
    valid_department_set = {str(department) for department in valid_departments}

    missing_tags = [
        str(tag) for tag in predicted_tags
        if str(tag) not in tag_to_department
    ]
    invalid_departments = {
        str(tag): tag_to_department.get(str(tag))
        for tag in predicted_tags
        if tag_to_department.get(str(tag)) not in valid_department_set
    }

    if missing_tags or invalid_departments:
        raise ValueError(
            "Predicted tags are not fully covered by the routing label policy: "
            f"missing_tags={missing_tags}, "
            f"invalid_departments={invalid_departments}"
        )


def _normalize_vector(vector):
    arr = np.asarray(vector, dtype=float).reshape(-1)
    if arr.size == 0:
        return arr
    norm = np.linalg.norm(arr)
    if norm == 0.0:
        return arr
    return arr / norm


def _build_department_semantic_vectors(
    valid_departments,
    *,
    dept_prototypes=None,
    embed_text_fn=None,
):
    department_vectors = {}

    for department in valid_departments:
        weighted_parts = []
        if dept_prototypes is not None and department in dept_prototypes:
            proto = _normalize_vector(dept_prototypes[department])
            if proto.size:
                weighted_parts.append((0.25, proto))

        if embed_text_fn is not None:
            label_vector = _normalize_vector(
                embed_text_fn(str(department).replace("_", " "))
            )
            if label_vector.size:
                weighted_parts.append((0.75, label_vector))

        if not weighted_parts:
            continue

        if len(weighted_parts) == 1:
            department_vectors[str(department)] = weighted_parts[0][1]
            continue

        merged = sum(weight * vector for weight, vector in weighted_parts)
        merged = _normalize_vector(merged)
        department_vectors[str(department)] = merged

    return department_vectors


def _department_semantic_scores(tag, department_vectors, *, embed_text_fn=None):
    if embed_text_fn is None or not department_vectors:
        return {}

    tag_vector = _normalize_vector(embed_text_fn(str(tag).replace("_", " ")))
    if tag_vector.size == 0:
        return {}

    scores = {}
    for department, department_vector in department_vectors.items():
        if department_vector.shape != tag_vector.shape:
            continue
        raw_similarity = float(np.dot(tag_vector, department_vector))
        scores[department] = normalize_semantic_similarity(raw_similarity)

    return scores


def build_department_prototypes_from_tag_map(
    texts,
    tag_lists,
    *,
    tag_to_department,
    embed_texts_fn,
    min_examples=5,
):
    if embed_texts_fn is None:
        raise ValueError("embed_texts_fn is required to build department prototypes.")

    normalized_mapping = _extract_tag_mapping(tag_to_department)
    department_texts: dict[str, list[str]] = defaultdict(list)

    for text, tags in zip(texts, tag_lists):
        matched_departments = {
            normalized_mapping[tag]
            for tag in parse_tag_list(tags)
            if tag in normalized_mapping
        }
        for department in matched_departments:
            department_texts[department].append(str(text))

    department_prototypes = {}
    for department, department_examples in department_texts.items():
        if len(department_examples) < int(min_examples):
            continue

        embeddings = np.asarray(embed_texts_fn(department_examples), dtype=float)
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)

        prototype = _normalize_vector(np.mean(embeddings, axis=0))
        if prototype.size == 0:
            continue
        department_prototypes[department] = prototype

    if not department_prototypes:
        raise ValueError("No department prototypes could be built from the provided texts and tags.")

    return department_prototypes


def analyze_routing_label_policy(
    dataset_paths,
    *,
    tag_classes,
    valid_departments,
    existing_mapping=None,
    queue_column="queue",
    tags_column="tags",
):
    import pandas as pd

    valid_tags = [str(tag) for tag in tag_classes]
    valid_departments = [str(department) for department in valid_departments]
    existing_mapping = _extract_tag_mapping(existing_mapping)

    tag_department_counts: dict[str, Counter] = defaultdict(Counter)
    observed_departments = set()
    total_rows = 0
    used_rows = 0

    for dataset_path in dataset_paths:
        path = Path(dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found for routing-label analysis: {path}")

        frame = pd.read_csv(path, usecols=[queue_column, tags_column])
        total_rows += len(frame)

        for queue_value, tags_value in zip(frame[queue_column], frame[tags_column]):
            department = canonicalize_department_name(
                queue_value,
                valid_departments=valid_departments,
            )
            tags = parse_tag_list(tags_value)
            if department is None or not tags:
                continue

            used_rows += 1
            observed_departments.add(department)

            for tag in tags:
                if tag in valid_tags:
                    tag_department_counts[tag][department] += 1

    tag_statistics = {}
    missing_mappings = []
    unused_tags = []
    majority_mismatch_tags = []

    for tag in valid_tags:
        counts = tag_department_counts.get(tag, Counter())
        ranked = counts.most_common()
        total_examples = int(sum(counts.values()))
        majority_department = ranked[0][0] if ranked else None
        majority_count = int(ranked[0][1]) if ranked else 0
        fallback_department = ranked[1][0] if len(ranked) > 1 else None
        fallback_count = int(ranked[1][1]) if len(ranked) > 1 else 0
        majority_share = float(majority_count / total_examples) if total_examples else 0.0
        majority_margin_share = (
            float((majority_count - fallback_count) / total_examples)
            if total_examples
            else 0.0
        )

        current_department = existing_mapping.get(tag)
        if current_department is None:
            missing_mappings.append(tag)
        if total_examples == 0:
            unused_tags.append(tag)
        if current_department is not None and majority_department is not None and current_department != majority_department:
            majority_mismatch_tags.append(tag)

        tag_statistics[tag] = {
            "current_department": current_department,
            "department_counts": dict(counts),
            "total_examples": total_examples,
            "majority_department": majority_department,
            "majority_share": majority_share,
            "majority_margin_share": majority_margin_share,
            "fallback_department": fallback_department,
            "fallback_share": float(fallback_count / total_examples) if total_examples else 0.0,
            "missing_mapping": current_department is None,
            "unused_tag": total_examples == 0,
        }

    redundant_mappings = [
        tag for tag in existing_mapping
        if tag not in valid_tags
    ]
    invalid_departments = {
        tag: department
        for tag, department in existing_mapping.items()
        if canonicalize_department_name(department, valid_departments=valid_departments) is None
    }

    return {
        "dataset_paths": [str(Path(path)) for path in dataset_paths],
        "valid_tags": valid_tags,
        "valid_departments": valid_departments,
        "tag_statistics": tag_statistics,
        "missing_mappings": missing_mappings,
        "redundant_mappings": redundant_mappings,
        "invalid_departments": invalid_departments,
        "unused_tags": unused_tags,
        "majority_mismatch_tags": majority_mismatch_tags,
        "observed_departments": sorted(observed_departments),
        "row_count": int(total_rows),
        "used_row_count": int(used_rows),
    }


def rebuild_routing_label_policy(
    analysis,
    *,
    existing_mapping=None,
    valid_departments=None,
    dept_prototypes=None,
    embed_text_fn=None,
    rare_tag_threshold=500,
    strong_majority_threshold=0.50,
    distribution_weight=0.60,
    semantic_weight=0.40,
    default_department="Human_Review",
    semantic_override_margin=0.05,
):
    tag_statistics = analysis.get("tag_statistics", {})
    valid_tags = [str(tag) for tag in analysis.get("valid_tags", tag_statistics.keys())]
    valid_departments = [
        str(department)
        for department in (valid_departments or analysis.get("valid_departments", []))
    ]
    existing_mapping = _extract_tag_mapping(existing_mapping)

    department_vectors = _build_department_semantic_vectors(
        valid_departments,
        dept_prototypes=dept_prototypes,
        embed_text_fn=embed_text_fn,
    )

    rebuilt_mapping = {}
    tag_metadata = {}

    for tag in valid_tags:
        stats = tag_statistics.get(tag, {})
        counts = Counter(stats.get("department_counts", {}))
        total_examples = int(stats.get("total_examples", 0))
        majority_department = stats.get("majority_department")
        majority_share = float(stats.get("majority_share", 0.0))
        semantic_scores = _department_semantic_scores(
            tag,
            department_vectors,
            embed_text_fn=embed_text_fn,
        )
        semantic_department = (
            max(semantic_scores, key=semantic_scores.get)
            if semantic_scores
            else None
        )

        if total_examples >= rare_tag_threshold and majority_department is not None:
            primary_department = majority_department
            selection_reason = (
                "majority_distribution"
                if majority_share >= strong_majority_threshold
                else "majority_with_fallback"
            )
            ranked_combined = []
        else:
            combined_scores = {}
            for department in valid_departments:
                semantic_score = float(semantic_scores.get(department, 0.0))
                combined_scores[department] = float(semantic_weight) * semantic_score

            ranked_combined = sorted(
                combined_scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            primary_department = semantic_department or (ranked_combined[0][0] if ranked_combined else None)
            current_department = existing_mapping.get(tag)
            current_semantic_score = float(semantic_scores.get(current_department, 0.0))
            winning_semantic_score = float(semantic_scores.get(primary_department, 0.0))
            if (
                current_department in valid_departments
                and current_semantic_score + float(semantic_override_margin) >= winning_semantic_score
            ):
                primary_department = current_department
            if total_examples == 0:
                selection_reason = "semantic_fallback"
            else:
                selection_reason = "rare_tag_semantic"

        if primary_department is None:
            primary_department = existing_mapping.get(tag)
            selection_reason = "existing_mapping_fallback"

        if primary_department is None or primary_department not in valid_departments:
            raise ValueError(f"Unable to determine a valid department for tag '{tag}'.")

        observed_fallback = stats.get("fallback_department")
        combined_fallback = (
            ranked_combined[1][0]
            if len(ranked_combined) > 1
            else None
        )
        fallback_department = observed_fallback or combined_fallback
        if fallback_department == primary_department:
            fallback_department = None

        rebuilt_mapping[tag] = primary_department
        tag_metadata[tag] = {
            "primary_department": primary_department,
            "fallback_department": fallback_department,
            "current_department": existing_mapping.get(tag),
            "majority_department": majority_department,
            "majority_share": majority_share,
            "total_examples": total_examples,
            "selection_reason": selection_reason,
            "department_counts": dict(counts),
            "semantic_department": semantic_department,
        }

    policy = build_routing_label_policy(
        valid_tags=valid_tags,
        valid_departments=valid_departments,
        base_mapping=rebuilt_mapping,
        fallback_tag_to_department=existing_mapping,
        default_department=default_department,
    )
    policy.update(
        {
            "tag_metadata": tag_metadata,
            "analysis_summary": {
                "row_count": int(analysis.get("row_count", 0)),
                "used_row_count": int(analysis.get("used_row_count", 0)),
                "missing_mappings": list(analysis.get("missing_mappings", [])),
                "redundant_mappings": list(analysis.get("redundant_mappings", [])),
                "invalid_departments": dict(analysis.get("invalid_departments", {})),
                "unused_tags": list(analysis.get("unused_tags", [])),
                "majority_mismatch_tags": list(analysis.get("majority_mismatch_tags", [])),
            },
            "policy_name": "routing_label_policy",
        }
    )
    return policy


def load_routing_label_policy(
    policy_path,
    *,
    fallback_tag_to_department=None,
    valid_tags=None,
    valid_departments=None,
    default_department="Human_Review",
):
    path = Path(policy_path) if policy_path is not None else None
    loaded_policy = {}
    if path is not None and path.exists():
        loaded_policy = joblib.load(path)

    base_mapping = _extract_tag_mapping(loaded_policy)

    valid_tags = (
        [str(tag) for tag in valid_tags]
        if valid_tags is not None
        else list(base_mapping)
    )
    valid_departments = (
        [str(department) for department in valid_departments]
        if valid_departments is not None
        else []
    )

    policy = build_routing_label_policy(
        valid_tags=valid_tags,
        valid_departments=valid_departments,
        base_mapping=base_mapping,
        fallback_tag_to_department=fallback_tag_to_department,
        default_department=default_department,
    )
    if isinstance(loaded_policy, Mapping):
        for key, value in loaded_policy.items():
            if key == "tag_to_department":
                continue
            policy[key] = value
    return policy


def normalize_semantic_similarity(raw_similarity: float) -> float:
    return float(np.clip((float(raw_similarity) + 1.0) / 2.0, 0.0, 1.0))


def _to_tag_prob_dict(tag_prob_source, tag_names=None) -> dict[str, float]:
    if isinstance(tag_prob_source, Mapping):
        return {str(tag): float(prob) for tag, prob in tag_prob_source.items()}

    if tag_names is None:
        raise ValueError("tag_names are required when tag_prob_source is not a mapping.")

    probs = np.asarray(tag_prob_source, dtype=float).reshape(-1)
    return {
        str(tag_names[idx]): float(probs[idx])
        for idx in range(min(len(tag_names), probs.size))
    }


def _department_classifier_confidence(probabilities) -> float:
    if len(probabilities) == 0:
        return 0.0
    probs = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    return float(1.0 - np.prod(1.0 - probs))


def compute_department_hybrid_scores(
    tag_prob_source,
    embedding,
    dept_prototypes,
    tag_to_department=None,
    *,
    tag_names=None,
    classifier_weight=0.7,
    similarity_weight=0.3,
    top_k=5,
):
    tag_to_department = tag_to_department or DEFAULT_TAG_TO_DEPARTMENT
    tag_prob_dict = _to_tag_prob_dict(tag_prob_source, tag_names=tag_names)
    sorted_tags = sorted(
        tag_prob_dict.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    if top_k is not None:
        sorted_tags = sorted_tags[:top_k]

    assert_predicted_tags_mapped(
        [tag for tag, _ in sorted_tags],
        tag_to_department,
        valid_departments=dept_prototypes.keys(),
    )

    department_prob_lists: dict[str, list[float]] = {}
    top_tag_votes = []

    for tag, prob in sorted_tags:
        department = tag_to_department.get(tag)
        if department is None:
            continue
        clipped_prob = float(np.clip(prob, 0.0, 1.0))
        department_prob_lists.setdefault(department, []).append(clipped_prob)
        top_tag_votes.append(
            {
                "tag": tag,
                "score": clipped_prob,
                "department": department,
            }
        )

    details = {}
    candidate_departments = set(dept_prototypes) | set(department_prob_lists)
    if not candidate_departments:
        return None, 0.0, {}, top_tag_votes

    emb = np.asarray(embedding, dtype=float).reshape(1, -1)

    for department in candidate_departments:
        classifier_confidence = _department_classifier_confidence(
            department_prob_lists.get(department, [])
        )

        proto = dept_prototypes.get(department)
        raw_similarity = 0.0
        if proto is not None:
            raw_similarity = float(
                cosine_similarity(
                    emb,
                    np.asarray(proto, dtype=float).reshape(1, -1),
                )[0][0]
            )

        semantic_similarity = normalize_semantic_similarity(raw_similarity)
        hybrid_confidence = (
            float(classifier_weight) * classifier_confidence
            + float(similarity_weight) * semantic_similarity
        )

        details[department] = {
            "department": department,
            "classifier_confidence": float(classifier_confidence),
            "semantic_similarity": float(semantic_similarity),
            "raw_semantic_similarity": float(raw_similarity),
            "hybrid_confidence": float(hybrid_confidence),
        }

    best_department = max(
        details,
        key=lambda dept: details[dept]["hybrid_confidence"],
    )
    best_hybrid_confidence = float(details[best_department]["hybrid_confidence"])
    return best_department, best_hybrid_confidence, details, top_tag_votes
