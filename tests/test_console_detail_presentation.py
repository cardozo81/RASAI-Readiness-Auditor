from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO

from rasai import integration_network_diagnostics as network
from rasai.console_detail_presentation import detail_text, install


def test_detail_text_does_not_emit_leading_colon_without_code() -> None:
    assert detail_text("", "o host respondeu") == "o host respondeu"
    assert detail_text(None, ": o host respondeu") == "o host respondeu"
    assert detail_text("TLS_ERROR", "falha de certificado") == "TLS_ERROR: falha de certificado"


def test_network_detail_row_has_only_the_label_separator() -> None:
    install()
    assessment = network.NetworkAssessment(
        integration_id="ai:copilot",
        checked_at="2026-09-14T18:00:00+00:00",
        endpoint="https://api.githubcopilot.com/_ping",
        host="api.githubcopilot.com",
        port=443,
        dns_status="OK",
        tcp_status="OK",
        tls_status="OK",
        http_status=200,
        attempt_count=1,
        latencies_ms=(460,),
        classification=network.NETWORK_PATH_OK,
        error_code="",
        error_detail="o host de runtime do Copilot concluiu DNS/TCP/TLS sem criar sessão nem enviar prompt",
    )
    output = StringIO()
    with redirect_stdout(output):
        network._render_network_assessment(assessment)
    rendered = output.getvalue()
    assert "Detalhe      : o host de runtime" in rendered
    assert "Detalhe      : :" not in rendered
