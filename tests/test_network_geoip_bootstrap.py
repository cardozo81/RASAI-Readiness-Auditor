"""Consent-gated bootstrap is nonblocking and never acquires tools by default."""
from rasai import network_geoip_bootstrap as bootstrap


def test_default_bootstrap_does_not_download(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RASAI_GEOIP_ACQUIRE_TOOLS", raising=False)
    monkeypatch.setattr(bootstrap, "install_official_updater", lambda **kw:
                        (_ for _ in ()).throw(AssertionError("download not authorized")))
    assert bootstrap.prepare()["state"] == "NOT_AUTHORIZED"


def test_invalid_persisted_or_override_consent_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RASAI_GEOIP_ACQUIRE_TOOLS", "yes")
    assert bootstrap.acquisition_authorized() is False
    monkeypatch.setenv("RASAI_GEOIP_ACQUIRE_TOOLS", "true")
    seen = []
    monkeypatch.setattr(bootstrap, "install_official_updater", lambda **kw:
                        seen.append(kw) or {"state": "READY"})
    assert bootstrap.prepare()["state"] == "READY"
    assert seen == [{"acquisition_authorized": True}]
