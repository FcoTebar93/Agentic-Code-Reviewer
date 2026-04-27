"""Q&A over the pipeline knowledge base (semantic memory + optional plan events)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.llm_adapter import LLMProvider
from shared.prompt_locale import natural_language_rules_for_locale

logger = logging.getLogger(__name__)

ASK_AGENT_USER_TEMPLATE = """You are an ADMADC assistant. Answer the user's question using ONLY the CONTEXT below
(semantic memories from the pipeline knowledge base and, when provided, recent events for a specific plan).

Rules:
- If the context is insufficient, say so clearly and suggest what would help (e.g. run a plan first, or pass a plan_id).
- Do not invent file paths, metrics, or events that are not supported by the context.
- Be concise. Use short bullets when comparing several items.
- When you give engineering guidance, keep the same professional bar as the rest of the pipeline: actionable steps grounded in the context, clear boundaries (validation, errors, tests) when relevant, and no recommendations to disable security controls, ignore QA, or use dangerous shortcuts (e.g. eval, silent exception swallowing) unless the context explicitly calls for an exception and you state the risk.

RESPONSE LANGUAGE:
{response_language_rules}

CONTEXT — SEMANTIC MEMORY (retrieved snippets, highest relevance first):
{semantic_block}

CONTEXT — RECENT EVENTS (this plan only, if any):
{events_block}

USER QUESTION:
{question}
"""


async def _post_semantic_search(
    client: httpx.AsyncClient,
    *,
    query: str,
    plan_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        resp = await client.post(
            "/semantic/search",
            json={
                "query": query,
                "plan_id": plan_id,
                "event_types": [],
                "limit": limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("results") or []
        return raw if isinstance(raw, list) else []
    except Exception:
        logger.exception("ask_agent: semantic search failed")
        return []


async def _get_plan_events(
    client: httpx.AsyncClient,
    *,
    plan_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        resp = await client.get(
            "/events",
            params={"plan_id": plan_id, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        logger.exception("ask_agent: list events failed for plan %s", plan_id[:8])
        return []


def _format_semantic_block(results: list[dict[str, Any]], max_chars: int = 6000) -> tuple[str, list[dict[str, Any]]]:
    lines: list[str] = []
    sources: list[dict[str, Any]] = []
    for i, item in enumerate(results, 1):
        payload = item.get("payload") or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            continue
        etype = str(payload.get("event_type", ""))
        pid = str(payload.get("plan_id", ""))
        score = float(item.get("heuristic_score", item.get("score", 0.0)) or 0.0)
        preview = text[:500] + ("…" if len(text) > 500 else "")
        lines.append(f"[{i}] type={etype} plan_id={pid or '—'} score={score:.3f}\n{preview}\n")
        sources.append(
            {
                "rank": i,
                "id": str(item.get("id", "")),
                "score": float(item.get("score", 0.0) or 0.0),
                "heuristic_score": score,
                "event_type": etype,
                "plan_id": pid,
                "text_preview": preview,
            }
        )
    block = "\n".join(lines).strip() or "(No semantic hits — the knowledge base may be empty or the query did not match indexed memories.)"
    if len(block) > max_chars:
        block = block[:max_chars] + "\n…(truncated)"
    return block, sources


def _format_events_block(events: list[dict[str, Any]], max_items: int = 12, max_chars: int = 4000) -> str:
    lines: list[str] = []
    for ev in events[:max_items]:
        etype = str(ev.get("event_type", ""))
        ts = str(ev.get("created_at", ""))[:19]
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        summary = ""
        if isinstance(payload, dict):
            if "reasoning" in payload and str(payload.get("reasoning", "")).strip():
                summary = str(payload.get("reasoning", ""))[:200].replace("\n", " ")
            elif "issues" in payload:
                summary = str(payload.get("issues", ""))[:200]
        lines.append(f"- {ts} [{etype}] {summary}")
    block = "\n".join(lines).strip()
    if not block:
        return "(No events loaded for this plan — omit plan_id to search global semantic memory only.)"
    if len(block) > max_chars:
        return block[:max_chars] + "\n…(truncated)"
    return block


async def run_ask_agent(
    llm: LLMProvider,
    *,
    memory_client: httpx.AsyncClient,
    question: str,
    plan_id: str | None,
    user_locale: str = "en",
    semantic_limit: int = 10,
    events_limit: int = 20,
) -> tuple[str, list[dict[str, Any]], int, int]:
        """Returns (answer_markdown_plain, sources, prompt_tokens, completion_tokens)."""
    q = (question or "").strip()
    if not q:
        return (
            "Please provide a non-empty question.",
            [],
            0,
            0,
        )

    semantic_raw = await _post_semantic_search(
        memory_client,
        query=q,
        plan_id=plan_id,
        limit=semantic_limit,
    )
    semantic_block, sources = _format_semantic_block(semantic_raw)

    events_block = "(No plan_id — skipping plan-scoped event timeline.)"
    if plan_id and plan_id.strip():
        evs = await _get_plan_events(
            memory_client,
            plan_id=plan_id.strip(),
            limit=events_limit,
        )
        events_block = _format_events_block(evs)

    rules = natural_language_rules_for_locale(user_locale)
    prompt = ASK_AGENT_USER_TEMPLATE.format(
        response_language_rules=rules,
        semantic_block=semantic_block,
        events_block=events_block,
        question=q,
    )

    resp = await llm.generate_text(prompt)
    pt = resp.prompt_tokens or 0
    ct = resp.completion_tokens or 0
    answer = (resp.content or "").strip() or "(Empty model response.)"
    return answer, sources, pt, ct
