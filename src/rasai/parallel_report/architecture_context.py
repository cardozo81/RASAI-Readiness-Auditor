"""Decision-oriented architecture facts from the sealed AUD, independent of catalog HTML.

One compact overview per observed capture. Network IP/route details remain on
rede.html; browser events remain on extracao.html; no duplicate evidence dump.
"""
from pathlib import Path

from rasai.architecture_audit_facts import read_architecture_audit_facts
from .components import table, text
from .presentation_labels import public_value

_CLASS = {
    'CSR_SPA': 'SPA renderizada no cliente',
    'HYDRATED': 'Componentes hidratados',
    'MIXED': 'Arquitetura mista',
    'STATIC_OR_SSR': 'Estática ou renderizada no servidor',
    'UNKNOWN': 'Não determinada',
}


def architecture_context(root, audit_id, timezone_name):
    """Render observed classification and coverage, never infer from missing data."""
    title = '<h2>Arquitetura identificada na captura</h2>'
    if not audit_id:
        return title + '<p class="callout">Identidade da auditoria indisponível; arquitetura N/D.</p>'
    database = Path(root) / 'audit.db'
    if not database.is_file() or database.is_symlink():
        return title + '<p class="callout">Banco original indisponível; arquitetura N/D.</p>'
    facts = read_architecture_audit_facts(database, audit_id)
    if not facts:
        return title + '<p class="callout">Nenhuma classificação arquitetural verificável nesta AUD.</p>'

    rows = []
    unknown = 0
    for fact in facts:
        observed = fact.get('observed_architecture')
        label = _CLASS.get(observed, _CLASS['UNKNOWN'])
        if observed not in _CLASS or observed == 'UNKNOWN':
            unknown += 1
        hypothesis = fact.get('hypothesis')
        hypothesis = hypothesis if isinstance(hypothesis, dict) else {}
        candidate = hypothesis.get('candidate') if observed == 'UNKNOWN' else None
        candidate_label = (
            _CLASS.get(candidate, 'Classe não reconhecida')
            if isinstance(candidate, str) and candidate else None
        )
        net = fact.get('network_facts')
        net = net if isinstance(net, dict) else {}
        # A host, IP, ASN or route is not an architecture classification.
        # The network page already renders those details with their own proof.
        quality = fact.get('raw_signals_state')
        rows.append({
            'snapshot_id': fact.get('snapshot_id'),
            'device': fact.get('device'),
            'captured_at': public_value(fact.get('captured_at'), 'captured_at', timezone_name),
            'classification': label,
            'origin': 'Classificação M6 persistida' if observed != 'UNKNOWN' else 'Classificação não comprovada',
            'hypothesis': ('Hipótese não confirmada: ' + candidate_label) if candidate_label else 'N/D',
            'confidence': public_value(hypothesis.get('confidence'), 'confidence') if candidate_label else 'N/D',
            'raw_state': quality or 'N/D',
            'raw_verified': 'Sim' if fact.get('raw_verified_against_capture_digest') else 'Não verificado',
            'dom_resources': net.get('dom_count'),
            'script_observations': fact.get('runtime_script_resources_count'),
            'load_observations': net.get('response_count'),
            'capture_quality': fact.get('capture_quality'),
        })
    columns = [
        ('device','Dispositivo'), ('captured_at','Captura'),
        ('classification','Arquitetura observada'),
        ('origin','Origem da classificação'), ('hypothesis','Hipótese preliminar'),
        ('raw_verified','RAW íntegro'), ('dom_resources','Recursos declarados'),
        ('load_observations','Recursos observados na rede'),
    ]
    html = (
        title + '<p class="rf">Cada linha corresponde a uma captura persistida; '
        'classificação M6 e hipótese estrutural são informações diferentes. '
        'A hipótese não altera a classe observada nem o score. '
        'Recursos declarados no DOM não comprovam requisições nem topologia.</p>'
        + table('Arquitetura por captura', rows, columns, timezone_name=timezone_name)
    )
    if unknown:
        html += (
            '<p class="callout w">' + text(unknown)
            + ' captura(s) com arquitetura não determinada. '
            'Não concluir SPA, SSR ou arquitetura de infraestrutura '
            'a partir de hipótese, domínio, IP ou recurso de navegador.</p>'
        )
    html += (
        '<p class="rf">Rede, IP público, rastreamento e GeoIP — somente as '
        'medições verificadas — permanecem na '
        '<a class="tech-link" href="rede.html">página Rede e conectividade</a>. '
        'Os detalhes físicos originais permanecem no inventário desta '
        'apresentação, sem link para outro relatório.</p>'
    )
    return html
