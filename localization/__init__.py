"""AetherOS Localization Module   Multi-language support for GUI and CLI.

Supported Languages:
    - English (en)   Default
    - Hindi (hi)    
    - Spanish (es)   Espa ol
"""
from localization.i18n import (
    I18nManager,
    LocaleRegistry,
    TranslationLoader,
    LanguageCode,
    TranslationEntry,
    PluralRules,
    FormattedMessage,
)
from localization.locale_data import TRANSLATIONS

__all__ = [
    "I18nManager", "LocaleRegistry", "TranslationLoader",
    "LanguageCode", "TranslationEntry", "PluralRules",
    "FormattedMessage", "TRANSLATIONS",
]
