"""
Pin ``util/check_image_no_secrets.py``, the credential block in ``.dockerignore``, and where
``publish-image.yml`` runs the scan.

Merged in #191. Docker does not honour ``.gitignore``, and a ``COPY <pkg>/`` allowlist ships
every file beneath that directory. ``.dockerignore`` patterns are root-anchored, so the ``**/``
twins are load-bearing, and ``*.p12`` / ``*.pfx`` are excluded at the context root only. The
in-image scan is the defence that still fires when a pattern is wrong: it must fail closed on
an empty walk, and it must name a credential-shaped file that reached a shipped tree.

These tests need no Docker. ``main`` is driven against a temporary tree with ``scan_roots``
replaced; ``scan_roots`` itself is driven against a temporary site-packages.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "util" / "check_image_no_secrets.py"
SCRIPT_REL = "util/check_image_no_secrets.py"
DOCKERIGNORE = REPO / ".dockerignore"
PUBLISH = REPO / ".github" / "workflows" / "publish-image.yml"
PUBLISH_IF = "github.event_name == 'release' || inputs.push"
BUILD_ONLY_IF = "github.event_name != 'release' && !inputs.push"

# The credential block, in the order Docker evaluates it. ``!.env.example`` must stay last:
# a later ``.env*`` pattern would re-exclude the template (last match wins).
CREDENTIAL_BLOCK = """\
secrets/
**/secrets/
*.key
**/*.key
*.pem
**/*.pem
*.p12
*.pfx
.env
.env.*
**/.env
**/.env.*
!.env.example
"""

# Names the globs must reject. ``.env.example.txt`` matches ``.env.*`` and does not end in an
# allowed suffix -- "example" appearing somewhere in the name is not a template.
BAD_FILENAMES = (
    ".env",
    ".env.local",
    ".env.example.txt",
    "server.key",
    "server.pem",
    "client.p12",
    "client.pfx",
    "store.jks",
    "store.keystore",
    "id_rsa",
    "id_rsa.pub",
    "id_ecdsa",
    "id_ed25519",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "vault.kdbx",
)

# Templates match a bad glob and are saved only by the suffix check running first.
# The other names match no glob; a widened glob (``*credentials*``, ``.env*``) would flag them.
ALLOWED_FILENAMES = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    "id_rsa.example",
    "server.key.template",
    "README.md",
    "mycredentials",
    "not.env",
    ".environment",
)

BAD_DIR_NAMES = ("secrets", ".git", ".ssh", ".aws", ".gnupg", "private")
PRUNE_DIR_NAMES = ("__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules")


def _load():
    spec = importlib.util.spec_from_file_location("check_image_no_secrets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    return _load()


def _findings(out: str) -> list[str]:
    marker = "credential-shaped path(s) in the image:"
    if marker not in out:
        return []
    tail = out.split(marker, 1)[1]
    return [line.strip() for line in tail.splitlines() if line.strip()]


def _use_root(monkeypatch, scanner, root: Path) -> None:
    monkeypatch.setattr(scanner, "scan_roots", lambda: [root])


def _publish() -> dict:
    data = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) reads the bare `on:` key as boolean True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def _publish_step(name_prefix: str) -> dict:
    matches = [s for s in _publish()["jobs"]["build"]["steps"] if str(s.get("name", "")).startswith(name_prefix)]
    assert len(matches) == 1, f"expected exactly one step named {name_prefix!r}..., found {len(matches)}"
    return matches[0]


# ─────────────────────────────────────────────────────────────────────────────────────────────
# The scan verdict
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestScanVerdict:
    @pytest.mark.parametrize("name", BAD_FILENAMES)
    def test_a_credential_shaped_filename_fails_the_scan(self, scanner, tmp_path, monkeypatch, capsys, name):
        root = tmp_path / "root"
        nested = root / "juniper_cascor_worker" / "certs"
        nested.mkdir(parents=True)
        (nested / name).write_text("x", encoding="utf-8")
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 1
        out = capsys.readouterr().out
        assert any(line.endswith(name) for line in _findings(out)), out
        assert "no credential-shaped file" not in out

    @pytest.mark.parametrize("name", ALLOWED_FILENAMES)
    def test_a_template_or_ordinary_name_passes(self, scanner, tmp_path, monkeypatch, capsys, name):
        root = tmp_path / "root"
        root.mkdir()
        (root / name).write_text("x", encoding="utf-8")
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 0
        out = capsys.readouterr().out
        assert "no credential-shaped file" in out
        assert _findings(out) == []

    def test_a_symlink_whose_name_is_credential_shaped_fails(self, scanner, tmp_path, monkeypatch, capsys):
        """The name is the contract. A link at ``.env`` is still ``.env`` whatever it points at."""
        root = tmp_path / "root"
        root.mkdir()
        (root / "readme.txt").write_text("ok", encoding="utf-8")
        (root / ".env").symlink_to("readme.txt")
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 1
        assert any(line.endswith(".env") for line in _findings(capsys.readouterr().out))

    @pytest.mark.parametrize("dirname", BAD_DIR_NAMES)
    def test_a_credential_shaped_directory_fails_even_when_its_files_are_ordinary(self, scanner, tmp_path, monkeypatch, capsys, dirname):
        root = tmp_path / "root"
        bad = root / dirname
        bad.mkdir(parents=True)
        (bad / "note.txt").write_text("x", encoding="utf-8")
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 1
        findings = _findings(capsys.readouterr().out)
        assert findings == [f"{bad}/  (directory)"]

    def test_findings_from_every_root_are_sorted(self, scanner, tmp_path, monkeypatch, capsys):
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        (first / "ok.py").write_text("o", encoding="utf-8")
        (second / "z.pem").write_text("z", encoding="utf-8")
        (second / "a.key").write_text("a", encoding="utf-8")
        monkeypatch.setattr(scanner, "scan_roots", lambda: [first, second])

        assert scanner.main() == 1
        out = capsys.readouterr().out
        assert "scanned 3 files across 2 root(s):" in out
        assert str(first) in out and str(second) in out
        findings = _findings(out)
        assert findings == sorted(findings)
        assert [Path(line).name for line in findings] == ["a.key", "z.pem"]

    def test_prune_dirs_are_not_walked_and_do_not_hide_a_sibling(self, scanner, tmp_path, monkeypatch, capsys):
        root = tmp_path / "root"
        root.mkdir()
        (root / "ok.py").write_text("x", encoding="utf-8")
        (root / "real.key").write_text("k", encoding="utf-8")
        for name in PRUNE_DIR_NAMES:
            pruned = root / name
            pruned.mkdir()
            (pruned / "ignored.py").write_text("i", encoding="utf-8")
            (pruned / "nested.key").write_text("k", encoding="utf-8")
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 1
        out = capsys.readouterr().out
        assert "scanned 2 files across 1 root(s):" in out
        assert [Path(line).name for line in _findings(out)] == ["real.key"]
        assert "ignored.py" not in out
        assert "nested.key" not in out

    def test_no_scan_root_is_exit_2_not_a_pass(self, scanner, monkeypatch, capsys):
        monkeypatch.setattr(scanner, "scan_roots", lambda: [])

        assert scanner.main() == 2
        out = capsys.readouterr().out
        assert "no scan root found" in out
        assert "inspected NOTHING" in out
        assert "no credential-shaped file" not in out

    def test_a_root_that_walks_zero_files_is_exit_2_not_a_pass(self, scanner, tmp_path, monkeypatch, capsys):
        root = tmp_path / "empty"
        root.mkdir()
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 2
        out = capsys.readouterr().out
        assert "ZERO files" in out
        assert "Refusing to report success" in out
        assert "no credential-shaped file" not in out

    def test_an_empty_secrets_directory_still_refuses_success(self, scanner, tmp_path, monkeypatch, capsys):
        """Zero files is checked before findings, so an empty ``secrets/`` is exit 2, not a pass."""
        root = tmp_path / "root"
        (root / "secrets").mkdir(parents=True)
        _use_root(monkeypatch, scanner, root)

        assert scanner.main() == 2
        out = capsys.readouterr().out
        assert "ZERO files" in out
        assert "Refusing to report success" in out
        assert "no credential-shaped file" not in out


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Which trees the image actually ships
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestScanRoots:
    def _patch(self, monkeypatch, scanner, *, app: Path | None, purelib: str | None) -> None:
        real_path = scanner.Path

        def fake_path(value, *args, **kwargs):
            if value == "/app":
                return app if app is not None else real_path("/no/such/app-for-scan-roots-test")
            return real_path(value, *args, **kwargs)

        monkeypatch.setattr(scanner, "Path", fake_path)
        paths = {} if purelib is None else {"purelib": purelib}
        monkeypatch.setattr(scanner.sysconfig, "get_paths", lambda: paths)

    def test_app_comes_first_then_the_shipped_package_trees_in_name_order(self, scanner, tmp_path, monkeypatch):
        app = tmp_path / "app"
        app.mkdir()
        site = tmp_path / "site"
        site.mkdir()
        for name in (
            "juniper_cascor_worker",
            "juniper_cascor_worker-0.6.1.dist-info",
            "cascade_correlation",
            "candidate_unit",
            "numpy",
            "Juniper_upper",
            "notjuniper",
        ):
            (site / name).mkdir()
        (site / "juniper_marker.py").write_text("not a directory", encoding="utf-8")
        self._patch(monkeypatch, scanner, app=app, purelib=str(site))

        roots = scanner.scan_roots()
        assert [p.name for p in roots] == [
            "app",
            "candidate_unit",
            "cascade_correlation",
            "juniper_cascor_worker",
            "juniper_cascor_worker-0.6.1.dist-info",
        ]

    def test_a_missing_app_leaves_only_the_package_trees(self, scanner, tmp_path, monkeypatch):
        site = tmp_path / "site"
        (site / "candidate_unit").mkdir(parents=True)
        self._patch(monkeypatch, scanner, app=None, purelib=str(site))

        assert [p.name for p in scanner.scan_roots()] == ["candidate_unit"]

    def test_a_missing_site_packages_leaves_only_app(self, scanner, tmp_path, monkeypatch):
        app = tmp_path / "app"
        app.mkdir()
        self._patch(monkeypatch, scanner, app=app, purelib=str(tmp_path / "absent-site"))

        assert scanner.scan_roots() == [app]

    def test_no_app_and_no_site_packages_is_an_empty_root_list(self, scanner, monkeypatch):
        self._patch(monkeypatch, scanner, app=None, purelib=None)

        assert scanner.scan_roots() == []


# ─────────────────────────────────────────────────────────────────────────────────────────────
# The two defences around the scan: dockerignore patterns, and the publish workflow running it
# ─────────────────────────────────────────────────────────────────────────────────────────────
class TestDockerignoreAndPublishWiring:
    def test_credential_patterns_are_doubled_for_nested_paths_and_the_example_stays_last(self):
        text = DOCKERIGNORE.read_text(encoding="utf-8")
        assert CREDENTIAL_BLOCK in text
        nonempty = [line for line in text.splitlines() if line.strip()]
        assert nonempty[-1] == "!.env.example"

    def test_paths_filter_covers_the_script(self):
        assert SCRIPT_REL in _publish()["on"]["pull_request"]["paths"]

    def test_the_smoke_arm_runs_it_inside_the_built_image(self):
        step = _publish_step("Smoke test (build-only runs)")
        assert step["if"] == BUILD_ONLY_IF
        assert 'docker run --rm -i --entrypoint python "${img}" - < util/check_image_no_secrets.py' in step["run"]

    def test_the_publish_arm_runs_it_on_the_pushed_digest_before_export(self):
        steps = _publish()["jobs"]["build"]["steps"]
        names = [str(s.get("name", "")) for s in steps]
        verify = next(i for i, name in enumerate(names) if name.startswith("Verify pushed image is CPU-only"))
        export = next(i for i, name in enumerate(names) if name.startswith("Export digest"))
        assert verify < export, "a credential finding must fail the arch before its digest is exported"
        step = steps[verify]
        assert step["if"] == PUBLISH_IF
        run = step["run"]
        assert 'ref="${REGISTRY}/${IMAGE_NAME}@${digest}"' in run
        assert 'docker run --rm -i --entrypoint python "${ref}" - < util/check_image_no_secrets.py' in run
        assert run.index(SCRIPT_REL) < run.index("import juniper_cascor_worker")
