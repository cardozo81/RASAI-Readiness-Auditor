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
    monkeypatch.setattr(auto, "_sealed_primary_host", lambda *args: "www.hetzner.com")
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
    monkeypatch.setattr(auto, "_sealed_primary_host", lambda *args: "loja.bradescoseguros.com.br")
    assert auto.dispatch_for_new_audit(tmp_path, "AUD-666")["state"] == "OUT_OF_SCOPE"
    assert len(calls) == 1
    monkeypatch.setattr(auto, "_sealed_primary_host", lambda *args: "www.hetzner.com")
    monkeypatch.setattr(probe, "_audit_has_target", lambda *args: False)
    assert auto.dispatch_for_new_audit(tmp_path, "AUD-666")["state"] == "OUT_OF_SCOPE"
    assert len(calls) == 1


def test_primary_host_requires_aud_sealed_console_target(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from rasai.audit_configuration_reuse import KIND_CONSOLE
    from rasai import audit_configuration_reuse as reuse

    assert auto._sealed_primary_host(tmp_path, "AUD-666") is None

    def matching(root, audit_id, *, expected_kind):
        assert expected_kind == KIND_CONSOLE
        assert root == tmp_path.parent
        assert audit_id == "AUD-666"
        return SimpleNamespace(configuration={
            "targets": ["https://www.hetzner.com/redirect?query=1"]
        })

    monkeypatch.setattr(reuse, "load_reusable_audit_configuration", matching)
    assert auto._sealed_primary_host(tmp_path, "AUD-666") == "www.hetzner.com"
    monkeypatch.setattr(
        reuse, "load_reusable_audit_configuration",
        lambda *args, **kwargs: SimpleNamespace(
            configuration={"targets": ["https://www.hetzner.com/", "https://other.example.org/"]}
        ),
    )
    assert auto._sealed_primary_host(tmp_path, "AUD-666") is None
