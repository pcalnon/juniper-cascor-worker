"""Lint test: every `python|bash <path/to/script>` invocation in a
.github/workflows/*.yml file must reference a path that exists in the repo.

Catches the failure class that broke 3 juniper-X CIs on 2026-05-18, where a
script was renamed (or its symlink target moved into a non-checked-out
sibling repo) but the workflow continued to invoke the old path. The CI
would fail with `python: can't open file '.../scripts/check_doc_links.py'`
on every run until somebody noticed.

This file is **location-agnostic**: drop it anywhere in any Juniper repo
(top-level ``tests/``, ``src/tests/repo_meta/``, ``meta_tests/``, etc.)
and it discovers the repo root by walking up the filesystem looking for
``.github/workflows/``. Copy the file into ``<repo>/<wherever>/`` and
invoke via ``python3 -m unittest <wherever>/test_workflow_script_paths.py``.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import yaml

# Path-like script references: a token containing at least one ``/`` and
# ending in .py/.sh/.bash, not preceded by another path char. Catches all
# the common invocation forms:
#
#   python scripts/check_doc_links.py
#   python3 -m unittest -v tests/test_foo.py
#   bash util/generate_dep_docs.sh
#   $PYTHON scripts/foo.py            (shell var)
#
# Module form ``python -m foo.bar`` is intentionally not validated because
# we cannot resolve a module to a path without importing the package.
_SCRIPT_PATH = re.compile(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_-]+(?:/[A-Za-z0-9_./-]+)+\.(?:py|sh|bash))\b")


def _iter_yaml_strings(node):
    """Yield every string value reachable in a parsed YAML tree."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_yaml_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_yaml_strings(value)


def _extract_script_paths(yaml_text: str) -> set[str]:
    """Extract `python <path.py>` and `bash <path.{bash,sh}>` paths from a
    workflow YAML file's parsed content.
    """
    paths: set[str] = set()
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        # Workflow that doesn't parse is its own problem; skip rather than
        # mask the YAML error in this test.
        return paths

    for value in _iter_yaml_strings(parsed):
        for match in _SCRIPT_PATH.finditer(value):
            paths.add(match.group(1))
    return paths


# Sibling ecosystem repos that scheduled workflows clone into the runner
# workspace before invoking. Any path under one of these is runtime-resolved
# from a clone, not a path checked into this repo, so the lint test must
# skip it.
_ECOSYSTEM_SIBLING_PREFIXES = (
    "juniper-canopy/",
    "juniper-cascor/",
    "juniper-cascor-client/",
    "juniper-cascor-worker/",
    "juniper-data/",
    "juniper-data-client/",
    "juniper-deploy/",
    "juniper-ml/",
)


def _is_validatable(path: str) -> bool:
    """Filter out paths the lint test cannot resolve."""
    if "${" in path or "$(" in path:  # shell-expanded variables
        return False
    if path.startswith("/"):  # absolute paths (e.g., toolcache python)
        return False
    if path.startswith("-"):  # caught a flag like ``-m``
        return False
    if path.startswith(_ECOSYSTEM_SIBLING_PREFIXES):
        return False  # cross-repo path resolved at runtime, not at lint time
    # Skip standalone short filenames (likely a shell variable or a runtime-
    # extracted name) -- we only validate paths that include a directory.
    return "/" in path


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` looking for the first ancestor that
    contains a ``.github/workflows/`` directory. That's the repo root
    relative to which every workflow path resolves.

    This replaces the prior ``Path(__file__).resolve().parent.parent``
    heuristic so the test file can live anywhere in the consuming repo
    (top-level ``tests/``, ``src/tests/repo_meta/``,
    ``meta_tests/``, etc.) -- the test discovers the repo without
    caring about its own location.
    """
    for parent in [start, *start.parents]:
        if (parent / ".github" / "workflows").is_dir():
            return parent
    raise RuntimeError(f"Could not locate repo root: no .github/workflows/ directory " f"found in any ancestor of {start}")


class WorkflowScriptPathsTest(unittest.TestCase):
    """Every script path referenced from a CI workflow must exist."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = _find_repo_root(Path(__file__).resolve().parent)
        cls.workflows_dir = cls.repo_root / ".github" / "workflows"

    def test_workflows_dir_exists(self):
        self.assertTrue(
            self.workflows_dir.is_dir(),
            f"Expected workflows directory at {self.workflows_dir}",
        )

    def test_every_script_path_in_every_workflow_exists(self):
        workflow_files = sorted(self.workflows_dir.glob("*.yml")) + sorted(self.workflows_dir.glob("*.yaml"))
        self.assertGreater(
            len(workflow_files),
            0,
            f"No workflow files found in {self.workflows_dir}",
        )

        missing: list[tuple[Path, str]] = []
        for wf_file in workflow_files:
            text = wf_file.read_text(encoding="utf-8")
            for script_path in _extract_script_paths(text):
                if not _is_validatable(script_path):
                    continue
                resolved = self.repo_root / script_path
                if not resolved.exists():
                    missing.append((wf_file, script_path))

        if missing:
            report = "\n".join(f"  {wf.relative_to(self.repo_root)}: references missing path '{p}'" for wf, p in missing)
            self.fail("CI workflow(s) reference script paths that do not exist:\n" + report + "\n\nThis is the failure class that broke 3 juniper-X CIs on " "2026-05-18 (script rename without workflow update).\n" "Either restore the missing path or update the workflow.")


class WorkflowScriptPathExtractionTest(unittest.TestCase):
    """Direct unit tests for the parsing helpers."""

    def test_extracts_python_script_invocation(self):
        yaml_text = "jobs:\n" "  docs:\n" "    steps:\n" "      - run: python scripts/check_doc_links.py --exclude templates\n"
        self.assertEqual(_extract_script_paths(yaml_text), {"scripts/check_doc_links.py"})

    def test_extracts_python3_with_minor_version(self):
        yaml_text = "jobs:\n" "  t:\n" "    steps:\n" "      - run: python3.14 util/foo.py --bar\n"
        self.assertEqual(_extract_script_paths(yaml_text), {"util/foo.py"})

    def test_extracts_bash_script_invocation(self):
        yaml_text = "jobs:\n" "  t:\n" "    steps:\n" "      - run: bash util/generate_dep_docs.bash\n"
        self.assertEqual(_extract_script_paths(yaml_text), {"util/generate_dep_docs.bash"})

    def test_extracts_unittest_positional_test_files(self):
        yaml_text = "jobs:\n" "  t:\n" "    steps:\n" "      - run: python3 -m unittest -v tests/test_foo.py\n"
        # The unittest module form is ``-m unittest`` (no .py path), so the
        # parser does NOT pick up ``-m unittest``. It DOES pick up the
        # positional tests/test_foo.py which is what we want validated.
        self.assertEqual(_extract_script_paths(yaml_text), {"tests/test_foo.py"})

    def test_ignores_shell_variable_substitution(self):
        # A shell-expanded variable like $PYTHON should not be a path. The
        # regex only matches literal file extensions, so this is implicit;
        # this test pins the behavior so a future regex broadening doesn't
        # silently start emitting variable-paths.
        yaml_text = "jobs:\n" "  t:\n" "    steps:\n" "      - run: $PYTHON scripts/check_doc_links.py\n"
        self.assertEqual(_extract_script_paths(yaml_text), {"scripts/check_doc_links.py"})

    def test_skips_cross_repo_prefix_paths(self):
        self.assertFalse(_is_validatable("juniper-ml/util/foo.bash"))
        self.assertFalse(_is_validatable("juniper-data/scripts/bar.py"))

    def test_validates_intra_repo_paths(self):
        self.assertTrue(_is_validatable("scripts/check_doc_links.py"))
        self.assertTrue(_is_validatable("util/generate_dep_docs.sh"))
        self.assertTrue(_is_validatable("tests/test_foo.py"))

    def test_skips_absolute_and_variable_paths(self):
        self.assertFalse(_is_validatable("/usr/local/bin/foo.py"))
        self.assertFalse(_is_validatable("${{ env.SCRIPT }}/foo.py"))
        self.assertFalse(_is_validatable("$(get_path)/foo.sh"))
        # standalone filename without a directory -- ambiguous, skip
        self.assertFalse(_is_validatable("foo.py"))


class RepoRootDiscoveryTest(unittest.TestCase):
    """Regression for the location-agnostic repo-root finder.

    Replaces the prior ``Path(__file__).resolve().parent.parent``
    heuristic that assumed the test file lives at
    ``<repo>/tests/test_workflow_script_paths.py`` -- some consumer
    repos use a top-level ``tests`` symlink (to a bash run-all
    script), so the test file must live elsewhere there.
    """

    def test_finds_root_via_dot_github_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fake-repo"
            (fake / ".github" / "workflows").mkdir(parents=True)
            nested = fake / "deep" / "nested" / "tests"
            nested.mkdir(parents=True)
            self.assertEqual(_find_repo_root(nested), fake)
            self.assertEqual(_find_repo_root(nested / "more"), fake)

    def test_raises_when_no_dot_github_workflows_in_ancestors(self):
        with tempfile.TemporaryDirectory() as tmp:
            isolated = Path(tmp) / "isolated"
            isolated.mkdir()
            with self.assertRaises(RuntimeError):
                _find_repo_root(isolated)


if __name__ == "__main__":
    unittest.main()
