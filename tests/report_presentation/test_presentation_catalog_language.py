"""Only the independent report-presentation humanizes internal CAT-## references.

Technical identifiers, catalog HTML, persisted audit facts, model names, URLs,
anchors and raw annexes remain literal, so provenance stays checkable.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
import sqlite3

from rasai.parallel_report.artifact_reader import inventory
from rasai.parallel_report.generator import generate
from rasai.report_presentation import humanize_module_references_html

from test_parallel_report import fixture


class EditorialText(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.stack = []
        self.visible = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            idx = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:idx]

    def handle_data(self, text):
        if not any(tag in self.stack for tag in
                   ("pre", "code", "script", "style", "blockquote", "samp", "textarea")):
            self.visible.append(text)


def test_presentation_replaces_every_known_catalog_reference_in_editorial_prose():
    html = "".join(
        f"<p>Consultar CAT-{i:02d} para a auditoria.</p>"
        for i in range(1, 11)
    ) + (
        "<p>Revisar CAT-03/CAT-05 antes do plano.</p>"
        "<p>Revisar CAT-03/05 nos critérios de execução.</p>"
        "<p>Verificar CAT-01 e CAT-07.</p>"
        "<p>CAT-03 não equivale a CAT-05.</p>"
        "<p>CAT-03. CAT-04, CAT-05: três áreas distintas.</p>"
    )
    once = humanize_module_references_html(html)
    assert "conteúdo, semântica e dados estruturados" in once
    assert "inteligência de busca e IA" in once
    assert "Apdex de experiência" in once
    assert "fundamentos técnicos e descoberta" in once
    assert "segurança passiva" in once
    assert not re.search(r"\bCAT-(?:0[1-9]|10)\b", once)
    assert humanize_module_references_html(once) == once


def test_presentation_keeps_technical_contract_literals_and_external_identifiers():
    html = (
        "<p>Contrato CAT-03 registrado; CAT-09: remediações.</p>"
        "<a href='cat-03.html' data-catalog='CAT-05'>Consultar CAT-03</a>"
        "<pre>{\"catalog_id\": \"CAT-03\", \"contract\": \"CAT-05\"}</pre>"
        "<code>CAT-06</code>"
        "<blockquote>O texto da página cita CAT-07.</blockquote>"
        "<span>Produto CAT-04-XYZ. Modelo CAT-05.html</span>"
        "&lt;section data-contract=&quot;CAT-08&quot;&gt;CAT-08&lt;/section&gt;"
        "<span>CAT-99 é uma referência desconhecida.</span>"
    )
    readable = humanize_module_references_html(html)
    assert "Critério de avaliação de conteúdo, semântica e dados estruturados registrado" in readable
    assert "href='cat-03.html' data-catalog='CAT-05'" in readable
    assert "<pre>{\"catalog_id\": \"CAT-03\", \"contract\": \"CAT-05\"}</pre>" in readable
    assert "<code>CAT-06</code>" in readable
    assert "<blockquote>O texto da página cita CAT-07.</blockquote>" in readable
    assert "Produto CAT-04-XYZ. Modelo CAT-05.html" in readable
    assert "&lt;section data-contract=&quot;CAT-08&quot;&gt;CAT-08&lt;/section&gt;" in readable
    assert "CAT-99 é uma referência desconhecida" in readable


def test_new_independent_presentation_plan_hides_catalog_ids_without_source_changes(tmp_path):
    root = fixture(tmp_path / "audit")
    database = root / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE directed_analysis_actions SET title=?, validation_steps_json=? "
            "WHERE action_id='action-1'",
            (
                "Revisar CAT-03 e CAT-05 na mesma auditoria",
                '["Confirmar CAT-01 antes de CAT-09"]',
            ),
        )
        connection.execute(
            "UPDATE findings SET title=? WHERE finding_id='finding-1'",
            ("Achado associado a CAT-07",),
        )
    before = inventory(root)

    # report-catalog is an independent visual projection and must remain untouched.
    original_catalog = root / "report-catalog" / "index.html"
    original_catalog.write_text("<p>CAT-03 é um identificador técnico.</p>", encoding="utf-8")

    package = generate(root)
    assert inventory(root) == before
    assert original_catalog.read_text(encoding="utf-8") == (
        "<p>CAT-03 é um identificador técnico.</p>"
    )
    html_files = list(package.glob("*.html"))
    assert len(html_files) == 11
    for page in html_files:
        text = page.read_text(encoding="utf-8")
        editorial = " ".join(EditorialText(text).visible)
        assert not re.search(r"\bCAT-(?:0[1-9]|10)\b", editorial), page.name

    plan = (package / "plano.html").read_text(encoding="utf-8")
    assert "Revisar conteúdo, semântica e dados estruturados e inteligência de busca e IA" in plan
    assert "Confirmar fundamentos técnicos e descoberta antes de remediações" in plan
    assert 'CAT-03' in (root / "audit.db").read_bytes().decode("latin-1")
    manifest = json.loads((package / "_geracao.json").read_text(encoding="utf-8"))
    assert manifest["integrity"] == "PASS"
    assert manifest["source_db_logical_sha256"]


def test_presentation_source_vocabulary_is_readable_without_rewriting_vendor_names():
    raw = (
        "<p>M2 physical HTTP acquisition persisted as page_snapshots.browser_metadata.raw_http</p>"
        "<p>RASAi RuleExecutions</p><p>RASAi discovery provenance</p>"
        "<p>Search Intelligence SERP observations</p>"
        "<p>Search Intelligence explicit relevance judgments</p>"
        "<p>OPEN-WEB-METRICS-001</p>"
        "<p>MDN HTTP Observatory; W3C CSS Validation Service</p>"
        "<pre>M2 physical HTTP acquisition persisted as page_snapshots.browser_metadata.raw_http</pre>"
    )
    shown = humanize_module_references_html(raw)
    assert "Coleta HTTP realizada pelo RASAi" in shown
    assert "Execução das regras de auditoria do RASAi" in shown
    assert "Evidências de descoberta coletadas pelo RASAi" in shown
    assert "Resultados de busca observados" in shown
    assert "Avaliações explícitas de relevância em resultados de busca" in shown
    assert "Referência técnica de métricas abertas da web" in shown
    assert "MDN HTTP Observatory; W3C CSS Validation Service" in shown
    assert "<pre>M2 physical HTTP acquisition persisted as page_snapshots.browser_metadata.raw_http</pre>" in shown
    assert shown == humanize_module_references_html(shown)
