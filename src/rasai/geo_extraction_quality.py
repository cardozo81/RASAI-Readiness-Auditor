"""Read-only, advisory identification of extraction dominated by navigation chrome.

This does not reclassify M4, change a captured snapshot, or alter scoring.
Only additive diagnostic metadata is persisted alongside the original artifacts.
"""
from __future__ import annotations

from pathlib import Path
import json
import re


_NAVIGATION_WORDS = frozenset({
    "produtos", "menu", "buscar", "pesquisar", "atendimento", "acessibilidade",
    "entrar", "login", "contato", "início", "inicio", "home", "dental",
    "residencial", "vida", "viagem", "capitalização", "capitalizacao",
})


def classify_extracted_text(text: str) -> dict:
    """Conservative signal: short text mostly consisting of navigation labels."""
    words = re.findall(r"[^\W_]+", text.casefold(), re.UNICODE)
    unique = set(words)
    nav_hits = sum(word in _NAVIGATION_WORDS for word in words)
    fraction = round(nav_hits / len(words), 3) if words else 0
    short = len(words) <= 35
    shell = bool(words and short and fraction >= 0.65 and len(unique) <= 25)
    return {
        "state": "NAVIGATION_DOMINATED_SUSPECTED" if shell else (
            "NO_EXTRACTED_TEXT" if not words else "NOT_FLAGGED"
        ),
        "word_count": len(words),
        "navigation_ratio": fraction,
        "classification": "HEURISTIC_ADVISORY_ONLY",
        "limitation": "Does not prove missing DOM or crawler failure; original extraction is immutable.",
    }


def inspect_workspace_extractions(root: Path) -> list[dict]:
    """Inspect only M4 text files, without editing or deleting source artifacts."""
    extraction = Path(root) / "artifacts" / "extraction"
    if not extraction.is_dir():
        return []
    output = []
    for artifact in sorted(extraction.rglob("main_content.txt"))[:1000]:
        if artifact.is_symlink() or not artifact.is_file():
            continue
        if artifact.stat().st_size > 2_000_000:
            continue
        text = artifact.read_text(encoding="utf-8", errors="replace")
        result = classify_extracted_text(text)
        if result["state"] in {"NAVIGATION_DOMINATED_SUSPECTED", "NO_EXTRACTED_TEXT"}:
            output.append({
                "artifact_ref": artifact.relative_to(root).as_posix(),
                **result,
            })
    return output


def materialize_extraction_quality(root: Path) -> str | None:
    """Add one stable advisory file, without changing M4 persistence or score."""
    findings = inspect_workspace_extractions(root)
    if not findings:
        return None
    destination = Path(root) / "artifacts" / "geo-extraction-quality.json"
    payload = json.dumps({
        "contract_version": "GEO-EXTRACTION-QUALITY-1",
        "observations": findings,
        "source": "PERSISTED_M4_EXTRACTION_TEXT",
        "scoring_effect": "NONE",
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination.write_text(payload, encoding="utf-8")
    return destination.relative_to(root).as_posix()
