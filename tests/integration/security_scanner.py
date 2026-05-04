"""Scanner de seguridad: reglas regex sin bandit/semgrep (rápido y estable en CI)."""

from __future__ import annotations

import pytest

from services.security_service.config import SecurityConfig
from services.security_service.scanner import scan_files

pytestmark = [pytest.mark.integration]


def _cfg_no_subprocess() -> SecurityConfig:
    return SecurityConfig(
        rabbitmq_url="amqp://unused",
        memory_service_url="http://unused",
        log_level="INFO",
        redis_url="redis://unused",
        agent_name="test",
        agent_goal="test",
        strategy="test",
        enable_bandit=False,
        enable_semgrep=False,
    )


def test_scan_blocks_dangerous_eval() -> None:
    cfg = _cfg_no_subprocess()
    files = [
        {
            "file_path": "bad.py",
            "code": "x = eval('1+1')\n",
            "language": "python",
            "reasoning": "",
        }
    ]
    r = scan_files(files, cfg)
    assert r.approved is False
    assert r.files_scanned == 1
    assert any("dangerous_eval" in v for v in r.violations)


def test_scan_blocks_hardcoded_password_literal() -> None:
    cfg = _cfg_no_subprocess()
    files = [
        {
            "file_path": "secrets.py",
            "code": 'password = "super_secret_password_here"\n',
            "language": "python",
            "reasoning": "",
        }
    ]
    r = scan_files(files, cfg)
    assert r.approved is False
    assert any("hardcoded_password" in v for v in r.violations)


def test_scan_passes_safe_stub_code() -> None:
    cfg = _cfg_no_subprocess()
    files = [
        {
            "file_path": "ok.py",
            "code": (
                "from __future__ import annotations\n\n"
                "def hello() -> None:\n"
                '    """Hi."""\n'
                "    pass\n"
            ),
            "language": "python",
            "reasoning": "",
        }
    ]
    r = scan_files(files, cfg)
    assert r.approved is True
    assert r.violations == []
