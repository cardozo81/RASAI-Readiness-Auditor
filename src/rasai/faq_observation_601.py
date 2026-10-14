"""Read-only, bounded interpretation of FAQ accordion visibility (#601).

This diagnostic never clicks links, modifies the DOM, runs JavaScript or changes
SARI. A collapsed, unmounted panel is not proof the publisher omitted an answer,
and a response available only after a click is not proved accessible to crawlers.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import sqlite3
from typing import Any

_FAQ_CONTEXT = re.compile(r"faq|frequent(?:ly)?asked|perguntas?frequentes?|questions?", re.I)
_MAX_HTML_BYTES = 4_000_000
_MAX_SNAPSHOTS = 12
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})
_NON_CONTENT_TAGS = frozenset({"script", "style", "template", "noscript"})


class _AccordionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.ids_with_dom_text: set[str] = set()
        self.controls: list[tuple[str, str]] = []
        self._open: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        props = dict(attrs)
        element_id = str(props.get("id") or "").strip()
        if element_id:
            self.ids.add(element_id)
        target = str(props.get("aria-controls") or "").strip()
        expanded = str(props.get("aria-expanded") or "").strip().lower()
        if target and expanded in {"true", "false"} and _FAQ_CONTEXT.search(target):
            self.controls.append((target, expanded))
        if tag not in _VOID_TAGS:
            self._open.append((tag, element_id))

    def handle_endtag(self, tag: str) -> None:
        # HTML can contain unbalanced nesting. Drop the nearest matching
        # frame and its descendants rather than attributing distant text
        # to a long-closed panel.
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index][0] == tag:
                del self._open[index:]
                break

    def handle_data(self, data: str) -> None:
        if not data.strip() or any(tag in _NON_CONTENT_TAGS for tag, _ in self._open):
            return
        for _tag, element_id in self._open:
            if element_id:
                self.ids_with_dom_text.add(element_id)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)


def inspect_faq_html(html: str) -> dict[str, int]:
    parser = _AccordionParser()
    parser.feed(html)
    # Count each target once, never multiply UI clones of the same control.
    controls = dict(parser.controls)
    collapsed = [target for target, expanded in controls.items() if expanded == "false"]
    return {
        "controls": len(controls),
        "collapsed": len(collapsed),
        "unmounted": sum(target not in parser.ids for target in collapsed),
        "mounted": sum(target in parser.ids for target in collapsed),
        "mounted_with_text": sum(target in parser.ids_with_dom_text for target in collapsed),
        "mounted_without_text": sum(
            target in parser.ids and target not in parser.ids_with_dom_text
            for target in collapsed
        ),
    }


def _safe_rendered_file(root: Path, ref: Any) -> Path | None:
    relative = str(ref or "").replace("\\", "/")
    if not relative.startswith("artifacts/rendered/"):
        return None
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return None
    if candidate.stat().st_size > _MAX_HTML_BYTES:
        return None
    return candidate


def faq_observation_html(database: Any, audit_id: str) -> str:
    """Only add a factually bounded, non-scoring CAT-03 diagnostic."""
    root = Path(database).parent
    try:
        with sqlite3.connect(database) as connection:
            rows = connection.execute(
                "SELECT s.rendered_artifact_ref FROM page_snapshots s "
                "JOIN pages p ON p.page_id=s.page_id "
                "WHERE p.audit_id=? ORDER BY s.snapshot_id LIMIT ?",
                (audit_id, _MAX_SNAPSHOTS),
            ).fetchall()
    except sqlite3.OperationalError:
        return ""
    observations = []
    for (ref,) in rows:
        try:
            rendered = _safe_rendered_file(root, ref)
            if rendered is None:
                continue
            counts = inspect_faq_html(rendered.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        if counts["controls"]:
            observations.append(counts)
    if not observations:
        return ""
    total = sum(item["controls"] for item in observations)
    collapsed = sum(item["collapsed"] for item in observations)
    unmounted = sum(item["unmounted"] for item in observations)
    mounted = sum(item["mounted"] for item in observations)
    mounted_with_text = sum(item["mounted_with_text"] for item in observations)
    mounted_without_text = sum(item["mounted_without_text"] for item in observations)
    return (
        "<div class='subsection' data-contract='FAQ-OBSERVATION-601-001'>"
        "<h3>FAQ interativo — limite da captura</h3>"
        f"<p>Foram identificados {total} controle(s) associados a FAQ, "
        f"{collapsed} recolhido(s); entre estes, {unmounted} painel(is) "
        f"não estavam presentes no DOM capturado e {mounted} tinham um alvo no DOM "
        f"({mounted_with_text} com texto recuperável no DOM e {mounted_without_text} sem texto recuperável).</p>"
        "<p class='muted'>A existência de texto em painel recolhido significa somente que ele "
        "estava no DOM desta captura; não comprova que fosse visível, indexado ou correto. "
        "A auditoria não abriu esses controles nesta observação. "
        "Painel não materializado não prova ausência editorial de resposta. "
        "Painel disponível após clique também não comprova acesso sem interação "
        "por robôs de busca. Esta leitura não altera BR-GEO-039, BR-GEO-049, "
        "SARI, evidências ou pontuações persistidas; os resultados semânticos "
        "devem ser interpretados à luz dessa limitação.</p></div>"
    )
