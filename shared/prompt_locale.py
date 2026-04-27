"""User-facing natural language for agent prompts."""

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
            "(e.g. REASONING, CODE, VERDICT, SPEC, TESTS, TASKS JSON keys, SUMMARY, DETAILS, REMEDIATIONS)."
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


def qa_hot_module_stm_block(locale: str | None, module: str) -> str:
    """Prefix injected into short-term memory when the file is in a hot module."""
    loc = normalize_user_locale(locale)
    if loc == "es":
        return (
            "MODULO EN ZONA CALIENTE:\n"
            f"- Este archivo pertenece al módulo '{module}', que tiene un historial "
            "de fallos QA/seguridad según los patrones agregados.\n"
            "- Sé más estricto con validaciones de entrada, manejo de errores y "
            "casos borde, y NO aceptes soluciones frágiles aunque parezcan pasar tests simples.\n\n"
        )
    return (
        "HOT-SPOT MODULE:\n"
        f"- This file belongs to module '{module}', which has elevated QA/security failure "
        "rates in aggregated historical patterns.\n"
        "- Apply stricter criteria for input validation, error handling, and edge cases; "
        "do not accept brittle fixes that only pass superficial tests.\n\n"
    )


def qa_static_pattern_security_title(locale: str | None) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return "Patrones estáticos peligrosos detectados antes del QA LLM"
    return "Dangerous static patterns detected before LLM QA"


def qa_heuristic_network_warning(locale: str | None) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return (
            "Suspicious network access detected (HTTP client usage). "
            "Verifica timeouts, validación de entradas y manejo de errores."
        )
    return (
        "Suspicious network access detected (HTTP client usage). "
        "Check timeouts, input validation, and error handling."
    )


def qa_heuristic_fs_warning(locale: str | None) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return (
            "Suspicious filesystem access detected. Comprueba rutas, permisos y riesgos de path traversal."
        )
    return (
        "Suspicious filesystem access detected. Check paths, permissions, and path traversal risks."
    )


def qa_heuristic_secrets_warning(locale: str | None) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return (
            "Possible secrets or environment variable usage detected. "
            "Asegura que no se exponen credenciales ni se registran valores sensibles."
        )
    return (
        "Possible secrets or environment variable usage detected. "
        "Ensure credentials are not exposed or logged."
    )


def qa_synthetic_budget_fail(locale: str | None, kind: str) -> str:
    """Structured QA fallback when tool-loop budgets are exceeded (kind = loop key)."""
    loc = normalize_user_locale(locale)
    if loc == "es":
        es: dict[str, str] = {
            "loop_tokens": (
                "REASONING: Bucle de herramientas QA detenido por límite de tokens del bucle.\n"
                "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
                "  DETAILS: Se superó ADMADC_TOOL_LOOP_MAX_TOKENS_PER_LOOP.\n"
            ),
            "plan_tokens": (
                "REASONING: Bucle de herramientas QA detenido por límite de tokens acumulados del plan.\n"
                "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
                "  DETAILS: Se superó ADMADC_PLAN_TOOL_LOOP_MAX_TOKENS.\n"
            ),
            "tool_calls": (
                "REASONING: Bucle de herramientas QA detenido por límite de llamadas a herramientas.\n"
                "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
                "  DETAILS: Se superó ADMADC_TOOL_LOOP_MAX_TOOL_CALLS.\n"
            ),
            "exhausted": (
                "REASONING: Bucle de herramientas QA agotó el máximo de pasos sin veredicto final.\n"
                "VERDICT: FAIL\nISSUES:\n- [error|functional] exhausted\n"
                "  DETAILS: Aumenta QA_TOOL_LOOP_MAX_STEPS o reduce el alcance.\n"
            ),
        }
        return es.get(kind, es["loop_tokens"])
    en: dict[str, str] = {
        "loop_tokens": (
            "REASONING: QA tool loop stopped: per-loop token budget exceeded.\n"
            "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
            "  DETAILS: ADMADC_TOOL_LOOP_MAX_TOKENS_PER_LOOP was exceeded.\n"
        ),
        "plan_tokens": (
            "REASONING: QA tool loop stopped: plan cumulative token budget exceeded.\n"
            "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
            "  DETAILS: ADMADC_PLAN_TOOL_LOOP_MAX_TOKENS was exceeded.\n"
        ),
        "tool_calls": (
            "REASONING: QA tool loop stopped: tool-call budget exceeded.\n"
            "VERDICT: FAIL\nISSUES:\n- [error|functional] budget_exceeded\n"
            "  DETAILS: ADMADC_TOOL_LOOP_MAX_TOOL_CALLS was exceeded.\n"
        ),
        "exhausted": (
            "REASONING: QA tool loop exhausted max steps without a final verdict.\n"
            "VERDICT: FAIL\nISSUES:\n- [error|functional] exhausted\n"
            "  DETAILS: Increase QA_TOOL_LOOP_MAX_STEPS or narrow scope.\n"
        ),
    }
    return en.get(kind, en["loop_tokens"])


def qa_parse_repair_no_tools_suffix(locale: str | None) -> str:
    loc = normalize_user_locale(locale)
    if loc == "es":
        return " Responde sin herramientas."
    return " Reply without tools."
