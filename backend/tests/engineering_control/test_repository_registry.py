from dataclasses import FrozenInstanceError, fields

import pytest

from app.engineering_control.registry import (
    EngineeringRepositoryDefinition,
    EngineeringRepositoryRegistry,
    EngineeringRepositoryRegistryError,
    engineering_repository_registry,
)


def test_acp_enterprise_repository_policy_is_safe_and_immutable() -> None:
    definition = engineering_repository_registry.resolve("acp-enterprise")

    assert definition.repository_identity == "ACP Enterprise"
    assert definition.approved_active_branch == "customer-management-v1"
    assert definition.remote_execution_enabled is False
    assert definition.inspection_allowed is True
    assert definition.validation_allowed is True
    assert definition.uncommitted_code_changes_allowed is True
    assert definition.commit_allowed is False
    assert definition.push_allowed is False
    assert definition.merge_allowed is False
    assert definition.deployment_allowed is False
    assert definition.infrastructure_mutation_allowed is False
    assert definition.destructive_cleanup_allowed is False
    with pytest.raises(FrozenInstanceError):
        definition.remote_execution_enabled = True  # type: ignore[misc]


def test_registry_public_definition_exposes_no_execution_secrets() -> None:
    exposed_fields = {item.name for item in fields(EngineeringRepositoryDefinition)}
    forbidden_markers = {
        "path",
        "url",
        "credential",
        "secret",
        "host",
        "codex",
        "endpoint",
    }

    assert not any(
        marker in field_name
        for marker in forbidden_markers
        for field_name in exposed_fields
    )


def test_registry_rejects_unknown_duplicate_and_unsafe_definitions() -> None:
    definition = engineering_repository_registry.resolve("acp-enterprise")
    with pytest.raises(EngineeringRepositoryRegistryError):
        engineering_repository_registry.resolve("unknown")
    with pytest.raises(EngineeringRepositoryRegistryError, match="duplicate"):
        EngineeringRepositoryRegistry((definition, definition))
    with pytest.raises(EngineeringRepositoryRegistryError, match="prohibited"):
        EngineeringRepositoryRegistry(
            (
                EngineeringRepositoryDefinition(
                    **{
                        **definition.__dict__,
                        "repository_key": "unsafe-repository",
                        "commit_allowed": True,
                    }
                ),
            )
        )
    with pytest.raises(EngineeringRepositoryRegistryError, match="remote execution"):
        EngineeringRepositoryRegistry(
            (
                EngineeringRepositoryDefinition(
                    **{
                        **definition.__dict__,
                        "repository_key": "remote-repository",
                        "remote_execution_enabled": True,
                    }
                ),
            )
        )
