"""Offline historical/consolidated reporting for RASAi.

This package is deliberately one-way: it reads completed AUD databases and
writes only its own rebuildable index and CONS snapshots.
"""
from pathlib import Path

from rasai.runtime_paths import runtime_directory

from . import index as _index


def _rasai_index_init(self: _index.ConsolidationIndex, audits_root: str | Path) -> None:
    self.audits_root = Path(audits_root)
    self.index_dir = runtime_directory(self.audits_root)
    self.path = self.index_dir / "consolidated-index.db"


# Preserve the public class while moving its default local cache to .rasai.
# Direct imports of rasai.consolidation.index also execute this package
# initializer first, so they receive the canonical path behavior as well.
_index.ConsolidationIndex.__init__ = _rasai_index_init

# Install CONS-only reporting enrichment before service-level function imports are
# bound. This keeps actionable remediation/rule references isolated from the audit
# provider/pricing pipeline, which may evolve independently.
from . import presentation as _presentation
from . import specialist as _specialist
from .consolidated_report_enrichment import install as _install_consolidated_report_enrichment

_install_consolidated_report_enrichment(_specialist, _presentation)

from .models import ConsolidationFilter, GenerationResult, RefreshResult
from .service import generate, normalize_filter

__all__ = ["ConsolidationFilter", "GenerationResult", "RefreshResult", "generate", "normalize_filter"]
