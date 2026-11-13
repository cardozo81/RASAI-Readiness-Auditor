"""Offline HTML rendering; consumes only the intermediate model."""
from html import escape
import json
from hashlib import sha256
from .coverage import display, state
from .read_model import PAGES, destination, thaw
from .templates import label as public_label
from .presentation_labels import public_value, timezone_for_records, metric_label


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


def record_html(record, links, physical_links=(), timezone_name=None):
    data = thaw(record.data)
    title = next((data[k] for k in ('title', 'label', 'dimension', 'metric_id', 'rule_id') if data.get(k) is not None), None)
    if title is None:
        title = next((v for _, v in record.identity), 'Registro persistido')
    status = state(data.get('status', data.get('state', data.get('consolidation_status'))), data.get('reason'))
    origin = 'Regra' if record.table in {'rule_executions', 'findings', 'score_contributions'} else 'Medido'
    if 'suggestion' in record.table or record.table == 'improvement_intelligence_recommendations':
        origin = 'IA sugeriu · Sugestão não aprovada'
    elif data.get('provider') and data.get('model'):
        origin = 'IA avaliou' if 'assessment' in record.table else 'Proveniência de IA persistida'
    elif record.table.startswith(('serp_', 'perplexity_', 'web_performance', 'lighthouse_')):
        origin = 'Externo'
    fields = ('value', 'performance_score', 'accessibility_score', 'apdex_score', 'lcp_p75_ms', 'coverage', 'confidence', 'device', 'url', 'field_scope', 'profile_id', 'valid_samples', 'severity', 'priority', 'priority_class', 'validation', 'verification', 'expected_condition', 'observed_value')
    summary = ''.join(f'<dt>{esc(metric_label({**data,"_source_table":record.table},k,{}) if k=="apdex_score" else public_label(k))}</dt><dd>{esc(public_value(data[k],k,timezone_name))}</dd>' for k in fields if k in data and not isinstance(data[k], (dict, list)))
    refs = ''.join(f'<a href="{esc(target)}">Referência vinculada {i + 1}</a> ' for i, target in enumerate(links[record.href]))
    refs += ''.join(f'<a href="extracao.html#physical-{index}">Referência de evidência física</a> ' for index in physical_links)
    return f'<div class="record" id="{record.anchor}"><h3>{esc(title)}</h3><p class="org">{esc(origin)}</p><p>{esc(status)}</p><dl>{summary}</dl><details><summary>Dados persistidos e proveniência</summary>{payload(data)}<p>ID de apresentação: {record.anchor}</p></details><nav aria-label="Referências bidirecionais">{refs}</nav></div>'


def review_table(records, links, evidence, physical):
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
        evidence_rows = sorted({index for r in [record] + [r for r in related if r.table in {'evidence', 'element_observations'}] for index in physical.get(r.href, ())})
        for index in evidence_rows or [None]:
            item = evidence[index] if index is not None else {}
            file = esc(item.get('reference')) + '<br><code>' + esc(item.get('sha256')) + '</code>'
            element = esc(item.get('selector', data.get('selector'))) + '<pre>' + esc(item.get('excerpt')) + '</pre>'
            problem = f'<a href="{record.href}">{esc(data.get("title", data.get("finding_id")))}</a><br>{esc(public_value(data.get("severity"),"severity"))} / {esc(public_value(data.get("priority"),"priority"))}'
            origin = esc(data.get('source', data.get('origin_kind'))) + '<br>' + esc(item.get('coverage', 'Parcial — vínculo físico inequívoco ausente'))
            action = '<br>'.join(f'<a href="{r.href}">{esc(thaw(r.data).get("title", "Ação vinculada"))}</a>' for r in actions) or 'N/D'
            evidence_link = f'<a href="extracao.html#physical-{index}">Referência de evidência</a>' if index is not None else 'N/D'
            validation = [thaw(r.data).get('validation_steps_json', thaw(r.data).get('validation', thaw(r.data).get('verification'))) for r in actions]
            validation = [value for value in validation if value is not None]
            body += '<tr>' + ''.join(f'<td>{value}</td>' for value in (file, element, problem, origin, action, evidence_link, payload(validation) if validation else esc(data.get('validation')))) + '</tr>'
    return body + '</tbody></table></div>'


def render(records, links, tables, evidence, calculated, costs, parity, thresholds, missing):
    from .page_views import editorial
    from .components import table, kv
    output, physical = {}, {}
    timezone_name, _ = timezone_for_records(records)
    for index, item in enumerate(evidence):
        family = [r for r in records if r.table == item['table']]
        source = family[item['row_index']]
        item['source_href'] = source.href
        physical.setdefault(source.href, []).append(index)
    for page, title in PAGES:
        body = editorial(page, records, costs, thresholds)
        if page == 'extracao':
            body += '<h2>Contagens derivadas da captura</h2>' + table('Calculado no relatório', calculated, [('source','Fonte'),('sha256','SHA-256'),('words','Palavras'),('links','Links'),('images','Imagens'),('algorithm_version','Algoritmo')])
            body += '<h2>Arquivos e referências físicas</h2>'
            for index, item in enumerate(evidence):
                body += f'<details id="physical-{index}"><summary>{esc(item["reference"])}</summary>' + kv([(public_label(k),public_value(item.get(k),k,timezone_name)) for k in ('sha256','type','coverage','selector','line','column')]) + f'<pre>{esc(item.get("excerpt"))}</pre><a href="{item["source_href"]}">Voltar à origem</a><details class="in"><summary>Proveniência completa</summary>{payload(item)}</details></details>'
        if page == 'performance':
            body += '<p class="callout w">Laboratório, campo e amostras sintéticas são universos independentes. Sem série temporal comparável persistida, nenhum gráfico histórico é fabricado.</p>'
        if page == 'search-geo':
            body += '<p class="callout w">Busca não equivale a citação. Posição não prova causalidade. Consulta, idioma, mercado, dispositivo e instante delimitam a amostra.</p>'
        body += '<h2>Evidências e detalhe técnico</h2><details><summary>Inventário integral de registros e anexos</summary>'
        if page == 'plano':
            body += '<details><summary>Arquivos e conteúdos a revisar</summary>' + review_table(records,links,evidence,physical) + '</details>'
        for table_name in tables:
            if destination(table_name) != page:
                continue
            items = [r for r in records if r.table == table_name]
            body += f'<details><summary>{esc(public_label(table_name))} · {len(items)} registros</summary><a href="anexos/{sha256(table_name.encode()).hexdigest()}.json">Anexo sanitizado integral</a>'
            body += ''.join(record_html(record, links, physical.get(record.href, ()), timezone_name) for record in items) + '</details>'
        body += '</details><details><summary>Limitações, cobertura e conferência de paridade</summary>' + payload({'missing_data':missing,'parity':parity}) + '</details>'
        audit_id = tables.get('audits',[{}])[0].get('audit_id') if tables.get('audits') else None
        output[page+'.html'] = shell(page,title,body,audit_id)
    return output
