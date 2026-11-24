"""Source-by-page evidence receipts for every offline presentation HTML.

This is NOT a claim of analytical completeness. It only inventories rows and
validated network sidecars already available at publication time. No catalog
HTML, API, collectors, AI, score recalculation, or source mutation.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rasai.network_active_probe import read_authorized_probes
from rasai.network_observation import snapshots_from_audit
from rasai.network_observation_store import read_network_observations, sidecar_path

from .components import text
from .read_model import PAGES, destination, SEARCH_PAGE

# Human meaning is deliberately narrower than the family names.
# An observed browser resource does not prove a security finding.
GROUPS = {
    'index': (
        ('Identidade e alvo', ('audits', 'audit_targets')),
        ('Requisitos de execução', ('audit_fulfillment_work_items', 'audit_fulfillment_contracts')),
        ('Índices registrados', ('scores',)),
        ('Projeções operacionais da interface de auditoria', ('console_execution_projections',)),
    ),
    'extracao': (
        ('Capturas persistidas', ('page_snapshots',)),
        ('Evidências físicas e elementos', ('evidence', 'element_observations',
                                        'finding_element_observations')),
    ),
    'descoberta': (
        ('Diagnósticos de descoberta', ('m24_diagnostics',)),
        ('Métricas e validações de padrões', ('standards_metric_observations',
                                           'standards_service_runs')),
    ),
    'indices': (
        ('Índices e dimensões', ('scores',)),
        ('Regras e contribuições', ('rule_executions', 'score_contributions')),
    ),
    'conteudo': (
        ('Contexto editorial/semântico', ('content_analysis_contexts',
                                       'property_semantic_contexts')),
        ('Coerência semântica medida', ('semantic_coherence_assessments',)),
        ('Achados persistidos', ('findings', 'improvement_intelligence_findings')),
        ('Entidades observadas', ('entity_observations',)),
        ('Sugestões estruturadas não aprovadas', ('jsonld_remediation_suggestions',)),
    ),
    'performance': (
        ('Laboratório e campo', ('web_performance_observations',)),
        ('Navegação sintética', ('synthetic_apdex_summaries',)),
        ('Experiência sintética', ('synthetic_ux_apdex_summaries',
                                 'synthetic_ux_apdex_error_details')),
    ),
    SEARCH_PAGE: (
        ('SERP e resultados classificados', ('serp_observations',
                                            'serp_competitive_results')),
        ('Projeção GEO persistida', ('geo_observation_runs',)),
        ('Pesquisa externa persistida', ('perplexity_search_runs',)),
    ),
    'seguranca': (
        ('Execuções da análise passiva', ('passive_security_runs',)),
        ('Achados da análise passiva', ('passive_security_findings',)),
        ('Recursos observados na captura (não são vulnerabilidades)',
         ('passive_security_resources',)),
        ('Integrações técnicas observadas (não são achados)',
         ('passive_security_integrations',)),
    ),
    'plano': (
        ('Análise direcionada', ('directed_analysis_runs',
                               'directed_analysis_actions')),
        ('Decisões de governança', ('recommendation_governance',)),
        ('Recomendações consultivas', ('improvement_intelligence_recommendations',)),
        ('Textos propostos', ('content_remediation_suggestions',)),
    ),
    'ia-custos': (
        ('Tentativas de IA', ('ai_provider_attempts', 'content_remediation_attempts')),
        ('Proveniência das chamadas', ('ai_tasks', 'ai_exchange_log')),
        ('Resultado da previsão financeira persistida',
         ('console_cost_forecast_outcomes',)),
    ),
}


def _network_counts(root: Path, audit_id: str | None):
    if not audit_id:
        return {'passive': 0, 'probes': 0, 'sidecar_invalid': False}
    packet = sidecar_path(root)
    present = packet.exists() or packet.is_symlink()
    passive = read_network_observations(root, audit_id)
    if not passive and not present:
        db = root / 'audit.db'
        if db.is_file() and not db.is_symlink():
            try:
                passive = snapshots_from_audit(db, audit_id)
            except (OSError, ValueError, TypeError):
                passive = []
    return {
        'passive': len(passive),
        'probes': len(read_authorized_probes(root, audit_id)),
        'sidecar_invalid': bool(present and not passive),
    }


def build_coverage(root: Path, audit_id: str | None, tables: dict):
    """Return text-only coverage by page and one sanitized numeric JSON receipt.

    Missing rows are not represented as zero measured issues, verified absence,
    unrequested work, or proof that any collector completed successfully.
    """
    root = Path(root)
    rows = {name: len(entries) for name, entries in tables.items()}
    routed = defaultdict(dict)
    for name, count in rows.items():
        page = destination(name)
        if page is not None:
            routed[page][name] = count

    network = _network_counts(root, audit_id)
    record = {
        'contract': 'RASAI-PRESENTATION-EVIDENCE-COVERAGE-001',
        'audit_id': audit_id,
        'measurement': 'PERSISTED_ROWS_AND_VERIFIED_SIDECARS_ONLY',
        'certifies_editorial_completeness': False,
        'pages': {},
        'non_routed': {name: count for name, count in sorted(rows.items())
                       if destination(name) is None and count > 0},
    }
    rendered = {}
    # Every page, including a page with no data, must explain the available
    # and missing evidence without repeating the canonical row inventories.
    for page, _ in PAGES:
        topics = []
        accounted = set()
        if page == 'rede':
            topics.extend([
                ('Capturas passivas de rede verificadas', network['passive'], 'validated_network'),
                ('Sondas complementares verificadas', network['probes'], 'validated_network'),
            ])
        for label, source_names in GROUPS.get(page, ()):
            quantity = sum(rows.get(name, 0) for name in source_names)
            accounted.update(source_names)
            topics.append((label, quantity, 'audit_db'))
        if page == 'seguranca':
            resource_count = sum(number for name, number in routed[page].items()
                                 if name.startswith('passive_security_')
                                 and name not in accounted)
            if resource_count:
                topics.append(('Demais registros técnicos de segurança (não são achados)',
                               resource_count, 'audit_db'))
            accounted.update(n for n in routed[page] if n.startswith('passive_security_'))
        remainder = sum(number for name, number in routed[page].items()
                        if name not in accounted)
        if remainder:
            topics.append(('Demais registros técnicos locais', remainder, 'audit_db'))
        nonzero = sum(quantity > 0 for _, quantity, _ in topics)
        evidence_state = ('COM_REGISTROS_PERSISTIDOS' if nonzero
                          else 'SEM_REGISTROS_NAS_FONTES_DESTA_PAGINA')
        record['pages'][page + '.html'] = {
            'evidence_state': evidence_state,
            'sources': [{'label': label, 'records': number, 'source': source}
                        for label, number, source in topics],
            'sqlite_record_count': sum(routed[page].values()),
            'verified_network_observations': network['passive'] if page == 'rede' else None,
            'verified_network_probes': network['probes'] if page == 'rede' else None,
        }
        cards = ''.join(
            '<div><dt>' + text(label) + '</dt><dd>' + text(number)
            + (' <small>registro(s)</small>' if source == 'audit_db'
               else ' <small>observação(ões) verificada(s)</small>')
            + '</dd></div>'
            for label, number, source in topics
        )
        body = (
            '<section class="evidence-coverage" data-evidence-page="' + text(page) + '">'
            '<h2>Evidências materializadas nesta página</h2>'
            '<dl class="kv">' + cards + '</dl>'
        )
        if not nonzero:
            body += (
                '<p class="callout w">Nenhum registro verificável encontrado '
                'nas fontes desta página. Esta condição não comprova que '
                'a atividade tenha sido executada com resultado negativo. '
                'Consulte o estado operacional da auditoria.</p>'
            )
        if page == 'seguranca':
            body += (
                '<p class="rf">Os recursos e integrações capturados não constituem '
                'uma execução da análise de segurança passiva, não são vulnerabilidades '
                'e não substituem os achados formalmente registrados.</p>'
            )
        if page == 'rede' and network['sidecar_invalid']:
            body += (
                '<p class="callout w">Pacote passivo presente, porém não validado. '
                'Não foram projetados valores não verificáveis desse pacote.</p>'
            )
        body += (
            '<p><a class="tech-link" href="#presentation-records">'
            'Consultar inventário técnico próprio desta página</a></p></section>'
        )
        rendered[page + ':coverage'] = body
    return rendered, record
