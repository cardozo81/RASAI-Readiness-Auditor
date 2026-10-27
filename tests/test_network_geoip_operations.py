"""#666 GeoIP operations must not depend on system PATH or block an audit."""
from pathlib import Path
from rasai import network_geoip_operations as geo


def test_application_local_database_path_is_cwd_independent(monkeypatch, tmp_path):
    root = tmp_path / "rasai-program"
    root.mkdir()
    monkeypatch.setattr(geo, "application_directory", lambda: root)
    monkeypatch.chdir(tmp_path)
    assert geo.database_directory() == root / "data" / "geoip"
    monkeypatch.chdir(root)
    assert geo.database_directory() == root / "data" / "geoip"


def test_read_only_application_directory_is_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path / "user")
    monkeypatch.setattr(geo, "application_directory", lambda: tmp_path / "app")
    exe = geo.updater_executable()
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    config = tmp_path / "GeoIP.conf"
    config.write_text("placeholder", encoding="utf-8")
    original_mkdir = Path.mkdir

    def readonly(path, *args, **kwargs):
        if path == geo.database_directory():
            raise PermissionError("read-only application directory")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", readonly)
    monkeypatch.setattr(geo.subprocess, "run", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("unexpected update")))
    assert geo.run_authorized_update(config, licensed=True) == {
        "state": "FAILED", "error": "UPDATER_EXECUTION_FAILED"
    }


def test_missing_license_does_not_execute(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    monkeypatch.setattr(geo, "application_directory", lambda: tmp_path)
    def prohibited(*args, **kwargs):
        raise AssertionError("Updater must not execute")
    monkeypatch.setattr(geo.subprocess, "run", prohibited)
    result = geo.run_authorized_update(tmp_path / "missing.conf", licensed=False)
    assert result["state"] == "NOT_CONFIGURED"
    assert geo.local_databases() == {"city_database": None, "asn_database": None}


def test_rejects_unmanaged_or_missing_updater(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    monkeypatch.setattr(geo, "application_directory", lambda: tmp_path)
    config = tmp_path / "GeoIP.conf"
    config.write_text("AccountID 123", encoding="utf-8")
    assert geo.run_authorized_update(config, licensed=True)["state"] == "NOT_CONFIGURED"


def test_only_managed_executable_and_database_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    monkeypatch.setattr(geo, "application_directory", lambda: tmp_path)
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


def test_local_databases_reject_corrupt_or_wrong_type(monkeypatch, tmp_path):
    import types
    monkeypatch.setattr(geo, "operational_home", lambda: tmp_path)
    monkeypatch.setattr(geo, "application_directory", lambda: tmp_path)
    root = geo.database_directory()
    root.mkdir(parents=True)
    (root / "GeoLite2-City.mmdb").write_bytes(b"invalid")
    (root / "GeoLite2-ASN.mmdb").write_bytes(b"invalid")
    class Reader:
        def __init__(self, category):
            self.category = category
        def metadata(self):
            return types.SimpleNamespace(database_type=self.category, build_epoch=1750000000)
        def close(self):
            pass
    fake = types.SimpleNamespace(open_database=lambda filename:
        Reader("GeoLite2-ASN"))
    original_import = geo.importlib.import_module
    monkeypatch.setattr(geo.importlib, "import_module", lambda name:
        fake if name == "maxminddb" else original_import(name))
    found = geo.local_databases()
    assert found["city_database"] is None
    assert found["asn_database"] == str(root / "GeoLite2-ASN.mmdb")
