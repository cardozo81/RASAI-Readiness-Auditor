from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path: str, replacements: dict[str, str]) -> None:
    target = ROOT / path
    text = target.read_text(encoding='utf-8')
    for old, new in replacements.items():
        text = text.replace(old, new)
    target.write_text(text, encoding='utf-8', newline='\n')


patch('src/searchgeo/report_navigation.py', {
    'Análise Análise semântica por IA, roteamento e telemetria': 'Análise semântica por IA',
    'Remediação Sugestões e remediação de conteúdo por IA': 'Remediação textual por IA',
    '("Relatório Mobile", "mobile.html")': '("Evidências Mobile", "mobile.html")',
    '("Relatório Desktop", "desktop.html")': '("Evidências Desktop", "desktop.html")',
})

# Behavioral wording changed intentionally: explicit provider NONE is not a
# missing credential/configuration state.
patch('tests/test_m7_semantic_provider.py', {
    'self.assertIn("AI_NOT_CONFIGURED", persistence.audits.get(audit.audit_id).limitations)':
    'self.assertIn("AI_DISABLED_BY_CONFIGURATION", persistence.audits.get(audit.audit_id).limitations)'
})

# Public report wording must no longer expose delivery identifiers.
patch('tests/test_report_navigation.py', {
    'self.assertIn("Análise M18 0.01000000 USD + Remediação M20 0.00250000 USD", html)':
    'self.assertIn("Análise semântica por IA 0.01000000 USD + Remediação textual por IA 0.00250000 USD", html)'
})
