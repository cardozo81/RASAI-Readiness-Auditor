"""FAQ collector receipt UTC clock provenance guards."""
from datetime import timezone

from rasai.faq_interaction_receipt import _utc


def test_receipt_clocks_require_explicit_utc_offset() -> None:
    assert _utc("2026-10-14T20:00:00Z").tzinfo == timezone.utc
    assert _utc("2026-10-14T20:00:00+00:00").tzinfo == timezone.utc
    assert _utc("2026-10-14T20:00:00-03:00") is None
    assert _utc("2026-10-14T20:00:00") is None
    assert _utc("invalid") is None
