"""Optional catalog links and independent structured previews.

Never obtain material facts from report-catalog HTML. SQLite/authorized sidecars
are the source. Catalog package checks govern links only, not presentation facts.
"""
from collections import defaultdict
import json

from rasai.catalog_report_site import verify_catalog_report_package
from rasai.catalog_source_dependencies import verify_source_dependencies
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
    'indices': ('methodology', 'Método e versão das regras de pontuação'),
    'descoberta': ('cat-01', 'Ocorrências e detalhes do validador técnico'),
    'extracao': ('capture-context', 'Captura e prévia técnica local'),
    'ia-custos': ('metrics', 'Telemetria e intervalos técnicos persistidos'),
}


def _verified_links(root, logical, audit_id):
    """Return validated optional destinations, never a fact source."""
    directory = root / 'report-catalog'
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('audit_id') != audit_id
                or manifest.get('audit_snapshot', {}).get('source_logical_sha256') != logical
                or not verify_catalog_report_package(directory)[0]
                or not verify_source_dependencies(root, manifest.get('source_dependencies'))[0]):
            return set()
        return {item['path'] for item in manifest['packaged_files']
                if isinstance(item, dict) and isinstance(item.get('path'), str)}
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return set()


def catalog_context(root, logical, audit_id, tables=None):
    """Build the same material preview whether the catalog exists or not.

    A catalog is used *only* to determine availability of deep-dive hyperlinks.
    The already-verified, same-audit SQLite rows are passed explicitly by the
    presentation generator. Unknown families stay in the sanitized annex.
    """
    sections = defaultdict(str)
    available = _verified_links(root, logical, audit_id)
    for page, specs in STRUCTURED.items():
        for title, source, fields, limit, technical_target in specs:
            rows = (tables or {}).get(source, ())
            if not rows:
                continue
            preview = [{**sanitize(row), '_source_table': source} for row in rows[:limit]]
            sections[page] += ('<details><summary>' + text(title) + '</summary>'
                               + '<p class="rf">Origem: evidências registradas na auditoria · ' + str(len(preview)) + ' de ' + str(len(rows))
                               + ' registros; detalhe integral no inventário sanitizado.</p>'
                               + table(title, preview, fields)
                               + ('<p>' + technical_link('../report-catalog/' + technical_target,
                                                        'Abrir aprofundamento técnico opcional') + '</p>'
                                  if technical_target in available
                                  else '<p class="rf">Aprofundamento técnico não incluído ou não verificável neste pacote.</p>')
                               + '</details>')
    sections['rede'] += (
        '<p><button type="button" class="modal-open" data-modal="network-context-modal" '
        'aria-haspopup="dialog" aria-controls="network-context-modal">'
        'Consultar detalhes da medição de rede</button></p>'
    )
    for page, (stem, title) in REFERENCES.items():
        target = stem + '.html'
        if target in available:
            sections[page] += ('<p>' + technical_link('../report-catalog/' + target, title)
                               + ' <span class="rf">(aprofundamento opcional; requer o pacote técnico junto da apresentação)</span></p>')
        else:
            sections[page] += ('<p class="rf">Aprofundamento técnico opcional (' + text(title)
                               + ') indisponível neste pacote. A leitura executiva utiliza as fontes '
                               'persistidas, independentemente do HTML técnico.</p>')
    return sections
