"""#603: offline batch documentary reviews, without AUD or provider writes."""
from datetime import date
from hashlib import sha256
import hmac
import json

from rasai.claim_review_batch import inspect_claim_review_batch, main
from rasai.claim_review_batch_html import render_claim_review_batch_html

KEY = b"independent-trusted-document-review-key-32bytes"
REVIEWERS = frozenset({"reviewer-1"})


def _fixture(tmp_path):
    folder = tmp_path / "review-packet"
    folder.mkdir()
    claim = "Life cover starts after 24 hours"
    document = (
        b"Source conditions: Life cover starts after 24 hours "
        b"for product A on receipt date."
    )
    (folder / "claim.txt").write_text(claim, encoding="utf-8")
    (folder / "document.txt").write_bytes(document)

    def signed(decision):
        receipt = {
            "source_url": "https://official.example.test/conditions",
            "document_sha256": sha256(document).hexdigest(),
            "effective_from": "2026-01-01",
            "effective_until": "2026-12-31",
            "reviewed_on": "2026-10-12",
            "collected_on": "2026-10-11",
            "product_scope": "product-A",
            "claim_text": claim,
            "document_version": "2026.1",
            "issuer": "Independent issuer assessed by reviewer",
            "reviewer_receipt_id": "receipt-1",
            "reviewer_id": "reviewer-1",
            "matched_excerpt": "Life cover starts after 24 hours",
            "review_decision": decision,
            "independent_source_authenticity_verified": True,
        }
        payload = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {"review": receipt, "mac": hmac.new(KEY, payload, sha256).hexdigest()}

    (folder / "valid.json").write_text(
        json.dumps(signed("CORROBORATES")), encoding="utf-8",
    )
    (folder / "contradicted.json").write_text(
        json.dumps(signed("CONTRADICTS")), encoding="utf-8",
    )
    poisoned = signed("CORROBORATES")
    poisoned["review"]["document_version"] = "wrong-new-version"
    (folder / "tampered.json").write_text(
        json.dumps(poisoned), encoding="utf-8",
    )
    manifest = {
        "audit_id": "AUD-OPERATOR-LABEL",
        "at_date": "2026-10-14",
        "claims": [
            {"claim_id": identity, "claim_file": "claim.txt",
             "document_file": "document.txt",
             "receipt_file": receipt_path,
             "product_scope": "product-A"}
            for identity, receipt_path in [
                ("C-VALID", "valid.json"),
                ("C-DISPUTED", "contradicted.json"),
                ("C-HTML<script>", "tampered.json"),
            ]
        ],
    }
    (folder / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    return folder


def test_603_multi_claim_packet_preserves_document_version_and_abstention(tmp_path):
    folder = _fixture(tmp_path)
    originals = {path.name: path.read_bytes() for path in folder.iterdir()}
    result = inspect_claim_review_batch(
        folder / "manifest.json",
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert result["audit_id_operator_label_only"] == "AUD-OPERATOR-LABEL"
    assert result["claims_total"] == 3
    rows = {row["claim_id"]: row for row in result["claims"]}
    assert rows["C-VALID"]["state"] == "CLAIM_CORROBORATED"
    assert rows["C-DISPUTED"]["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"
    assert rows["C-HTML<script>"]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert rows["C-VALID"]["source_version_verified"] is True
    assert rows["C-VALID"]["document_sha256"] == sha256(
        (folder / "document.txt").read_bytes(),
    ).hexdigest()
    assert rows["C-VALID"]["collected_on"] == "2026-10-11"
    assert rows["C-HTML<script>"]["source_version_verified"] is False
    assert "document_sha256" not in rows["C-HTML<script>"]
    assert result["legal_compliance_certified"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0

    html = render_claim_review_batch_html(result)
    assert "Corroboração documental por revisor autenticado" in html
    assert "Contradição documental apontada por revisor autenticado" in html
    assert "Não validado contra documentação oficial vigente" in html
    assert "C-HTML&lt;script&gt;" in html
    assert "C-HTML<script>" not in html
    assert "não equivale a conformidade" in html

    assert {p.name: p.read_bytes() for p in folder.iterdir()} == originals


def test_603_missing_key_and_cross_scope_are_unverified(tmp_path):
    folder = _fixture(tmp_path)
    for key, reviewers in (
        (b"", REVIEWERS),
        (KEY, frozenset({"other-reviewer"})),
    ):
        result = inspect_claim_review_batch(
            folder / "manifest.json",
            trusted_key=key, trusted_reviewer_ids=reviewers,
        )
        if key == b"":
            assert result["status"] == "NOT_VERIFIABLE"
            assert result["claims"] == []
        else:
            assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
            assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
                       for row in result["claims"])
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["claims"][0]["product_scope"] = "another-product"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS,
    )
    assert result["claims"][0]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"


def test_603_unsafe_members_do_not_escape_manifest_directory(tmp_path):
    folder = _fixture(tmp_path)
    manifest_file = folder / "manifest.json"
    original = json.loads(manifest_file.read_text())
    for unsafe in ("../other/claim.txt", "/outside.txt"):
        changed = dict(original)
        changed["claims"] = [dict(original["claims"][0])]
        changed["claims"][0]["claim_file"] = unsafe
        manifest_file.write_text(json.dumps(changed))
        result = inspect_claim_review_batch(
            manifest_file, trusted_key=KEY,
            trusted_reviewer_ids=REVIEWERS,
        )
        assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
        assert result["claims"][0]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    if hasattr((folder / "alias.txt"), "symlink_to"):
        try:
            (folder / "alias.txt").symlink_to(folder / "claim.txt")
        except (OSError, NotImplementedError):
            return
        changed["claims"][0]["claim_file"] = "alias.txt"
        manifest_file.write_text(json.dumps(changed))
        result = inspect_claim_review_batch(
            manifest_file, trusted_key=KEY,
            trusted_reviewer_ids=REVIEWERS,
        )
        assert result["claims"][0]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"


def test_603_batch_cli_outputs_json_and_html_without_aud_creation(tmp_path, monkeypatch, capsys):
    folder = _fixture(tmp_path)
    monkeypatch.setenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", KEY.hex())
    monkeypatch.setenv("RASAI_CLAIM_REVIEWER_ALLOWLIST", "reviewer-1")
    for format in ("json", "html"):
        code = main(["--manifest", str(folder / "manifest.json"), "--format", format])
        text = capsys.readouterr().out
        assert code == 0
        if format == "json":
            assert json.loads(text)["claims_total"] == 3
        else:
            assert text.startswith("<!doctype html>")
            assert "C-DISPUTED" in text
    assert not any(p.is_dir() for p in folder.iterdir())

def test_603_invalid_primary_url_abstains_only_affected_signed_claim(tmp_path):
    """One malformed but re-signed URL must not poison unrelated reviews."""
    folder = _fixture(tmp_path)
    receipt_path = folder / "valid.json"
    envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
    envelope["review"]["source_url"] = "https://@official.example.test/conditions"
    payload = json.dumps(
        envelope["review"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    envelope["mac"] = hmac.new(KEY, payload, sha256).hexdigest()
    receipt_path.write_text(json.dumps(envelope), encoding="utf-8")
    result = inspect_claim_review_batch(
        folder / "manifest.json",
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    rows = {row["claim_id"]: row for row in result["claims"]}
    assert rows["C-VALID"]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert rows["C-DISPUTED"]["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"
    assert rows["C-VALID"]["source_version_verified"] is False


def test_603_batch_rejects_silent_claim_whitespace_normalization(tmp_path):
    folder = _fixture(tmp_path)
    source = folder / "claim.txt"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = inspect_claim_review_batch(folder / "manifest.json", trusted_key=KEY, trusted_reviewer_ids=REVIEWERS)
    assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL" for row in result["claims"])

def _aud_with_claim_snapshot(tmp_path, packet):
    """Synthetic physical AUD, no provider or real-browser operation."""
    import sqlite3
    root = tmp_path / "AUD-OPERATOR-LABEL"
    root.mkdir()
    literal = (packet / "claim.txt").read_text(encoding="utf-8")
    path = root / "artifacts" / "capture" / "main.txt"
    path.parent.mkdir(parents=True)
    path.write_text("Observed page copy: " + literal + ". End.", encoding="utf-8")
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript("""
            CREATE TABLE audits (
                audit_id TEXT, status TEXT, completion_status TEXT
            );
            CREATE TABLE pages (page_id TEXT, audit_id TEXT);
            CREATE TABLE page_snapshots (
                snapshot_id TEXT, page_id TEXT, main_content_ref TEXT,
                captured_at TEXT
            );
            INSERT INTO audits VALUES (
                'AUD-OPERATOR-LABEL','COMPLETED','COMPLETE'
            );
            INSERT INTO pages VALUES ('PAGE-1','AUD-OPERATOR-LABEL');
            INSERT INTO page_snapshots VALUES (
                'SNP-SIGNED','PAGE-1','artifacts/capture/main.txt',
                '2026-10-14T15:30:00+00:00'
            );
        """)
    manifest_file = packet / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    for claim in manifest["claims"]:
        claim["snapshot_id"] = "SNP-SIGNED"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    return root, path


def test_603_optin_binding_preserves_trusted_reviews_and_physical_source(tmp_path):
    folder = _fixture(tmp_path)
    root, text = _aud_with_claim_snapshot(tmp_path, folder)
    before_db = (root / "audit.db").read_bytes()
    before_text = text.read_bytes()
    before_manifest = (folder / "manifest.json").read_bytes()
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert result["audit_binding_mode"] == "OBSERVATIONAL_BINDING_CHECKED"
    assert result["audit_db_sha256"] == sha256(before_db).hexdigest()
    rows = {row["claim_id"]: row for row in result["claims"]}
    assert rows["C-VALID"]["state"] == "CLAIM_CORROBORATED"
    assert rows["C-DISPUTED"]["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"
    assert rows["C-HTML<script>"]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert all(
        row["audit_binding"]["status"] == "TEXT_PRESENT_IN_SNAPSHOT_MAIN_CONTENT"
        for row in rows.values()
    )
    assert rows["C-VALID"]["audit_binding"]["page_id"] == "PAGE-1"
    assert rows["C-VALID"]["audit_binding"]["main_content_sha256"] == sha256(
        before_text,
    ).hexdigest()
    page = render_claim_review_batch_html(result)
    assert "Vínculo textual à captura AUD" in page
    assert "OBSERVATIONAL_BINDING_CHECKED" in page
    assert "C-HTML&lt;script&gt;" in page
    assert "<script>" not in page
    assert (root / "audit.db").read_bytes() == before_db
    assert text.read_bytes() == before_text
    assert (folder / "manifest.json").read_bytes() == before_manifest
    assert result["provider_requests"] == result["audit_writes"] == 0


def test_603_optin_missing_literal_abstains_without_false_aud_corroboration(tmp_path):
    folder = _fixture(tmp_path)
    root, text = _aud_with_claim_snapshot(tmp_path, folder)
    text.write_text("Completely different actual page body.", encoding="utf-8")
    out = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    assert out["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert out["audit_binding_mode"] == "OBSERVATIONAL_BINDING_CHECKED"
    assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL" for row in out["claims"])
    assert all(row["basis"] == "AUD_CLAIM_TEXT_BINDING_NOT_PROVEN" for row in out["claims"])
    assert all(row["audit_binding"]["status"] == "NOT_VERIFIED" for row in out["claims"])


def test_603_optin_wrong_aud_or_ambiguous_snapshot_is_rejected(tmp_path):
    import sqlite3
    folder = _fixture(tmp_path)
    root, _ = _aud_with_claim_snapshot(tmp_path, folder)
    wrong = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=tmp_path / "AUD-OTHER",
    )
    assert wrong["status"] == "NOT_VERIFIABLE"
    assert wrong["reason"] == "AUD_BINDING_NOT_VERIFIABLE"
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("INSERT INTO pages VALUES ('P-OTHER','AUD-FOREIGN')")
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?)",
            ("SNP-SIGNED", "P-OTHER", "artifacts/capture/main.txt"),
        )
    out = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    assert out["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL" for row in out["claims"])
    assert all(row["audit_binding"]["status"] == "NOT_VERIFIED" for row in out["claims"])


def test_603_optin_out_of_scope_artifact_and_sqlite_sidecar_are_rejected(tmp_path):
    import sqlite3
    folder = _fixture(tmp_path)
    root, _ = _aud_with_claim_snapshot(tmp_path, folder)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "UPDATE page_snapshots SET main_content_ref='../foreign.txt'"
        )
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL" for row in result["claims"])
    (root / "audit.db-wal").write_bytes(b"pending")
    rejected = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    assert rejected["status"] == "NOT_VERIFIABLE"
    assert rejected["claims"] == []


def test_603_optin_cli_accepts_only_matching_aud_source(tmp_path, monkeypatch, capsys):
    folder = _fixture(tmp_path)
    root, _ = _aud_with_claim_snapshot(tmp_path, folder)
    monkeypatch.setenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", KEY.hex())
    monkeypatch.setenv("RASAI_CLAIM_REVIEWER_ALLOWLIST", "reviewer-1")
    assert main([
        "--manifest", str(folder / "manifest.json"),
        "--audit-directory", str(root), "--format", "json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audit_binding_mode"] == "OBSERVATIONAL_BINDING_CHECKED"
    assert payload["claims"][0]["audit_binding"]["snapshot_id"] == "SNP-SIGNED"
    assert list(root.glob("**/audit.db-*")) == []



def test_603_optin_required_collection_date_abstains_without_changing_legacy(tmp_path):
    """Material claims cannot promote a signed document with unknown collection date."""
    folder = _fixture(tmp_path)
    source = folder / "valid.json"
    envelope = json.loads(source.read_text(encoding="utf-8"))
    envelope["review"].pop("collected_on")
    payload = json.dumps(
        envelope["review"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    envelope["mac"] = hmac.new(KEY, payload, sha256).hexdigest()
    source.write_text(json.dumps(envelope), encoding="utf-8")
    original = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS,
    )
    strict = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, require_collection_date=True,
    )
    legacy_rows = {row["claim_id"]: row for row in original["claims"]}
    strict_rows = {row["claim_id"]: row for row in strict["claims"]}
    assert original["document_collection_date_policy"] == "LEGACY_OPTIONAL"
    assert strict["document_collection_date_policy"] == "REQUIRED"
    assert legacy_rows["C-VALID"]["state"] == "CLAIM_CORROBORATED"
    assert strict_rows["C-VALID"]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert strict_rows["C-VALID"]["basis"] == "PRIMARY_COLLECTION_DATE_NOT_VERIFIED"
    assert strict_rows["C-DISPUTED"]["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"
    assert "source_url_attested" not in strict_rows["C-VALID"]
    assert "PRIMARY_COLLECTION_DATE_NOT_VERIFIED" in render_claim_review_batch_html(strict)


def test_603_strict_policy_cli_and_single_receipt_respect_collection_provenance(
    tmp_path, monkeypatch, capsys,
):
    from rasai.claim_review_import_cli import inspect_local_claim_receipt
    folder = _fixture(tmp_path)
    monkeypatch.setenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", KEY.hex())
    monkeypatch.setenv("RASAI_CLAIM_REVIEWER_ALLOWLIST", "reviewer-1")
    source = folder / "valid.json"
    envelope = json.loads(source.read_text(encoding="utf-8"))
    envelope["review"].pop("collected_on")
    payload = json.dumps(
        envelope["review"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    envelope["mac"] = hmac.new(KEY, payload, sha256).hexdigest()
    source.write_text(json.dumps(envelope), encoding="utf-8")
    checked = inspect_local_claim_receipt(
        claim_file=folder / "claim.txt",
        document_file=folder / "document.txt",
        receipt_file=source,
        product_scope="product-A", at_date=date(2026, 10, 14),
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
        require_collection_date=True,
    )
    assert checked["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert checked["basis"] == "PRIMARY_COLLECTION_DATE_NOT_VERIFIED"
    code = main([
        "--manifest", str(folder / "manifest.json"),
        "--format", "json", "--require-collection-date",
    ])
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["document_collection_date_policy"] == "REQUIRED"
    assert result["claims"][0]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert result["claims"][1]["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"


def test_603_missing_primary_file_preserves_physically_observed_claim_without_corroboration(tmp_path):
    """The absence of a primary document does not erase the AUD's own wording."""
    folder = _fixture(tmp_path)
    root, artifact = _aud_with_claim_snapshot(tmp_path, folder)
    before_db = (root / "audit.db").read_bytes()
    before_artifact = artifact.read_bytes()
    (folder / "document.txt").unlink()
    response = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
        require_collection_date=True,
    )
    assert response["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert response["audit_binding_mode"] == "OBSERVATIONAL_BINDING_CHECKED"
    assert all(row["audit_observation_state"] == "CLAIM_OBSERVED"
               for row in response["claims"])
    assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
               for row in response["claims"])
    assert all(not row["source_version_verified"] for row in response["claims"])
    text = render_claim_review_batch_html(response)
    assert "Observação da alegação" in text
    assert "Alegação observada literalmente na AUD" in text
    assert "Não validado contra documentação oficial vigente" in text
    assert "não apaga a alegação" in text
    assert (root / "audit.db").read_bytes() == before_db
    assert artifact.read_bytes() == before_artifact


def test_603_missing_signed_receipt_is_not_a_false_absence_of_claim(tmp_path):
    folder = _fixture(tmp_path)
    root, _artifact = _aud_with_claim_snapshot(tmp_path, folder)
    (folder / "valid.json").unlink()
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    rows = {row["claim_id"]: row for row in result["claims"]}
    assert rows["C-VALID"]["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert rows["C-VALID"]["audit_observation_state"] == "CLAIM_OBSERVED"
    assert rows["C-DISPUTED"]["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"
    assert rows["C-DISPUTED"]["audit_observation_state"] == "CLAIM_OBSERVED"


def test_603_unrelated_snapshot_never_claims_observation_or_documentary_verification(tmp_path):
    folder = _fixture(tmp_path)
    root, artifact = _aud_with_claim_snapshot(tmp_path, folder)
    artifact.write_text("A wholly unrelated document, no product text.", encoding="utf-8")
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=root,
    )
    assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
    assert all(row["audit_observation_state"] == "NOT_VERIFIED"
               for row in result["claims"])
    assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
               for row in result["claims"])
    page = render_claim_review_batch_html(result)
    assert "Alegação não comprovada no snapshot da AUD" in page
    assert "Alegação observada literalmente na AUD" not in page


def test_603_without_aud_binding_never_claims_literal_aud_observation(tmp_path):
    folder = _fixture(tmp_path)
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS,
    )
    assert result["audit_binding_mode"] == "NOT_REQUESTED"
    assert all("audit_observation_state" not in row for row in result["claims"])
    page = render_claim_review_batch_html(result)
    assert "Observação física da alegação não solicitada" in page
    assert "Alegação observada literalmente na AUD" not in page


def test_documentary_executive_advisory_is_strict_and_never_rewrites_aud(tmp_path):
    from rasai.report_claim_review_advisory import inspect_documentary_claim_advisory
    folder = _fixture(tmp_path)
    root, artifact = _aud_with_claim_snapshot(tmp_path, folder)
    original_db = (root / "audit.db").read_bytes()
    original_artifact = artifact.read_bytes()
    summary = inspect_documentary_claim_advisory(
        root, folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS,
    )
    assert summary["status"] == "AUD_BOUND_DOCUMENTARY_REVIEW_OBSERVED"
    assert summary["population"] == "SUBMITTED_CLAIMS_ONLY"
    assert summary["claims_submitted"] == 3
    assert summary["claims_observed_in_aud"] == 3
    assert summary["claims_reviewed_as_corroborated"] == 1
    assert summary["claims_reviewed_as_contradicted"] == 1
    assert summary["claims_without_documentary_verification"] == 1
    assert summary["collection_date_policy"] == "REQUIRED"
    assert summary["official_source_authenticated_by_this_tool"] is False
    assert summary["legal_or_regulatory_conformity_certified"] is False
    assert summary["provider_requests"] == summary["audit_writes"] == 0
    assert "Life cover starts" not in str(summary)
    assert "https://official.example.test" not in str(summary)
    assert "reviewer-1" not in str(summary)
    assert (root / "audit.db").read_bytes() == original_db
    assert artifact.read_bytes() == original_artifact


def test_documentary_executive_advisory_denies_missing_trust_and_unrelated_aud(tmp_path):
    from rasai.report_claim_review_advisory import inspect_documentary_claim_advisory
    folder = _fixture(tmp_path)
    root, _artifact = _aud_with_claim_snapshot(tmp_path, folder)
    manifest = folder / "manifest.json"
    for key, reviewers in (
        (b"", REVIEWERS), (KEY, frozenset({"unknown-reviewer"})),
        (KEY, frozenset()),
    ):
        summary = inspect_documentary_claim_advisory(
            root, manifest, trusted_key=key, trusted_reviewer_ids=reviewers,
        )
        if key == b"" or not reviewers:
            assert summary["status"] == "NOT_VERIFIABLE"
        else:
            # Authorized reviewers are a per-claim check, not evidence
            # the physical AUD or reviewer decision was authenticated.
            assert summary["claims_reviewed_as_corroborated"] == 0
            assert summary["claims_reviewed_as_contradicted"] == 0
            assert summary["claims_without_documentary_verification"] == 3
    different = tmp_path / "AUD-OTHER"
    different.mkdir()
    unrelated = inspect_documentary_claim_advisory(
        different, manifest, trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    assert unrelated["status"] == "NOT_VERIFIABLE"
    assert "claims_submitted" not in unrelated


def test_documentary_executive_advisory_requires_signed_collection_date(tmp_path):
    from rasai.report_claim_review_advisory import inspect_documentary_claim_advisory
    folder = _fixture(tmp_path)
    root, _artifact = _aud_with_claim_snapshot(tmp_path, folder)
    signed = folder / "valid.json"
    envelope = json.loads(signed.read_text(encoding="utf-8"))
    envelope["review"].pop("collected_on")
    encoded = json.dumps(
        envelope["review"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    envelope["mac"] = hmac.new(KEY, encoded, sha256).hexdigest()
    signed.write_text(json.dumps(envelope), encoding="utf-8")
    summary = inspect_documentary_claim_advisory(
        root, folder / "manifest.json",
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    assert summary["status"] == "AUD_BOUND_DOCUMENTARY_REVIEW_OBSERVED"
    assert summary["claims_observed_in_aud"] == 3
    assert summary["claims_reviewed_as_corroborated"] == 0
    assert summary["claims_reviewed_as_contradicted"] == 1
    assert summary["claims_without_documentary_verification"] == 2
    assert summary["legal_or_regulatory_conformity_certified"] is False


def test_documentary_executive_advisory_abstains_on_changed_source(tmp_path):
    from rasai.report_claim_review_advisory import inspect_documentary_claim_advisory
    folder = _fixture(tmp_path)
    root, _artifact = _aud_with_claim_snapshot(tmp_path, folder)
    (root / "audit.db-wal").write_bytes(b"unsealed")
    summary = inspect_documentary_claim_advisory(
        root, folder / "manifest.json",
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    assert summary["status"] == "NOT_VERIFIABLE"
    assert "claims_reviewed_as_corroborated" not in summary


def test_documentary_advisory_rejects_artifact_replaced_after_batch_binding(
    tmp_path, monkeypatch,
):
    """A successful initial binding must not attest bytes changed afterward."""
    from rasai import report_claim_review_advisory as adapter
    folder = _fixture(tmp_path)
    root, artifact = _aud_with_claim_snapshot(tmp_path, folder)
    real_batch = adapter.inspect_claim_review_batch

    def replace_after_binding(*args, **kwargs):
        result = real_batch(*args, **kwargs)
        assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
        artifact.write_text("The original claim disappeared.", encoding="utf-8")
        return result

    monkeypatch.setattr(adapter, "inspect_claim_review_batch", replace_after_binding)
    projected = adapter.inspect_documentary_claim_advisory(
        root, folder / "manifest.json",
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    assert projected["status"] == "NOT_VERIFIABLE"
    assert "claims_reviewed_as_corroborated" not in projected
    assert projected["audit_writes"] == projected["provider_requests"] == 0


def test_documentary_advisory_rejects_wal_created_after_batch_binding(
    tmp_path, monkeypatch,
):
    """A post-read SQLite WAL forbids treating a changing AUD as sealed."""
    from rasai import report_claim_review_advisory as adapter
    folder = _fixture(tmp_path)
    root, _artifact = _aud_with_claim_snapshot(tmp_path, folder)
    real_batch = adapter.inspect_claim_review_batch

    def create_journal_after_binding(*args, **kwargs):
        result = real_batch(*args, **kwargs)
        assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
        (root / "audit.db-wal").write_bytes(b"concurrent-write")
        return result

    monkeypatch.setattr(
        adapter, "inspect_claim_review_batch", create_journal_after_binding,
    )
    projected = adapter.inspect_documentary_claim_advisory(
        root, folder / "manifest.json",
        trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
    )
    assert projected["status"] == "NOT_VERIFIABLE"
    assert "claims_observed_in_aud" not in projected


def test_603_capture_time_bound_to_aud_prevents_manifest_backdating(tmp_path):
    folder = _fixture(tmp_path)
    aud, artifact = _aud_with_claim_snapshot(tmp_path, folder)
    manifest_file = folder / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    before_db = (aud / "audit.db").read_bytes()
    before_artifact = artifact.read_bytes()
    for wrong_date in ("2026-09-14", "2026-10-15"):
        manifest["at_date"] = wrong_date
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        result = inspect_claim_review_batch(
            manifest_file, trusted_key=KEY, trusted_reviewer_ids=REVIEWERS,
            audit_directory=aud, require_collection_date=True,
        )
        assert result["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
        assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
                   for row in result["claims"])
        assert all(row["audit_binding"]["reason"] == "SNAPSHOT_CAPTURE_DATE_NOT_ATTESTED"
                   for row in result["claims"])
    assert (aud / "audit.db").read_bytes() == before_db
    assert artifact.read_bytes() == before_artifact


def test_603_unsigned_snapshot_timestamp_refused_and_offset_normalized(tmp_path):
    import sqlite3
    folder = _fixture(tmp_path)
    aud, _ = _aud_with_claim_snapshot(tmp_path, folder)
    for invalid in ("2026-10-14T15:30:00", "", "invalid"):
        with sqlite3.connect(aud / "audit.db") as con:
            con.execute("UPDATE page_snapshots SET captured_at=?", (invalid,))
        result = inspect_claim_review_batch(
            folder / "manifest.json", trusted_key=KEY,
            trusted_reviewer_ids=REVIEWERS, audit_directory=aud,
        )
        assert all(row["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
                   for row in result["claims"])
    with sqlite3.connect(aud / "audit.db") as con:
        con.execute("UPDATE page_snapshots SET captured_at=?",
                    ("2026-10-14T12:30:00-03:00",))
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=aud,
    )
    assert result["claims"][0]["state"] == "CLAIM_CORROBORATED"


def test_603_capture_timestamp_column_required_for_optin_aud(tmp_path):
    import sqlite3
    folder = _fixture(tmp_path)
    aud, _ = _aud_with_claim_snapshot(tmp_path, folder)
    with sqlite3.connect(aud / "audit.db") as con:
        con.execute("ALTER TABLE page_snapshots DROP COLUMN captured_at")
    result = inspect_claim_review_batch(
        folder / "manifest.json", trusted_key=KEY,
        trusted_reviewer_ids=REVIEWERS, audit_directory=aud,
    )
    assert result["status"] == "NOT_VERIFIABLE"
    assert result["reason"] == "AUD_BINDING_NOT_VERIFIABLE"
    assert result["claims"] == []


def test_603_one_command_physical_gate_is_redacted_and_readonly(tmp_path, monkeypatch, capsys):
    from rasai.claim_review_physical_gate import main as gate_main
    folder = _fixture(tmp_path)
    aud, artifact = _aud_with_claim_snapshot(tmp_path, folder)
    before_db = (aud / "audit.db").read_bytes()
    before_artifact = artifact.read_bytes()
    monkeypatch.setenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", KEY.hex())
    monkeypatch.setenv("RASAI_CLAIM_REVIEWER_ALLOWLIST", "reviewer-1")
    assert gate_main(["--audit-directory", str(aud),
                      "--manifest", str(folder / "manifest.json")]) == 0
    output = capsys.readouterr().out
    public = json.loads(output)
    assert public["status"] == "AUTHENTICATED_REVIEW_AND_AUD_LINK_VERIFIED"
    assert public["promoted_documentary_decisions"] == 2
    assert public["official_source_authenticated_by_this_tool"] is False
    assert public["legal_compliance_certified"] is False
    assert public["audit_writes"] == public["provider_requests"] == 0
    assert "Life cover" not in output
    assert KEY.hex() not in output
    assert (aud / "audit.db").read_bytes() == before_db
    assert artifact.read_bytes() == before_artifact
    monkeypatch.delenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX")
    assert gate_main(["--audit-directory", str(aud),
                      "--manifest", str(folder / "manifest.json")]) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["status"] == "NOT_VERIFIABLE"
