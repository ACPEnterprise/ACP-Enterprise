from app.operational_migration.hcp_successor_reconciliation import (
    IdentityBinding,
    SealedIdentity,
    SuccessorDisposition,
    reconcile_successors_v2,
)


def test_v2_splits_reuse_create_and_conflict_and_keeps_ids_private() -> None:
    result = reconcile_successors_v2(
        current_bindings=[
            IdentityBinding("customer", "housecall_pro", "reuse", "target-1"),
            IdentityBinding(
                "customer", "housecall_pro_source4", "conflict", "target-2"
            ),
        ],
        sealed_source4=[
            SealedIdentity("customer", "reuse"),
            SealedIdentity("customer", "create"),
            SealedIdentity("customer", "conflict"),
        ],
    )
    assert result.report.disposition_counts == {
        SuccessorDisposition.EXACT_SUCCESSOR: 0,
        SuccessorDisposition.REUSE_LEGACY_TARGET: 1,
        SuccessorDisposition.CREATE_NEW_TARGET: 1,
        SuccessorDisposition.CONFLICT: 1,
    }
    assert result.report.admission_allowed is False
    assert result.private_manifest.entries[0].target_id == "target-1"
    assert "target-1" not in repr(result.report)


def test_v2_is_order_independent_and_manifest_digest_binds_mapping() -> None:
    bindings = [IdentityBinding("customer", "housecall_pro", "source", "target")]
    first = reconcile_successors_v2(
        current_bindings=bindings,
        sealed_source4=[SealedIdentity("customer", "source")],
    )
    replay = reconcile_successors_v2(
        current_bindings=reversed(bindings),
        sealed_source4=[SealedIdentity("customer", "source")],
    )
    assert first == replay
    assert first.report.admission_allowed is True
