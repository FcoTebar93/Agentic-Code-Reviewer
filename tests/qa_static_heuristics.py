from services.qa_service.reviewer import _heuristic_suspicious_snippets


def test_secrets_heuristic_does_not_flag_env_reads() -> None:
    code = """
import os

API_KEY = os.environ.get("OPENAI_API_KEY")
PASSWORD = os.getenv("DB_PASSWORD", "")
"""
    issues = _heuristic_suspicious_snippets(code, user_locale="en")
    assert not any("Possible secrets" in issue for issue in issues)


def test_secrets_heuristic_flags_hardcoded_secret_assignment() -> None:
    code = """
API_KEY = "sk-this-is-hardcoded"
settings = {"password": "supersecret123"}
"""
    issues = _heuristic_suspicious_snippets(code, user_locale="en")
    assert any("Possible secrets" in issue for issue in issues)
