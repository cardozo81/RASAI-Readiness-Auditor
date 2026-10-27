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



def test_windows_systemroot_survives_nested_worker_environment(monkeypatch, tmp_path):
    """#666 H4: Python uppercases Windows environ keys; don't drop SYSTEMROOT."""
    from rasai import network_active_probe as probe

    monkeypatch.setenv("SYSTEMROOT", r"C:\\Windows")
    monkeypatch.setenv("RASAI_PROVIDER_API_KEY", "must-not-cross-worker-boundary")
    monkeypatch.setenv("HTTPS_PROXY", "must-not-cross-worker-boundary")
    monkeypatch.setenv("RASAI_NETWORK_ACTIVE_HOST", "www.hetzner.com")
    monkeypatch.setattr(auto, "_approved_host", lambda: "www.hetzner.com")
    monkeypatch.setattr(auto, "_sealed_primary_host", lambda *args: "www.hetzner.com")
    monkeypatch.setattr(probe, "_audit_has_target", lambda *args: True)
    monkeypatch.setattr(probe, "probe_path", lambda *_:
                        tmp_path / "not-yet-collected-probe.json")

    dispatched = []
    monkeypatch.setattr(auto.subprocess, "Popen", lambda cmd, **kwargs:
                        dispatched.append((cmd, kwargs)))

    assert auto.dispatch_for_new_audit(tmp_path, "AUD-H4")["state"] == "DISPATCHED"
    assert len(dispatched) == 1
    cmd, options = dispatched[0]
    worker_environment = options["env"]
    assert worker_environment["SYSTEMROOT"] == r"C:\\Windows"
    assert "RASAI_PROVIDER_API_KEY" not in worker_environment
    assert "HTTPS_PROXY" not in worker_environment
    assert "RASAI_NETWORK_ACTIVE_HOST" not in worker_environment
    assert worker_environment["RASAI_NETWORK_MAX_HOPS"].isdigit()
    assert "rasai.network_acceptance" in cmd


def test_windows_systemroot_matching_is_case_insensitive_for_source(monkeypatch, tmp_path):
    """Also cover mixed-case POSIX fixtures; no normalization of actual values."""
    from rasai import network_active_probe as probe

    monkeypatch.setenv("SystemRoot", r"D:\\System")
    monkeypatch.setattr(auto, "_approved_host", lambda: "www.hetzner.com")
    monkeypatch.setattr(auto, "_sealed_primary_host", lambda *args: "www.hetzner.com")
    monkeypatch.setattr(probe, "_audit_has_target", lambda *args: True)
    monkeypatch.setattr(probe, "probe_path", lambda *_:
                        tmp_path / "not-yet-collected-probe.json")
    seen = []
    monkeypatch.setattr(auto.subprocess, "Popen", lambda cmd, **kwargs:
                        seen.append(kwargs["env"]))
    assert auto.dispatch_for_new_audit(tmp_path, "AUD-H4")["state"] == "DISPATCHED"
    assert seen
    assert any(key.upper() == "SYSTEMROOT" and value == r"D:\\System"
               for key, value in seen[0].items())
