from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from development_factory.task_contract import VALIDATION_AREAS


ROLE_CATALOG_VERSION = "1.0"


class AgentRoleError(ValueError):
    pass


@dataclass(frozen=True)
class AgentRole:
    role_id: str
    display_name: str
    responsibilities: tuple[str, ...]
    prohibited_responsibilities: tuple[str, ...]
    default_validation: tuple[str, ...]
    escalation_conditions: tuple[str, ...]
    may_propose_code_changes: bool
    may_review_other_work: bool
    may_commit: bool
    may_push: bool
    may_merge: bool
    may_deploy: bool


def load_agent_roles(path: Path) -> dict[str, AgentRole]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentRoleError(f"unable to load agent roles: {exc}") from exc
    if not isinstance(payload, dict) or payload.keys() != {
        "schema_version",
        "roles",
    }:
        raise AgentRoleError("agent-role catalog fields are invalid")
    if payload["schema_version"] != ROLE_CATALOG_VERSION:
        raise AgentRoleError(
            f"agent-role schema_version must be {ROLE_CATALOG_VERSION}"
        )
    raw_roles = payload["roles"]
    if not isinstance(raw_roles, list) or not raw_roles:
        raise AgentRoleError("agent-role catalog requires at least one role")
    roles: dict[str, AgentRole] = {}
    for raw in raw_roles:
        role = _parse_role(raw)
        if role.role_id in roles:
            raise AgentRoleError(f"duplicate agent role: {role.role_id}")
        roles[role.role_id] = role
    return dict(sorted(roles.items()))


def _parse_role(value: object) -> AgentRole:
    if not isinstance(value, dict):
        raise AgentRoleError("each agent role must be an object")
    expected = {
        "role_id",
        "display_name",
        "responsibilities",
        "prohibited_responsibilities",
        "default_validation",
        "escalation_conditions",
        "may_propose_code_changes",
        "may_review_other_work",
        "privileged_authority",
    }
    if value.keys() != expected:
        raise AgentRoleError("agent-role fields are invalid")
    role_id = _nonblank(value["role_id"], "role_id")
    authority = value["privileged_authority"]
    if not isinstance(authority, dict) or authority.keys() != {
        "commit",
        "push",
        "merge",
        "deployment",
    }:
        raise AgentRoleError("privileged_authority fields are invalid")
    if not all(isinstance(item, bool) for item in authority.values()):
        raise AgentRoleError("privileged_authority values must be booleans")
    if any(authority.values()):
        raise AgentRoleError(f"agent role {role_id} cannot have privileged authority")
    boolean_fields = ("may_propose_code_changes", "may_review_other_work")
    if not all(isinstance(value[field], bool) for field in boolean_fields):
        raise AgentRoleError("agent role capability flags must be booleans")
    default_validation = _strings(value["default_validation"], "default_validation")
    if not set(default_validation) <= VALIDATION_AREAS:
        raise AgentRoleError("default_validation contains an unsupported area")
    return AgentRole(
        role_id=role_id,
        display_name=_nonblank(value["display_name"], "display_name"),
        responsibilities=_strings(value["responsibilities"], "responsibilities"),
        prohibited_responsibilities=_strings(
            value["prohibited_responsibilities"], "prohibited_responsibilities"
        ),
        default_validation=default_validation,
        escalation_conditions=_strings(
            value["escalation_conditions"], "escalation_conditions"
        ),
        may_propose_code_changes=value["may_propose_code_changes"],
        may_review_other_work=value["may_review_other_work"],
        may_commit=False,
        may_push=False,
        may_merge=False,
        may_deploy=False,
    )


def _strings(value: object, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise AgentRoleError(f"{field} must be a non-empty string array")
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        raise AgentRoleError(f"{field} cannot contain duplicates")
    return result


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentRoleError(f"{field} must be a nonblank string")
    return value.strip()
