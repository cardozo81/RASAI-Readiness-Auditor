"""Immutable normalized model; routing never invokes a producer."""
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from .sanitization import sanitize

# The requested export filename combines two topic names, not a product brand.
# Keep its components explicit; the product namespace remains RASAi.
SEARCH_PAGE_PARTS = ('search', 'geo')
SEARCH_PAGE = '-'.join(SEARCH_PAGE_PARTS)

PAGES = (
    ('index', 'Painel'), ('extracao', 'Extração'), ('descoberta', 'Descoberta e padrões'),
    ('indices', 'Índices'), ('conteudo', 'Conteúdo e acessibilidade'),
    ('performance', 'Performance e experiência'), (SEARCH_PAGE, 'Search e GEO'),
    ('seguranca', 'Segurança passiva'), ('plano', 'Plano de ação'), ('ia-custos', 'IA, custos e proveniência'),
)


def destination(table):
    if table in {'scores', 'score_contributions', 'rule_executions'}:
        return 'indices'
    if table.startswith(('passive_security',)):
        return 'seguranca'
    if table.startswith(('serp_', 'geo_', 'perplexity_')):
        return SEARCH_PAGE
    if table.startswith(('web_performance', 'lighthouse_', 'synthetic_')):
        return 'performance'
    if table.startswith(('m24_', 'standards_')):
        return 'descoberta'
    if table.startswith(('directed_analysis', 'recommendation', 'remediation', 'root_cause', 'request_remediation')):
        return 'plano'
    if table in {'pages', 'page_snapshots', 'evidence', 'element_observations', 'finding_element_observations'}:
        return 'extracao'
    if table.startswith(('content_remediation_', 'ai_', 'provider_', 'console_cost_')):
        return 'ia-custos'
    if table.startswith(('semantic_', 'content_', 'property_', 'entity_', 'jsonld_', 'improvement_')) or table == 'findings':
        return 'conteudo'
    if table.startswith('audit'):
        return 'index'
    return 'ia-custos'  # explicitly inventoried supplemental persisted family


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class Record:
    table: str
    anchor: str
    identity: tuple
    data: object

    @property
    def href(self):
        return destination(self.table) + '.html#' + self.anchor


def build(tables, schema):
    records = []
    for table, rows in sorted(tables.items()):
        for ordinal, row in enumerate(rows):
            keys = schema[table]['primary_key']
            identity = tuple((key, row.get(key)) for key in keys)
            seed = json.dumps([table, identity if identity else ordinal], default=str, sort_keys=True)
            anchor = 'record-' + sha256(seed.encode()).hexdigest()[:24]
            records.append(Record(table, anchor, identity, freeze(sanitize(row))))
    return tuple(records)
