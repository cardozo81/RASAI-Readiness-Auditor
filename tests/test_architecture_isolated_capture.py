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
    assert "--pull=never" in args and "--log-driver=none" in args
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
        http_status=200, body=html, headers={"content-type": "text/html", "content-security-policy": "default-src 'self'"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image",
                        lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda cmd: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation",
                        lambda **kwargs: {"network_none": True})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary",
                        lambda **kwargs: None)
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
            assert bundle["resources"][0]["response_headers"]["content-security-policy"] == "default-src 'self'"
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
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation",
                        lambda **kwargs: {"network_none": True})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary",
                        lambda **kwargs: None)
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
    assert result.quality_reason == "OCI_WORKER_PROCESS_FAILED"
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
            "loopback_ipv6", "external_dns", "udp_public_ipv4",
            "udp_private_ipv4", "udp_metadata_ipv4", "udp_private_ipv6")
        }))
    with patch("rasai.architecture_isolation_smoke.subprocess.run",
               side_effect=runner):
        assert all(verify_isolation().values())


def test_unattested_oci_container_refuses_dns_and_http(monkeypatch):
    from rasai.architecture_isolation_smoke import verify_isolation
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image",
                        lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda _: "docker")
    def failure(**kwargs):
        raise RuntimeError("Unattested sockets")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", failure)
    with patch("rasai.architecture_isolated_capture._default_resolver") as dns, patch(
        "rasai.architecture_isolated_capture.PublicWebFetcher"
    ) as fetch:
        result = capture_isolated_public_architecture(
            "https://example.org/", DeviceContext.MOBILE
        )
    assert result.quality_reason == "OCI_NETWORK_ISOLATION_NOT_ATTESTED"
    dns.assert_not_called()
    fetch.assert_not_called()


def test_browser_canary_is_networkless_and_uses_bounded_synthetic_html():
    from rasai.architecture_isolation_smoke import verify_browser_canary
    def fake_run(command, **kwargs):
        assert "--network=none" in command
        assert "--read-only" in command
        assert "--pull=never" in command
        assert DIGEST == command[-1]
        manifest = json.loads(kwargs["input"])
        assert manifest["url"] == "https://example.org/"
        assert "rasai-offline-canary" in __import__("base64").b64decode(
            manifest["resources"][0]["body_b64"]
        ).decode()
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "reason": None,
                "rendered_html": "<html><main>rasai-offline-canary</main></html>",
            }),
        )
    with patch("rasai.architecture_isolation_smoke.subprocess.run", side_effect=fake_run):
        verify_browser_canary(digest=DIGEST, docker="docker")


def test_browser_canary_failure_blocks_site_dns(monkeypatch):
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **kwargs: {})
    def abort(**kwargs):
        raise RuntimeError("synthetic renderer unavailable")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", abort)
    with patch("rasai.architecture_isolated_capture._default_resolver") as resolver, patch(
        "rasai.architecture_isolated_capture.PublicWebFetcher"
    ) as fetch:
        result = capture_isolated_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "OCI_BROWSER_CANARY_FAILED"
    assert result.raw_html is None and result.rendered_html is None
    resolver.assert_not_called()
    fetch.assert_not_called()


def test_renderer_bounded_reason_is_preserved_instead_of_generic_inconclusive(monkeypatch):
    from rasai.architecture_isolated_capture import ContentFetchStatus
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/", http_status=200,
        body=b"<html><main>static</main></html>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **kwargs: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", lambda **kwargs: None)
    monkeypatch.setattr(
        "rasai.architecture_isolated_capture._validate_public_url", lambda url, _r: url
    )
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_isolated_capture.subprocess.run",
        return_value=SimpleNamespace(
            returncode=2, stdout=json.dumps({
                "rendered_html": None, "reason": "ISOLATED_RESOURCES_BLOCKED",
            }),
        ),
    ):
        fetch.return_value.fetch.return_value = root
        result = capture_isolated_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "ISOLATED_RESOURCES_BLOCKED"
    assert result.rendered_html is None


def test_worker_failure_does_not_disclose_untrusted_stderr(monkeypatch):
    from rasai.architecture_isolated_capture import ContentFetchStatus
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/", http_status=200,
        body=b"<html><main>static</main></html>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **kwargs: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", lambda **kwargs: None)
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", lambda url, _r: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_isolated_capture.subprocess.run",
        return_value=SimpleNamespace(returncode=125, stdout="", stderr="operator-secret"),
    ):
        fetch.return_value.fetch.return_value = root
        result = capture_isolated_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "OCI_WORKER_PROCESS_FAILED"
    assert "operator-secret" not in result.quality_reason


def test_canary_exposes_only_safe_enum_on_worker_failure():
    from rasai.architecture_isolation_smoke import verify_browser_canary
    value = SimpleNamespace(returncode=2, stdout=json.dumps({
        "rendered_html": None, "reason": "ISOLATED_BROWSER_UNAVAILABLE",
    }), stderr="untrusted-data")
    import pytest
    with patch("rasai.architecture_isolation_smoke.subprocess.run", return_value=value):
        with pytest.raises(RuntimeError, match="CANARY_ISOLATED_BROWSER_UNAVAILABLE"):
            verify_browser_canary(digest=DIGEST, docker="docker")
    value.stdout = json.dumps({"rendered_html": None, "reason": "SECRET_PLACEHOLDER"})
    with patch("rasai.architecture_isolation_smoke.subprocess.run", return_value=value):
        with pytest.raises(RuntimeError, match="CANARY_EXECUTION_FAILED"):
            verify_browser_canary(digest=DIGEST, docker="docker")



def test_html_asset_failure_is_diagnosed_before_docker_execution(monkeypatch):
    from rasai.architecture_isolated_capture import ContentFetchStatus
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/", http_status=200,
        body=b"<html><main>static</main></html>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **_: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", lambda **_: None)
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", lambda url, _: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_isolated_capture._bundle_resources",
        side_effect=ValueError("resources fail closed"),
    ), patch("rasai.architecture_isolated_capture.subprocess.run") as run:
        fetch.return_value.fetch.return_value = root
        result = capture_isolated_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert result.quality_reason == "OCI_ASSET_BUNDLE_REJECTED"
    run.assert_not_called()


def test_render_timeout_and_invalid_output_remain_distinct(monkeypatch):
    from rasai.architecture_isolated_capture import ContentFetchStatus
    import subprocess
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/", http_status=200,
        body=b"<html><main>static</main></html>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **_: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", lambda **_: None)
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", lambda url, _: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.return_value = root
        with patch("rasai.architecture_isolated_capture.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=40)):
            timed_out = capture_isolated_public_architecture("https://example.org/", DeviceContext.MOBILE)
        with patch("rasai.architecture_isolated_capture.subprocess.run",
                   return_value=SimpleNamespace(returncode=2, stdout="{", stderr="do not print")):
            invalid = capture_isolated_public_architecture("https://example.org/", DeviceContext.MOBILE)
    assert timed_out.quality_reason == "OCI_WORKER_TIMEOUT"
    assert invalid.quality_reason == "OCI_WORKER_OUTPUT_INVALID"



def test_cross_origin_script_public_asset_is_host_fetched_and_replayed(monkeypatch):
    from rasai.architecture_isolated_capture import _bundle_resources, ContentFetchStatus
    target = "https://example.org/"
    asset = "https://cdn.example.net/app.js"
    markup = '<html><main>Fixture</main><script src="' + asset + '"></script></html>'
    root = SimpleNamespace(status=ContentFetchStatus.OBSERVED,
                           final_url=target, http_status=200,
                           body=markup.encode(), headers={"content-type": "text/html"})
    resource = SimpleNamespace(status=ContentFetchStatus.OBSERVED,
                               final_url=asset, http_status=200,
                               body=b"console.log(1)", headers={"content-type": "text/javascript"})
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url",
                        lambda url, _: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.return_value = resource
        result = _bundle_resources(target, root, markup)
    assert [a["url"] for a in result] == [target, asset]
    fetch.return_value.fetch.assert_called_once_with(asset)


def test_invalid_resource_url_reports_specific_safe_reason():
    import pytest
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ArchitectureAssetFailure, ContentFetchStatus,
    )
    markup = '<html><main>Fixture</main><script src="javascript:alert(1)"></script></html>'
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/",
        http_status=200,
        body=markup.encode(),
        headers={"content-type": "text/html"},
    )
    with pytest.raises(ArchitectureAssetFailure) as raised:
        _bundle_resources("https://example.org/", root, markup)
    assert raised.value.reason == "OCI_ASSET_URL_REJECTED"


def test_inline_data_favicon_does_not_require_http_replay():
    from rasai.architecture_isolated_capture import (
        _AssetReferences, _bundle_resources, ContentFetchStatus,
    )
    markup = ('<html><head><link rel="icon" '
              'href="data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22%3E">'
              '</head><main>Static content</main></html>')
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/", http_status=200,
        body=markup.encode(), headers={"content-type": "text/html"},
    )
    parsed = _AssetReferences()
    parsed.feed(markup)
    assert parsed.urls == []
    assert [item["url"] for item in _bundle_resources("https://example.org/", root, markup)] == [
        "https://example.org/"
    ]


def test_inline_exemption_never_applies_to_script_or_stylesheet():
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ArchitectureAssetFailure, ContentFetchStatus,
    )
    import pytest
    examples = (
        '<script src="data:text/javascript,alert(1)"></script>',
        '<link rel="stylesheet" href="data:text/css,body%7B%7D">',
        '<link rel="icon stylesheet" href="data:text/css,body%7B%7D">',
        '<link rel="icon" href="javascript:alert(1)">',
        '<link rel="icon" href="data:text/javascript,alert(1)">',
    )
    for reference in examples:
        markup = "<html><main>Text</main>" + reference + "</html>"
        root = SimpleNamespace(
            status=ContentFetchStatus.OBSERVED,
            final_url="https://example.org/", http_status=200,
            body=markup.encode(), headers={"content-type": "text/html"},
        )
        with pytest.raises(ArchitectureAssetFailure, match="OCI_ASSET_URL_REJECTED"):
            _bundle_resources("https://example.org/", root, markup)


def test_private_favicon_destination_is_rejected_before_network(monkeypatch):
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ArchitectureAssetFailure, ContentFetchStatus,
    )
    import pytest
    markup = '<html><link rel="icon" href="http://127.0.0.1/icon.svg"></html>'
    root = SimpleNamespace(status=ContentFetchStatus.OBSERVED,
                           final_url="https://example.org/", http_status=200,
                           body=markup.encode(), headers={"content-type": "text/html"})
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        with pytest.raises(ArchitectureAssetFailure, match="OCI_CROSS_ORIGIN_ASSET_REJECTED"):
            _bundle_resources("https://example.org/", root, markup)
    fetch.assert_not_called()


def test_empty_data_favicon_sentinel_is_preserved_without_network_resource():
    from rasai.architecture_isolated_capture import (
        _AssetReferences, _bundle_resources, ContentFetchStatus,
    )
    markup = '<html><head><link rel="icon" href="data:,"></head><main>Content.</main></html>'
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED,
        final_url="https://example.org/", http_status=200,
        body=markup.encode("utf-8"), headers={"content-type": "text/html"},
    )
    reader = _AssetReferences()
    reader.feed(markup)
    assert reader.urls == []
    assert len(_bundle_resources("https://example.org/", root, markup)) == 1


def test_public_html_failure_reasons_are_specific_and_do_not_open_browser(monkeypatch):
    """#646: a redirect/HTTP failure cannot be mistaken for arbitrary HTML outage."""
    from rasai.architecture_isolated_capture import ContentFetchStatus

    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **_: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", lambda **_: None)
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", lambda url, _: url)

    cases = (
        (ContentFetchStatus.ERROR, 301, "TOO_MANY_REDIRECTS", "PUBLIC_REDIRECT_NOT_FOLLOWED"),
        (ContentFetchStatus.ERROR, 200, "CONTENT_BODY_LIMIT", "PUBLIC_HTML_SIZE_LIMIT"),
        (ContentFetchStatus.BLOCKED, None, "PUBLIC_WEB_DESTINATION_BLOCKED", "PUBLIC_DESTINATION_REJECTED"),
        (ContentFetchStatus.UNAVAILABLE, None, "CONTENT_TIMEOUT", "PUBLIC_TIMEOUT"),
        (ContentFetchStatus.OBSERVED, 403, None, "PUBLIC_HTTP_NOT_SUCCESS"),
        (ContentFetchStatus.OBSERVED, 200, None, "PUBLIC_RESPONSE_NOT_HTML"),
    )
    for status, code, error, expected in cases:
        document = SimpleNamespace(
            status=status, final_url="https://example.org/", http_status=code,
            error_code=error, body=b"", headers={"content-type": "application/json"},
        )
        with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
            "rasai.architecture_isolated_capture.subprocess.run"
        ) as docker_run:
            fetch.return_value.fetch.return_value = document
            result = capture_isolated_public_architecture(
                "https://example.org/", DeviceContext.MOBILE
            )
        assert result.quality_reason == expected
        assert result.rendered_html is None
        docker_run.assert_not_called()


def test_duplicate_resource_references_consume_one_slot_and_one_fetch(monkeypatch):
    """Repeated resource references must not consume the 64-resource budget."""
    from rasai.architecture_isolated_capture import _bundle_resources, ContentFetchStatus
    root_url = "https://example.org/"
    asset_url = "https://example.org/site.css"
    markup = "<html><head>" + (
        '<link rel="stylesheet" href="/site.css">' * 80
    ) + "</head><main>Valid</main></html>"
    def doc(url, payload=b"<style>body{color:black}</style>", mime="text/css"):
        return SimpleNamespace(
            status=ContentFetchStatus.OBSERVED, final_url=url, http_status=200,
            body=payload, headers={"content-type": mime},
        )
    root = doc(root_url, markup.encode(), "text/html")
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url",
                        lambda url, _: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        fetch.return_value.fetch.return_value = doc(asset_url)
        items = _bundle_resources(root_url, root, markup)
    assert [item["url"] for item in items] == [root_url, asset_url]
    fetch.return_value.fetch.assert_called_once_with(asset_url)


def test_64_unique_assets_are_acquired_with_same_public_destination_checks(monkeypatch):
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ContentFetchStatus, MAX_ASSETS,
    )
    assert MAX_ASSETS == 64
    root_url = "https://example.org/"
    markup = "<main>Example</main>" + "".join(
        f'<script src="/resource-{i}.js"></script>' for i in range(MAX_ASSETS)
    )
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, final_url=root_url,
        http_status=200, body=markup.encode(), headers={"content-type": "text/html"},
    )
    checked = []

    def validate(url, _resolver):
        checked.append(url)
        return url

    def fetch(url):
        return SimpleNamespace(
            status=ContentFetchStatus.OBSERVED, final_url=url, http_status=200,
            body=b"/* safe asset */", headers={"content-type": "text/javascript"},
        )

    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", validate)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetcher:
        fetcher.return_value.fetch.side_effect = fetch
        bundle = _bundle_resources(root_url, root, markup)
    assert len(bundle) == MAX_ASSETS + 1
    assert fetcher.return_value.fetch.call_count == MAX_ASSETS
    # Inventory AND immediate pre-request destination validation still occur.
    assert len(checked) == MAX_ASSETS * 2


def test_unique_resource_limit_refuses_before_network_or_partial_replay(monkeypatch):
    """The cap is strict for unique resources; even the 65th is not fetched."""
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ArchitectureAssetFailure, ContentFetchStatus, MAX_ASSETS,
    )
    import pytest
    root_url = "https://example.org/"
    markup = "<main>Example</main>" + "".join(
        f'<script src="/resource-{i}.js"></script>' for i in range(MAX_ASSETS + 1)
    )
    root = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, final_url=root_url,
        http_status=200, body=markup.encode(), headers={"content-type": "text/html"},
    )
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        with pytest.raises(ArchitectureAssetFailure, match="OCI_ASSET_COUNT_LIMIT"):
            _bundle_resources(root_url, root, markup)
    fetch.return_value.fetch.assert_not_called()


def test_invalid_cross_origin_resource_is_rejected_even_when_repeated(monkeypatch):
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ArchitectureAssetFailure, ContentFetchStatus,
    )
    import pytest
    root_url = "https://example.org/"
    markup = ('<script src="http://127.0.0.1/private.js"></script>' * 40)
    root = SimpleNamespace(status=ContentFetchStatus.OBSERVED, final_url=root_url,
                           http_status=200, body=markup.encode(), headers={"content-type": "text/html"})
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        with pytest.raises(ArchitectureAssetFailure, match="OCI_CROSS_ORIGIN_ASSET_REJECTED"):
            _bundle_resources(root_url, root, markup)
    fetch.assert_not_called()


def test_three_human_smoke_urls_have_distinct_deterministic_diagnostics(monkeypatch):
    """Regression fixtures for #646; NEVER fetch or assert live-site behavior.

    Each supplied URL is associated with a simulated failure condition. This
    exercises public diagnostic separation, not claims about current sites.
    Real HTTP must be confirmed in one later authorized Windows smoke.
    """
    from rasai.architecture_isolated_capture import ContentFetchStatus
    from rasai.architecture_probe import probe_architecture
    from rasai.console_architecture_discovery import describe_architecture_assessment

    cases = (
        ("https://loja.bradescoseguros.com.br/seguro-de-vida",
         ContentFetchStatus.OBSERVED, 200, None,
         "OCI_ASSET_COUNT_LIMIT", "Página excede"),
        ("https://mdsgroup.com/",
         ContentFetchStatus.OBSERVED, 403, None,
         "PUBLIC_HTTP_NOT_SUCCESS", "HTTP"),
        ("https://google.com/",
         ContentFetchStatus.ERROR, 301, "TOO_MANY_REDIRECTS",
         "PUBLIC_REDIRECT_NOT_FOLLOWED", "Redirecionamento"),
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image",
                        lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which",
                        lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation",
                        lambda **_: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary",
                        lambda **_: None)
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url",
                        lambda url, _: url)
    for url, status, code, error, expected, text in cases:
        document = SimpleNamespace(
            status=status, http_status=code, error_code=error, final_url=url,
            headers={"content-type": "text/html"},
            body=b"<main>Example</main>",
        )
        with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
            "rasai.architecture_isolated_capture._bundle_resources",
            side_effect=ValueError("asset fixture unavailable")
            if expected == "OCI_ASSET_COUNT_LIMIT" else None,
        ) as bundler, patch(
            "rasai.architecture_isolated_capture.subprocess.run"
        ) as docker_run:
            fetch.return_value.fetch.return_value = document
            if expected == "OCI_ASSET_COUNT_LIMIT":
                from rasai.architecture_isolated_capture import ArchitectureAssetFailure
                bundler.side_effect = ArchitectureAssetFailure(expected)
            observed = probe_architecture(
                url, DeviceContext.MOBILE,
                capture=capture_isolated_public_architecture,
            )
        assert observed.architecture.value == "UNKNOWN"
        assert observed.limitation == expected
        assert text in "\n".join(describe_architecture_assessment(observed))
        docker_run.assert_not_called()


def test_cross_origin_asset_revalidation_refuses_dns_change_before_fetch(monkeypatch):
    """Asset public on inventory but private before request must fail closed."""
    from rasai.architecture_isolated_capture import (
        _bundle_resources, ArchitectureAssetFailure, ContentFetchStatus,
    )
    import pytest
    url = "https://example.org/"
    asset = "https://cdn.example.net/app.js"
    raw = '<main>Example</main><script src="' + asset + '"></script>'
    root = SimpleNamespace(status=ContentFetchStatus.OBSERVED, final_url=url,
                           http_status=200, body=raw.encode(),
                           headers={"content-type": "text/html"})
    calls = []

    def public_check(candidate, resolver):
        calls.append(candidate)
        if candidate == asset and calls.count(asset) == 2:
            raise ValueError("destination changed to private address")
        return candidate

    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", public_check)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch:
        with pytest.raises(ArchitectureAssetFailure, match="OCI_CROSS_ORIGIN_ASSET_REJECTED"):
            _bundle_resources(url, root, raw)
        fetch.return_value.fetch.assert_not_called()
    assert calls == [asset, asset]

def test_redirected_partial_raw_preserves_actual_tls_final_url(monkeypatch):
    """#646: incomplete browser render must not misattribute redirected RAW."""
    from hashlib import sha256
    from rasai.architecture_isolated_capture import (
        ArchitectureAssetFailure, ContentFetchStatus,
    )
    from rasai.architecture_probe import probe_architecture

    requested, final = "http://example.org/", "https://example.org/"
    raw = "<main>" + "Visible content after public TLS upgrade. " * 4 + "</main>"
    document = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, final_url=final, redirects=(final,),
        http_status=200, body=raw.encode("utf-8"),
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr("rasai.architecture_isolated_capture.inspect_local_image", lambda: DIGEST)
    monkeypatch.setattr("rasai.architecture_isolated_capture.shutil.which", lambda _: "docker")
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_isolation", lambda **_: {})
    monkeypatch.setattr("rasai.architecture_isolation_smoke.verify_browser_canary", lambda **_: None)
    monkeypatch.setattr("rasai.architecture_isolated_capture._validate_public_url", lambda url, _: url)
    with patch("rasai.architecture_isolated_capture.PublicWebFetcher") as fetch, patch(
        "rasai.architecture_isolated_capture._bundle_resources",
        side_effect=ArchitectureAssetFailure("OCI_ASSET_COUNT_LIMIT"),
    ), patch("rasai.architecture_isolated_capture.subprocess.run") as docker_run:
        fetch.return_value.fetch.return_value = document
        captured = capture_isolated_public_architecture(requested, DeviceContext.MOBILE)
    docker_run.assert_not_called()
    assert captured.requested_url == requested
    assert captured.final_url == final
    assert captured.redirect_chain == (final,)
    assert captured.origin is not None
    assert captured.origin.raw_sha256 == sha256(raw.encode("utf-8")).hexdigest()
    assert captured.origin.rendered_sha256 is None
    assert captured.origin.transport == "PINNED_HTTP_STATIC"

    with patch("rasai.architecture_probe._default_resolver") as resolver:
        assessed = probe_architecture(
            requested, DeviceContext.MOBILE, capture=lambda _url, _device: captured,
        )
    resolver.assert_not_called()
    assert assessed.architecture.value == "UNKNOWN"
    assert assessed.limitation == "OCI_ASSET_COUNT_LIMIT"
    assert assessed.raw_available and not assessed.rendered_available
    assert assessed.redirect_hops_reported == 1
    assert assessed.protocol_transition == "HTTP_TO_HTTPS"
    assert assessed.acquisition_transport == "PINNED_HTTP_STATIC"
