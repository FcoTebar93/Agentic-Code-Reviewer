"""
Límites explícitos para bucles de herramientas: llamadas, tokens por bucle y por plan.

Usa Redis (opcional) para acumular tokens de bucles por plan_id entre tareas.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolLoopBudget:
    """0 en max_tool_calls / max_tokens_loop / max_tokens_plan = sin límite."""

    max_steps: int
    max_tool_calls: int = 0
    max_tokens_loop: int = 0
    max_tokens_plan: int = 0


def tool_loop_budget_from_env(max_steps: int) -> ToolLoopBudget:
    return ToolLoopBudget(
        max_steps=max_steps,
        max_tool_calls=int(os.environ.get("ADMADC_TOOL_LOOP_MAX_TOOL_CALLS", "48")),
        max_tokens_loop=int(os.environ.get("ADMADC_TOOL_LOOP_MAX_TOKENS_PER_LOOP", "0")),
        max_tokens_plan=int(os.environ.get("ADMADC_PLAN_TOOL_LOOP_MAX_TOKENS", "0")),
    )


def loop_tokens_exceeds_budget(total_pt: int, total_ct: int, max_tokens_loop: int) -> bool:
    if max_tokens_loop <= 0:
        return False
    return (total_pt + total_ct) > max_tokens_loop


def tool_calls_exceeds_budget(tool_calls: int, max_tool_calls: int) -> bool:
    if max_tool_calls <= 0:
        return False
    return tool_calls > max_tool_calls


async def plan_tool_loop_try_add_tokens(
    redis_url: str | None,
    plan_id: str | None,
    delta: int,
    cap: int,
) -> bool:
    """
    Acumula tokens de bucle para el plan. Devuelve False si superaría cap (no suma).
    Sin redis, plan_id vacío o cap<=0: siempre True.
    """
    if cap <= 0 or not redis_url or not plan_id or delta <= 0:
        return True
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning("redis no disponible; se omite presupuesto de tokens por plan")
        return True

    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        key = f"admadc:plan:{plan_id}:tool_loop_tokens"
        new_val = await r.incrby(key, delta)
        if new_val == delta:
            await r.expire(key, int(os.environ.get("ADMADC_PLAN_TOKEN_BUDGET_TTL_SEC", "604800")))
        if new_val > cap:
            await r.incrby(key, -delta)
            return False
        return True
    except Exception:
        logger.exception("plan_tool_loop_try_add_tokens falló; se permite el bucle")
        return True
    finally:
        close = getattr(r, "aclose", None) or getattr(r, "close", None)
        if close:
            await close()


def semantic_index_dedup_key(text: str) -> str:
    h = hashlib.sha256(text.strip()[:8000].encode("utf-8", errors="replace")).hexdigest()
    return f"admadc:semantic_idx_dedup:{h}"
