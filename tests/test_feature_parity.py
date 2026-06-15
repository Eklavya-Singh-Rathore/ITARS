"""Proves the priority feature-skew fix (numpy-only; no heavy deps needed).

`extract_handcrafted` must (a) match the TRAINING `text_features` the scaler was
fit on, and (b) NOT reproduce the deployed substring bugs ("down" in "download",
"no" in "now") or the wrong vocab-richness denominator.
"""

import numpy as np

from backend.services.features import (
    NEGATION_WORDS,
    N_HANDCRAFTED_FEATURES,
    URGENCY_WORDS,
    extract_handcrafted,
)


# --- Reference: the TRAINING function (Model_Training_and_Evaluation.ipynb) ---
def training_text_features(t: str):
    words = t.split()
    unique = set(words)
    return [
        len(t),
        len(words),
        len(unique) / max(len(words), 1),
        float(np.mean([len(w) for w in words])) if words else 0.0,
        sum(1 for w in words if w in URGENCY_WORDS),
        sum(1 for w in words if w in NEGATION_WORDS),
    ]


# --- Reference: the deployed BUGGY serving function (hf_deploy/app.py) ---
def buggy_serving_features(text: str):
    words = text.split()
    return [
        len(text),
        len(words),
        len(set(words)) / (len(words) + 1),
        float(np.mean([len(word) for word in words])) if words else 0.0,
        sum(word in text.lower() for word in ["urgent", "critical", "down"]),
        sum(word in text.lower() for word in ["not", "cannot", "no"]),
    ]


LOWERCASE_SAMPLES = [
    "the server is down and this is urgent",
    "please download the installer from the portal",
    "now is the time to renew the subscription",
    "a a a b b c",
    "",
    "critical outage broken crash blocked severe emergency immediately asap",
    "i cannot log in and there is no access nor any response",
]


def test_feature_count_and_order():
    feats = extract_handcrafted("the server is down")
    assert len(feats) == N_HANDCRAFTED_FEATURES == 6


def test_matches_training_function():
    for text in LOWERCASE_SAMPLES:
        assert extract_handcrafted(text) == training_text_features(text)


def test_substring_bug_is_fixed_download():
    # "download" must NOT count as the urgency word "down".
    feats = extract_handcrafted("please download the installer")
    urgency = feats[4]
    assert urgency == 0
    # The deployed bug counted it.
    assert buggy_serving_features("please download the installer")[4] >= 1


def test_substring_bug_is_fixed_now():
    # "now" must NOT count as the negation word "no".
    feats = extract_handcrafted("now is the time")
    assert feats[5] == 0
    assert buggy_serving_features("now is the time")[5] >= 1


def test_vocab_richness_denominator():
    # training uses max(len(words),1); buggy serving used len(words)+1.
    text = "a a a b b c"
    assert extract_handcrafted(text)[2] == training_text_features(text)[2]
    assert extract_handcrafted(text)[2] != buggy_serving_features(text)[2]


def test_full_urgency_and_negation_vocab_detected():
    # The deployed version only knew 3 urgency + 3 negation words.
    text = "emergency immediately asap outage broken crash blocked severe"
    # 8 urgency words present, all whole-word.
    assert extract_handcrafted(text)[4] == 8
    assert buggy_serving_features(text)[4] < 8


def test_case_insensitive_whole_word():
    assert extract_handcrafted("The Server Is DOWN")[4] == 1
