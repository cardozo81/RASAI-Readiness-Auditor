"""#666 GeoIP operations must not depend on system PATH or block an audit."""
from pathlib import Path
from rasai import network_geoip_operations as geo


def test_missing_license_does_not_execute(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    def prohibited(*args, **kwargs):
        raise AssertionError("Updater must not execute")
    monkeypatch.setattr(geo.subprocess, "run", prohibited)
    result = geo.run_authorized_update(tmp_path / "missing.conf", licensed=False)
    assert result["state"] == "NOT_CONFIGURED"
    assert geo.local_databases() == {"city_database": None, "asn_database": None}


def test_rejects_unmanaged_or_missing_updater(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    config = tmp_path / "GeoIP.conf"
    config.write_text("AccountID 123", encoding="utf-8")
    assert geo.run_authorized_update(config, licensed=True)["state"] == "NOT_CONFIGURED"


def test_only_managed_executable_and_database_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    exe = geo.updater_executable()
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    config = tmp_path / "GeoIP.conf"
    config.write_text("dummy", encoding="utf-8")
    seen = []
    def fake(cmd, **kw):
        seen.append((cmd, kw))
        return type("Completed", (), {"returncode": 0})()
    monkeypatch.setattr(geo.subprocess, "run", fake)
    result = geo.run_authorized_update(config, licensed=True, timeout=2)
    assert result["state"] == "UPDATED"
    assert seen[0][0] == [str(exe), "-f", str(config), "-d", str(geo.database_directory())]
    assert seen[0][1]["timeout"] == 2
