"""Standalone preview must not invoke the audit engine or change architecture choice."""
from types import SimpleNamespace
from unittest.mock import patch

from rasai.architecture_discovery import ArchitectureAssessment
from rasai.console_architecture_discovery import architecture_preview_menu
from rasai.domain import ArchitectureClassification


def test_home_preview_uses_existing_target_without_touching_audit(monkeypatch, capsys):
    state = SimpleNamespace(target="https://example.org/", device="mobile")
    console = SimpleNamespace(render_header=lambda _: None,
                              _configure=lambda *_: (_ for _ in ()).throw(AssertionError("unexpected edit")))
    monkeypatch.setenv('RASAI_ARCH_PROBE_EGRESS_GUARDED', '1')
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
    monkeypatch.delenv('RASAI_ARCH_PROBE_EGRESS_GUARDED', raising=False)
    state = SimpleNamespace(target='https://example.org/', device='mobile')
    console = SimpleNamespace(render_header=lambda _: None)
    answers = iter(['1', '', 'V'])
    monkeypatch.setattr('builtins.input', lambda *args: next(answers))
    with patch('rasai.console_architecture_discovery.probe_architecture') as probe:
        architecture_preview_menu(console, state)
        probe.assert_not_called()
    assert 'Nenhuma consulta' in capsys.readouterr().out

def test_architecture_explanation_is_evidence_bounded():
    from rasai.console_architecture_discovery import describe_architecture_assessment
    from rasai.architecture_discovery import assess_architecture
    raw = "<html><main>Visible server content.</main></html>"
    rendered = "<html><main>Visible server content. With hydrated text.</main></html>"
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
