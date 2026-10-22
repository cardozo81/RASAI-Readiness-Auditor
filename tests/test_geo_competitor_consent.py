"""#330 local consent grant/revoke register and pre-DNS/capture gates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from rasai.geo_competitor_consent import (
    check_local_consent, record_local_consent, main,
)
from rasai.geo_competitor_fetch import inspect_consented_public_html
from rasai.search_intelligence.content import PublicWebFetcher
from tests.test_geo_competitor_fetch import _FakeTransport, _client


_HOST = "competitor.example.org"
_ROLE = "COMPETITOR_CANDIDATE"
_PURPOSE = "GEO_COMPETITOR_STATIC_CONTENT_REVIEW"
_OPS = ("GET_ROBOTS_TXT", "GET_STATIC_HTML")


def _expiry():
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _record(path, action, *, role=_ROLE, purpose=None, expires_at=None):
    return record_local_consent(
        path, hostname=_HOST, role=role,
        purpose=purpose or (_PURPOSE if role == _ROLE
                           else "AUD_CUSTOMER_STATIC_CONTENT_REVIEW"),
        action=action, expires_at=expires_at, confirmed=True,
    )


def _inspect(path, transport=None, resolver=None):
    t = transport or _FakeTransport(
        b"User-agent: *\nAllow: /\n",
        html=b"<html><body><main><h1>Seguro de vida</h1>"
             b"<p>seguro de vida e coberturas</p></main></body></html>",
    )
    client = _client(t, resolved=resolver)
    return inspect_consented_public_html(
        "https://" + _HOST + "/seguro", query="seguro de vida",
        role=_ROLE, consented_hostnames=(_HOST,),
        consent_purpose=_PURPOSE, consented_operations=_OPS,
        consent_registry=path, fetcher=client,
    ), t


def test_consent_requires_confirmed_scoped_grant_and_expires(tmp_path):
    path = tmp_path / "consent.json"
    with pytest.raises(ValueError, match="confirmation"):
        record_local_consent(
            path, hostname=_HOST, role=_ROLE, purpose=_PURPOSE,
            action="GRANT", expires_at=_expiry(),
        )
    assert not path.exists()
    grant = _record(path, "GRANT", expires_at=_expiry())
    assert check_local_consent(path, hostname=_HOST, role=_ROLE,
                               purpose=_PURPOSE) == grant
    assert check_local_consent(
        path, hostname=_HOST, role="CUSTOMER",
        purpose="AUD_CUSTOMER_STATIC_CONTENT_REVIEW",
    ) is None
    result, transport = _inspect(path)
    assert result["status"] == "STATIC_HTML_FEATURES_OBSERVED"
    assert result["local_consent_event_sha256"] == grant
    assert result["local_consent_authority_attested"] is False
    assert len(transport.urls) == 2

    revoke = _record(path, "REVOKE")
    assert revoke != grant
    denied, blocked = _inspect(path, resolver=lambda *args:
                               pytest.fail("revoked consent must not perform DNS"))
    assert denied["status"] == "LOCAL_CONSENT_REVOKED_OR_NOT_GRANTED"
    assert denied["provider_requests"] == 0
    assert not blocked.urls
    # An explicit new grant after revocation is distinguishable by digest.
    again = _record(path, "GRANT", expires_at=_expiry())
    assert again not in {grant, revoke}
    assert check_local_consent(path, hostname=_HOST, role=_ROLE,
                               purpose=_PURPOSE) == again


def test_absent_corrupt_expired_and_symlink_registry_deny_before_dns(tmp_path):
    path = tmp_path / "consent.json"
    for bad in ("missing", "corrupt"):
        if bad == "corrupt":
            path.write_text('{"schema":"RASAI-COBS-LOCAL-CONSENT-1",'
                            '"schema":"RASAI-COBS-LOCAL-CONSENT-1","events":[]}')
        result, transport = _inspect(
            path, resolver=lambda *args: pytest.fail("must not call DNS"),
        )
        assert result["status"] == "LOCAL_CONSENT_REGISTRY_UNVERIFIABLE"
        assert not transport.urls
    path.unlink()
    _record(path, "GRANT", expires_at=_expiry())
    payload = json.loads(path.read_text())
    payload["events"][0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(payload))
    result, _ = _inspect(path, resolver=lambda *args:
                         pytest.fail("must not call DNS"))
    assert result["status"] == "LOCAL_CONSENT_REGISTRY_UNVERIFIABLE"
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.symlink_to(outside)
    result, _ = _inspect(path, resolver=lambda *args:
                         pytest.fail("must not call DNS"))
    assert result["status"] == "LOCAL_CONSENT_REGISTRY_UNVERIFIABLE"


def test_revocation_after_robots_stops_html_get(tmp_path):
    path = tmp_path / "consent.json"
    _record(path, "GRANT", expires_at=_expiry())
    real = _FakeTransport(b"User-agent: *\nAllow: /\n")

    def revoke_during_robots(request, *, timeout):
        response = real(request, timeout=timeout)
        if request.full_url.endswith("/robots.txt"):
            _record(path, "REVOKE")
        return response

    result, transport = _inspect(path, transport=revoke_during_robots)
    assert result["status"] == "LOCAL_CONSENT_REVOKED_DURING_ROBOTS"
    assert result["provider_requests"] == 1
    assert real.urls == ["https://" + _HOST + "/robots.txt"]


def test_invalid_hostname_expiry_and_registry_location_are_denied(tmp_path):
    registry = tmp_path / "consent.json"
    for host in ("*.example.com", "example.com/path", "EXAMPLE.COM",
                 "localhost:443", "../anything"):
        with pytest.raises(ValueError):
            record_local_consent(
                registry, hostname=host, role=_ROLE, purpose=_PURPOSE,
                action="GRANT", expires_at=_expiry(), confirmed=True,
            )
    with pytest.raises(ValueError, match="expiry"):
        _record(registry, "GRANT", expires_at="2000-01-01T00:00:00Z")
    audit = tmp_path / "AUD-ISOLATED"
    audit.mkdir()
    with pytest.raises(ValueError, match="outside sealed"):
        _record(audit / "consent.json", "GRANT", expires_at=_expiry())


def test_offline_cli_requires_confirm_then_revokes(tmp_path, capsys):
    path = tmp_path / "consent.json"
    args = ["--registry", str(path), "--host", _HOST,
            "--role", _ROLE, "--purpose", _PURPOSE]
    with pytest.raises(SystemExit) as exc:
        main([*args, "--action", "GRANT", "--expires-at", _expiry()])
    assert exc.value.code == 2
    assert not path.exists()
    assert main([*args, "--action", "GRANT",
                 "--expires-at", _expiry(), "--confirm"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "LOCAL_GRANT_RECORDED"
    assert main([*args, "--action", "REVOKE", "--confirm"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "LOCAL_REVOKE_RECORDED"
