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
    assert 0 < seen[0][1]["timeout"] <= t.MAX_TRACE_SECONDS
    assert seen[0][0][-1] == "8.8.8.8"
    with pytest.raises(ValueError):
        t.bounded_trace("192.168.1.2", 443)


def test_hetzner_windows_eight_hops_six_public_and_two_no_reply():
    destination = "2a01:4f8:0:1::7:4"
    stdout = ("Rastreando a rota para " + destination + "\n"
              "  1     1 ms     2 ms     1 ms  2804:d51:21d:ff89::1\n"
              "  2     6 ms     6 ms     6 ms  2804:d50:1:3000::6\n"
              "  3     *        *        *     Esgotado o tempo limite do pedido.\n"
              "  4     *        *        *     Esgotado o tempo limite do pedido.\n"
              "  5    40 ms    41 ms    39 ms  2804:4f7c:200:74:74:1217:0:a\n"
              "  6    60 ms    61 ms    62 ms  2800:6e0:0:1::23:24\n"
              "  7    88 ms    89 ms    87 ms  2800:6e0:0:1::16:1\n"
              "  8   131 ms   132 ms   133 ms  2800:6e0:0:1::1:1\n")
    parsed = t.parse_trace(stdout, destination)
    assert len(parsed["hops"]) == 8
    assert len([h for h in parsed["hops"] if h["state"] == "PUBLIC_HOP"]) == 6
    assert [h["hop"] for h in parsed["hops"] if h["state"] == "NO_REPLY"] == [3, 4]
    assert parsed["target_reached"] is False


def test_timeout_keeps_partial_stdout(monkeypatch):
    import subprocess
    stdout = (" 1  2804:d51:21d:ff89::1  1 ms\n"
              " 2  2804:d50:1:3000::6  5 ms\n"
              " 3  * * *\n").encode("utf-8")
    def fake(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"], output=stdout)
    monkeypatch.setattr(t.subprocess, "run", fake)
    result = t.bounded_trace("2a01:4f8:0:1::7:4", 443)
    assert result["state"] == "OBSERVED"
    assert result["error"] == "TRACE_TIME_BUDGET_EXCEEDED"
    assert result["value"]["partial"] is True
    assert len(result["value"]["hops"]) == 3
    assert result["value"]["target_reached"] is False


def test_windows_samples_and_nonzero_exit_preserve_observation(monkeypatch):
    stdout = (" 1     1 ms     2 ms     3 ms  8.8.4.4\n"
              " 2     *        *        *     Request timed out.\n")
    def fake(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout=stdout)
    monkeypatch.setattr(t.subprocess, "run", fake)
    result = t.bounded_trace("8.8.8.8", 443)
    assert result["state"] == "OBSERVED"
    assert result["error"] == "TRACE_COMMAND_FAILED"
    assert result["value"]["collection_status"] == "NONZERO_EXIT"
    assert result["value"]["hops"][0]["rtt_samples_ms"] == [1.0, 2.0, 3.0]
    assert result["value"]["hops"][0]["rtt_ms"] == 1.0
    assert result["value"]["hops"][1]["state"] == "NO_REPLY"
    assert result["value"]["target_reached"] is False


def test_configurable_hops_respect_ceiling(monkeypatch):
    seen = []
    def fake(cmd, **kwargs):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout="1  8.8.8.8  2 ms\n")
    monkeypatch.setattr(t.subprocess, "run", fake)
    observed = t.bounded_trace("8.8.8.8", 443, max_hops=12)
    assert observed["value"]["max_hops"] == 12
    assert "12" in seen[0]
    for invalid in (0, 17, True, "8"):
        with pytest.raises(ValueError):
            t.bounded_trace("8.8.8.8", 443, max_hops=invalid)
