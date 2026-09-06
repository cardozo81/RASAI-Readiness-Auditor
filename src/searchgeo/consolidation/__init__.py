"""Offline historical/consolidated reporting for SearchGEO.

This package is deliberately one-way: it reads completed AUD databases and
writes only its own rebuildable index and CONS snapshots.
"""
from .models import ConsolidationFilter, GenerationResult, RefreshResult
from .service import generate, normalize_filter

__all__ = ["ConsolidationFilter", "GenerationResult", "RefreshResult", "generate", "normalize_filter"]
