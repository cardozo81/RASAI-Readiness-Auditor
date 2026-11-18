"""Prototype components; only persisted values enter these presentation views."""
from html import escape
from hashlib import sha256
import json
import math
from .presentation_labels import FIELD_LABELS, ORIGIN_LABELS, public_value, chip_tone, TECHNICAL_ONLY_FIELDS, presentation_timestamps
from .annex_payloads import register_payload


def text(value):
    if value is None:
        return 'N/D'
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return escape(str(value), quote=True)


def chip(value, field='status'):
    tone = chip_tone(value, field)
    return f'<span class="chip {tone}" title="{text(public_value(value,field))}">{text(public_value(value,field))}</span>'


def origin(value='Medido'):
    kind = 'iasug' if 'sugeriu' in value else ('iaav' if 'avaliou' in value else ('ext' if value == 'Externo' else ''))
    return f'<span class="org {kind}">{text(value)}</span>'


def kv(pairs):
    return '<dl class="kv">' + ''.join(f'<div><dt>{text(k)}</dt><dd>{text(v)}</dd></div>' for k, v in pairs) + '</dl>'


def technical_link(href, label='Abrir registro técnico'):
    if not href:
        return ''
    return f'<a class="tech-link" href="{text(href)}" aria-label="{text("Detalhe: " + label + " · " + str(href))}">{text(label)}</a>'


def _ruler_band(value, proposal):
    """Visible qualitative band from the already-versioned display contract."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return 'N/D — sem valor medido'
    if not proposal:
        return 'Sem faixa textual definida no contrato'
    metric = proposal.get('metric_id')
    thresholds = proposal.get('thresholds') or []
    index = sum(value >= threshold for threshold in thresholds)
    if metric == 'APDEX_RESULT_PERSISTED_CONTRACT' and len(thresholds) == 2:
        return ('Ruim', 'Regular', 'Bom')[index]
    if metric == 'LIGHTHOUSE_CATEGORY_PERSISTED_CONTRACT' and len(thresholds) == 2:
        return ('Ruim', 'Precisa melhorar', 'Bom')[index]
    if metric == 'SARI_PRESENTATION_PROPOSAL' and len(thresholds) == 3:
        return ('Abaixo do mínimo proposto', 'Mínimo proposto',
                'Ideal proposto', 'Ótimo proposto')[index] + ' · Proposta não aprovada'
    return 'Sem faixa textual definida no contrato'


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
    title = text(label)
    technical = ('<p class="rf">' + technical_link(href) + '</p>') if href else ''
    return f'<div class="ruler"><div class="rh"><strong>{title}</strong><span class="rv" title="{text(value)}">{display_value}</span><span class="zl none">{text(_ruler_band(value, proposal))}</span></div><div class="bar">{bars}{marker}</div><div class="rf">{text(labels)} · {text(ORIGIN_LABELS.get(reference, reference))}</div><div class="rf">{text(scope)}</div><details class="in"><summary>Detalhes técnicos da faixa e limites</summary>{text(note)}<p><code>{text(reference)}</code></p>{technical}</details></div>'


def _detail_title(row, index):
    for key in ('title', 'label', 'query', 'url', 'requested_url', 'name'):
        value = row.get(key)
        if value not in (None, ''):
            return str(public_value(value, key))
    source = str(row.get('_source_table') or 'Registro persistido')
    identifier = str(row.get('_ref') or '').split('#')[-1]
    return source + (' · ' + identifier if identifier else ' · entrada ' + str(index + 1))


def _detail_dialog(caption, row, columns, index, timezone_name=None):
    persisted = {key: value for key, value in row.items() if not key.startswith('_')}
    if not persisted:
        return '', ''
    seed = f"{caption}|{row.get('_source_table')}|{row.get('_ref')}|{index}"
    dialog_id = 'detail-' + sha256(seed.encode('utf-8')).hexdigest()[:12]
    title_id = dialog_id + '-title'
    title = _detail_title(row, index)
    trigger = (
        f'<button type="button" class="modal-open" data-modal="{dialog_id}" '
        f'aria-haspopup="dialog" aria-controls="{dialog_id}">Ver detalhes</button>'
    )
    visible = []
    seen = set()
    for key, label in columns:
        if key.startswith('_') or key in seen:
            continue
        seen.add(key)
        value = row.get(key)
        if value is None:
            continue
        rendered = public_value(value, key, timezone_name)
        if isinstance(rendered, (dict, list)):
            rendered = json.dumps(rendered, ensure_ascii=False)
        if key in TECHNICAL_ONLY_FIELDS:
            rendered = 'Conteúdo técnico registrado; consultar os dados técnicos abaixo.'
        visible.append((FIELD_LABELS.get(key, label), rendered))
    summary = kv(visible) if visible else '<p class="rf">Sem campos resumidos adicionais.</p>'
    source = row.get('_source_table')
    source_html = (
        f'<p class="rf">Tabela de origem: <code>{text(source)}</code></p>' if source else ''
    )
    original = presentation_timestamps(persisted, timezone_name)
    annex = register_payload(original)
    if annex:
        filename, digest = annex
        raw = ('<a class="tech-link" href="anexos/' + text(filename) +
               '">Abrir JSON original sanitizado · SHA-256 ' + text(digest) + '</a>')
    else:
        raw = '<pre>' + text(json.dumps(original, ensure_ascii=False, indent=2, default=str)) + '</pre>'
    technical = technical_link(row.get('_ref'), 'Abrir registro técnico completo')
    dialog = ''.join([
        f'<dialog class="detail-dialog" id="{dialog_id}" aria-labelledby="{title_id}">',
        '<div class="modal-head"><div><span class="modal-kicker">' + text(caption) + '</span>',
        f'<h2 id="{title_id}">{text(title)}</h2><span class="modal-kicker">Registro {index + 1}</span></div>',
        '<button type="button" class="modal-close" data-modal-close aria-label="Fechar detalhes">×</button></div>',
        '<div class="modal-body">' + summary,
        '<details class="in"><summary>Dados técnicos originais (rastreabilidade)</summary><p class="rf">Horários exibidos no fuso da auditoria; valores originais permanecem nos anexos.</p>'
        + source_html + raw + '</details>',
        '</div><div class="modal-foot">',
        technical if technical else '<span class="rf">Sem referência técnica adicional.</span>',
        '<button type="button" class="modal-dismiss" data-modal-close>Fechar</button></div></dialog>',
    ])
    return trigger, dialog



def _map_point_cell(value):
    """Trusted, derived-only link and swatch for the presentation map."""
    if not isinstance(value, dict):
        return 'Não localizado no mapa'
    number = value.get('number')
    color = value.get('color')
    if type(number) is not int or not 1 <= number <= 10000:
        return 'Não localizado no mapa'
    if not isinstance(color, str) or len(color) != 7 or not color.startswith('#'):
        return 'Não localizado no mapa'
    if any(char not in '0123456789abcdefABCDEF' for char in color[1:]):
        return 'Não localizado no mapa'
    return (
        '<span class="map-ref">'
        '<svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">'
        f'<rect x="1" y="1" width="12" height="12" rx="2" fill="{color}"/></svg>'
        f'<a href="#network-map-point-{number}">Ponto {number}</a>'
        '</span>'
    )


def table(caption, rows, columns, timezone_name=None, *, full_text=False):
    if not rows:
        return '<p class="callout">Não medido — nenhum registro disponível para esta seção.</p>'
    has_details = any(
        row.get('_ref')
        or any(not key.startswith('_') and key not in {name for name, _ in columns} for key in row)
        or any(key in TECHNICAL_ONLY_FIELDS and row.get(key) is not None for key, _ in columns)
        for row in rows
    )
    headings = ''.join(f'<th scope="col">{text(FIELD_LABELS.get(key,label))}</th>' for key, label in columns)
    if has_details:
        headings += '<th scope="col" class="no-sort" data-sort="none">Detalhes</th>'
    body = ''
    dialogs = []
    for index, row in enumerate(rows):
        cells = []
        for key, _ in columns:
            value = row.get(key)
            if key in {'status', 'state', 'result', 'severity', 'priority', 'priority_class'}:
                cell = chip(value,key)
            elif key == '_ref':
                cell = technical_link(value) if value else 'N/D'
            elif key == '_map_point':
                cell = _map_point_cell(value)
                title_value = ('Correspondência com a localização aproximada do mapa'
                               if isinstance(value, dict) else 'Não localizado no mapa')
            else:
                if key in TECHNICAL_ONLY_FIELDS and value is not None:
                    rendered = 'Conteúdo técnico disponível em Ver detalhes'
                else:
                    rendered = public_value(value,key,timezone_name)
                plain = json.dumps(rendered, ensure_ascii=False) if isinstance(rendered, (dict, list)) else str(rendered)
                if len(plain) > 180 and not full_text:
                    cell = text(plain[:177].rstrip() + '…')
                    title_value = 'Conteúdo completo disponível em Ver detalhes'
                else:
                    cell = text(rendered)
                    title_value = rendered
            if key in {'status', 'state', 'result', 'severity', 'priority', 'priority_class'}:
                title_value = public_value(value,key,timezone_name)
            elif key == '_ref':
                title_value = 'Abrir vínculo de rastreabilidade técnica'
            cells.append('<td title="' + text(title_value) + '">' + cell + '</td>')
        if has_details:
            trigger, dialog = _detail_dialog(caption, row, columns, index, timezone_name)
            cells.append('<td class="detail-cell">' + (trigger or 'N/D') + '</td>')
            if dialog:
                dialogs.append(dialog)
        body += '<tr>' + ''.join(cells) + '</tr>'
    table_html = f'<div class="tw"><table><caption>{text(caption)}</caption><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div>'
    return table_html + ''.join(dialogs)

def stack(parts, title='Composição proporcional', unit=None, note=None):
    """Offline accessible cost composition with row-local, evidence-bound metadata.

    The eight cat* CSS classes denote palette positions, not catalog IDs.
    A tooltip can never fabricate a per-catalog allocation from those classes.
    """
    normalized = []
    for part in parts:
        if len(part) == 2:
            label, value = part
            detail, metadata = None, {}
        elif len(part) == 3:
            label, value, detail = part
            metadata = {}
        else:
            label, value, detail, metadata = part
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric) or numeric < 0:
            continue
        normalized.append((label, value, detail, numeric,
                           metadata if isinstance(metadata, dict) else {}))
    total = sum(item[3] for item in normalized)
    if total <= 0:
        return '<p>Composição não disponível para total nulo.</p>'

    aria_parts, spans, legend, technical = [], [], [], []
    for index, (label, raw_value, detail, numeric, metadata) in enumerate(normalized):
        percentage = numeric / total * 100
        tone = f'cat{index % 8 + 1}'  # Palette only, never a CAT-xx identifier.
        amount_label = (f'{unit} ' if unit else '') + str(public_value(str(raw_value), 'amount'))
        percentage_label = f'{percentage:.1f}'.replace('.', ',') + '%'
        kind = {
            'observado': 'Custo observado pelo provedor',
            'estimado': 'Custo estimado persistido',
        }.get(metadata.get('kind'), 'Valor apresentado')
        def described(name):
            value = metadata.get(name)
            return str(value) if value not in (None, '') else 'N/D'
        origin = described('source')
        purpose = described('purpose')
        provider = described('provider')
        model = described('model')
        reasoning = described('reasoning')
        catalog = 'Catálogo de origem não individualizado nesta tentativa'
        provenance = (f'Origem: {origin}; finalidade: {purpose}; provedor: {provider}; '
                      f'modelo: {model}; esforço solicitado: {reasoning}; {catalog}')
        fallback = described('fallback')
        if fallback != 'N/D':
            provenance += f'; motivo do fallback: {fallback}'
        description = (f'{label}. {kind}: {amount_label}; {percentage_label} do total '
                       f'desta moeda. {provenance}. Referência: {detail or "N/D"}. '
                       'Não representa cobrança final.')
        aria_parts.append(description)
        spans.append(
            f'<span class="{tone}" data-width="{percentage:g}" '
            f'title="{text(description)}" data-explanation="{text(description)}" '
            'aria-hidden="true"></span>'
        )
        # Metadata remains readable without hover and keyboard users receive
        # a focusable explanation outside the graphic's role=img boundary.
        visible = (f'{kind} · {origin} · {purpose} · {provider} / {model} '
                   f'· {reasoning} · {catalog}'
                   + (f' · Fallback: {fallback}' if fallback != 'N/D' else ''))
        legend.append(
            f'<li tabindex="0" aria-label="{text(description)}" '
            f'data-explanation="{text(description)}">'
            '<span class="sw ' + tone + '" aria-hidden="true"></span>'
            f'<span class="stack-label">{text(label)}'
            f'<small class="stack-context">{text(visible)}</small></span>'
            f'<strong>{text(amount_label)}</strong><span>{percentage_label}</span></li>'
        )
        if detail:
            technical.append(f'<li><strong>{text(label)}</strong>: <code>{text(detail)}</code></li>')

    total_label = ((str(unit) + ' ') if unit else '') + format(total, '.10g').replace('.', ',')
    aria = f'{title}. Total {total_label}. ' + '; '.join(aria_parts)
    html = (
        f'<div class="stack-head"><strong>{text(title)}</strong><span>{text(total_label)}</span></div>'
        f'<div class="stack" role="img" aria-label="{text(aria)}">' + ''.join(spans) + '</div>'
        '<ul class="stack-legend">' + ''.join(legend) + '</ul>'
    )
    if note:
        html += f'<p class="rf">{text(note)}</p>'
    if technical:
        html += ('<details class="in"><summary>Ver IDs técnicos das tentativas</summary>'
                 '<ul class="stack-tech">' + ''.join(technical) + '</ul></details>')
    return html
