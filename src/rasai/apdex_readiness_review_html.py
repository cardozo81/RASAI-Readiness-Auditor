"""Accessible no-write HTML companion for documentary content readiness."""
from __future__ import annotations
from html import escape
from typing import Any, Mapping

from rasai.apdex_readiness_review import CONTRACT

_STATUS = {
    "OBSERVED": "Materialidade informada pelo produtor",
    "TIMEOUT": "Janela excedida sem comprovação de conteúdo",
    "NOT_OBSERVED": "Conteúdo não observado na amostra informada",
    "NOT_APPLICABLE": "Verificação não aplicável ou não habilitada",
    "ERROR": "Observação incompleta ou inválida",
}
_ARCH = {
    "CSR_SPA": "SPA (renderização cliente)",
    "HYDRATED": "Hidratação",
    "MIXED": "Mista",
    "STATIC_OR_SSR": "Estática ou servidor",
    "UNKNOWN": "Arquitetura não determinada",
}


def _e(value: object) -> str:
    return escape(str(value) if value is not None else "N/D", quote=True)


def _ms(value: object) -> str:
    if type(value) in (float, int) and 0 <= value <= 172_800_000:
        return _e(f"{value:g} ms")
    return "N/D"


def content_readiness_review_html(view: Mapping[str, Any]) -> str:
    """Render a separate, fully bounded document without redefining Apdex."""
    valid = (
        isinstance(view, Mapping)
        and view.get("contract") == CONTRACT
        and view.get("status") == "DOCUMENTARY_SIDECAR_OBSERVED"
        and isinstance(view.get("observation"), dict)
        and view.get("physical_sample_attested") is False
        and view.get("apdex_recalculated") is False
    )
    obs = view["observation"] if valid else {}
    if valid and obs.get("status") not in _STATUS:
        valid = False
    cells = ""
    if valid:
        for label, value in (
            ("Alegação do registro", _STATUS[obs["status"]]),
            ("Amostra declarada", obs.get("sample_id")),
            ("Contexto declarado", obs.get("context_id")),
            ("Página declarada", obs.get("page_id")),
            ("Dispositivo", obs.get("device")),
            ("Arquitetura", _ARCH.get(obs.get("architecture"), "N/D")),
            ("Versão metodológica", obs.get("method_version")),
            ("Fronteira de carregamento informada", _ms(obs.get("load_ms"))),
            ("Conteúdo principal informado", _ms(obs.get("primary_content_ms"))),
            ("Delta pós-carregamento informado", _ms(obs.get("post_load_delta_ms"))),
            ("Janela de observação", _ms(obs.get("observation_window_ms"))),
            ("Critério ou censura", obs.get("reason")),
        ):
            cells += "<tr><th>" + _e(label) + "</th><td>" + _e(value) + "</td></tr>"
    message = (
        "<table><caption>Registro consultivo do produtor</caption><tbody>"
        + cells + "</tbody></table>"
        if valid else "<p>N/D: sidecar ou vínculo físico com a AUD não verificável.</p>"
    )
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Prontidão de conteúdo - registro consultivo</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:980px;"
        "margin:auto;padding:24px;color:#203147}table{border-collapse:collapse;"
        "width:100%}th,td{border-bottom:1px solid #dbe4ee;text-align:left;"
        "vertical-align:top;padding:10px;overflow-wrap:anywhere}"
        "th{width:43%}</style></head><body>"
        "<h1>Registro experimental de prontidão de conteúdo</h1>"
        "<p>Identidade AUD local: <code>"
        + _e(view.get("audit_id") if valid else "N/D")
        + "</code>. Este documento não pertence ao relatório CONS/CAT "
        "e não modifica o Apdex homologado.</p>"
        + message
        + "<p><strong>Limite da prova:</strong> o SHA-256 do sidecar e os "
        "hashes do banco e do manifesto atestam consistência de bytes locais, "
        "não a origem real da medição Playwright. As marcas monotônicas "
        "são declarações externas do produtor, não medidas reconstruídas "
        "dos eventos ou amostras M23/M25. Sem vínculo de mesma amostra "
        "autenticado, nenhuma diferença de desempenho, classificação "
        "SATISFIED/TOLERATING/FRUSTRATED ou readiness de conteúdo é "
        "inferida do índice. Valores N/D e TIMEOUT não são zero nem falha "
        "universal da aplicação.</p></body></html>"
    )


__all__ = ["content_readiness_review_html"]
