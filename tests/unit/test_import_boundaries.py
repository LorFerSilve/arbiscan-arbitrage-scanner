"""Regression tests for package import boundaries."""

import subprocess
import sys


def test_matching_and_normalization_import_in_fresh_interpreter() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import arbiscan.matching; import arbiscan.normalization",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
