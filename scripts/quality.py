"""Run the local quality gates used by CI.

The tools are intentionally pinned here so a developer and CI invoke the same
versions even before the project has runtime dependencies.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

RUFF_VERSION = "0.16.7"
MYPY_VERSION = "2.3.1"
PYTEST_VERSION = "9.1.1"
PIP_AUDIT_VERSION = "2.10.1"


def run(command: Sequence[str]) -> None:
    """Run one quality command and fail immediately on errors."""
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def uvx(package: str, executable: str, *args: str) -> list[str]:
    """Build an isolated uvx command with an exactly pinned tool package."""
    return ["uvx", "--from", package, executable, *args]


def project_tool(package: str, executable: str, *args: str) -> list[str]:
    """Run a pinned tool inside the project environment."""
    return ["uv", "run", "--with", package, executable, *args]


def run_fast_checks() -> None:
    """Run the non-audit quality checks."""
    run(["uv", "lock", "--check"])
    run(uvx(f"ruff=={RUFF_VERSION}", "ruff", "format", "--check", "."))
    run(uvx(f"ruff=={RUFF_VERSION}", "ruff", "check", "."))
    run(uvx(f"mypy=={MYPY_VERSION}", "mypy", "src", "tests", "scripts"))
    run(project_tool(f"pytest=={PYTEST_VERSION}", "pytest"))


def run_security_checks() -> None:
    """Run dependency vulnerability checks that require network access."""
    run(uvx(f"pip-audit=={PIP_AUDIT_VERSION}", "pip-audit", "."))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (["--fast"], ["--all"], []):
        raise SystemExit("usage: quality.py [--fast|--all]")

    run_fast_checks()
    if args == ["--all"]:
        run_security_checks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
