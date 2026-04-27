from __future__ import annotations


def infer_group_id(file_path: str) -> str:
    """Infer approximate module/group id from file path."""
    norm = (file_path or "").replace("\\", "/").strip()
    if not norm:
        return "root"
    parts = norm.split("/")
    if len(parts) >= 3:
        return "/".join(parts[:3])
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return norm
