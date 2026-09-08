from pathlib import Path
import re

ROOT = Path('.')

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding='utf-8', newline='\n')

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one occurrence, found {count}')
    return text.replace(old, new, 1)

# 1) Public report contract: no development-only versioned alias; device pages may show a read-only scorecard mirror.
path = 'src/rasai/report_contract.py'
text = read(path)
text = replace_once(text, '        aliases=("score-geo-004.html",),\n', '        aliases=(),\n', 'remove scoring alias')
text = text.replace('        outputs=("findings e evidências Mobile",),', '        outputs=("scorecard de contexto read-only", "findings e evidências Mobile"),')
text = text.replace('        outputs=("findings e evidências Desktop",),', '        outputs=("scorecard de contexto read-only", "findings e evidências Desktop"),')
write(path, text)

# 2) Shared contract cards: visually delimit each dependency/input/output block.
path = 'src/rasai/report_registry.py'
text = read(path)
text = replace_once(text,
    '        f"<h2>{escape(surface.label)}: inputs, outputs e dependências</h2>"\n        "<div class=\'grid\'>"\n',
    '        f"<h2>{escape(surface.label)}: inputs, outputs e dependências</h2>"\n        "<div class=\'report-contract-grid\'>"\n',
    'contract grid class')
for label in ('Inputs','Outputs','Dependências obrigatórias','Dependências opcionais','Uso de IA','Impacto no SARI/SCORE','Fonte de verdade'):
    old = f'f"<div><h3>{label}</h3><p>'
    new = f'f"<div class=\'report-contract-item\'><h3>{label}</h3><p>'
    if old not in text:
        raise SystemExit(f'contract item not found: {label}')
    text = text.replace(old, new, 1)
write(path, text)

# 3) Shared site CSS for contract-area delimiters.
path = 'src/rasai/report_site.py'
text = read(path)
css_marker = '.remediation-grid strong{font-size:.82rem;overflow-wrap:anywhere}\n'
css_add = """.report-contract-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px;align-items:stretch}.report-contract-item{min-width:0;border:1px solid var(--line);border-radius:10px;background:#fbfcfe;padding:13px 14px;box-shadow:inset 0 1px 0 rgba(255,255,255,.75)}.report-contract-item h3{margin:0 0 .45rem;font-size:.88rem;color:#2d3b52}.report-contract-item p{margin:0;color:#4b5565;overflow-wrap:anywhere}.report-contract-item code{overflow-wrap:anywhere}.report-reading-governance{margin-top:16px}\n@media(max-width:1180px){.report-contract-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n@media(max-width:700px){.report-contract-grid{grid-template-columns:1fr}}\n"""
if css_add.strip() not in text:
    text = replace_once(text, css_marker, css_marker + css_add, 'site contract css')
write(path, text)

# 4) Four-state score semantics, reusable in Readiness and device scorecards; fix stale Structured Data wording.
path = 'src/rasai/report_semantics.py'
text = read(path)
semantic_css_marker = '@media(max-width:1120px){.indicator-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}'
semantic_css_add = """
.score-condition-tag{display:inline-flex;margin-left:7px;padding:2px 7px;border-radius:999px;font-size:.66rem;font-weight:760;line-height:1.3;vertical-align:middle;white-space:nowrap}.score-condition-tag.expected{background:rgba(95,150,116,.16);color:#3f7452}.score-condition-tag.near{background:rgba(182,138,80,.18);color:#855f2c}.score-condition-tag.below{background:rgba(169,111,56,.18);color:#815126}.score-condition-tag.critical{background:rgba(191,111,112,.18);color:#98494c}.score-condition-tag.neutral{background:rgba(101,127,198,.14);color:#4d65a0}
tr.score-condition-expected{background:rgba(95,150,116,.06)}tr.score-condition-near{background:rgba(182,138,80,.08)}tr.score-condition-below{background:rgba(169,111,56,.08)}tr.score-condition-critical{background:rgba(191,111,112,.08)}tr.score-condition-neutral{background:rgba(101,127,198,.06)}
tr.score-condition-expected>td:first-child{box-shadow:inset 4px 0 0 var(--green)}tr.score-condition-near>td:first-child{box-shadow:inset 4px 0 0 var(--amber)}tr.score-condition-below>td:first-child{box-shadow:inset 4px 0 0 #a96f38}tr.score-condition-critical>td:first-child{box-shadow:inset 4px 0 0 var(--red)}tr.score-condition-neutral>td:first-child{box-shadow:inset 4px 0 0 var(--blue)}
.score-condition-legend{display:flex;gap:8px;flex-wrap:wrap;margin:9px 0 12px}.score-condition-legend .score-condition-tag{margin-left:0}
.apdex-class{display:inline-flex;padding:2px 8px;border-radius:999px;font-size:.7rem;font-weight:760;white-space:nowrap}.apdex-class-satisfied{background:rgba(95,150,116,.16);color:#3f7452}.apdex-class-tolerating{background:rgba(205,161,60,.18);color:#7b5a10}.apdex-class-frustrated{background:rgba(191,111,112,.18);color:#98494c}.apdex-class-excluded{background:#eef0f3;color:#596274}
"""
if semantic_css_add.strip() not in text:
    text = replace_once(text, semantic_css_marker, semantic_css_add + semantic_css_marker, 'semantic score css')

new_score_fn = r'''def _score_condition(score_text: str, confidence: str, consolidation: str) -> tuple[str, str]:
    consolidation_key = consolidation.casefold().strip()
    confidence_key = confidence.casefold().strip()
    if consolidation_key in {"não aplicável", "nao aplicavel"}:
        return "neutral", "Não aplicável"
    value = _first_number(score_text)
    if value is None:
        return "neutral", "Sem medição conclusiva"
    if value < 40:
        return "critical", "Crítico"
    if value < 75:
        return "below", "Abaixo do esperado"
    if consolidation_key != "consolidado" or confidence_key == "baixa":
        return "near", "Quase no esperado"
    return "expected", "Dentro do esperado"


def _enhance_score_page(html: str) -> str:
    low_rows: list[tuple[str, str]] = []

    def row_replace(match: re.Match[str]) -> str:
        dimension = unescape(match.group("dimension")).strip()
        score = match.group("score").strip()
        coverage = match.group("coverage").strip()
        confidence = unescape(match.group("confidence")).strip()
        consolidation = unescape(match.group("consolidation")).strip()
        attrs = _strip_result_state(match.group("attrs"))
        state, label = _score_condition(score, confidence, consolidation)
        if confidence.casefold() == "baixa":
            low_rows.append((dimension, coverage))
        if dimension.casefold() == "dados estruturados" and consolidation.casefold() == "não aplicável":
            coverage = "-"
            confidence = "Não aplicável"
        tag = f" <span class='score-condition-tag {state}'>{escape(label)}</span>"
        return (
            f"<tr{attrs} class='score-condition-{state}'><td>{escape(dimension)}</td>"
            f"<td>{score}{tag}</td><td>{coverage}</td><td>{escape(confidence)}</td><td>{escape(consolidation)}</td></tr>"
        )

    html = _DIMENSION_ROW_RE.sub(row_replace, html)
    if "score-condition-legend" not in html:
        legend = (
            "<div class='score-condition-legend' aria-label='Legenda de condição do score'>"
            "<span class='score-condition-tag expected'>Dentro do esperado</span>"
            "<span class='score-condition-tag near'>Quase no esperado</span>"
            "<span class='score-condition-tag below'>Abaixo do esperado</span>"
            "<span class='score-condition-tag critical'>Crítico</span>"
            "<span class='score-condition-tag neutral'>Sem medição / não aplicável</span></div>"
        )
        html = re.sub(r"(<h2>Dimensões[^<]*</h2>)", r"\1" + legend, html, count=1, flags=re.IGNORECASE)
    if "score-confidence-note" not in html and "Confiança baixa" in html:
        items = "".join(f"<li><strong>{escape(name)}</strong>: coverage {escape(coverage)}.</li>" for name, coverage in low_rows)
        detail = (
            "<div class='notice warn score-confidence-note'><strong>Por que a confiança está baixa?</strong> "
            "Confidence mede completude/cobertura da avaliação, não a qualidade do site. "
            "Ela aumenta quando regras aplicáveis deixam de ficar UNKNOWN/ERROR e passam a ter resultado e evidência suficientes."
            + (f"<ul>{items}</ul>" if items else "")
            + "<span class='result-tag warn'>Não elevar artificialmente</span></div>"
        )
        html = html.replace("</header>", "</header>" + detail, 1)
    if "Dados estruturados" in html and "structured-data-absence-note" not in html:
        note = (
            "<div class='notice structured-data-absence-note'><strong>Dados estruturados: ausência é uma lacuna leve, não falha de coleta.</strong> "
            "Quando nenhum JSON-LD é observado, BR-GEO-034 permanece aplicável e recebe WARNING com fator reduzido; regras de tipos/consistência sem markup podem ficar NOT_APPLICABLE. "
            "JSON-LD válido e coerente pode melhorar a dimensão; markup inválido ou contraditório pode reduzi-la.</div>"
        )
        scorecard_end = html.find("</section>", html.find("Dimensões"))
        if scorecard_end >= 0:
            html = html[:scorecard_end] + note + html[scorecard_end:]
    return html
'''
pattern = r'def _enhance_score_page\(html: str\) -> str:.*?\n\ndef _enhance_accessibility\(html: str\) -> str:'
match = re.search(pattern, text, flags=re.DOTALL)
if not match:
    raise SystemExit('score enhancer block not found')
text = text[:match.start()] + new_score_fn + '\n\ndef _enhance_accessibility(html: str) -> str:' + text[match.end():]
write(path, text)

# 5) Keep a device-local read-only scorecard mirror instead of removing it.
path = 'src/rasai/rasai_readiness_reporting.py'
text = read(path)
new_rewrite = r'''def _rewrite_device_page(html: str, filename: str) -> str:
    label = "Mobile" if filename == "mobile.html" else "Desktop"
    marker = "data-rasai-device-role='evidence-only'"
    if marker not in html:
        notice = (
            f"<section class='notice' {marker}><strong>Papel desta página:</strong> evidências e findings {label}. "
            f"O scorecard é um espelho read-only dos mesmos scores persistidos; a interpretação canônica de SARI, Coverage, Confidence e Consolidation permanece em <a href='{RASAI_FILE}'>Search & AI Readiness</a>.</section>"
        )
        html = html.replace("</header>", "</header>" + notice, 1)
    html = html.replace("Relatório por dispositivo", "Evidências por dispositivo")
    return html
'''
pattern = r'def _rewrite_device_page\(html: str, filename: str\) -> str:.*?\n\ndef _dashboard\('
match = re.search(pattern, text, flags=re.DOTALL)
if not match:
    raise SystemExit('rewrite device function not found')
text = text[:match.start()] + new_rewrite + '\n\ndef _dashboard(' + text[match.end():]
write(path, text)

# 6) Apdex persisted sample class uses the semantic class palette without inventing a fourth Apdex class.
path = 'src/rasai/m23_reporting.py'
text = read(path)
helper = r'''def _apdex_class_badge(value: Any) -> str:
    raw = str(value or "EXCLUÍDA").upper()
    mapping = {
        "SATISFIED": ("satisfied", "Satisfied"),
        "TOLERATING": ("tolerating", "Tolerating"),
        "FRUSTRATED": ("frustrated", "Frustrated"),
    }
    css, label = mapping.get(raw, ("excluded", "Excluída"))
    return f"<span class='apdex-class apdex-class-{css}'>{escape(label)}</span>"


'''
if 'def _apdex_class_badge' not in text:
    text = replace_once(text, 'def _sample_row(row: sqlite3.Row) -> str:\n', helper + 'def _sample_row(row: sqlite3.Row) -> str:\n', 'apdex helper insertion')
text = replace_once(text,
    '        f"<td>{escape(str(row[\'classification\'] or \'EXCLUÍDA\'))}</td>"\n',
    '        f"<td>{_apdex_class_badge(row[\'classification\'])}</td>"\n',
    'apdex class cell')
write(path, text)

# 7) Development-only compatibility alias: stop materializing it and make scoring.html the only current report file.
path = 'src/rasai/score_geo_004_reporting.py'
text = read(path)
text = text.replace('# Public URLs are version-neutral. Method versions live in persisted metadata and\n# in the rendered content. The versioned 004 path is compatibility-only.\n', '# Public URLs are version-neutral. Method versions live in persisted metadata and\n# in the rendered content. This pre-publication build exposes only the canonical path.\n')
text = text.replace('    if effective_version == SCORING_VERSION:\n        _write_legacy_alias(report_dir)\n    else:\n        # A versioned 004 alias on a historical AUD would falsely imply that\n        # the historical audit was scored with 004. Report files are projections,\n        # so removing only this compatibility alias does not mutate audit evidence.\n        (report_dir / LEGACY_REPORT_FILE).unlink(missing_ok=True)\n    return path\n', '    # Pre-publication development contract: keep only the canonical version-neutral surface.\n    (report_dir / LEGACY_REPORT_FILE).unlink(missing_ok=True)\n    return path\n')
text = re.sub(r'\n\ndef _write_legacy_alias\(report_dir: Path\) -> Path:.*?\n\ndef _scoring_versions', '\n\ndef _scoring_versions', text, flags=re.DOTALL)
text = text.replace('<div><h3>Comparabilidade histórica</h3><p>Somente séries com metodologia compatível. 002, 003 e 004 não são misturados como se fossem o mesmo método.</p></div>', '<div><h3>Contrato vigente</h3><p>Esta build de desenvolvimento publica somente o contrato vigente da auditoria. A versão continua persistida em <code>scoring_version</code>.</p></div>')
text = text.replace('<section class=\'panel\'><h2>Contrato do arquivo</h2><p><code>{REPORT_FILE}</code> é o endereço canônico e estável. A versão metodológica pertence a <code>scoring_version</code>, banco, manifests, metadados e conteúdo. {_alias_explanation(effective_version)}</p></section>', '<section class=\'panel\'><h2>Contrato do arquivo</h2><p><code>{REPORT_FILE}</code> é o único endereço canônico desta build de desenvolvimento. A versão metodológica pertence a <code>scoring_version</code>, banco, manifests, metadados e conteúdo.</p></section>')
write(path, text)

# 8) Public contract gate now requires no aliases in the unpublished build.
path = 'src/rasai/public_contract_gate.py'
text = read(path)
text = text.replace('from rasai.score_geo_004_reporting import LEGACY_REPORT_FILE, REPORT_FILE\n', 'from rasai.score_geo_004_reporting import REPORT_FILE\n')
text = text.replace('    if LEGACY_REPORT_FILE in nav_filenames:\n        errors.append("alias versionado está na navegação canônica")\n', '')
text = text.replace('    if REPORT_ALIASES.get("score-geo-004.html") != "scoring.html":\n        errors.append("alias score-geo-004.html não aponta para scoring.html")\n', '    if REPORT_ALIASES:\n        errors.append("build pré-publicação não deve expor aliases históricos de report")\n')
write(path, text)

# 9) Existing tests: device pages now retain a read-only scorecard; registry no longer exposes a compatibility alias.
path = 'tests/test_rasai_readiness_reporting.py'
text = read(path)
text = text.replace('            assert "<div class=\\"score-grid\\">" not in html\n            assert "<div class=\'kicker\'>Scorecard</div>" not in html\n', '            assert "score-grid" in html\n            assert "<div class=\'kicker\'>Scorecard</div>" in html\n            assert "espelho read-only" in html\n')
write(path, text)

path = 'tests/test_report_registry_and_method_docs.py'
text = read(path)
text = text.replace('from rasai.score_geo_004_reporting import LEGACY_REPORT_FILE, REPORT_FILE, _write_legacy_alias\n', 'from rasai.score_geo_004_reporting import LEGACY_REPORT_FILE, REPORT_FILE\n')
text = text.replace('        assert not any(filename == LEGACY_REPORT_FILE for _, filename in CANONICAL_NAV_ITEMS)\n', '        assert not any(filename == LEGACY_REPORT_FILE for _, filename in CANONICAL_NAV_ITEMS)\n')
# Remove any direct legacy-alias writer test block if present.
text = re.sub(r'\n\ndef test_legacy_alias.*?(?=\n\ndef |\Z)', '\n', text, flags=re.DOTALL)
write(path, text)

# 10) New focused regression tests.
new_test = r'''from pathlib import Path

from rasai.report_semantics import enhance_report_html
from rasai.report_contract import REPORT_ALIASES, surface_by_id
from rasai.m23_reporting import _apdex_class_badge


def test_score_rows_use_four_state_visual_language(tmp_path: Path) -> None:
    html = """<h2>Dimensões Mobile</h2><table><tbody>
    <tr><td>A</td><td>92.0</td><td>100%</td><td>Alta</td><td>Consolidado</td></tr>
    <tr><td>B</td><td>88.0</td><td>67%</td><td>Baixa</td><td>Parcial</td></tr>
    <tr><td>C</td><td>62.0</td><td>100%</td><td>Alta</td><td>Consolidado</td></tr>
    <tr><td>D</td><td>35.0</td><td>100%</td><td>Alta</td><td>Consolidado</td></tr>
    </tbody></table>"""
    rendered = enhance_report_html(html, page_name="mobile.html", report_dir=tmp_path)
    assert "score-condition-expected" in rendered
    assert "score-condition-near" in rendered
    assert "score-condition-below" in rendered
    assert "score-condition-critical" in rendered
    assert "Dentro do esperado" in rendered and "Quase no esperado" in rendered


def test_structured_data_note_matches_current_scoring_contract(tmp_path: Path) -> None:
    html = "<h2>Dimensões Mobile</h2><table><tbody><tr><td>Dados estruturados</td><td>80.0</td><td>100%</td><td>Alta</td><td>Consolidado</td></tr></tbody></table>"
    rendered = enhance_report_html(html, page_name="mobile.html", report_dir=tmp_path)
    assert "BR-GEO-034" in rendered
    assert "lacuna leve" in rendered
    assert "não reduz o Overall" not in rendered


def test_apdex_class_badges_preserve_apdex_classes() -> None:
    assert "apdex-class-satisfied" in _apdex_class_badge("SATISFIED")
    assert "apdex-class-tolerating" in _apdex_class_badge("TOLERATING")
    assert "apdex-class-frustrated" in _apdex_class_badge("FRUSTRATED")
    assert "apdex-class-excluded" in _apdex_class_badge(None)


def test_prepublication_report_contract_has_no_historical_aliases() -> None:
    assert REPORT_ALIASES == {}
    assert surface_by_id("scoring").aliases == ()
    assert "scorecard de contexto read-only" in surface_by_id("mobile").outputs
'''
write('tests/test_visual_semantics_refinement_20260908.py', new_test)

# 11) Documentation: remove the development-only versioned alias from current docs and record the pre-publication decision.
for doc in [ROOT / 'README.md', *(ROOT / 'docs').rglob('*.md')]:
    if not doc.is_file():
        continue
    body = doc.read_text(encoding='utf-8')
    if 'score-geo-004.html' in body:
        lines = []
        for line in body.splitlines():
            if 'score-geo-004.html' in line:
                # The versioned path was only an unpublished compatibility alias; omit it from current contracts.
                continue
            lines.append(line)
        body = '\n'.join(lines) + ('\n' if body.endswith('\n') else '')
        doc.write_text(body, encoding='utf-8', newline='\n')

path = 'docs/REPORT_GUIDE.md'
text = read(path)
append = """

### Semântica visual compartilhada

Scorecards do SARI e das páginas Mobile/Desktop usam a mesma linguagem visual de condição: dentro do esperado, quase no esperado, abaixo do esperado e crítico. A cor nunca substitui o texto, Score, Coverage, Confidence ou Consolidation.

Nas amostras persistidas do Synthetic Navigation Apdex, a coluna Classe usa as três classes do próprio Apdex: Satisfied, Tolerating e Frustrated; tentativas excluídas permanecem neutras. O RASAi não cria uma quarta classe Apdex apenas para completar uma paleta visual.

Os contratos de superfície usam cartões delimitados para separar inputs, outputs, dependências, uso de IA, impacto no score e fonte de verdade.

Durante a fase pré-publicação, `scoring.html` é a única superfície de metodologia. Não são mantidos aliases históricos de HTML que nunca foram publicados externamente.
"""
if '### Semântica visual compartilhada' not in text:
    text += append
write(path, text)

path = 'docs/specification/10_DECISIONS.md'
text = read(path)
append = """

### D-043 - Pré-publicação: superfície única e sem aliases históricos

Enquanto o RASAi permanecer em desenvolvimento local e sem publicação externa, a superfície pública de metodologia é somente `report/scoring.html`. Aliases HTML versionados criados apenas durante o desenvolvimento não são preservados como contrato de compatibilidade. `scoring_version` continua obrigatório no banco, manifests, metadados e conteúdo para rastreabilidade metodológica.

A simplificação de aliases não autoriza misturar resultados produzidos por métodos diferentes. Ela apenas remove compatibilidade de URL que nunca foi publicada.

Scorecards SARI/por dispositivo devem usar semântica visual compartilhada e textual, e o Apdex deve colorir suas classes próprias sem inventar novas classes metodológicas.
"""
if '### D-043 - Pré-publicação: superfície única e sem aliases históricos' not in text:
    text += append
write(path, text)

print('visual semantics refinement applied')
