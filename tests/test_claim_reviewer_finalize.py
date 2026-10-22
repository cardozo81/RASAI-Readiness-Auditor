"""#603: reviewer-owned packet finalization, entirely offline/no AUD or HTTP."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from rasai.claim_review_receipt import verify_claim_review_receipt
from scripts.claim_review_reviewer_finalize import finalize_reviewer_packet

_KEY = b"k" * 32
_ALLOWED = frozenset({"reviewer-internal-01"})
_AUD = "AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF"


def _private(tmp_path: Path) -> Path:
    root = tmp_path / "private-603"
    root.mkdir()
    (root / "manifest.template.json").write_text(json.dumps({
        "audit_id": _AUD, "at_date": "2026-10-14",
        "claims": [{
            "claim_id": "CLM-603-REVIEW-PENDING",
            "snapshot_id": "SNP-0AE3B21E599D46C2AD41F2808C20AEA3",
            "claim_file": "claim.txt", "document_file": "conditions.txt",
            "receipt_file": "receipt.json",
            "product_scope": "REVISOR_DEVE_INFORMAR_PRODUTO_E_VERSAO_REAIS",
        }],
    }), encoding="utf-8")
    (root / "claim.txt").write_text(
        "Cobertura esta sujeita as condicoes contratuais.",
        encoding="utf-8",
    )
    (root / "conditions.txt").write_text(
        "Este texto identifica o escopo contratual vigente no produto revisado.",
        encoding="utf-8",
    )
    (root / "review.authorized.json").write_text(json.dumps({
        "source_url": "https://www.example.org/arquivo-oficial",
        "effective_from": "2025-01-01", "effective_until": "2027-12-31",
        "collected_on": date.today().isoformat(),
        "reviewed_on": date.today().isoformat(),
        "product_scope": "PRODUTO-VERSAO-AUTENTICADA-PELO-REVISOR",
        "document_version": "2026-01", "issuer": "Emitente comprovado",
        "reviewer_receipt_id": "PRIV-REVIEW-1",
        "reviewer_id": "reviewer-internal-01",
        "matched_excerpt": "escopo contratual vigente no produto revisado",
        "review_decision": "CORROBORATES",
        "independent_source_authenticity_verified": True,
    }), encoding="utf-8")
    return root


def _finalize(root, **kwargs):
    return finalize_reviewer_packet(
        root, trusted_key=kwargs.pop("trusted_key", _KEY),
        trusted_reviewer_ids=kwargs.pop("trusted_reviewer_ids", _ALLOWED),
        reviewer_confirmed=kwargs.pop("reviewer_confirmed", True),
    )


def test_reviewer_input_and_real_private_key_finalize_then_reuse_idempotently(tmp_path):
    root = _private(tmp_path)
    first = _finalize(root)
    assert first["status"] == "PRIVATE_REVIEW_PACKET_FINALIZED"
    assert first["signed_receipt_created"] and first["manifest_created"]
    assert first["final_physical_aud_gate_required"] is True
    assert first["official_source_authenticated_by_tool"] is False
    envelope = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["claims"][0]["product_scope"] == envelope["review"]["product_scope"]
    assert envelope["review"]["claim_text"] == (root / "claim.txt").read_text()
    assert "document_sha256" in envelope["review"]
    verified = verify_claim_review_receipt(
        envelope["review"]["claim_text"], product_scope=envelope["review"]["product_scope"],
        at_date=date.fromisoformat(manifest["at_date"]),
        primary_bytes=(root / "conditions.txt").read_bytes(),
        receipt=envelope["review"], receipt_mac=envelope["mac"],
        trusted_key=_KEY, trusted_reviewer_ids=_ALLOWED,
        require_collection_date=True,
    )
    assert verified["state"] == "CLAIM_CORROBORATED"
    originals = [(root / p).read_bytes() for p in ("receipt.json", "manifest.json")]
    second = _finalize(root)
    assert second["status"] == "PRIVATE_REVIEW_PACKET_REUSED"
    assert not second["signed_receipt_created"] and not second["manifest_created"]
    assert [(root / p).read_bytes() for p in ("receipt.json", "manifest.json")] == originals


@pytest.mark.parametrize("change", [
    {"reviewer_confirmed": False},
    {"trusted_key": b""},
    {"trusted_reviewer_ids": frozenset({"other"})},
])
def test_no_reviewer_confirmation_or_trust_no_files(tmp_path, change):
    root = _private(tmp_path)
    with pytest.raises(ValueError):
        _finalize(root, **change)
    assert not (root / "receipt.json").exists()
    assert not (root / "manifest.json").exists()


@pytest.mark.parametrize("field,value", [
    ("matched_excerpt", "not present in official source"),
    ("product_scope", "  "),
    ("independent_source_authenticity_verified", False),
    ("effective_until", "2025-01-01"),
    ("source_url", "http://not-https.example.org/"),
    ("review_decision", "UNREVIEWED"),
    ("collected_on", "2099-01-01"),
])
def test_invalid_authorized_evidence_not_signed(tmp_path, field, value):
    root = _private(tmp_path)
    path = root / "review.authorized.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj[field] = value
    path.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(ValueError):
        _finalize(root)
    assert not (root / "receipt.json").exists()
    assert not (root / "manifest.json").exists()


def test_untrusted_duplicate_json_refused(tmp_path):
    root = _private(tmp_path)
    (root / "review.authorized.json").write_text(
        '{"reviewer_id":"reviewer-internal-01","reviewer_id":"forged"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _finalize(root)
    assert not (root / "receipt.json").exists()


def test_existing_review_material_is_never_overwritten(tmp_path):
    root = _private(tmp_path)
    receipt = root / "receipt.json"
    receipt.write_bytes(b"real reviewer work MUST survive")
    with pytest.raises(ValueError, match="no overwrite"):
        _finalize(root)
    assert receipt.read_bytes() == b"real reviewer work MUST survive"
    assert not (root / "manifest.json").exists()


def test_symlink_source_refused(tmp_path):
    root = _private(tmp_path)
    (root / "conditions.txt").unlink()
    (tmp_path / "external.txt").write_text("external private bytes")
    try:
        (root / "conditions.txt").symlink_to(tmp_path / "external.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError):
        _finalize(root)
    assert not (root / "receipt.json").exists()


def test_packet_refuses_wrong_aud_identity(tmp_path):
    root = _private(tmp_path)
    p = root / "manifest.template.json"
    obj = json.loads(p.read_text())
    obj["audit_id"] = "AUD-OTHER"
    p.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        _finalize(root)
