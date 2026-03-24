"""
Heuristics to flag unusually large rewrites before QA (dev_service).

Deterministic and cheap: line-based similarity, not a full semantic diff.
"""

from __future__ import annotations

import difflib


def large_change_note(
    previous_code: str,
    new_code: str,
    *,
    soft_line_limit: int = 120,
    similarity_warn_below: float = 0.52,
    qa_retry: bool = False,
) -> str | None:
    """
    Return a short English note for reasoning/logs, or None if the change looks proportionate.

    ``qa_retry`` tightens thresholds (expect surgical patches).
    """
    new_lines = new_code.splitlines()
    new_n = len(new_lines)
    soft = min(soft_line_limit, 80) if qa_retry else soft_line_limit
    sim_floor = max(similarity_warn_below, 0.62) if qa_retry else similarity_warn_below

    prev = previous_code or ""
    if not prev.strip():
        if new_n > soft:
            return (
                f"Large new file ({new_n} lines vs empty/non-existent previous; "
                f"soft guideline {soft} lines)."
            )
        return None

    old_lines = prev.splitlines()
    old_n = len(old_lines)
    ratio = difflib.SequenceMatcher(a=old_lines, b=new_lines).ratio()

    if new_n > soft * 2:
        return (
            f"Very large output ({new_n} lines). Consider splitting work or minimising unrelated edits."
        )

    if new_n > soft and ratio < sim_floor:
        return (
            f"Heavy rewrite: {new_n} lines, ~{ratio:.2f} line similarity to previous on disk "
            f"(guideline: stay closer to prior file unless the task requires a full replace)."
        )

    return None
