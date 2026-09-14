"""Offline historical/consolidated reporting for RASAi.

This package is deliberately one-way: it reads completed AUD databases and
writes only its own rebuildable index and CONS snapshots.
"""
from pathlib import Path

from rasai.runtime_paths import runtime_directory
from rasai.report_reader_experience import enhance_consolidated_experience

from . import index as _index


def _rasai_index_init(self: _index.ConsolidationIndex, audits_root: str | Path) -> None:
    self.audits_root = Path(audits_root)
    self.index_dir = runtime_directory(self.audits_root)
    self.path = self.index_dir / "consolidated-index.db"


# Preserve the public class while moving its default local cache to .rasai.
# Direct imports of rasai.consolidation.index also execute this package
# initializer first, so they receive the canonical path behavior as well.
_index.ConsolidationIndex.__init__ = _rasai_index_init

# Keep the consolidated renderer on the current public scoring vocabulary. The
# TECHNICAL_ACCESSIBILITY key is read-only compatibility for persisted development
# artifacts; new producers persist DISCOVERY_ACCESS.
from . import reporting as _reporting

_reporting._DIMENSIONS.update(
    {
        "DISCOVERY_ACCESS": "Acesso e descoberta",
        "TECHNICAL_ACCESSIBILITY": "Acesso e descoberta",
        "INDEXABILITY": "Capacidade de indexação",
        "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
        "SEMANTIC_STRUCTURE": "Estrutura semântica",
        "ENTITY_CLARITY": "Clareza de entidades",
        "STRUCTURED_DATA": "Dados estruturados",
        "ANSWERABILITY": "Capacidade de resposta",
        "CITATION_READINESS": "Preparação para citação",
        "EVIDENCE_TRUST": "Evidências e confiabilidade",
        "INTENT_COVERAGE": "Cobertura de intenções",
        "CONTENT_VALUE": "Valor do conteúdo",
    }
)

# Install CONS-only reporting enrichment before service-level function imports are
# bound. This keeps actionable remediation/rule references isolated from the audit
# provider/pricing pipeline, which may evolve independently.
from . import presentation as _presentation
from . import specialist as _specialist
from .consolidated_report_enrichment import install as _install_consolidated_report_enrichment

_install_consolidated_report_enrichment(_specialist, _presentation)

# Last-mile consolidated UX: presentation only. It consumes the already materialized
# CONS artifact and never changes historical calculations, eligibility or evidence.
_refine_html_before_reader_experience = _presentation.refine_html


def _refine_html_with_reader_experience(html: str, artifact=None) -> str:
    rendered = _refine_html_before_reader_experience(html, artifact)
    return enhance_consolidated_experience(rendered, artifact)


_presentation.refine_html = _refine_html_with_reader_experience

from .models import ConsolidationFilter, GenerationResult, RefreshResult
from .service import generate, normalize_filter

__all__ = ["ConsolidationFilter", "GenerationResult", "RefreshResult", "generate", "normalize_filter"]
