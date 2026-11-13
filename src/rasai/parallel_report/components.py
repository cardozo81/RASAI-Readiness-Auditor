"""Prototype components; only persisted values enter these presentation views."""
from html import escape
import json
import math


def text(value):
    if value is None:
        return 'N/D'
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return escape(str(value), quote=True)


def chip(value):
    token = str(value or '').upper()
    tone = 'none'
    if token in {'SUCCESS', 'COMPLETE', 'COMPLETED', 'PASS', 'CONSOLIDATED'}:
        tone = 'ok'
    elif token in {'PARTIAL', 'WARNING', 'HIGH', 'P1', 'COMPLETE_WITH_LIMITATIONS'}:
        tone = 'warn'
    elif token in {'FAILED', 'ERROR', 'FAIL', 'CRITICAL', 'BLOCKED'}:
        tone = 'bad'
    return f'<span class="chip {tone}">{text(value)}</span>'


def origin(value='Medido'):
    kind = 'iasug' if 'sugeriu' in value else ('iaav' if 'avaliou' in value else ('ext' if value == 'Externo' else ''))
    return f'<span class="org {kind}">{text(value)}</span>'


def kv(pairs):
    return '<dl class="kv">' + ''.join(f'<div><dt>{text(k)}</dt><dd>{text(v)}</dd></div>' for k, v in pairs) + '</dl>'


def ruler(label, value, maximum=100, proposal=None, scope=None, href=None):
    valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    position = min(100, max(0, value / maximum * 100)) if valid else None
    zones = proposal['thresholds'] if proposal else []
    boundaries = [0] + zones + [maximum]
    bars = ''.join(f'<i class="z{i+1 if zones else 0}" data-width="{(end-start)/maximum*100:g}"></i>' for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])))
    marker = f'<b class="mk" data-position="{position:g}" aria-hidden="true"></b>' if valid else ''
    note = proposal['note'] if proposal else 'Escala de leitura; sem faixa universal aplicada. Não altera a medição persistida.'
    reference = proposal['origin'] if proposal else 'PERSISTED_CONTRACT · escala da fonte'
    labels = ' · '.join(f'{label}: {value}' for label, value in zip(proposal['labels'], zones)) if proposal else f'0–{maximum}'
    display_value = (format(value, '.2f').rstrip('0').rstrip('.').replace('.', ',') if valid else text(value))
    title = f'<a href="{text(href)}">{text(label)}</a>' if href else text(label)
    return f'<div class="ruler"><div class="rh"><strong>{title}</strong><span class="rv" title="{text(value)}">{display_value}</span><span class="zl none">{"Proposta" if proposal else "Valor persistido"}</span></div><div class="bar">{bars}{marker}</div><div class="rf">{text(labels)} · {text(reference)}</div><div class="rf">{text(scope)}</div><details class="in"><summary>Origem da faixa e limites</summary>{text(note)}</details></div>'


def table(caption, rows, columns):
    headings = ''.join(f'<th scope="col">{text(label)}</th>' for _, label in columns)
    body = ''
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key)
            if key in {'status', 'state', 'result', 'severity', 'priority', 'priority_class'}:
                cell = chip(value)
            elif key == '_ref':
                cell = f'<a href="{text(value)}">Evidência e detalhes</a>' if value else 'N/D'
            else:
                cell = text(value)
                if len(str(value)) > 180:
                    cell = '<details class="in"><summary>Ver conteúdo completo</summary>' + cell + '</details>'
            cells.append('<td>' + cell + '</td>')
        body += '<tr>' + ''.join(cells) + '</tr>'
    return f'<div class="tw"><table><caption>{text(caption)}</caption><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div>' if rows else '<p class="callout">Não medido — nenhum registro disponível para esta seção.</p>'


def stack(parts):
    total = sum(float(value) for _, value in parts)
    if total <= 0:
        return '<p>Composição não disponível para total nulo.</p>'
    spans = ''.join(f'<span class="z{i%4+1}" data-width="{float(value)/total*100:g}"></span>' for i, (_, value) in enumerate(parts))
    return '<div class="stack" role="img" aria-label="Composição proporcional">' + spans + '</div><p class="rf">' + ' · '.join(f'{text(label)}: {text(value)}' for label, value in parts) + '</p>'
