"""
Rehearse the shell in ``.github/workflows/pr-budget-alarm.yml`` (#187).

The alarm is report-only: a breach stays a green run, and a failed ``gh pr list`` stays a
green run that says it could not query -- it must not look like an empty queue. Thresholds
compare as integers (``9`` is under ``10``; ``100`` is over ``90``). An unset or empty repo
variable falls back to 15 / 30, which is the shape GitHub gives a missing ``vars.*`` value.
Only a head ref that starts with ``cursor/`` counts toward the cursor column. The Slack
payload carries the counts and the run URL, never the webhook, and a missing webhook does
not call curl.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404 - runs this repo's own workflow shell with a fixed argv
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "pr-budget-alarm.yml"
WEBHOOK = "https://hooks.example.test/services/T00/B00/secret-token"  # nosec B105 - fixture URL, never a real webhook
RUN_URL = "https://github.com/pcalnon/juniper-cascor-worker/actions/runs/1"


def _workflow() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) reads the bare `on:` key as boolean True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def _step(name_prefix: str) -> dict:
    matches = [s for s in _workflow()["jobs"]["budget-alarm"]["steps"] if str(s.get("name", "")).startswith(name_prefix)]
    assert len(matches) == 1, f"expected exactly one step named {name_prefix!r}..., found {len(matches)}"
    return matches[0]


def _parse_output(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        parsed[key] = value
    return parsed


def _jq_dir() -> str:
    jq = shutil.which("jq")
    assert jq, "jq is required to rehearse the workflow shell"
    return str(Path(jq).parent)


def _child_env(stub: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": f"{stub}{os.pathsep}{_jq_dir()}{os.pathsep}/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/tmp"),  # nosec B108 - git-free fallback; bash wants a HOME
        "LANG": "C",
    }
    env.update(extra)
    return env


def _run_count(tmp_path: Path, prs: list[dict] | None, *, warn: str | None = None, alarm: str | None = None, gh_fail: bool = False, gh_err: str = "api down\ntry later\n", raw: str | None = None):
    work = tmp_path / "work"
    stub = work / "bin"
    stub.mkdir(parents=True)
    (work / "prs.json").write_text(raw if raw is not None else json.dumps(prs or []), encoding="utf-8")
    (work / "gh.err").write_text(gh_err, encoding="utf-8")
    gh = stub / "gh"
    gh.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
if [ "${{GH_FAIL:-0}}" = "1" ]; then
  cat "{work / "gh.err"}" >&2
  exit 1
fi
cat "{work / "prs.json"}"
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    output = work / "github_output"
    summary = work / "github_summary"
    output.write_text("", encoding="utf-8")
    summary.write_text("", encoding="utf-8")
    script = work / "count.sh"
    script.write_text(_step("Count open PRs")["run"], encoding="utf-8")
    env = _child_env(
        stub,
        GH_REPO="pcalnon/juniper-cascor-worker",
        GH_TOKEN="unused",  # nosec B106 - dummy token for the PATH-stubbed gh, never a real credential
        GITHUB_OUTPUT=str(output),
        GITHUB_STEP_SUMMARY=str(summary),
        GH_FAIL="1" if gh_fail else "0",
    )
    if warn is not None:
        env["PR_BUDGET_WARN"] = warn
    if alarm is not None:
        env["PR_BUDGET_ALARM"] = alarm
    proc = subprocess.run(  # nosec B603 B607 - workflow shell, fixed argv, no untrusted input
        ["bash", str(script)],
        cwd=work,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    return proc, _parse_output(output.read_text(encoding="utf-8")), summary.read_text(encoding="utf-8")


def _prs(count: int, prefix: str = "dependabot/github_actions/") -> list[dict]:
    return [{"number": i + 1, "headRefName": f"{prefix}{i}"} for i in range(count)]


def _run_slack(tmp_path: Path, *, webhook: str | None, curl_rc: int = 0, level: str = "WARN", total: str = "17", cursor: str = "4"):
    work = tmp_path / "slack"
    stub = work / "bin"
    stub.mkdir(parents=True)
    args_file = work / "curl.args"
    curl = stub / "curl"
    curl.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\0' "$@" > "{args_file}"
exit {int(curl_rc)}
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    script = work / "slack.sh"
    script.write_text(_step("Slack notification")["run"], encoding="utf-8")
    extra = {
        "LEVEL": level,
        "TOTAL": total,
        "CURSOR": cursor,
        "WARN": "15",
        "ALARM": "30",
        "RUN_URL": RUN_URL,
    }
    if webhook is not None:
        extra["SLACK_WEBHOOK_URL"] = webhook
    proc = subprocess.run(  # nosec B603 B607 - workflow shell, fixed argv, no untrusted input
        ["bash", str(script)],
        cwd=work,
        capture_output=True,
        text=True,
        env=_child_env(stub, **extra),
        check=False,
        timeout=30,
    )
    recorded = args_file.read_text(encoding="utf-8") if args_file.exists() else None
    return proc, recorded


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Workflow contract: schedule/dispatch only, read-only, report-only Slack
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestWorkflowContract:
    def test_it_is_schedule_and_dispatch_only_with_read_only_permissions(self):
        wf = _workflow()
        assert set(wf["on"]) == {"schedule", "workflow_dispatch"}
        assert wf["on"]["schedule"] == [{"cron": "0 14 * * *"}]
        assert "pull_request" not in wf["on"]
        assert wf["permissions"] == {"contents": "read", "pull-requests": "read"}
        assert wf["concurrency"] == {"group": "pr-budget-alarm", "cancel-in-progress": True}

    def test_the_count_step_never_sees_the_slack_webhook(self):
        step = _step("Count open PRs")
        assert "SLACK_WEBHOOK_URL" not in step.get("env", {})
        assert "SLACK_WEBHOOK_URL" not in step["run"]
        assert step["env"]["GH_TOKEN"] == "${{ github.token }}"

    def test_slack_fires_only_on_a_breach_and_cannot_fail_the_run(self):
        step = _step("Slack notification")
        assert step["if"] == "steps.count.outputs.level != 'OK'"
        assert step["continue-on-error"] is True
        assert "SLACK_WEBHOOK_URL" in step["env"]
        assert "curl -fsS" in step["run"]


# ─────────────────────────────────────────────────────────────────────────────────────────────
# The count: integer thresholds, defaults, and the cursor/ prefix
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestBudgetCount:
    @pytest.mark.parametrize(
        ("count", "warn", "alarm", "level"),
        [
            (0, None, None, "OK"),
            (14, None, None, "OK"),
            (15, None, None, "WARN"),
            (29, None, None, "WARN"),
            (30, None, None, "ALARM"),
            (9, "8", "10", "WARN"),  # "9" > "10" lexicographically; the comparison is numeric
            (100, "80", "90", "ALARM"),  # "100" < "90" lexicographically
            (10, "10", "10", "ALARM"),  # a count on both thresholds is an alarm, not a warning
        ],
    )
    def test_level_follows_integer_thresholds_and_a_breach_stays_green(self, tmp_path, count, warn, alarm, level):
        proc, outputs, summary = _run_count(tmp_path, _prs(count), warn=warn, alarm=alarm)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert outputs["total"] == str(count)
        assert outputs["cursor"] == "0"
        assert outputs["level"] == level
        assert f"**{level}**" in summary
        if warn is None:
            assert outputs["warn"] == "15"
            assert outputs["alarm"] == "30"
        if level == "ALARM":
            assert "Report-only" in summary
        elif level == "OK":
            assert "within range" in summary

    def test_an_empty_variable_uses_the_same_default_as_an_unset_one(self, tmp_path):
        """GitHub renders an unset repo variable as an empty env value, and ``:-`` must still default."""
        proc, outputs, _summary = _run_count(tmp_path, _prs(15), warn="", alarm="")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert outputs == {"total": "15", "cursor": "0", "warn": "15", "alarm": "30", "level": "WARN"}

    def test_only_a_cursor_slash_prefix_counts(self, tmp_path):
        prs = [
            {"number": 1, "headRefName": "cursor/missing-test-coverage-618f"},
            {"number": 2, "headRefName": "cursor/"},
            {"number": 3, "headRefName": "Cursor/foo"},
            {"number": 4, "headRefName": "cursor-bot/foo"},
            {"number": 5, "headRefName": "feature/cursor/inside"},
            {"number": 6, "headRefName": "cursor"},
            {"number": 7, "headRefName": "dependabot/github_actions/anthropics/claude-code-action-1.0.240"},
        ]
        proc, outputs, summary = _run_count(tmp_path, prs)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert outputs["total"] == "7"
        assert outputs["cursor"] == "2"
        assert outputs["level"] == "OK"
        assert "| Open `cursor/` PRs | 2 |" in summary

    def test_a_non_numeric_alarm_still_warns_and_compares_as_an_integer(self, tmp_path):
        """``[`` inside ``if`` does not abort on a bad threshold. The warn compare still runs, and stderr shows it was numeric."""
        proc, outputs, summary = _run_count(tmp_path, _prs(30), alarm="abc")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert outputs["level"] == "WARN"
        assert outputs["total"] == "30"
        # bash <= 5.2 says "integer expression expected"; bash 5.3 says "integer expected".
        assert re.search(r"integer (expression )?expected", proc.stderr), proc.stderr
        assert "**ALARM**" not in summary

    def test_gh_failure_stays_green_and_is_not_an_empty_queue(self, tmp_path):
        proc, outputs, summary = _run_count(tmp_path, _prs(40), gh_fail=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert outputs == {"level": "OK"}
        assert "total" not in outputs
        assert "::warning title=pr-budget-alarm::Could not list open PRs: api down try later" in proc.stdout
        assert "Could not query open PRs" in summary
        assert "Open PRs (total)" not in summary
        assert "within range" not in summary

    def test_unreadable_pr_json_fails_closed_rather_than_reporting_zero(self, tmp_path):
        proc, outputs, summary = _run_count(tmp_path, None, raw="not-json")
        assert proc.returncode != 0
        assert "level" not in outputs
        assert "within range" not in summary
        assert "Open PRs (total)" not in summary


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Slack: annotate when there is no webhook, and never put the webhook in the payload
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestSlackStep:
    @pytest.mark.parametrize("webhook", [None, ""])
    def test_a_missing_webhook_annotates_and_does_not_call_curl(self, tmp_path, webhook):
        proc, recorded = _run_slack(tmp_path, webhook=webhook, curl_rc=1)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert recorded is None
        assert "SLACK_WEBHOOK_URL is not set" in proc.stdout
        assert "17 open PR(s), 4 on cursor/ branches" in proc.stdout
        assert WEBHOOK not in proc.stdout

    def test_the_payload_carries_the_counts_and_not_the_webhook(self, tmp_path):
        proc, recorded = _run_slack(tmp_path, webhook=WEBHOOK)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert recorded is not None
        assert "Slack notification posted." in proc.stdout
        args = recorded.split("\0")
        assert WEBHOOK in args
        assert "-fsS" in args
        body = next(arg for arg in args if arg.lstrip().startswith("{"))
        payload = json.loads(body)
        assert WEBHOOK not in payload["text"]
        assert payload["text"] == f"PR budget WARN: 17 open PR(s), 4 on cursor/ branches (thresholds warn=15 / alarm=30). Run: {RUN_URL}"

    def test_a_failed_post_exits_non_zero(self, tmp_path):
        """The step stays green only because the workflow sets continue-on-error, which is pinned above."""
        proc, recorded = _run_slack(tmp_path, webhook=WEBHOOK, curl_rc=22)
        assert proc.returncode == 22
        assert recorded is not None
        assert "Slack notification posted." not in proc.stdout
