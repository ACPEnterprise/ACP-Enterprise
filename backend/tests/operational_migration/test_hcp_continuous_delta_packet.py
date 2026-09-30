from __future__ import annotations

import argparse
import json

from scripts.build_hcp_continuous_delta_packet import build


def test_private_packet_builder_is_deterministic_and_preserves_parent_graph(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    provider = tmp_path / "provider.json"
    native = tmp_path / "native.json"
    provider.write_text(
        json.dumps(
            {
                "acquired_at": "2026-09-30T12:00:00Z",
                "records": [
                    {
                        "domain": "appointment",
                        "source_id": "appointment-1",
                        "source_digest": "b" * 64,
                        "acquired_at": "2026-09-30T12:00:00Z",
                        "source_updated_at": "2026-09-29T12:00:00Z",
                        "payload": {"id": "appointment-1"},
                        "parent_keys": [
                            {"domain": "job", "source_id": "job-1"}
                        ],
                    }
                ],
            }
        )
    )
    native.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "domain": "appointment",
                        "source_id": "appointment-1",
                        "source_digest": "c" * 64,
                        "source_applied_at": "2026-09-20T12:00:00Z",
                        "native_updated_at": "2026-09-20T12:00:00Z",
                    }
                ]
            }
        )
    )
    args = argparse.Namespace(
        cutoff="2026-09-12T23:59:59Z",
        base_source4_digest="a" * 64,
        company_id="company",
        branch_id="branch",
        provider_observations=provider,
        native_observations=native,
    )
    first = build(args)
    second = build(args)
    assert first == second
    assert first.manifest is not None
    assert first.manifest.records[0].parent_keys[0].source_id == "job-1"
