"""Políticas de idioma BCP-47 y textos auxiliares para prompts."""

from __future__ import annotations

from shared.prompt_locale import (
    natural_language_rules_for_locale,
    normalize_user_locale,
    qa_hot_module_note,
    qa_memory_section_headers,
    security_memory_context_prefix,
)


def test_normalize_user_locale_primary_tags() -> None:
    assert normalize_user_locale(None) == "en"
    assert normalize_user_locale("") == "en"
    assert normalize_user_locale("   ") == "en"
    assert normalize_user_locale("ES-MX") == "es"
    assert normalize_user_locale("pt_BR") == "pt"
    assert normalize_user_locale("zh-CN") == "zh"


def test_normalize_user_locale_unknown_falls_back_en() -> None:
    assert normalize_user_locale("xx") == "en"
    assert normalize_user_locale("tlh-Klingon") == "en"


def test_natural_language_rules_spanish_vs_english() -> None:
    es = natural_language_rules_for_locale("es")
    en = natural_language_rules_for_locale("en")
    assert "Spanish" in es
    assert "English" in en
    assert es != en


def test_natural_language_rules_german() -> None:
    assert "German" in natural_language_rules_for_locale("de")


def test_qa_memory_section_headers_spanish() -> None:
    recent, repo = qa_memory_section_headers("es")
    assert "MEMORIA" in recent
    assert "REPOSITORIO" in repo


def test_qa_hot_module_note_language_split() -> None:
    assert "zona caliente" in qa_hot_module_note("es", "services/foo").lower()
    assert "hot spot" in qa_hot_module_note("en", "services/foo").lower()


def test_security_memory_context_prefix() -> None:
    assert "Contexto" in security_memory_context_prefix("es")
    assert "historical" in security_memory_context_prefix("en").lower()
