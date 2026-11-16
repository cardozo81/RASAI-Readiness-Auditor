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


def esc(value):
    return escape(display(value), quote=True)


def payload(value):
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


def record_html(record, links, physical_links=(), timezone_name=None, governance=None):
    data = thaw(record.data)
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
    refs = ''.join(f'<a class="tech-link" href="{esc(target)}">Abrir registro técnico relacionado {i + 1}</a> ' for i, target in enumerate(links[record.href]))
    refs += ''.join(f'<a class="tech-link" href="extracao.html#physical-{index}">Abrir evidência física</a> ' for index in physical_links)
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
    for page, title in PAGES:
        body = editorial(page, records, costs, thresholds, governance=governance)
        body += (supplements or {}).get(page, '')
        if page == 'extracao':
            body += '<span id="capture-counts"></span><h2>Contagens derivadas da captura</h2><p>Palavras são tokens de texto no HTML renderizado, excluídos script e style. O contador não testa visibilidade CSS. A comparação competitiva pode usar outro documento e método.</p>' + table('Calculado no relatório', calculated, [('source','Fonte'),('sha256','SHA-256'),('words','Palavras'),('links','Links'),('images','Imagens'),('algorithm_version','Algoritmo')])
            body += '<h2>Arquivos e referências físicas</h2>'
            for index, item in enumerate(evidence):
                body += f'<details id="physical-{index}"><summary>{esc(item["reference"])}</summary>' + kv([(public_label(k),public_value(item.get(k),k,timezone_name)) for k in ('sha256','type','coverage','selector','line','column')]) + f'<pre>{esc(item.get("excerpt"))}</pre><a class="tech-link" href="{item["source_href"]}">Voltar ao registro técnico de origem</a><details class="in"><summary>Proveniência completa</summary>{payload(item)}</details></details>'
        if page == 'performance':
            body += '<p class="callout w">Laboratório, campo e amostras sintéticas são universos independentes. Sem série temporal comparável persistida, nenhum gráfico histórico é fabricado.</p>'
        if page == SEARCH_PAGE:
            body += '<p class="callout w">Busca não equivale a citação. Posição não prova causalidade. Consulta, idioma, mercado, dispositivo e instante delimitam a amostra.</p>'
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
            body += f'<details><summary>{esc(public_label(table_name))} · {len(items)} registros</summary><a class="tech-link" href="anexos/{sha256(table_name.encode()).hexdigest()}.json">Abrir anexo sanitizado integral</a>'
            body += ''.join(record_html(record, links, physical.get(record.href, ()), timezone_name, governance) for record in items) + '</details>'
        body += '</details><details><summary>Limitações, cobertura e conferência de paridade</summary>' + payload({'missing_data':missing,'parity':parity}) + '</details>'
        audit_id = tables.get('audits',[{}])[0].get('audit_id') if tables.get('audits') else None
        output[page+'.html'] = shell(page,title,body,audit_id)
    return output
