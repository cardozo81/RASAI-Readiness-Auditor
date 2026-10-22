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


def test_real_chromium_sqlite_to_sealed_sidecar_and_consultative_report(
    tmp_path, monkeypatch,
):
    """Physical same-page sample through M25 SQLite, real seal, sidecar, report.

    Offline engineering provenance, not external representative-site acceptance.
    """
    import sqlite3
    from rasai.persistence import AuditWorkspace
    from rasai.catalog_report_site import (
        materialize_catalog_report_site, catalog_report_is_fresh,
    )
    from rasai.m25_experimental_probe_runtime import publish_after_seal
    from rasai.apdex_readiness_sidecar import read_readiness_sidecar
    from rasai.apdex_readiness_review import inspect_content_readiness_review
    from rasai.experimental_observation_report import render_experimental_observation_report
    from tests.test_catalog_report_site import _workspace, AUDIT_ID

    prepared, _ = _workspace(tmp_path)
    workspace = AuditWorkspace(prepared.root)
    forget_experimental_readiness(AUDIT_ID)
    monkeypatch.setattr(m25, "_log_progress", lambda *args, **kwargs: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Spa)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/spa"
    try:
        with sqlite3.connect(workspace.database) as db:
            db.executescript(
                "CREATE TABLE pages(page_id TEXT PRIMARY KEY, "
                "audit_id TEXT NOT NULL, normalized_url TEXT NOT NULL, "
                "discovered_url TEXT NOT NULL, discovery_sources TEXT NOT NULL, "
                "depth INTEGER NOT NULL);"
                "CREATE TABLE page_snapshots("
                "snapshot_id TEXT PRIMARY KEY, page_id TEXT NOT NULL, "
                "device TEXT NOT NULL, requested_url TEXT NOT NULL, "
                "final_url TEXT, captured_at TEXT NOT NULL, http_status INTEGER, "
                "content_type TEXT, title TEXT, description TEXT, "
                "canonical TEXT, meta_robots TEXT, rendering_mode TEXT, "
                "raw_artifact_ref TEXT, rendered_artifact_ref TEXT, "
                "main_content_ref TEXT, structured_data_ref TEXT, "
                "browser_metadata TEXT NOT NULL, "
                "architecture_classification TEXT NOT NULL);"
            )
            db.execute(
                "INSERT INTO pages VALUES (?,?,?,?,?,?)",
                (PAGE, AUDIT_ID, url, url, '["DIRECT_INPUT"]', 0),
            )
            db.execute(
                "INSERT INTO page_snapshots("
                "snapshot_id,page_id,device,requested_url,final_url,"
                "captured_at,http_status,content_type,browser_metadata,"
                "architecture_classification) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("SNP-REAL-CONTENT", PAGE, "DESKTOP", url, url,
                 "2026-10-22T12:00:00+00:00", 200, "text/html",
                 "{}", "CSR_SPA"),
            )

        def factory():
            gateway = experimental_gateway_factory(
                session_mode="cold", policy=("CSR_SPA", 2200),
            )
            gateway.executable_path = shutil.which("google-chrome") or shutil.which("chromium")
            return gateway

        config = m25.ExperienceApdexConfig(
            enabled=True, target_samples_per_page=1,
            max_attempts_per_page=1, max_pages=1,
            device_mix=(("DESKTOP", 100.0),), session_mode="cold",
            kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=2.0, frustrated_threshold_seconds=8.0,
            settle_seconds=0.7, delay_seconds=0.0, concurrency=1,
        )
        result = m25.execute_m25_experience(
            audit_id=AUDIT_ID, workspace=workspace, config=config,
            gateway_factory=factory,
        )
        assert result.valid_samples == 1
        with sqlite3.connect(workspace.database) as db:
            row = db.execute(
                "SELECT sample_id,page_id,device,final_url,load_event_end_ms "
                "FROM synthetic_ux_apdex_samples WHERE audit_id=?",
                (AUDIT_ID,),
            ).fetchone()
            assert row is not None and row[1:4] == (PAGE, "DESKTOP", url)
            assert row[4] is not None
            db.execute(
                "UPDATE audits SET status='COMPLETED', completion_status='COMPLETE' "
                "WHERE audit_id=?", (AUDIT_ID,),
            )
        manifest_page = materialize_catalog_report_site(
            audit_id=AUDIT_ID, workspace=workspace,
        )
        assert manifest_page.is_file()
        assert catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace)
        db_before = workspace.database.read_bytes()
        manifest = workspace.root / "report-catalog" / "manifest.json"
        manifest_before = manifest.read_bytes()

        published = publish_after_seal(audit_id=AUDIT_ID, aud_dir=workspace.root)
        assert published == {"eligible": 1, "published": 1, "rejected": 0}
        sidecars = list(
            (workspace.root.parent / ".rasai-readiness-sidecars" / AUDIT_ID).glob("*.json")
        )
        assert len(sidecars) == 1
        verified = read_readiness_sidecar(workspace.root, sidecars[0])
        assert verified["observation"]["sample_id"] == row[0]
        assert verified["observation"]["page_id"] == row[1]
        assert verified["observation"]["device"] == row[2]
        assert verified["observation"]["status"] == "OBSERVED"
        assert verified["probe_cost"]["sample_id"] == row[0]
        review = inspect_content_readiness_review(workspace.root, sidecars[0])
        assert review["status"] == "DOCUMENTARY_SIDECAR_OBSERVED"
        assert review["persisted_sample_link_verified"] is True
        assert review["physical_sample_attested"] is False
        report = render_experimental_observation_report(workspace.root)
        assert report is not None
        text_html = report.read_text(encoding="utf-8")
        assert "CAT-06" in text_html and "CAT-07" in text_html
        assert "Prontidão posterior ao load" in text_html
        assert workspace.database.read_bytes() == db_before
        assert manifest.read_bytes() == manifest_before
        assert publish_after_seal(audit_id=AUDIT_ID, aud_dir=workspace.root) == {
            "eligible": 0, "published": 0, "rejected": 0,
        }
        print("RASAI_POSTSEAL_CHROMIUM_SQLITE=" + json.dumps({
            "status": "SAME_PERSISTED_SAMPLE_SIDECAR_VERIFIED",
            "sample_rows": 1, "sidecars": len(sidecars),
            "source_aud_unchanged": True,
            "independent_browser_provenance_attested": False,
            "external_provider_requests": 0,
        }, sort_keys=True))
    finally:
        forget_experimental_readiness(AUDIT_ID)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
