from __future__ import annotations

from typing import Any

from shared.prompt_locale import normalize_user_locale

_SUPPORTED = {"es", "en"}

_ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "upstream_empty_response": {
        "es": "El servicio remoto devolvió una respuesta vacía.",
        "en": "The upstream service returned an empty response.",
    },
    "invalid_upstream_response": {
        "es": "El servicio remoto devolvió una respuesta inválida.",
        "en": "The upstream service returned an invalid response.",
    },
    "gateway_proxy_failed": {
        "es": "No se pudo completar la petición contra el servicio remoto.",
        "en": "The request to the upstream service could not be completed.",
    },
    "invalid_plan_revision_payload": {
        "es": "La solicitud de replan no es válida.",
        "en": "The replan request payload is invalid.",
    },
    "approval_auth_token_missing": {
        "es": "La autenticación de aprobaciones está activada pero no tiene token configurado.",
        "en": "Approvals authentication is enabled but the token is not configured.",
    },
    "forbidden": {
        "es": "No tienes permisos para realizar esta acción.",
        "en": "You do not have permission to perform this action.",
    },
    "approval_rate_limited": {
        "es": "Se han realizado demasiadas solicitudes de aprobación en poco tiempo.",
        "en": "Too many approval requests were made in a short period of time.",
    },
    "approval_not_found_or_decided": {
        "es": "La aprobación indicada no existe o ya fue resuelta.",
        "en": "The requested approval does not exist or has already been decided.",
    },
    "not_found": {
        "es": "No se encontró el recurso solicitado.",
        "en": "The requested resource was not found.",
    },
    "failed_to_fetch_events": {
        "es": "No se pudieron recuperar los eventos del plan.",
        "en": "Failed to fetch plan events.",
    },
    "plan_execution_failed": {
        "es": "La ejecución del plan ha fallado.",
        "en": "Plan execution failed.",
    },
    "llm_rate_limited": {
        "es": "Se ha alcanzado el límite de uso del proveedor LLM. Espera unos minutos o cambia de proveedor.",
        "en": "The LLM provider rate limit has been reached. Wait a few minutes or switch providers.",
    },
    "service_not_ready": {
        "es": "El servicio todavía no está listo.",
        "en": "The service is not ready yet.",
    },
    "question_required": {
        "es": "La pregunta no puede estar vacía.",
        "en": "The question must not be empty.",
    },
    "agent_ask_failed": {
        "es": "La consulta al agente ha fallado.",
        "en": "The agent query failed.",
    },
    "store_not_initialized": {
        "es": "El almacén todavía no está inicializado.",
        "en": "The store is not initialized yet.",
    },
    "key_not_found": {
        "es": "No se ha encontrado la clave solicitada.",
        "en": "The requested key could not be found.",
    },
}

_EXACT_MESSAGE_CODES: dict[str, str] = {
    "Approvals auth enabled but token is not configured": "approval_auth_token_missing",
    "Forbidden": "forbidden",
    "Too many approval requests": "approval_rate_limited",
    "Not found": "not_found",
    "Failed to fetch events": "failed_to_fetch_events",
    "Plan execution failed": "plan_execution_failed",
    "Service not ready": "service_not_ready",
    "question must be non-empty": "question_required",
    "Agent ask failed": "agent_ask_failed",
    "Store not initialized": "store_not_initialized",
    "Key not found": "key_not_found",
}


def resolve_request_locale(accept_language: Any) -> str:
    if not isinstance(accept_language, str) or not accept_language.strip():
        return "es"
    first = accept_language.split(",", 1)[0].strip()
    normalized = normalize_user_locale(first)
    if normalized in _SUPPORTED:
        return normalized
    return "es"


def error_code_from_message(message: str | None) -> str | None:
    if not message:
        return None
    raw = message.strip()
    if raw in _EXACT_MESSAGE_CODES:
        return _EXACT_MESSAGE_CODES[raw]
    if raw.startswith("Límite de uso del LLM alcanzado"):
        return "llm_rate_limited"
    if raw.lower().startswith("llm rate limit reached"):
        return "llm_rate_limited"
    if raw.startswith("Approval ") and raw.endswith(" not found or already decided"):
        return "approval_not_found_or_decided"
    if raw.startswith("Invalid PlanRevisionPayload:"):
        return "invalid_plan_revision_payload"
    return None


def localize_error_message(
    code: str | None,
    locale: str,
    *,
    fallback: str | None = None,
) -> str:
    if not code:
        return fallback or ""
    by_locale = _ERROR_MESSAGES.get(code, {})
    return by_locale.get(locale) or by_locale.get("es") or fallback or code


def build_localized_error_payload(
    *,
    locale: str,
    code: str | None = None,
    message: str | None = None,
    status: int | None = None,
    field: str = "error",
    params: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    resolved_code = code or error_code_from_message(message)
    translated = localize_error_message(resolved_code, locale, fallback=message)
    payload: dict[str, Any] = {field: translated}
    if resolved_code:
        payload["code"] = resolved_code
    if params:
        payload["params"] = params
    if status is not None:
        payload["status"] = status
    payload.update(extra)
    return payload


def normalize_error_content(content: Any, locale: str) -> Any:
    if not isinstance(content, dict):
        return content

    field: str | None = None
    message: str | None = None
    params = content.get("params")
    if not isinstance(params, dict):
        params = None

    if isinstance(content.get("error"), str) and content["error"].strip():
        field = "error"
        message = str(content["error"]).strip()
    elif isinstance(content.get("detail"), str) and content["detail"].strip():
        field = "detail"
        message = str(content["detail"]).strip()
    elif isinstance(content.get("message"), str) and content["message"].strip():
        field = "message"
        message = str(content["message"]).strip()

    code = content.get("code") if isinstance(content.get("code"), str) else None
    resolved_code = code or error_code_from_message(message)
    if not resolved_code or not field:
        return content

    normalized = dict(content)
    normalized[field] = localize_error_message(
        resolved_code,
        locale,
        fallback=message,
    )
    normalized["code"] = resolved_code
    if params:
        normalized["params"] = params
    return normalized
