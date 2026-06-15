"""Runtime translation service (Phase 3) — langdetect -> MarianMT -> English.

Ported from `Code/MariaMT_translator.ipynb` and made first-class at inference time
(the notebook only translated datasets offline; paper Limitation 5). The routing
pipeline runs on the English translation while the ORIGINAL text is preserved.

Design:
  * langdetect for detection (seeded for determinism);
  * Helsinki-NLP MarianMT: de -> opus-mt-de-en, {es,fr,pt} -> opus-mt-ROMANCE-en
    (with the `>>lang<<` target prefix), 400-word chunking, max_length 512;
  * models load lazily on first non-English ticket (heavy + network);
  * a bounded LRU cache avoids re-translating identical text;
  * English / unsupported / detection-failure / model-error all PASS THROUGH the
    original text (translation_applied=False) so routing never breaks on translation.

Heavy deps (`langdetect`, `transformers`, `torch`, `sentencepiece`) are imported
lazily so this module imports cheaply and the service constructs without them.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from ..core.config import SETTINGS, Settings

_EMAIL_RE = re.compile(r"\S+@\S+")
_URL_RE = re.compile(r"http\S+")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-]{7,}")


def clean_for_detection(text: str) -> str:
    """Strip emails/URLs/phone numbers before language detection (notebook parity)."""
    text = _EMAIL_RE.sub(" ", str(text))
    text = _URL_RE.sub(" ", text)
    text = _PHONE_RE.sub(" ", text)
    return text.strip()


def chunk_text(text: str, max_words: int = 400):
    """Yield successive `max_words`-word chunks (MarianMT input-length guard)."""
    words = text.split()
    for i in range(0, len(words), max_words):
        yield " ".join(words[i : i + max_words])


class TranslationService:
    def __init__(self, settings: Settings = SETTINGS):
        self.settings = settings
        self._tokenizers: dict[str, Any] = {}
        self._models: dict[str, Any] = {}
        self._device: str | None = None
        self._cache: "OrderedDict[tuple[str, str], str]" = OrderedDict()

    # ----------------------------------------------------------- detection
    def detect_language(self, text: str) -> str:
        cleaned = clean_for_detection(text)
        if not cleaned:
            return "unknown"
        try:
            from langdetect import DetectorFactory, detect

            DetectorFactory.seed = 0
            return detect(cleaned)
        except Exception:
            return "unknown"

    def _model_key(self, lang: str) -> str | None:
        if lang == "de":
            return "de"
        if lang in self.settings.translation_romance_langs:
            return "romance"
        return None

    # ----------------------------------------------------------- model load
    def _resolve_device(self) -> str:
        if self._device is None:
            try:
                import torch

                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                self._device = "cpu"
        return self._device

    def _get_model(self, key: str):
        if key not in self._models:
            from transformers import MarianMTModel, MarianTokenizer

            model_name = (
                self.settings.translation_model_de
                if key == "de"
                else self.settings.translation_model_romance
            )
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name).to(self._resolve_device())
            self._tokenizers[key] = tokenizer
            self._models[key] = model
        return self._tokenizers[key], self._models[key]

    # ----------------------------------------------------------- translate
    def _translate_with_model(self, text: str, lang: str, key: str) -> str:
        tokenizer, model = self._get_model(key)
        device = self._resolve_device()
        prepared = f">>{lang}<< {text}" if key == "romance" else text

        translated_chunks = []
        for chunk in chunk_text(prepared, self.settings.translation_max_words):
            inputs = tokenizer(chunk, return_tensors="pt", truncation=True).to(device)
            output = model.generate(**inputs, max_length=self.settings.translation_max_length)
            translated_chunks.append(
                tokenizer.decode(output[0], skip_special_tokens=True)
            )
        return " ".join(translated_chunks).strip()

    def _cache_get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key, value):
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > int(self.settings.translation_cache_size):
            self._cache.popitem(last=False)

    @staticmethod
    def _result(original, lang, translated, applied, model, error=None) -> dict:
        return {
            "original_text": original,
            "detected_language": lang,
            "translated_text": translated,
            "translation_applied": bool(applied),
            "model": model,
            "error": error,
        }

    def translate(self, text: str, detected_lang: str | None = None) -> dict:
        original = str(text)
        if not original.strip():
            return self._result(original, "unknown", original, False, None)

        lang = detected_lang or self.detect_language(original)
        key = self._model_key(lang)
        if lang == "en" or key is None:
            return self._result(original, lang, original, False, None)

        cache_key = (lang, original)
        cached = self._cache_get(cache_key)
        if cached is not None:
            model_name = (
                self.settings.translation_model_de
                if key == "de"
                else self.settings.translation_model_romance
            )
            return self._result(original, lang, cached, True, model_name)

        try:
            translated = self._translate_with_model(original, lang, key)
        except Exception as exc:  # missing deps / network / model error -> passthrough
            return self._result(original, lang, original, False, None, error=str(exc))

        self._cache_put(cache_key, translated)
        model_name = (
            self.settings.translation_model_de
            if key == "de"
            else self.settings.translation_model_romance
        )
        return self._result(original, lang, translated, True, model_name)
