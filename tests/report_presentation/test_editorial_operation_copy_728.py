"""#728/A — contextual humanization only; protect canonical source evidence.

The local fixtures exercise all eleven page shells but are not a substitute
for acceptance of the customer's physical AUD and 11 HTML pages.
"""
from rasai.parallel_report.read_model import PAGES
from rasai.report_presentation import humanize_module_references_html


def test_known_operation_copy_is_human_on_all_eleven_presentation_surfaces():
    assert len(PAGES) == 11
    for page, title in PAGES:
        html = (
            f'<article data-page="{page}"><h1>{title}</h1>'
            '<p>Operação: SEMANTIC_M7.</p>'
            '<p>Finalidade: SEMANTIC_M7</p>'
            '<span>Propósito: SEMANTIC_M7</span>'
            '<dl><dt>Finalidade</dt><dd>SEMANTIC_M7</dd></dl>'
            '<div title="Operação: SEMANTIC_M7" '
            'aria-label="Finalidade: SEMANTIC_M7">Texto</div>'
            '</article>'
        )
        rendered = humanize_module_references_html(html)
        assert rendered.count('Análise semântica por IA') == 6, page
        assert 'SEMANTIC_M7' not in rendered, page
        assert f'data-page="{page}"' in rendered
        assert humanize_module_references_html(rendered) == rendered


def test_provenance_attributes_and_literal_evidence_are_never_rewritten():
    html = (
        '<a href="evidence/SEMANTIC_M7.json" id="SEMANTIC_M7" '
        'data-code="SEMANTIC_M7" title="Rastro: SEMANTIC_M7">'
        'Consultar fonte</a>'
        '<pre>Operação: SEMANTIC_M7</pre>'
        '<code>Finalidade: SEMANTIC_M7</code>'
        '<blockquote>Operação: SEMANTIC_M7</blockquote>'
        '<q>Finalidade: SEMANTIC_M7</q>'
        '<samp>Operação: SEMANTIC_M7</samp>'
        '<textarea>Finalidade: SEMANTIC_M7</textarea>'
        '<span>&lt;div data-operation="SEMANTIC_M7"&gt;'
        'Operação: SEMANTIC_M7&lt;/div&gt;</span>'
        '<p>Modelo SEMANTIC_M7 é um identificador fornecido pela fonte.</p>'
        '<p>SEMANTIC_M7 isolado não determina o campo.</p>'
    )
    assert humanize_module_references_html(html) == html


def test_only_labeled_purpose_values_change_in_accessible_attributes():
    html = (
        '<section title="Finalidade: SEMANTIC_M7" '
        'aria-label="Operação: SEMANTIC_M7" '
        'data-operation="Finalidade: SEMANTIC_M7" '
        'id="SEMANTIC_M7" class="SEMANTIC_M7">'
        '<dl><dt>Modelo</dt><dd>SEMANTIC_M7</dd>'
        '<dt>Finalidade</dt><dd>SEMANTIC_M7</dd>'
        '<dt>Identificador da fonte</dt><dd>SEMANTIC_M7</dd></dl>'
        '</section>'
    )
    rendered = humanize_module_references_html(html)
    assert 'title="Finalidade: Análise semântica por IA"' in rendered
    assert 'aria-label="Operação: Análise semântica por IA"' in rendered
    assert 'data-operation="Finalidade: SEMANTIC_M7"' in rendered
    assert 'id="SEMANTIC_M7"' in rendered
    assert 'class="SEMANTIC_M7"' in rendered
    assert '<dt>Modelo</dt><dd>SEMANTIC_M7</dd>' in rendered
    assert '<dt>Finalidade</dt><dd>Análise semântica por IA</dd>' in rendered
    assert '<dt>Identificador da fonte</dt><dd>SEMANTIC_M7</dd>' in rendered


def test_unknown_operation_and_inline_evidence_do_not_gain_invented_meaning():
    html = (
        '<p>Operação: UNKNOWN_NEW_MODULE</p>'
        '<p>Opção técnica: SEMANTIC_M7</p>'
        '<p>Este módulo M25 usa estados persistidos.</p>'
        '<a href="anexos/SEMANTIC_M7.json">Código técnico</a>'
    )
    rendered = humanize_module_references_html(html)
    assert 'UNKNOWN_NEW_MODULE' in rendered
    assert 'Opção técnica: SEMANTIC_M7' in rendered
    assert 'Este módulo Apdex de experiência usa estados persistidos.' in rendered
    assert 'href="anexos/SEMANTIC_M7.json"' in rendered
