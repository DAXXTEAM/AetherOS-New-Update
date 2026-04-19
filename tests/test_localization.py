"""Tests for AetherOS Localization System."""
import pytest
from localization.i18n import (
    I18nManager, LocaleRegistry, TranslationLoader,
    LanguageCode, TranslationEntry, PluralRules, FormattedMessage,
)
from localization.locale_data import TRANSLATIONS


class TestLanguageData:
    def test_english_translations_exist(self):
        assert "en" in TRANSLATIONS
        assert len(TRANSLATIONS["en"]) > 50

    def test_hindi_translations_exist(self):
        assert "hi" in TRANSLATIONS
        assert len(TRANSLATIONS["hi"]) > 50

    def test_spanish_translations_exist(self):
        assert "es" in TRANSLATIONS
        assert len(TRANSLATIONS["es"]) > 50

    def test_all_languages_have_same_keys(self):
        en_keys = set(TRANSLATIONS["en"].keys())
        hi_keys = set(TRANSLATIONS["hi"].keys())
        es_keys = set(TRANSLATIONS["es"].keys())
        assert en_keys == hi_keys == es_keys


class TestI18nManager:
    def test_default_locale(self):
        i18n = I18nManager()
        assert i18n.current_locale == LanguageCode.ENGLISH

    def test_translate_english(self):
        i18n = I18nManager()
        text = i18n.t("welcome_message")
        assert "AetherOS" in text

    def test_translate_hindi(self):
        i18n = I18nManager()
        i18n.set_locale(LanguageCode.HINDI)
        text = i18n.t("welcome_message")
        assert " " in text

    def test_translate_spanish(self):
        i18n = I18nManager()
        i18n.set_locale(LanguageCode.SPANISH)
        text = i18n.t("welcome_message")
        assert "Bienvenido" in text

    def test_missing_key_returns_key(self):
        i18n = I18nManager()
        result = i18n.t("nonexistent_key_xyz")
        assert result == "nonexistent_key_xyz"

    def test_switch_locale(self):
        i18n = I18nManager()
        i18n.set_locale(LanguageCode.HINDI)
        assert i18n.current_locale == LanguageCode.HINDI
        i18n.set_locale(LanguageCode.SPANISH)
        assert i18n.current_locale == LanguageCode.SPANISH

    def test_locale_observer(self):
        i18n = I18nManager()
        changes = []
        i18n.register_locale_observer(lambda lang: changes.append(lang))
        i18n.set_locale(LanguageCode.HINDI)
        assert len(changes) == 1
        assert changes[0] == LanguageCode.HINDI

    def test_stats(self):
        i18n = I18nManager()
        stats = i18n.stats
        assert stats["current_locale"] == "en"
        assert "en" in stats["available_locales"]

    def test_add_runtime_translations(self):
        i18n = I18nManager()
        i18n.add_translations("en", {"custom_key": "Custom Value"})
        assert i18n.t("custom_key") == "Custom Value"


class TestLocaleRegistry:
    def test_list_locales(self):
        reg = LocaleRegistry()
        locales = reg.list_locales()
        assert len(locales) == 3
        codes = [l["code"] for l in locales]
        assert "en" in codes
        assert "hi" in codes
        assert "es" in codes

    def test_format_number_english(self):
        reg = LocaleRegistry()
        result = reg.format_number(1234567, LanguageCode.ENGLISH)
        assert "," in result

    def test_format_number_spanish(self):
        reg = LocaleRegistry()
        result = reg.format_number(1234567, LanguageCode.SPANISH)
        assert "." in result


class TestPluralRules:
    def test_english_plural(self):
        assert PluralRules.get_form(1, LanguageCode.ENGLISH) == "one"
        assert PluralRules.get_form(2, LanguageCode.ENGLISH) == "other"
        assert PluralRules.get_form(0, LanguageCode.ENGLISH) == "other"

    def test_hindi_plural(self):
        assert PluralRules.get_form(0, LanguageCode.HINDI) == "one"
        assert PluralRules.get_form(1, LanguageCode.HINDI) == "one"
        assert PluralRules.get_form(2, LanguageCode.HINDI) == "other"


class TestFormattedMessage:
    def test_format(self):
        msg = FormattedMessage(template="Hello {name}!", params={"name": "World"})
        assert msg.format() == "Hello World!"

    def test_no_params(self):
        msg = FormattedMessage(template="Static text")
        assert msg.format() == "Static text"
