"""Canonical prerequisite lifecycle: deterministic, no real Docker or downloads."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rasai.runtime_prerequisites import (
    ARCHITECTURE_BROWSER, prepare_prerequisite,
)


def test_ready_image_needs_no_prompt_or_build():
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value="sha256:" + "a" * 64), patch(
        "rasai.runtime_prerequisites.subprocess.run"
    ) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER,
            consent=lambda _: (_ for _ in ()).throw(AssertionError("no prompt")),
        )
    assert result.ready and not result.changed
    run.assert_not_called()


def test_missing_docker_never_prompts_or_downloads():
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.runtime_prerequisites.shutil.which", return_value=None
    ), patch("rasai.runtime_prerequisites.subprocess.run") as run:
        result = prepare_prerequisite(ARCHITECTURE_BROWSER, consent=lambda _: True)
    assert not result.ready and result.reason == "DOCKER_INSTALL_REQUIRED"
    run.assert_not_called()


def test_declined_preparation_makes_no_host_changes(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run") as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=lambda _: False, source_root=tmp_path,
        )
    assert not result.ready and result.reason == "PREREQUISITE_DECLINED"
    run.assert_not_called()


def test_consented_build_reuses_single_fixed_image(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    consented = []
    def allow(message):
        consented.append(message)
        return True
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               side_effect=[None, "sha256:" + "b" * 64]), patch(
        "rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run",
             return_value=SimpleNamespace(returncode=0)) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=allow, source_root=tmp_path,
        )
    assert result.ready and result.changed and len(consented) == 1
    args = run.call_args.args[0]
    assert args[0:2] == ["docker", "build"]
    assert args[-1] == str(tmp_path.resolve())


def test_failed_build_cannot_claim_ready(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run",
             return_value=SimpleNamespace(returncode=1)):
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=lambda _: True, source_root=tmp_path,
        )
    assert not result.ready and result.reason == "OCI_BUILD_FAILED"


def test_unknown_capability_does_not_touch_host():
    with patch("rasai.runtime_prerequisites.shutil.which") as which:
        result = prepare_prerequisite("nonexistent", consent=lambda _: True)
    assert not result.ready
    which.assert_not_called()
