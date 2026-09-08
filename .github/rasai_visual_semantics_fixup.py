from pathlib import Path
import re

ROOT = Path('.')

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding='utf-8', newline='\n')

# Keep the current JSON-LD semantics while retaining useful user-facing wording.
path = 'src/rasai/report_semantics.py'
text = read(path)
old = (
    '            "<div class=\'notice structured-data-absence-note\'><strong>Dados estruturados: ausência é uma lacuna leve, não falha de coleta.</strong> "\n'
    '            "Quando nenhum JSON-LD é observado, BR-GEO-034 permanece aplicável e recebe WARNING com fator reduzido; regras de tipos/consistência sem markup podem ficar NOT_APPLICABLE. "\n'
)
new = (
    '            "<div class=\'notice structured-data-absence-note\'><strong>Dados estruturados: ausência é uma lacuna leve, não falha de coleta.</strong> "\n'
    '            "Estado observado <strong>Opcional / não detectado</strong> não significa que a dimensão inteira saiu do SARI: quando nenhum JSON-LD é observado, BR-GEO-034 permanece aplicável e recebe WARNING com fator reduzido; regras de tipos/consistência sem markup podem ficar NOT_APPLICABLE. "\n'
)
if old not in text:
    raise SystemExit('structured-data note block not found')
text = text.replace(old, new, 1)
old = (
    '        scorecard_end = html.find("</section>", html.find("Dimensões"))\n'
    '        if scorecard_end >= 0:\n'
    '            html = html[:scorecard_end] + note + html[scorecard_end:]\n'
    '    return html\n'
)
new = (
    '        scorecard_end = html.find("</section>", html.find("Dimensões"))\n'
    '        if scorecard_end >= 0:\n'
    '            html = html[:scorecard_end] + note + html[scorecard_end:]\n'
    '        else:\n'
    '            html += note\n'
    '    return html\n'
)
if old not in text:
    raise SystemExit('structured-data insertion fallback not found')
text = text.replace(old, new, 1)

# The four-state score condition has precedence over a generic terminal-state label.
# Keep legacy result-state classes only as an internal CSS hook, mapped from the
# new condition semantics rather than recalculated from Consolidation alone.
# When the near state is caused by insufficient Coverage, say so explicitly.
old = (
    '        tag = f" <span class=\'score-condition-tag {state}\'>{escape(label)}</span>"\n'
    '        return (\n'
    '            f"<tr{attrs} class=\'score-condition-{state}\'><td>{escape(dimension)}</td>"\n'
)
new = (
    '        coverage_number = _first_number(coverage)\n'
    '        if state == "near" and coverage_number is not None and coverage_number < 80:\n'
    '            label = "Quase no esperado · Cobertura insuficiente"\n'
    '        elif state == "near" and confidence.casefold() == "baixa":\n'
    '            label = "Quase no esperado · Confiança baixa"\n'
    '        tag = f" <span class=\'score-condition-tag {state}\'>{escape(label)}</span>"\n'
    '        legacy_state = {"expected": "good", "near": "warn", "below": "warn", "critical": "bad", "neutral": "neutral"}[state]\n'
    '        return (\n'
    '            f"<tr{attrs} class=\'score-condition-{state} result-state-{legacy_state}\'><td>{escape(dimension)}</td>"\n'
)
if old not in text:
    raise SystemExit('score row semantic block not found')
text = text.replace(old, new, 1)
write(path, text)

# A stale unpublished alias from an older local audit folder is housekeeping, not
# a current report surface. Remove it before normalizing navigation.
path = 'src/rasai/report_navigation.py'
text = read(path)
needle = '    _ensure_premium_css(report_dir)\n    _enhance_ai_cost_total(report_dir)\n'
replacement = (
    '    _ensure_premium_css(report_dir)\n'
    '    _enhance_ai_cost_total(report_dir)\n'
    '    # Pré-publicação: remover alias versionado residual de audits locais antigos.\n'
    '    (report_dir / "score-geo-004.html").unlink(missing_ok=True)\n'
)
if needle not in text:
    raise SystemExit('navigation normalization insertion point not found')
text = text.replace(needle, replacement, 1)
write(path, text)

# Replace the obsolete compatibility-alias test with the pre-publication contract.
path = 'tests/test_report_registry_and_method_docs.py'
text = read(path)
pattern = r'def test_versioned_score_report_is_compatibility_alias_not_canonical_navigation\(\) -> None:.*?(?=\n\ndef test_current_method_documents_use_score_geo_004_without_declaring_003_current)'
replacement = '''def test_prepublication_scoring_report_has_no_versioned_alias() -> None:\n    assert REPORT_FILE == "scoring.html"\n    assert LEGACY_REPORT_FILE == "score-geo-004.html"\n    assert REPORT_FILE != LEGACY_REPORT_FILE\n    assert not any(filename == LEGACY_REPORT_FILE for _, filename in CANONICAL_NAV_ITEMS)\n\n\n'''
text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
if count != 1:
    raise SystemExit(f'legacy alias test replacement count={count}')
write(path, text)

# Old assertions described the pre-refinement Structured Data semantics. Current
# SCORE-GEO-004 keeps BR-GEO-034 applicable as a modest WARNING when JSON-LD is absent.
path = 'tests/test_report_semantics.py'
text = read(path)
old_assert = '        self.assertIn("Não aplicável ao score", output)\n'
new_assert = '        self.assertIn("não significa que a dimensão inteira saiu do SARI", output)\n        self.assertIn("BR-GEO-034", output)\n'
if old_assert not in text:
    raise SystemExit('old structured-data semantic assertion not found')
text = text.replace(old_assert, new_assert, 1)
old_wording = '        self.assertIn("ausência, não falha de coleta", output)\n'
new_wording = '        self.assertIn("ausência é uma lacuna leve, não falha de coleta", output)\n'
if old_wording not in text:
    raise SystemExit('old structured-data wording assertion not found')
text = text.replace(old_wording, new_wording, 1)
write(path, text)

# Historical scoring-version persistence remains testable, but the unpublished
# versioned HTML URL is no longer generated or advertised.
path = 'tests/test_historical_scoring_report_contract.py'
text = read(path)
pattern = r'def test_current_004_scoring_report_creates_compatibility_alias_only\(\) -> None:.*?(?=\n\ndef test_report_manifest_exposes_version_axes_without_score_or_evidence_payloads)'
replacement = '''def test_current_004_scoring_report_uses_only_canonical_prepublication_surface() -> None:\n    install()\n    with tempfile.TemporaryDirectory() as directory:\n        workspace = _workspace(Path(directory) / "AUD-CURRENT", "SCORE-GEO-004")\n        before = _sha256(workspace.database)\n        path = write_score_geo_004_report(audit_id="AUD-HIST", workspace=workspace)\n        alias = path.parent / LEGACY_REPORT_FILE\n        after = _sha256(workspace.database)\n        html = path.read_text(encoding="utf-8")\n        assert "SCORE-GEO-004" in html\n        assert "VIGENTE" in html\n        assert "O que entra no score" in html\n        assert "O que não entra automaticamente no score" in html\n        assert not alias.exists()\n        assert before == after\n\n\n'''
text, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
if count != 1:
    raise SystemExit(f'historical current-004 test replacement count={count}')
old_alias_assert = '        assert payload["aliases"] == {"score-geo-004.html": "scoring.html"}\n'
if old_alias_assert not in text:
    raise SystemExit('manifest alias assertion not found')
text = text.replace(old_alias_assert, '        assert payload["aliases"] == {}\n', 1)
write(path, text)

# Navigation cleans up the stale development alias instead of trying to normalize it.
path = 'tests/test_report_navigation.py'
text = read(path)
old = '            self.assertEqual(alias.read_text(encoding="utf-8"), alias_html)\n            self.assertIn("<aside class=\'app-nav\'", (report_dir / "index.html").read_text(encoding="utf-8"))\n'
new = '            self.assertFalse(alias.exists())\n            self.assertIn("<aside class=\'app-nav\'", (report_dir / "index.html").read_text(encoding="utf-8"))\n'
if old not in text:
    raise SystemExit('navigation stale alias assertion not found')
text = text.replace(old, new, 1)
write(path, text)

print('visual semantics fixup applied')
