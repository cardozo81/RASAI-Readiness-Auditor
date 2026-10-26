"""Focused no-network contract checks for #659 G1."""
from rasai.network_observation import CONTRACT, _public_ip, _item, snapshots_from_audit


def test_public_ip_rejects_private_and_loopback():
    assert _public_ip("192.168.1.1") is None
    assert _public_ip("127.0.0.1") is None
    assert _public_ip("8.8.8.8") == "8.8.8.8"


def test_unknown_not_automatically_observed():
    assert _item(None, source="NO_DNS_CAPTURE")["state"] == "NOT_OBSERVED"
    assert _item("bad", source="sample", state="COLLECTION_FAILED")["value"] is None


def test_missing_legacy_audit_is_safe(tmp_path):
    assert snapshots_from_audit(tmp_path / "missing.db", "AUD-LEGACY") == []
    assert CONTRACT.endswith("-v1")
