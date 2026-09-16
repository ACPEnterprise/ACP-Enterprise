from __future__ import annotations

import subprocess
import sys


def test_candidate_admission_cli_loads_complete_model_registry() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import scripts.pricebook_candidate_admission; "
                "from sqlalchemy.orm import configure_mappers; "
                "configure_mappers()"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
