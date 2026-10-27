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


def test_canonical_worker_environment_keeps_systemroot_across_subprocesses(monkeypatch):
    """Physical H4 case: pass SYSTEMROOT to both subprocess layers, no secrets."""
    import json
    import subprocess
    import sys

    monkeypatch.setenv("SYSTEMROOT", r"C:\\Windows")
    monkeypatch.setenv("RASAI_ANTHROPIC_API_KEY", "must-not-propagate")
    monkeypatch.setenv("HTTPS_PROXY", "must-not-propagate")
    environment = auto._authorized_worker_environment()
    assert environment["SYSTEMROOT"] == r"C:\\Windows"
    assert "RASAI_ANTHROPIC_API_KEY" not in environment
    assert "HTTPS_PROXY" not in environment

    # The acceptance subprocess inherits the sanitized env; its child worker
    # inherits that same env unless a second override is explicitly supplied.
    nested_script = (
        "import json,os,subprocess,sys;"
        "grandchild='import json,os; print(json.dumps({k: os.environ.get(k) for k in "
        "(\"SYSTEMROOT\",\"RASAI_ANTHROPIC_API_KEY\",\"HTTPS_PROXY\")}))';"
        "r=subprocess.run([sys.executable,'-c',grandchild],capture_output=True,"
        "text=True,timeout=10,check=True);print(r.stdout)"
    )
    executed = subprocess.run(
        [sys.executable, "-c", nested_script], env=environment,
        capture_output=True, text=True, timeout=20, check=True,
    )
    worker_env = json.loads(executed.stdout.strip())
    assert worker_env == {
        "SYSTEMROOT": r"C:\\Windows",
        "RASAI_ANTHROPIC_API_KEY": None,
        "HTTPS_PROXY": None,
    }



def test_console_report_open_waits_for_authorized_async_map_without_new_probe(monkeypatch, tmp_path):
    """Opening HTML during post-AUD worker must use the final network projection."""
    from types import SimpleNamespace
    from rasai import console_artifacts as artifacts
    from rasai import catalog_report_site as catalog
    from rasai import persistence
    from rasai import network_active_probe as probe

    audit = tmp_path / "AUD-CONSOLE-NETWORK"
    (audit / "report-catalog").mkdir(parents=True)
    (audit / "audit.db").write_bytes(b"sealed-audit-placeholder")
    index = audit / "report-catalog" / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    manifest = audit / "report-catalog" / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    expected_probe = audit / "artifacts" / "network" / "probes" / "known.json"

    monkeypatch.setattr(persistence.AuditWorkspace, "open", staticmethod(
        lambda path: SimpleNamespace(root=path, database=path / "audit.db")))
    monkeypatch.setattr(probe, "read_authorized_probes", lambda *_: [])
    monkeypatch.setattr(probe, "probe_path", lambda *_: expected_probe)
    monkeypatch.setattr(auto, "_approved_host", lambda: "www.hetzner.com")
    monkeypatch.setattr(auto, "_sealed_primary_host", lambda *_: "www.hetzner.com")

    progressed = [0.0]
    ready = [False]
    monkeypatch.setattr(artifacts.time, "time", lambda: manifest.stat().st_mtime)
    monkeypatch.setattr(artifacts.time, "monotonic", lambda: progressed[0])
    monkeypatch.setattr(catalog, "catalog_report_is_fresh", lambda **_: ready[0])

    def finish_worker(_delay):
        expected_probe.parent.mkdir(parents=True, exist_ok=True)
        expected_probe.write_text("worker-owns-immutable-packet", encoding="utf-8")
        ready[0] = True
        progressed[0] += 0.5

    monkeypatch.setattr(artifacts.time, "sleep", finish_worker)

    assert artifacts._synchronize_network_report_before_open(index) == "READY"
    assert ready[0]
    assert expected_probe.is_file()


def test_console_report_open_reprojects_only_sealed_probe_without_sockets(monkeypatch, tmp_path):
    """Old stale catalog: use canonical read-only materializer, never re-probe."""
    from types import SimpleNamespace
    from rasai import console_artifacts as artifacts
    from rasai import catalog_report_site as catalog
    from rasai import persistence, report_completion
    from rasai import network_active_probe as probe

    audit = tmp_path / "AUD-HISTORICAL-NETWORK"
    (audit / "report-catalog").mkdir(parents=True)
    (audit / "audit.db").write_bytes(b"sealed-audit-placeholder")
    index = audit / "report-catalog" / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    manifest = audit / "report-catalog" / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(persistence.AuditWorkspace, "open", staticmethod(
        lambda path: SimpleNamespace(root=path, database=path / "audit.db")))
    monkeypatch.setattr(probe, "read_authorized_probes", lambda *_: [{"state": "OBSERVED"}])
    monkeypatch.setattr(artifacts.time, "time", lambda: manifest.stat().st_mtime + 300)
    fresh = [False]
    monkeypatch.setattr(catalog, "catalog_report_is_fresh", lambda **_: fresh[0])
    called = []

    def project(*, audit_id, workspace, read_only):
        called.append((audit_id, read_only))
        fresh[0] = True
        return SimpleNamespace(renderer_errors=())

    monkeypatch.setattr(report_completion, "materialize_catalog_report_projection", project)
    assert artifacts._synchronize_network_report_before_open(index) == "READY"
    assert called == [("AUD-HISTORICAL-NETWORK", True)]


def test_console_report_open_preserves_other_pages_and_no_unsolicited_probe(tmp_path):
    """Non-report artifacts do not run network resolution or collection."""
    from rasai import console_artifacts as artifacts

    general = tmp_path / "report" / "index.html"
    general.parent.mkdir(parents=True)
    general.write_text("<html></html>", encoding="utf-8")
    assert artifacts._synchronize_network_report_before_open(general) == "NOT_APPLICABLE"
