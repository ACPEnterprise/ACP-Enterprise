from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from scripts.hcp_financial_accountant_packet import write_packet


def test_write_packet_is_immutable_and_private(tmp_path: Path) -> None:
    output = tmp_path / "private" / "packet.json"
    packet = {"contract": "test/v1", "digest": "accepted"}

    first_sha = write_packet(packet=packet, output=output)

    assert json.loads(output.read_bytes()) == packet
    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert len(first_sha) == 64
    with pytest.raises(FileExistsError):
        write_packet(packet=packet, output=output)
