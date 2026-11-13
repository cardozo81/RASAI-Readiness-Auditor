"""Offline HTML rendering; consumes only the intermediate model."""
from html import escape
import json
from hashlib import sha256
from .coverage import display, state
from .read_model import PAGES, destination, thaw
from .templates import label as public_label


def esc(value):
    return escape(display(value), quote=True)


def payload(value):
    return '<pre>' + esc(json.dumps(value, ensure_ascii=False, indent=2, default=str)) + '</pre>'


def shell(page, title, body):
    nav = ''.join(f'<a href="{name}.html"' + (' aria-current="page"' if name == page else '') + f'>{esc(label)}</a>' for name, label in PAGES)
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>{esc(title)} · RASAi</title><link rel="stylesheet" href="assets/site.css"><script defer src="assets/app.js"></script></head>
<body><a class="skip" href="#main">Pular para o conteúdo</a><aside><strong>RASAi</strong><p>Relatório paralelo</p><nav aria-label="Páginas">{nav}</nav></aside>
<main id="main" tabindex="-1"><header><span>ANÁLISE DA AUDITORIA · LEITURA OFFLINE</span><button id="theme" type="button">Alternar tema</button><h1>{esc(title)}</h1>
<p>Projeção dos fatos persistidos. Sem nova coleta, IA ou recálculo de score.</p></header>
<div class="toolbar"><label>Filtrar registros <input id="filter" type="search"></label><button id="expand">Expandir tudo</button><button id="collapse">Recolher tudo</button><button id="sort">Ordenar por título</button><span id="visible" role="status"></span></div>
{body}<footer>Dados ausentes permanecem N/D. Confiança declarada por IA não é probabilidade estatística. Literais são escapados e credenciais reconhecidas são ocultadas.</footer></main></body></html>'''


def record_html(record, links, physical_links=()):
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
    summary = ''.join(f'<dt>{esc(public_label(k))}</dt><dd>{esc(data[k])}</dd>' for k in fields if k in data and not isinstance(data[k], (dict, list)))
    refs = ''.join(f'<a href="{esc(target)}">Referência vinculada {i + 1}</a> ' for i, target in enumerate(links[record.href]))
    refs += ''.join(f'<a href="extracao.html#physical-{index}">Referência de evidência física</a> ' for index in physical_links)
    return f'<article class="record" id="{record.anchor}"><h3>{esc(title)}</h3><p class="badge">{esc(origin)}</p><p>{esc(status)}</p><dl>{summary}</dl><details><summary>Dados persistidos e proveniência</summary>{payload(data)}<p>ID de apresentação: {record.anchor}</p></details><nav aria-label="Referências bidirecionais">{refs}</nav></article>'


def review_table(records, links, evidence, physical):
    by_href = {record.href: record for record in records}
    body = '<div class="table-scroll"><table><caption>Arquivos e conteúdos a revisar — vínculos persistidos explícitos</caption><thead><tr>'
    headings = ('Arquivo / SHA-256', 'Elemento / trecho', 'Problema / severidade / prioridade', 'Origem / cobertura', 'Ação', 'Evidência', 'Validação')
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
            problem = f'<a href="{record.href}">{esc(data.get("title", data.get("finding_id")))}</a><br>{esc(data.get("severity"))} / {esc(data.get("priority"))}'
            origin = esc(data.get('source', data.get('origin_kind'))) + '<br>' + esc(item.get('coverage', 'Parcial — vínculo físico inequívoco ausente'))
            action = '<br>'.join(f'<a href="{r.href}">{esc(thaw(r.data).get("title", "Ação vinculada"))}</a>' for r in actions) or 'N/D'
            evidence_link = f'<a href="extracao.html#physical-{index}">Referência de evidência</a>' if index is not None else 'N/D'
            validation = [thaw(r.data).get('validation_steps_json', thaw(r.data).get('validation', thaw(r.data).get('verification'))) for r in actions]
            validation = [value for value in validation if value is not None]
            body += '<tr>' + ''.join(f'<td>{value}</td>' for value in (file, element, problem, origin, action, evidence_link, payload(validation) if validation else esc(data.get('validation')))) + '</tr>'
    return body + '</tbody></table></div>'


def render(records, links, tables, evidence, calculated, costs, parity, thresholds, missing):
    output = {}
    physical = {}
    for index, item in enumerate(evidence):
        family = [r for r in records if r.table == item['table']]
        source = family[item['row_index']]
        item['source_href'] = source.href
        physical.setdefault(source.href, []).append(index)
    notes = {
        'performance': 'Lighthouse: laboratório, escala persistida 0–100. CrUX: campo, URL/ORIGIN. Apdex: sintético por dispositivo/perfil; amostras não representam usuários reais.',
        'search-geo': 'Busca não equivale a citação generativa. Ranking não prova causalidade. Ausência é limitada à amostra; comparabilidade entre query/idioma/mercado/device/tempo não é inferida.',
        'indices': 'SARI, Lighthouse, CWV, Apdex e Observatory são independentes. Coverage, confiança, consolidação e limitações qualificam cada resultado. Nenhum score agregado novo.',
        'plano': 'Ações preservam identidade canônica. Agrupamentos não são somáveis. Conteúdo sugerido por IA depende de decisão humana.',
        'seguranca': 'Somente segurança passiva persistida. Nenhum probe executado.',
    }
    for page, title in PAGES:
        groups = {table: [r for r in records if r.table == table] for table in tables if destination(table) == page}
        body = '<p class="notice">' + esc(notes.get(page, 'Cobertura limitada aos dados efetivamente persistidos.')) + '</p>'
        if page == 'index':
            body += '<section><h2>Inventário da auditoria</h2><div class="cards">'
            for table, label in [('scores', 'Índices persistidos'), ('findings', 'Achados'), ('directed_analysis_actions', 'Ações canônicas'), ('evidence', 'Evidências')]:
                count = len(tables[table]) if table in tables else None
                body += f'<div><strong>{esc(count)}</strong><p>{label}</p></div>'
            body += '</div><details><summary>Limitações e conferência com o snapshot canônico</summary>' + payload({'missing_data': missing, 'parity': parity}) + '</details></section>'
            body += '<section><h2>Indicadores independentes</h2><div class="cards">'
            for record in records:
                if record.table in {'scores', 'web_performance_observations', 'synthetic_apdex_summaries', 'synthetic_ux_apdex_summaries'}:
                    data = thaw(record.data)
                    for metric in ('value', 'performance_score', 'accessibility_score', 'apdex_score'):
                        if metric in data:
                            label = data.get('dimension', metric)
                            body += f'<div><a href="{record.href}">{esc(label)}</a><p><strong>{esc(data[metric])}</strong></p><p>{esc(data.get("device"))} · {esc(data.get("profile_id"))}</p><p>{esc(data.get("consolidation_status", data.get("status")))}</p></div>'
            body += '</div><p>Valores independentes; a qualidade numérica não substitui o estado de prontidão.</p></section>'
        if page == 'ia-custos':
            body += '<section><h2>Custos conciliados</h2><p>' + esc(costs['coverage']) + ' · ' + str(costs['attempt_count']) + ' tentativas identificadas</p><div class="cards">'
            for currency, amounts in costs['totals'].items():
                for kind, value in amounts.items():
                    body += f'<div><strong>{esc(value)}</strong><p>{esc(currency)} · {esc(kind)}</p></div>'
            body += '</div><details><summary>Reconciliação por tentativa e limitações</summary>' + payload(costs) + '</details><p>Previsto/forecast permanece no seu registro; realizado técnico não equivale a invoice.</p></section>'
        if page == 'indices':
            body += '<details><summary>Faixas de apresentação propostas</summary>' + payload(thresholds) + '</details>'
            for proposal in thresholds:
                ticks = ''.join(f'<line x1="{value * 5 + 20}" y1="35" x2="{value * 5 + 20}" y2="55" stroke="currentColor"/><text x="{value * 5 + 20}" y="78" text-anchor="middle" fill="currentColor">{value}</text>' for value in proposal['thresholds'])
                body += f'<figure><svg role="img" aria-label="Faixas propostas para apresentação, não aprovadas" viewBox="0 0 550 100"><line x1="20" y1="45" x2="520" y2="45" stroke="currentColor"/>{ticks}</svg><figcaption>{esc(proposal["note"])} {esc(" / ".join(proposal["labels"]))}</figcaption></figure>'
        if page == 'extracao':
            body += '<section><h2>Referências de evidência física</h2>'
            for index, item in enumerate(evidence):
                body += f'<details id="physical-{index}"><summary>{esc(item["reference"])} · {esc(item["coverage"])}</summary>{payload(item)}<a href="{item["source_href"]}">Voltar à origem persistida</a></details>'
            body += '<h2>Contagens derivadas</h2>' + payload(calculated) + '</section>'
        if page == 'plano':
            body += '<section><h2>Arquivos e conteúdos a revisar</h2><p>Os vínculos abaixo preservam achado, elemento, evidência e validação quando os IDs são inequívocos. A ausência de vínculo não autoriza localizar um trecho por aproximação.</p>'
            body += review_table(records, links, evidence, physical)
            body += '</section>'
        body += '<nav aria-label="Nesta página"><h2>Nesta página</h2>' + ''.join(f'<a href="#family-{i}">{esc(public_label(table))} ({len(items)})</a> ' for i, (table, items) in enumerate(groups.items())) + '</nav>'
        for i, (table, items) in enumerate(groups.items()):
            body += f'<section id="family-{i}"><h2>{esc(public_label(table))}</h2><p>{len(items)} registros disponíveis. <a href="anexos/{sha256(table.encode()).hexdigest()}.json">Anexo sanitizado integral</a></p><div class="records">'
            body += ''.join(record_html(record, links, physical.get(record.href, ())) for record in items)
            if not items:
                body += '<p>Não medido — nenhum registro persistido nesta família.</p>'
            body += '</div></section>'
        if not groups:
            body += '<p>Não medido — fontes não disponíveis nesta versão da auditoria.</p>'
        output[page + '.html'] = shell(page, title, body)
    return output
