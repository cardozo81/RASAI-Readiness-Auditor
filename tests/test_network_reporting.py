"""#659 G1: sidecar should never mutate frozen audit bytes."""
import json
import pytest

from rasai.network_observation_store import (
    persist_network_observations, read_network_observations, sidecar_path,
)
from rasai.network_reporting import materialize_network_report


def test_legacy_report_is_neutral(tmp_path):
    page = materialize_network_report(tmp_path, "AUD-LEGACY")
    assert "Dados ainda indisponíveis" in page.read_text(encoding="utf-8")
    assert not sidecar_path(tmp_path).exists()


def test_sidecar_requires_audit_and_valid_id(tmp_path):
    assert persist_network_observations(tmp_path, "AUD-LEGACY") is None
    with pytest.raises(ValueError):
        persist_network_observations(tmp_path, "../escape")


def test_reader_rejects_foreign_audit(tmp_path):
    dest = sidecar_path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps({"contract": "rasai-network-observation-v1", "audit_id": "AUD-OTHER", "observations": []}))
    assert read_network_observations(tmp_path, "AUD-LEGACY") == []


def test_tampered_sidecar_is_rejected(tmp_path):
    from rasai.network_observation import CONTRACT
    import hashlib
    dest = sidecar_path(tmp_path)
    dest.parent.mkdir(parents=True)
    row = {"contract": CONTRACT, "audit_id": "AUD-X", "observation_id": "SN-X",
           "metrics": {"http_status": {"state": "OBSERVED", "value": 200}}}
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    row["sha256"] = hashlib.sha256(canonical).hexdigest()
    row["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
    payload = {"contract": CONTRACT, "audit_id": "AUD-X", "observations": [row]}
    dest.write_text(json.dumps(payload), encoding="utf-8")
    assert len(read_network_observations(tmp_path, "AUD-X")) == 1
    payload["observations"][0]["metrics"]["http_status"]["value"] = 500
    dest.write_text(json.dumps(payload), encoding="utf-8")
    assert read_network_observations(tmp_path, "AUD-X") == []


def test_report_does_not_mutate_sealed_catalog_directory(tmp_path):
    page = materialize_network_report(tmp_path, "AUD-LEGACY")
    assert page.parent.name == "report"
    assert "network" in page.parts
    assert not (tmp_path / "report-catalog").exists()

def test_network_body_is_read_only_on_legacy(tmp_path):
    from rasai.network_reporting import network_report_body
    assert "Dados ainda indisponíveis" in network_report_body(tmp_path, "AUD-LEGACY")
    assert not (tmp_path / "report-catalog").exists()
