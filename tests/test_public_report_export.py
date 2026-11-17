"""Offline, adversarial checks for the independent #717 export profile."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

import pytest

from rasai.public_report_export import (
    CONTRACT, MANIFEST, export_public_catalog, verify_public_catalog_export,
)
from rasai.catalog_report_style import _JS as TRUSTED_UI_SCRIPT


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _with_trusted_script(html: str) -> str:
    assert "</body>" in html
    return html.replace("</body>", "<script>" + TRUSTED_UI_SCRIPT + "</script></body>")


def catalog_fixture(tmp_path: Path, *, html: str | None = None,
                    attachment: str | None = None, security_ok: bool = True) -> Path:
    root = tmp_path / "report-catalog"
    (root / "integrity").mkdir(parents=True)
    (root / "css").mkdir()
    db = root / "integrity" / "audit-snapshot.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE ai_exchange_log(response_payload TEXT)")
        connection.execute(
            "INSERT INTO ai_exchange_log VALUES (?)",
            ('{"output":[{"encrypted_content":"ghp_' + "X" * 24 + '"}]}',),
        )
    (root / "index.html").write_text(
        _with_trusted_script(
            html or '<!doctype html><html><head><link rel="stylesheet" href="css/site.css">'
            '</head><body><h1 id="overview">Resumo</h1>'
            '<a href="details.html#item-1">Abrir detalhe</a></body></html>'
        ),
        encoding="utf-8",
    )
    (root / "details.html").write_text(
        _with_trusted_script(
            '<!doctype html><html><body><h1 id="item-1">Detalhe</h1>'
            '<a href="index.html#overview">Voltar</a></body></html>'
        ), encoding="utf-8",
    )
    (root / "css" / "site.css").write_text("body { color: #123; }\n", encoding="utf-8")
    if attachment is not None:
        (root / "attachment.txt").write_text(attachment, encoding="utf-8")
    assurance = {
        "metric_semantics": "synthetic test fixture",
        "thresholds": {"security": 100},
        "global": {"security": 100},
        "package_integrity": {"final_source_snapshot_match": True},
        "closure_eligible": True,
        "global_output_security": {"passed": security_ok},
    }
    (root / "integrity" / "catalog-assurance.json").write_text(
        json.dumps(assurance), encoding="utf-8"
    )
    records = [
        {"path": p.relative_to(root).as_posix(), "sha256": digest(p.read_bytes()),
         "size_bytes": p.stat().st_size}
        for p in sorted(root.rglob("*")) if p.is_file()
    ]
    manifest = {
        "audit_id": "AUD-SYNTHETIC",
        "freshness": "FINAL",
        "audit_snapshot": {
            "path": "integrity/audit-snapshot.db",
            "sha256": digest(db.read_bytes()),
        },
        "packaged_files": records,
        "assurance": {
            key: assurance[key] for key in
            ("metric_semantics", "thresholds", "global", "package_integrity",
             "closure_eligible")
        } | {"artifact": "integrity/catalog-assurance.json"},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_export_is_isolated_deterministic_and_excludes_entire_sqlite(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path, attachment="Anexo técnico sem credenciais")
    before = {
        p.relative_to(root).as_posix(): digest(p.read_bytes())
        for p in root.rglob("*") if p.is_file()
    }
    first = export_public_catalog(root, tmp_path / "public-one.zip")
    second = export_public_catalog(root, tmp_path / "public-two.zip")
    assert first.read_bytes() == second.read_bytes()
    assert verify_public_catalog_export(first) == (True, ())
    with ZipFile(first) as archive:
        names = set(archive.namelist())
        assert names == {
            MANIFEST, "index.html", "details.html", "css/site.css", "attachment.txt"
        }
        assert b"encrypted_content" not in first.read_bytes()
        assert b"ghp_" not in first.read_bytes()
        receipt = json.loads(archive.read(MANIFEST))
        assert receipt["contract"] == CONTRACT
        assert receipt["forensic_equivalence"] is False
        assert receipt["privacy_review"] == "REQUIRED_BEFORE_DISTRIBUTION"
        assert "audit-snapshot.db" not in names
        assert "manifest.json" not in names
    after = {
        p.relative_to(root).as_posix(): digest(p.read_bytes())
        for p in root.rglob("*") if p.is_file()
    }
    assert after == before
    with pytest.raises(ValueError, match="destino"):
        export_public_catalog(root, first)


@pytest.mark.parametrize(
    "html",
    [
        '<html><body>encrypted_content: opaque-binary-payload</body></html>',
        '<html><body>Bearer ' + 'AVeryLongRealTokenValue12345</body></html>',
        '<html><body>ghp_' + "A" * 24 + '</body></html>',
        '<html><body>contato: titular@private.example</body></html>',
        '<html><body>CPF 123.456.789-01</body></html>',
        '<html><body><a href="missing.html">quebrado</a></body></html>',
        '<html><body><img src="../outside.png"></body></html>',
        '<html><body><script src="https://evil.example/script.js"></script></body></html>',
        '<html><body><iframe src="https://evil.example"></iframe></body></html>',
        '<html><body><a href="details.html#missing">âncora</a></body></html>',
    ],
)
def test_export_refuses_sensitive_or_broken_html(tmp_path: Path, html: str) -> None:
    root = catalog_fixture(tmp_path, html=html)
    destination = tmp_path / "refused.zip"
    with pytest.raises(ValueError, match="recusada"):
        export_public_catalog(root, destination)
    assert not destination.exists()


def test_export_refuses_sensitive_attachment(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path, attachment="Authorization: " + "Bearer " + "SecretReallySensitiveToken")
    with pytest.raises(ValueError):
        export_public_catalog(root, tmp_path / "refused.zip")
    assert not (tmp_path / "refused.zip").exists()


def test_export_refuses_insecure_assurance_and_invalid_source(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path, security_ok=False)
    with pytest.raises(ValueError, match="segurança"):
        export_public_catalog(root, tmp_path / "failed.zip")
    root.joinpath("index.html").write_text("<p>tampered</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="canônico"):
        export_public_catalog(root, tmp_path / "failed.zip")
    assert not (tmp_path / "failed.zip").exists()


def test_export_detects_unmanifested_file(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    (root / "hidden.ini").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="não inventariados"):
        export_public_catalog(root, tmp_path / "blocked.zip")


def test_export_verifier_rejects_zip_extra_files_and_tampering(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    exported = export_public_catalog(root, tmp_path / "public.zip")
    with ZipFile(exported, "a") as archive:
        archive.writestr("integrity/audit-snapshot.db", b"fake-raw-db")
    ok, failures = verify_public_catalog_export(exported)
    assert not ok and failures
    with ZipFile(exported, "a") as archive:
        archive.writestr("../outside.txt", "zip slip")
    ok, failures = verify_public_catalog_export(exported)
    assert not ok and failures


def test_export_verifier_rejects_hashed_text_modified_in_zip(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    exported = export_public_catalog(root, tmp_path / "public.zip")
    with ZipFile(exported, "a") as archive:
        # Duplicate member is not a legitimate replacement.
        archive.writestr("index.html", "<h1>tampered</h1>")
    ok, failures = verify_public_catalog_export(exported)
    assert not ok and failures


def test_export_disallows_destination_within_source(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    with pytest.raises(ValueError, match="destino"):
        export_public_catalog(root, root / "public.zip")


def test_export_textual_attachment_must_be_utf8_and_no_embedded_null(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path, attachment="OK")
    attachment = root / "attachment.txt"
    attachment.write_bytes(b"\xff\x00")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["packaged_files"]:
        if record["path"] == "attachment.txt":
            record["size_bytes"] = attachment.stat().st_size
            record["sha256"] = digest(attachment.read_bytes())
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="recusada"):
        export_public_catalog(root, tmp_path / "blocked.zip")


def test_export_verifier_rejects_uninventoried_zip_comment(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    exported = export_public_catalog(root, tmp_path / "public.zip")
    with ZipFile(exported, "a") as archive:
        archive.comment = b"unmanifested metadata"
    assert verify_public_catalog_export(exported)[0] is False


def test_export_rejects_nonfinal_source_even_if_hashes_are_valid(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    path = root / "manifest.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["freshness"] = "PARTIAL"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="não final"):
        export_public_catalog(root, tmp_path / "blocked.zip")


def test_export_rejects_symlinked_source_root(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable in this runtime")
    with pytest.raises(ValueError, match="symlink"):
        export_public_catalog(alias, tmp_path / "blocked.zip")


@pytest.mark.parametrize("attack", [
    '<img src="https://remote.example/track.png">',
    '<div onerror="dangerousAction()">evento</div>',
    '<button formaction="https://remote.example/collect">Transmitir</button>',
    '<div style="background:url(https://remote.example/collect)">X</div>',
    '<style>@import "https://remote.example/style.css";</style>',
    '<style>body{background:url(https://remote.example/track.png)}</style>',
    '<script>dangerousAction()</script>',
    '<script src="local.js"></script>',
    '<svg><image href="https://remote.example/snoop"></image></svg>',
    '<meta http-equiv="refresh" content="1;url=https://remote.example">',
    '<img srcset="https://remote.example/evil 1x">',
    '<iframe srcdoc="<h1>hidden</h1>"></iframe>',
])
def test_export_rejects_active_or_untrusted_markup(tmp_path: Path, attack: str) -> None:
    valid = (
        '<!doctype html><html><body><h1 id="overview">Resumo</h1>'
        + attack
        + '<a href="details.html#item-1">Detalhes</a></body></html>'
    )
    root = catalog_fixture(tmp_path, html=valid)
    with pytest.raises(ValueError, match="recusada"):
        export_public_catalog(root, tmp_path / "blocked.zip")


def test_export_allows_canonical_static_ui_and_local_css(tmp_path: Path) -> None:
    valid = (
        '<!doctype html><html><body><h1 id="overview">Resumo</h1>'
        '<style>main{color:rgb(2,3,4)}</style>'
        '<a href="details.html#item-1">Detalhes</a></body></html>'
    )
    root = catalog_fixture(tmp_path, html=valid)
    exported = export_public_catalog(root, tmp_path / "candidate.zip")
    assert verify_public_catalog_export(exported) == (True, ())


def test_export_verifier_rejects_zip_appended_overlay(tmp_path: Path) -> None:
    root = catalog_fixture(tmp_path)
    exported = export_public_catalog(root, tmp_path / "candidate.zip")
    assert verify_public_catalog_export(exported) == (True, ())
    with exported.open("ab") as handle:
        handle.write(b"overlay bytes not present in the ZIP inventory")
    assert verify_public_catalog_export(exported)[0] is False


def test_export_from_real_catalog_renderer_with_synthetic_audit(tmp_path: Path) -> None:
    """Prove integration with the current canonical 21-page renderer, offline."""
    from rasai.audit_configuration_reuse import configuration_hash
    from rasai.catalog_report_site import materialize_catalog_report_site
    from tests.test_catalog_report_site import AUDIT_ID, _workspace

    workspace, _noncatalog = _workspace(tmp_path)
    # That upstream test deliberately injects a secret-shaped config in order
    # to test redaction. Use an untainted config for this public-export fixture.
    with sqlite3.connect(workspace.database) as connection:
        config = json.loads(connection.execute(
            "SELECT configuration_json FROM audit_execution_configurations WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0])
        config["settings"]["environment"].pop("RASAI_OPENAI_API_KEY", None)
        connection.execute(
            "UPDATE audit_execution_configurations SET configuration_json=?, configuration_hash=? "
            "WHERE audit_id=?",
            (json.dumps(config, ensure_ascii=False), configuration_hash(config), AUDIT_ID),
        )
    index = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace)
    from rasai.catalog_report_site import verify_catalog_report_package
    assert verify_catalog_report_package(index.parent)[0] is True
    artifact = export_public_catalog(index.parent, tmp_path / "candidate.zip")
    assert verify_public_catalog_export(artifact) == (True, ())
    with ZipFile(artifact) as archive:
        assert len([name for name in archive.namelist() if name.endswith(".html")]) >= 20
        assert "integrity/audit-snapshot.db" not in archive.namelist()
