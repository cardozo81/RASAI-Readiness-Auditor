from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    text = read(path)
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"expected {count}, found {actual} in {path}: {old[:120]!r}")
    write(path, text.replace(old, new, count))


replace(
    "src/rasai/report_semantics.py",
    '''    html = _decorate_metrics(html, page_name)\n    html = _decorate_actionable_rows(html)\n    html = _translate_readiness_table_headers(html)\n    if page_name in {"mobile.html", "desktop.html"}:\n        html = _enhance_score_page(html)\n    elif page_name == "accessibility.html":\n        html = _enhance_accessibility(html)\n    elif page_name == "ai-usage.html":\n        html = _enhance_ai_usage(html)\n    elif page_name == "apdex.html":\n        html = _enhance_apdex(html, report_dir)\n    elif page_name == "web-performance.html":\n        html = _enhance_web_performance(html)\n    return enrich_indicator_provenance_html(html, page_name=page_name)\n''',
    '''    html = _decorate_metrics(html, page_name)\n    html = _translate_readiness_table_headers(html)\n    # Domain-specific semantics must run before the generic table decorator.\n    # Otherwise a generic terminal state such as "Consolidado" can mask a more\n    # important condition such as low confidence/coverage.\n    if page_name in {"readiness.html", "mobile.html", "desktop.html"}:\n        html = _enhance_score_page(html)\n    elif page_name == "accessibility.html":\n        html = _enhance_accessibility(html)\n    elif page_name == "ai-usage.html":\n        html = _enhance_ai_usage(html)\n    elif page_name == "apdex.html":\n        html = _enhance_apdex(html, report_dir)\n    elif page_name == "web-performance.html":\n        html = _enhance_web_performance(html)\n    html = _decorate_actionable_rows(html)\n    return enrich_indicator_provenance_html(html, page_name=page_name)\n''',
)

replace(
    "src/rasai/report_semantics.py",
    '''    def replace_row(match: re.Match[str]) -> str:\n        body = match.group("body")\n        cells = list(_TABLE_CELL_RE.finditer(body))\n''',
    '''    def replace_row(match: re.Match[str]) -> str:\n        # A domain-specific row state has precedence over generic terminal values.\n        # This keeps e.g. LOW confidence + CONSOLIDATED visually warning, not green.\n        if re.search(r"\\bresult-state-(?:good|warn|bad|neutral)\\b", match.group("attrs")):\n            return match.group(0)\n        body = match.group("body")\n        cells = list(_TABLE_CELL_RE.finditer(body))\n''',
)

# Add direct regressions around the exact condition shown in the supplied report.
test_path = "tests/test_report_polish_20260908.py"
test = read(test_path)
marker = "def test_readiness_low_confidence_has_precedence_over_consolidated_state()"
if marker not in test:
    test += '''\n\ndef test_readiness_low_confidence_has_precedence_over_consolidated_state() -> None:\n    html = (\n        "<table><tbody><tr><td>Evidências e confiabilidade</td><td>75.0</td>"\n        "<td>67%</td><td>Baixa</td><td>Consolidado</td></tr></tbody></table>"\n    )\n    rendered = enhance_report_html(html, page_name="readiness.html", report_dir=ROOT)\n    assert "result-state-warn" in rendered\n    assert "Cobertura insuficiente" in rendered\n    assert "result-state-good" not in rendered\n\n\ndef test_readiness_partial_state_remains_warning_after_global_decoration() -> None:\n    html = (\n        "<table><tbody><tr><td>Evidências e confiabilidade</td><td>75.0</td>"\n        "<td>100%</td><td>Alta</td><td>Parcial</td></tr></tbody></table>"\n    )\n    rendered = enhance_report_html(html, page_name="readiness.html", report_dir=ROOT)\n    assert "result-state-warn" in rendered\n    assert "result-state-good" not in rendered\n'''
    write(test_path, test)

# Documentation: state semantic precedence explicitly so later UI work does not regress it.
report_guide = read("docs/REPORT_GUIDE.md")
doc_marker = "### Precedência dos estados visuais"
if doc_marker not in report_guide:
    report_guide += '''\n\n### Precedência dos estados visuais\n\nQuando uma tabela possui semântica específica de domínio, ela prevalece sobre o decorador genérico de estados. Em `readiness.html`, por exemplo, **Confiança baixa/Cobertura insuficiente** ou **Consolidação parcial** permanece em estado de atenção mesmo quando outra célula da mesma linha contém um valor terminal positivo. O decorador genérico de `Aprovado`, `Alerta`, `Erro`, `Consolidado` etc. só classifica linhas que ainda não receberam um estado semântico específico. Isso evita que um status operacional positivo esconda uma limitação material da medição.\n'''
    write("docs/REPORT_GUIDE.md", report_guide)

print("readiness semantic precedence fix applied")
