"""
User-facing natural language for agent prompts.

Prompt templates are written in English. Inject `natural_language_rules_for_locale`
so the model writes prose (reasoning, issues, specs, etc.) in the user's language
while keeping structural labels (REASONING, CODE, VERDICT, TASKS JSON, …) unchanged.
"""

from __future__ import annotations


def normalize_user_locale(raw: str | None) -> str:
    """BCP-47-ish primary tag: en, es, fr, … Default English."""
    if not raw or not str(raw).strip():
        return "en"
    loc = str(raw).strip().lower().replace("_", "-")
    primary = loc.split("-", 1)[0]
    if primary in {"en", "es", "fr", "de", "pt", "it", "ja", "zh", "ko"}:
        return primary
    return "en"


def natural_language_rules_for_locale(locale: str | None) -> str:
    """Paragraph appended to English system/user prompts."""
    loc = normalize_user_locale(locale)
    if loc == "es":
        return (
            "Natural-language policy: Write all explanatory prose (reasoning, issue descriptions, "
            "suggestions, spec narrative, security commentary, bullet details under each section) in Spanish. "
            "Keep structural labels and keywords exactly as specified in this prompt "
            "(e.g. REASONING, CODE, VERDICT, SPEC, TESTS, TASKS JSON keys, SUMMARY)."
        )
    if loc == "fr":
        return (
            "Natural-language policy: Write all explanatory prose in French. "
            "Keep structural labels exactly as specified in this prompt."
        )
    if loc == "de":
        return (
            "Natural-language policy: Write all explanatory prose in German. "
            "Keep structural labels exactly as specified in this prompt."
        )
    if loc == "pt":
        return (
            "Natural-language policy: Write all explanatory prose in Portuguese. "
            "Keep structural labels exactly as specified in this prompt."
        )
    return (
        "Natural-language policy: Write all explanatory prose in English. "
        "Keep structural labels exactly as specified in this prompt."
    )


def qa_memory_section_headers(locale: str | None) -> tuple[str, str]:
    """(recent_memory_title, repo_context_title) including trailing newline."""
    loc = normalize_user_locale(locale)
    if loc == "es":
        return ("MEMORIA RECIENTE DEL PLAN:\n", "CONTEXTO DEL REPOSITORIO:\n")
    return ("RECENT PLAN MEMORY:\n", "REPOSITORY CONTEXT:\n")


def qa_hot_module_note(locale: str | None, module: str) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return (
            f"\n[QA] Esta revisión se aplicó con mayor rigor porque el módulo "
            f"'{module}' aparece como zona caliente en patrones históricos de fallos."
        )
    return (
        f"\n[QA] This review used stricter criteria because module '{module}' "
        "appears as a historical failure hot spot."
    )


def security_memory_context_prefix(locale: str | None) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return "Contexto histórico de seguridad relevante:\n"
    return "Relevant historical security context:\n"
