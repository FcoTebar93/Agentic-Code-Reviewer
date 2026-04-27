from __future__ import annotations

import os

_TRUE_VALUES = {"1", "true", "yes"}


def env_str(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise KeyError(key)
    return value


def env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


def env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, str(default)))


def env_bool(key: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.environ.get(key, fallback).lower() in _TRUE_VALUES
