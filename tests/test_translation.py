"""TranslationService tests (no transformers/network needed for most cases)."""

import pytest

from backend.services.translation import (
    TranslationService,
    chunk_text,
    clean_for_detection,
)


def test_clean_for_detection_strips_pii():
    cleaned = clean_for_detection("mail me at a@b.com or http://x.io or +1 234 567 8901")
    assert "@" not in cleaned
    assert "http" not in cleaned
    assert "567" not in cleaned


def test_chunk_text_splits_on_word_count():
    assert list(chunk_text("a b c d e", max_words=2)) == ["a b", "c d", "e"]


def test_model_key_mapping():
    svc = TranslationService()
    assert svc._model_key("de") == "de"
    assert svc._model_key("es") == "romance"
    assert svc._model_key("fr") == "romance"
    assert svc._model_key("pt") == "romance"
    assert svc._model_key("en") is None
    assert svc._model_key("ru") is None


def test_english_or_unknown_passthrough():
    svc = TranslationService()
    r = svc.translate("hello, the production server is down")
    assert r["translation_applied"] is False
    assert r["translated_text"] == r["original_text"]
    assert r["detected_language"] in {"en", "unknown"}


def test_unsupported_language_passthrough():
    svc = TranslationService()
    r = svc.translate("whatever text", detected_lang="ru")
    assert r["translation_applied"] is False
    assert r["translated_text"] == "whatever text"


def test_empty_text_passthrough():
    svc = TranslationService()
    r = svc.translate("   ")
    assert r["translation_applied"] is False


def test_cache_translates_once(monkeypatch):
    svc = TranslationService()
    calls = {"n": 0}

    def fake_translate(text, lang, key):
        calls["n"] += 1
        return "the server is down"

    monkeypatch.setattr(svc, "_translate_with_model", fake_translate)
    first = svc.translate("el servidor esta caido", detected_lang="es")
    second = svc.translate("el servidor esta caido", detected_lang="es")
    assert first["translation_applied"] is True
    assert first["translated_text"] == "the server is down"
    assert second["translated_text"] == "the server is down"
    assert calls["n"] == 1  # second call served from cache


def test_model_error_falls_back_to_passthrough(monkeypatch):
    svc = TranslationService()

    def boom(text, lang, key):
        raise RuntimeError("no model available")

    monkeypatch.setattr(svc, "_translate_with_model", boom)
    r = svc.translate("el servidor esta caido", detected_lang="es")
    assert r["translation_applied"] is False
    assert r["translated_text"] == "el servidor esta caido"
    assert r["error"]


def test_detect_language_english():
    pytest.importorskip("langdetect")
    svc = TranslationService()
    assert svc.detect_language("This is clearly an English sentence about servers.") == "en"
