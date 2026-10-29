"""#657 opt-in preview-to-new-AUD binding, offline without network or SQLite writes."""
from datetime import datetime, timezone

import pytest

from rasai.architecture_discovery import ArchitectureAssessment
from rasai.architecture_preview_store import (
    REFERENCE_KEY, reference_saved_preview, save_preview, validate_preview_reference,
)
from rasai.architecture_choice_audit_adapter import prepare_audit_choice_configuration
from rasai.architecture_audit_html import _preview_reference_html
from rasai.domain import ArchitectureClassification, DeviceContext


def _preview():
    return ArchitectureAssessment(
        ArchitectureClassification.UNKNOWN, None, "PUBLIC_HTTP_NOT_SUCCESS",
    )


def test_explicit_reference_only_exact_url_device_and_unexpired(tmp_path):
    stamp = datetime(2026, 10, 29, 17, 0, tzinfo=timezone.utc)
    url = "https://example.org/a?token=private"
    saved = save_preview(tmp_path, url, DeviceContext.MOBILE, "STATIC", _preview(), now=stamp)
    args = dict(root=tmp_path, preview_id=saved["preview_id"], url=url,
                device=DeviceContext.MOBILE, now=stamp)
    reference = reference_saved_preview(**args)
    assert reference["status"] == "PRELIMINARY_UNVERIFIED"
    assert reference["record_sha256"] == saved["record_sha256"]
    assert validate_preview_reference(reference) == reference
    assert "token=private" not in repr(reference)
    for changes in ({"url": "https://example.org/other"}, {"device": DeviceContext.DESKTOP},
                    {"now": datetime(2027, 1, 1, tzinfo=timezone.utc)}):
        with pytest.raises(ValueError):
            reference_saved_preview(**(args | changes))


def test_no_implicit_reference_or_architecture_promotion(tmp_path):
    stamp = datetime(2026, 10, 29, tzinfo=timezone.utc)
    url = "https://example.org/"
    saved = save_preview(tmp_path, url, DeviceContext.MOBILE, "STATIC", _preview(), now=stamp)
    effective = {"targets": [url], "settings": {"console": {"device": "mobile"}}}
    untouched = prepare_audit_choice_configuration(effective)
    assert REFERENCE_KEY not in untouched
    reference = reference_saved_preview(tmp_path, preview_id=saved["preview_id"],
                                       url=url, device=DeviceContext.MOBILE, now=stamp)
    frozen = prepare_audit_choice_configuration(effective, preview_reference=reference)
    assert frozen[REFERENCE_KEY] == reference
    assert "architecture_choice" not in frozen
    assert effective == untouched
    with pytest.raises(ValueError):
        prepare_audit_choice_configuration(effective, preview_reference={"id": "forged"})


def test_reference_report_is_only_advisory_and_escaped():
    assert _preview_reference_html({}) == ""
    stamp = "2026-10-29T17:00:00+00:00"
    valid = {
        "contract": "RASAI-ARCH-PREVIEW-657-LINK-v1",
        "preview_id": "pv-" + "a" * 32,
        "created_utc": stamp,
        "device": "MOBILE",
        "status": "PRELIMINARY_UNVERIFIED",
        "scope_sha256": "a" * 64,
        "record_sha256": "b" * 64,
        "preview_architecture": "UNKNOWN",
        "method": "V1",
        "limitation": "PUBLIC_HTTP_NOT_SUCCESS",
    }
    html = _preview_reference_html(valid)
    assert "PRELIMINARY_UNVERIFIED" in html
    assert "não evidência M6" in html
    assert "pode expirar" in html
    assert _preview_reference_html(valid | {"method": "<script>"}) == ""
