from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from app.beacon.contracts import BeaconSeverity
from app.beacon.definitions import (
    BEACON_SIGNAL_DEFINITIONS,
    BeaconSignalDefinitionRegistry,
)
from app.beacon.evaluation import SignalEvaluationService
from tests.beacon.test_beacon import NOW, snapshot


def test_definitions_are_immutable_versioned_and_uniquely_registered() -> None:
    definition = BEACON_SIGNAL_DEFINITIONS.definitions[0]

    assert definition.version == 1
    assert definition.definition_id == definition.rule_code
    with pytest.raises(FrozenInstanceError):
        definition.version = 2  # type: ignore[misc]
    with pytest.raises(ValueError, match="identity and version"):
        BeaconSignalDefinitionRegistry((definition, definition))
    with pytest.raises(ValueError, match="one active version"):
        BeaconSignalDefinitionRegistry((definition, replace(definition, version=2)))


def test_evaluation_produces_deterministic_business_event_conditions() -> None:
    source = snapshot()
    service = SignalEvaluationService()

    first = service.evaluate_conditions(source)
    second = service.evaluate_conditions(source)

    assert first == second
    assert len(first) == 3
    assert all(condition.definition_version == 1 for condition in first)
    assert all(condition.evidence_digest for condition in first)
    assert all(
        evidence.event_id is not None
        for condition in first
        for fact in condition.supporting_facts
        for evidence in fact.evidence
    )
    assert [condition.severity for condition in first] == [
        BeaconSeverity.CRITICAL,
        BeaconSeverity.ATTENTION,
        BeaconSeverity.IMPORTANT,
    ]
    assert all(
        condition.expires_at == NOW + timedelta(minutes=15) for condition in first
    )


def test_definition_version_is_part_of_reproducible_signal_evidence() -> None:
    source = snapshot()
    original = SignalEvaluationService()
    definitions = BEACON_SIGNAL_DEFINITIONS.definitions
    versioned = SignalEvaluationService(
        registry=BeaconSignalDefinitionRegistry(
            (replace(definitions[0], version=2), *definitions[1:])
        )
    )

    original_signal = original.evaluate_signals(source)[0]
    versioned_signal = versioned.evaluate_signals(source)[0]

    assert original_signal.condition_key == versioned_signal.condition_key
    assert original_signal.evidence_digest != versioned_signal.evidence_digest
    assert original_signal.id != versioned_signal.id
    assert versioned_signal.definition_version == 2


def test_authorization_scope_is_part_of_signal_and_condition_identity() -> None:
    service = SignalEvaluationService()
    source = snapshot()
    branch_a = service.evaluate_signals(
        replace(source, scope_identity="branch-scope-a")
    )[0]
    branch_b = service.evaluate_signals(
        replace(source, scope_identity="branch-scope-b")
    )[0]

    assert branch_a.evidence_digest == branch_b.evidence_digest
    assert branch_a.condition_key != branch_b.condition_key
    assert branch_a.id != branch_b.id


def test_definitions_own_escalation_and_expiration_without_module_callbacks() -> None:
    service = SignalEvaluationService()
    signal = service.evaluate_signals(snapshot())[0]

    assert signal.definition_id == "scheduling.overdue_committed_appointments"
    assert signal.definition_version == 1
    assert signal.severity is BeaconSeverity.CRITICAL
    assert signal.expires_at == signal.created_at + timedelta(seconds=900)
    assert not any(
        callable(value) for value in vars(BEACON_SIGNAL_DEFINITIONS).values()
    )
