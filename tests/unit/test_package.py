"""Bootstrap tests for the package skeleton."""

import arbiscan


def test_package_exposes_bootstrap_version() -> None:
    assert arbiscan.__version__ == "0.1.0.dev0"
