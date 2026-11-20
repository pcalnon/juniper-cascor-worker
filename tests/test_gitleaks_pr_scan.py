"""Pin the Security Scans job's Gitleaks wiring: one engine on every event, and a pull request scanned over its whole range.

gitleaks-action v3.0.0 lists a pull request's commits with one unpaginated API call (30 per page,
oldest first) and scans ``--no-merges --first-parent <first>^..<last>`` across that page, so it
never reaches the 31st commit, and, at any length, it drops every commit a merge brought into the
branch (juniper-data#530; ruling 10 in section 8 of juniper-ml's
notes/JUNIPER_2026-11-06_JUNIPER-ECOSYSTEM_CURSOR-FLOOD-4-DISPOSITION.md ports that fix here).
ci.yml therefore skips the action on ``pull_request`` and runs two steps of its own: an install of
the same 8.24.3 engine, checked against the release's SHA-256, and a scan of ``base..head`` from the
event payload, with ``--remerge-diff`` so that what a two-parent merge commit itself changed (a
conflict resolution, a file added during the merge) is scanned too. git prints no such patch for an
octopus merge, so the scan refuses a range that holds one. It also hands the engine a ``git`` that
deletes the ``remerge ...`` notes git writes into a merge's file headers: gitleaks 8.24.3's patch
parser otherwise names such a finding ``b/<path>``, and when a note holds the word "commit" drops
the merge's SHA from it, so no commit-scoped ``.gitleaksignore`` entry can match it.

The static cases pin that wiring, and the engine version on the action step, which ``push`` and
``workflow_dispatch`` still run: the two paths must not drift apart. The rehearsals run the scan
step's own ``run:`` block under ``bash -e``, the default shell for a step that names none, in a
hermetic repository: with a stand-in ``gitleaks`` that records its argv and exits with the status
under test, or that runs ``git log`` the way the engine does, and with the real engine. The engine
has to find a token in the 1st and the 35th commit of a 35-commit range, one a merge brought in,
and one that only a merge commit's own changes hold, under the merge's SHA and the file's own path
even when the conflict note says "commit", and it has to pass a clean range whose BASE commit holds
a token and a clean merge of the base branch whose side holds one.

This repository has no ``.gitleaks.toml`` and no ``.gitleaksignore``, so its scan runs the engine's
built-in ruleset. The hermetic repository carries whichever of the two files the repository root
holds, so a config added later is the one these cases load: a config that loaded no rule would
turn every real-engine case that expects a finding red.

The real-engine cases run the gitleaks binary (``GITLEAKS_BIN``, else ``gitleaks`` on PATH) on
tokens ASSEMBLED AT RUNTIME, so this file holds no literal that gitleaks or GitHub push protection
would flag. They skip without a binary, except in ci.yml's Security Scans job, which runs this file
with ``GITLEAKS_PARITY_REQUIRED=1`` after gitleaks-action, or on a pull request the ``Install
Gitleaks`` step, has put the binary on PATH: a check that could not run is not a pass. That job installs
nothing a test needs before pip-audit, so one step after pip-audit installs the package with its ``test`` extra
(tests/conftest.py imports the package) for the self-test.

Project: juniper-cascor-worker
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import string
import subprocess  # nosec B404 -- runs gitleaks, git and the workflow's own extracted shell with a fixed argv
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit]

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
THIS_FILE = "tests/test_gitleaks_pr_scan.py"
#: The two files gitleaks auto-discovers at a repository's root. This repository has neither.
GITLEAKS_FILES = (".gitleaks.toml", ".gitleaksignore")
#: The engine gitleaks-action v3.0.0 installs by default, pinned in ci.yml as GITLEAKS_VERSION on both paths.
ENGINE_VERSION = "8.24.3"
#: The events gitleaks-action v3.0.0 accepts (src/index.js at the pinned SHA); it exits 1 on any other.
ACTION_EVENTS = {"push", "pull_request", "workflow_dispatch", "schedule"}
ENTRY = re.compile(r"[0-9a-f]{40}:[^:\s]+:[a-z0-9-]+:[0-9]+")
INSTALL_STEP = "Install Gitleaks (pull request)"
PR_SCAN_STEP = "Run Gitleaks over the pull request (Secrets Detection)"
ON_PULL_REQUEST = "github.event_name == 'pull_request'"
UPLOAD_STEP = "Upload Security Reports"
#: The self-test step's whole command: an `|| true`, a -k or a --deselect after it would let the real-engine cases fail or never run.
SELF_TEST_COMMAND = "python -m pytest tests/test_gitleaks_pr_scan.py -v -v --timeout=120"
#: The step that installs what the self-test imports, whole: the package, its dependencies and its `test` extra.
SELF_TEST_INSTALL = 'pip install -e ".[test]"'
PIP_AUDIT_STEP = "Run pip-audit (Dependency Vulnerabilities)"
#: The install step's digest line, whole: the pinned digest against the downloaded file, and nothing after it.
DIGEST_CHECK = 'echo "${GITLEAKS_SHA256}  ${RUNNER_TEMP}/${asset}" | sha256sum --check --strict'
#: The digest the pull-request install checks: the linux_x64 line of the v8.24.3 release's gitleaks_8.24.3_checksums.txt.
ENGINE_LINUX_X64_SHA256 = "9991e0b2903da4c8f6122b5c3186448b927a5da4deef1fe45271c3793f4ee29c"
#: gitleaks-action v3.0.0's own argv (src/gitleaks.js Scan()) with the report under reports/security/; --log-opts follows.
PR_SCAN_ARGV = ["detect", "--redact", "-v", "--exit-code=2", "--report-format=sarif", "--report-path=reports/security/gitleaks.sarif", "--log-level=debug"]
#: Where the action's first API page ends: GitHub's default per_page for GET /repos/{Overtoad}/{repo}/pulls/{n}/commits.
ACTION_PAGE = 30
#: The colour codes gitleaks -v may wrap around a finding's lines.
ANSI = re.compile(r"\x1b\[[0-9;]*m")

_ALPHABET = string.ascii_letters + string.digits


def _fabricated_github_pat(step: int = 29) -> str:
    """A GitHub-PAT-SHAPED value from a fixed-step walk over the alphabet: deterministic, never a credential.

    ``step`` is coprime to the alphabet's 62 characters (29, 37, 41, 43, 47, 53, 59), so each value has 36 distinct characters.
    """
    return "gh" + "p_" + "".join(_ALPHABET[(11 + i * step) % len(_ALPHABET)] for i in range(36))


def _workflow() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) reads the bare `on:` key as boolean True.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def _security_steps() -> list[dict]:
    return _workflow()["jobs"]["security"]["steps"]


def _index(steps: list[dict], name: str) -> int:
    found = [i for i, s in enumerate(steps) if s.get("name") == name]
    assert len(found) == 1, f"expected exactly one Security Scans step named {name!r}, found {len(found)}"
    return found[0]


def _action_index(steps: list[dict]) -> int:
    return next(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("gitleaks/gitleaks-action@"))


def test_the_unit_lane_selects_this_file() -> None:
    # Two lanes run this file. The Security Scans self-test names it. The unit job reaches it only because its one
    # pytest command collects all of tests/ with no filter: an -m, -k, --ignore or --deselect added there could drop
    # this file from every unit leg while the job stayed green. Such an edit fails here until this pin is changed on
    # purpose. The `unit` mark keeps the file in `pytest tests/ -m unit`, the documented unit run.
    assert "unit" in {mark.name for mark in pytestmark}
    runs = [str(s["run"]) for s in _workflow()["jobs"]["unit-tests"]["steps"] if "python -m pytest" in str(s.get("run", ""))]
    assert len(runs) == 1, f"expected exactly one pytest command in the unit-tests job, found {len(runs)}"
    command = runs[0][runs[0].index("python -m pytest") :].replace("\\\n", " ").splitlines()[0]
    argv = shlex.split(command)[3:]
    assert "tests/" in argv, f"the unit lane no longer collects tests/: {argv}"
    filters = [arg for arg in argv if arg in ("-m", "-k") or arg.startswith(("-m=", "-k=", "--ignore", "--deselect"))]
    assert not filters, f"the unit lane gained a filter that may deselect {THIS_FILE}: {filters}"


def test_ci_pins_the_engine_and_requires_the_real_engine_run() -> None:
    steps = _security_steps()
    action = _action_index(steps)
    # Unset, the action falls back to its own default: a bump of the action SHA would then move the engine on push and
    # workflow_dispatch while the pull-request install stayed where it is.
    assert str(steps[action].get("env", {}).get("GITLEAKS_VERSION")) == ENGINE_VERSION
    runs = [s for s in steps[action + 1 :] if THIS_FILE in str(s.get("run", ""))]
    assert runs, f"no Security Scans step after the gitleaks action runs {THIS_FILE}"
    assert all(str(s.get("env", {}).get("GITLEAKS_PARITY_REQUIRED")) == "1" for s in runs), "the real-engine run must set GITLEAKS_PARITY_REQUIRED=1"
    # On every event of the workflow one of the two paths has put the binary on PATH, so the run needs no condition,
    # and a failure in it must fail the job.
    assert all("if" not in s and "continue-on-error" not in s for s in runs), "the real-engine run must be unconditional and blocking"
    assert [str(s["run"]).strip() for s in runs] == [SELF_TEST_COMMAND], "the real-engine run must be this command and nothing more"
    # `Security Scans` is a required check under that name. A job-level `if` reports a skipped job as passed, and a
    # job-level continue-on-error lets a failed scan pass the run.
    job = _workflow()["jobs"]["security"]
    assert job.get("name") == "Security Scans"
    assert "if" not in job and "continue-on-error" not in job, "the job must run on every event, and its failure must fail the run"


def test_the_self_test_installs_what_it_imports_after_pip_audit() -> None:
    # tests/conftest.py imports the package, and this job installs no pytest before pip-audit, so one step installs the
    # package with its `test` extra for the self-test. It comes after pip-audit: torch is then the CPU build pip-audit's
    # step installed, which `torch>=2.10.0` accepts (an earlier `.[test]` would pull torch from PyPI), and pip-audit has
    # already frozen and audited its requirements, so the self-test changes nothing that the audit covers.
    steps = _security_steps()
    pip_audit = _index(steps, PIP_AUDIT_STEP)
    installs = [i for i, s in enumerate(steps) if str(s.get("run", "")).strip() == SELF_TEST_INSTALL]
    assert len(installs) == 1, f"expected exactly one Security Scans step that runs {SELF_TEST_INSTALL!r}, found {len(installs)}"
    self_test = next(i for i, s in enumerate(steps) if THIS_FILE in str(s.get("run", "")))
    assert pip_audit < installs[0] < self_test, "pip-audit, then the self-test's install, then the self-test"
    assert not any(".[test]" in str(s.get("run", "")) for s in steps[: pip_audit + 1]), "the `test` extra must not be installed before pip-audit has run"


def test_the_action_no_longer_scans_a_pull_request() -> None:
    # Its pull_request path never reaches past the 30th commit, and at any length its --first-parent walk drops what a
    # merge brought in; the two steps pinned below scan a pull request instead.
    steps = _security_steps()
    assert steps[_action_index(steps)].get("if") == "github.event_name != 'pull_request'"
    events = set(_workflow()["on"])
    assert "pull_request" in events, "ci.yml no longer runs on pull_request, so the pull-request scan below never runs"
    # The action step has no other condition: an event it rejects (repository_dispatch, merge_group) would fail the job
    # there, and leave the self-test without a binary.
    assert events <= ACTION_EVENTS, f"ci.yml gained an event gitleaks-action exits 1 on: {sorted(events - ACTION_EVENTS)}"


def test_a_pull_request_installs_the_same_engine_checked_by_digest() -> None:
    steps = _security_steps()
    install = steps[_index(steps, INSTALL_STEP)]
    assert install.get("if") == ON_PULL_REQUEST
    assert "continue-on-error" not in install
    env = install.get("env", {})
    assert str(env.get("GITLEAKS_VERSION")) == ENGINE_VERSION, "the pull-request engine must be the version the action runs on every other event"
    assert str(env.get("GITLEAKS_SHA256")) == ENGINE_LINUX_X64_SHA256, "a version bump moves the digest too: copy the linux_x64 line of the release's checksums file"
    run = str(install["run"])
    assert "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/" in run
    assert DIGEST_CHECK in [line.strip() for line in run.splitlines()], "the tarball must be checked against the pinned digest, and a mismatch must stop the step"
    assert run.index("sha256sum --check") < run.index("tar -xzf"), "the digest check must come before the unpack"
    assert '>> "${GITHUB_PATH}"' in run, "the pull-request scan and the self-test find the binary on PATH"
    assert not re.search(r"\|\s*(?:ba|z)?sh\b", run), "a download is never piped into a shell"


def test_the_pull_request_scan_reads_its_range_from_the_event() -> None:
    steps = _security_steps()
    scan = steps[_index(steps, PR_SCAN_STEP)]
    assert scan.get("if") == ON_PULL_REQUEST
    assert "continue-on-error" not in scan, "a leak must fail the job"
    assert scan.get("env") == {
        "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
        "PR_COMMITS": "${{ github.event.pull_request.commits }}",
    }
    # The rehearsals below run the step under `bash -e`, which is the default only when the step names no shell.
    assert "shell" not in scan
    assert "--first-parent" not in str(scan["run"]), "--first-parent drops every commit a merge brought into the branch"
    self_test = next(i for i, s in enumerate(steps) if THIS_FILE in str(s.get("run", "")))
    order = [_action_index(steps), _index(steps, INSTALL_STEP), _index(steps, PR_SCAN_STEP), self_test]
    assert order == sorted(order), "the action, then the install, then the scan, then the self-test that needs the binary"
    # The scan writes its report and then fails on a leak: the upload has to run anyway, and take the report's directory.
    upload = steps[_index(steps, UPLOAD_STEP)]
    assert upload.get("if") == "always()" and upload.get("with", {}).get("path") == "reports/security/", "a failed scan must still upload its report"
    assert _index(steps, UPLOAD_STEP) > _index(steps, PR_SCAN_STEP)


def test_the_security_checkout_fetches_every_commit() -> None:
    # base..head must resolve in the checkout, and the workflow_dispatch --all scan must see all of history.
    steps = _security_steps()
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout.get("with", {}).get("fetch-depth") == 0


@pytest.fixture
def gitleaks_bin() -> str:
    found = os.environ.get("GITLEAKS_BIN") or shutil.which("gitleaks")
    if found is None:
        if os.environ.get("GITLEAKS_PARITY_REQUIRED") == "1":
            pytest.fail("GITLEAKS_PARITY_REQUIRED=1 but no gitleaks binary (GITLEAKS_BIN unset, none on PATH)")
        pytest.skip("no gitleaks binary (set GITLEAKS_BIN, or put gitleaks on PATH)")
    return found


def _git(repo: Path, *args: str, ok: tuple[int, ...] = (0,)) -> str:
    # HOME is the test's own directory and the system file is off, so no user or system config (signing, hooks) applies.
    # ``ok`` names the exit codes the caller expects: a merge that has to stop on a conflict passes (1,).
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(repo.parent),
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    res = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, timeout=60, check=False)  # nosec B603 B607
    assert res.returncode in ok, f"git {' '.join(args)} exited {res.returncode}, expected {ok}: {res.stdout}{res.stderr}"
    return res.stdout.strip()


def _write(repo: Path, rel: str, content: str | bytes) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _commit(repo: Path, rel: str, content: str | bytes, subject: str | None = None) -> str:
    _write(repo, rel, content)
    _git(repo, "add", "--", rel)
    _git(repo, "commit", "--no-verify", "-q", "-m", subject or rel)
    return _git(repo, "rev-parse", "HEAD")


def _pr_fixture(tmp_path: Path) -> tuple[Path, str]:
    """A root commit with whichever gitleaks files this repo's root holds (none today), then the BASE commit, which adds a token no range may include.

    The base has a parent, so an off-by-one range (``base^..head``) would reach the token instead of failing to resolve.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo, "README.md", "a scratch repository for the pull-request scan rehearsals\n")
    tracked = ["README.md"]
    for name in GITLEAKS_FILES:
        if (REPO / name).is_file():
            shutil.copyfile(REPO / name, repo / name)
            tracked.append(name)
    _git(repo, "add", "--", *tracked)
    _git(repo, "commit", "--no-verify", "-q", "-m", "root")
    base = _commit(repo, "base/token.txt", "GITHUB_TOKEN=" + _fabricated_github_pat(43) + "\n")
    return repo, base


def _linear_range(repo: Path, count: int, tokens: dict[int, str]) -> list[str]:
    """``count`` commits on top of HEAD, commit ``i`` adding a token when ``i`` is in ``tokens``; returns the SHAs, oldest first."""
    return [_commit(repo, f"pr/commit-{i:02d}.txt", ("GITHUB_TOKEN=" + tokens[i] if i in tokens else f"filler {i}") + "\n") for i in range(1, count + 1)]


def _run_scan_step(tmp_path: Path, repo: Path, bindir: Path, base: str, head: str, pr_commits: str) -> subprocess.CompletedProcess[str]:
    """Run the pull-request scan step's own shell in ``repo``, as GitHub does, with ``bindir`` (holding ``gitleaks``) first on PATH."""
    steps = _security_steps()
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    env = {
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
        "HOME": str(tmp_path),
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "BASE_SHA": base,
        "HEAD_SHA": head,
        "PR_COMMITS": pr_commits,
        "GITHUB_STEP_SUMMARY": str(tmp_path / "step-summary.md"),
        # GitHub sets it for every step; the scan writes its git filter there.
        "RUNNER_TEMP": str(runner_temp),
    }
    script = str(steps[_index(steps, PR_SCAN_STEP)]["run"])
    return subprocess.run(["bash", "-e", "-c", script], cwd=repo, env=env, capture_output=True, text=True, timeout=120, check=False)  # nosec B603 B607


def _stub_engine(tmp_path: Path, status: int) -> tuple[Path, Path]:
    """A stand-in ``gitleaks`` that records its argv, one per line, and exits ``status``."""
    bindir = tmp_path / "stub-bin"
    bindir.mkdir()
    argv_log = tmp_path / "gitleaks-argv.txt"
    stub = bindir / "gitleaks"
    stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {shlex.quote(str(argv_log))}\nexit {status}\n', encoding="utf-8")
    stub.chmod(0o755)
    return bindir, argv_log


def _git_log_engine(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A stand-in ``gitleaks`` that calls the ``git`` on its PATH as gitleaks 8.24.3 does: ``git log -p -U0`` with its
    ``--log-opts`` split on spaces (``sources/git.go``), saving what git printed, then ``git ls-remote --quiet --get-url``
    (``detect/git.go``), saving only its exit status, which gitleaks reads to tell a missing remote from a failure."""
    bindir = tmp_path / "git-log-bin"
    bindir.mkdir()
    seen = tmp_path / "engine-saw.txt"
    remote_status = tmp_path / "engine-remote-status.txt"
    script = '#!/bin/sh\nfor a in "$@"; do case "$a" in --log-opts=*) opts="${a#--log-opts=}" ;; esac; done\n'
    script += "git -C . log -p -U0 $opts > " + shlex.quote(str(seen)) + " || exit $?\n"
    script += "git ls-remote --quiet --get-url > /dev/null 2>&1; echo $? > " + shlex.quote(str(remote_status)) + "\n"
    stub = bindir / "gitleaks"
    stub.write_text(script, encoding="utf-8")
    stub.chmod(0o755)
    return bindir, seen, remote_status


def test_the_scan_step_hands_the_engine_the_whole_range(tmp_path: Path) -> None:
    repo, base = _pr_fixture(tmp_path)
    head = _linear_range(repo, 3, {})[-1]
    bindir, argv_log = _stub_engine(tmp_path, 0)
    res = _run_scan_step(tmp_path, repo, bindir, base, head, "3")
    assert res.returncode == 0, res.stdout + res.stderr
    # --remerge-diff is what gives a merge commit's own changes a patch; without it they are not scanned.
    assert argv_log.read_text(encoding="utf-8").splitlines() == [*PR_SCAN_ARGV, f"--log-opts=--remerge-diff {base}..{head}"]
    assert f"Scanning 3 commit(s) in {base}..{head}; the pull request reports 3." in res.stdout
    assert "::warning" not in res.stdout and "::error" not in res.stdout
    assert f"3 commit(s) scanned in {base}..{head}; gitleaks exited 0." in (tmp_path / "step-summary.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("engine_exit", "step_exit", "annotation"),
    [
        (0, 0, None),
        (2, 1, "::error title=Gitleaks::leaks detected in "),
        (1, 1, "::error title=Gitleaks::gitleaks exited 1, which is not a scan result"),
        (126, 126, "::error title=Gitleaks::gitleaks exited 126, which is not a scan result"),
    ],
    ids=["no-leaks", "leaks", "engine-error", "engine-not-executable"],
)
def test_the_scan_step_fails_the_way_the_action_does(tmp_path: Path, engine_exit: int, step_exit: int, annotation: str | None) -> None:
    # gitleaks-action (src/index.js): exit 2 (leaks) fails the step with 1; any other non-zero code fails it with that code.
    repo, base = _pr_fixture(tmp_path)
    head = _linear_range(repo, 1, {})[-1]
    bindir, _ = _stub_engine(tmp_path, engine_exit)
    res = _run_scan_step(tmp_path, repo, bindir, base, head, "1")
    assert res.returncode == step_exit, res.stdout + res.stderr
    if annotation is None:
        assert "::error" not in res.stdout
    else:
        assert annotation in res.stdout


@pytest.mark.parametrize("which", ["base-empty", "base-not-hex", "head-not-in-checkout"])
def test_the_scan_step_refuses_a_range_it_cannot_resolve(tmp_path: Path, which: str) -> None:
    # Fail closed before the engine runs: a scan of the wrong range, or of none, must not pass.
    repo, base = _pr_fixture(tmp_path)
    head = _linear_range(repo, 1, {})[-1]
    if which == "base-empty":
        base = ""
    elif which == "base-not-hex":
        base = "main"
    else:
        head = "0123456789abcdef0123456789abcdef01234567"
    bindir, argv_log = _stub_engine(tmp_path, 0)
    res = _run_scan_step(tmp_path, repo, bindir, base, head, "1")
    assert res.returncode == 1, res.stdout + res.stderr
    assert "is not a commit in this checkout, so the pull request cannot be scanned" in res.stdout
    assert not argv_log.exists(), "the engine ran on a range the step could not resolve"


def test_the_scan_step_warns_when_the_range_and_the_pull_request_disagree(tmp_path: Path) -> None:
    repo, base = _pr_fixture(tmp_path)
    head = _linear_range(repo, 2, {})[-1]
    bindir, _ = _stub_engine(tmp_path, 0)
    res = _run_scan_step(tmp_path, repo, bindir, base, head, "3")
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"::warning title=Gitleaks::{base}..{head} holds 2 commit(s), and the pull request reports 3" in res.stdout


def test_the_scan_step_refuses_an_octopus_merge(tmp_path: Path) -> None:
    # git prints no --remerge-diff patch for a merge of three or more parents ("diff: warning: Skipping remerge-diff for
    # octopus merges." on stdout, exit 0), so what such a merge changed itself would pass unscanned: the step fails instead.
    repo, base = _pr_fixture(tmp_path)
    _commit(repo, "pr/p1.txt", "p1\n")
    for side in ("s1", "s2"):
        _git(repo, "checkout", "-q", "-b", side)
        _commit(repo, f"pr/{side}.txt", f"{side}\n")
        _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "--no-ff", "--no-verify", "-q", "-m", "octopus", "s1", "s2")
    head = _git(repo, "rev-parse", "HEAD")
    bindir, argv_log = _stub_engine(tmp_path, 0)
    res = _run_scan_step(tmp_path, repo, bindir, base, head, "4")
    assert res.returncode == 1, res.stdout + res.stderr
    assert f"::error title=Gitleaks::{base}..{head} holds 1 octopus merge(s)" in res.stdout
    assert not argv_log.exists(), "the engine ran on a range that holds an octopus merge"


def _merge_whose_conflict_note_says_commit(tmp_path: Path, note: str, added_line: str) -> tuple[Path, str, str, str]:
    """A pull request that merges its base branch in over a conflict whose ``--remerge-diff`` note holds the word "commit".

    ``note`` is where the word is: ``conflicted-path`` conflicts in ``.pre-commit-config.yaml``, which the note names;
    ``parent-subject`` conflicts in a binary file under a pull-request tip whose subject is "chore: pre-commit
    autoupdate", which git quotes in that note. The merge resolves the conflict, writing ``added_line`` into the
    resolution when the file is text, and adds ``zz/added-in-the-merge.txt`` holding ``added_line``, a later file of
    the same merge. Returns (repo, base, merge, head); base..head is the pull request's three commits.
    """
    repo, _ = _pr_fixture(tmp_path)
    rel = ".pre-commit-config.yaml" if note == "conflicted-path" else "data/blob.bin"
    tip_subject = None if note == "conflicted-path" else "chore: pre-commit autoupdate"
    # The file's start, the pull request's side, the base branch's side, and the merge's resolution.
    sides: dict[str, tuple[str | bytes, ...]] = {
        "conflicted-path": ("repos:\n- rev: v1\n  id: x\n", "repos:\n- rev: v2-pr\n  id: x\n", "repos:\n- rev: v2-base\n  id: x\n", "repos:\n- rev: v2-base\n" + added_line + "  id: x\n"),
        "parent-subject": (b"\x00start\xff" * 8, b"\x00pr\xfe" * 8, b"\x00base\xfd" * 8, b"\x00resolved\xfc" * 8),
    }
    start, pr_side, base_side, resolution = sides[note]
    _commit(repo, rel, start)
    _git(repo, "checkout", "-q", "-b", "pr")
    _commit(repo, rel, pr_side, tip_subject)
    _git(repo, "checkout", "-q", "-")
    base = _commit(repo, rel, base_side)
    _git(repo, "checkout", "-q", "pr")
    # The merge has to stop on the conflict, or what is committed below is not a conflict resolution.
    _git(repo, "merge", "--no-ff", "--no-verify", "-q", "-m", "merge the base branch", base, ok=(1,))
    _write(repo, rel, resolution)
    _write(repo, "zz/added-in-the-merge.txt", added_line)
    _git(repo, "add", "--", rel, "zz/added-in-the-merge.txt")
    _git(repo, "commit", "--no-verify", "-q", "-m", "merge the base branch")
    merge = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, "pr/p2.txt", "p2\n")
    return repo, base, merge, head


def test_the_scan_step_gives_the_engine_a_git_without_remerge_notes(tmp_path: Path) -> None:
    # gitleaks 8.24.3 runs `git log -p -U0 <--log-opts>` through the git on its PATH. The step puts a git there that
    # deletes --remerge-diff's `remerge ...` notes and nothing else: the rest of the log reaches the engine unchanged, and
    # so does git's exit status, which gitleaks reads from `git ls-remote --get-url` (128 here: the repository has no remote).
    repo, base, _, head = _merge_whose_conflict_note_says_commit(tmp_path, "conflicted-path", "resolved=1  # never remerge by hand\n")
    plain = _git(repo, "log", "-p", "-U0", "--remerge-diff", f"{base}..{head}").splitlines()
    assert any(line.startswith("remerge CONFLICT") for line in plain), "this git wrote no remerge note, so the case below would pin nothing"
    _git(repo, "ls-remote", "--quiet", "--get-url", ok=(128,))
    bindir, seen, remote_status = _git_log_engine(tmp_path)
    res = _run_scan_step(tmp_path, repo, bindir, base, head, "3")
    assert res.returncode == 0, res.stdout + res.stderr
    engine_saw = seen.read_text(encoding="utf-8").splitlines()
    assert "+resolved=1  # never remerge by hand" in engine_saw, "the merge commit's own change must still reach the engine, the word remerge in it included"
    assert engine_saw == [line for line in plain if not line.startswith("remerge ")]
    assert remote_status.read_text(encoding="utf-8").strip() == "128", "the engine's git must exit as git does"


def _real_engine(tmp_path: Path, gitleaks_bin: str) -> Path:
    bindir = tmp_path / "engine-bin"
    bindir.mkdir()
    (bindir / "gitleaks").symlink_to(Path(gitleaks_bin).resolve())
    return bindir


def _reported(repo: Path) -> set[tuple[str, str]]:
    """``{(commit, file)}`` for each finding in the scan step's SARIF report, which has to be redacted."""
    with open(repo / "reports" / "security" / "gitleaks.sarif", encoding="utf-8") as fh:
        results = json.load(fh)["runs"][0].get("results") or []
    assert all(r["locations"][0]["physicalLocation"]["region"]["snippet"]["text"] == "REDACTED" for r in results), "the report was not redacted"
    return {(r["partialFingerprints"]["commitSha"], r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]) for r in results}


def _reported_commits(repo: Path) -> set[str]:
    return {commit for commit, _ in _reported(repo)}


def test_real_engine_scan_step_finds_a_token_past_the_actions_first_page(gitleaks_bin: str, tmp_path: Path) -> None:
    # The action's page is commits 1-30; a token in commit 35 is what it missed. Commit 1 pins the range's other end.
    repo, base = _pr_fixture(tmp_path)
    shas = _linear_range(repo, ACTION_PAGE + 5, {1: _fabricated_github_pat(29), ACTION_PAGE + 5: _fabricated_github_pat(37)})
    res = _run_scan_step(tmp_path, repo, _real_engine(tmp_path, gitleaks_bin), base, shas[-1], str(len(shas)))
    assert res.returncode == 1, res.stdout + res.stderr
    assert f"Scanning {len(shas)} commit(s)" in res.stdout
    assert _reported_commits(repo) == {shas[0], shas[-1]}, "commit 1 and commit 35 must both be reported, and the base commit must not"


def test_real_engine_scan_step_finds_a_token_a_merge_brought_in(gitleaks_bin: str, tmp_path: Path) -> None:
    # The side-branch commit is in base..head but not on the head's first-parent chain, which is all the action walks.
    repo, base = _pr_fixture(tmp_path)
    _commit(repo, "pr/p1.txt", "p1\n")
    _git(repo, "checkout", "-q", "-b", "side")
    side = _commit(repo, "pr/side.txt", "GITHUB_TOKEN=" + _fabricated_github_pat(41) + "\n")
    _git(repo, "checkout", "-q", "-")
    _commit(repo, "pr/p2.txt", "p2\n")
    _git(repo, "merge", "--no-ff", "--no-verify", "-q", "-m", "merge side", "side")
    head = _commit(repo, "pr/p3.txt", "p3\n")
    res = _run_scan_step(tmp_path, repo, _real_engine(tmp_path, gitleaks_bin), base, head, "5")
    assert res.returncode == 1, res.stdout + res.stderr
    assert _reported_commits(repo) == {side}


@pytest.mark.parametrize("how", ["added-during-the-merge", "conflict-resolution"])
def test_real_engine_scan_step_finds_a_token_only_a_merge_commit_holds(gitleaks_bin: str, tmp_path: Path, how: str) -> None:
    # The pull request merges the base branch in, and neither parent holds the token: only the merge commit's own
    # changes do. `git log -p` alone prints no patch for a merge commit; --remerge-diff prints what the merge changed
    # beyond a plain re-merge of its parents, and gitleaks reports it under the merge's SHA.
    repo, _ = _pr_fixture(tmp_path)
    token_line = "GITHUB_TOKEN=" + _fabricated_github_pat(47) + "\n"
    _commit(repo, "conf/settings.txt", "a=1\nb=2\nc=3\n")
    _git(repo, "checkout", "-q", "-b", "pr")
    _commit(repo, "conf/settings.txt", "a=1\nb=PR\nc=3\n")
    _git(repo, "checkout", "-q", "-")
    if how == "conflict-resolution":
        base = _commit(repo, "conf/settings.txt", "a=1\nb=BASE\nc=3\n")
        _git(repo, "checkout", "-q", "pr")
        # The merge has to stop on the conflict, or what is committed below is not a conflict resolution.
        _git(repo, "merge", "--no-ff", "--no-verify", "-q", "-m", "merge the base branch", base, ok=(1,))
        (repo / "conf" / "settings.txt").write_text("a=1\nb=PR\n" + token_line + "c=3\n", encoding="utf-8")
        _git(repo, "add", "--", "conf/settings.txt")
    else:
        base = _commit(repo, "base/later.txt", "later\n")
        _git(repo, "checkout", "-q", "pr")
        _git(repo, "merge", "--no-ff", "--no-verify", "--no-commit", "-q", base)
        (repo / "pr").mkdir(exist_ok=True)
        (repo / "pr" / "added-in-the-merge.txt").write_text(token_line, encoding="utf-8")
        _git(repo, "add", "--", "pr/added-in-the-merge.txt")
    _git(repo, "commit", "--no-verify", "-q", "-m", "merge the base branch")
    merge = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, "pr/p2.txt", "p2\n")
    res = _run_scan_step(tmp_path, repo, _real_engine(tmp_path, gitleaks_bin), base, head, "3")
    assert res.returncode == 1, res.stdout + res.stderr
    assert "::warning" not in res.stdout, "base..head is the pull request's three commits, the merge among them"
    assert _reported_commits(repo) == {merge}, "the merge commit's own change must be reported, under the merge's SHA"


@pytest.mark.parametrize("note", ["conflicted-path", "parent-subject"])
def test_real_engine_scan_step_keeps_a_merge_findings_commit_and_path(gitleaks_bin: str, tmp_path: Path, note: str) -> None:
    # gitleaks 8.24.3 parses `git log` with go-gitdiff v0.9.1, which ends a file header at a --remerge-diff note and
    # re-reads any preamble that holds the word "commit" as a commit header. Unfiltered, a note naming
    # .pre-commit-config.yaml or quoting the subject "chore: pre-commit autoupdate" cost the merge's findings their
    # commit, and the conflicted file came back as b/<path>: a file-scoped Fingerprint that no .gitleaksignore entry can
    # match. Through the step's git filter each finding keeps both, so the documented remedy works: the Fingerprint
    # lines, written to a .gitleaksignore as they stand, clear the next run.
    line = "GITHUB_TOKEN=" + _fabricated_github_pat(59) + "\n"
    repo, base, merge, head = _merge_whose_conflict_note_says_commit(tmp_path, note, line)
    engine = _real_engine(tmp_path, gitleaks_bin)
    res = _run_scan_step(tmp_path, repo, engine, base, head, "3")
    assert res.returncode == 1, res.stdout + res.stderr
    files = {"zz/added-in-the-merge.txt"} | ({".pre-commit-config.yaml"} if note == "conflicted-path" else set())
    assert _reported(repo) == {(merge, f) for f in files}, "each finding in the merge's own changes must carry the merge's SHA and the file's own path"
    fingerprints = sorted(ln.split("Fingerprint:", 1)[1].strip() for ln in ANSI.sub("", res.stdout + res.stderr).splitlines() if "Fingerprint:" in ln)
    assert len(fingerprints) == len(files) and all(ENTRY.fullmatch(fp) and fp.startswith(merge + ":") for fp in fingerprints), f"not commit-scoped entries: {fingerprints}"
    # This repository has no .gitleaksignore; the remedy creates one, or appends to the one the fixture copied.
    ignore_file = repo / ".gitleaksignore"
    kept = ignore_file.read_text(encoding="utf-8") if ignore_file.is_file() else ""
    head = _commit(repo, ".gitleaksignore", kept + "# fabricated values a merge commit added (this test)\n" + "".join(fp + "\n" for fp in fingerprints))
    res = _run_scan_step(tmp_path, repo, engine, base, head, "4")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _reported(repo) == set()


def test_real_engine_scan_step_passes_a_clean_range(gitleaks_bin: str, tmp_path: Path) -> None:
    # The base commit holds a token, so a pass here also shows the scan starts after the base.
    repo, base = _pr_fixture(tmp_path)
    shas = _linear_range(repo, ACTION_PAGE + 5, {})
    res = _run_scan_step(tmp_path, repo, _real_engine(tmp_path, gitleaks_bin), base, shas[-1], str(len(shas)))
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"Scanning {len(shas)} commit(s)" in res.stdout
    assert _reported_commits(repo) == set()


def test_real_engine_scan_step_passes_a_clean_merge_of_the_base_branch(gitleaks_bin: str, tmp_path: Path) -> None:
    # The base branch gains a token, and the pull request merges the base branch in cleanly. The token is outside
    # base..head, and --remerge-diff prints nothing for a clean merge, where the merge's first-parent patch (-m, or
    # --diff-merges=first-parent) would carry the base branch's whole side into the scan.
    repo, _ = _pr_fixture(tmp_path)
    _git(repo, "checkout", "-q", "-b", "pr")
    _commit(repo, "pr/p1.txt", "p1\n")
    _git(repo, "checkout", "-q", "-")
    _commit(repo, "base/later-token.txt", "GITHUB_TOKEN=" + _fabricated_github_pat(53) + "\n")
    base = _commit(repo, "base/later.txt", "later\n")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "merge", "--no-ff", "--no-verify", "-q", "-m", "merge the base branch", base)
    head = _commit(repo, "pr/p2.txt", "p2\n")
    res = _run_scan_step(tmp_path, repo, _real_engine(tmp_path, gitleaks_bin), base, head, "3")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "::warning" not in res.stdout, "base..head is the pull request's three commits: p1, the merge and p2"
    assert _reported_commits(repo) == set()
