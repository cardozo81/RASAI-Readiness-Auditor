from __future__ import annotations

import json
from pathlib import Path

from rasai.consolidation.presentation import _render_usage, _sari_confidence_label, finalize_reader_experience, refine_html, specialist_usage_summary


def _artifact() -> dict:
    return {
        "changes": [
            {
                "evidence_id": "CHANGE-0001",
                "topic": "PERFORMANCE",
                "label": "LCP",
                "status": "IMPROVED",
                "before": 3.2,
                "after": 2.1,
                "delta": -1.1,
                "delta_percent": -34.4,
                "severity": "HIGH",
                "device": "MOBILE",
                "url": "https://example.test/",
                "unit": "s",
            }
        ],
        "ai": {
            "requested": True,
            "status": "COMPLETE",
            "summary": "Síntese da evolução.",
            "topic_analyses": [
                {
                    "topic": "SEO",
                    "assessment": "Ação menos urgente.",
                    "recommended_actions": ["Revisar títulos."],
                    "priority": "P2",
                    "confidence": 0.8,
                    "evidence_ids": ["CHANGE-0001"],
                },
                {
                    "topic": "PERFORMANCE",
                    "assessment": "Ação crítica.",
                    "recommended_actions": ["Validar regressões remanescentes."],
                    "priority": "P0",
                    "confidence": 0.9,
                    "evidence_ids": ["CHANGE-0001"],
                },
            ],
            "attempts": [
                {
                    "provider": "OPENAI",
                    "model": "gpt-test",
                    "reasoning": "LOW",
                    "status": "SUCCESS",
                    "input_tokens": 1000,
                    "cached_input_tokens": 100,
                    "output_tokens": 200,
                    "reasoning_tokens": 50,
                    "estimated_cost": 0.0123,
                    "currency": "USD",
                }
            ],
            "forecast": {
                "currency": "USD",
                "expected_cost": 0.01,
                "likely_high": 0.012,
                "potential": 0.02,
                "confidence": "MÉDIA",
                "pricing_coverage": 1.0,
                "confidence_basis": "preços conhecidos; volume de tokens/saída permanece estimado antes da execução",
            },
            "reason": None,
        },
    }


def test_refine_html_localizes_trend_and_marks_ai_provenance() -> None:
    html = """<html><head></head><body><nav><a href='#evolution'>Evolução</a></nav>
<section id='specialist-evolution'><div class='metric'><span>Melhorias</span><strong>1</strong></div><table><tr><td>IMPROVED</td></tr></table><h3>Fix Verification</h3></section>
<section id='specialist-ai' class='panel'>old advisory/non-scoring</section>
<section id='method'><div><small>Chamadas externas</small><strong>Nenhuma</strong><p>O consolidado não chama IA, PageSpeed, CrUX ou qualquer API.</p></div></section>
<footer>fim</footer></body></html>"""
    rendered = refine_html(html, _artifact())

    assert "signal-positive" in rendered
    assert "Melhorou" in rendered
    assert "Verificação de correções" in rendered
    assert "Conteúdo gerado por IA" in rendered
    assert "Destaques de melhora observada" in rendered
    assert rendered.index("P0 · Crítica") < rendered.index("P2 · Média")
    assert "Provedor" in rendered and "Raciocínio" in rendered
    assert "Confiança da previsão" in rendered
    assert "Cobertura de preços" in rendered
    assert "Média" in rendered
    assert "100%" in rendered
    assert "Base da confiança:" in rendered
    assert "volume de tokens/saída permanece estimado" in rendered
    assert "Somente IA especialista, quando autorizada" in rendered
    assert "href='#specialist-ai'" in rendered
    assert ".metric-grid>div>strong{display:block;font-size:1.28rem;font-weight:750" in rendered
    assert "main details>summary" in rendered


def test_sari_confidence_is_always_humanized_in_pt_br() -> None:
    expected = {
        "VERY_HIGH": "Muito alta",
        "HIGH": "Alta",
        "MEDIUM": "Média",
        "LOW": "Baixa",
        "VERY_LOW": "Muito baixa",
        "UNAVAILABLE": "Indisponível",
        "NOT_AVAILABLE": "Indisponível",
        "NOT_APPLICABLE": "Não aplicável",
        "NOT_DETERMINABLE": "Não determinada",
        "UNKNOWN": "Não determinada",
        "FUTURE_ENUM": "Não determinada",
        None: "Não determinada",
    }
    for raw, label in expected.items():
        assert _sari_confidence_label(raw) == label


def test_visible_audit_ids_link_only_canonical_sources_without_touching_raw_payloads() -> None:
    html = (
        "<html><head></head><body><main><p>Comparar AUD-ABC123 com AUD-XYZ789 e AUD-TRUNC.</p>"
        "<pre>AUD-RAW123</pre><svg><title>AUD-SVG123</title></svg>"
        "<a href='already.html'>AUD-LINKED123</a></main></body></html>"
    )
    artifact = {"scope": {"audit_ids": ["AUD-ABC123", "AUD-XYZ789"]}}
    rendered = finalize_reader_experience(html, artifact)
    assert "href='../../AUD-ABC123/report-catalog/index.html'" in rendered
    assert "href='../../AUD-XYZ789/report-catalog/index.html'" in rendered
    assert "../../AUD-TRUNC/report-catalog/index.html" not in rendered
    assert "AUD-TRUNC" in rendered
    assert rendered.count("target='_blank'") == 2
    assert "<pre>AUD-RAW123</pre>" in rendered
    assert "<svg><title>AUD-SVG123</title></svg>" in rendered
    assert "<a href='already.html'>AUD-LINKED123</a>" in rendered


def test_visible_audit_ids_do_not_autolink_when_artifact_has_no_canonical_sources() -> None:
    rendered = finalize_reader_experience(
        "<html><body><main><p>AUD-NOT-CANONICAL</p></main></body></html>",
        {},
    )
    assert "AUD-NOT-CANONICAL" in rendered
    assert "audit-link" not in rendered


def test_specialist_usage_summary_aggregates_cost_and_tokens(tmp_path: Path) -> None:
    payload = _artifact()
    payload["ai"]["attempts"].append(
        {
            "provider": "SECOND",
            "model": "m",
            "reasoning": "LOW",
            "status": "TECHNICAL_ERROR",
            "input_tokens": 50,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost": None,
            "currency": None,
        }
    )
    (tmp_path / "specialist-analysis.json").write_text(json.dumps(payload), encoding="utf-8")

    summary = specialist_usage_summary(tmp_path)
    assert summary is not None
    assert summary.requested is True
    assert summary.attempts == 2
    assert summary.successes == 1
    assert summary.input_tokens == 1050
    assert summary.output_tokens == 200
    assert summary.costs == (("USD", 0.0123),)
    assert summary.unpriced_attempts == 1



def test_render_usage_uses_persisted_output_tokens_without_name_error() -> None:
    html = _render_usage(
        [
            {
                "provider": "OPENAI",
                "model": "gpt-test",
                "reasoning": "LOW",
                "status": "SUCCESS",
                "input_tokens": 120,
                "cached_input_tokens": 0,
                "output_tokens": 42,
                "reasoning_tokens": 0,
                "estimated_cost": 0.0,
                "currency": "USD",
                "duration_ms": 250,
            }
        ]
    )

    assert "120" in html
    assert "42" in html
    assert "USD 0.00000000" in html
    assert "no-cost-value" in html

def test_stale_source_report_is_not_autolinked_when_governance_proves_staleness() -> None:
    html = "<html><head></head><body><main><p>AUD-FRESH e AUD-STALE</p></main></body></html>"
    artifact = {
        "scope": {"audit_ids": ["AUD-FRESH", "AUD-STALE"]},
        "decision_context": {
            "source_governance": {
                "audits": [
                    {"audit_id": "AUD-FRESH", "report_catalog_present": True, "report_catalog_fresh": True},
                    {"audit_id": "AUD-STALE", "report_catalog_present": True, "report_catalog_fresh": False},
                ]
            }
        },
    }

    rendered = finalize_reader_experience(html, artifact)

    assert "../../AUD-FRESH/report-catalog/index.html" in rendered
    assert "../../AUD-STALE/report-catalog/index.html" not in rendered
    assert "AUD-STALE" in rendered


def test_presentation_uses_subtle_traffic_lights_ai_tags_and_ten_pixel_axis_labels() -> None:
    rendered = refine_html("<html><head></head><body><main></main></body></html>", _artifact())

    assert ".axis-label{font-size:10px}" in rendered
    assert ".strategy-card{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:14px 16px}" in rendered
    assert ".strategy-card h4{margin:0 0 8px;color:var(--ink)}" in rendered
    assert ".closure-grid{display:grid;grid-template-columns:1fr;gap:12px}" in rendered
    assert "@media(min-width:780px){.closure-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}" in rendered
    assert "@media(min-width:1280px){.closure-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}" in rendered
    assert "@media(min-width:1920px){.closure-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}" in rendered
    assert ".ai-origin{display:inline-flex" in rendered
    assert "border-left:4px solid var(--red)" in rendered
    assert "border-left:3px solid var(--amber)" in rendered

def test_stale_preexisting_source_report_link_is_stripped_but_text_is_preserved() -> None:
    html = (
        "<html><head></head><body><main>"
        "<a class='audit-link' href='../../AUD-FRESH/report-catalog/index.html' target='_blank'>AUD-FRESH</a>"
        "<a class='audit-link' href='../../AUD-STALE/report-catalog/index.html' target='_blank'>AUD-STALE</a>"
        "</main></body></html>"
    )
    artifact = {
        "decision_context": {
            "source_governance": {
                "audits": [
                    {"audit_id": "AUD-FRESH", "report_catalog_fresh": True},
                    {"audit_id": "AUD-STALE", "report_catalog_fresh": False},
                ]
            }
        }
    }

    rendered = finalize_reader_experience(html, artifact)

    assert "../../AUD-FRESH/report-catalog/index.html" in rendered
    assert "../../AUD-STALE/report-catalog/index.html" not in rendered
    assert "AUD-STALE" in rendered

def test_visible_unrelated_state_is_humanized_without_touching_raw_payloads() -> None:
    html = (
        "<html><head></head><body><main>"
        "<p>Configuração: UNRELATED</p>"
        "<pre>{\"pair_status\":\"UNRELATED\"}</pre>"
        "</main></body></html>"
    )

    rendered = finalize_reader_experience(html, {})

    assert "Configuração: Configurações não equivalentes" in rendered
    assert "<pre>{\"pair_status\":\"UNRELATED\"}</pre>" in rendered

def test_visible_ai_prose_finishes_pt_br_normalization_without_touching_raw_payloads() -> None:
    html = (
        "<html><head></head><body><main>"
        "<p>Os findings de GEO / AI Readiness usam main thread e benchmark index.</p>"
        "<p>Revisar dos findings e esses findings antes da próxima execução.</p>"
        "<p>estado retryable failed; falha retryable; Performance mobile; benchmark_index.</p>"
        "<pre>{\"label\":\"GEO / AI Readiness\",\"term\":\"main thread\",\"findings\":2,\"state\":\"retryable failed\",\"device\":\"mobile\",\"metric\":\"benchmark_index\"}</pre>"
        "</main></body></html>"
    )

    rendered = finalize_reader_experience(html, {})

    assert "As ocorrências de GEO / preparação para IA usam thread principal e índice de referência." in rendered
    assert "Revisar das ocorrências e essas ocorrências antes da próxima execução." in rendered
    assert "estado falha passível de nova tentativa; falha passível de nova tentativa; Desempenho em dispositivo móvel; índice de referência." in rendered
    assert "<pre>{\"label\":\"GEO / AI Readiness\",\"term\":\"main thread\",\"findings\":2,\"state\":\"retryable failed\",\"device\":\"mobile\",\"metric\":\"benchmark_index\"}</pre>" in rendered

