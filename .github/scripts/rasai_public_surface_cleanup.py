from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old in text:
        p.write_text(text.replace(old, new), encoding='utf-8', newline='\n')

# Avoid release/version language for a product that has not published a commercial version.
for path in [Path('README.md'), *Path('docs').rglob('*.md'), *Path('src/searchgeo').rglob('*.py')]:
    if not path.is_file():
        continue
    text = path.read_text(encoding='utf-8')
    updated = text.replace('Nesta versão', 'Na implementação atual').replace('nesta versão', 'na implementação atual')
    if updated != text:
        path.write_text(updated, encoding='utf-8', newline='\n')

# Shared report navigation: keep internal software_version parameter for API compatibility,
# but do not expose the package build number as a public product version in HTML.
path = Path('src/searchgeo/report_navigation.py')
text = path.read_text(encoding='utf-8')
text = text.replace('from searchgeo import __version__\n', '')
text = text.replace('    """Render the canonical report menu with version, timestamp and active item."""', '    """Render the canonical report menu with timestamp and active item."""')
text = text.replace('    version = software_version or __version__\n', '')
text = text.replace('        f"<small>Versão {escape(version)}</small>"\n', '')
text = text.replace('    version = software_version or __version__\n', '')
text = text.replace('            software_version=version,\n', '            software_version=software_version,\n')
path.write_text(text, encoding='utf-8', newline='\n')

# Interactive console: do not advertise the internal package version in the public header.
path = Path('src/searchgeo/console_runtime.py')
text = path.read_text(encoding='utf-8')
text = text.replace('from searchgeo import __version__\n', '')
text = text.replace('    print(f"{PRODUCT_DISPLAY_NAME} | versão {__version__}")', '    print(PRODUCT_DISPLAY_NAME)')
path.write_text(text, encoding='utf-8', newline='\n')

# Documentation: keep --version as a technical diagnostic command, but do not present it as a public release identifier.
replace('docs/CLI_REFERENCE.md', '- `--version` — versão do RASAi quando exposta pelo router principal.', '- `--version` — identificador técnico do pacote quando necessário para diagnóstico; não representa uma versão comercial divulgada do produto.')

# Remove release-evolution phrasing around current scoring identifiers.
replace('docs/SCORING_GUIDE.md', '## Versão vigente', '## Método de scoring')
replace('docs/RULES_GUIDE.md', 'O guia de regras **não define a versão vigente de cálculo por coluna local**. A referência atual é:', 'O guia de regras referencia o método de scoring aplicado:')
replace('docs/SCORE_GEO_003.md', 'Versão inicial:', 'Parâmetros do contrato:')
replace('docs/specification/05_SCORING_MODEL.md', 'A versão `003` introduz calibração empírica somente no `OVERALL_READINESS`. As dimensões permanecem determinísticas, evidence-backed e reprodutíveis.', 'O `SCORE-GEO-003` aplica calibração empírica somente no `OVERALL_READINESS`. As dimensões permanecem determinísticas, evidence-backed e reprodutíveis.')

# Test contract for report metadata now verifies that no public product version is rendered.
replace('tests/test_report_navigation.py', '                self.assertIn("Versão 9.9.9", html)', '                self.assertNotIn("Versão 9.9.9", html)')

# Public version-display invariant.
for path in Path('src/searchgeo').rglob('*.py'):
    text = path.read_text(encoding='utf-8')
    if '<small>Versão {escape(version)}</small>' in text:
        raise SystemExit(f'public report version label remains in {path}')

nav_test = Path('tests/test_report_navigation.py').read_text(encoding='utf-8')
assert 'self.assertNotIn("Versão 9.9.9", html)' in nav_test
