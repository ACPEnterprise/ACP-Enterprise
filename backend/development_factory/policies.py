from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Iterable

from development_factory.models import Finding


SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".sh", ".yml", ".yaml"}
EXCLUDED_PARTS = {
    ".git",
    ".development-factory",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "__pycache__",
}


def scan_policies(repo_root: Path, config: dict[str, Any]) -> tuple[Finding, ...]:
    allowlisted = tuple(config.get("policy", {}).get("allowlisted_paths", ()))
    suppressions = _load_suppressions(config)
    findings: list[Finding] = []
    files = tuple(_source_files(repo_root))

    for path in files:
        relative = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(_conflict_markers(relative, text))
        if relative.startswith("backend/app/"):
            findings.extend(_runtime_checks(relative, text))
        if relative.startswith("backend/app/") and relative.endswith("router.py"):
            findings.extend(_router_checks(relative, text))
            findings.extend(_router_protection_checks(relative, text))
        if relative.startswith("backend/app/") and "repository" in path.name:
            findings.extend(_repository_checks(relative, text))
        if relative.startswith("backend/app/") and "service" in path.name:
            findings.extend(_service_checks(relative, text))
        if not relative.startswith(allowlisted):
            findings.extend(_raw_sql_checks(relative, text))
        if relative.startswith("backend/app/") and relative.endswith("models.py"):
            findings.extend(_tenant_model_checks(relative, text))
        if relative.startswith("backend/app/") and relative.endswith("records.py"):
            findings.extend(_immutable_record_checks(relative, text))
        findings.extend(_security_checks(relative, text))
        if relative.startswith(
            ("scripts/development-factory", "backend/development_factory/")
        ):
            findings.extend(_forbidden_factory_actions(relative, text))

    findings.extend(_runtime_import_isolation(repo_root))
    return tuple(
        sorted(
            (_apply_suppression(item, suppressions) for item in findings),
            key=lambda item: (item.severity, item.rule_id, item.path, item.line or 0),
        )
    )


def _source_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if (
            path.is_file()
            and (path.suffix in SOURCE_SUFFIXES or path.name == "development-factory")
            and not any(part in EXCLUDED_PARTS for part in path.parts)
        ):
            yield path


def _conflict_markers(path: str, text: str) -> list[Finding]:
    return _pattern_findings(
        "repository.merge_marker",
        "error",
        path,
        text,
        re.compile(r"^(<<<<<<< |=======\s*$|>>>>>>> )", re.MULTILINE),
        "Unresolved merge-conflict marker",
    )


def _runtime_checks(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if "development_factory" in text:
        findings.append(
            Finding(
                "runtime.factory_import",
                "error",
                "Runtime application code references Development Factory tooling",
                path,
                _line(text, "development_factory"),
            )
        )
    if re.search(r"(test_only|bypass_auth|fake_auth)", text, re.IGNORECASE):
        findings.append(
            Finding(
                "security.test_bypass",
                "warning",
                "Possible test-only authentication bypass in runtime code",
                path,
            )
        )
    return findings


def _router_checks(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for token, message in (
        ("select(", "Router appears to construct a SQL query"),
        (".commit(", "Router appears to commit a transaction"),
        (".rollback(", "Router appears to roll back a transaction"),
        (".add(", "Router appears to add a persistence entity directly"),
    ):
        if token in text:
            findings.append(
                Finding(
                    "architecture.router_boundary",
                    "warning",
                    message,
                    path,
                    _line(text, token),
                )
            )
    return findings


def _router_protection_checks(path: str, text: str) -> list[Finding]:
    if "/api/" in path or path.endswith("health.py"):
        return []
    if "APIRouter" in text and not any(
        token in text
        for token in (
            "Depends",
            "Security",
            "require_permission",
            "get_authorization_context",
        )
    ):
        return [
            Finding(
                "security.router_protection",
                "warning",
                "Business router has no apparent authentication/authorization dependency",
                path,
            )
        ]
    return []


def _repository_checks(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for token, message, severity in (
        (".commit(", "Repository owns a transaction commit", "error"),
        (".rollback(", "Repository owns a transaction rollback", "error"),
        ("fastapi", "Repository imports HTTP framework concerns", "error"),
        (
            "BusinessEventService",
            "Repository appears to publish business events",
            "error",
        ),
        ("AuthorizationContext", "Repository appears to own authorization", "warning"),
    ):
        if token in text:
            findings.append(
                Finding(
                    "architecture.repository_boundary",
                    severity,  # type: ignore[arg-type]
                    message,
                    path,
                    _line(text, token),
                )
            )
    if "company_id" not in text and ("select(" in text or "update(" in text):
        findings.append(
            Finding(
                "tenant.repository_scope",
                "warning",
                "Repository query code has no apparent company_id predicate",
                path,
            )
        )
    return findings


def _service_checks(path: str, text: str) -> list[Finding]:
    if "JSONResponse" in text or "HTTPException" in text:
        return [
            Finding(
                "architecture.service_http",
                "warning",
                "Domain service appears to construct HTTP responses",
                path,
                _line(text, "HTTP"),
            )
        ]
    return []


def _raw_sql_checks(path: str, text: str) -> list[Finding]:
    if not path.startswith("backend/app/"):
        return []
    if re.search(r"\b(text|select|update|delete|insert)\s*\(", text) and not (
        "repository" in path or path.endswith("models.py")
    ):
        return [
            Finding(
                "architecture.sql_placement",
                "warning",
                "Possible SQL construction outside repository/model allowlist",
                path,
            )
        ]
    return []


def _tenant_model_checks(path: str, text: str) -> list[Finding]:
    tenant_names = (
        "Customer",
        "ServiceLocation",
        "Appointment",
        "Job",
        "Employee",
        "Branch",
        "Membership",
        "Workforce",
    )
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings: list[Finding] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not node.name.startswith(tenant_names):
            continue
        class_text = ast.get_source_segment(text, node) or ""
        if "company_id" not in class_text:
            findings.append(
                Finding(
                    "tenant.model_company_id",
                    "warning",
                    f"Apparently Company-owned model {node.name} lacks company_id",
                    path,
                    node.lineno,
                )
            )
    return findings


def _immutable_record_checks(path: str, text: str) -> list[Finding]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings: list[Finding] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        decorators = [
            ast.get_source_segment(text, item) or "" for item in node.decorator_list
        ]
        if any(item.startswith("dataclass") for item in decorators) and not any(
            "frozen=True" in item.replace(" ", "") for item in decorators
        ):
            findings.append(
                Finding(
                    "architecture.immutable_record",
                    "warning",
                    f"Public record {node.name} is not a frozen dataclass",
                    path,
                    node.lineno,
                )
            )
    return findings


def _security_checks(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if path.startswith(
        ("backend/tests/", "frontend/src/", "backend/development_factory/")
    ) or path.startswith("backend/alembic/versions/"):
        return findings
    patterns = (
        (
            "security.secret_literal",
            re.compile(
                r"(?i)(password|api_key|private_key|secret)\s*[:=]\s*['\"][^'\"]{12,}"
            ),
            "Possible committed credential literal",
        ),
        (
            "security.cors_wildcard",
            re.compile(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]"),
            "CORS wildcard requires review when credentials are enabled",
        ),
        (
            "security.plaintext_token",
            re.compile(r"(?i)(token|refresh_token).*(String|varchar).*nullable"),
            "Possible plaintext token persistence",
        ),
    )
    for rule_id, pattern, message in patterns:
        for finding in _pattern_findings(
            rule_id, "warning", path, text, pattern, message
        ):
            if rule_id == "security.plaintext_token":
                line = text.splitlines()[max((finding.line or 1) - 1, 0)]
                if re.search(r"(hash|digest|hmac|encrypted)", line, re.IGNORECASE):
                    continue
            findings.append(finding)
    if re.search(r"environment\s*==\s*['\"]production['\"]", text) and re.search(
        r"debug\s*=\s*True", text
    ):
        findings.append(
            Finding(
                "security.production_debug",
                "warning",
                "Production configuration appears to enable debug mode",
                path,
            )
        )
    if re.search(
        r"\[[^\]]+for\s+\w+\s+in\s+\w+\s+if\s+[^]]*company_id", text, re.DOTALL
    ):
        findings.append(
            Finding(
                "tenant.post_query_filter",
                "warning",
                "Possible in-memory Company filtering requires tenant-isolation review",
                path,
            )
        )
    return findings


def _forbidden_factory_actions(path: str, text: str) -> list[Finding]:
    if path.endswith("development_factory/policies.py"):
        return []
    patterns = (
        r"\bgit\s+commit\b",
        r"\bgit\s+push\b",
        r"\bgit\s+merge\b",
        r"\b(terraform|pulumi)\s+(apply|destroy)\b",
        r"\b(doctl|kubectl)\b.*\b(deploy|apply|delete)\b",
        r"(preview|production).*(dropdb|alembic upgrade|psql)",
    )
    findings: list[Finding] = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            findings.append(
                Finding(
                    "factory.forbidden_action",
                    "error",
                    "Development Factory contains a prohibited mutation command",
                    path,
                    text.count("\n", 0, match.start()) + 1,
                )
            )
    return findings


def _runtime_import_isolation(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    app_root = repo_root / "backend" / "app"
    for path in app_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = " ".join(alias.name for alias in node.names)
            if "development_factory" in module:
                findings.append(
                    Finding(
                        "runtime.factory_import",
                        "error",
                        "Runtime imports Development Factory tooling",
                        path.relative_to(repo_root).as_posix(),
                        getattr(node, "lineno", None),
                    )
                )
    return findings


def _load_suppressions(config: dict[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for item in config.get("policy", {}).get("suppressions", ()):
        if not isinstance(item, dict) or not item.get("rationale"):
            raise ValueError("every policy suppression requires a rationale")
        result[(str(item["rule_id"]), str(item["path"]))] = str(item["rationale"])
    return result


def _apply_suppression(
    finding: Finding, suppressions: dict[tuple[str, str], str]
) -> Finding:
    rationale = suppressions.get((finding.rule_id, finding.path))
    if rationale is None:
        return finding
    return Finding(
        **{
            **finding.__dict__,
            "suppressed": True,
            "rationale": rationale,
        }
    )


def _pattern_findings(
    rule_id: str,
    severity: str,
    path: str,
    text: str,
    pattern: re.Pattern[str],
    message: str,
) -> list[Finding]:
    return [
        Finding(
            rule_id,
            severity,  # type: ignore[arg-type]
            message,
            path,
            text.count("\n", 0, match.start()) + 1,
        )
        for match in pattern.finditer(text)
    ]


def _line(text: str, token: str) -> int | None:
    position = text.find(token)
    return None if position < 0 else text.count("\n", 0, position) + 1
