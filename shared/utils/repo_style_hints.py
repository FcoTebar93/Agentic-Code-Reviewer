"""
Compact excerpts from repo root config files for agent prompts (linters, formatters).

Keeps reads small and best-effort: missing files are skipped.
"""

from __future__ import annotations

from pathlib import Path


def _infer_language_from_path(file_path: str) -> str:
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith((".py", ".pyi")):
        return "python"
    if name.endswith((".js", ".jsx", ".mjs", ".cjs")):
        return "javascript"
    if name.endswith((".ts", ".tsx")):
        return "typescript"
    if name.endswith(".java"):
        return "java"
    return ""


def _normalize_language(language: str, file_path: str) -> str:
    raw = (language or "").strip().lower()
    if raw in {"py", "python"}:
        return "python"
    if raw in {"js", "javascript"}:
        return "javascript"
    if raw in {"ts", "typescript"}:
        return "typescript"
    if raw == "java":
        return "java"
    return _infer_language_from_path(file_path).lower()


def _read_truncated(path: Path, max_chars: int) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24].rstrip() + "\n... [truncated]"


def _pyproject_tool_snippet(text: str, max_chars: int) -> str:
    """Prefer [tool.*] sections when present; otherwise head."""
    if not text.strip():
        return ""
    markers = (
        "[tool.ruff]",
        "[tool.black]",
        "[tool.pytest.ini_options]",
        "[tool.mypy]",
    )
    best = -1
    for m in markers:
        idx = text.find(m)
        if idx >= 0 and (best < 0 or idx < best):
            best = idx
    if best >= 0:
        chunk = text[best : best + max_chars]
        if len(chunk) > max_chars:
            chunk = chunk[: max_chars - 24].rstrip() + "\n... [truncated]"
        return chunk
    if len(text) > max_chars:
        return text[: max_chars - 24].rstrip() + "\n... [truncated]"
    return text


def _pyproject_excerpt(path: Path, max_chars: int) -> str | None:
    raw = _read_truncated(path, min(max_chars * 3, 24_000))
    if raw is None:
        return None
    snippet = _pyproject_tool_snippet(raw, max_chars)
    return snippet.strip() or None


def _config_candidates(normalized_lang: str) -> list[tuple[str, int]]:
    shared: list[tuple[str, int]] = [(".editorconfig", 450)]
    if normalized_lang == "python":
        return shared + [
            ("ruff.toml", 700),
            ("pyproject.toml", 900),
            (".flake8", 400),
        ]
    if normalized_lang in {"javascript", "typescript"}:
        return shared + [
            ("package.json", 650),
            ("eslint.config.mjs", 550),
            ("eslint.config.js", 550),
            ("eslint.config.cjs", 550),
            (".eslintrc.json", 550),
            (".eslintrc.cjs", 550),
            (".prettierrc", 350),
            (".prettierrc.json", 350),
        ]
    return shared + [
        ("pyproject.toml", 500),
        ("package.json", 400),
        ("ruff.toml", 400),
    ]


def build_repo_style_hints(
    repo_root: Path | str,
    *,
    language: str = "",
    file_path: str = "",
    max_total_chars: int = 1200,
) -> str:
    """
    Return a single string with truncated config excerpts for LLM context.

    ``language`` may be empty; then it is inferred from ``file_path`` when possible.
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        return ""

    lang = _normalize_language(language, file_path)
    candidates = _config_candidates(lang)

    parts: list[str] = []
    total = 0

    for rel, per_file_limit in candidates:
        if total >= max_total_chars:
            break
        path = root / rel
        if not path.is_file():
            continue

        if rel == "pyproject.toml":
            content = _pyproject_excerpt(path, per_file_limit)
        else:
            content = _read_truncated(path, per_file_limit)
            if content is not None:
                content = content.strip() or None

        if not content:
            continue

        header = f"--- {rel} (truncated) ---"
        block = f"{header}\n{content}\n"
        if total + len(block) > max_total_chars:
            room = max_total_chars - total - len(header) - 30
            if room < 64:
                break
            block = f"{header}\n{content[:room].rstrip()}\n... [truncated]\n"
        parts.append(block)
        total += len(block)

    return "\n".join(parts).strip()
