"""Automatic network sidecar only after a new exact-host authorized AUD."""
from pathlib import Path

from rasai import network_auto_probe as auto


def test_dispatch_disabled_does_not_spawn(monkeypatch, tmp_path):
    monkeypatch.setattr(auto, "_approved_host", lambda: None)
    monkeypatch.setattr(auto.subprocess, "Popen", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("not authorized")))
    assert auto.dispatch_for_new_audit(tmp_path, "AUD-666")["state"] == "NOT_AUTHORIZED"


def test_dispatch_requires_audit_host_and_uses_canonical_worker(monkeypatch, tmp_path):
    from rasai import network_active_probe as probe
    monkeypatch.setattr(auto, "_approved_host", lambda: "www.hetzner.com")
    monkeypatch.setattr(probe, "_audit_has_target", lambda *args: True)
    monkeypatch.setattr(probe, "probe_path", lambda root, audit, host, port:
                        tmp_path / "absent-probe.json")
    calls = []
    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))
    monkeypatch.setattr(auto.subprocess, "Popen", fake_popen)
    output = auto.dispatch_for_new_audit(tmp_path, "AUD-666")
    assert output["state"] == "DISPATCHED"
    assert len(calls) == 1
    args, options = calls[0]
    assert "rasai.network_acceptance" in args
    assert "--include-traceroute" in args
    assert "--authorize-active-network" in args
    assert args[args.index("--host") + 1] == "www.hetzner.com"
    assert options["stdout"] == auto.subprocess.DEVNULL
    monkeypatch.setattr(probe, "_audit_has_target", lambda *args: False)
    assert auto.dispatch_for_new_audit(tmp_path, "AUD-666")["state"] == "OUT_OF_SCOPE"
    assert len(calls) == 1
