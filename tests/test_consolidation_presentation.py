from __future__ import annotations

import json
from pathlib import Path

from rasai.consolidation.presentation import refine_html, specialist_usage_summary


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
    assert "Provedor" in rendered and "Perfil de raciocínio" in rendered
    assert "Somente IA especialista, quando autorizada" in rendered
    assert "href='#specialist-ai'" in rendered


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
