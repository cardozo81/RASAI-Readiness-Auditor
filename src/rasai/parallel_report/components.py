"""Prototype components; only persisted values enter these presentation views."""
from html import escape
import json
import math
from .presentation_labels import FIELD_LABELS, ORIGIN_LABELS, public_value, chip_tone


def text(value):
    if value is None:
        return 'N/D'
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return escape(str(value), quote=True)


def chip(value, field='status'):
    tone = chip_tone(value, field)
    return f'<span class="chip {tone}" title="{text(value)}">{text(public_value(value,field))}</span>'


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
    zone_classes = proposal.get('zone_classes') if proposal else None
    default_classes = [f'z{i + 1}' for i in range(len(boundaries) - 1)] if zones else ['z0']
    classes = zone_classes if zone_classes and len(zone_classes) == len(boundaries) - 1 else default_classes
    bars = ''.join(f'<i class="{classes[i]}" data-width="{(end-start)/maximum*100:g}"></i>' for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])))
    marker = f'<b class="mk" data-position="{position:g}" aria-hidden="true"></b>' if valid else ''
    note = proposal['note'] if proposal else 'Escala de leitura; sem faixa universal aplicada. Não altera a medição persistida.'
    reference = proposal['origin'] if proposal else 'PERSISTED_CONTRACT'
    labels = (proposal.get('range_text') or ' · '.join(f'{label}: {value}' for label, value in zip(proposal['labels'], zones))) if proposal else f'0–{maximum}'
    display_value = (format(value, '.2f').rstrip('0').rstrip('.').replace('.', ',') if valid else text(value))
    title = f'<a href="{text(href)}">{text(label)}</a>' if href else text(label)
    return f'<div class="ruler"><div class="rh"><strong>{title}</strong><span class="rv" title="{text(value)}">{display_value}</span><span class="zl none">{text(ORIGIN_LABELS.get(reference, reference))}</span></div><div class="bar">{bars}{marker}</div><div class="rf">{text(labels)} · {text(ORIGIN_LABELS.get(reference, reference))}</div><div class="rf">{text(scope)}</div><details class="in"><summary>Origem da faixa e limites</summary>{text(note)}<p><code>{text(reference)}</code></p></details></div>'


def table(caption, rows, columns, timezone_name=None):
    headings = ''.join(f'<th scope="col">{text(FIELD_LABELS.get(key,label))}</th>' for key, label in columns)
    body = ''
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key)
            if key in {'status', 'state', 'result', 'severity', 'priority', 'priority_class'}:
                cell = chip(value,key)
            elif key == '_ref':
                cell = f'<a href="{text(value)}">Evidência e detalhes</a>' if value else 'N/D'
            else:
                cell = text(public_value(value,key,timezone_name))
                if len(str(value)) > 180:
                    cell = '<details class="in"><summary>Ver conteúdo completo</summary>' + cell + '</details>'
            cells.append('<td title="' + text(value) + '">' + cell + '</td>')
        body += '<tr>' + ''.join(cells) + '</tr>'
    return f'<div class="tw"><table><caption>{text(caption)}</caption><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div>' if rows else '<p class="callout">Não medido — nenhum registro disponível para esta seção.</p>'


def stack(parts, title='Composição proporcional', unit=None, note=None):
    normalized = []
    for part in parts:
        if len(part) == 2:
            label, value = part
            detail = None
        else:
            label, value, detail = part
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric) or numeric < 0:
            continue
        normalized.append((label, value, detail, numeric))
    total = sum(item[3] for item in normalized)
    if total <= 0:
        return '<p>Composição não disponível para total nulo.</p>'

    aria_parts = []
    spans = []
    legend = []
    technical = []
    for index, (label, raw_value, detail, numeric) in enumerate(normalized):
        percentage = numeric / total * 100
        tone = f'cat{index % 8 + 1}'
        amount_label = (f'{unit} ' if unit else '') + str(public_value(str(raw_value),'amount'))
        percentage_label = f'{percentage:.1f}'.replace('.', ',') + '%'
        aria_parts.append(f'{label}: {amount_label}, {percentage_label}')
        spans.append(
            f'<span class="{tone}" data-width="{percentage:g}" '
            f'title="{text(label)} · {text(amount_label)} · {percentage_label}"></span>'
        )
        legend.append(
            '<li><span class="sw ' + tone + '" aria-hidden="true"></span>'
            f'<span class="stack-label">{text(label)}</span>'
            f'<strong>{text(amount_label)}</strong><span>{percentage_label}</span></li>'
        )
        if detail:
            technical.append(f'<li><strong>{text(label)}</strong>: <code>{text(detail)}</code></li>')

    total_label = ((str(unit)+' ') if unit else '') + format(total, '.10g').replace('.',',')
    aria = f'{title}. Total {total_label}. ' + '; '.join(aria_parts)
    html = (
        f'<div class="stack-head"><strong>{text(title)}</strong><span>{text(total_label)}</span></div>'
        f'<div class="stack" role="img" aria-label="{text(aria)}">' + ''.join(spans) + '</div>'
        '<ul class="stack-legend">' + ''.join(legend) + '</ul>'
    )
    if note:
        html += f'<p class="rf">{text(note)}</p>'
    if technical:
        html += '<details class="in"><summary>Ver IDs técnicos das tentativas</summary><ul class="stack-tech">' + ''.join(technical) + '</ul></details>'
    return html
