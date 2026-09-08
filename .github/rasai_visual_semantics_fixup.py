from pathlib import Path
import re

ROOT = Path('.')

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding='utf-8', newline='\n')

# Keep the current JSON-LD semantics while retaining the useful user-facing phrase.
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

# The old test treated the whole Structured Data dimension as non-scoring when JSON-LD was absent.
# Current SCORE-GEO-004 keeps BR-GEO-034 applicable as a modest WARNING, so assert the new contract.
path = 'tests/test_report_semantics.py'
text = read(path)
old_assert = '        self.assertIn("Não aplicável ao score", output)\n'
new_assert = '        self.assertIn("não significa que a dimensão inteira saiu do SARI", output)\n        self.assertIn("BR-GEO-034", output)\n'
if old_assert not in text:
    raise SystemExit('old structured-data semantic assertion not found')
text = text.replace(old_assert, new_assert, 1)
write(path, text)

print('visual semantics fixup applied')
