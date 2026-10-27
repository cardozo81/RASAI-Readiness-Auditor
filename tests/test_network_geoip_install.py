"""Offline acceptance for managed geoipupdate installation."""
import hashlib
import io
import json
import zipfile

from rasai import network_geoip_install as installer


def test_install_requires_explicit_acquisition_authorization(monkeypatch, tmp_path):
    monkeypatch.setattr(installer, "updater_executable", lambda: tmp_path / "geoipupdate.exe")
    monkeypatch.setattr(installer, "_download",
                        lambda *args: (_ for _ in ()).throw(AssertionError("No network")))
    assert installer.install_official_updater(acquisition_authorized=False)["state"] == "NOT_AUTHORIZED"


def test_install_from_verified_official_asset_and_reuse(monkeypatch, tmp_path):
    target = tmp_path / "tools" / "geoipupdate.exe"
    monkeypatch.setattr(installer, "updater_executable", lambda: target)
    monkeypatch.setattr(installer, "_asset_platform", lambda: ("windows", "amd64", "zip"))
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("geoipupdate_8.0.0_windows_amd64/geoipupdate.exe", b"M" * 100001)
    payload = archive_data.getvalue()
    asset_url = ("https://github.com/maxmind/geoipupdate/releases/download/"
                 "v8.0.0/geoipupdate_8.0.0_windows_amd64.zip")
    manifest = {"tag_name": "v8.0.0", "assets": [{
        "name": "geoipupdate_8.0.0_windows_amd64.zip",
        "browser_download_url": asset_url,
        "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}]}
    requests = []
    def fake_download(url, limit):
        requests.append(url)
        return json.dumps(manifest).encode() if url == installer.RELEASE_API else payload
    monkeypatch.setattr(installer, "_download", fake_download)
    assert installer.install_official_updater(acquisition_authorized=True)["state"] == "INSTALLED"
    assert target.read_bytes() == b"M" * 100001
    assert installer.install_official_updater(acquisition_authorized=False)["state"] == "READY"
    assert requests == [installer.RELEASE_API, asset_url]


def test_invalid_release_digest_never_replaces_binary(monkeypatch, tmp_path):
    target = tmp_path / "geoipupdate.exe"
    monkeypatch.setattr(installer, "updater_executable", lambda: target)
    monkeypatch.setattr(installer, "_asset_platform", lambda: ("windows", "amd64", "zip"))
    manifest = {"tag_name": "v8.0.0", "assets": [{
        "name": "geoipupdate_8.0.0_windows_amd64.zip",
        "browser_download_url": "https://github.com/maxmind/geoipupdate/releases/download/v8.0.0/geoipupdate_8.0.0_windows_amd64.zip",
        "digest": "sha256:" + "0" * 64}]}
    monkeypatch.setattr(installer, "_download", lambda url, limit:
                        json.dumps(manifest).encode() if url == installer.RELEASE_API else b"bad")
    assert installer.install_official_updater(acquisition_authorized=True)["state"] == "FAILED"
    assert not target.exists()
