"""Five physical M25 Chromium A/B pairs against a loopback SPA (issue #322).

No production sites, provider calls, AUD mutation, score change or network
outside the local HTTP fixture. Results do NOT authorize production rollout.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import threading

from rasai import m25_apdex_experience as m25
from rasai.m25_experimental_probe_runtime import (
    _drain, experimental_gateway_factory, forget_experimental_readiness,
)
from rasai.readiness_matched_pilot import assess_matched_readiness_pilot

AUD = "AUD-LOCAL-READINESS-322"
PAGE = "PGE-LOCAL-READINESS-322"
BODY = " ".join(["Informações e coberturas do conteúdo principal observáveis."] * 16)


class Spa(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/spa":
            self.send_error(404)
            return
        body = (
            "<!doctype html><html lang='pt-BR'><head><title>SPA local</title>"
            "<meta charset='utf-8'></head><body>"
            "<main aria-busy='true'><h1>Carregando</h1>"
            "<div class='skeleton' data-loading='true'>...</div></main>"
            "<script>window.addEventListener('load',()=>{setTimeout(()=>{"
            "const m=document.querySelector('main');"
            "m.removeAttribute('aria-busy');"
            "m.innerHTML='<h1>Conteúdo pronto</h1><p>'+"
            + json.dumps(BODY, ensure_ascii=False)
            + "+'</p>';},850);});</script></body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class NoPacer:
    def wait_for_slot(self):
        pass


def test_five_physical_same_gateway_m25_ab_pairs(monkeypatch):
    # The only replaced method is operational progress logging. M25 navigation,
    # browser contexts, load boundary, same-page callback and model persistence
    # conversion all execute their real production code.
    monkeypatch.setattr(m25, "_log_progress", lambda *args, **kwargs: None)
    forget_experimental_readiness(AUD)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Spa)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/spa"
    browser_path = shutil.which("google-chrome") or shutil.which("chromium")
    # A single Playwright sync driver and one Chromium process for BOTH arms.
    # Simultaneous sync_playwright.start() drivers are not supported in-thread.
    # Cold contexts preserve isolation while alternating observer opt-in.
    gateway = experimental_gateway_factory(
        session_mode="cold", policy=("CSR_SPA", 2200),
    )
    gateway.executable_path = browser_path
    observer = gateway.advisory_same_page_observer
    profile = m25.DESKTOP_STANDARD_PROFILE
    config = m25.ExperienceApdexConfig(
        settle_seconds=0.7, concurrency=1,
    )
    calibration = m25.Calibration(
        source="LOCAL_PHYSICAL_PILOT", kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=2.0, frustrated_threshold_seconds=8.0,
        errors_affect_apdex=True, metadata={},
    )
    measured = []
    try:
        for index in range(5):
            # Alternate arm order to avoid systematic sequential warm-up bias.
            order = ("control", "probe") if index % 2 == 0 else ("probe", "control")
            pair = {}
            for arm in order:
                gateway.advisory_same_page_observer = (
                    observer if arm == "probe" else None
                )
                rows = m25._measure_device(
                    audit_id=AUD, workspace=object(), url=url,
                    device="DESKTOP", target=1, max_attempts=1,
                    page_index=1, page_total=1, calibration=calibration,
                    config=config, pacer=NoPacer(),
                    shared_gateway=gateway, factory=lambda g=gateway: g,
                    profile=profile, page_id=PAGE, start_index=index + 1,
                )
                assert len(rows) == 1
                item = rows[0]
                actual = item.measurement
                assert actual.status == "SUCCESS", (
                    arm, actual.status, actual.error_code,
                )
                assert actual.http_status == 200 and actual.final_url == url
                assert actual.load_event_end_ms is not None
                assert actual.user_action_duration_ms is not None
                # Late SPA materialization must not inflate the existing
                # LOAD_ACTION Apdex measurement.
                assert abs(
                    actual.user_action_duration_ms - actual.load_event_end_ms
                ) <= 50.0
                saved = m25._persisted_sample(
                    AUD, PAGE, url, profile, config, calibration, item,
                )
                assert saved.page_id == PAGE and saved.sample_id
                assert saved.kpm_value_ms == item.kpm_value_ms
                pair[arm] = (item, saved)
                if arm == "probe":
                    observed = gateway.last_advisory_observation
                    assert observed.status == "OBSERVED", (
                        observed.status, getattr(observed, "reason", None),
                    )
                    assert item.experimental_sample_id == saved.sample_id
                    assert observed.sample_id == saved.sample_id
                    assert observed.page_id == saved.page_id
                    assert observed.device == saved.device
                    assert observed.primary_content_ms is not None
                    assert observed.post_load_delta_ms is not None
                    assert observed.post_load_delta_ms >= 0
            measured.append(pair)
        versions = {gateway.environment()["chromium_version"]}
        assert len(versions) == 1
        observed, costs = _drain(AUD)
        assert len(observed) == 5 and len(costs) == 5
        pairs = []
        for row in measured:
            control_item, control_saved = row["control"]
            probe_item, probe_saved = row["probe"]
            cost = costs[probe_saved.sample_id]
            assert cost.identity_proof == "CALLER_DECLARED_NOT_ATTESTED_BY_M25"
            assert cost.source_page_reused is True
            assert cost.number_of_dom_evaluations >= 2
            assert cost.provider_requests == 0 and cost.audit_writes == 0
            pairs.append({
                "page_id": PAGE,
                "device": "DESKTOP",
                "architecture": "CSR_SPA",
                "browser_version": next(iter(versions)),
                "network_profile": profile.network_profile_id,
                "cpu_profile": profile.hardware_profile_id,
                "context_profile": profile.profile_id,
                "navigation_url": url,
                "control": {
                    "sample_id": control_saved.sample_id,
                    "load_duration_ms": control_item.measurement.user_action_duration_ms,
                },
                "probe": {
                    "sample_id": probe_saved.sample_id,
                    "load_duration_ms": probe_item.measurement.user_action_duration_ms,
                    "active_probe_wall_ms": cost.active_probe_wall_ms,
                    "enabled": True,
                    "identity_proof": cost.identity_proof,
                    "source_page_reused": True,
                },
            })
        # 30ms is only the contract's diagnostic EXAMPLE, never an approved SLO.
        report = assess_matched_readiness_pilot(
            pairs, overhead_budget_ms=30.0, min_pairs=5,
        )
        assert report["status"] == "MATCHED_LOCAL_PILOT_ASSESSED"
        assert report["pairs_accepted"] == 5
        assert report["m25_apdex_changed"] is False
        assert report["gateway_identity_attested"] is False
        assert report["m25_production_activation_approved"] is False
        assert report["provider_requests"] == 0 and report["audit_writes"] == 0
        print("RASAI_322_FIVE_REAL_LOCAL_BROWSER_PAIRS=" + json.dumps({
            field: report[field] for field in (
                "status", "pairs_accepted", "measured_wall_delta_median_ms",
                "measured_wall_delta_p90_ms", "max_observed_probe_active_ms",
                "within_declared_overhead_budget",
                "gateway_identity_attested", "m25_production_activation_approved",
                "provider_requests", "audit_writes",
            )
        }, sort_keys=True))
    finally:
        gateway.close()
        forget_experimental_readiness(AUD)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

def test_real_m25_sqlite_persists_exact_same_page_probe_samples(tmp_path, monkeypatch):
    """Physical controlled audit confirms actual M25 SQLite sample linkage.

    Uses two disposable AUDs (A and B), the same real Chromium version and
    loopback SPA. Does not mutate any pre-existing sealed or production AUD.
    """
    from pathlib import Path
    import sqlite3
    from rasai.persistence import AuditWorkspace

    monkeypatch.setattr(m25, "_log_progress", lambda *args, **kwargs: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Spa)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/spa"
    browser_path = shutil.which("google-chrome") or shutil.which("chromium")
    config = m25.ExperienceApdexConfig(
        enabled=True, target_samples_per_page=5, max_attempts_per_page=5,
        max_pages=1, device_mix=(("DESKTOP", 100.0),),
        session_mode="cold", kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=2.0, frustrated_threshold_seconds=8.0,
        settle_seconds=0.7, delay_seconds=0.0, concurrency=1,
    )
    observations = {}
    try:
        for arm in ("control", "probe"):
            audit_id = "AUD-LOCAL-322-" + arm.upper()
            # AuditWorkspace writes only beneath pytest's disposable tmp_path.
            ws = AuditWorkspace.create(tmp_path / arm, audit_id)
            with sqlite3.connect(ws.database) as con:
                con.executescript(
                    "CREATE TABLE audits(audit_id TEXT PRIMARY KEY);"
                    "CREATE TABLE pages(page_id TEXT PRIMARY KEY,"
                    "audit_id TEXT NOT NULL,normalized_url TEXT NOT NULL);"
                    "CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,"
                    "page_id TEXT NOT NULL,device TEXT NOT NULL,final_url TEXT);"
                )
                con.execute("INSERT INTO audits VALUES (?)", (audit_id,))
                con.execute(
                    "INSERT INTO pages VALUES (?,?,?)", (PAGE,audit_id,url),
                )
                con.execute(
                    "INSERT INTO page_snapshots VALUES (?,?,?,?)",
                    ("SNP-LOCAL-322",PAGE,"DESKTOP",url),
                )
            forget_experimental_readiness(audit_id)
            if arm == "probe":
                def factory():
                    # GitHub runner has system Chrome, not the downloaded
                    # Playwright Chromium. Use the same pinned executable
                    # in both physically measured arms.
                    gateway = experimental_gateway_factory(
                        session_mode="cold", policy=("CSR_SPA",2200),
                    )
                    gateway.executable_path = browser_path
                    return gateway
            else:
                factory = lambda: m25.PlaywrightSyntheticUxGateway(
                    session_mode="cold", executable_path=browser_path,
                )
            # Own and close the browser through the *actual* M25 executor;
            # sample rows are committed by M25Persistence, not emulated.
            result = m25.execute_m25_experience(
                audit_id=audit_id, workspace=ws, config=config,
                gateway_factory=factory,
            )
            assert result.valid_samples == 5, (arm,result)
            with sqlite3.connect(ws.database) as con:
                rows = con.execute(
                    "SELECT sample_id,page_id,device,run_index,status,"
                    "user_action_duration_ms,load_event_end_ms,final_url "
                    "FROM synthetic_ux_apdex_samples WHERE audit_id=? "
                    "ORDER BY run_index", (audit_id,),
                ).fetchall()
            assert len(rows) == 5
            assert len({x[0] for x in rows}) == 5
            assert all(
                x[1] == PAGE and x[2] == "DESKTOP"
                and x[4] == "SUCCESS" and x[7] == url
                and x[5] is not None and x[6] is not None
                and abs(x[5]-x[6]) <= 50.0
                for x in rows
            )
            observations[arm] = rows
            if arm == "probe":
                observed, costs = _drain(audit_id)
                assert len(observed) == 5 and len(costs) == 5
                assert {v.sample_id for v in observed} == {x[0] for x in rows}
                assert all(v.status == "OBSERVED" for v in observed)
                assert all(v.primary_content_ms is not None
                           and v.post_load_delta_ms is not None
                           and v.post_load_delta_ms >= 0 for v in observed)
                assert set(costs) == {x[0] for x in rows}
                observations["costs"] = costs
        versions = m25.DESKTOP_STANDARD_PROFILE
        pairs = []
        for control, probe in zip(
            observations["control"], observations["probe"]
        ):
            cost = observations["costs"][probe[0]]
            pairs.append({
                "page_id": PAGE, "device": "DESKTOP",
                "architecture": "CSR_SPA",
                "browser_version": "same-runner-chrome",
                "network_profile": versions.network_profile_id,
                "cpu_profile": versions.hardware_profile_id,
                "context_profile": versions.profile_id,
                "navigation_url": url,
                "control": {
                    "sample_id": control[0], "load_duration_ms": control[5],
                },
                "probe": {
                    "sample_id": probe[0], "load_duration_ms": probe[5],
                    "active_probe_wall_ms": cost.active_probe_wall_ms,
                    "enabled": True,
                    "identity_proof": cost.identity_proof,
                    "source_page_reused": cost.source_page_reused,
                },
            })
        report = assess_matched_readiness_pilot(
            pairs, overhead_budget_ms=30.0, min_pairs=5,
        )
        assert report["status"] == "MATCHED_LOCAL_PILOT_ASSESSED"
        assert report["pairs_accepted"] == 5
        assert report["gateway_identity_attested"] is False
        assert report["m25_production_activation_approved"] is False
        assert report["m25_apdex_changed"] is False
        print("RASAI_322_SQLITE_M25_PHYSICAL_BINDING=" + json.dumps({
            "sqlite_control_samples": len(observations["control"]),
            "sqlite_probe_samples": len(observations["probe"]),
            "same_sample_probe_rows": 5,
            "pair_status": report["status"],
            "gateway_identity_attested": report["gateway_identity_attested"],
            "m25_production_activation_approved":
                report["m25_production_activation_approved"],
            "historical_aud_writes": 0,
            "external_requests": 0,
        }, sort_keys=True))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
        forget_experimental_readiness("AUD-LOCAL-322-CONTROL")
        forget_experimental_readiness("AUD-LOCAL-322-PROBE")
