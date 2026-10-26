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
