"""AetherOS Localization — Internationalization Engine.

Provides translation management, plural rule handling, message formatting,
and dynamic locale switching for the entire AetherOS interface.
"""
from __future__ import annotations

import enum
import json
import logging
import os
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("localization.i18n")


class LanguageCode(enum.Enum):
    """Supported language codes."""
    ENGLISH = "en"
    HINDI = "hi"
    SPANISH = "es"


@dataclass
class TranslationEntry:
    """A single translation entry with context and plural forms."""
    key: str
    value: str
    context: str = ""
    plural_forms: Dict[str, str] = field(default_factory=dict)
    description: str = ""

    def get_plural(self, count: int, lang: LanguageCode = LanguageCode.ENGLISH) -> str:
        """Get the correct plural form for a count."""
        if not self.plural_forms:
            return self.value
        form = PluralRules.get_form(count, lang)
        return self.plural_forms.get(form, self.value)


class PluralRules:
    """Plural rules for supported languages."""

    @staticmethod
    def get_form(count: int, lang: LanguageCode) -> str:
        """Get the plural form name for a count in a language."""
        if lang == LanguageCode.ENGLISH:
            return "one" if count == 1 else "other"
        elif lang == LanguageCode.HINDI:
            return "one" if count in (0, 1) else "other"
        elif lang == LanguageCode.SPANISH:
            return "one" if count == 1 else "other"
        return "other"


@dataclass
class FormattedMessage:
    """A message with interpolation support."""
    template: str
    params: Dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        result = self.template
        for key, value in self.params.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


class TranslationLoader:
    """Loads translations from files or dictionaries."""

    def __init__(self, translations_dir: Optional[str] = None):
        self.translations_dir = translations_dir or os.path.join(
            os.path.dirname(__file__), "locale_files"
        )

    def load_from_dict(self, data: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, TranslationEntry]]:
        """Load translations from a nested dictionary."""
        result: Dict[str, Dict[str, TranslationEntry]] = {}
        for lang_code, translations in data.items():
            result[lang_code] = {}
            for key, value in translations.items():
                if isinstance(value, dict):
                    entry = TranslationEntry(
                        key=key,
                        value=value.get("text", ""),
                        plural_forms=value.get("plural", {}),
                        context=value.get("context", ""),
                    )
                else:
                    entry = TranslationEntry(key=key, value=str(value))
                result[lang_code][key] = entry
        return result

    def load_from_json(self, filepath: str) -> Dict[str, TranslationEntry]:
        """Load translations from a JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = {}
            for key, value in data.items():
                if isinstance(value, str):
                    entries[key] = TranslationEntry(key=key, value=value)
                elif isinstance(value, dict):
                    entries[key] = TranslationEntry(
                        key=key,
                        value=value.get("text", ""),
                        plural_forms=value.get("plural", {}),
                    )
            return entries
        except Exception as e:
            logger.error(f"Failed to load translations from {filepath}: {e}")
            return {}


class LocaleRegistry:
    """Registry of available locales and their metadata."""

    LOCALE_INFO = {
        LanguageCode.ENGLISH: {
            "name": "English",
            "native_name": "English",
            "direction": "ltr",
            "date_format": "%Y-%m-%d %H:%M:%S",
            "number_decimal": ".",
            "number_thousands": ",",
        },
        LanguageCode.HINDI: {
            "name": "Hindi",
            "native_name": "हिंदी",
            "direction": "ltr",
            "date_format": "%d-%m-%Y %H:%M:%S",
            "number_decimal": ".",
            "number_thousands": ",",
        },
        LanguageCode.SPANISH: {
            "name": "Spanish",
            "native_name": "Español",
            "direction": "ltr",
            "date_format": "%d/%m/%Y %H:%M:%S",
            "number_decimal": ",",
            "number_thousands": ".",
        },
    }

    def get_info(self, lang: LanguageCode) -> Dict[str, str]:
        return self.LOCALE_INFO.get(lang, self.LOCALE_INFO[LanguageCode.ENGLISH])

    def list_locales(self) -> List[Dict[str, str]]:
        return [
            {"code": lang.value, **info}
            for lang, info in self.LOCALE_INFO.items()
        ]

    def format_date(self, dt: datetime, lang: LanguageCode) -> str:
        info = self.get_info(lang)
        return dt.strftime(info["date_format"])

    def format_number(self, number: Union[int, float], lang: LanguageCode) -> str:
        info = self.get_info(lang)
        if isinstance(number, float):
            int_part, dec_part = str(number).split(".")
            formatted_int = self._add_thousands(int_part, info["number_thousands"])
            return f"{formatted_int}{info['number_decimal']}{dec_part}"
        return self._add_thousands(str(number), info["number_thousands"])

    @staticmethod
    def _add_thousands(s: str, sep: str) -> str:
        result = []
        for i, char in enumerate(reversed(s)):
            if i > 0 and i % 3 == 0 and char != "-":
                result.append(sep)
            result.append(char)
        return "".join(reversed(result))


class I18nManager:
    """Main internationalization manager.

    Central interface for all translation and localization operations.

    Usage:
        i18n = I18nManager()
        i18n.set_locale(LanguageCode.HINDI)
        text = i18n.t("welcome_message")  # Returns Hindi translation
        text = i18n.t("files_count", count=5)  # Handles plurals
    """

    def __init__(self, default_locale: LanguageCode = LanguageCode.ENGLISH):
        self._current_locale = default_locale
        self._fallback_locale = LanguageCode.ENGLISH
        self._translations: Dict[str, Dict[str, TranslationEntry]] = {}
        self._loader = TranslationLoader()
        self._registry = LocaleRegistry()
        self._observers: List[Callable[[LanguageCode], None]] = []
        self._lock = threading.Lock()
        self._missing_keys: Set[str] = set()
        self._load_default_translations()
        logger.info(f"I18nManager initialized with locale: {default_locale.value}")

    def _load_default_translations(self) -> None:
        """Load built-in translations."""
        from localization.locale_data import TRANSLATIONS
        loaded = self._loader.load_from_dict(TRANSLATIONS)
        with self._lock:
            self._translations = loaded

    def set_locale(self, locale: LanguageCode) -> None:
        """Switch the active locale."""
        with self._lock:
            old = self._current_locale
            self._current_locale = locale
        logger.info(f"Locale changed: {old.value} → {locale.value}")
        for observer in self._observers:
            try:
                observer(locale)
            except Exception as e:
                logger.error(f"Locale observer error: {e}")

    @property
    def current_locale(self) -> LanguageCode:
        with self._lock:
            return self._current_locale

    def t(self, key: str, count: Optional[int] = None, **kwargs: Any) -> str:
        """Translate a key to the current locale.

        Args:
            key: Translation key (e.g., "welcome_message")
            count: For plural forms
            **kwargs: Interpolation parameters

        Returns:
            Translated string, or the key itself if not found
        """
        with self._lock:
            locale = self._current_locale
            fallback = self._fallback_locale

        # Try current locale
        entry = self._get_entry(key, locale.value)
        if not entry:
            # Try fallback
            entry = self._get_entry(key, fallback.value)
        if not entry:
            self._missing_keys.add(key)
            return key

        if count is not None:
            text = entry.get_plural(count, locale)
        else:
            text = entry.value

        # Interpolate parameters
        if kwargs:
            for k, v in kwargs.items():
                text = text.replace(f"{{{k}}}", str(v))
            if count is not None:
                text = text.replace("{count}", str(count))

        return text

    def _get_entry(self, key: str, lang_code: str) -> Optional[TranslationEntry]:
        with self._lock:
            lang_translations = self._translations.get(lang_code, {})
            return lang_translations.get(key)

    def add_translations(self, lang_code: str, translations: Dict[str, str]) -> None:
        """Add translations at runtime."""
        with self._lock:
            if lang_code not in self._translations:
                self._translations[lang_code] = {}
            for key, value in translations.items():
                self._translations[lang_code][key] = TranslationEntry(key=key, value=value)

    def get_missing_keys(self) -> Set[str]:
        return set(self._missing_keys)

    def register_locale_observer(self, callback: Callable[[LanguageCode], None]) -> None:
        self._observers.append(callback)

    def format_date(self, dt: datetime) -> str:
        return self._registry.format_date(dt, self._current_locale)

    def format_number(self, number: Union[int, float]) -> str:
        return self._registry.format_number(number, self._current_locale)

    def list_locales(self) -> List[Dict[str, str]]:
        return self._registry.list_locales()

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_locale": self._current_locale.value,
                "available_locales": list(self._translations.keys()),
                "translation_counts": {
                    lang: len(entries) for lang, entries in self._translations.items()
                },
                "missing_keys": len(self._missing_keys),
            }
