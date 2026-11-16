"""Self-contained structured previews over already-read audit SQLite evidence.

No navigation or runtime dependency on report-catalog. Each preview has local
modal details and an in-page link to the complete sanitized record inventory.
"""
from collections import defaultdict
from .components import table, text, technical_link
from .read_model import SEARCH_PAGE
from .sanitization import sanitize

# Known source-table projections. Fields describe SQLite columns, not technical
# HTML headings or row positions. Missing columns remain N/D, never synthesized.
STRUCTURED = {
    'index': (
        ('Estado funcional persistido', 'audit_fulfillment_work_items',
         (('component', 'Componente'), ('status', 'Estado'), ('required', 'Obrigatório')), 10, 'execution-evidence.html'),
    ),
    'extracao': (
        ('Identidade das capturas', 'page_snapshots',
         (('device', 'Dispositivo'), ('requested_url', 'URL solicitada'),
          ('final_url', 'URL final'), ('captured_at', 'Instante'),
          ('http_status', 'HTTP'), ('rendering_mode', 'Renderização'),
          ('preview_browser', 'Navegador observado'),
          ('preview_viewport', 'Área visível'),
          ('preview_runtime_count', 'Ocorrências do navegador'),
          ('preview_visual_ref', 'Referência da captura visual')), 4, 'index.html'),
    ),
    SEARCH_PAGE: (
        ('Cobertura observada de pesquisa', 'serp_observations',
         (('query', 'Consulta'), ('engine', 'Mecanismo'), ('requested_depth', 'Profundidade'),
          ('result_count', 'Resultados'), ('observation_status', 'Estado')), 8, 'cat-05.html'),
    ),
    'performance': (
        ('Escopos de desempenho observados', 'web_performance_observations',
         (('url', 'URL'), ('device', 'Dispositivo'), ('field_scope', 'Escopo de campo'),
          ('performance_score', 'Índice laboratório'), ('lcp_p75_ms', 'LCP campo p75 (ms)')), 8, 'cat-04.html'),
    ),
    'ia-custos': (
        ('Tentativas de IA persistidas', 'ai_provider_attempts',
         (('provider', 'Provedor'), ('model', 'Modelo'), ('status', 'Estado'),
          ('input_tokens', 'Tokens de entrada'), ('output_tokens', 'Tokens de saída')), 10, 'ai-integrations.html'),
    ),
    'seguranca': (
        ('Alcance passivo registrado', 'passive_security_runs',
         (('status', 'Estado'), ('pages_analyzed', 'Páginas'),
          ('resources_count', 'Recursos'), ('findings_count', 'Achados')), 10, 'cat-10.html'),
    ),
}

REFERENCES = {
    'indices': ('#presentation-records', 'Consultar regras e evidências nesta apresentação'),
    'descoberta': ('#presentation-records', 'Consultar registros do validador nesta apresentação'),
    'extracao': ('#capture-preview', 'Captura e prévia técnica local'),
    'ia-custos': ('#presentation-records', 'Consultar telemetria técnica nesta apresentação'),
}


def _capture_preview(row):
    """Read-only browser context from snapshot metadata, with explicit N/D.

    Does not open visual evidence or guess missing browser/runtime measurements.
    All original columns remain available in the local record inventory.
    """
    item = dict(row)
    metadata = item.get('browser_metadata')
    metadata = metadata if isinstance(metadata, dict) else {}
    browser = metadata.get('browser_identity')
    browser = browser if isinstance(browser, dict) else {}
    profile = metadata.get('profile')
    profile = profile if isinstance(profile, dict) else {}
    viewport = profile.get('viewport')
    viewport = viewport if isinstance(viewport, dict) else {}
    visual = metadata.get('visual_snapshot')
    visual = visual if isinstance(visual, dict) else {}
    width = viewport.get('width', visual.get('viewport_width'))
    height = viewport.get('height', visual.get('viewport_height'))
    runtime = metadata.get('runtime_diagnostics')
    runtime = runtime if isinstance(runtime, dict) else {}
    occurrences = runtime.get('items')
    item['preview_runtime_count'] = (
        len([event for event in occurrences if isinstance(event, dict)])
        if isinstance(occurrences, list) else 'N/D'
    )
    item['preview_viewport'] = (
        str(width) + ' x ' + str(height)
        if width is not None and height is not None else 'N/D'
    )
    channel = browser.get('channel') or 'Chrome'
    version = browser.get('browser_version') or metadata.get('browser_version')
    item['preview_browser'] = (
        str(channel) + ((' ' + str(version)) if version else '')
        if browser or version else 'N/D'
    )
    item['preview_visual_ref'] = metadata.get('visual_artifact_ref') or 'N/D'
    return item


def _runtime_rows(captures):
    """Project captured browser diagnostics locally; no extra analysis/API."""
    result = []
    known = {
        'CONSOLE_ERROR': 'Erro do console',
        'CONSOLE_WARNING': 'Alerta do console',
        'PAGE_ERROR': 'Erro de JavaScript',
        'REQUEST_FAILED': 'Requisição com falha',
        'HTTP_ERROR': 'Resposta HTTP com erro',
    }
    for capture in captures:
        meta = capture.get('browser_metadata')
        meta = meta if isinstance(meta, dict) else {}
        runtime = meta.get('runtime_diagnostics')
        runtime = runtime if isinstance(runtime, dict) else {}
        items = runtime.get('items')
        if not isinstance(items, list):
            continue
        for diagnostic in items:
            if not isinstance(diagnostic, dict):
                continue
            result.append({
                'device': capture.get('device'),
                'snapshot_id': capture.get('snapshot_id'),
                'type': known.get(str(diagnostic.get('type') or '').upper(),
                                  'Diagnóstico de navegador não classificado'),
                'message': diagnostic.get('message'),
                'url': diagnostic.get('url'),
                '_source_table': 'page_snapshots',
            })
    return result


def _verified_links(root, logical, audit_id):
    """Compatibility with older tests; external catalog links are prohibited."""
    return set()


def _capture_context_modal(tables, timezone_name):
    """Complete local capture overview in the existing offline dialog component.

    This is a visible action, not an anchor to a collapsed details element.
    It never accesses catalog HTML or changes persisted audit evidence.
    """
    fields = STRUCTURED['extracao'][0][2]
    captures = [_capture_preview(sanitize(row))
                for row in (tables or {}).get('page_snapshots', ())]
    # The modal is intentionally complete; the shorter inline preview is not.
    rows = [{key: capture.get(key) for key, _ in fields} for capture in captures]
    return (
        '<dialog class="detail-dialog" id="capture-context-modal" '
        'aria-labelledby="capture-context-modal-title">'
        '<div class="modal-head"><div>'
        '<span class="modal-kicker">Extração - evidências registradas</span>'
        '<h2 id="capture-context-modal-title">Captura e prévia técnica local</h2>'
        '</div><button type="button" class="modal-close" data-modal-close '
        'aria-label="Fechar detalhes">×</button></div>'
        '<div class="modal-body">'
        '<p class="rf">Registros de captura: ' + text(len(captures))
        + '. Os dados abaixo vêm da auditoria e não exigem o catálogo técnico. '
          'Ausência de medição permanece N/D.</p>'
        + table('Capturas persistidas na auditoria', rows, fields,
                timezone_name=timezone_name)
        + '<p><a class="tech-link" href="#capture-preview">'
          'Consultar a prévia da captura nesta página</a></p>'
        + '<p><a class="tech-link" href="#capture-counts">'
          'Consultar contagens derivadas da captura</a></p>'
        + '<p><a class="tech-link" href="#presentation-records">'
          'Consultar o inventário completo e anexos locais</a></p>'
        + '</div><div class="modal-foot">'
        '<span class="rf">Fonte: audit.db - somente leitura.</span>'
        '<button type="button" class="modal-dismiss" data-modal-close>Fechar</button>'
        '</div></dialog>'
    )


def catalog_context(root, logical, audit_id, tables=None, timezone_name=None):
    """Present persisted facts locally without inspecting or linking another report.

    Preview limits do not limit the full record inventory and JSON annexes.
    """
    sections = defaultdict(str)
    for page, specs in STRUCTURED.items():
        for title, source, fields, limit, _legacy_catalog_target in specs:
            rows = (tables or {}).get(source, ())
            if not rows and page != 'extracao':
                continue
            preview = [{**sanitize(row), '_source_table': source} for row in rows[:limit]]
            if page == 'extracao':
                preview = [_capture_preview(row) for row in preview]
            attrs = ' id="capture-preview"' if page == 'extracao' else ''
            sections[page] += (
                '<details' + attrs + '><summary>' + text(title) + '</summary>'
                + '<p class="rf">Fonte: registros persistidos na auditoria. '
                + text(len(preview)) + ' de ' + text(len(rows))
                + ' registros nesta prévia. Abra "Ver detalhes" para consultar '
                'cada registro, ou use o inventário local para todos os dados.</p>'
                + table(title, preview, fields, timezone_name=timezone_name)
                + '<p><a class="tech-link" href="#presentation-records">'
                  'Abrir inventário técnico completo nesta página</a></p>'
                + '</details>'
            )
    # The original technical capture link used to hide these facts in the
    # catalog. Include the browser's persisted diagnostic events here instead.
    capture_rows = [sanitize(row) for row in (tables or {}).get('page_snapshots', ())]
    runtime_rows = _runtime_rows(capture_rows)
    if runtime_rows:
        sections['extracao'] += (
            '<h2>Ocorrências registradas pelo navegador na captura</h2>'
            + '<p class="rf">Eventos observados por captura; não representam '
              'falhas universais nem medições adicionais.</p>'
            + table('Diagnósticos do navegador', runtime_rows,
                    [('device', 'Dispositivo'), ('snapshot_id', 'Captura'),
                     ('type', 'Tipo'), ('message', 'Descrição'),
                     ('url', 'Recurso / URL')], timezone_name=timezone_name)
        )
    else:
        sections['extracao'] += '<p class="rf">Nenhum diagnóstico de navegador disponível para as capturas persistidas.</p>'
    if audit_id:
        sections['rede'] += (
            '<p><button type="button" class="modal-open" data-modal="network-context-modal" '
            'aria-haspopup="dialog" aria-controls="network-context-modal">'
            'Consultar detalhes da medição de rede</button></p>'
        )
    else:
        sections['rede'] += '<p class="rf">Detalhes de rede indisponíveis: identidade da auditoria não comprovada.</p>'
    for page, (target, title) in REFERENCES.items():
        if page == 'extracao':
            # A hash link to a closed <details> looked inert in the offline
            # browser. Make the action explicit and independently testable.
            sections[page] += (
                '<p><button type="button" class="modal-open" '
                'data-modal="capture-context-modal" aria-haspopup="dialog" '
                'aria-controls="capture-context-modal">'
                + text(title) + '</button></p>'
                + _capture_context_modal(tables, timezone_name)
            )
        else:
            sections[page] += (
                '<p>' + technical_link(target, title)
                + ' <span class="rf">(conteúdo local, sem dependência de outro relatório)</span></p>'
            )
    return sections
