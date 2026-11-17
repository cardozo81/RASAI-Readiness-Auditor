"""Offline HTML rendering; consumes only the intermediate model."""
from html import escape
import json
from hashlib import sha256
from .governance import Governance
from .components import kv
from .coverage import display, state
from .read_model import PAGES, destination, thaw, SEARCH_PAGE
from .templates import label as public_label
from .presentation_labels import public_value, timezone_for_records, metric_label, presentation_timestamps
from .annex_payloads import register_payload, table_annex_filename


def esc(value):
    return escape(display(value), quote=True)


def payload(value):
    annex = register_payload(value)
    if annex:
        filename, digest = annex
        return ('<p><a class="tech-link" href="anexos/' + esc(filename) +
                '">Abrir JSON sanitizado · SHA-256 ' + esc(digest) + '</a></p>')
    return '<pre>' + esc(json.dumps(value, ensure_ascii=False, indent=2, default=str)) + '</pre>'


def shell(page, title, body, audit_id=None):
    import re
    headings = []
    def heading(match):
        anchor = 'section-' + str(len(headings))
        headings.append((anchor, match.group(1)))
        return f'<h2 id="{anchor}">{match.group(1)}</h2>'
    body = re.sub(r'<h2>(.*?)</h2>', heading, body)
    nav = ''.join(f'<a href="{name}.html"' + (' aria-current="page"' if name == page else '') + f'>{esc(label)}</a>' for name, label in PAGES)
    rail = ''.join(f'<a href="#{anchor}">{label}</a>' for anchor, label in headings)
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>{esc(title)} · RASAi</title><link rel="stylesheet" href="assets/site.css"><script defer src="assets/app.js"></script></head>
<body><a class="skip" href="#main">Pular para o conteúdo</a><aside><div class="brand">RASAi<small>Relatório de análise</small></div><nav aria-label="Páginas">{nav}</nav><div class="aud">{esc(audit_id)}</div></aside>
<main id="main" tabindex="-1"><div class="top"><span>Auditoria · {esc(title)}</span><span class="sp"></span><button id="expand">Expandir detalhes</button><button id="theme">Alternar tema</button></div>
<div class="shell"><article><h1>{esc(title)}</h1><p class="lead">Análise dos fatos persistidos, com evidências, escopos e limitações. Sem nova coleta ou recálculo de score.</p>{body}<footer>Projeção derivada offline. Ausência não é zero. Sugestões de IA dependem de revisão humana.</footer></article><div class="rail"><b>Nesta página</b>{rail}</div></div></main></body></html>'''


def _record_link_name(href, lookup):
    target = lookup.get(href)
    if target is None:
        return 'Detalhe: referência ' + href
    data = thaw(target.data)
    name = next((str(data[key]) for key in
                 ('title', 'label', 'rule_id', 'metric_id', 'dimension', 'name', 'action_id')
                 if data.get(key) not in (None, '')), target.table)
    dimension = str(data.get('dimension') or data.get('device') or '')
    return 'Detalhe: ' + target.table + ' · ' + name + (
        ' · ' + dimension if dimension else '') + ' · ' + target.anchor


def _redact_nonpublic_platform_identifiers(data):
    """Presentation-only protection: do not render non-public identifier display text."""
    identifiers = data.get('identifiers_json')
    if not isinstance(identifiers, (str, list)):
        return data
    try:
        entries = json.loads(identifiers) if isinstance(identifiers, str) else identifiers
    except (ValueError, TypeError):
        return data
    if not isinstance(entries, list):
        return data
    protected = []
    for item in entries:
        if not isinstance(item, dict):
            protected.append(item)
        elif item.get('identifier_class') == 'PUBLIC_IDENTIFIER':
            protected.append(item)
        else:
            protected.append({
                'identifier_class': item.get('identifier_class'),
                'identifier_type': item.get('identifier_type'),
                'identifier_hash': item.get('identifier_hash'),
            })
    return {**data, 'identifiers_json': protected}


def record_html(record, links, physical_links=(), timezone_name=None, governance=None, lookup=None):
    data = thaw(record.data)
    if record.table == 'passive_security_platforms':
        data = _redact_nonpublic_platform_identifiers(data)
    title = next((data[k] for k in ('title', 'label', 'dimension', 'metric_id', 'rule_id') if data.get(k) is not None), None)
    if title is None:
        title = next((v for _, v in record.identity), 'Registro persistido')
    elif isinstance(title, str):
        for key in ('dimension', 'metric_id', 'rule_id'):
            if data.get(key) == title:
                title = public_value(title, key, timezone_name)
                break
    status = state(data.get('status', data.get('state', data.get('consolidation_status'))), data.get('reason'))
    if record.table == 'serp_observations':
        status = ('Observado' if data.get('observation_status') == 'OBSERVED' else state(data.get('observation_status'), data.get('reason')))
    if record.table.startswith('synthetic_') and record.table.endswith('_summaries') and data.get('apdex_score') is not None:
        status = 'Índice medido'
    origin = 'Regra' if record.table in {'rule_executions', 'findings', 'score_contributions'} else 'Medido'
    if record.table == 'jsonld_remediation_suggestions':
        origin = 'Proposta determinística do RASAi · baseada na captura'
    elif record.table == 'content_remediation_suggestions' or (record.table == 'improvement_intelligence_recommendations' and data.get('source') == 'AI'):
        origin = 'IA sugeriu · Sugestão não aprovada'
    elif data.get('provider') and data.get('model'):
        origin = 'IA avaliou' if 'assessment' in record.table else 'Proveniência de IA persistida'
    elif record.table.startswith(('serp_', 'perplexity_', 'web_performance', 'lighthouse_')):
        origin = 'Externo'
    fields = ('value', 'performance_score', 'accessibility_score', 'apdex_score', 'lcp_p75_ms', 'coverage', 'confidence', 'device', 'url', 'field_scope', 'profile_id', 'valid_samples', 'severity', 'priority', 'priority_class', 'validation', 'verification', 'expected_condition', 'observed_value')
    summary = ''.join(f'<dt>{esc(metric_label({**data,"_source_table":record.table},k,{}) if k=="apdex_score" else public_label(k))}</dt><dd>{esc(public_value(data[k],k,timezone_name))}</dd>' for k in fields if k in data and not isinstance(data[k], (dict, list)))
    if governance is not None and record.table in {'improvement_intelligence_recommendations', 'directed_analysis_actions', 'recommendations', 'content_remediation_suggestions', 'jsonld_remediation_suggestions'}:
        summary += '<dt>Governança</dt><dd>' + esc(governance.disposition(record.table, data)) + '</dd>'
    if record.table == 'recommendation_governance':
        summary += ''.join(f'<dt>{esc(label)}</dt><dd>{esc(value)}</dd>' for label, value in (
            ('Decisão', data.get('decision')), ('Alvo', data.get('target_class')), ('Motivo', data.get('rejection_reason'))))
    lookup = lookup or {}
    refs = ''.join(
        f'<a class="tech-link" href="{esc(target)}" '
        f'aria-label="{esc(_record_link_name(target, lookup))}">'
        f'{esc(_record_link_name(target, lookup))}</a> '
        for target in links[record.href]
    )
    refs += ''.join(
        f'<a class="tech-link" href="extracao.html#physical-{index}" '
        f'aria-label="Detalhe: evidência física {index + 1}">Abrir evidência física {index + 1}</a> '
        for index in physical_links
    )
    return f'<div class="record" id="{record.anchor}"><h3>{esc(title)}</h3><p class="org">{esc(origin)}</p><p>{esc(status)}</p><dl>{summary}</dl><details><summary>Dados persistidos e proveniência (datas no fuso da auditoria)</summary>{payload(presentation_timestamps(data, timezone_name))}<p>ID de apresentação: {record.anchor}</p></details><nav aria-label="Referências bidirecionais">{refs}</nav></div>'


def review_table(records, links, evidence, physical, governance=None):
    by_href = {record.href: record for record in records}
    body = '<div class="tw"><table><caption>Arquivos e conteúdos a revisar — vínculos persistidos explícitos</caption><thead><tr>'
    headings = ('Arquivo / SHA-256', 'Elemento / trecho', 'Problema / criticidade / prioridade', 'Origem / cobertura', 'Ação', 'Evidência', 'Validação')
    body += ''.join(f'<th scope="col">{heading}</th>' for heading in headings) + '</tr></thead><tbody>'
    for record in records:
        if record.table not in {'findings', 'improvement_intelligence_findings', 'passive_security_findings'}:
            continue
        data = thaw(record.data)
        related = [by_href[href] for href in links[record.href]]
        actions = [r for r in related if r.table in {'directed_analysis_actions', 'recommendations', 'improvement_intelligence_recommendations', 'passive_security_remediations'}]
        if governance is not None:
            actions = [r for r in actions if not governance.excluded(r.table, r.data)]
        evidence_rows = sorted({index for r in [record] + [r for r in related if r.table in {'evidence', 'element_observations'}] for index in physical.get(r.href, ())})
        for index in evidence_rows or [None]:
            item = evidence[index] if index is not None else {}
            file = esc(item.get('reference')) + '<br><code>' + esc(item.get('sha256')) + '</code>'
            element = esc(item.get('selector', data.get('selector'))) + '<pre>' + esc(item.get('excerpt')) + '</pre>'
            problem = f'{esc(data.get("title", data.get("finding_id")))}<br>{esc(public_value(data.get("severity"),"severity"))} / {esc(public_value(data.get("priority"),"priority"))}<br><a class="tech-link" href="{record.href}">Abrir achado técnico</a>'
            origin = esc(public_value(data.get('source', data.get('origin_kind')), 'source')) + '<br>' + esc(public_value(item.get('coverage', 'Parcial — vínculo físico inequívoco ausente'), 'coverage'))
            action = '<br>'.join(f'{esc(thaw(r.data).get("title", "Ação vinculada"))}<br><a class="tech-link" href="{r.href}">Abrir ação técnica</a>' for r in actions) or 'N/D'
            evidence_link = f'<a class="tech-link" href="extracao.html#physical-{index}">Abrir evidência física</a>' if index is not None else 'N/D'
            validation = [thaw(r.data).get('validation_steps_json', thaw(r.data).get('validation', thaw(r.data).get('verification'))) for r in actions]
            validation = [value for value in validation if value is not None]
            body += '<tr>' + ''.join(f'<td>{value}</td>' for value in (file, element, problem, origin, action, evidence_link, payload(validation) if validation else esc(data.get('validation')))) + '</tr>'
    return body + '</tbody></table></div>'



def grouped_physical_references(evidence, timezone_name):
    """Show each physical path once, preserving every indexed provenance link.

    The physical reference index is intentionally *not* deduplicated: existing
    `extracao.html#physical-N` anchors still identify individual observations.
    A group merely changes the presentation of an immutable evidence inventory.
    """
    from .components import kv

    grouped = {}
    for index, item in enumerate(evidence):
        reference = str(item.get('reference') or '')
        grouped.setdefault(reference, []).append((index, item))
    total_references = len(evidence)
    body = (
        '<p class="rf">Arquivos referenciados: ' + str(len(grouped))
        + ' caminho(s) único(s) - ' + str(total_references)
        + ' referência(s) persistida(s). Entradas repetidas apontam ao '
        'mesmo arquivo; cada vínculo e sua proveniência são preservados.</p>'
    )
    for reference, occurrences in grouped.items():
        hashes = {item.get('sha256') for _, item in occurrences if item.get('sha256')}
        count = len(occurrences)
        body += (
            '<details class="physical-file-group"><summary>'
            + esc(reference)
            + ' <span class="rf">(' + str(count) + ' referência'
            + ('s' if count != 1 else '') + ')</span></summary>'
        )
        if len(hashes) == 1:
            body += '<p class="rf">SHA-256 do arquivo: <code>' + esc(next(iter(hashes))) + '</code></p>'
        elif len(hashes) > 1:
            body += '<p class="callout w">Hashes divergentes entre referências; verificar cada vínculo.</p>'
        else:
            body += '<p class="rf">SHA-256: N/D - arquivo ausente ou não verificado.</p>'
        for index, item in occurrences:
            label = (
                'Referência ' + str(index + 1) + ' - '
                + str(item.get('table') or 'registro')
                + ' / ' + str(item.get('field') or 'campo não identificado')
                + ' (linha ' + str(item.get('row_index', 0) + 1) + ')'
            )
            body += (
                '<details class="in" id="physical-' + str(index) + '">'
                '<summary>' + esc(label) + '</summary>'
                + kv([
                    (public_label(k), public_value(item.get(k), k, timezone_name))
                    for k in ('sha256', 'type', 'coverage', 'selector', 'line', 'column')
                    if k != 'sha256' or len(hashes) != 1
                ])
                + '<pre>' + esc(item.get('excerpt')) + '</pre>'
                + '<a class="tech-link" href="' + esc(item['source_href'])
                + '">Voltar ao registro técnico de origem</a>'
                + '<details class="in"><summary>Proveniência completa</summary>'
                + payload(item) + '</details></details>'
            )
        body += '</details>'
    return body


def render(records, links, tables, evidence, calculated, costs, parity, thresholds, missing, supplements=None):
    from .page_views import editorial
    from .components import table, kv
    output, physical = {}, {}
    timezone_name, _ = timezone_for_records(records)
    for index, item in enumerate(evidence):
        family = [r for r in records if r.table == item['table']]
        source = family[item['row_index']]
        item['source_href'] = source.href
        physical.setdefault(source.href, []).append(index)
    governance = Governance(tables.get('recommendation_governance', ()))
    lookup = {record.href: record for record in records}
    for page, title in PAGES:
        # Visual capture evidence is visible in HTML immediately, not hidden in
        # technical tables or available only via a modal.
        body = ((supplements or {}).get('extracao:visual', '') if page == 'extracao' else '')
        body += (supplements or {}).get(page + ':primary', '')
        if page == 'plano':
            body += editorial(page, records, costs, thresholds, governance=governance)
        body += (supplements or {}).get(page + ':execution', '')
        body += (supplements or {}).get(page + ':coverage', '')
        if page != 'plano':
            body += editorial(page, records, costs, thresholds, governance=governance)
        body += (supplements or {}).get(page, '')
        if page == 'extracao':
            body += '<span id="capture-counts"></span><h2>Contagens derivadas da captura</h2><p>Palavras são tokens de texto no HTML renderizado, excluídos script e style. O contador não testa visibilidade CSS. A comparação competitiva pode usar outro documento e método.</p>' + table('Calculado no relatório', calculated, [('source','Fonte'),('sha256','SHA-256'),('words','Palavras'),('links','Links'),('images','Imagens'),('algorithm_version','Algoritmo')])
            body += '<h2>Arquivos e referências físicas</h2>'
            body += grouped_physical_references(evidence, timezone_name)
        if page == 'performance':
            body += '<p class="callout w">Laboratório, campo e amostras sintéticas são universos independentes. Sem série temporal comparável persistida, nenhum gráfico histórico é fabricado.</p>'
        if page == SEARCH_PAGE:
            body += '<p class="callout w">Busca não equivale a citação. Posição não prova causalidade. Consulta, idioma, mercado, dispositivo e instante delimitam a amostra.</p>'
        if page == 'index':
            routed = [(name, destination(name), len(items))
                      for name, items in sorted(tables.items())
                      if destination(name) is not None]
            body += (
                '<h2>Fontes e localização dos registros</h2>'
                '<p class="rf">Cada fonte persistida permanece disponível na página '
                'temática de origem. O Painel apresenta o contexto e as contagens, '
                'não replica o inventário técnico completo de outras páginas.</p>'
                '<div class="tw"><table><caption>Fontes da auditoria</caption>'
                '<thead><tr><th scope="col">Fonte</th><th scope="col">Registros</th>'
                '<th scope="col">Abrir na página de origem</th></tr></thead><tbody>'
            )
            for name, destination_page, count in routed:
                target = (destination_page + '.html#source-' +
                          sha256(name.encode()).hexdigest()[:12])
                body += ('<tr><td>' + esc(public_label(name)) + '</td><td>' +
                         str(count) + '</td><td><a class="tech-link" href="' +
                         esc(target) + '" aria-label="Detalhe: ' +
                         esc(public_label(name)) + ' · ' + esc(name) + ' · ' + esc(destination_page) +
                         '">Abrir registros da fonte</a></td></tr>')
            body += '</tbody></table></div>'
        inventory_anchor = ' id="network-evidence-inventory"' if page == 'rede' else ''
        body += '<h2>Evidências e detalhe técnico</h2><details' + inventory_anchor + '><summary>Inventário integral de registros e anexos</summary><span id="presentation-records"></span>'
        if page == 'rede':
            body += (supplements or {}).get(
                'rede:inventory',
                '<p class="callout">Inventário local de rede indisponível para esta projeção.</p>',
            )
        if page == 'plano':
            body += '<details><summary>Arquivos e conteúdos a revisar</summary>' + review_table(records,links,evidence,physical,governance) + '</details>'
        routed_tables = [table_name for table_name in tables if destination(table_name) == page]
        if page != 'rede' and not routed_tables:
            body += '<p class="callout">Nenhuma família de registros do audit.db foi roteada para esta página.</p>'
        for table_name in routed_tables:
            items = [r for r in records if r.table == table_name]
            body += f'<details id="source-{sha256(table_name.encode()).hexdigest()[:12]}"><summary>{esc(public_label(table_name))} · {len(items)} registros</summary><a class="tech-link" href="anexos/{table_annex_filename(table_name)}">Abrir anexo sanitizado integral</a>'
            body += ''.join(record_html(record, links, physical.get(record.href, ()), timezone_name, governance, lookup) for record in items) + '</details>'
        body += '</details><details><summary>Limitações, cobertura e conferência de paridade</summary>' + payload({'missing_data':missing,'parity':parity}) + '</details>'
        audit_id = tables.get('audits',[{}])[0].get('audit_id') if tables.get('audits') else None
        output[page+'.html'] = shell(page,title,body,audit_id)
    return output
