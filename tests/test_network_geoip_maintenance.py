"""GeoIP maintenance is independent, daily, idempotent and non-blocking."""
from datetime import datetime, timedelta, timezone
import json
from rasai import network_geoip_maintenance as m


def test_daily_skips_without_license_or_before_interval(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "operational_home", lambda: tmp_path)
    when = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    cfg = tmp_path / "GeoIP.conf"
    assert m.run_daily(cfg, licensed=False, now=when)["state"] == "NOT_CONFIGURED"
    state = tmp_path / "data" / "geoip" / "last-check.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"checked_utc": when.isoformat()}), encoding="utf-8")
    monkeypatch.setattr(m, "install_official_updater", lambda **kw:
                        (_ for _ in ()).throw(AssertionError("no install before daily interval")))
    assert m.run_daily(cfg, licensed=True, now=when + timedelta(hours=12))["state"] == "UP_TO_DATE"


def test_failed_update_does_not_mark_successful_daily_check(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "operational_home", lambda: tmp_path)
    monkeypatch.setattr(m, "install_official_updater", lambda **kw:
                        {"state": "READY"})
    monkeypatch.setattr(m, "run_authorized_update", lambda *a, **kw:
                        {"state": "FAILED", "error": "UPDATER_EXECUTION_FAILED"})
    status = m.run_daily(tmp_path / "GeoIP.conf", licensed=True,
                         now=datetime(2026, 10, 27, tzinfo=timezone.utc))
    assert status["state"] == "FAILED"
    assert not (tmp_path / "data" / "geoip" / "last-check.json").exists()
