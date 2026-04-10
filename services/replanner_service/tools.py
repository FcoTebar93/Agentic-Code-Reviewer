from __future__ import annotations

from typing import Any

import httpx
from pydantic import Field

from shared.tools import ToolDefinition, ToolInput, ToolRegistry


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


class FailurePatternsInput(ToolInput):
    module_prefix: str | None = Field(
        default=None,
        description="Prefijo de módulo/carpeta para filtrar (por ejemplo 'services/dev_service')",
    )
    limit: int = Field(
        default=200,
        ge=10,
        le=1000,
        description="Máximo de eventos base a considerar al construir patrones",
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


async def failure_patterns_tool(
    args: FailurePatternsInput,
    base_url: str,
) -> dict[str, Any]:
    """
    Wrapper sobre /patterns/failures del memory_service para el replanner.
    Opcionalmente filtra por prefijo de módulo en el cliente.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.get(
            "/patterns/failures",
            params={"limit": args.limit},
        )
        resp.raise_for_status()
        data = resp.json()

    patterns = data.get("patterns") or []
    if args.module_prefix:
        prefix = args.module_prefix.replace("\\", "/").lower()
        patterns = [
            p
            for p in patterns
            if isinstance(p, dict)
            and str(p.get("module", "")).replace("\\", "/").lower().startswith(prefix)
        ]
    return {"patterns": patterns}


def build_replanner_tool_registry(memory_service_url: str) -> ToolRegistry:
    """
    Construye un ToolRegistry con herramientas de memoria especializadas para el replanner.
    """
    registry = ToolRegistry()

    async def _semantic_outcome_wrapper(args: SemanticOutcomeInput) -> dict[str, Any]:
        return await semantic_outcome_memory_tool(args, base_url=memory_service_url)

    async def _failure_patterns_wrapper(args: FailurePatternsInput) -> dict[str, Any]:
        return await failure_patterns_tool(args, base_url=memory_service_url)

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

    registry.register(
        ToolDefinition(
            name="failure_patterns",
            description="Recuperar patrones históricos de fallos (qa.failed, security.blocked) agregados por módulo",
            input_model=FailurePatternsInput,
            func=_failure_patterns_wrapper,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["memory", "patterns"],
        )
    )

    return registry

