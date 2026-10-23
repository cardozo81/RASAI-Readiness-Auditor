"""Canonical prerequisite lifecycle: deterministic, no real Docker or downloads."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rasai.architecture_image_identity import expected_source_sha256, WORKER_INPUTS

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


def test_worker_source_fingerprint_changes_only_when_worker_inputs_change(tmp_path):
    for relative in WORKER_INPUTS:
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("source A", encoding="utf-8")
    first = expected_source_sha256(tmp_path)
    assert len(first) == 64
    (tmp_path / "src/rasai/architecture_offline_worker.py").write_text(
        "source B", encoding="utf-8"
    )
    second = expected_source_sha256(tmp_path)
    assert first != second
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "independent.md").write_text("not a worker input")
    assert expected_source_sha256(tmp_path) == second


def test_missing_worker_source_refuses_fingerprint_without_build(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="OCI_WORKER_SOURCE_UNAVAILABLE"):
        expected_source_sha256(tmp_path)


def test_stale_image_prompts_and_rebuilds_once_with_explicit_consent(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    answers = []
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               side_effect=[None, "sha256:" + "b" * 64]), patch(
        "rasai.runtime_prerequisites.expected_source_sha256",
        return_value="c" * 64,
    ), patch(
        "rasai.architecture_isolated_capture.local_docker_transport", return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run",
             side_effect=[SimpleNamespace(returncode=0, stdout="29.8.2"),
                          SimpleNamespace(returncode=0)]) as run:
        outcome = prepare_prerequisite(
            ARCHITECTURE_BROWSER, source_root=tmp_path,
            consent=lambda message: answers.append(message) or True,
        )
    assert outcome.ready and outcome.changed
    assert len(answers) == 1 and "desatualizada" in answers[0]
    assert run.call_count == 2
    assert "--build-arg" in run.call_args.args[0]


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
               return_value=None), patch("rasai.runtime_prerequisites.expected_source_sha256", return_value="d" * 64), patch(
        "rasai.architecture_isolated_capture.local_docker_transport", return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which", return_value="docker"
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
        "rasai.runtime_prerequisites.expected_source_sha256",
        return_value="d" * 64,
    ), patch(
        "rasai.architecture_isolated_capture.local_docker_transport", return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run",
             side_effect=[SimpleNamespace(returncode=0, stdout="29.8.2"), SimpleNamespace(returncode=0)] ) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=allow, source_root=tmp_path,
        )
    assert result.ready and result.changed and len(consented) == 1
    args = run.call_args.args[0]
    assert args[0:2] == ["docker", "build"]
    assert "--build-arg" in args
    assert args[args.index("--build-arg") + 1] == (
        "RASAI_ARCHITECTURE_SOURCE_SHA256=" + "d" * 64
    )
    assert args[-1] == str(tmp_path.resolve())


def test_docker_build_discards_output_before_windows_charmap_decoder(tmp_path):
    """No PIPE readers: UTF-8 Docker progress cannot crash Windows CP1252."""
    import subprocess
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               side_effect=[None, "sha256:" + "b" * 64]), patch(
        "rasai.runtime_prerequisites.expected_source_sha256",
        return_value="d" * 64,
    ), patch(
        "rasai.architecture_isolated_capture.local_docker_transport", return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run",
             side_effect=[SimpleNamespace(returncode=0, stdout="29.8.2"),
                          SimpleNamespace(returncode=0)]) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=lambda _: True, source_root=tmp_path,
        )
    assert result.ready and result.changed
    build = run.call_args
    assert build.args[0][:2] == ["docker", "build"]
    assert build.kwargs["stdout"] == subprocess.DEVNULL
    assert build.kwargs["stderr"] == subprocess.DEVNULL
    assert build.kwargs["stdin"] == subprocess.DEVNULL
    assert "capture_output" not in build.kwargs
    assert "text" not in build.kwargs


def test_failed_build_cannot_claim_ready(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch("rasai.runtime_prerequisites.expected_source_sha256", return_value="d" * 64), patch(
        "rasai.architecture_isolated_capture.local_docker_transport", return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which", return_value="docker"
    ), patch("rasai.runtime_prerequisites.subprocess.run",
             side_effect=[SimpleNamespace(returncode=0, stdout="29.8.2"), SimpleNamespace(returncode=1)] ):
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=lambda _: True, source_root=tmp_path,
        )
    assert not result.ready and result.reason == "OCI_BUILD_FAILED"


def test_unknown_capability_does_not_touch_host():
    with patch("rasai.runtime_prerequisites.shutil.which") as which:
        result = prepare_prerequisite("nonexistent", consent=lambda _: True)
    assert not result.ready
    which.assert_not_called()


def test_remote_docker_cannot_build_or_prompt(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.architecture_isolated_capture.local_docker_transport",
        return_value=False
    ), patch("rasai.runtime_prerequisites.shutil.which",
             return_value="docker"), patch(
        "rasai.runtime_prerequisites.subprocess.run"
    ) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER,
            consent=lambda _: (_ for _ in ()).throw(AssertionError("unsafe prompt")),
            source_root=tmp_path,
        )
    assert not result.ready
    assert result.reason == "DOCKER_LOCAL_DAEMON_REQUIRED"
    run.assert_not_called()


def test_stopped_daemon_never_requests_consent_or_build(tmp_path):
    (tmp_path / "Dockerfile.architecture-offline").write_text("FROM scratch")
    (tmp_path / "pyproject.toml").write_text("[build-system]")
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.architecture_isolated_capture.local_docker_transport",
        return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which",
             return_value="docker"), patch(
        "rasai.runtime_prerequisites.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout="", stderr="private daemon details")
    ) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER,
            consent=lambda _: (_ for _ in ()).throw(AssertionError("unexpected consent")),
            source_root=tmp_path,
        )
    assert result.reason == "DOCKER_DAEMON_UNAVAILABLE" and not result.ready
    assert run.call_count == 1
    assert run.call_args.args[0][1] == "info"


def test_daemon_timeout_cannot_trigger_build(tmp_path):
    import subprocess
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.architecture_isolated_capture.local_docker_transport",
        return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which",
             return_value="docker"), patch(
        "rasai.runtime_prerequisites.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="docker info", timeout=10)
    ) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER,
            consent=lambda _: (_ for _ in ()).throw(AssertionError("unexpected consent")),
            source_root=tmp_path,
        )
    assert result.reason == "DOCKER_DAEMON_UNAVAILABLE" and not result.changed
    assert run.call_count == 1


def test_docker_permission_denied_is_safe_and_does_not_build(tmp_path):
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.architecture_isolated_capture.local_docker_transport",
        return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which",
             return_value="docker"), patch(
        "rasai.runtime_prerequisites.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout="",
                                     stderr="permission denied: confidential host path")
    ) as run:
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER,
            consent=lambda _: (_ for _ in ()).throw(AssertionError("no consent")),
            source_root=tmp_path,
        )
    assert result.reason == "DOCKER_PERMISSION_DENIED"
    assert not result.ready and not result.changed
    assert run.call_count == 1
    assert run.call_args.args[0][1] == "info"


def test_daemon_generic_error_never_leaks_stderr(tmp_path):
    with patch("rasai.architecture_isolated_capture.inspect_local_image",
               return_value=None), patch(
        "rasai.architecture_isolated_capture.local_docker_transport",
        return_value=True
    ), patch("rasai.runtime_prerequisites.shutil.which",
             return_value="docker"), patch(
        "rasai.runtime_prerequisites.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout="",
                                     stderr="internal daemon error: sensitive identifier")
    ):
        result = prepare_prerequisite(
            ARCHITECTURE_BROWSER, consent=lambda _: True, source_root=tmp_path,
        )
    assert result.reason == "DOCKER_DAEMON_UNAVAILABLE"
    assert "sensitive" not in result.reason
