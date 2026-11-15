#!/usr/bin/env python3
"""Negative control for the pull-request Gitleaks scan: prove the tests/test_gitleaks_pr_scan.py cases can FAIL.

Project: juniper-cascor-worker
Sub-Project: ad-hoc tooling
Author: Paul Calnon
Created: 2026-11-14
Status: ad-hoc — investigation (negative control for the port of juniper-data#530; ruling 10 in section 8 of juniper-ml's notes/JUNIPER_2026-11-06_JUNIPER-ECOSYSTEM_CURSOR-FLOOD-4-DISPOSITION.md)
Retire when: the pull-request scan steps in ci.yml are replaced or removed.
Related: .github/workflows/ci.yml ("Install Gitleaks (pull request)", "Run Gitleaks over the pull request",
         "Install the package and its test extra (Gitleaks self-test)"), tests/test_gitleaks_pr_scan.py;
         the reproduction of the action's window is not copied here: juniper-data's
         util/ad-hoc/2026-11-08_reproduce_gitleaks_pr_commit_window.py and juniper-data-client's
         util/ad-hoc/2026-11-11_reproduce_gitleaks_pr_commit_window.py run the same scan step's shell

WHY THIS EXISTS
---------------
A test that passes against both the fixed and the broken workflow pins nothing. Each mutation below undoes one
property by an exact-match edit, runs the tests that must go red and the tests that must stay green, each test in a
pytest process of its own, then restores the file and proves the restore by SHA-256. Most mutations edit ci.yml.
One edits the test file's own mark, and one adds a `.gitleaks.toml` that loads no rule to the repository root,
which the hermetic repositories then carry.

The list is juniper-data-client's (its util/ad-hoc/2026-11-11_verify_gitleaks_pr_scan_tests_are_not_vacuous.py,
juniper-data-client#260), with four more at the end. The scan step's shell is juniper-data's, so the first fourteen
mutations are juniper-data's own (util/ad-hoc/2026-11-08_verify_gitleaks_pr_scan_tests_are_not_vacuous.py there).
The next undo what the port adds or pins differently: the engine version on the action step, the self-test step and
its required real-engine run, the unit lane's unfiltered `pytest tests/`, the events the workflow runs on, and each
remaining assertion of the static cases. Thirteen of those are on what keeps a failure blocking: `continue-on-error`
on the job, on the install or on the scan, a job-level `if`, the job's name (a required check), the self-test's
whole command, the whole digest line, the report upload (its `if: always()`, its path, its place after the scan),
and the anchor of the `git` filter's `sed` expression. The last four are this repository's: its security job
installs no pytest before pip-audit, so one step after pip-audit installs the package with its `test` extra for the
self-test, and they move that install ahead of pip-audit or behind the self-test, drop the extra, or add the extra
to the security tools' install.

The real-engine cases need a gitleaks 8.24.3 binary: set GITLEAKS_BIN. GITLEAKS_PARITY_REQUIRED=1 is forced, so a
missing binary turns the baseline red instead of skipping (a skip would score as a pass).

Run from the repo root, with an interpreter that holds the package and its `[test]` extra (tests/conftest.py imports
the package; the cases need pytest, pytest-asyncio, pytest-timeout and PyYAML)::

    GITLEAKS_BIN=<gitleaks 8.24.3> python util/ad-hoc/2026-11-14_verify_gitleaks_pr_scan_tests_are_not_vacuous.py --basetemp <dir> --backup <dir> [--workers 4] [--json <file>]

It edits ci.yml in place, so run nothing else that reads the workflow while it runs, and pass --backup when the
tree is uncommitted: the script restores each file in a `finally`, which an interrupt (SIGINT) runs and a kill does
not. With --backup it keeps a pristine copy of every file it is about to mutate, and it refuses to start when a
copy left by an earlier run differs from the file, which is what a run killed mid-mutation leaves behind.

Exit 0 when the baseline is green, every mutation is caught by every test listed for it, no listed survivor goes
red, and every restore is exact; exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess  # nosec B404 - runs pytest on fixed node ids
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CI = ".github/workflows/ci.yml"
TEST_FILE = "tests/test_gitleaks_pr_scan.py"
ZERO_RULE_CONFIG = ".gitleaks.toml"
T = TEST_FILE + "::"

LANE = T + "test_the_unit_lane_selects_this_file"
ENGINE_PIN = T + "test_ci_pins_the_engine_and_requires_the_real_engine_run"
SELF_INSTALL = T + "test_the_self_test_installs_what_it_imports_after_pip_audit"
ACTION_SKIPS_PR = T + "test_the_action_no_longer_scans_a_pull_request"
DIGEST = T + "test_a_pull_request_installs_the_same_engine_checked_by_digest"
EVENT_RANGE = T + "test_the_pull_request_scan_reads_its_range_from_the_event"
FETCH_DEPTH = T + "test_the_security_checkout_fetches_every_commit"
ARGV = T + "test_the_scan_step_hands_the_engine_the_whole_range"
NO_LEAKS = T + "test_the_scan_step_fails_the_way_the_action_does[no-leaks]"
LEAKS = T + "test_the_scan_step_fails_the_way_the_action_does[leaks]"
ENGINE_ERROR = T + "test_the_scan_step_fails_the_way_the_action_does[engine-error]"
NOT_EXECUTABLE = T + "test_the_scan_step_fails_the_way_the_action_does[engine-not-executable]"
REFUSE = [T + f"test_the_scan_step_refuses_a_range_it_cannot_resolve[{w}]" for w in ("base-empty", "base-not-hex", "head-not-in-checkout")]
WARN = T + "test_the_scan_step_warns_when_the_range_and_the_pull_request_disagree"
OCTOPUS = T + "test_the_scan_step_refuses_an_octopus_merge"
NOTES = T + "test_the_scan_step_gives_the_engine_a_git_without_remerge_notes"
PAST_PAGE = T + "test_real_engine_scan_step_finds_a_token_past_the_actions_first_page"
MERGE = T + "test_real_engine_scan_step_finds_a_token_a_merge_brought_in"
MERGE_OWN = [T + f"test_real_engine_scan_step_finds_a_token_only_a_merge_commit_holds[{w}]" for w in ("added-during-the-merge", "conflict-resolution")]
MERGE_KEEPS = [T + f"test_real_engine_scan_step_keeps_a_merge_findings_commit_and_path[{w}]" for w in ("conflicted-path", "parent-subject")]
CLEAN = T + "test_real_engine_scan_step_passes_a_clean_range"
CLEAN_MERGE = T + "test_real_engine_scan_step_passes_a_clean_merge_of_the_base_branch"

RANGE = '          range="${BASE_SHA}..${HEAD_SHA}"'
LOG_OPTS = '"--log-opts=--remerge-diff ${range}"'
ON_PR = "        if: github.event_name == 'pull_request'\n"
SELF_TEST_RUN = "        run: python -m pytest tests/test_gitleaks_pr_scan.py -v -v --timeout=120\n"
PARITY_ENV = '        env:\n          GITLEAKS_PARITY_REQUIRED: "1"\n'
UNIT_LANE = "            tests/ \\\n            --verbose \\\n            --timeout=60 \\\n"
SHA_CHECK = '          echo "${GITLEAKS_SHA256}  ${RUNNER_TEMP}/${asset}" | sha256sum --check --strict\n'
UNPACK = '          mkdir -p "${dest}"\n          tar -xzf "${RUNNER_TEMP}/${asset}" -C "${dest}" gitleaks\n'
JOB_HEAD = "  security:\n    name: Security Scans\n    runs-on: ubuntu-latest\n    needs: [pre-commit]\n"
UPLOAD_NAME = "      - name: Upload Security Reports\n"
PR_SCAN_NAME = "      - name: Run Gitleaks over the pull request (Secrets Detection)\n"
INSTALL_RUN = '        run: pip install -e ".[test]"\n'
PIP_AUDIT_NAME = "      - name: Run pip-audit (Dependency Vulnerabilities)\n"
SECURITY_TOOLS_PIP = '          pip install "setuptools>=82" "bandit[sarif]" pip-audit\n'


@dataclass
class Mutation:
    """One revert, plus the tests that must catch it and the tests it must leave green."""

    name: str
    edits: list[tuple[str, str]]  # (exact text in the file, replacement); each must match exactly once
    must_fail: list[str]
    must_still_pass: list[str] = field(default_factory=list)
    path: str = CI  # repo-relative; a path that does not exist is created from edits[0][1] and deleted afterwards


MUTATIONS = [
    # --- juniper-data's fourteen: the scan step's shell is the same ---
    Mutation("page cap: the range ends at the 30th commit", [(RANGE, '          range="${BASE_SHA}..$(git rev-list --reverse "${BASE_SHA}..${HEAD_SHA}" | head -n 30 | tail -n 1)"')], [PAST_PAGE, CLEAN], [MERGE, ARGV, *MERGE_OWN, CLEAN_MERGE]),
    Mutation("action's flags: --no-merges --first-parent back on the log options", [(LOG_OPTS, '"--log-opts=--no-merges --first-parent --remerge-diff ${range}"')], [EVENT_RANGE, MERGE, ARGV, *MERGE_OWN], [PAST_PAGE, CLEAN, CLEAN_MERGE]),
    Mutation("first-parent: --first-parent alone back on the log options", [(LOG_OPTS, '"--log-opts=--first-parent --remerge-diff ${range}"')], [EVENT_RANGE, MERGE, ARGV], [PAST_PAGE, CLEAN, CLEAN_MERGE, *MERGE_OWN]),
    Mutation("no remerge-diff: a merge commit's own changes go unscanned", [(LOG_OPTS, '"--log-opts=${range}"')], [ARGV, *MERGE_OWN], [EVENT_RANGE, MERGE, PAST_PAGE, CLEAN, CLEAN_MERGE]),
    Mutation("first-parent diff: a merge's first-parent patch in place of --remerge-diff", [(LOG_OPTS, '"--log-opts=--diff-merges=first-parent ${range}"')], [ARGV, CLEAN_MERGE, MERGE], [PAST_PAGE, CLEAN, *MERGE_OWN]),
    Mutation("off-by-one: base^..head", [(RANGE, '          range="${BASE_SHA}^..${HEAD_SHA}"')], [PAST_PAGE, CLEAN, ARGV], []),
    Mutation("leak passes: a leak passes the step", [('reports/security/gitleaks.sarif"\n              exit 1\n', 'reports/security/gitleaks.sarif"\n              exit 0\n')], [LEAKS, PAST_PAGE, MERGE], [ENGINE_ERROR, CLEAN]),
    Mutation("no SHA checks: the SHA checks removed", [('            if ! [[ "${sha}" =~ ^[0-9a-f]{40}$ ]] || ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then\n', "            if false; then\n")], REFUSE, [ARGV, WARN]),
    Mutation("action on PRs: the action scans pull requests again", [("        if: github.event_name != 'pull_request'\n", "")], [ACTION_SKIPS_PR], [EVENT_RANGE, ENGINE_PIN]),
    Mutation("no digest check: the tarball is unpacked without it", [(SHA_CHECK, "          true\n")], [DIGEST], [EVENT_RANGE]),
    Mutation("version drift: the pull-request install moves to another engine version", [('          GITLEAKS_VERSION: "8.24.3"\n          GITLEAKS_SHA256:', '          GITLEAKS_VERSION: "8.24.2"\n          GITLEAKS_SHA256:')], [DIGEST], [EVENT_RANGE, ENGINE_PIN]),
    Mutation("octopus passes: the octopus-merge refusal no longer stops the step", [('replace it with two-parent merges"\n            exit 1\n', 'replace it with two-parent merges"\n')], [OCTOPUS], [ARGV, MERGE, *MERGE_OWN, NOTES]),
    Mutation("no git filter: the engine reads git's remerge notes again", [('REAL_GIT="${real_git}" PATH="${filter}:${PATH}" gitleaks detect', "gitleaks detect")], [NOTES, *MERGE_KEEPS], [ARGV, OCTOPUS, *MERGE_OWN, CLEAN_MERGE]),
    Mutation("filter status: the filter exits with sed's status, not git's", [("          #!/usr/bin/env bash\n          set -o pipefail\n", "          #!/usr/bin/env bash\n")], [NOTES], [ARGV, OCTOPUS, *MERGE_KEEPS]),
    # --- the engine pin this port adds to the action step, and the self-test step it adds to the job ---
    Mutation("action unpinned: GITLEAKS_VERSION leaves the action step", [('          GITLEAKS_VERSION: "8.24.3"\n        # The action declares no inputs', "        # The action declares no inputs")], [ENGINE_PIN], [DIGEST, ACTION_SKIPS_PR]),
    Mutation("action drift: the action step moves to another engine version", [('          GITLEAKS_VERSION: "8.24.3"\n        # The action declares no inputs', '          GITLEAKS_VERSION: "8.24.2"\n        # The action declares no inputs')], [ENGINE_PIN], [DIGEST]),
    Mutation("self-test optional: a missing binary skips again", [(PARITY_ENV, '        env:\n          GITLEAKS_PARITY_REQUIRED: "0"\n')], [ENGINE_PIN], [EVENT_RANGE]),
    Mutation("self-test conditional: it runs on push only", [(PARITY_ENV, "        if: github.event_name == 'push'\n" + PARITY_ENV)], [ENGINE_PIN], [EVENT_RANGE]),
    Mutation("self-test tolerated: its failure no longer fails the job", [(PARITY_ENV, "        continue-on-error: true\n" + PARITY_ENV)], [ENGINE_PIN], [EVENT_RANGE]),
    Mutation("self-test gone: the step runs another file", [(SELF_TEST_RUN, "        run: python -m pytest tests/test_cli.py -v\n")], [ENGINE_PIN, EVENT_RANGE], [DIGEST]),
    Mutation(
        "self-test first: it runs before anything has installed the binary",
        [("      - name: Run Gitleaks (Secrets Detection)\n", "      - name: Early self-test\n" + PARITY_ENV + SELF_TEST_RUN + "\n      - name: Run Gitleaks (Secrets Detection)\n")],
        [EVENT_RANGE],
        [ENGINE_PIN, DIGEST],
    ),
    # --- the lane that selects the file, the events the workflow runs on, and the checkout ---
    Mutation("unit lane filtered: -m integration", [(UNIT_LANE, '            -m "integration" \\\n' + UNIT_LANE)], [LANE], [ENGINE_PIN]),
    Mutation("unit lane filtered: the file is ignored", [(UNIT_LANE, "            --ignore=tests/test_gitleaks_pr_scan.py \\\n" + UNIT_LANE)], [LANE], [ENGINE_PIN]),
    Mutation("unit lane filtered: the file is deselected by keyword", [(UNIT_LANE, '            -k "not gitleaks" \\\n' + UNIT_LANE)], [LANE], [ENGINE_PIN]),
    Mutation("unit lane filtered: the file is deselected by path", [(UNIT_LANE, "            --deselect tests/test_gitleaks_pr_scan.py \\\n" + UNIT_LANE)], [LANE], [ENGINE_PIN]),
    Mutation("unit lane narrowed: one file instead of tests/", [(UNIT_LANE, UNIT_LANE.replace("tests/ ", "tests/test_cli.py ", 1))], [LANE], [ENGINE_PIN]),
    Mutation("unit lane replaced: the job no longer runs pytest", [("          python -m pytest \\\n" + UNIT_LANE, "          python -m unittest discover \\\n" + UNIT_LANE)], [LANE], [ENGINE_PIN]),
    Mutation("unmarked: the file loses its unit mark", [("pytestmark = [pytest.mark.unit]\n", "pytestmark = []\n")], [LANE], [ENGINE_PIN], path=TEST_FILE),
    Mutation("unsupported event: merge_group joins the workflow's events", [("  workflow_dispatch:\n\nconcurrency:", "  workflow_dispatch:\n  merge_group:\n\nconcurrency:")], [ACTION_SKIPS_PR], [EVENT_RANGE]),
    Mutation("no pull_request: the workflow stops running on pull requests", [("  pull_request:\n    branches:\n      - main\n      - develop\n  workflow_dispatch:", "  workflow_dispatch:")], [ACTION_SKIPS_PR], [EVENT_RANGE]),
    Mutation(
        "shallow checkout: the security job fetches one commit",
        [("        with:\n          fetch-depth: 0\n\n      - name: Run Gitleaks (Secrets Detection)", "        with:\n          fetch-depth: 1\n\n      - name: Run Gitleaks (Secrets Detection)")],
        [FETCH_DEPTH],
        [EVENT_RANGE, ARGV],
    ),
    # --- the install step's remaining pins ---
    Mutation("install unconditional: the install runs on every event", [(ON_PR + "        env:\n          GITLEAKS_VERSION:", "        env:\n          GITLEAKS_VERSION:")], [DIGEST], [EVENT_RANGE]),
    Mutation("digest drift: one digit of the pinned digest", [('GITLEAKS_SHA256: "9991e0b2', 'GITLEAKS_SHA256: "8991e0b2')], [DIGEST], [EVENT_RANGE]),
    Mutation("legacy URL: the tarball comes from the old repository name", [("https://github.com/gitleaks/gitleaks/releases/download/", "https://github.com/zricethezav/gitleaks/releases/download/")], [DIGEST], [EVENT_RANGE]),
    Mutation("check after unpack: the digest is checked once the tarball is unpacked", [(SHA_CHECK + UNPACK, UNPACK + SHA_CHECK)], [DIGEST], [EVENT_RANGE]),
    Mutation("not on PATH: the install no longer exports its directory", [('          echo "${dest}" >> "${GITHUB_PATH}"\n', "")], [DIGEST], [EVENT_RANGE]),
    Mutation("piped install: a download is piped into a shell", [('          "${dest}/gitleaks" version\n', '          "${dest}/gitleaks" version\n          curl -fsSL https://example.invalid/setup.sh | sh\n')], [DIGEST], [EVENT_RANGE]),
    # --- the scan step's remaining pins ---
    Mutation("scan unconditional: the scan runs on every event", [(ON_PR + "        env:\n          BASE_SHA:", "        env:\n          BASE_SHA:")], [EVENT_RANGE], [DIGEST, ARGV]),
    Mutation("scan names a shell: the rehearsals no longer run what GitHub runs", [(ON_PR + "        env:\n          BASE_SHA:", ON_PR + "        shell: sh\n        env:\n          BASE_SHA:")], [EVENT_RANGE], [DIGEST, ARGV]),
    Mutation("range from elsewhere: the head is the merge commit, not the pull request's head", [("          HEAD_SHA: ${{ github.event.pull_request.head.sha }}\n", "          HEAD_SHA: ${{ github.sha }}\n")], [EVENT_RANGE], [DIGEST, ARGV]),
    Mutation("silent count: the range's commit count is no longer logged", [('          echo "Scanning ${count} commit(s) in ${range}; the pull request reports ${PR_COMMITS}."\n', "")], [ARGV, PAST_PAGE, CLEAN], [WARN, MERGE]),
    Mutation("no warning: a count that differs from the pull request's passes in silence", [('            echo "::warning title=Gitleaks::${range} holds ${count} commit(s), and the pull request reports ${PR_COMMITS}"\n', "            true\n")], [WARN], [ARGV, OCTOPUS]),
    Mutation("no summary: the job summary loses the count and the exit code", [("printf '### Gitleaks\\n\\n%s commit(s) scanned in %s; gitleaks exited %s.\\n'", "printf ''")], [ARGV], [WARN, LEAKS]),
    Mutation("engine error passes: a gitleaks failure that is not a scan result passes", [('which is not a scan result"\n              exit "${rc}"\n', 'which is not a scan result"\n              exit 0\n')], [ENGINE_ERROR, NOT_EXECUTABLE], [LEAKS, NO_LEAKS]),
    Mutation("engine error flattened: every gitleaks failure exits 1", [('which is not a scan result"\n              exit "${rc}"\n', 'which is not a scan result"\n              exit 1\n')], [NOT_EXECUTABLE], [ENGINE_ERROR, LEAKS, NO_LEAKS]),
    Mutation("clean scan fails: exit 0 from gitleaks fails the step", [("            0) ;;\n", "            0) exit 1 ;;\n")], [NO_LEAKS, ARGV, CLEAN], [LEAKS, *REFUSE]),
    Mutation("unredacted: the scan drops --redact", [("gitleaks detect --redact -v", "gitleaks detect -v")], [ARGV, PAST_PAGE], [LEAKS, WARN]),
    # --- what keeps a failure blocking: the job, the two pull-request steps, the self-test's command, the report upload, the filter's anchor ---
    Mutation("job tolerated: a failed security job no longer fails the run", [(JOB_HEAD, JOB_HEAD + "    continue-on-error: true\n")], [ENGINE_PIN], [EVENT_RANGE, DIGEST]),
    Mutation("job conditional: the whole security job skips Dependabot's pull requests", [(JOB_HEAD, JOB_HEAD + "    if: github.actor != 'dependabot[bot]'\n")], [ENGINE_PIN], [EVENT_RANGE, DIGEST]),
    Mutation("job renamed: the required check's name is gone", [("    name: Security Scans\n", "    name: Security\n")], [ENGINE_PIN], [EVENT_RANGE, DIGEST]),
    Mutation("install tolerated: a failed install no longer fails the job", [(ON_PR + "        env:\n          GITLEAKS_VERSION:", ON_PR + "        continue-on-error: true\n        env:\n          GITLEAKS_VERSION:")], [DIGEST], [EVENT_RANGE]),
    Mutation("scan tolerated: a leak no longer fails the job", [(ON_PR + "        env:\n          BASE_SHA:", ON_PR + "        continue-on-error: true\n        env:\n          BASE_SHA:")], [EVENT_RANGE], [DIGEST, ARGV]),
    Mutation("self-test swallowed: its own shell drops a failure", [(SELF_TEST_RUN, SELF_TEST_RUN.replace("--timeout=120\n", "--timeout=120 || true\n"))], [ENGINE_PIN], [EVENT_RANGE, DIGEST]),
    Mutation("self-test narrowed: -k deselects the real-engine cases", [(SELF_TEST_RUN, SELF_TEST_RUN.replace("--timeout=120\n", '--timeout=120 -k "not real_engine"\n'))], [ENGINE_PIN], [EVENT_RANGE, DIGEST]),
    Mutation("digest check swallowed: a mismatch no longer stops the install", [(SHA_CHECK, SHA_CHECK.replace("--strict\n", "--strict || true\n"))], [DIGEST], [EVENT_RANGE]),
    Mutation("self-hash: the tarball is checked against its own digest, not the pinned one", [(SHA_CHECK, '          echo "$(sha256sum "${RUNNER_TEMP}/${asset}" | cut -d " " -f 1)  ${RUNNER_TEMP}/${asset}" | sha256sum --check --strict\n')], [DIGEST], [EVENT_RANGE]),
    Mutation("report lost: the upload no longer runs after a failed scan", [("        if: always()\n        with:\n          name: security-reports\n", "        with:\n          name: security-reports\n")], [EVENT_RANGE], [DIGEST, ENGINE_PIN]),
    Mutation("report left out: the upload takes Bandit's file only", [("          name: security-reports\n          path: reports/security/\n", "          name: security-reports\n          path: reports/security/bandit.sarif\n")], [EVENT_RANGE], [DIGEST, ENGINE_PIN]),
    Mutation(
        "report early: the upload runs before the scan has written its report",
        [(UPLOAD_NAME, "      - name: Upload Security Reports (late)\n"), (PR_SCAN_NAME, UPLOAD_NAME + "        uses: actions/upload-artifact@v7\n        if: always()\n        with:\n          name: security-reports\n          path: reports/security/\n\n" + PR_SCAN_NAME)],
        [EVENT_RANGE],
        [DIGEST, ENGINE_PIN],
    ),
    Mutation("filter unanchored: every line that holds the word remerge is deleted, not only git's notes", [("sed -e '/^remerge /d'", "sed -e '/remerge/d'")], [NOTES], [ARGV, OCTOPUS, *MERGE_KEEPS]),
    # --- the repository's own ruleset: a config at the root that loads no rule ---
    Mutation("zero-rule config: a .gitleaks.toml that loads no rule appears at the repository root", [("", 'title = "a config with no [extend] table and no rule"\n')], [PAST_PAGE, MERGE, *MERGE_OWN, *MERGE_KEEPS], [CLEAN, CLEAN_MERGE, ARGV], path=ZERO_RULE_CONFIG),
    # --- this repository's: the self-test's install, which the security job needs because it installs no pytest before pip-audit ---
    Mutation("self-test install narrowed: the package without its test extra", [(INSTALL_RUN, "        run: pip install -e .\n")], [SELF_INSTALL], [ENGINE_PIN, EVENT_RANGE]),
    Mutation(
        "self-test install early: the test extra is installed before pip-audit",
        [(INSTALL_RUN, '        run: "true"\n'), (PIP_AUDIT_NAME, "      - name: Install the package early\n" + INSTALL_RUN + "\n" + PIP_AUDIT_NAME)],
        [SELF_INSTALL],
        [ENGINE_PIN, EVENT_RANGE],
    ),
    Mutation(
        "self-test install late: the self-test runs before its install",
        [(INSTALL_RUN, '        run: "true"\n'), (UPLOAD_NAME, "      - name: Install the package late\n" + INSTALL_RUN + "\n" + UPLOAD_NAME)],
        [SELF_INSTALL],
        [ENGINE_PIN, EVENT_RANGE],
    ),
    Mutation("test extra in the security tools: `.[test]` is installed before pip-audit runs", [(SECURITY_TOOLS_PIP, SECURITY_TOOLS_PIP + '          pip install -e ".[test]"\n')], [SELF_INSTALL], [ENGINE_PIN, EVENT_RANGE]),
]


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def run_one(node_id: str, basetemp: Path | None, slot: int) -> bool:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "GITLEAKS_PARITY_REQUIRED": "1"}
    env.pop("GITLEAKS_CONFIG", None)
    env.pop("GITLEAKS_CONFIG_TOML", None)
    argv = [sys.executable, "-m", "pytest", node_id, "-q", "--no-header", "-p", "no:cacheprovider", "--timeout=180"]
    if basetemp is not None:
        argv.append(f"--basetemp={basetemp / f'slot-{slot}'}")
    return subprocess.run(argv, cwd=REPO, capture_output=True, text=True, env=env, check=False).returncode == 0  # nosec B603


def run_tests(node_ids: list[str], basetemp: Path | None, workers: int) -> dict[str, bool]:
    """Return {node_id: passed}; each id runs in a pytest process of its own so one red cannot mask another."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Each run gets a basetemp slot of its own: pytest empties the directory it is given.
        futures = [pool.submit(run_one, node_id, basetemp, slot) for slot, node_id in enumerate(node_ids)]
        return {node_id: future.result() for node_id, future in zip(node_ids, futures)}


def keep_pristine_copies(backup: Path, paths: list[str]) -> None:
    """Copy every file about to be mutated to ``backup``, after checking the copies an earlier run left there.

    A copy that differs from its file means an earlier run was killed between a mutation and its restore, or the file
    was edited since: either way a person has to choose, so the run stops before it touches anything.
    """
    for path in paths:
        source, copy = REPO / path, backup / path
        if source.is_file() and copy.is_file() and source.read_bytes() != copy.read_bytes():
            raise SystemExit(f"FATAL: {path} differs from the pristine copy an earlier run left at {copy}.\n  If that run died mid-mutation, restore the file:  cp {copy} {source}\n  If you have edited {path} since, delete the copy and run again.")
    for path in paths:
        source, copy = REPO / path, backup / path
        if source.is_file():
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copy)


def mutated_text(original: str, mutation: Mutation) -> str:
    text = original
    for find, replace in mutation.edits:
        if find == "":
            if original != "":
                raise SystemExit(f"FATAL: {mutation.name}: {mutation.path} exists, so it cannot be created (delete it if an earlier run of this script died while it was there)")
            return replace
        count = text.count(find)
        if count != 1:
            raise SystemExit(f"FATAL: {mutation.name}: a pattern matched {count} times (expected 1) in {mutation.path}:\n  {find.strip()}")
        text = text.replace(find, replace)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--basetemp", type=Path, help="a directory for pytest's --basetemp, one sub-directory per run (default: pytest's own, under TMPDIR)")
    ap.add_argument("--backup", type=Path, help="keep a pristine copy of every file this run mutates here; a copy from an earlier run that differs from its file stops the run")
    ap.add_argument("--workers", type=int, default=4, help="pytest processes at a time (default and maximum: 4)")
    ap.add_argument("--json", type=Path, help="write every result to this file")
    ap.add_argument("--only", help="run only the mutations whose name contains this text")
    args = ap.parse_args()
    workers = max(1, min(args.workers, 4))
    if not os.environ.get("GITLEAKS_BIN"):
        print("GITLEAKS_BIN is unset: the real-engine cases cannot run, so the baseline would be red")
        return 1
    basetemp = args.basetemp.resolve() if args.basetemp else None
    if basetemp is not None:
        # pytest creates the directory it is given, but not that directory's parent.
        basetemp.mkdir(parents=True, exist_ok=True)
    for stale in (REPO / "tests" / "__pycache__").glob("test_gitleaks_pr_scan*.pyc"):
        stale.unlink()
    mutations = [m for m in MUTATIONS if args.only is None or args.only in m.name]
    # Every mutation is checked against the unmutated files before any test runs, so a stale pattern stops the run here.
    originals: dict[str, str] = {}
    for mutation in mutations:
        target = REPO / mutation.path
        originals[mutation.path] = target.read_text(encoding="utf-8") if target.is_file() else ""
        mutated_text(originals[mutation.path], mutation)
    if args.backup:
        keep_pristine_copies(args.backup.resolve(), sorted(originals))
    before = {path: sha256(REPO / path) for path in originals}
    failures: list[str] = []
    record: dict = {"baseline": {}, "mutations": []}
    every = sorted({n for m in mutations for n in m.must_fail + m.must_still_pass})

    print("baseline (unmutated files): every listed test must PASS")
    for node_id, passed in run_tests(every, basetemp, workers).items():
        print(f"  {'OK  ' if passed else 'RED '} {node_id.removeprefix(T)}")
        record["baseline"][node_id] = passed
        if not passed:
            failures.append(f"baseline: {node_id} is RED before any mutation")
    if failures:
        # A test that is red before any edit cannot show that an edit turned it red.
        print("FAIL: the baseline is red, so no mutation was run")
        for line in failures:
            print(f"  - {line}")
        return 1

    for mutation in mutations:
        print(f"\n{mutation.name}  [{mutation.path}]")
        target = REPO / mutation.path
        original = originals[mutation.path]
        try:
            target.write_text(mutated_text(original, mutation), encoding="utf-8")
            caught = run_tests(mutation.must_fail, basetemp, workers)
            survived = run_tests(mutation.must_still_pass, basetemp, workers)
        finally:
            if before[mutation.path] is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(original, encoding="utf-8")
        restored = sha256(target) == before[mutation.path]
        if not restored:
            failures.append(f"{mutation.name}: RESTORE FAILED -- {mutation.path} still holds the mutation")
        for node_id, passed in caught.items():
            print(f"  {'VACUOUS' if passed else 'CAUGHT '} {node_id.removeprefix(T)}")
            if passed:
                failures.append(f"{mutation.name}: {node_id} stayed GREEN -- it pins nothing here")
        for node_id, passed in survived.items():
            print(f"  {'OK     ' if passed else 'OVERBRD'} {node_id.removeprefix(T)} (expected unaffected)")
            if not passed:
                failures.append(f"{mutation.name}: {node_id} went red too -- the mutation is not the property it claims")
        record["mutations"].append({"name": mutation.name, "path": mutation.path, "killed_by": {n: not p for n, p in caught.items()}, "left_green": dict(survived), "restored_sha256": restored})

    pairs = sum(len(m["killed_by"]) for m in record["mutations"])
    killed = sum(sum(m["killed_by"].values()) for m in record["mutations"])
    kept = sum(sum(m["left_green"].values()) for m in record["mutations"])
    survivors = sum(len(m["left_green"]) for m in record["mutations"])
    record["totals"] = {"mutations": len(mutations), "mutation_test_pairs": pairs, "pairs_caught": killed, "survivors_listed": survivors, "survivors_green": kept, "failures": failures}
    record["sha256_after"] = {path: sha256(REPO / path) for path in originals}
    record["sha256_before"] = before
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1)
            fh.write("\n")
    print(f"\n{len(mutations)} mutations: {killed} of {pairs} mutation-test pairs caught; {kept} of {survivors} listed survivors green.")
    if failures:
        print("FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("PASS: every mutation is caught by every test listed for it, no listed survivor went red, and every file was restored exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
