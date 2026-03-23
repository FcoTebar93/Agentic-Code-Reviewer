"""
Reintento automático cuando el parseo de la salida del LLM falla (formato roto).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from shared.llm_adapter import LLMProvider
from shared.llm_adapter.models import LLMRequest, LLMResponse
from shared.observability.metrics import llm_tokens

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def generate_text_with_parse_retry(
    llm: LLMProvider,
    *,
    initial_prompt: str,
    repair_instruction: str,
    parse: Callable[[str], tuple[T | None, bool]],
    service_name: str,
    max_attempts: int = 2,
    response_format: dict[str, Any] | None = None,
) -> tuple[T, int, int]:
    """
    Llama al LLM hasta max_attempts veces. `parse` devuelve (valor, ok).
    Si ok es False, se reintenta anteponiendo repair_instruction al prompt original.
    """
    total_pt = 0
    total_ct = 0
    last_raw = ""
    for attempt in range(max(1, max_attempts)):
        prompt = initial_prompt if attempt == 0 else f"{initial_prompt}\n\n{repair_instruction}"
        if attempt > 0 and last_raw.strip():
            prompt = (
                f"{prompt}\n\n---\nTu respuesta anterior no cumplió el formato exigido. "
                f"Corrige y vuelve a responder completo.\nRespuesta inválida (truncada):\n"
                f"{last_raw[:2500]}"
            )
        req = LLMRequest(
            prompt=prompt,
            temperature=0.0,
            response_format=response_format,
        )
        response: LLMResponse = await llm.generate(req)
        pt = response.prompt_tokens or 0
        ct = response.completion_tokens or 0
        total_pt += pt
        total_ct += ct
        if pt or ct:
            llm_tokens.labels(service=service_name, direction="prompt").inc(pt)
            llm_tokens.labels(service=service_name, direction="completion").inc(ct)
        last_raw = response.content or ""
        value, ok = parse(last_raw)
        if ok and value is not None:
            return value, total_pt, total_ct
        logger.warning(
            "parse_retry intento %d/%d falló para %s",
            attempt + 1,
            max_attempts,
            service_name,
        )

    value, _ok = parse(last_raw)
    if value is not None:
        return value, total_pt, total_ct
    raise RuntimeError(f"{service_name}: parse_retry agotado sin resultado válido")
