from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tarfile

from rasai.domain import Audit, DeviceContext, DiscoverySource, Page, PageSnapshot, utc_now
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.web_platform_baseline import (
    DATA_ARTIFACT,
    METADATA_ARTIFACT,
    OBSERVATIONS_ARTIFACT,
    NPM_LATEST_URL,
    _resolve_dataset,
    detect_compat_features,
    materialize_web_platform_baseline,
)


def _dataset_payload(*, status: str | bool = "high") -> bytes:
    return json.dumps(
        {
            "features": {
                "dialog": {
                    "kind": "feature",
                    "name": "Dialog",
                    "description": "HTML dialog element",
                    "status": {"baseline": status},
                    "compat_features": ["html.elements.dialog"],
                }
            }
        },
        sort_keys=True,
    ).encode("utf-8")


def _tarball_with_data_json(payload: bytes) -> bytes:
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo("package/data.json")
        member.size = len(payload)
        archive.addfile(member, BytesIO(payload))
    return buffer.getvalue()


def test_detector_maps_html_css_and_inline_js_without_refetching_external_assets() -> None:
    known = {
        "html.elements.dialog",
        "css.properties.display.grid",
        "api.Document.querySelector",
    }
    html = """
    <!doctype html>
    <html><head>
      <link rel="stylesheet" href="/site.css">
      <style>.card { display: grid; }</style>
    </head><body>
      <dialog open>Teste</dialog>
      <script>document.querySelector('.card')</script>
      <script src="/app.js"></script>
    </body></html>
    """

    signals, metadata = detect_compat_features(html, known)

    assert known.issubset(signals)
    assert metadata["external_scripts_not_refetched"] == 1
    assert metadata["external_stylesheets_not_refetched"] == 1
    assert metadata["inline_css_chars"] > 0
    assert metadata["inline_js_chars"] > 0


def test_auto_dataset_is_frozen_and_reused_without_second_network_resolution(tmp_path: Path) -> None:
    workspace = AuditWorkspace.create(tmp_path, "AUD-WEBDX-FREEZE")
    data_payload = _dataset_payload()
    tarball = _tarball_with_data_json(data_payload)
    tarball_url = "https://registry.npmjs.org/web-features/-/web-features-9.9.9.tgz"
    calls: list[str] = []

    def fake_read_url(url: str, **_: object) -> bytes:
        calls.append(url)
        if url == NPM_LATEST_URL:
            return json.dumps(
                {
                    "version": "9.9.9",
                    "dist": {
                        "tarball": tarball_url,
                        "integrity": "sha512-test",
                        "shasum": "deadbeef",
                    },
                }
            ).encode("utf-8")
        if url == tarball_url:
            return tarball
        raise AssertionError(f"unexpected URL: {url}")

    first_data, first_metadata = _resolve_dataset(
        workspace,
        {"RASAI_WEB_FEATURES_DATASET": "auto"},
        read_url=fake_read_url,
    )

    assert calls == [NPM_LATEST_URL, tarball_url]
    assert first_data["features"]["dialog"]["status"]["baseline"] == "high"
    assert first_metadata["version"] == "9.9.9"
    assert len(first_metadata["sha256"]) == 64
    assert (workspace.root / DATA_ARTIFACT).is_file()
    assert (workspace.root / METADATA_ARTIFACT).is_file()

    def no_network(*_: object, **__: object) -> bytes:
        raise AssertionError("frozen AUD must be reopened before any network resolution")

    second_data, second_metadata = _resolve_dataset(
        workspace,
        {"RASAI_WEB_FEATURES_DATASET": "auto"},
        read_url=no_network,
    )

    assert second_data == first_data
    assert second_metadata["sha256"] == first_metadata["sha256"]
    assert second_metadata["version"] == first_metadata["version"]


def test_materialization_persists_feature_classification_and_service_success(tmp_path: Path) -> None:
    workspace = AuditWorkspace.create(tmp_path, "AUD-WEBDX")
    rendered_ref = Path("artifacts", "rendered", "page.html")
    rendered_path = workspace.root / rendered_ref
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text("<!doctype html><html><body><dialog open>Teste</dialog></body></html>", encoding="utf-8")

    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(
            Audit(
                audit_id="AUD-WEBDX",
                project_name="webdx-test",
                auditor_version="test",
                ruleset_version="test",
            )
        )
        persistence.pages.add(
            Page(
                page_id="P-WEBDX",
                audit_id="AUD-WEBDX",
                normalized_url="https://example.com/",
                discovered_url="https://example.com/",
                discovery_sources=(DiscoverySource.SEED,),
            )
        )
        persistence.snapshots.add(
            PageSnapshot(
                snapshot_id="S-WEBDX",
                page_id="P-WEBDX",
                device=DeviceContext.MOBILE,
                requested_url="https://example.com/",
                final_url="https://example.com/",
                captured_at=utc_now(),
                http_status=200,
                content_type="text/html",
                rendered_artifact_ref=rendered_ref.as_posix(),
            )
        )

    local_dataset = tmp_path / "data.json"
    local_dataset.write_bytes(_dataset_payload(status="high"))

    result = materialize_web_platform_baseline(
        audit_id="AUD-WEBDX",
        workspace=workspace,
        env={
            "RASAI_WEB_PLATFORM_BASELINE": "true",
            "RASAI_WEB_FEATURES_DATASET": str(local_dataset),
        },
    )

    assert result["state"] == "SUCCESS"
    assert result["attempted"] == 1
    assert result["succeeded"] == 1
    assert result["detected_features"] == 1
    assert (workspace.root / OBSERVATIONS_ARTIFACT).is_file()

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        service_run = connection.execute(
            "SELECT state,targets_attempted,targets_succeeded FROM standards_service_runs "
            "WHERE audit_id=? AND service_id=?",
            ("AUD-WEBDX", "web-platform-baseline"),
        ).fetchone()
        feature = connection.execute(
            "SELECT metric_id,state,target,device FROM standards_metric_observations "
            "WHERE audit_id=? AND metric_id=?",
            ("AUD-WEBDX", "web_platform_feature::dialog"),
        ).fetchone()
    finally:
        connection.close()

    assert service_run is not None
    assert dict(service_run) == {
        "state": "SUCCESS",
        "targets_attempted": 1,
        "targets_succeeded": 1,
    }
    assert feature is not None
    assert feature["state"] == "WIDELY_AVAILABLE"
    assert feature["target"] == "https://example.com/"
    assert feature["device"] == "MOBILE"

    observations = json.loads((workspace.root / OBSERVATIONS_ARTIFACT).read_text(encoding="utf-8"))
    rendered = json.dumps(observations, sort_keys=True)
    assert "dialog" in rendered
    assert "WIDELY_AVAILABLE" in rendered
