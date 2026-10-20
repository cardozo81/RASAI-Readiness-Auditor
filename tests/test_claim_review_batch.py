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
