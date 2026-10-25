"""#657 Fase A, offline. No HTTP, browser, Docker, AUD or paid providers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rasai.architecture_discovery import ArchitectureAssessment
from rasai.architecture_preview_store import (
    CONTRACT, KEEP_DAYS, MAX_RECORDS, list_previews, save_preview,
)
from rasai.architecture_acquisition_preferences import DYNAMIC, STATIC
from rasai.domain import ArchitectureClassification, DeviceContext

URL = "https://www.nytimes.com/"
DEVICE = DeviceContext.MOBILE
STAMP = datetime(2026, 10, 25, 17, 0, tzinfo=timezone.utc)


def _unknown() -> ArchitectureAssessment:
    return ArchitectureAssessment(
        ArchitectureClassification.UNKNOWN, None, "PUBLIC_HTTP_NOT_SUCCESS",
    )


def test_657_inconclusive_docker_403_like_preview_is_opt_in_and_non_authoritative(tmp_path):
    # A failed safe pinned request does not prove the exact HTTP code nor SPA.
    db = tmp_path / "audits" / "AUD-EXISTING" / "audit.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"DO-NOT-MODIFY-SEALED-AUD")
    assert list_previews(tmp_path, url=URL, device=DEVICE, now=STAMP) == ()
    rec = save_preview(tmp_path, URL, DEVICE, DYNAMIC, _unknown(), now=STAMP)
    assert rec["status"] == "PRELIMINARY_UNVERIFIED"
    assert rec["architecture"] == "UNKNOWN"
    assert rec["limitations"] == ["PUBLIC_HTTP_NOT_SUCCESS"]
    assert rec["rendered_observed"] is False and rec["raw_observed"] is False
    assert rec["audit_id"] is None and rec["audit_writes"] == 0
    assert rec["final_public_origin"] is None
    assert rec["final_origin_status"] == "NOT_VERIFIED_FROM_ASSESSMENT"
    assert rec["provider_requests"] == 0
    assert rec["contract"] == CONTRACT
    assert db.read_bytes() == b"DO-NOT-MODIFY-SEALED-AUD"
    stored = tmp_path / ".rasai-runtime" / "architecture" / "previews" / (rec["preview_id"] + ".json")
    assert stored.exists() and stored.stat().st_size <= 4096
    assert list_previews(tmp_path, url=URL, device=DEVICE, now=STAMP) == (rec,)
    assert list_previews(tmp_path, url="https://www.nytimes.com/other", device=DEVICE, now=STAMP) == ()
    assert list_previews(tmp_path, url=URL, device=DeviceContext.DESKTOP, now=STAMP) == ()


def test_657_no_query_cookie_header_credential_path_or_html_in_ledger(tmp_path):
    secret = "SECRET_657_QUERY_9FAB"
    raw = "https://www.nytimes.com/sensitive/path?auth=" + secret
    rec = save_preview(tmp_path, raw, DEVICE, STATIC, _unknown(), now=STAMP)
    stored = (tmp_path / ".rasai-runtime/architecture/previews" / (rec["preview_id"] + ".json")).read_text()
    assert secret not in stored
    assert "sensitive" not in stored
    assert "path" not in stored
    assert "cookie" not in stored.lower()
    assert "content" not in stored.lower()
    assert "https://www.nytimes.com" in stored
    assert list_previews(tmp_path, url=raw, device=DEVICE, now=STAMP)
    assert not list_previews(tmp_path, url="https://www.nytimes.com/sensitive/path", device=DEVICE, now=STAMP)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://10.0.0.12/",
    "https://localhost/",
    "http://[::1]/",
    "https://user:pass@example.org/",
])
def test_657_private_or_credentialed_scope_is_not_persisted(tmp_path, url):
    with pytest.raises(ValueError):
        save_preview(tmp_path, url, DEVICE, STATIC, _unknown(), now=STAMP)
    assert not (tmp_path / ".rasai-runtime").exists()


def test_657_hash_mismatch_and_untrusted_record_never_reuse_or_count_as_verified(tmp_path):
    rec = save_preview(tmp_path, URL, DEVICE, DYNAMIC, _unknown(), now=STAMP)
    location = tmp_path / ".rasai-runtime/architecture/previews" / (rec["preview_id"] + ".json")
    mutated = json.loads(location.read_text())
    mutated["architecture"] = "CSR_SPA"
    location.write_text(json.dumps(mutated))
    assert list_previews(tmp_path, url=URL, device=DEVICE, now=STAMP) == ()


def test_657_bounded_store_and_expiration_apply_without_deleting_unknown_content(tmp_path):
    for i in range(MAX_RECORDS + 2):
        save_preview(
            tmp_path, URL, DEVICE, DYNAMIC, _unknown(),
            now=STAMP + timedelta(seconds=i),
        )
    folder = tmp_path / ".rasai-runtime/architecture/previews"
    assert len(list(folder.glob("pv-*.json"))) == MAX_RECORDS
    assert len(list_previews(tmp_path, url=URL, device=DEVICE,
                             now=STAMP + timedelta(minutes=1))) == MAX_RECORDS
    unknown = folder / "operator_private.json"
    unknown.write_text("DO NOT TOUCH")
    save_preview(
        tmp_path, URL, DEVICE, DYNAMIC, _unknown(),
        now=STAMP + timedelta(days=KEEP_DAYS + 1),
    )
    assert unknown.read_text() == "DO NOT TOUCH"
    assert len(list(folder.glob("pv-*.json"))) == 1


def test_657_preexisting_symlinked_storage_is_rejected_without_writes(tmp_path):
    safe = tmp_path / "external"
    safe.mkdir()
    path = tmp_path / ".rasai-runtime" / "architecture"
    path.mkdir(parents=True)
    try:
        (path / "previews").symlink_to(safe, target_is_directory=True)
    except OSError:
        pytest.skip("symlink unavailable on this environment")
    with pytest.raises(ValueError, match="PREVIEW_STORAGE_SYMLINK"):
        save_preview(tmp_path, URL, DEVICE, DYNAMIC, _unknown(), now=STAMP)
    assert list(safe.iterdir()) == []


def test_657_ui_no_implicit_write_and_explicit_save_after_inconclusive(monkeypatch, capsys):
    from rasai import console_architecture_discovery as ui
    from rasai import architecture_acquisition_service as service
    from rasai import architecture_preview_store as ledger

    monkeypatch.setattr(ui, "read_mode", lambda: DYNAMIC)
    execution = service.DiscoveryExecution(True, DYNAMIC, _unknown(), "PUBLIC_HTTP_NOT_SUCCESS")
    monkeypatch.setattr(service, "run_optional_discovery", Mock(return_value=execution))
    store = Mock(return_value={"preview_id": "pv-verified-opt-in"})
    monkeypatch.setattr(ledger, "save_preview", store)
    state = SimpleNamespace(target=URL, device="mobile")
    console = SimpleNamespace(render_header=lambda _: None)
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ui.architecture_preview_menu(console, state)
    store.assert_not_called()
    printed = capsys.readouterr().out
    assert "UNKNOWN" in printed
    assert "não recebeu resposta 2xx" in printed
    assert "código HTTP específico não está disponível" not in printed.lower() or "não está disponível" in printed
    answers = iter(["1", "", "5", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ui.architecture_preview_menu(console, state)
    store.assert_called_once()
    assert store.call_args.args[1:4] == (URL, DEVICE, DYNAMIC)
    assert "PRELIMINARY_UNVERIFIED" in capsys.readouterr().out


def test_657_ui_saved_previews_use_exact_scope_without_probe(monkeypatch, capsys):
    from rasai import console_architecture_discovery as ui
    from rasai import architecture_preview_store as ledger

    monkeypatch.setattr(ui, "read_mode", lambda: STATIC)
    list_mock = Mock(return_value=({
        "preview_id": "pv-0123456789",
        "created_utc": STAMP.isoformat(),
        "mode": STATIC,
        "architecture": "UNKNOWN",
        "limitations": ["PUBLIC_HTTP_NOT_SUCCESS"],
    },))
    monkeypatch.setattr(ledger, "list_previews", list_mock)
    state = SimpleNamespace(target=URL, device="mobile")
    console = SimpleNamespace(render_header=lambda _: None)
    answers = iter(["6", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ui.architecture_preview_menu(console, state)
    list_mock.assert_called_once()
    assert list_mock.call_args.kwargs == {"url": URL, "device": DEVICE}
    output = capsys.readouterr().out
    assert "pv-0123456789" in output and "PRELIMINARY_UNVERIFIED" in output
