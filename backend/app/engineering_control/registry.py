import re
from dataclasses import dataclass
from types import MappingProxyType

from app.core.config import settings


class EngineeringRepositoryRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class EngineeringRepositoryDefinition:
    repository_key: str
    repository_identity: str
    approved_active_branch: str
    approved_inspection_branches: tuple[str, ...]
    execution_environment_policy: str
    remote_execution_enabled: bool
    inspection_allowed: bool
    validation_allowed: bool
    uncommitted_code_changes_allowed: bool
    commit_allowed: bool
    push_allowed: bool
    merge_allowed: bool
    deployment_allowed: bool
    infrastructure_mutation_allowed: bool
    destructive_cleanup_allowed: bool


class EngineeringRepositoryRegistry:
    def __init__(
        self, definitions: tuple[EngineeringRepositoryDefinition, ...]
    ) -> None:
        if not definitions:
            raise EngineeringRepositoryRegistryError(
                "at least one repository definition is required"
            )
        resolved: dict[str, EngineeringRepositoryDefinition] = {}
        for definition in definitions:
            self._validate(definition)
            if definition.repository_key in resolved:
                raise EngineeringRepositoryRegistryError(
                    f"duplicate repository key: {definition.repository_key}"
                )
            resolved[definition.repository_key] = definition
        self._definitions = MappingProxyType(resolved)

    def resolve(self, repository_key: str) -> EngineeringRepositoryDefinition:
        try:
            return self._definitions[repository_key]
        except KeyError as exc:
            raise EngineeringRepositoryRegistryError(
                "repository key is not allowlisted"
            ) from exc

    @staticmethod
    def _validate(definition: EngineeringRepositoryDefinition) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,79}", definition.repository_key):
            raise EngineeringRepositoryRegistryError("repository key is unsafe")
        for value, field_name in (
            (definition.repository_identity, "repository identity"),
            (definition.approved_active_branch, "approved branch"),
            (definition.execution_environment_policy, "execution policy"),
        ):
            if not value.strip():
                raise EngineeringRepositoryRegistryError(
                    f"{field_name} cannot be blank"
                )
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", branch)
            or branch.startswith("/")
            or ".." in branch.split("/")
            or ".git" in branch.split("/")
            for branch in definition.approved_inspection_branches
        ):
            raise EngineeringRepositoryRegistryError(
                "approved inspection branch is unsafe"
            )
        if any(
            (
                definition.commit_allowed,
                definition.push_allowed,
                definition.merge_allowed,
                definition.deployment_allowed,
                definition.infrastructure_mutation_allowed,
                definition.destructive_cleanup_allowed,
            )
        ):
            raise EngineeringRepositoryRegistryError(
                "privileged repository capabilities are prohibited in DF.5A"
            )
        if definition.remote_execution_enabled:
            raise EngineeringRepositoryRegistryError(
                "remote execution must remain disabled in DF.5A"
            )


engineering_repository_registry = EngineeringRepositoryRegistry(
    (
        EngineeringRepositoryDefinition(
            repository_key="acp-enterprise",
            repository_identity="ACP Enterprise",
            approved_active_branch="customer-management-v1",
            approved_inspection_branches=tuple(
                settings.engineering_inspection_branches
            ),
            execution_environment_policy="df5b_private_control_plane_required",
            remote_execution_enabled=False,
            inspection_allowed=True,
            validation_allowed=True,
            uncommitted_code_changes_allowed=True,
            commit_allowed=False,
            push_allowed=False,
            merge_allowed=False,
            deployment_allowed=False,
            infrastructure_mutation_allowed=False,
            destructive_cleanup_allowed=False,
        ),
    )
)
