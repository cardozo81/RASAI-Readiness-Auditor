"""Win Task Scheduler is opt-in and never stores credentials."""
from pathlib import Path
from rasai import network_geoip_schedule as schedule


def test_scheduler_fail_closed_without_authorization(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule.sys, "platform", "win32")
    monkeypatch.setattr(schedule.subprocess, "run", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("unexpected process")))
    assert schedule.install_daily_windows_task(tmp_path / "GeoIP.conf", licensed=False,
                                                authorized=True)["state"] == "NOT_AUTHORIZED"
    assert schedule.remove_daily_windows_task(authorized=False)["state"] == "NOT_AUTHORIZED"


def test_schedulable_command_contains_no_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule.sys, "platform", "win32")
    monkeypatch.setattr(schedule.sys, "executable", str(tmp_path / "python.exe"))
    (tmp_path / "python.exe").write_bytes(b"exe")
    cfg = tmp_path / "GeoIP.conf"
    cfg.write_text("LicenseKey SECRET", encoding="utf-8")
    calls = []
    def fake(cmd, **kwargs):
        calls.append(cmd)
        return type("Result", (), {"returncode": 0})()
    monkeypatch.setattr(schedule.subprocess, "run", fake)
    assert schedule.install_daily_windows_task(cfg, licensed=True,
                                               authorized=True)["state"] == "SCHEDULED"
    args = " ".join(calls[0])
    assert "SECRET" not in args
    assert "GeoIP.conf" in args
    assert schedule.remove_daily_windows_task(authorized=True)["state"] == "REMOVED"
