"""Lint test: ``AGENTS.md`` ``**Version**:`` header matches
``pyproject.toml`` ``[project].version``.

Catches the failure class where ``pyproject.toml``'s version bumps but
the human-curated ``AGENTS.md`` (the contract Claude / Amp / other
agents read first) does not get updated. ``juniper-ml#295`` bumped
``pyproject.toml`` from 0.4.1 to 0.5.0 but left the ``AGENTS.md``
header at 0.4.0; that drift was only caught 6 days later via an
ad-hoc grep (``juniper-ml#304``). This test makes the same drift
impossible to ship in any direction (header ahead, pyproject ahead,
or simply out of sync).

The test is intentionally portable: it auto-locates the repo root by
walking up from this file, so the same module can be dropped into any
Juniper repo that has both ``AGENTS.md`` and ``pyproject.toml``. Repos
without a ``pyproject.toml`` (e.g. ``juniper-deploy``) should not adopt
this test -- they have nothing to compare the header against.
"""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path
from typing import ClassVar


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file():
            return parent
    raise RuntimeError(f"Could not locate repo root (pyproject.toml + AGENTS.md) from {here}")


_REPO = _repo_root()
_PYPROJECT = _REPO / "pyproject.toml"
_AGENTS_MD = _REPO / "AGENTS.md"

# Matches the canonical header line, e.g. ``**Version**: 0.5.0``. We
# intentionally only accept the bold-version-then-colon-then-version
# shape that every Juniper AGENTS.md uses today -- a stricter pattern
# fails fast on accidental reformatting.
_HEADER_RE = re.compile(r"^\*\*Version\*\*:\s*(?P<version>\S+)\s*$", re.MULTILINE)


class AgentsMdVersionDriftTest(unittest.TestCase):
    """Pin ``AGENTS.md`` ``**Version**`` to ``pyproject.toml`` ``[project].version``."""

    pyproject_version: ClassVar[str]
    agents_md_version: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        with _PYPROJECT.open("rb") as handle:
            pyproject = tomllib.load(handle)
        cls.pyproject_version = pyproject["project"]["version"]

        text = _AGENTS_MD.read_text(encoding="utf-8")
        matches = _HEADER_RE.findall(text)
        if not matches:
            raise unittest.SkipTest(f"{_AGENTS_MD} has no `**Version**: X.Y.Z` header; " "this lint only applies to AGENTS.md files that opt in " "by including the canonical header.")
        if len(matches) > 1:
            raise AssertionError(f"{_AGENTS_MD} has multiple `**Version**:` headers: {matches!r}. " "Expected exactly one canonical header at the top of the file.")
        cls.agents_md_version = matches[0]

    def test_versions_match(self) -> None:
        self.assertEqual(
            self.agents_md_version,
            self.pyproject_version,
            (f"AGENTS.md `**Version**: {self.agents_md_version}` does not match " f'pyproject.toml `[project].version = "{self.pyproject_version}"`. ' "Bump AGENTS.md in the same PR as the pyproject version bump " "so the agent-facing contract stays in sync with the package."),
        )


if __name__ == "__main__":
    unittest.main()
