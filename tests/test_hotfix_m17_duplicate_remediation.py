from __future__ import annotations

from datetime import datetime, timezone
import unittest

from rasai.m16_root_cause import RootCauseAnalysis
from rasai.m17_duplicate_remediation import refine_br_geo_051_html
from rasai.m17_precision import derive_precision


_NOW = datetime(2026, 9, 3, 13, 0, tzinfo=timezone.utc)


def _analysis(observed: dict[str, object]) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        analysis_id="RCA-DUP",
        audit_id="AUD-DUP",
        finding_id="FND-DUP",
        rule_id="BR-GEO-051",
        cause_type="RULE_CONDITION_MISMATCH",
        affected_scope="DOCUMENT_OR_CONTENT",
        cause_summary="A condição observada não satisfaz a condição esperada da Business Rule para esta ocorrência.",
        evidence_basis=("EV-DUP",),
        affected_elements=(),
        selector_status="NOT_DETERMINED",
        observed_value=observed,
        expected_condition="material exact or near-duplicate content is identified only within the audited universe",
        exact_change="fallback",
        example_after=None,
        acceptance_criteria=("fallback",),
        revalidation_steps=("fallback",),
        human_decision_required=None,
        diagnostic_confidence="MEDIUM",
        materialized_at=_NOW,
    )


class HotfixM17DuplicateRemediationTests(unittest.TestCase):
    def test_exact_duplicate_evidence_gets_precise_reason_without_selector_invention(self) -> None:
        precision = derive_precision(
            analysis=_analysis({
                "matches": [
                    {"page_id": "PGE-2", "similarity": 1.0},
                    {"page_id": "PGE-3", "similarity": 1.0},
                ],
                "near_duplicate_jaccard_threshold": 0.9,
                "universe": "AUDITED_ONLY",
            })
        )

        self.assertEqual(precision.reason_code, "EXACT_DUPLICATE_MAIN_CONTENT")
        self.assertEqual(precision.observed_element_status, "NOT_APPLICABLE")
        self.assertIsNone(precision.observed_selector)
        self.assertIsNone(precision.target_selector)
        self.assertIn("2 outra(s) página(s)", precision.precise_cause_summary)
        self.assertIn("similaridade 1.0", precision.precise_cause_summary)

    def test_near_duplicate_evidence_gets_threshold_specific_reason(self) -> None:
        precision = derive_precision(
            analysis=_analysis({
                "matches": [{"page_id": "PGE-2", "similarity": 0.93}],
                "near_duplicate_jaccard_threshold": 0.9,
                "universe": "AUDITED_ONLY",
            })
        )
        self.assertEqual(precision.reason_code, "NEAR_DUPLICATE_MAIN_CONTENT")
        self.assertIn("0.90", precision.precise_cause_summary)

    def test_html_projection_replaces_only_br_geo_051_fallback(self) -> None:
        duplicate = '''
<section class="m16-root m17-precision">
<div><small>Causa</small><strong>RULE_CONDITION_MISMATCH</strong></div>
<div><small>Motivo técnico</small><strong>EXACT_DUPLICATE_MAIN_CONTENT</strong></div>
<div><small>Regra</small><strong>BR-GEO-051</strong></div>
<p><strong>Causa raiz:</strong> A condição observada não satisfaz a condição esperada da Business Rule para esta ocorrência.</p>
<p><strong>Recipe técnica:</strong> Remediar BR-GEO-051</p>
<h5>Mudança recomendada</h5><div class="m16-change">Ação: REVIEW_AND_CORRECT · Alvo: Condição registrada no finding · Atender à condição esperada registrada no finding usando somente a evidência persistida. Este é um fallback porque ainda não existe recipe específica para a regra.</div>
<h5>Critério de aceite</h5><ul><li>A condição esperada do finding é atendida sem criar conflito com outras regras.</li></ul>
<h5>Revalidação</h5><ol><li>Reexecutar BR-GEO-051 e revisar as evidence_ids associadas.</li></ol>
</section>
'''
        other = '''
<section class="m16-root m17-precision">
<div><small>Causa</small><strong>RULE_CONDITION_MISMATCH</strong></div>
<div><small>Regra</small><strong>BR-GEO-099</strong></div>
<h5>Mudança recomendada</h5><div class="m16-change">Ação: REVIEW_AND_CORRECT · Alvo: Condição registrada no finding · Atender à condição esperada registrada no finding usando somente a evidência persistida. Este é um fallback porque ainda não existe recipe específica para a regra.</div>
</section>
'''

        html = refine_br_geo_051_html(duplicate + other)

        self.assertIn("DUPLICATE_MAIN_CONTENT", html)
        self.assertIn("Revisar duplicidade do conteúdo principal", html)
        self.assertIn("REVIEW_DUPLICATE_CONTENT", html)
        self.assertIn("Decisão humana necessária", html)
        self.assertIn("BR-GEO-099", html)
        self.assertEqual(html.count("Ação: REVIEW_AND_CORRECT · Alvo: Condição registrada no finding"), 1)


if __name__ == "__main__":
    unittest.main()
