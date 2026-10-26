"""Read-only pt-BR humanization only for known RASAi-owned legacy GEO copy.

Preserved snapshots, user text, search results, URLs and trace identifiers never
change. Do not add a generic accent correction algorithm to an evidence surface.
"""
from __future__ import annotations

_GEO_OLD = {
    "Preservar fatos verificaveis e acompanhar a mesma consulta em novas observacoes.": "Preservar fatos verificáveis e acompanhar a mesma consulta em novas observações.",
    "Investigar a relacao entre a URL auditada e as URLs alternativas do dominio; nao presumir problema de canonical.": "Investigar a relação entre a URL auditada e as URLs alternativas do domínio; não presumir problema de canonicalização.",
    "Revisar cobertura da intencao, clareza da oferta e evidencias no CAT-03 antes de propor remediacao.": "Revisar a cobertura da intenção, a clareza da oferta e as evidências no CAT-03 antes de propor remediação.",
}

def public_geo_action(value: object) -> str:
    raw = str(value or "")
    return _GEO_OLD.get(raw, raw)
