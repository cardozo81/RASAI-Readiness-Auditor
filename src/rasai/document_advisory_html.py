"""Escaped, script-free companion projection. No new CAT or historical HTML edits."""
from html import escape


def render_advisory(report: dict) -> str:
    from rasai.catalog_report_style import _CSS

    def e(value):
        return escape(str(value) if value is not None else "N/D", quote=True)

    sections = []
    for capture in report["captures"]:
        rows = []
        for occurrence in capture["occurrences"]:
            oid = occurrence["occurrence_id"]
            rows.append(
                f'<tr id="o-{e(oid)}"><td>{e(occurrence["text"])}</td>'
                f'<td>{e(occurrence["href_literal"])}<br>{e(occurrence["resolved_url"])}</td>'
                f'<td>{e(occurrence["context"])}</td><td>{e(occurrence["reference_state"])}<br>'
                f'{e(occurrence["url_policy"])}</td><td>{e(occurrence["applicability"])}</td></tr>'
            )
        sections.append(
            f'<section class="card" id="s-{e(capture["snapshot_id"])}"><h2>{e(capture["page_id"])} · {e(capture["device"])}</h2>'
            f'<p>Snapshot {e(capture["snapshot_id"])} · captura {e(capture["captured_at"])} · {e(capture["surface"])}</p>'
            f'<p>Solicitada: {e(capture["requested_url"])}<br>Final observada: {e(capture["final_url_observed"])}</p>'
            f'<p>Fonte: {e(capture["artifact_ref"])} · SHA-256 {e(capture["source_sha256"])}</p>'
            f'<p>Limitações: {e(", ".join(capture["limitations"]) or "N/D")}</p>'
            '<div class="table-wrap"><table><thead><tr><th>Referência</th><th>Href / URL candidata</th>'
            '<th>Contexto observado</th><th>Aquisição / segurança</th><th>Aplicabilidade</th></tr></thead>'
            f'<tbody>{"".join(rows) or "<tr><td colspan=5>N/D — nenhuma referência identificada na fonte observada.</td></tr>"}</tbody></table></div></section>'
        )
    for doc in report["documents"]:
        sections.append(
            f'<section class="card" id="d-{e(doc["document_id"])}"><h2>Documento candidato</h2>'
            f'<p>Estado: {e(doc["status"])} · limitação: {e(doc["reason"])}</p>'
            f'<p>SHA-256 original: {e(doc["original_sha256"])}<br>SHA-256 derivado: {e(doc["text_sha256"])}</p>'
            f'<p>Tipo verificado: {e(doc["verified_media_type"])} · observado em {e(doc["observed_at"])}</p>'
            f'<p>Origem: {e(doc["acquisition_basis"])} · {e(doc["origin_verification"])}</p>'
            f'<p>Ferramenta: {e(doc["tool"])}</p><p>Bytes preservados em {e(doc["original_ref"])}</p></section>'
        )
    for relation in report["relationships"]:
        quotes = "".join(f'<blockquote><p>{e(s["quote"])}</p><footer>Página {e(s["page"])} · offsets {e(s["start"])}–{e(s["end"])} · SHA-256 {e(s["text_sha256"])}</footer></blockquote>' for s in relation["excerpts"])
        sections.append(
            '<section class="card"><h2>Vínculo consultivo</h2>'
            f'<p><a href="#o-{e(relation["occurrence_id"])}">Referência de origem</a> · '
            f'<a href="#d-{e(relation["document_id"])}">Documento candidato</a></p>'
            f'<p>Produto/modalidade: {e(relation["product_candidate"])} · versão {e(relation["version_observed"])} · vigência {e(relation["effective_observed"])}</p>'
            f'<p>{e(relation["applicability"])} · base {e(relation["basis"])}</p>'
            f'<p>Alegação literal: {e(relation["claim_literal"])}</p>{quotes}'
            '<p>Recomendação editorial: explicitar produto, versão e condições; encaminhar fonte e alegação ao fluxo independente de revisão.</p>'
            '<p>Não validado contra documentação oficial vigente. Não declara conformidade.</p></section>'
        )
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        '<title>RASAi · Documentos e vínculos consultivos</title>'
        f'<style>{_CSS} body{{padding:24px;max-width:1200px;margin:auto}} '
        'td,p,blockquote{overflow-wrap:anywhere} .table-wrap{overflow-x:auto} '
        'a:focus-visible{outline:3px solid var(--blue);outline-offset:3px}</style></head><body><main>'
        '<h1>Documentos e vínculos consultivos</h1>'
        f'<p>AUD {e(report["audit_id"])} · <a href="inventory.json">Inventário e cadeia de proveniência JSON</a></p>'
        '<p>Saída local potencialmente sensível: não publicar. Fontes e relatório histórico preservados.</p>'
        '<p>Referência, hash ou hipótese não autenticam fonte, produto, vigência ou alegação. '
        'N/D significa evidência insuficiente. Sem revisão independente, não há corroboração nem declaração de conformidade.</p>'
        f'<p>IA: {e(report["ai"]["state"])} · chamadas: 0 · coleta ativa desabilitada.</p>'
        + "".join(sections) + '</main></body></html>'
    )
