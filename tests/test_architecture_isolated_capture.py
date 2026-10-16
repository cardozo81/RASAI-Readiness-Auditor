"""Negative-path checks of OCI architecture capture; Docker is never run here."""
from types import SimpleNamespace
from unittest.mock import patch
import json

from rasai.architecture_isolated_capture import (
    OFFLINE_IMAGE, capture_isolated_public_architecture,
    inspect_local_image, sandbox_command,
)
from rasai.domain import DeviceContext


DIGEST = "sha256:" + "a" * 64


def test_offline_sandbox_uses_no_network_no_mounts_and_nonroot():
    args = sandbox_command("docker", DIGEST)
    assert args[0:2] == ["docker", "run"]
    assert "--network=none" in args
    assert "--read-only" in args
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges" in args
    assert "--user=10001:10001" in args
    assert "--pull=never" in args
    assert "--memory=1g" in args and "--pids-limit=128" in args
    assert not any(arg.startswith(("-v", "--volume", "--mount",
                                    "--privileged", "--network=host")) for arg in args)
    assert args[-1] == DIGEST


def test_preflight_requires_locally_resolved_immutable_oci_image(monkeypatch):
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda name: "/usr/bin/docker")
    def fake_run(argv, **kwargs):
        if argv[1] == "context":
            return SimpleNamespace(returncode=0, stdout="unix:///var/run/docker.sock")
        return SimpleNamespace(returncode=0, stdout=DIGEST)
    with patch("rasai.architecture_isolated_capture.subprocess.run",
               side_effect=fake_run) as runner:
        assert inspect_local_image() == DIGEST
    assert runner.call_args.args[0] == [
        "/usr/bin/docker", "image", "inspect", "--format", "{{.Id}}", OFFLINE_IMAGE
    ]


def test_preflight_rejects_missing_or_unverified_image_before_http(monkeypatch):
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda name: None)
    with patch("rasai.architecture_isolated_capture._default_resolver") as dns, patch(
        "rasai.architecture_isolated_capture.PublicWebFetcher"
    ) as fetch:
        got = capture_isolated_public_architecture(
            "https://example.org/", DeviceContext.MOBILE
        )
    assert got.quality_reason == "OCI_IMAGE_NOT_AVAILABLE"
    assert got.raw_html is None and got.rendered_html is None
    dns.assert_not_called()
    fetch.assert_not_called()


def test_capture_preloaded_document_in_networkless_container(monkeypatch):
    from rasai.architecture_isolated_capture import ContentFetchStatus
    html = b"<html><body><main>Visible server content.</main></body></html>"
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, final_url="https://example.org/",
        http_status=200, body=html, headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image",
                        lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda cmd: "docker")
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url",
                        lambda url, _resolver: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.return_value = root
        def fake_docker_run(argv, **kwargs):
            assert "--network=none" in argv
            assert "--read-only" in argv
            assert argv[-1] == DIGEST
            assert "api_key" not in kwargs["input"].lower()
            bundle = json.loads(kwargs["input"])
            assert bundle["device"] == "mobile"
            assert len(bundle["resources"]) == 1
            assert bundle["resources"][0]["url"] == "https://example.org/"
            return SimpleNamespace(
                returncode=0, stdout=json.dumps({
                    "reason": None, "rendered_html": html.decode("utf-8")
                }),
            )
        with patch("rasai.architecture_isolated_capture.subprocess.run",
                   side_effect=fake_docker_run):
            got = capture_isolated_public_architecture(
                "https://example.org/", DeviceContext.MOBILE
            )
    assert got.quality_reason is None
    assert got.raw_html == got.rendered_html == html.decode()


def test_container_failure_abstains_without_ungated_browser(monkeypatch):
    from rasai.architecture_isolated_capture import ContentFetchStatus
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, final_url="https://example.org/",
        http_status=200, body=b"<main>safe</main>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image",
                        lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda _cmd: "docker")
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url",
                        lambda url, _resolver: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_isolated_capture.subprocess.run",
        return_value=SimpleNamespace(returncode=125, stdout="", stderr="docker unavailable"),
    ):
        fetch.return_value.fetch.return_value = root
        result = capture_isolated_public_architecture(
            "https://example.org/", DeviceContext.DESKTOP
        )
    assert result.quality_reason == "ISOLATED_RENDER_INCONCLUSIVE"
    assert result.rendered_html is None


def test_deprecated_guard_flag_alone_does_not_trigger_capture(monkeypatch):
    from rasai.architecture_live_capture import capture_public_architecture
    monkeypatch.setenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", "1")
    monkeypatch.delenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", raising=False)
    with patch("rasai.architecture_live_capture._default_resolver") as resolver:
        result = capture_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "SAFE_EGRESS_NOT_CONFIGURED"
    resolver.assert_not_called()


def test_remote_docker_daemon_rejected_before_inspecting_image(monkeypatch):
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda name: "/usr/bin/docker")
    monkeypatch.setenv("DOCKER_HOST", "tcp://192.168.1.20:2375")
    with patch("rasai.architecture_isolated_capture.subprocess.run") as run:
        assert inspect_local_image() is None
    run.assert_not_called()


def test_remote_docker_context_rejected_before_inspecting_image(monkeypatch):
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda name: "/usr/bin/docker")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    with patch("rasai.architecture_isolated_capture.subprocess.run",
               return_value=SimpleNamespace(returncode=0, stdout="ssh://server.example")) as run:
        assert inspect_local_image() is None
    assert run.call_count == 1
    assert run.call_args.args[0][1:3] == ["context", "inspect"]


def test_physical_isolation_probe_requires_all_socket_checks(monkeypatch):
    from rasai.architecture_isolation_smoke import verify_isolation
    monkeypatch.setattr("rasai.architecture_isolation_smoke.inspect_local_image",
                        lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolation_smoke.shutil.which",
                        lambda cmd: "docker")
    def runner(argv, **kwargs):
        assert "--network=none" in argv
        assert "--entrypoint=python" in argv
        assert argv[-3] == DIGEST
        assert argv[-2] == "-c"
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            name: True for name in ("public_ipv4", "private_ipv4",
            "link_local_metadata", "loopback", "private_ipv6",
            "loopback_ipv6", "external_dns")
        }))
    with patch("rasai.architecture_isolation_smoke.subprocess.run",
               side_effect=runner):
        assert all(verify_isolation().values())
