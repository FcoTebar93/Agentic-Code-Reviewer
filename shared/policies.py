from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


Language = Literal["python", "java", "javascript", "typescript", "any"]


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    languages: tuple[Language, ...] = ("any",)
    severity: Severity = Severity.WARNING
    category: Literal["qa", "security"] = "qa"


QA_RULES: list[Rule] = [
    Rule(
        id="TASK_FULFILLMENT",
        description="The code must clearly implement the task description and produce the expected behaviour.",
        languages=("any",),
        severity=Severity.BLOCKER,
        category="qa",
    ),
    Rule(
        id="NO_DEAD_CODE",
        description="Avoid adding unused functions, classes, or modules that are not referenced anywhere.",
        languages=("any",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="NO_OBVIOUS_BUGS",
        description="There must be no obvious runtime bugs such as undefined variables, unreachable code, or inconsistent return types.",
        languages=("any",),
        severity=Severity.BLOCKER,
        category="qa",
    ),
    Rule(
        id="SMALL_FUNCTIONS",
        description="Functions should stay reasonably small and focused; large functions should be highlighted for future refactor.",
        languages=("any",),
        severity=Severity.INFO,
        category="qa",
    ),
    Rule(
        id="MEANINGFUL_NAMES",
        description="Use meaningful names for variables, functions and classes; avoid tmp/foo/bar style naming in new code.",
        languages=("any",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="NO_DUPLICATED_LOGIC",
        description="Avoid copy-pasting the same logic in multiple places; prefer extracting helpers.",
        languages=("any",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="SEPARATION_OF_CONCERNS",
        description="Keep business logic separated from IO/transport concerns where practical.",
        languages=("any",),
        severity=Severity.INFO,
        category="qa",
    ),
    Rule(
        id="ERROR_HANDLING_API",
        description="API endpoints must handle predictable errors (validation, downstream failures) instead of crashing.",
        languages=("python", "java", "javascript", "typescript"),
        severity=Severity.ERROR,
        category="qa",
    ),
    Rule(
        id="NO_SWALLOW_ERRORS",
        description="Do not silently swallow exceptions (empty catch/except) without logging or handling.",
        languages=("any",),
        severity=Severity.ERROR,
        category="qa",
    ),
    Rule(
        id="VALIDATION_FOR_INPUTS",
        description="External inputs (request body, query, path, headers) must be validated at least for basic type/shape.",
        languages=("python", "java", "javascript", "typescript"),
        severity=Severity.ERROR,
        category="qa",
    ),
    Rule(
        id="CONSISTENT_FORMATTING",
        description="Follow consistent formatting and style conventions for the language/framework.",
        languages=("any",),
        severity=Severity.INFO,
        category="qa",
    ),
    Rule(
        id="COMMENTS_FOR_NON_OBVIOUS_LOGIC",
        description="Non-obvious or complex logic should include a short comment explaining the intent.",
        languages=("any",),
        severity=Severity.INFO,
        category="qa",
    ),
    Rule(
        id="NO_DEBUG_PRINTS",
        description="Remove debug prints/logs such as print/console.log/System.out.println from production code.",
        languages=("any",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="BASIC_TESTS_PRESENT",
        description="When adding non-trivial logic, at least one basic test should be added or clearly suggested.",
        languages=("python", "java", "javascript", "typescript"),
        severity=Severity.INFO,
        category="qa",
    ),
    Rule(
        id="PYTHON_PYDANTIC_OR_SCHEMA",
        description="For Python APIs, prefer using Pydantic/models/schemas for request/response instead of untyped dicts.",
        languages=("python",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="JAVA_NULL_SAFETY",
        description="For Java, avoid obvious NullPointerException risks; add null checks or safer types where appropriate.",
        languages=("java",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="JS_TS_ASYNC_ERRORS",
        description="In JS/TS, async code and Promises must handle rejections and errors explicitly.",
        languages=("javascript", "typescript"),
        severity=Severity.ERROR,
        category="qa",
    ),
    Rule(
        id="TS_STRICT_TYPES",
        description="In TypeScript, avoid unnecessary use of `any` in new code, especially in API surfaces.",
        languages=("typescript",),
        severity=Severity.WARNING,
        category="qa",
    ),
    Rule(
        id="NO_HARDCODED_SECRETS_QA",
        description="Do not hardcode secrets, passwords or tokens in code even for examples.",
        languages=("any",),
        severity=Severity.BLOCKER,
        category="qa",
    ),
    Rule(
        id="LOGGING_FOR_CRITICAL_PATHS",
        description="Critical operations (auth, data modification) should have at least minimal logging (without leaking sensitive data).",
        languages=("any",),
        severity=Severity.WARNING,
        category="qa",
    ),
]


SECURITY_RULES: list[Rule] = [
    Rule(
        id="AUTH_REQUIRED_FOR_MUTATIONS",
        description="API endpoints that mutate state (POST/PUT/PATCH/DELETE) must be protected by authentication.",
        languages=("python", "java", "javascript", "typescript"),
        severity=Severity.BLOCKER,
        category="security",
    ),
    Rule(
        id="AUTH_REQUIRED_FOR_SENSITIVE_READS",
        description="Sensitive data reads (user profiles, internal configs, PII) must require authentication.",
        languages=("python", "java", "javascript", "typescript"),
        severity=Severity.ERROR,
        category="security",
    ),
    Rule(
        id="ROLE_OR_SCOPE_CHECKS",
        description="Administrative or high-impact operations must be protected by roles/scopes, not just 'logged-in' checks.",
        languages=("any",),
        severity=Severity.ERROR,
        category="security",
    ),
    Rule(
        id="INPUT_VALIDATION_REQUIRED",
        description="All external input must be validated and sanitised to an appropriate degree.",
        languages=("any",),
        severity=Severity.BLOCKER,
        category="security",
    ),
    Rule(
        id="NO_RAW_SQL_CONCAT",
        description="Do not build SQL queries by string concatenation with user input; use parameters/ORM instead.",
        languages=("python", "java", "javascript", "typescript"),
        severity=Severity.BLOCKER,
        category="security",
    ),
    Rule(
        id="NO_UNSAFE_DESERIALIZATION",
        description="Avoid unsafe deserialization of untrusted data (e.g. Java ObjectInputStream, Python pickle) without strict controls.",
        languages=("python", "java"),
        severity=Severity.BLOCKER,
        category="security",
    ),
    Rule(
        id="NO_STACKTRACE_LEAK",
        description="Do not expose stacktraces or internal error details to API clients.",
        languages=("any",),
        severity=Severity.ERROR,
        category="security",
    ),
    Rule(
        id="SANE_ERROR_MESSAGES",
        description="Error messages must not reveal infrastructure details such as file paths, table names, or raw queries.",
        languages=("any",),
        severity=Severity.WARNING,
        category="security",
    ),
    Rule(
        id="SECURITY_LOGS_FOR_AUTH_EVENTS",
        description="Authentication-related events (login/logout/failures) should be logged in a security-conscious way.",
        languages=("any",),
        severity=Severity.INFO,
        category="security",
    ),
    Rule(
        id="NO_DEBUG_IN_PRODUCTION",
        description="Debug/development modes must not be enabled in production-oriented code paths.",
        languages=("any",),
        severity=Severity.ERROR,
        category="security",
    ),
    Rule(
        id="CORS_RESTRICTED",
        description="CORS for sensitive APIs should not be wide-open (*) without strong justification.",
        languages=("javascript", "typescript", "python", "java"),
        severity=Severity.WARNING,
        category="security",
    ),
    Rule(
        id="HTTPS_ENFORCED_HINT",
        description="APIs intended for production should be deployable behind HTTPS; avoid assumptions of plain HTTP.",
        languages=("any",),
        severity=Severity.INFO,
        category="security",
    ),
    Rule(
        id="NO_HARDCODED_SECRETS_SEC",
        description="Secrets, passwords and tokens must never be hardcoded; they must come from environment/secret management.",
        languages=("any",),
        severity=Severity.BLOCKER,
        category="security",
    ),
    Rule(
        id="NO_SENSITIVE_DATA_IN_LOGS",
        description="Do not log sensitive data such as passwords, tokens, or full personal identifiers.",
        languages=("any",),
        severity=Severity.ERROR,
        category="security",
    ),
    Rule(
        id="JAVA_SPRING_SECURITY_CONFIG",
        description="For Java Spring-based APIs, there should be some form of security configuration (filters, SecurityConfig, or equivalent).",
        languages=("java",),
        severity=Severity.WARNING,
        category="security",
    ),
    Rule(
        id="PYTHON_API_SECURITY",
        description="For Python APIs (FastAPI/Flask/Django), security/authentication mechanisms should be present where appropriate.",
        languages=("python",),
        severity=Severity.WARNING,
        category="security",
    ),
    Rule(
        id="NODE_EXPRESS_SECURITY_MIDDLEWARES",
        description="For Node/Express APIs, recommend use of security middlewares (helmet, rate limiting, body size limits).",
        languages=("javascript", "typescript"),
        severity=Severity.INFO,
        category="security",
    ),
    Rule(
        id="BASIC_RATE_LIMIT_RECOMMENDED",
        description="Public-facing endpoints (especially login/registration) should have some form of rate limiting.",
        languages=("any",),
        severity=Severity.WARNING,
        category="security",
    ),
    Rule(
        id="CSRF_PROTECTION_FOR_STATEFUL_APPS",
        description="Stateful web apps using cookies/sessions should implement CSRF protection for state-changing operations.",
        languages=("any",),
        severity=Severity.WARNING,
        category="security",
    ),
]


def rules_for_language(
    language: str,
    category: Literal["qa", "security"] | None = None,
) -> list[Rule]:
    lang = (language or "").lower()
    all_rules = QA_RULES + SECURITY_RULES
    result: list[Rule] = []
    for rule in all_rules:
        if category and rule.category != category:
            continue
        if "any" in rule.languages or lang in rule.languages:
            result.append(rule)
    return result

