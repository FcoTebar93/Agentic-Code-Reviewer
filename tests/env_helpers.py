"""Helpers `shared.utils.env` (lectura tipada de variables de entorno)."""

from __future__ import annotations

import pytest

from shared.utils.env import env_bool, env_float, env_int, env_str


def test_env_str_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMADC_TEST_ENV_STR", "hello")
    assert env_str("ADMADC_TEST_ENV_STR") == "hello"


def test_env_str_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMADC_TEST_ENV_STR_MISSING", raising=False)
    with pytest.raises(KeyError):
        env_str("ADMADC_TEST_ENV_STR_MISSING")


def test_env_str_default_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMADC_TEST_ENV_STR_DEF", raising=False)
    assert env_str("ADMADC_TEST_ENV_STR_DEF", default="fallback") == "fallback"


def test_env_int_and_float(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMADC_TEST_ENV_INT", "7")
    monkeypatch.setenv("ADMADC_TEST_ENV_FLOAT", "3.5")
    assert env_int("ADMADC_TEST_ENV_INT", default=0) == 7
    assert env_float("ADMADC_TEST_ENV_FLOAT", default=0.0) == 3.5


def test_env_bool_truthy_and_falsey(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMADC_TEST_ENV_BOOL_T", "TRUE")
    monkeypatch.setenv("ADMADC_TEST_ENV_BOOL_F", "0")
    assert env_bool("ADMADC_TEST_ENV_BOOL_T") is True
    assert env_bool("ADMADC_TEST_ENV_BOOL_F") is False


def test_env_bool_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMADC_TEST_ENV_BOOL_ABSENT", raising=False)
    assert env_bool("ADMADC_TEST_ENV_BOOL_ABSENT", default=True) is True
    assert env_bool("ADMADC_TEST_ENV_BOOL_ABSENT", default=False) is False
