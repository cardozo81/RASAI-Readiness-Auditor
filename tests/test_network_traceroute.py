"""#659 G2: traceroute is bounded and never discloses private intermediaries."""
from types import SimpleNamespace
from rasai import network_traceroute as t
import pytest


def test_parse_trace_redacts_private_and_preserves_partial():
    stdout = ("traceroute to 8.8.8.8, 8 hops max\n"
              "1  192.168.1.1  1.3 ms\n"
              "2  *\n"
              "3  8.8.8.8  11.7 ms\n")
    result = t.parse_trace(stdout, "8.8.8.8")
    assert result["target_reached"] is True
    assert result["hops"][0]["public_ip"] is None
    assert result["hops"][0]["state"] == "PRIVATE_HOP_REDACTED"
    assert result["hops"][1]["state"] == "NO_REPLY"
    assert result["hops"][2]["public_ip"] == "8.8.8.8"


def test_bounded_trace_uses_only_vetted_destination(monkeypatch):
    seen = []
    def fake(cmd, **kw):
        seen.append((cmd, kw))
        return SimpleNamespace(returncode=0, stdout="1  8.8.8.8  4.0 ms\n")
    monkeypatch.setattr(t.subprocess, "run", fake)
    result = t.bounded_trace("8.8.8.8", 443)
    assert result["state"] == "OBSERVED"
    assert seen[0][1]["timeout"] == 8
    assert seen[0][0][-1] == "8.8.8.8"
    with pytest.raises(ValueError):
        t.bounded_trace("192.168.1.2", 443)
