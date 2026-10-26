"""Offline, read-only HTML projection of #659 passive network evidence."""
from __future__ import annotations

from html import escape
from pathlib import Path

from rasai.network_observation import snapshots_from_audit
from rasai.network_observation_store import read_network_observations

_PAGE = "network.html"
_LABELS = {
    "connected_public_ip": "Endereço público da conexão observada",
    "http_protocol": "Protocolo HTTP",
    "tls_protocol": "Versão TLS",
    "http_status": "Resposta HTTP",
    "redirect_count": "Redirecionamentos HTTP",
    "dns_resolution": "Resolução DNS",
    "tcp_handshake_ms": "Conexão TCP",
    "tls_handshake_ms": "Negociação TLS",
    "traceroute": "Caminho de rede",
    "asn": "Operador de rede",
    "geoip": "Localização aproximada",
}
_STATE = {
    "OBSERVED": "Observado",
    "NOT_OBSERVED": "Não observado",
    "BLOCKED": "Bloqueado",
    "NOT_APPLICABLE": "Não aplicável",
    "INCONCLUSIVE": "Inconclusivo",
    "COLLECTION_FAILED": "Falha na coleta",
}


def network_report_body(workspace: str | Path, audit_id: str) -> str:
    """Build a deterministic and offline page without writing to the AUD."""
    root = Path(workspace)
    observations = read_network_observations(root, audit_id)
    if not observations and not (root / "artifacts" / "network" / "network-observations.json").exists():
        observations = snapshots_from_audit(root / "audit.db", audit_id)
    blocks = []
    for item in observations[:100]:
        cells = []
        for key, label in _LABELS.items():
            metric = item.get("metrics", {}).get(key, {})
            status = _STATE.get(metric.get("state"), "Inconclusivo")
            value = metric.get("value") if metric.get("state") == "OBSERVED" else None
            shown = str(value) if value is not None else "Sem medição disponível"
            cells.append(
                f"<tr><th scope='row'>{escape(label)}</th>"
                f"<td>{escape(shown)}</td><td>{escape(status)}</td></tr>"
            )
        blocks.append(
            "<section class='panel'><h2>Observação do dispositivo "
            + escape(str(item.get("device") or "não informado"))
            + "</h2><p>Informações extraídas da captura da auditoria, sem novas sondagens.</p>"
            + "<div class='table-wrap'><table><thead><tr><th>Indicador</th><th>Resultado</th><th>Situação</th></tr></thead><tbody>"
            + "".join(cells) + "</tbody></table></div></section>"
        )
    if not blocks:
        blocks.append("<section class='panel'><h2>Dados ainda indisponíveis</h2>"
                      "<p>Esta auditoria não possui observações de rede utilizáveis. "
                      "Não significa que houve falha de conexão.</p></section>")
    html = """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Rede e conectividade — RASAi</title>
<style>body{font:16px/1.55 system-ui,sans-serif;color:#263449;background:#f6f7fb;margin:0}
main{max-width:1050px;margin:auto;padding:2rem 1rem}.panel,header{background:white;border:1px solid #e1e4ea;border-radius:6px;padding:1.3rem;margin-bottom:1rem}
table{width:100%;border-collapse:collapse;text-align:left}td,th{padding:.7rem;border-bottom:1px solid #eceef2}
.table-wrap{overflow:auto}a{color:#254c91}</style></head><body><main>
<p><a href='index.html'>Voltar à visão geral</a></p>
<header><h1>Rede e conectividade</h1><p>Informações observadas na auditoria. Dados ausentes não são interpretados como falhas. A localização física e o caminho completo da rede não podem ser deduzidos a partir de um endereço IP.</p></header>
""" + "".join(blocks) + """<footer><p>Esta página é consultiva, não altera pontuações ou conclusões e funciona sem conexão à internet.</p></footer></main></body></html>"""
    return html


def network_catalog_sections(workspace: str | Path, audit_id: str) -> str:
    """Reusable canonical catalog body, without nested html/head/body tags."""
    page = network_report_body(workspace, audit_id)
    start = page.find("<header><h1>")
    end = page.find("<footer>", start)
    if start < 0 or end < 0:
        raise ValueError("Projeção de rede incompatível")
    return page[start:end]


def materialize_network_report(workspace: str | Path, audit_id: str) -> Path:
    """Standalone extension preview, not the canonical signed catalog."""
    report = Path(workspace) / "artifacts" / "network" / "report"
    report.mkdir(parents=True, exist_ok=True)
    dest = report / _PAGE
    dest.write_text(network_report_body(workspace, audit_id), encoding="utf-8", newline="\n")
    return dest
