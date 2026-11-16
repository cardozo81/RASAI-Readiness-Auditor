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
          ('final_url', 'URL final'), ('captured_at', 'Instante')), 4, 'index.html'),
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


def _verified_links(root, logical, audit_id):
    """Compatibility with older tests; external catalog links are prohibited."""
    return set()


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
    if audit_id:
        sections['rede'] += (
            '<p><button type="button" class="modal-open" data-modal="network-context-modal" '
            'aria-haspopup="dialog" aria-controls="network-context-modal">'
            'Consultar detalhes da medição de rede</button></p>'
        )
    else:
        sections['rede'] += '<p class="rf">Detalhes de rede indisponíveis: identidade da auditoria não comprovada.</p>'
    for page, (target, title) in REFERENCES.items():
        sections[page] += (
            '<p>' + technical_link(target, title)
            + ' <span class="rf">(conteúdo local, sem dependência de outro relatório)</span></p>'
        )
    return sections
