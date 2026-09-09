"""
Pin the CPU-only torch contract between the Dockerfile, the CPU lock, the publish workflow
and the in-image check script.

Regression guard for the 2026-09-07 image (``ghcr.io/pcalnon/juniper-cascor-worker:dispatch-3d81f2c``)
that shipped ``torch 2.12.1+cu130`` plus the ``nvidia-*`` / ``triton`` stack -- 3 GB per Raspberry
Pi node -- despite the Dockerfile's claim of a CPU-only build. The causal chain was:

* ``requirements-cpu.lock`` is compiled ``--no-emit-package torch`` with ``--override torch==2.12.0+cpu``,
  so its torch-derived pins (``setuptools==70.2.0`` ...) are consistent only with torch 2.12.x;
* the Dockerfile installed torch UNPINNED from the CPU index (newest = 2.14.0, needs ``setuptools>=77``);
* the lock install then ran with NO index flags, so pip -- finding the installed torch inconsistent
  with the lock -- re-resolved torch from PyPI alone and installed the CUDA build.

Each test below fails on one link of that chain re-forming. None of them build an image; the
publish workflow's PR arm does that on both arches and runs ``util/check_image_cpu_only.py``
inside the result.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess  # nosec B404 - runs this repo's own check script with the test interpreter
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO / "Dockerfile"
CPU_LOCK = REPO / "requirements-cpu.lock"
GPU_LOCK = REPO / "requirements.lock"
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
WORKFLOW = REPO / ".github" / "workflows" / "publish-image.yml"
CHECK_SCRIPT = REPO / "util" / "check_image_cpu_only.py"
CHECK_SCRIPT_REL = "util/check_image_cpu_only.py"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"
PUBLISH_IF = "github.event_name == 'release' || inputs.push"
CUDA_STACK_PREFIXES = ("nvidia-", "triton==", "cuda-")


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────────────────────
def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _dockerfile_args() -> dict[str, str]:
    """Default values of every ``ARG NAME=value`` in the Dockerfile."""
    return dict(re.findall(r"^ARG\s+([A-Z_]+)=\"?([^\"\n]*)\"?$", _dockerfile_text(), re.MULTILINE))


def _expand(line: str, args: dict[str, str]) -> str:
    for name, value in args.items():
        line = line.replace("${" + name + "}", value).replace("$" + name, value)
    return line


def _run_instructions() -> list[str]:
    """Every RUN instruction with continuation lines joined, ARGs expanded and shell quotes dropped."""
    joined = re.sub(r"\\\n\s*", " ", _dockerfile_text())
    args = _dockerfile_args()
    return [_expand(line, args).replace('"', "") for line in joined.splitlines() if line.startswith("RUN ")]


def _dockerfile_torch_version() -> str:
    version = _dockerfile_args().get("TORCH_VERSION")
    assert version, "Dockerfile must declare `ARG TORCH_VERSION=<x.y.z>` -- the CPU-only contract has no pin without it"
    return version


def _pins(lock: Path) -> list[str]:
    return [line for line in lock.read_text(encoding="utf-8").splitlines() if line and not line.startswith((" ", "\t", "#"))]


def _lock_override_version() -> str:
    match = re.search(r"torch==(\d+\.\d+\.\d+)\+cpu", CPU_LOCK.read_text(encoding="utf-8"))
    assert match, "requirements-cpu.lock header must carry its `torch==X.Y.Z+cpu` --override recipe"
    return match.group(1)


def _workflow() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) reads the bare `on:` key as boolean True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def _steps(job: str) -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def _step(job: str, name_prefix: str) -> dict:
    matches = [s for s in _steps(job) if str(s.get("name", "")).startswith(name_prefix)]
    assert len(matches) == 1, f"expected exactly one step in job {job!r} named {name_prefix!r}..., found {len(matches)}"
    return matches[0]


def _load_check_module():
    spec = importlib.util.spec_from_file_location("check_image_cpu_only", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Dockerfile <-> lock
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestDockerfileTorchPin:
    def test_dockerfile_pin_matches_lock_override(self):
        """The two declarations of the CPU torch version must agree, or the lock's pins are for a different torch."""
        assert _dockerfile_torch_version() == _lock_override_version()

    def test_lock_excludes_torch(self):
        """The lock must keep torch OUT (``--no-emit-package torch``); an emitted torch pin would come from PyPI."""
        pins = [line for line in CPU_LOCK.read_text(encoding="utf-8").splitlines() if line.startswith("torch==")]
        assert pins == [], f"requirements-cpu.lock must not pin torch itself: {pins}"

    def test_cpu_lock_excludes_the_cuda_stack(self):
        """The other half of "CPU-only": the lock must not pin an nvidia-* / triton / cuda-* wheel either."""
        offenders = [p for p in _pins(CPU_LOCK) if p.startswith(CUDA_STACK_PREFIXES)]
        assert offenders == [], f"requirements-cpu.lock must not pin any CUDA-stack package: {offenders}"

    def test_cpu_lock_is_the_gpu_lock_minus_the_cuda_stack(self):
        """Shared pins are identical by construction (``--constraint requirements.lock``); a divergence means one lock was regenerated without the other.

        This is the guard the CI checks could not give: both repos assert only that every
        pyproject dependency is PRESENT in the CPU lock, so the two locks drifted on 10 of
        19 shared pins (setuptools 70.2.0 vs 83.0.0, numpy 2.4.4 vs 2.5.1, ...) while every
        build stayed green -- ``lockfile-update.yml`` regenerates ``requirements.lock`` alone.
        """
        gpu = {p for p in _pins(GPU_LOCK) if not p.startswith(CUDA_STACK_PREFIXES)}
        cpu = set(_pins(CPU_LOCK))
        assert cpu == gpu, f"only in CPU lock: {sorted(cpu - gpu)}; only in GPU lock (non-CUDA): {sorted(gpu - cpu)}"

    def test_gpu_lock_still_pins_the_cuda_stack(self):
        """Guards the test above against becoming vacuous: if the GPU lock ever stops pinning CUDA wheels, the two locks are the same file and the parity assertion proves nothing."""
        cuda = [p for p in _pins(GPU_LOCK) if p.startswith(CUDA_STACK_PREFIXES)]
        assert cuda, "requirements.lock no longer pins the CUDA stack -- requirements-cpu.lock may be redundant; re-derive the split deliberately rather than deleting this test"

    def test_torch_install_is_pinned_cpu_wheel_from_cpu_index(self):
        version = _dockerfile_torch_version()
        installs = [r for r in _run_instructions() if "pip install" in r and "-r requirements-cpu.lock" not in r and "torch==" in r]
        assert len(installs) == 1, f"expected exactly one standalone torch install, found {installs}"
        line = installs[0]
        assert f"torch=={version}+cpu" in line, line
        assert f"--index-url {CPU_INDEX}" in line, line

    def test_lock_install_carries_cpu_index_and_pin(self):
        """The link that actually broke: the lock install must be able to SEE the CPU wheel and must be held to it."""
        version = _dockerfile_torch_version()
        installs = [r for r in _run_instructions() if "-r requirements-cpu.lock" in r]
        assert len(installs) == 1, f"expected exactly one lock install, found {installs}"
        line = installs[0]
        assert f"--extra-index-url {CPU_INDEX}" in line, line
        assert f"torch=={version}+cpu" in line, line
        # --index-url would REPLACE PyPI, and the CPU index 403s pydantic and websockets.
        assert "--index-url" not in line.replace("--extra-index-url", ""), line

    def test_builder_runs_pip_check(self):
        assert any("pip check" in r for r in _run_instructions()), "the builder stage must end with `pip check`"


class TestCiTestsTheShippedTorch:
    """``ci.yml`` must run the unit suite against the torch the IMAGE ships, not the newest one.

    Unpinned, the two diverge on every PyTorch release with nothing to report it: on
    2026-09-08 the suite tested 2.14.0 while the image shipped the lock header's 2.12.0.
    """

    @staticmethod
    def _install_step_run() -> str:
        data = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
        data["on"] = data.pop(True, data.get("on"))
        steps = data["jobs"]["unit-tests"]["steps"]
        matches = [s for s in steps if str(s.get("name", "")) == "Install dependencies"]
        assert len(matches) == 1, f"expected exactly one 'Install dependencies' step in the unit-tests job, found {len(matches)}"
        return matches[0]["run"]

    def test_ci_reads_the_pin_from_the_dockerfile(self):
        """Restating the version in the workflow would create a third place to bump; the ARG is the single source."""
        run = self._install_step_run()
        assert "ARG TORCH_VERSION=" in run, "the install step must read `ARG TORCH_VERSION` out of the Dockerfile"
        assert f"torch=={_dockerfile_torch_version()}" not in run, "the workflow must not hardcode the torch version -- derive it from the Dockerfile"

    def test_ci_installs_a_pinned_torch_on_both_platforms(self):
        run = self._install_step_run()
        assert 'pip install "torch==${TORCH_VERSION}+cpu"' in run, "the Linux arm must install the pinned +cpu wheel"
        assert 'pip install "torch==${TORCH_VERSION}"' in run, "the macOS arm must pin the version too (no +cpu wheels are published for macOS)"
        assert "pip install torch " not in run and "pip install torch\n" not in run, "no unpinned `pip install torch` may remain in the test job"


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Workflow: the contract is asserted on the PR arm AND on the publish path
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestPublishWorkflowAssertsContract:
    def test_paths_filter_covers_the_image_inputs_and_the_check(self):
        paths = _workflow()["on"]["pull_request"]["paths"]
        for required in ("Dockerfile", "requirements-cpu.lock", CHECK_SCRIPT_REL, ".github/workflows/publish-image.yml"):
            assert required in paths, f"{required!r} missing from the pull_request paths filter: {paths}"

    def test_provenance_step_exports_the_expected_torch(self):
        run = _step("build", "Resolve build provenance")["run"]
        assert "ARG TORCH_VERSION=" in run
        assert "expect_torch=" in run

    def test_smoke_test_runs_the_check(self):
        run = _step("build", "Smoke test")["run"]
        assert CHECK_SCRIPT_REL in run
        assert "EXPECT_TORCH=" in run

    def test_publish_path_verifies_each_arch_before_exporting_its_digest(self):
        """A failing arch must stop the merge job from ever seeing that digest."""
        names = [str(s.get("name", "")) for s in _steps("build")]
        verify = next(i for i, n in enumerate(names) if n.startswith("Verify pushed image is CPU-only"))
        export = next(i for i, n in enumerate(names) if n.startswith("Export digest"))
        assert verify < export, names
        step = _step("build", "Verify pushed image is CPU-only")
        assert step["if"] == PUBLISH_IF, "the publish-path check must run under the same condition as the push itself"
        assert CHECK_SCRIPT_REL in step["run"]
        assert "@${digest}" in step["run"], "the publish-path check must address the image by the digest just pushed"

    def test_merge_job_checks_the_published_tag(self):
        steps = _steps("merge")
        assert any(str(s.get("uses", "")).startswith("actions/checkout@") for s in steps), "the merge job must check out the repo to read the pin and the check script"
        step = _step("merge", "Verify published image is CPU-only")
        assert CHECK_SCRIPT_REL in step["run"]
        assert "ARG TORCH_VERSION=" in step["run"]
        assert "/tmp/manifest.json" in step["run"] and "/tmp/digests" in step["run"], "digest identity between the manifest list and the verified digests must be asserted"

    def test_identity_step_admits_one_linux_image_per_pushed_digest(self):
        """A pushed per-arch digest names an OCI index; it must carry exactly one linux image, for the arch the census ran on (the digest file's name)."""
        run = _step("merge", "Verify published image is CPU-only")["run"]
        assert 'arch_file="$(basename "${f}")"' in run, "the expected arch is the digest file's name"
        assert '"${image_arch}" != "${arch_file}"' in run, "the linux image's architecture must equal the digest file's name"
        assert "-ne 1" in run, "exactly one linux image per pushed digest"

    def test_merge_job_requires_a_version_tag_on_release(self):
        step = _step("merge", "Verify the release produced a version tag")
        assert step["if"] == "github.event_name == 'release'"
        assert "[0-9]+" in step["run"]

    def test_jobs_are_guarded_to_this_packages_release_tags(self):
        """A sibling package's release must not republish `latest`: both jobs check the tag prefix."""
        jobs = _workflow()["jobs"]
        assert jobs["build"]["if"] == "github.event_name != 'release' || startsWith(github.event.release.tag_name, 'v')"
        assert jobs["merge"]["if"] == "(github.event_name == 'release' && startsWith(github.event.release.tag_name, 'v')) || inputs.push"


# ─────────────────────────────────────────────────────────────────────────────────────────────
# The in-image check itself
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestCheckImageCpuOnly:
    @pytest.mark.parametrize("value", ["", "2.12.0", "2.12.0+cu130", "latest", "+cpu"])
    def test_rejects_malformed_expectation_with_usage_exit(self, value):
        env = {k: v for k, v in os.environ.items() if k != "EXPECT_TORCH"}
        env["EXPECT_TORCH"] = value
        result = subprocess.run([sys.executable, str(CHECK_SCRIPT)], env=env, capture_output=True, text=True, timeout=120)  # nosec B603 - fixed argv, no shell
        assert result.returncode == 2, result.stderr
        assert "EXPECT_TORCH must be" in result.stderr

    def test_census_flags_every_cuda_stack_distribution(self):
        mod = _load_check_module()
        names = {"numpy", "nvidia-cublas", "nvidia_cudnn_cu13", "triton", "cuda-toolkit", "cuda_bindings", "sympy"}
        offenders = mod.forbidden_distributions({mod._normalise(n) for n in names})
        assert offenders == ["cuda-bindings", "cuda-toolkit", "nvidia-cublas", "nvidia-cudnn-cu13", "triton"]

    def test_census_forbids_the_cuda_prefix_family(self):
        """The 2026-09-07 CUDA image also carried cuda-toolkit / cuda-bindings / cuda-pathfinder; the first census let those through."""
        mod = _load_check_module()
        assert mod.forbidden_distributions({"cuda-toolkit", "cuda-bindings", "cuda-pathfinder", "numpy"}) == ["cuda-bindings", "cuda-pathfinder", "cuda-toolkit"]

    def test_absent_contract_passes_only_without_torch(self, monkeypatch):
        mod = _load_check_module()
        monkeypatch.setattr(mod, "torch_importable", lambda: False)
        assert mod.check("absent", {"numpy", "pydantic-core"}) == []
        monkeypatch.setattr(mod, "torch_importable", lambda: True)
        problems = mod.check("absent", {"numpy"})
        assert len(problems) == 1 and "EXPECT_TORCH=absent" in problems[0]

    def test_absent_contract_still_reports_orphaned_cuda_wheels(self, monkeypatch):
        """The vacuous-fix shape: torch gone (or CPU) but the nvidia wheels left behind."""
        mod = _load_check_module()
        monkeypatch.setattr(mod, "torch_importable", lambda: False)
        problems = mod.check("absent", {"nvidia-nccl-cu13", "numpy"})
        assert len(problems) == 1 and "nvidia-nccl-cu13" in problems[0]

    def test_version_contract_reports_a_mismatch(self):
        """Uses the real torch in this environment; whatever it is, it is not 0.0.1+cpu."""
        pytest.importorskip("torch")
        mod = _load_check_module()
        problems = mod.check("0.0.1+cpu", set())
        assert any("expected '0.0.1+cpu'" in p for p in problems), problems
