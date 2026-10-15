from pathlib import Path

def test_method_docs_keep_llms_non_scoring_and_jsonld_absence_traceable() -> None:
    decisions = Path("docs/specification/10_DECISIONS.md").read_text(encoding="utf-8")
    guide = Path("docs/REPORT_GUIDE.md").read_text(encoding="utf-8")
    assert "ausência de JSON-LD é materializada" in decisions
    assert "llms.txt" in guide and "peso direto" in guide and "`0`" in guide
