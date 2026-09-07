from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old in text:
        p.write_text(text.replace(old, new), encoding='utf-8', newline='\n')

# Consolidated validation: expose only scoring versions actually relevant to the current contract.
replace(
    'docs/CONSOLIDATED_REPORTING_VALIDATION.md',
    'O HTML só apresenta versões efetivamente persistidas nas fontes selecionadas. `SCORE-GEO-001` não é exibido como alternativa quando não existe nos AUDs.',
    'O HTML só apresenta versões efetivamente persistidas nas fontes selecionadas e não inventa alternativas metodológicas ausentes dos AUDs.'
)
replace(
    'docs/CONSOLIDATED_REPORTING_VALIDATION.md',
    '- `SCORE-GEO-001` ausente da UI quando não existe nas fontes;',
    '- versões de scoring ausentes das fontes não são inventadas pela UI;'
)

# Older delivery specifications now state the current invariant instead of naming an unreleased predecessor.
replace('docs/specification/14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md', '**Scoring contract:** `SCORE-GEO-001` — unchanged', '**Scoring contract:** `SCORE-GEO-003` — unchanged by this capability')
replace('docs/specification/14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md', 'Auditoria multi-URL e evidência visual does not change `SCORE-GEO-001`.', 'Auditoria multi-URL e evidência visual não altera `SCORE-GEO-003` nem o `SARI-001`.')

replace('docs/specification/17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md', '`SCORE-GEO-001`, `REPORT-GEO-003`, `REMEDIATION-GEO-001`', '`SCORE-GEO-003`, `REPORT-GEO-003`, `REMEDIATION-GEO-001`')
replace('docs/specification/17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md', '- SCORE-GEO-001;', '- SCORE-GEO-003;')

for old, new in (
    ('- preservar `SCORE-GEO-001`;', '- preservar o contrato de scoring `SCORE-GEO-003`;'),
    ('- guia das dez dimensões oficiais de `SCORE-GEO-001`;', '- guia das dez dimensões do `SARI-001` e do contrato `SCORE-GEO-003`;'),
    ('- preservar `SCORE-GEO-001`, Coverage, Confidence, Consolidation e actionability;', '- preservar `SCORE-GEO-003`, Coverage, Confidence, Consolidation e actionability;'),
    ('- `diagnostic_confidence` mede apenas precisão de localização/causa e não participa de `SCORE-GEO-001`;', '- `diagnostic_confidence` mede apenas precisão de localização/causa e não participa do `SARI-001`/`SCORE-GEO-003`;'),
    ('- preservar `SCORE-GEO-001`, `PRIORITY-GEO-001`, severity, actionability, Coverage, Confidence e Consolidation;', '- preservar `SCORE-GEO-003`, `PRIORITY-GEO-001`, severity, actionability, Coverage, Confidence e Consolidation;'),
):
    replace('docs/specification/09_IMPLEMENTATION_PLAN.md', old, new)

replace('docs/specification/16_ROOT_CAUSE_ELEMENT_REMEDIATION.md', '`SCORE-GEO-001`, `REPORT-GEO-003`, `REMEDIATION-GEO-001`', '`SCORE-GEO-003`, `REPORT-GEO-003`, `REMEDIATION-GEO-001`')

# Tests must verify the current public/reporting contract rather than predecessor wording.
replace(
    'tests/test_report_registry_and_method_docs.py',
    '        assert "SCORE-GEO-002" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]\n        assert "histórico" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]',
    '        assert "SCORE-GEO-002" not in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]\n        assert "histórico" not in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]'
)
replace(
    'tests/test_m21_web_performance.py',
    'def test_report_keeps_external_metrics_separate_from_score_geo_002(self) -> None:',
    'def test_report_keeps_external_metrics_separate_from_score_geo_003(self) -> None:'
)
replace('tests/test_m21_web_performance.py', '            self.assertIn("SCORE-GEO-002", html)', '            self.assertIn("SCORE-GEO-003", html)')

# Final public-documentation gate: no unreleased predecessor naming or supersession narrative.
banned = ('SCORE-GEO-001', 'SCORE-GEO-002', 'SGRI-001')
for path in [Path('README.md'), *Path('docs').rglob('*.md')]:
    text = path.read_text(encoding='utf-8')
    for token in banned:
        if token in text:
            lines = [f'{i}: {line}' for i, line in enumerate(text.splitlines(), 1) if token in line]
            raise SystemExit(f'{token} remains in {path}:\n' + '\n'.join(lines))

# Brand gate: standalone all-caps RASAI is allowed only in the explicit acronym explanation;
# technical identifiers such as RASAI-OBS-* are preserved by design.
readme = Path('README.md').read_text(encoding='utf-8')
assert '# RASAi — Search & AI Readiness Auditor' in readme
assert '**R**eadiness **A**ssessment for **S**earch & **AI**' in readme
assert '**Framework:** RASAi Framework' in readme
