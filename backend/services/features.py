"""Canonical handcrafted-feature extraction — the single source of truth.

This fixes the training/serving feature skew (audit defect #5). The deployed
`app.py:extract_features` diverged from the function the priority model and
`hf_scaler` were actually fit on:

  Training (`Model_Training_and_Evaluation.ipynb:text_features`):
    - 11 URGENCY_WORDS, 6 NEGATION_WORDS, matched **whole-word**
    - vocab richness denominator: max(len(words), 1)
  Serving (`hf_deploy/app.py:extract_features`, BUGGY):
    - only 3 urgency + 3 negation words, matched as **substrings**
      => "down" fired inside "download", "no" inside "now", etc.
    - vocab richness denominator: (len(words) + 1)

`hf_scaler.pkl` / `tuned_priority_model.pkl` were fitted on the TRAINING
distribution, so the serving variant fed every priority prediction
out-of-distribution features. We standardize on the training function.

Parity note: feature ORDER and arithmetic exactly match the training function.
Text is lowercased before whole-word matching (training operated on cleaned,
lowercased text). Re-cleaning/lemmatizing the input to fully match the training
text representation is intentionally out of Phase-1 scope; the keyword/denominator
divergences fixed here are the documented skew.
"""

from __future__ import annotations

import numpy as np

# Exact word sets from Model_Training_and_Evaluation.ipynb (the fitted distribution).
URGENCY_WORDS = frozenset(
    {
        "urgent",
        "asap",
        "critical",
        "emergency",
        "immediately",
        "down",
        "outage",
        "broken",
        "crash",
        "blocked",
        "severe",
    }
)
NEGATION_WORDS = frozenset({"not", "no", "nor", "never", "neither", "cannot"})

# Number of handcrafted features produced (must match hf_scaler's fitted shape).
N_HANDCRAFTED_FEATURES = 6


def extract_handcrafted(text: str) -> list[float]:
    """Return the 6 handcrafted features in the order the priority model expects.

    [char_length, word_count, vocab_richness, avg_word_length,
     urgency_count, negation_count]
    """
    raw = str(text)
    words = raw.lower().split()
    unique = set(words)
    return [
        len(raw),                                          # char length
        len(words),                                        # word count
        len(unique) / max(len(words), 1),                  # vocab richness
        float(np.mean([len(w) for w in words])) if words else 0.0,  # avg word length
        sum(1 for w in words if w in URGENCY_WORDS),       # urgency keywords (whole-word)
        sum(1 for w in words if w in NEGATION_WORDS),      # negation keywords (whole-word)
    ]


def extract_handcrafted_with_evidence(text: str) -> tuple[list[float], dict]:
    """Same features as `extract_handcrafted`, plus the matched words for explainability.

    The numerical features remain byte-identical so the priority model is fed
    exactly what `hf_scaler` was fit on. The `evidence` dict additionally exposes
    which urgency/negation words actually fired — what the priority explanation
    panel needs.
    """
    raw = str(text)
    words = raw.lower().split()
    unique = set(words)
    matched_urgency = [w for w in words if w in URGENCY_WORDS]
    matched_negation = [w for w in words if w in NEGATION_WORDS]
    features = [
        len(raw),
        len(words),
        len(unique) / max(len(words), 1),
        float(np.mean([len(w) for w in words])) if words else 0.0,
        len(matched_urgency),
        len(matched_negation),
    ]
    evidence = {
        "char_length": features[0],
        "word_count": features[1],
        "vocab_richness": round(features[2], 4),
        "avg_word_length": round(features[3], 2),
        "urgency_words_matched": sorted(set(matched_urgency)),
        "negation_words_matched": sorted(set(matched_negation)),
        "urgency_count": features[4],
        "negation_count": features[5],
    }
    return features, evidence
