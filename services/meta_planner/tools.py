from __future__ import annotations

from typing import Any

import httpx
from pydantic import Field

from shared.tools import ToolInput, ToolDefinition, ToolRegistry


class SemanticMemoryInput(ToolInput):
    query: str = Field(
        description="Texto de búsqueda semántica (prompt del usuario o resumen)",
    )
    plan_id: str | None = Field(
        default=None,
        description="Filtrar memorias asociadas a un plan_id concreto (opcional)",
    )
    event_types: list[str] = Field(
        default_factory=list,
        description="Lista opcional de tipos de evento a considerar en la búsqueda",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Máximo de memorias a devolver",
    )


class QueryEventsInput(ToolInput):
    event_type: str | None = Field(
        default=None,
        description="Tipo de evento a filtrar (por ejemplo 'plan.created')",
    )
    plan_id: str | None = Field(
        default=None,
        description="Filtrar por plan_id concreto",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Máximo de eventos a devolver",
    )


async def semantic_memory_tool(args: SemanticMemoryInput, base_url: str) -> dict[str, Any]:
    """
    Wrapper de alto nivel sobre /semantic/search del memory_service.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.post(
            "/semantic/search",
            json={
                "query": args.query,
                "plan_id": args.plan_id,
                "event_types": args.event_types,
                "limit": args.limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"results": data.get("results", [])}


async def query_events_tool(args: QueryEventsInput, base_url: str) -> dict[str, Any]:
    """
    Wrapper tipado sobre /events del memory_service.
    """
    params: dict[str, Any] = {"limit": args.limit}
    if args.event_type:
        params["event_type"] = args.event_type
    if args.plan_id:
        params["plan_id"] = args.plan_id

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()
    return {"events": data}


def build_planner_tool_registry(memory_service_url: str) -> ToolRegistry:
    """
    Construye un ToolRegistry con herramientas de memoria para meta_planner.
    """
    registry = ToolRegistry()

    async def _semantic_wrapper(args: SemanticMemoryInput) -> dict[str, Any]:
        return await semantic_memory_tool(args, base_url=memory_service_url)

    async def _events_wrapper(args: QueryEventsInput) -> dict[str, Any]:
        return await query_events_tool(args, base_url=memory_service_url)

    registry.register(
        ToolDefinition(
            name="semantic_search_memory",
            description="Buscar memorias relevantes en el memory_service usando Qdrant",
            input_model=SemanticMemoryInput,
            func=_semantic_wrapper,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["memory", "semantic"],
        )
    )

    registry.register(
        ToolDefinition(
            name="query_events",
            description="Listar eventos recientes desde el memory_service (tipado)",
            input_model=QueryEventsInput,
            func=_events_wrapper,
            timeout_s=10.0,
            max_retries=0,
            sandboxed=True,
            tags=["memory", "events"],
        )
    )

    return registry

