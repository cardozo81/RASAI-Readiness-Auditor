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
from rasai.cat07_architecture_reporting_358 import cat07_architecture_advice_html
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
    assert "M25 comprovada" in html and "USER_ACTION_DURATION" in html
    assert "3.0" in html and "12.0" in html
    assert "N/D (não congelado nesta AUD)" in html
    assert "M25 mede a navegação inicial" in html
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
    assert db.read_bytes() == before


def test_cat07_legacy_database_without_snapshot_or_m25_gracefully_reports_nd(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db):
        pass
    original = db.read_bytes()
    html = cat07_architecture_advice_html(db, "AUD-LEGACY")
    assert "N/D" in html and "Sem configuração M25 persistida" in html
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
    assert "user action" in html.lower()
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
