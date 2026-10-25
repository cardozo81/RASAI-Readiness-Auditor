"""#358 end-to-end boundaries: INI, guided console and read-only CAT-07 advisory."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from rasai import console_apdex_configuration as ui
from rasai import console_environment
from rasai import console_settings
from rasai.cat07_architecture_reporting import cat07_architecture_advice_html
from rasai.console_m23 import State, validate_env_value
from rasai.m25_cli import UX_ARCHITECTURE_ENV, UX_PROFILE_MODE_ENV


def test_ini_round_trip_and_menu_six_registry_include_nonexecuting_metadata(tmp_path, monkeypatch):
    state = State()
    state.apdex_experience_architecture = "HYDRATED"
    state.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
    path = tmp_path / "console.ini"
    monkeypatch.delenv(UX_ARCHITECTURE_ENV, raising=False)
    monkeypatch.delenv(UX_PROFILE_MODE_ENV, raising=False)
    console_settings.save_console_config(state, path)
    contents = path.read_text(encoding="utf-8")
    assert "architecture = HYDRATED" in contents
    assert "profile_mode = DYNATRACE_GUIDED" in contents
    assert UX_ARCHITECTURE_ENV in contents
    assert UX_PROFILE_MODE_ENV in contents
    restored = State()
    result = console_settings.load_console_config(restored, path)
    assert result.warnings == ()
    assert restored.apdex_experience_architecture == "HYDRATED"
    assert restored.apdex_experience_profile_mode == "DYNATRACE_GUIDED"
    specs = {spec.name: spec for spec in console_environment.environment_specs()}
    assert UX_ARCHITECTURE_ENV in specs and UX_PROFILE_MODE_ENV in specs
    assert not specs[UX_ARCHITECTURE_ENV].sensitive
    assert not specs[UX_PROFILE_MODE_ENV].sensitive


@pytest.mark.parametrize("name,bad", [
    (UX_ARCHITECTURE_ENV, "BAD_ARCH"),
    (UX_PROFILE_MODE_ENV, "VISUALLY_COMPLETE"),
])
def test_menu_six_env_rejects_invalid_architecture_or_mode(name, bad):
    with pytest.raises(ValueError):
        validate_env_value(name, bad)


def _quiet_ui(monkeypatch, *, confirm=True):
    monkeypatch.setattr(ui, "_show_experience_defaults", lambda: None)
    monkeypatch.setattr(ui, "_configure_experience_runtime_profiles", lambda device: None)
    monkeypatch.setattr(ui, "_number", lambda name, current, **kwargs: current)
    monkeypatch.setattr(ui, "_choice", lambda label, current, options, *args: current)
    monkeypatch.setattr(ui, "_required_positive", lambda label, current: current)
    def yn(label, current):
        if "Aplicar os 3 valores" in label:
            return confirm
        return current
    monkeypatch.setattr(ui, "_yes_no", yn)


def test_guided_console_applies_only_three_existing_load_fields_after_confirmation(monkeypatch):
    _quiet_ui(monkeypatch, confirm=True)
    state = State()
    state.apdex_experience = True
    state.apdex_experience_kpm = "DOM_INTERACTIVE"
    state.apdex_experience_satisfied = 5.0
    state.apdex_experience_frustrated = 20.0
    state.apdex_experience_architecture = "CSR_SPA"
    state.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
    before = (state.apdex_experience_samples, state.apdex_experience_max_attempts,
              state.apdex_experience_concurrency, state.device)
    ui._configure_experience(state)
    assert state.apdex_experience_kpm == "USER_ACTION_DURATION"
    assert state.apdex_experience_satisfied == 3.0
    assert state.apdex_experience_frustrated == 12.0
    assert state.apdex_dynatrace_import is False
    assert before == (
        state.apdex_experience_samples, state.apdex_experience_max_attempts,
        state.apdex_experience_concurrency, state.device,
    )


def test_custom_console_never_overwrites_operator_thresholds(monkeypatch):
    _quiet_ui(monkeypatch)
    state = State()
    state.apdex_experience = True
    state.apdex_experience_profile_mode = "CUSTOM"
    state.apdex_experience_architecture = "STATIC_OR_SSR"
    state.apdex_experience_kpm = "DOM_INTERACTIVE"
    state.apdex_experience_satisfied = 5.0
    state.apdex_experience_frustrated = 20.0
    ui._configure_experience(state)
    assert (state.apdex_experience_kpm, state.apdex_experience_satisfied,
            state.apdex_experience_frustrated) == ("DOM_INTERACTIVE", 5.0, 20.0)


def test_rejected_guided_preview_restores_state_and_environment(monkeypatch):
    _quiet_ui(monkeypatch, confirm=False)
    state = State()
    state.synthetic_apdex = True
    state.apdex_experience = True
    state.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
    state.apdex_experience_satisfied = 5.0
    state.apdex_experience_frustrated = 20.0
    monkeypatch.setattr(ui, "_configure_navigation", lambda s: None)
    original = {
        "kpm": state.apdex_experience_kpm,
        "sat": state.apdex_experience_satisfied,
        "fru": state.apdex_experience_frustrated,
        "mode": state.apdex_experience_profile_mode,
    }
    ui.configure_apdex(state)
    assert state.operation == "LOCAL:APDEX_EDIT_CANCELLED"
    assert original == {
        "kpm": state.apdex_experience_kpm, "sat": state.apdex_experience_satisfied,
        "fru": state.apdex_experience_frustrated, "mode": state.apdex_experience_profile_mode,
    }


def _db(path: Path, *, arch="CSR_SPA", cfg=None):
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE pages (page_id TEXT PRIMARY KEY, audit_id TEXT);
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY, page_id TEXT, device TEXT,
                architecture_classification TEXT
            );
            CREATE TABLE synthetic_ux_apdex_runs (
                audit_id TEXT, configuration TEXT
            );
        """)
        con.execute("INSERT INTO pages VALUES ('P-1','AUD-1')")
        con.execute("INSERT INTO pages VALUES ('P-OTHER','AUD-OTHER')")
        con.execute(
            "INSERT INTO page_snapshots VALUES ('SNP-1','P-1','MOBILE',?)", (arch,),
        )
        con.execute(
            "INSERT INTO page_snapshots VALUES ('SNP-OTHER','P-OTHER','DESKTOP','STATIC_OR_SSR')"
        )
        if cfg is not None:
            con.execute(
                "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?)",
                ("AUD-1", json.dumps(cfg)),
            )


def test_cat07_report_shows_actual_m6_and_effective_m25_without_modifying_aud(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
    })
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "SPA com renderização principal no cliente" in html
    assert "Configuração efetiva do Apdex de experiência" in html
    assert "Duração da ação de carregamento inicial" in html
    assert "Identificada pela captura desta auditoria" in html
    assert "Rastreabilidade da arquitetura identificada (contexto observado)" in html
    assert "snapshot <code>SNP-1</code>" in html
    assert "página <code>P-1</code>" in html
    assert "dispositivo <code>MOBILE</code>" in html
    assert "RASAI-CAT07-ARCHITECTURE-GUIDANCE-001" in html
    assert "SYNTHETIC_LOAD_ACTION" in html
    assert "Condição técnica não catalogada" not in html
    assert "3.0" in html and "12.0" in html
    assert "N/D (não congelado nesta AUD)" in html
    assert "Este Apdex mede apenas o carregamento inicial" in html
    assert "SNP-OTHER" not in html
    assert db.read_bytes() == before
    assert cat07_architecture_advice_html(db, "AUD-1") == html


def test_cat07_report_mixed_or_old_evidence_abstains_without_source_leak(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={"kpm": "VISUALLY_COMPLETE"})
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO page_snapshots VALUES ('SNP-2','P-1','MOBILE','STATIC_OR_SSR')"
        )
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "múltiplas capturas" in html
    assert "Não determinada" in html
    assert "Não determinável" in html
    assert "Rastreabilidade da arquitetura identificada:</strong> N/D" in html
    assert "snapshot <code>SNP-1</code>" not in html
    assert "snapshot <code>SNP-2</code>" not in html
    assert "Motivos do diagnóstico:" in html
    assert "arquitetura sem evidência conclusiva" in html
    assert db.read_bytes() == before


def test_cat07_legacy_database_without_snapshot_or_m25_gracefully_reports_nd(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db):
        pass
    original = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-LEGACY")
    assert "N/D" in html and "Sem configuração do Apdex de experiência persistida" in html
    assert "não determinada" in html.casefold()
    assert db.read_bytes() == original


def test_cat07_hash_verified_frozen_console_mode_is_shown_but_not_host_ini(tmp_path):
    from types import SimpleNamespace
    from rasai import catalog_report_page as page
    from rasai.audit_configuration_reuse import configuration_hash

    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
        "measurement_contract": {"version": "UAD-BOUNDARY-001"},
    })
    frozen = {
        "settings": {
            "synthetic_apdex_experience": {
                "architecture": "CSR_SPA",
                "profile_mode": "DYNATRACE_GUIDED",
            }
        },
        "targets": ["https://example.org/seguro"],
    }
    digest = configuration_hash(frozen)
    data = SimpleNamespace(
        audit_id="AUD-1", configuration=frozen,
        config_hash=digest, computed_hash=digest,
    )
    before = db.read_bytes()
    html = page._cat07_methodology_summary_html(db, data)
    assert "DYNATRACE_GUIDED" in html
    assert "SPA com renderização principal no cliente" in html
    assert "Duração da ação de carregamento inicial" in html
    assert "Identificada pela captura desta auditoria" in html
    assert db.read_bytes() == before

    # A current INI/state value is never retroactively inserted into an AUD.
    bad = SimpleNamespace(
        audit_id="AUD-1", configuration=frozen,
        config_hash="tampered", computed_hash=digest,
    )
    legacy_html = page._cat07_methodology_summary_html(db, bad)
    assert "N/D (não congelado nesta AUD)" in legacy_html
    assert "DYNATRACE_GUIDED" not in legacy_html
    assert db.read_bytes() == before


def test_cat07_experience_remains_configurable_with_navigation_disabled(monkeypatch):
    state = State()
    state.synthetic_apdex = False
    state.apdex_experience = False
    steps = []
    def navigation(item):
        item.synthetic_apdex = False
        steps.append("NAVIGATION_DISABLED")
    def experience(item):
        item.apdex_experience = True
        item.apdex_experience_profile_mode = "CUSTOM"
        steps.append("EXPERIENCE_ENABLED")
    monkeypatch.setattr(ui, "_configure_navigation", navigation)
    monkeypatch.setattr(ui, "_configure_experience", experience)
    ui.configure_apdex(state)
    assert steps == ["NAVIGATION_DISABLED", "EXPERIENCE_ENABLED"]
    assert state.synthetic_apdex is False
    assert state.apdex_experience is True
    assert state.error == ""


def test_cat07_guided_readonly_report_shows_approved_future_values_not_applied(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "LOAD_EVENT_END",
        "satisfied_threshold_seconds": 4.0,
        "frustrated_threshold_seconds": 16.0,
    })
    frozen = {"settings": {"synthetic_apdex_experience": {
        "architecture": "STATIC_OR_SSR",
        "profile_mode": "DYNATRACE_GUIDED",
    }}}
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1", frozen_meta=frozen)
    assert "Arquitetura informada antes da AUD" in html
    assert "arquitetura declarada diverge" in html
    assert "Prévia para uma NOVA auditoria (não aplicada)" in html
    assert "Métrica proposta para o Apdex de experiência" in html
    assert "RASAI_APDEX_EXPERIENCE_KPM" not in html
    assert "Limite da faixa satisfatória (segundos)" in html
    assert "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS" not in html
    assert "Limite da faixa frustrada (segundos)" in html
    assert "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS" not in html
    assert "RASAI_EXECUTABLE_DYNATRACE_LOAD_FALLBACK_REFERENCE" not in html
    assert "Sim - requer aceite" in html
    assert "Conclusão do evento de carregamento" in html and "4.0" in html
    assert "Somente Dynatrace externo" not in html or "não executado pelo RASAi" in html
    assert db.read_bytes() == before


def test_cat07_custom_report_never_proposes_guided_override_or_new_aud(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "RESPONSE_END",
        "satisfied_threshold_seconds": 2.0,
        "frustrated_threshold_seconds": 8.0,
    })
    frozen = {"settings": {"synthetic_apdex_experience": {
        "architecture": "CSR_SPA",
        "profile_mode": "CUSTOM",
    }}}
    source = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1", frozen_meta=frozen)
    assert "não gerar um preset substituto em modo Custom/Imported" in html
    assert "Prévia para uma NOVA auditoria" not in html
    assert "Conclusão da resposta HTTP" in html
    assert db.read_bytes() == source


def test_cat07_report_escapes_m6_context_and_keeps_audit_immutable(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
    })
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE page_snapshots SET snapshot_id=? WHERE snapshot_id='SNP-1'",
            ("<img src=x onerror=alert(1)>",),
        )
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "snapshot <code>&lt;img src=x onerror=alert(1)&gt;</code>" in html
    assert "página <code>P-1</code>" in html
    assert "SNP-OTHER" not in html
    assert db.read_bytes() == before
    assert cat07_architecture_advice_html(db, "AUD-1") == html


def test_cat07_report_escapes_untrusted_effective_kpm(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "<img src=x onerror=alert(1)>",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
    })
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "<img" not in html
    assert "&lt;img" in html


def test_guided_proposal_appears_before_concurrency_gate_and_is_non_destructive(
    monkeypatch, capsys,
):
    _quiet_ui(monkeypatch, confirm=False)
    state = State()
    state.apdex_experience = True
    state.apdex_experience_profile_mode = "DYNATRACE_GUIDED"
    state.apdex_experience_architecture = "CSR_SPA"
    state.apdex_experience_kpm = "DOM_INTERACTIVE"
    state.apdex_experience_satisfied = 5.0
    state.apdex_experience_frustrated = 20.0
    with pytest.raises(ui.EditCancelled):
        ui._configure_experience(state)
    text = capsys.readouterr().out
    assert "PRÉVIA GUIADA ANTECIPADA (NÃO APLICADA)" in text
    for field in ("RASAI_APDEX_EXPERIENCE_KPM",
                  "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS",
                  "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS"):
        assert field in text
    assert "origem:" in text and "substitui valor atual: SIM" in text
    assert text.index("PRÉVIA GUIADA ANTECIPADA") < text.index("Prévia de alteração guiada para a PRÓXIMA auditoria")
    assert (state.apdex_experience_kpm, state.apdex_experience_satisfied,
            state.apdex_experience_frustrated) == ("DOM_INTERACTIVE", 5.0, 20.0)


def test_custom_mode_does_not_display_guided_proposal(monkeypatch, capsys):
    _quiet_ui(monkeypatch)
    state = State()
    state.apdex_experience = True
    state.apdex_experience_profile_mode = "CUSTOM"
    state.apdex_experience_architecture = "CSR_SPA"
    ui._configure_experience(state)
    text = capsys.readouterr().out
    assert "Modo selecionado: CUSTOM" in text
    assert "Nenhum preset Guided será apresentado/aplicado" in text
    assert "PRÉVIA GUIADA ANTECIPADA" not in text



def test_real_aud_architecture_known_source_and_metric_do_not_trigger_public_enum_fallback(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
    })
    frozen = {"settings": {"synthetic_apdex_experience": {
        "architecture": "CSR_SPA", "profile_mode": "CUSTOM",
    }}}
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1", frozen_meta=frozen)
    assert "Duração da ação de carregamento inicial" in html
    assert "Identificada pela captura desta auditoria" in html
    assert "Arquitetura observada na captura" in html
    assert "Configuração M25" not in html
    assert "Arquitetura por M6" not in html
    assert "Condição técnica não catalogada" not in html
    assert db.read_bytes() == before


def test_cat07_no_snapshot_does_not_claim_observed_architecture(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, arch="UNKNOWN", cfg={
        "kpm": "DOM_INTERACTIVE",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
    })
    frozen = {"settings": {"synthetic_apdex_experience": {
        "architecture": "HYDRATED", "profile_mode": "CUSTOM",
    }}}
    html = cat07_architecture_advice_html(db, "AUD-1", frozen_meta=frozen)
    assert "Informada pelo operador; sem observação conclusiva" in html
    assert "Tempo até o documento ficar interativo (DOM)" in html
    assert "Identificada pela captura desta auditoria" not in html


def test_cat07_recorded_error_policy_and_context_are_safe_and_do_not_touch_aud(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
        "request_errors_affect_apdex": False,
        "console_errors_affect_apdex": True,
        "xhr_capture": True,
        "error_scope": "first-party",
        "target_samples_per_page": 12,
        "concurrency": 3,
        "settle_seconds": 5.0,
        "dynatrace_base_url": "NEVER_RENDER_TENANT_SECRET",
        "dynatrace_config_json": "NEVER_RENDER_VENDOR_JSON",
    })
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "Políticas de erro e contexto efetivamente persistidos" in html
    assert "Erros de requisição impactam a classificação:</strong> Não" in html
    assert "Erros de console impactam a classificação:</strong> Sim" in html
    assert "Escopo dos erros:</strong> first-party" in html
    assert "Concorrência efetiva:</strong> 3" in html
    assert "Observação pós-load (s; não somada ao Apdex):</strong> 5.0" in html
    assert "Capturar XHR/Fetch não equivale" in html
    assert "NEVER_RENDER_TENANT_SECRET" not in html
    assert "NEVER_RENDER_VENDOR_JSON" not in html
    assert db.read_bytes() == before
    assert cat07_architecture_advice_html(db, "AUD-1") == html


def test_cat07_legacy_policy_does_not_inherit_host_defaults(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, cfg={"kpm": "USER_ACTION_DURATION",
                 "satisfied_threshold_seconds": 3.0,
                 "frustrated_threshold_seconds": 12.0})
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "Escopo dos erros:</strong> N/D" in html
    assert "Concorrência efetiva:</strong> N/D" in html
    assert "Captura de observações XHR:</strong> N/D" in html


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_cat07_abstains_on_unsealed_sqlite_without_opening_aud(
    tmp_path, monkeypatch, suffix,
):
    from rasai import cat07_architecture_reporting as presentation

    db = tmp_path / "audit.db"
    _db(db, cfg={"kpm": "USER_ACTION_DURATION",
                 "satisfied_threshold_seconds": 3.0,
                 "frustrated_threshold_seconds": 12.0})
    before = db.read_bytes()
    sidecar = tmp_path / ("audit.db" + suffix)
    sidecar.write_bytes(b"fake-open-journal")
    monkeypatch.setattr(
        presentation.sqlite3, "connect",
        lambda *args, **kwargs: pytest.fail("must not open an unsealed AUD"),
    )
    html = presentation.cat07_architecture_advice_html(db, "AUD-1")
    assert "data-contract='CAT07-ARCHITECTURE-358'" in html
    assert "N/D" in html
    assert "Fonte SQLite não estável" in html
    assert "3.0" not in html and "CSR_SPA" not in html
    assert db.read_bytes() == before
    assert sidecar.read_bytes() == b"fake-open-journal"


def test_cat07_cannot_attribute_duplicate_foreign_snapshot_id_to_current_aud(
    tmp_path,
):
    db = tmp_path / "audit.db"
    _db(db, cfg={"kpm": "USER_ACTION_DURATION",
                 "satisfied_threshold_seconds": 3.0,
                 "frustrated_threshold_seconds": 12.0})
    with sqlite3.connect(db) as con:
        # Deliberately remove the fixture's PK, modeling an anomalous
        # legacy/corrupt source whose identifiers are not globally unique.
        con.execute("ALTER TABLE page_snapshots RENAME TO _unique_snapshots")
        con.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, device TEXT,"
            "architecture_classification TEXT)"
        )
        con.execute("INSERT INTO page_snapshots SELECT * FROM _unique_snapshots")
        con.execute("DROP TABLE _unique_snapshots")
        con.execute(
            "INSERT INTO page_snapshots VALUES "
            "('SNP-1','P-OTHER','DESKTOP','STATIC_OR_SSR')"
        )
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    assert "Identificador de snapshot repetido" in html
    assert "Rastreabilidade da arquitetura identificada:</strong> N/D" in html
    assert "Identificada pela captura desta auditoria" not in html
    assert "snapshot <code>SNP-1</code>" not in html
    assert db.read_bytes() == before


def test_cat07_rejects_new_sqlite_sidecar_appearing_during_projection(
    tmp_path, monkeypatch,
):
    from rasai import cat07_architecture_reporting as presentation
    db = tmp_path / "audit.db"
    _db(db, cfg={"kpm": "USER_ACTION_DURATION",
                 "satisfied_threshold_seconds": 3.0,
                 "frustrated_threshold_seconds": 12.0})
    original = db.read_bytes()
    real = presentation._run_config
    sidecar = tmp_path / "audit.db-wal"

    def moving_source(con, audit_id):
        observed = real(con, audit_id)
        sidecar.write_bytes(b"new-pending-transaction")
        return observed

    monkeypatch.setattr(presentation, "_run_config", moving_source)
    html = presentation.cat07_architecture_advice_html(db, "AUD-1")
    assert "Fonte SQLite não estável" in html
    assert "snapshot <code>SNP-1</code>" not in html
    assert db.read_bytes() == original
    assert sidecar.read_bytes() == b"new-pending-transaction"


@pytest.mark.parametrize("architecture,expected_review", [
    ("CSR_SPA", "Investigar soft navigation e ações XHR/Fetch"),
    ("HYDRATED", "Investigar soft navigation e ações XHR/Fetch"),
    ("MIXED", "Investigar soft navigation e ações XHR/Fetch"),
    ("STATIC_OR_SSR", "Somente considerar se ações XHR/Fetch"),
])
def test_355_cat07_rum_action_kpm_reference_is_not_tenant_observation(
    tmp_path, architecture, expected_review,
):
    db = tmp_path / "audit.db"
    _db(db, arch=architecture, cfg={
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
    })
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    section = html.split("Referência de KPMs Dynatrace RUM por tipo de ação", 1)[1]
    assert expected_review in section
    assert "Consultar KPMs possíveis por Load, XHR e Custom" in section
    assert "CUMULATIVE_LAYOUT_SHIFT" in section  # Load schema only
    assert "VISUALLY_COMPLETE" in section
    assert "Configuração comprovada" in section
    assert section.count("N/D (tenant não consultado)") == 3
    assert "KPM configurada no tenant: N/D; thresholds e fallback: N/D" in section
    assert "medições sintéticas de Apdex de navegação e experiência permanecem independentes" in section
    assert "a existência da arquitetura não obriga trocar" in section
    assert "Nenhuma configuração efetiva RUM" not in section
    assert db.read_bytes() == before
    assert cat07_architecture_advice_html(db, "AUD-1") == html


def test_355_cat07_without_architecture_proof_does_not_publish_kpm_options(tmp_path):
    db = tmp_path / "audit.db"
    _db(db, arch="UNKNOWN", cfg={"kpm": "DOM_INTERACTIVE"})
    before = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-1")
    section = html.split("Referência de KPMs Dynatrace RUM por tipo de ação", 1)[1]
    assert "Seleção por arquitetura: N/D" in section
    assert "Nenhuma configuração de Load, XHR ou Custom" in section
    assert "Consultar KPMs possíveis" not in section
    assert "CUMULATIVE_LAYOUT_SHIFT" not in section
    assert db.read_bytes() == before


def test_cat07_source_metadata_drift_during_sqlite_projection_abstains(
    tmp_path, monkeypatch,
):
    """A second matching sidecar check cannot certify an altered AUD source."""
    from rasai import cat07_architecture_reporting as presentation
    db = tmp_path / "audit.db"
    _db(db, cfg={"kpm": "USER_ACTION_DURATION",
                 "satisfied_threshold_seconds": 3.0,
                 "frustrated_threshold_seconds": 12.0})
    physical = db.read_bytes()
    original = presentation._source_stamp
    seen = []

    def substituted_stamp(path):
        value = original(path)
        if path == db:
            seen.append(True)
            if len(seen) == 2 and value is not None:
                return (*value[:3], value[3] + 2_000_000_000)
        return value

    monkeypatch.setattr(presentation, "_source_stamp", substituted_stamp)
    html = presentation.cat07_architecture_advice_html(db, "AUD-1")
    assert seen == [True, True]
    assert "Fonte SQLite não estável" in html
    assert "snapshot <code>SNP-1</code>" not in html
    assert "Adequação ao objetivo medido" not in html
    assert db.read_bytes() == physical


def test_cat07_missing_source_does_not_create_sqlite_or_infer_architecture(tmp_path):
    absent = tmp_path / "missing.db"
    html = cat07_architecture_advice_html(absent, "AUD-1")
    assert "Fonte SQLite não estável" in html
    assert "Configuração efetiva:</strong> N/D" in html
    assert not absent.exists()


def test_cat07_directory_symlink_cannot_expose_unrelated_aud_advisory(
    tmp_path, monkeypatch,
):
    from rasai import cat07_architecture_reporting as presentation
    physical = tmp_path / "physical"
    physical.mkdir()
    db = physical / "audit.db"
    _db(db, cfg={"kpm": "USER_ACTION_DURATION",
                 "satisfied_threshold_seconds": 3.0,
                 "frustrated_threshold_seconds": 12.0})
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(physical, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create symlink: {exc}")
    raw = db.read_bytes()
    monkeypatch.setattr(
        presentation.sqlite3, "connect",
        lambda *a, **kw: pytest.fail("must not open a symlinked AUD source"),
    )
    html = presentation.cat07_architecture_advice_html(alias / "audit.db", "AUD-1")
    assert "Fonte SQLite não estável" in html
    assert "snapshot <code>SNP-1</code>" not in html
    assert db.read_bytes() == raw
