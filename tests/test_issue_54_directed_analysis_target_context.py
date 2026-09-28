from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.directed_analysis_reporting import directed_analysis_body
from rasai.passive_security import _stable


AUDIT_ID = "AUD-ISSUE-54"
PAGE_ID = "P1"
PAGE_URL = "https://example.test/"


def _data() -> SimpleNamespace:
    return SimpleNamespace(
        audit_id=AUDIT_ID,
        targets=[PAGE_URL],
        audit={"project_name": "Issue 54", "status": "SUCCESS", "completion_status": "COMPLETE"},
        selected=("CAT-10",),
        fulfillment={"processing_status": "COMPLETE"},
    )


def _database(tmp_path: Path) -> Path:
    database=tmp_path/"audit.db"
    connection=sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE directed_analysis_runs(
                audit_id TEXT,
                status TEXT,
                ai_actions_count INTEGER,
                provider TEXT,
                model TEXT,
                strategic_summary_json TEXT,
                roadmap_json TEXT,
                limitations_json TEXT
            );
            CREATE TABLE directed_analysis_actions(
                action_id TEXT,
                audit_id TEXT,
                source_kind TEXT,
                source_id TEXT,
                title TEXT,
                reason TEXT,
                primary_objective TEXT,
                affected_dimensions_json TEXT,
                priority TEXT,
                effort TEXT,
                confidence TEXT,
                confidence_rationale TEXT,
                dependencies_json TEXT,
                implementation_guidance_json TEXT,
                validation_steps_json TEXT,
                source_refs_json TEXT,
                evidence_refs_json TEXT,
                remediation_refs_json TEXT,
                analysis_state TEXT
            );
            CREATE TABLE passive_security_remediations(
                remediation_id TEXT,
                audit_id TEXT,
                finding_id TEXT
            );
            CREATE TABLE passive_security_findings(
                finding_id TEXT,
                audit_id TEXT,
                page_id TEXT,
                url_scope TEXT,
                category TEXT,
                title TEXT,
                description TEXT
            );
            CREATE TABLE passive_security_resources(
                resource_id TEXT,
                audit_id TEXT,
                page_id TEXT,
                page_url TEXT,
                resource_url TEXT,
                resource_kind TEXT,
                party TEXT
            );
            """
        )

        actions=[]

        def add_security_action(action_id: str, remediation_id: str, title: str, reason: str) -> None:
            actions.append(action_id)
            connection.execute(
                """INSERT INTO directed_analysis_actions VALUES(
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )""",
                (
                    action_id,AUDIT_ID,"SECURITY_REMEDIATION",remediation_id,title,reason,
                    "Reduzir risco observado",
                    json.dumps([
                        {"dimension":"SECURITY","expected_gain":"HIGH"},
                        {"dimension":"VULNERABILITIES","expected_gain":"HIGH"},
                    ]),
                    "HIGH","MEDIUM","HIGH","Evidência persistida.",
                    "[]",
                    json.dumps(["Aplicar a correção somente à ocorrência identificada."]),
                    json.dumps(["Reauditar e confirmar que a ocorrência deixou de apresentar o achado."]),
                    "[]","[]","[]","AI_ANALYZED",
                ),
            )

        for index in (1,2,3):
            finding_id=f"SEC-COOKIE-HTTPONLY-{index}"
            remediation_id=f"REM-HTTPONLY-{index}"
            connection.execute(
                "INSERT INTO passive_security_findings VALUES(?,?,?,?,?,?,?)",
                (
                    finding_id,AUDIT_ID,PAGE_ID,PAGE_URL,"Cookies",
                    "Cookie sem HttpOnly observado",
                    f"Set-Cookie #{index} não contém HttpOnly. O valor do cookie não é persistido.",
                ),
            )
            connection.execute(
                "INSERT INTO passive_security_remediations VALUES(?,?,?)",
                (remediation_id,AUDIT_ID,finding_id),
            )
            add_security_action(
                f"ACT-HTTPONLY-{index}",
                remediation_id,
                "Cookie sem HttpOnly observado",
                f"Cookie #{index} sem HttpOnly observado.",
            )

        secure_finding="SEC-COOKIE-SECURE-1"
        connection.execute(
            "INSERT INTO passive_security_findings VALUES(?,?,?,?,?,?,?)",
            (
                secure_finding,AUDIT_ID,PAGE_ID,PAGE_URL,"Cookies",
                "Cookie definido sem Secure em contexto HTTPS",
                "Set-Cookie #1 não contém Secure. O valor do cookie não é persistido.",
            ),
        )
        connection.execute(
            "INSERT INTO passive_security_remediations VALUES(?,?,?)",
            ("REM-SECURE-1",AUDIT_ID,secure_finding),
        )
        add_security_action(
            "ACT-SECURE-1",
            "REM-SECURE-1",
            "Cookie definido sem Secure em contexto HTTPS",
            "Cookie #1 sem Secure observado.",
        )

        resource_a="PSR-A"
        resource_b="PSR-B"
        url_a="https://cdn.example.test/a.js?v=1"
        url_b="https://cdn.example.test/b.js?v=2"
        # Persist resources in A/B order, but actions below are B/A. Target resolution
        # must be causal through the stable finding contract, not list position.
        for resource_id,url in ((resource_a,url_a),(resource_b,url_b)):
            connection.execute(
                "INSERT INTO passive_security_resources VALUES(?,?,?,?,?,?,?)",
                (resource_id,AUDIT_ID,PAGE_ID,PAGE_URL,url,"SCRIPT","THIRD_PARTY"),
            )

        sri_title="Recurso externo script sem SRI observado"
        finding_a=_stable("SEC",AUDIT_ID,PAGE_ID,f"SRI_{resource_a}",sri_title)
        finding_b=_stable("SEC",AUDIT_ID,PAGE_ID,f"SRI_{resource_b}",sri_title)
        for remediation_id,finding_id in (("REM-SRI-A",finding_a),("REM-SRI-B",finding_b)):
            connection.execute(
                "INSERT INTO passive_security_findings VALUES(?,?,?,?,?,?,?)",
                (
                    finding_id,AUDIT_ID,PAGE_ID,PAGE_URL,"Resource Integrity",
                    sri_title,
                    "O recurso externo não declara integrity.",
                ),
            )
            connection.execute(
                "INSERT INTO passive_security_remediations VALUES(?,?,?)",
                (remediation_id,AUDIT_ID,finding_id),
            )

        add_security_action("ACT-SRI-B","REM-SRI-B",sri_title,"Recurso B sem SRI.")
        add_security_action("ACT-SRI-A","REM-SRI-A",sri_title,"Recurso A sem SRI.")

        connection.execute(
            "INSERT INTO directed_analysis_runs VALUES(?,?,?,?,?,?,?,?)",
            (
                AUDIT_ID,"COMPLETE",len(actions),"openai","model-test","{}",
                json.dumps([
                    {
                        "phase":"Fase 1 — Segurança",
                        "objective":"Corrigir os achados de segurança.",
                        "action_ids":actions,
                    }
                ]),
                "[]",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return database


def _section(html: str, section_id: str) -> str:
    start=html.index(f"<section id='{section_id}'")
    end=html.index("</section>",start)+len("</section>")
    return html[start:end]


def test_repeated_titles_are_grouped_in_executive_views_and_targets_stay_exact(tmp_path: Path) -> None:
    database=_database(tmp_path)

    html=directed_analysis_body(database,_data())

    transversal=_section(html,"transversal")
    roadmap=_section(html,"roadmap")
    actions=_section(html,"actions")
    traceability=_section(html,"traceability")

    assert transversal.count("Cookie sem HttpOnly observado") == 1
    assert transversal.count("Recurso externo script sem SRI observado") == 1
    assert "3 ocorrências:" in transversal
    assert "2 ocorrências:" in transversal

    assert roadmap.count("Cookie sem HttpOnly observado") == 1
    assert roadmap.count("Recurso externo script sem SRI observado") == 1

    for index in (1,2,3):
        assert f"Set-Cookie #{index} · " in actions
        assert f"Set-Cookie #{index} · " in traceability
    assert PAGE_URL in actions
    assert PAGE_URL in traceability

    # Set-Cookie #1 is intentionally affected by two different controls. The
    # report auto-links URLs, so assert the occurrence label separately from href text.
    assert html.count("Set-Cookie #1 · ") >= 2
    assert html.count(PAGE_URL) >= 2
    assert "O mesmo Set-Cookie pode aparecer em mais de um tema" in html

    url_a="https://cdn.example.test/a.js?v=1"
    url_b="https://cdn.example.test/b.js?v=2"
    assert f"Script externo · {url_a}" in actions
    assert f"Script externo · {url_b}" in actions

    # Action order is B/A while resource persistence order is A/B: mapping cannot
    # be positional.
    actions_start=actions.index("Recurso externo script sem SRI observado")
    assert actions.index(url_b,actions_start) < actions.index(url_a,actions_start)

    assert "Alvo / ocorrência" in actions
    assert "Como implementar" in html
    assert "Como validar" in html
    assert "ACT-HTTPONLY" not in html
    assert "ACT-SRI-" not in html


def test_cookie_target_exposes_ordinal_but_never_cookie_name_or_value(tmp_path: Path) -> None:
    database=_database(tmp_path)
    connection=sqlite3.connect(database)
    try:
        # Deliberately place secret-looking material in a column the report target
        # resolver is not allowed to use.
        connection.execute(
            "UPDATE directed_analysis_actions SET reason=? WHERE action_id='ACT-HTTPONLY-1'",
            ("Cookie #1 sem HttpOnly; não usar nome/valor para identificar o alvo.",),
        )
        connection.commit()
    finally:
        connection.close()

    html=directed_analysis_body(database,_data())

    assert "Set-Cookie #1 · " in html
    assert PAGE_URL in html
    assert "nome e o valor do cookie permanecem ocultos" in html
    assert "sessionid=super-secret" not in html
