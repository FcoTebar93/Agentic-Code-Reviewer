from __future__ import annotations

from typing import Any

import httpx
from pydantic import Field

from shared.tools import ToolInput, ToolDefinition, ToolRegistry


class SemanticOutcomeInput(ToolInput):
    plan_id: str = Field(
        description="Identificador del plan cuyas salidas queremos analizar",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Máximo de memorias a devolver",
    )


async def semantic_outcome_memory_tool(
    args: SemanticOutcomeInput,
    base_url: str,
) -> dict[str, Any]:
    """
    Recupera memorias semánticas relevantes para un plan concreto centradas
    en resultados de pipeline, fallos de QA y bloqueos de seguridad.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.post(
            "/semantic/search",
            json={
                "query": f"Outcome summary and reasoning for plan {args.plan_id}",
                "plan_id": args.plan_id,
                "event_types": [
                    "pipeline.conclusion",
                    "qa.failed",
                    "security.blocked",
                ],
                "limit": args.limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"results": data.get("results", [])}


def build_replanner_tool_registry(memory_service_url: str) -> ToolRegistry:
    """
    Construye un ToolRegistry con herramientas de memoria especializadas para el replanner.
    """
    registry = ToolRegistry()

    async def _semantic_outcome_wrapper(args: SemanticOutcomeInput) -> dict[str, Any]:
        return await semantic_outcome_memory_tool(args, base_url=memory_service_url)

    registry.register(
        ToolDefinition(
            name="semantic_outcome_memory",
            description="Obtener memorias semánticas sobre outcomes (QA/seguridad/conclusiones) para un plan",
            input_model=SemanticOutcomeInput,
            func=_semantic_outcome_wrapper,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["memory", "semantic", "outcome"],
        )
    )

    return registry

