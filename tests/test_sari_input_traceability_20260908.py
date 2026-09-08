from pathlib import Path


def test_readiness_exposes_observed_discovery_state_not_presence_claim() -> None:
    source = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    assert "Sitemap disponível: aquisição e interpretação" not in source
    assert "robots.txt presente: interpretabilidade" not in source
    assert "AUSENTE não significa encontrado" in source
    assert "peso SARI = 0" in source
    assert "m24_runs" in source
    assert "BR-GEO-055" in source and "BR-GEO-056" in source


def test_readiness_exposes_jsonld_scoring_trace() -> None:
    source = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    assert "_structured_data_scoring_block(data)" in source
    assert "JSON-LD no cálculo do SCORE-GEO-004" in source
    assert "script[type=&quot;application/ld+json&quot;]" in source
    assert "STRUCTURED_DATA_SYNTAX" in source
    assert "STRUCTURED_DATA_CONSISTENCY" in source
    assert "BR-GEO-034" in source and "BR-GEO-037" in source


def test_method_docs_keep_llms_non_scoring_and_jsonld_absence_traceable() -> None:
    decisions = Path("docs/specification/10_DECISIONS.md").read_text(encoding="utf-8")
    guide = Path("docs/REPORT_GUIDE.md").read_text(encoding="utf-8")
    assert "ausência de JSON-LD é materializada" in decisions
    assert "llms.txt" in guide and "peso direto" in guide and "`0`" in guide
