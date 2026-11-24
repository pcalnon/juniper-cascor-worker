"""The lockfile regen's commit step prints its own diagnostic when ``gh api graphql`` fails.

``lockfile-update.yml``'s commit step runs under ``set -euo pipefail``. ``gh api graphql`` exits 1 on a
response that carries GraphQL ``errors`` and on an HTTP failure, after writing the body to stdout and
``gh: <message>`` to stderr (cli/cli ``pkg/cmd/api/api.go``, ``processResponse``). Called bare, that exit
ended the step at the ``gh`` line, so the step's own ``createCommitOnBranch failed`` diagnostic, the check
right after it, could never print. The step now captures gh's status and stderr, prints gh's message with
the token's value masked, and fails with its own diagnostic: the same fix as juniper-canopy#814, ported
under the Overtoad's ruling 26 (2026-11-12) of the Cursor flood-4 evaluation. The step commits
``requirements.lock`` and ``requirements-cpu.lock`` in one request; these cases regenerate the first.

The shell under test is the workflow's own ``run:`` block, not a copy, run under ``bash -e`` (the shell a
step that names none gets). ``gh`` is a stub that fails the way the real CLI does: the body on stdout,
then its message on stderr, then the exit status. The step writes its request and gh's response under the
runner's ``/tmp/``; every run rewrites that prefix into the test's own ``tmp_path`` first and refuses a
step that would still name a ``/tmp`` path, so nothing is written there. Off Linux, a runner whose
``base64`` cannot run the step's ``base64 -w0 FILE`` gets a stand-in for exactly that form.

Project: juniper-cascor-worker
"""

from __future__ import annotations

import base64
import json
import os
import subprocess  # nosec B404 - bash runs the workflow's own extracted step, with a stub gh on PATH
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit]

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "lockfile-update.yml"
STEP_NAME = "Commit updated lockfiles (GitHub-signed, via API)"
#: The locks the step commits, in the order of its ``fileChanges.additions``.
LOCKS = ("requirements.lock", "requirements-cpu.lock")
#: The step's words for a commit that did not happen.
NOT_COMMITTED = "lockfiles NOT committed"
#: What a successful run prints, and nothing else, when only requirements.lock changed.
SUCCESS_OUT = "::notice::requirements.lock updated\n::notice::requirements-cpu.lock unchanged\nSigned lockfile commit: https://example.test/commit/abc123\n"
RUNNER_TMP = "/tmp/"  # nosec B108 - the prefix the step hardcodes; every run rewrites it into tmp_path
TOKEN = "lockfile-regen-token-not-real"  # nosec B105 - a stand-in that no run may print
REPO_NAME = "pcalnon/juniper-cascor-worker"
BRANCH = "dependabot/pip/example"
REGENERATED = b"# regenerated\npackage==9.9.9\n"
STALE = 'Expected branch to point to "abc" but it did not. Pull and try again.'
SIGNED = {"data": {"createCommitOnBranch": {"commit": {"oid": "abc123", "url": "https://example.test/commit/abc123"}}}}

# The real CLI's order: the response body on stdout, then, when it fails, its message on stderr and the exit status.
_GH = """\
#!/bin/bash
{
  printf '%s' gh
  for arg in "$@"; do printf '\\t%s' "$arg"; done
  printf '\\n'
} >> "$GH_LOG"
printf '%s' "${GH_STDOUT-}"
if [[ "${GH_RC:-0}" -ne 0 ]]; then
  printf '%s\\n' "${GH_ERR:-gh failed}" >&2
  exit "${GH_RC}"
fi
"""

# The step runs on ubuntu-latest and encodes with the coreutils form ``base64 -w0 FILE``. BSD/macOS base64
# refuses that FILE operand, so on CI's macOS unit leg the step would stop at its encode, before gh. Where
# this runner's base64 fails a probe of exactly that form, the cases get this stand-in; any other argv exits
# non-zero, so a changed invocation is not silently emulated. Linux always runs the real base64.
_BASE64_W0_STAND_IN = """\
#!/usr/bin/env python3
import base64
import sys

if len(sys.argv) != 3 or sys.argv[1] != "-w0":
    sys.exit("base64 stand-in emulates only `base64 -w0 FILE`, got " + repr(sys.argv[1:]))
with open(sys.argv[2], "rb") as fh:
    sys.stdout.write(base64.b64encode(fh.read()).decode("ascii"))
"""


def _base64_runs_the_steps_form(scratch: Path) -> bool:
    """Whether this runner's base64 runs ``base64 -w0 FILE`` on a one-byte file, judged by its output."""
    probe = scratch / "base64-probe"
    probe.mkdir()
    (probe / "requirements.lock").write_bytes(b"x")
    try:
        proc = subprocess.run(["base64", "-w0", "requirements.lock"], cwd=probe, capture_output=True, text=True, check=False, timeout=10)  # nosec B603 B607 - capability probe, fixed argv
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout == "eA=="


def _step_script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    found = [step for step in doc["jobs"]["update-lockfile"]["steps"] if step.get("name") == STEP_NAME]
    assert len(found) == 1, f"expected one step named {STEP_NAME!r}, found {len(found)}"
    return found[0]["run"]


def _relocated(script: str, scratch: Path) -> str:
    """The step with its runner-``/tmp/`` files moved into ``scratch``; a ``/tmp`` path left over is refused."""
    assert RUNNER_TMP in script, "the step no longer writes under /tmp/; drop the relocation"
    executed = script.replace(RUNNER_TMP, f"{scratch}/")
    assert "/tmp" not in executed.replace(str(scratch), ""), "the step names a /tmp path the relocation does not cover"
    return executed


def _write_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _git(repo: Path, *args: str) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(repo.parent), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    proc = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=False)  # nosec B603 B607 - git in the test's own repository
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


class _Run:
    """One run of the step on a repository whose ``requirements.lock`` was regenerated."""

    def __init__(self, proc: subprocess.CompletedProcess[str], scratch: Path, head: str, gh_log: Path) -> None:
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr
        self.payload = scratch / "lockfile-commit.json"
        self.head = head
        self.gh = gh_log.read_text(encoding="utf-8") if gh_log.is_file() else ""

    @property
    def combined(self) -> str:
        return self.out + self.err


def _run(tmp_path: Path, *, gh_stdout: str = "", gh_rc: int = 0, gh_err: str = "gh failed") -> _Run:
    scratch = tmp_path / "runner-tmp"
    scratch.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    for name in LOCKS:
        (repo / name).write_bytes(f"# {name}\npackage==1.2.3\n".encode("utf-8"))
    _git(repo, "add", *LOCKS)
    _git(repo, "commit", "-q", "-m", "base")
    head = _git(repo, "rev-parse", "HEAD")
    (repo / LOCKS[0]).write_bytes(REGENERATED)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "gh", _GH)
    if not sys.platform.startswith("linux") and not _base64_runs_the_steps_form(tmp_path):
        _write_exe(bin_dir / "base64", _BASE64_W0_STAND_IN)
    script = tmp_path / "step.sh"
    script.write_text(_relocated(_step_script(), scratch), encoding="utf-8")
    gh_log = tmp_path / "gh.log"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path),
        "LANG": "C",
        "GH_TOKEN": TOKEN,
        "GH_LOG": str(gh_log),
        "GH_STDOUT": gh_stdout,
        "GH_RC": str(gh_rc),
        "GH_ERR": gh_err,
        "GITHUB_REPOSITORY": REPO_NAME,
        "BRANCH": BRANCH,
    }
    proc = subprocess.run(["bash", "-e", str(script)], cwd=repo, env=env, capture_output=True, text=True, check=False, timeout=60)  # nosec B603 B607 - bash runs the extracted workflow step
    assert TOKEN not in proc.stdout + proc.stderr, "the commit step printed the token"
    return _Run(proc, scratch, head, gh_log)


def test_a_success_prints_what_it_printed_before(tmp_path: Path) -> None:
    """A signed commit: exit 0, the notices and the commit URL on stdout and nothing else, and one request carries both locks."""
    run = _run(tmp_path, gh_stdout=json.dumps(SIGNED))
    assert run.code == 0, run.combined
    assert run.out == SUCCESS_OUT
    assert run.err == ""
    change = json.loads(run.payload.read_text(encoding="utf-8"))["variables"]["input"]
    assert change["expectedHeadOid"] == run.head
    assert change["branch"] == {"repositoryNameWithOwner": REPO_NAME, "branchName": BRANCH}
    additions = change["fileChanges"]["additions"]
    assert [addition["path"] for addition in additions] == list(LOCKS)
    assert base64.b64decode(additions[0]["contents"]) == REGENERATED
    for addition in additions[1:]:
        assert base64.b64decode(addition["contents"]) == f"# {addition['path']}\npackage==1.2.3\n".encode("utf-8")
    assert run.gh.startswith(f"gh\tapi\tgraphql\t--input\t{run.payload}")


def test_a_graphql_error_that_fails_gh_prints_the_steps_diagnostic(tmp_path: Path) -> None:
    """The real CLI's shape: the ``errors`` body on stdout, ``gh: <message>`` on stderr, exit 1.

    A bare ``gh api graphql`` under ``set -e`` ended the step at that exit, so the step's own
    ``createCommitOnBranch failed`` diagnostic never printed.
    """
    body = {"data": {"createCommitOnBranch": None}, "errors": [{"type": "STALE_DATA", "message": STALE}]}
    run = _run(tmp_path, gh_stdout=json.dumps(body), gh_rc=1, gh_err=f"gh: {STALE}")
    assert run.code == 1, run.combined
    assert f"gh: {STALE}" in run.err
    assert "::error::createCommitOnBranch failed" in run.out
    assert NOT_COMMITTED in run.out
    assert "STALE_DATA" in run.out
    assert "gh exited 1" in run.out
    assert "re-run this job" in run.out
    assert "gh api graphql failed" not in run.combined
    assert "Signed lockfile commit" not in run.combined
    assert run.gh.startswith("gh\t")


@pytest.mark.parametrize(
    ("gh_stdout", "gh_err", "printed", "names_the_token"),
    [
        ("<html>502 Bad Gateway</html>\n", "gh: HTTP 502", "empty or not JSON", False),
        (json.dumps({"message": "Bad credentials", "status": "401"}), "gh: Bad credentials (HTTP 401)", '"Bad credentials"', True),
        ("", "error connecting to api.github.com", "empty or not JSON", False),
    ],
    ids=["http-502-html", "http-401-json", "no-response"],
)
def test_an_http_failure_prints_that_the_commit_is_unknown(tmp_path: Path, gh_stdout: str, gh_err: str, printed: str, names_the_token: bool) -> None:
    """No GraphQL ``errors``: the request failed at the HTTP level or before any response.

    The log alone cannot show whether a commit landed (an HTTP error is not proof that the mutation did
    not run), so the step does not say nothing was committed.
    """
    run = _run(tmp_path, gh_stdout=gh_stdout, gh_rc=1, gh_err=gh_err)
    assert run.code == 1, run.combined
    assert gh_err in run.err
    assert "::error::gh api graphql failed (exit 1)" in run.out
    assert "cannot show whether the lock commit landed" in run.out
    assert printed in run.out
    assert f"Check {BRANCH} for the lock commit" in run.out
    assert ("CROSS_REPO_DISPATCH_TOKEN is invalid or expired" in run.out) is names_the_token
    assert "createCommitOnBranch failed" not in run.combined
    assert "Signed lockfile commit" not in run.combined


def test_gh_output_is_printed_with_the_token_masked(tmp_path: Path) -> None:
    """What gh printed reaches the log through the step's mask; ``_run`` refuses any output that holds ``TOKEN``."""
    message = f"token {TOKEN} lacks access ({TOKEN})"
    run = _run(tmp_path, gh_stdout=json.dumps({"errors": [{"type": "FORBIDDEN", "message": message}]}), gh_rc=1, gh_err=f"gh: {message}")
    assert run.code == 1, run.combined
    assert "gh: token *** lacks access (***)" in run.err
    assert "token *** lacks access (***)" in run.out
    assert "createCommitOnBranch failed" in run.out


def test_an_http_failure_body_is_printed_with_the_token_masked(tmp_path: Path) -> None:
    """The HTTP-failure branch prints a JSON body through the same mask as gh's message."""
    run = _run(tmp_path, gh_stdout=json.dumps({"message": f"bad token {TOKEN}", "status": "403"}), gh_rc=1, gh_err=f"gh: bad token {TOKEN} (HTTP 403)")
    assert run.code == 1, run.combined
    assert "gh: bad token *** (HTTP 403)" in run.err
    assert "gh api graphql failed (exit 1)" in run.out
    assert '"bad token ***"' in run.out


@pytest.mark.parametrize(
    ("gh_rc", "gh_stdout", "printed"),
    [
        (4, "", "gh api graphql failed (exit 4)"),
        (0, json.dumps({"errors": [{"type": "X"}]}), "gh exited 0"),
    ],
    ids=["exit-4-no-token", "exit-0-errors-without-a-message"],
)
def test_the_diagnostic_names_the_exit_status_gh_gave(tmp_path: Path, gh_rc: int, gh_stdout: str, printed: str) -> None:
    """Both diagnostics report gh's own exit status, and the step exits 1 whatever that was.

    gh exits 4 when it has no usable token (cli/cli ``internal/ghcmd/cmd.go``, ``exitAuth``), and 0 on
    an ``errors`` body that carries no message.
    """
    run = _run(tmp_path, gh_stdout=gh_stdout, gh_rc=gh_rc, gh_err="gh: set the GH_TOKEN environment variable")
    assert run.code == 1, run.combined
    assert printed in run.out
    assert "Signed lockfile commit" not in run.combined
