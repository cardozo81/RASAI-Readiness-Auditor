"""Shared public pt-BR translations of RASAi-owned rule titles.

Presentation only: do not mutate canonical rule titles or persisted audit data.
"""
from __future__ import annotations

# Rule ID -> (canonical English title, public pt-BR title).
_RULE_TITLE_PAIRS = {
    "BR-GEO-003": (
        "Sitemap resources must be acquired and interpreted when available",
        "Recursos de sitemap devem ser adquiridos e interpretados quando disponíveis",
    ),
    "BR-GEO-013": (
        "Canonical declarations must be interpretable and non-conflicting",
        "Declarações canonical devem ser interpretáveis e não conflitantes",
    ),
    "BR-GEO-017": (
        "robots.txt must be interpretable when present",
        "robots.txt deve ser interpretável quando presente",
    ),
}

RULE_TITLES_PT_BY_ID = {
    rule_id: translated for rule_id, (_, translated) in _RULE_TITLE_PAIRS.items()
}
RULE_TITLES_PT_BY_EN = {
    english: translated for english, translated in _RULE_TITLE_PAIRS.values()
}
