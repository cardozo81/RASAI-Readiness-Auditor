"""Regressão isolada: campos tipados de CAT-04/05 e diagnóstico Chromium (#109)."""
from rasai.catalog_report_presentation import _table
from rasai.catalog_report_public_labels import public_text
from rasai.catalog_report_search_trust import _serp_geo_label
import json
import sqlite3

from rasai.catalog_report_analysis import _runtime_security_inventory_html
from rasai.passive_security import ensure_schema
from rasai.report_presentation import humanize_report_html


def test_cwv_metric_identifiers_remain_readable_and_assessment_is_localized() -> None:
    html = _table(("Métrica", "Avaliação"), [
        ("LCP", "NEEDS_IMPROVEMENT"),
        ("INP", "POOR"),
        ("CLS", "GOOD"),
    ])
    for label in ("LCP", "INP", "CLS", "Precisa melhorar", "Ruim", "Bom"):
        assert label in html
    assert "Condição técnica não catalogada" not in html


def test_serp_country_and_region_keep_geographical_meaning() -> None:
    assert _serp_geo_label("BR", None) == "Brasil"
    rendered = _serp_geo_label("BR", "Porto Alegre, Rio Grande do Sul, Brazil")
    assert rendered.startswith("Brasil")
    assert "Porto Alegre, Rio Grande do Sul, Brazil" in rendered
    assert _serp_geo_label("ZZ", "Localidade observada") == "Localidade observada"
    assert _serp_geo_label("ZZ", None) == "País (código ISO: ZZ)"
    html = _table(("País/região",), [(rendered,)])
    assert "Condição técnica não catalogada" not in html


def test_chromium_aborted_subresource_is_a_whole_localized_message() -> None:
    line = public_text("Falha: net::ERR_ABORTED")
    assert line == "Falha: Requisição interrompida pelo navegador"
    assert "net::Condição técnica" not in line
    assert "ERR_ABORTED" not in line



def test_final_html_presentation_keeps_cwv_table_identifiers() -> None:
    # The CAT-04 table generator is not the final rendering stage. The earlier
    # regression passed before humanize_report_html destroyed these labels.
    initial = _table(("Métrica", "Avaliação"), [
        ("LCP", "NEEDS_IMPROVEMENT"),
        ("INP", "POOR"),
        ("CLS", "GOOD"),
    ])
    final = humanize_report_html(initial, page_name="cat-04.html")
    for metric in ("LCP", "INP", "CLS"):
        assert f"<td>{metric}</td>" in final
    for assessment in ("Precisa melhorar", "Ruim", "Bom"):
        assert assessment in final
    assert "Condição técnica não catalogada" not in final
    # Unknown enums must still be humanized; do not globally expose raw codes.
    assert "Condição técnica não catalogada" in humanize_report_html("<td>NEW_UNKNOWN_METRIC</td>")
    assert humanize_report_html(final, page_name="cat-04.html") == final



def test_cat10_real_schema_preserves_safe_cookie_identifiers_and_human_creation(tmp_path) -> None:
    db_path = tmp_path / "audit.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript("""
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT);
            INSERT INTO audits VALUES ('AUD-COOKIES-109');
            INSERT INTO pages VALUES ('PG-1','AUD-COOKIES-109');
        """)
        ensure_schema(connection)
        sql = """INSERT INTO passive_security_cookie_attribution(
            cookie_attribution_id,audit_id,page_id,snapshot_id,cookie_ref,
            cookie_name_display,name_hash,creation_mechanism,effective_domain,
            effective_path,host_only,setter_script_url,setter_script_ref,
            platform_ref,party,purpose,purpose_confidence,attribution_confidence,
            details_json,evidence_ids_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        for i,(name,mechanism,purpose) in enumerate([
            ("AWSALB", "HTTP_SET_COOKIE", "NECESSARY"),
            ("JSESSIONID", "DOCUMENT_COOKIE", "ANALYTICS"),
        ], 1):
            connection.execute(sql, (
                f"PCA-{i}", "AUD-COOKIES-109", "PG-1", None, f"CK-COOKIE-{i}",
                name, f"hash-{i}", mechanism, "example.test", "/", 1,
                None, None, None, "FIRST_PARTY", purpose, "HIGH", "MEDIUM",
                json.dumps({"observation_state": "HTTP_SET_COOKIE_OBSERVED" if i == 1
                            else "WRITE_ATTEMPT_NOT_CONFIRMED",
                            "consent_state_at_creation": "NOT_OBSERVED"}), "[]",
            ))
        connection.commit()
    finally:
        connection.close()

    html = humanize_report_html(
        _runtime_security_inventory_html(db_path, "AUD-COOKIES-109"),
        page_name="cat-10.html",
    )
    for cookie in ("AWSALB", "JSESSIONID"):
        assert f"<code class='cookie-name'>{cookie}</code>" in html
    assert "Cabeçalho HTTP Set-Cookie" in html
    assert "JavaScript (document.cookie)" in html
    assert "Necessário para funcionamento" in html
    assert "Análise estatística" in html
    assert "Muito secreto" not in html
    assert "net::Condição técnica não catalogada" not in html


def test_typed_js_signals_survive_both_html_presentation_passes() -> None:
    signals = (
        "DYNAMIC_EVAL", "DYNAMIC_FUNCTION", "DOCUMENT_WRITE",
        "DYNAMIC_SCRIPT_INJECTION", "COOKIE_API", "WEB_STORAGE",
        "WEBSOCKET", "SERVICE_WORKER", "WORKER", "GEOLOCATION",
        "CLIPBOARD", "DYNAMIC_IMPORT", "FINGERPRINTING_SURFACE",
    )
    result = humanize_report_html(
        _table(("Sinal", "Relevância"), [(signal, "INFO") for signal in signals]),
        page_name="cat-04.html",
    )
    assert result.count("Condição técnica não catalogada") == 0
    assert "Execução dinâmica por eval()" in result
    assert "Acesso às APIs de cookies" in result
    assert "Acesso a recursos potencialmente usados" in result
    assert "Condição técnica não catalogada" in humanize_report_html(
        _table(("Sinal",), [("UNRECOGNIZED_JS_SIGNAL_2099",)]),
        page_name="cat-04.html",
    )


def test_final_html_humanizes_whole_chromium_aborted_resource_message() -> None:
    html = humanize_report_html(
        "<div>Falha: net::ERR_ABORTED</div>", page_name="cat-07.html",
    )
    assert html == "<div>Falha: Requisição interrompida pelo navegador</div>"
    assert "net::" not in html
