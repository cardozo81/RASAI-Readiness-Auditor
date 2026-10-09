"""Read-only, advisory identification of extraction dominated by navigation chrome.

This does not reclassify M4, change a captured snapshot, or alter scoring.
Only additive diagnostic metadata is persisted alongside the original artifacts.
"""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
from html.parser import HTMLParser
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


class _RenderedMainProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_count = 0
        self.main_depth = 0
        self.main_text_characters = 0
        self.h1_count = 0
        self.h1_depth = 0
        self.h1_text_characters = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"main", "article"}:
            self.main_count += 1
            self.main_depth += 1
        if tag == "h1":
            self.h1_count += 1
            self.h1_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"main", "article"} and self.main_depth:
            self.main_depth -= 1
        if tag == "h1" and self.h1_depth:
            self.h1_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.main_depth:
            self.main_text_characters += len(data.strip())
        if self.h1_depth:
            self.h1_text_characters += len(data.strip())


def _rendered_materiality(root: Path, path: Path) -> dict | None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 6_000_000:
        return None
    raw = path.read_bytes()
    probe = _RenderedMainProbe()
    probe.feed(raw.decode("utf-8", errors="replace"))
    probe.close()
    return {
        "rendered_html_ref": path.relative_to(root).as_posix(),
        "rendered_html_sha256": sha256(raw).hexdigest(),
        "main_element_count": probe.main_count,
        "main_text_characters": probe.main_text_characters,
        "h1_element_count": probe.h1_count,
        "h1_text_characters": probe.h1_text_characters,
        "main_empty_in_captured_html": bool(probe.main_count and not probe.main_text_characters),
        "limitation": (
            "Captured serialized HTML may not match screenshot timing, iframe "
            "or shadow-DOM content. Visual correspondence requires separate validation."
        ),
    }


def inspect_workspace_extractions(root: Path) -> list[dict]:
    """Inspect only M4 text files, without editing or deleting source artifacts."""
    extraction = Path(root) / "artifacts" / "extraction"
    if not extraction.is_dir():
        return []
    output = []
    rendered_root = Path(root) / "artifacts" / "rendered"
    rendered_by_snapshot = {
        candidate.stem: candidate
        for candidate in sorted(rendered_root.rglob("SNP-*.html"))[:1000]
        if candidate.is_file() and not candidate.is_symlink()
    } if rendered_root.is_dir() else {}
    visual_root = Path(root) / "artifacts" / "visual"
    visual_by_snapshot = {
        candidate.stem: candidate
        for candidate in sorted(visual_root.rglob("SNP-*.png"))[:1000]
        if candidate.is_file() and not candidate.is_symlink()
    } if visual_root.is_dir() else {}
    for artifact in sorted(extraction.rglob("main_content.txt"))[:1000]:
        if artifact.is_symlink() or not artifact.is_file():
            continue
        if artifact.stat().st_size > 2_000_000:
            continue
        text = artifact.read_text(encoding="utf-8", errors="replace")
        result = classify_extracted_text(text)
        rendered = rendered_by_snapshot.get(artifact.parent.name)
        materiality = _rendered_materiality(root, rendered) if rendered is not None else None
        if result["state"] in {"NAVIGATION_DOMINATED_SUSPECTED", "NO_EXTRACTED_TEXT"} or (
            materiality and materiality["main_empty_in_captured_html"]
        ):
            visual_path = visual_by_snapshot.get(artifact.parent.name)
            visual = None
            if visual_path is not None and visual_path.stat().st_size <= 10_000_000:
                visual = {
                    "screenshot_ref": visual_path.relative_to(root).as_posix(),
                    "screenshot_sha256": sha256(visual_path.read_bytes()).hexdigest(),
                    "interpretation": (
                        "Same SNP image exists; image content was not OCR-verified "
                        "or assumed indexable."
                    ),
                }
            output.append({
                "artifact_ref": artifact.relative_to(root).as_posix(),
                **result,
                "rendered_dom": materiality,
                "visual": visual,
            })
    return output


def materialize_extraction_quality(root: Path) -> str | None:
    """Add one stable advisory file, without changing M4 persistence or score."""
    if not (Path(root) / "artifacts" / "extraction").is_dir():
        return None
    findings = inspect_workspace_extractions(root)
    destination = Path(root) / "artifacts" / "geo-extraction-quality.json"
    payload = json.dumps({
        "contract_version": "GEO-EXTRACTION-QUALITY-1",
        "observations": findings,
        "source": "PERSISTED_M4_EXTRACTION_TEXT",
        "scoring_effect": "NONE",
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination.write_text(payload, encoding="utf-8")
    return destination.relative_to(root).as_posix()
