"""#334: focused, zero-provider responsive Directed Analysis roadmap tests."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re

from rasai.directed_analysis_reporting import _roadmap_phase_cards
from rasai.catalog_report_style import _CSS


class PhaseDom(HTMLParser):
    def __init__(self):
        super().__init__()
        self.triggers: list[str] = []
        self.modals: list[str] = []
        self.detail_count = 0

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "button" and "data-modal-open" in props:
            self.triggers.append(props["data-modal-open"])
        if tag == "dialog" and props.get("id", "").startswith("directed-roadmap-phase-"):
            self.modals.append(props["id"])
        if tag == "details" and "directed-roadmap-group" in props.get("class", ""):
            self.detail_count += 1


def _action(action_id, title, *, ref=None):
    action = {"action_id": action_id, "title": title}
    if ref:
        action["evidence_refs_json"] = [
            {"href": ref, "catalog_id": "CAT-10", "section_id": "evidence"}
        ]
    return action


def test_six_phases_have_one_button_and_one_modal_each_with_order_preserved():
    actions = {f"A-{n}": _action(f"A-{n}", f"Ação {n}") for n in range(1, 7)}
    roadmap = [
        {"phase": f"Fase {i}", "objective": f"Objetivo exclusivo {i}",
         "action_ids": [f"A-{i}"]}
        for i in range(1, 7)
    ]
    html = _roadmap_phase_cards(roadmap, actions, {})
    parsed = PhaseDom()
    parsed.feed(html)
    assert len(parsed.triggers) == 6
    assert len(parsed.modals) == 6
    assert len(set(parsed.modals)) == 6
    assert parsed.triggers == parsed.modals
    assert parsed.detail_count == 6
    assert html.count("class='card directed-roadmap-card'") == 6
    assert "<table" not in html  # phase summaries never contain squeezed tables
    for i in range(1, 6):
        assert html.index(f"<h3>Fase {i}</h3>") < html.index(f"<h3>Fase {i+1}</h3>")


def test_repeated_titles_preserve_distinct_occurrences_and_exact_targets():
    actions = {
        "K1": _action("K1", "Cookie sem HttpOnly", ref="cat-10.html#e-1"),
        "K2": _action("K2", "Cookie sem HttpOnly", ref="cat-10.html#e-2"),
        "J3": _action("J3", "Recurso sem SRI"),
    }
    targets = {
        "K1": {"label": "Set-Cookie #1 · SESSIONID", "note": "Cookie de sessão"},
        "K2": {"label": "Set-Cookie #2 · AUTHID", "note": "Outro cookie"},
        "J3": {"label": "https://cdn.example.test/a.js?v=1"},
    }
    html = _roadmap_phase_cards([
        {"phase": "Fase 1", "objective": "Mitigar riscos",
         "action_ids": ["K1", "K2", "J3", "K1", "MISSING"]},
    ], actions, targets)
    assert "2 ação(ões) temática(s)" in html
    assert "3 ocorrência(s) vinculada(s)" in html
    assert "Cookie sem HttpOnly · 2 ocorrência(s)" in html
    assert html.count("Alvo / ocorrência:") == 3
    assert html.count("Set-Cookie #1 · SESSIONID") == 1
    assert html.count("Set-Cookie #2 · AUTHID") == 1
    assert "https://cdn.example.test/a.js?v=1" in html
    assert "cat-10.html#e-1" in html
    assert "cat-10.html#e-2" in html
    assert "Ações estratégicas" in html
    assert "Nenhuma ação persistida" not in html


def test_empty_phase_and_invalid_roadmap_abstain_without_inventing_targets():
    actions = {"ID1": _action("ID1", "A")}
    html = _roadmap_phase_cards([
        {"phase": "Fase pendente", "objective": "Não observada", "action_ids": ["NOT-FOUND"]},
        "non-object",
        {"phase": "Fase sem lista", "action_ids": "ID1"},
    ], actions, {})
    dom = PhaseDom()
    dom.feed(html)
    assert len(dom.triggers) == 2
    assert len(dom.modals) == 2
    assert html.count("Nenhuma ação persistida está vinculada") == 2
    assert "0 ocorrência(s)" in html
    assert "ID1" not in html
    empty = _roadmap_phase_cards([], actions, {})
    assert "Ordem estratégica não materializada" in empty
    assert "data-modal-open" not in empty
    assert "Ordem estratégica não materializada" in _roadmap_phase_cards(None, actions, {})


def test_untrusted_phase_action_and_target_text_are_escaped():
    html = _roadmap_phase_cards(
        [{"phase": "<script>alert(1)</script>",
          "objective": "<img src=x onerror=alert(2)>",
          "action_ids": ["X"]}],
        {"X": _action("X", "<svg onload=alert(3)>")},
        {"X": {"label": "<iframe src=evil>", "note": "<b>unchecked</b>"}},
    )
    for attack in ("<script>", "<img", "<svg", "<iframe", "<b>unchecked</b>"):
        assert attack not in html
    for safe in ("&lt;script&gt;", "&lt;img", "&lt;svg", "&lt;iframe", "&lt;b&gt;"):
        assert safe in html
    assert "directed-roadmap-phase-1-" in html


def test_css_is_scoped_two_column_stacks_and_print_exposes_full_list():
    assert ".directed-roadmap-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in _CSS
    assert "@media(max-width:1000px){.directed-roadmap-grid{grid-template-columns:minmax(0,1fr)}}" in _CSS
    assert "#roadmap .directed-roadmap-grid{display:none!important}" in _CSS
    assert "dialog.rasai-modal[id^='directed-roadmap-phase-']{display:block!important" in _CSS
    assert "details:not([open])>.detail-body{display:block!important}" in _CSS
    # No broad override of global .grid or the original modal JS.
    assert ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))" in _CSS
