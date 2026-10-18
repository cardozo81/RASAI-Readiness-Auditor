"""Standalone preview must not invoke the audit engine or change architecture choice."""
from types import SimpleNamespace
import pytest
from unittest.mock import patch

from rasai.architecture_discovery import ArchitectureAssessment
from rasai.console_architecture_discovery import architecture_preview_menu
from rasai.domain import ArchitectureClassification
from rasai.architecture_acquisition_preferences import DYNAMIC


@pytest.fixture(autouse=True)
def isolated_dynamic_mode(monkeypatch):
    """Existing console contracts exercise the dynamic backend unless overridden."""
    monkeypatch.setattr("rasai.console_architecture_discovery.read_mode", lambda: DYNAMIC)


def test_home_preview_uses_existing_target_without_touching_audit(monkeypatch, capsys):
    state = SimpleNamespace(target="https://example.org/", device="mobile")
    console = SimpleNamespace(render_header=lambda _: None,
                              _configure=lambda *_: (_ for _ in ()).throw(AssertionError("unexpected edit")))
    monkeypatch.setenv('RASAI_ARCH_PROBE_OFFLINE_CONTAINER', '1')
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    with patch("rasai.console_architecture_discovery.probe_architecture",
               return_value=ArchitectureAssessment(ArchitectureClassification.HYDRATED, None, None)) as probe:
        architecture_preview_menu(console, state)
    assert probe.call_count == 1
    assert state.target == "https://example.org/"
    assert state.device == "mobile"
    assert "HYDRATED" in capsys.readouterr().out


def test_home_preview_cancel_does_not_access_network(monkeypatch):
    state = SimpleNamespace(target="", device="mobile")
    console = SimpleNamespace(render_header=lambda _: None)
    monkeypatch.setattr("builtins.input", lambda *args: "V")
    with patch("rasai.console_architecture_discovery.probe_architecture") as probe:
        architecture_preview_menu(console, state)
        probe.assert_not_called()


def test_home_preview_edit_delegates_to_canonical_console(monkeypatch):
    state = SimpleNamespace(target="https://example.org/", device="mobile")
    choices = []
    console = SimpleNamespace(render_header=lambda _: None,
                              _configure=lambda _state, choice: choices.append(choice))
    answers = iter(["2", "3", "V"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    architecture_preview_menu(console, state)
    assert choices == ["1", "3"]


def test_no_dns_or_probe_without_network_gate(monkeypatch, capsys):
    from rasai.console_architecture_discovery import architecture_preview_menu
    from types import SimpleNamespace
    from unittest.mock import patch
    monkeypatch.delenv('RASAI_ARCH_PROBE_OFFLINE_CONTAINER', raising=False)
    state = SimpleNamespace(target='https://example.org/', device='mobile')
    console = SimpleNamespace(render_header=lambda _: None)
    answers = iter(['1', '', 'V'])
    monkeypatch.setattr('builtins.input', lambda *args: next(answers))
    from rasai.runtime_prerequisites import PrerequisiteResult
    with patch('rasai.runtime_prerequisites.prepare_prerequisite',
               return_value=PrerequisiteResult(False, "DOCKER_INSTALL_REQUIRED")), patch(
        'rasai.console_architecture_discovery.probe_architecture'
    ) as probe:
        architecture_preview_menu(console, state)
        probe.assert_not_called()
    assert 'Nenhuma consulta' in capsys.readouterr().out

def test_architecture_explanation_is_evidence_bounded():
    from rasai.console_architecture_discovery import describe_architecture_assessment
    from rasai.architecture_discovery import assess_architecture
    raw = "<html><body><main><h1>Page</h1><p>Visible server content present.</p></main></body></html>"
    rendered = "<html><body><main><h1>Page</h1><p>Visible server content present. With hydrated text.</p></main></body></html>"
    result = assess_architecture(raw_html=raw, rendered_html=rendered)
    lines = describe_architecture_assessment(result)
    assert any("Conteúdo principal RAW: presente" in line for line in lines)
    assert any("Conteúdo principal renderizado: presente" in line for line in lines)
    assert any("Alterações observadas: main_content" in line for line in lines)
    assert any("uma URL e um dispositivo" in line for line in lines)


def test_inconclusive_architecture_explanation_does_not_claim_evidence():
    from rasai.console_architecture_discovery import describe_architecture_assessment
    from rasai.architecture_discovery import assess_architecture
    result = assess_architecture(raw_html=None, rendered_html=None, quality_reason="SAFE_EGRESS_NOT_CONFIGURED")
    lines = describe_architecture_assessment(result)
    assert any("UNKNOWN" in line for line in lines)
    assert any("indisponível ou rejeitada" in line for line in lines)


def test_preview_without_egress_preserves_existing_audit_database(tmp_path, monkeypatch):
    """Offline preview neither calls collectors nor changes existing AUD bytes."""
    import sqlite3
    from hashlib import sha256

    root = tmp_path / "audits"
    folder = root / "AUD-smoke"
    folder.mkdir(parents=True)
    db = folder / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE checkpoints (name TEXT NOT NULL)")
        con.execute("INSERT INTO checkpoints(name) VALUES (?)", ("original",))
        con.commit()
    original_bytes = db.read_bytes()
    original_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assert original_files == ["AUD-smoke", "AUD-smoke/audit.db"]

    state = SimpleNamespace(target="https://example.org/", device="mobile", audits_root=root)
    console = SimpleNamespace(render_header=lambda _state: None,
                              _configure=lambda *_: (_ for _ in ()).throw(AssertionError("no editor expected")))
    monkeypatch.delenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", raising=False)
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    from rasai.runtime_prerequisites import PrerequisiteResult
    with patch("rasai.runtime_prerequisites.prepare_prerequisite",
               return_value=PrerequisiteResult(False, "DOCKER_INSTALL_REQUIRED")), patch(
        "rasai.console_architecture_discovery.probe_architecture",
        side_effect=AssertionError("offline preview cannot open acquisition")
    ) as probe:
        architecture_preview_menu(console, state)
    probe.assert_not_called()
    assert db.read_bytes() == original_bytes
    assert sha256(db.read_bytes()).digest() == sha256(original_bytes).digest()
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == original_files


def test_offline_oci_rejection_uses_human_facing_reason():
    from rasai.console_architecture_discovery import describe_architecture_assessment
    from rasai.architecture_discovery import assess_architecture
    value = assess_architecture(
        raw_html=None, rendered_html=None, quality_reason="OCI_NETWORK_ISOLATION_NOT_ATTESTED",
    )
    text = "\n".join(describe_architecture_assessment(value))
    assert "Isolamento de rede do contêiner não comprovado" in text
    assert "OCI_NETWORK_ISOLATION_NOT_ATTESTED" not in text


@pytest.mark.parametrize(
    ("device", "rendered_suffix", "expected"),
    [
        ("mobile", "", "STATIC_OR_SSR"),
        ("desktop", "", "STATIC_OR_SSR"),
        ("mobile", " Client-rendered complementary description.", "HYDRATED"),
        ("desktop", " Client-rendered complementary description.", "HYDRATED"),
    ],
)
def test_windows_console_preview_canonical_raw_dom_without_aud_mutation(
    tmp_path, monkeypatch, capsys, device, rendered_suffix, expected,
):
    """Hosted Windows contract: menu 8 consumes canonical classification, no real egress.

    The physical OCI/Linux public-site smoke is independent. This checks the
    actual console menu -> probe -> assessor path using bounded known captures.
    """
    import hashlib
    import sqlite3
    from rasai.architecture_probe import ProbeCaptures
    from rasai.domain import DeviceContext

    audits = tmp_path / "audits"
    audit_folder = audits / "AUD-existing"
    audit_folder.mkdir(parents=True)
    db = audit_folder / "audit.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE audit_marker (value TEXT NOT NULL)")
        conn.execute("INSERT INTO audit_marker VALUES ('original')")
        conn.commit()
    before_bytes = hashlib.sha256(db.read_bytes()).hexdigest()
    before_files = sorted(p.relative_to(audits).as_posix() for p in audits.rglob("*"))

    raw = "<html><body><main>Visible server content.</main></body></html>"
    rendered = (
        "<html><body><main>Visible server content."
        + rendered_suffix
        + "</main></body></html>"
    )
    observed = []
    def captured(url, requested_device):
        observed.append((url, requested_device))
        return ProbeCaptures(url, url, requested_device, raw, rendered)

    state = SimpleNamespace(
        target="https://example.org/", device=device, audits_root=audits,
    )
    console = SimpleNamespace(
        render_header=lambda *_: None,
        _configure=lambda *_: (_ for _ in ()).throw(
            AssertionError("preview must not change configuration")
        ),
    )
    monkeypatch.setenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", "1")
    monkeypatch.setenv("RASAI_ARCH_PROBE_EGRESS_GUARDED", "0")
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    with patch(
        "rasai.console_architecture_discovery.capture_public_architecture",
        side_effect=captured,
    ) as capture, patch(
        "rasai.architecture_probe._validate_public_url",
        side_effect=lambda url, _resolver: url,
    ) as validated, patch(
        "rasai.architecture_probe._default_resolver",
    ) as network_resolver:
        architecture_preview_menu(console, state)

    output = capsys.readouterr().out
    assert f"Arquitetura observada: {expected}" in output
    assert "Conteúdo principal RAW: presente" in output
    assert "Conteúdo principal renderizado: presente" in output
    assert "Versão do método: architecture-observation-v1" in output
    assert "Esta observação não modifica a seleção nem os índices da AUD." in output
    assert observed == [("https://example.org/", DeviceContext(device.upper()))]
    capture.assert_called_once()
    validated.assert_called_once()
    network_resolver.assert_not_called()
    assert state.target == "https://example.org/" and state.device == device
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before_bytes
    assert sorted(p.relative_to(audits).as_posix() for p in audits.rglob("*")) == before_files


def test_windows_preview_rejects_unrendered_live_capture_without_aud_mutation(
    tmp_path, monkeypatch, capsys,
):
    """Real probe/assessor fail closed when the isolated capture declines."""
    import sqlite3
    from rasai.architecture_probe import ProbeCaptures
    from rasai.domain import DeviceContext

    folder = tmp_path / "AUD-original"
    folder.mkdir()
    db = folder / "audit.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE markers (label TEXT NOT NULL)")
        conn.execute("INSERT INTO markers VALUES ('original')")
        conn.commit()
    bytes_before = db.read_bytes()
    state = SimpleNamespace(
        target="https://example.org/", device="mobile", audits_root=tmp_path,
    )
    console = SimpleNamespace(
        render_header=lambda *_: None,
        _configure=lambda *_: (_ for _ in ()).throw(
            AssertionError("preview cannot configure an AUD")
        ),
    )
    monkeypatch.setenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", "1")
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    with patch(
        "rasai.console_architecture_discovery.capture_public_architecture",
        return_value=ProbeCaptures(
            "https://example.org/", "https://example.org/", DeviceContext.MOBILE,
            "<html><main>Visible server content.</main></html>",
            None, "OCI_ASSET_URL_REJECTED",
        ),
    ) as capture, patch("rasai.architecture_probe._default_resolver") as resolver:
        architecture_preview_menu(console, state)

    output = capsys.readouterr().out
    assert "Arquitetura observada: UNKNOWN" in output
    assert "Referência de recurso HTML inválida ou não autorizada" in output
    assert "Evidência: comparação RAW/renderizada indisponível ou rejeitada." in output
    capture.assert_called_once()
    resolver.assert_not_called()
    assert db.read_bytes() == bytes_before
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == [
        "AUD-original", "AUD-original/audit.db",
    ]


def test_menu_auto_prepared_executor_needs_no_flag_and_no_manual_commands(monkeypatch, capsys):
    from rasai.runtime_prerequisites import PrerequisiteResult
    from rasai.architecture_probe import ProbeCaptures
    from rasai.domain import DeviceContext
    state = SimpleNamespace(target="https://example.org/", device="mobile")
    console = SimpleNamespace(render_header=lambda _: None)
    monkeypatch.delenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", raising=False)
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    def captures(url, device):
        return ProbeCaptures(
            url, url, device, "<main>Visible static content</main>",
            "<main>Visible static content</main>",
        )
    with patch("rasai.runtime_prerequisites.prepare_prerequisite",
               return_value=PrerequisiteResult(True, "PREREQUISITE_READY")) as gate, patch(
        "rasai.console_architecture_discovery.probe_architecture",
        return_value=ArchitectureAssessment(ArchitectureClassification.STATIC_OR_SSR, None, None),
    ) as probe:
        architecture_preview_menu(console, state)
    assert gate.call_count == 1
    assert probe.call_count == 1
    assert probe.call_args.kwargs["capture"].__name__ == "capture_isolated_public_architecture"
    assert "STATIC_OR_SSR" in capsys.readouterr().out


def test_menu_refused_preparation_does_not_run_probe(monkeypatch, capsys):
    from rasai.runtime_prerequisites import PrerequisiteResult
    state = SimpleNamespace(target="https://example.org/", device="mobile")
    console = SimpleNamespace(render_header=lambda _: None)
    monkeypatch.delenv("RASAI_ARCH_PROBE_OFFLINE_CONTAINER", raising=False)
    answers = iter(["1", "", "V"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    with patch("rasai.runtime_prerequisites.prepare_prerequisite",
               return_value=PrerequisiteResult(False, "PREREQUISITE_DECLINED")), patch(
        "rasai.console_architecture_discovery.probe_architecture"
    ) as probe:
        architecture_preview_menu(console, state)
    probe.assert_not_called()
    assert "demais catálogos" in capsys.readouterr().out
