from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace(path: str, old: str, new: str, *, required: bool = True) -> None:
    text = read(path)
    if old not in text:
        if required:
            raise RuntimeError(f"anchor not found in {path}: {old[:120]!r}")
        return
    write(path, text.replace(old, new))


# 1) Avoid translating a value twice: translate normal visible prose first and
# then run the exact-cell fallback. code/pre/script/style remain untouched.
replace(
    "src/rasai/report_presentation.py",
    '''    html = _VISIBLE_VALUE_RE.sub(isolated, html)\n    parts = _TAG_SPLIT_RE.split(html)\n    blocked_depth = 0\n    output: list[str] = []\n    for part in parts:\n        if part.startswith("<"):\n            lowered = part.lower()\n            if re.match(r"<(script|style|pre|code)\\b", lowered):\n                blocked_depth += 1\n            elif re.match(r"</(script|style|pre|code)\\b", lowered):\n                blocked_depth = max(0, blocked_depth - 1)\n            output.append(part)\n            continue\n        if blocked_depth:\n            output.append(part)\n            continue\n        output.append(_PUBLIC_TOKEN_RE.sub(lambda match: _PUBLIC_LABELS[match.group(1)], part))\n    return "".join(output)\n''',
    '''    parts = _TAG_SPLIT_RE.split(html)\n    blocked_depth = 0\n    output: list[str] = []\n    for part in parts:\n        if part.startswith("<"):\n            lowered = part.lower()\n            if re.match(r"<(script|style|pre|code)\\b", lowered):\n                blocked_depth += 1\n            elif re.match(r"</(script|style|pre|code)\\b", lowered):\n                blocked_depth = max(0, blocked_depth - 1)\n            output.append(part)\n            continue\n        if blocked_depth:\n            output.append(part)\n            continue\n        output.append(_PUBLIC_TOKEN_RE.sub(lambda match: _PUBLIC_LABELS[match.group(1)], part))\n    return _VISIBLE_VALUE_RE.sub(isolated, "".join(output))\n''',
)

# 2) The canonical report contract is the only menu source. Several older
# generators still mutate NAV_ITEMS as an implementation detail; rendering must
# not depend on import order or on those side effects.
replace(
    "src/rasai/report_navigation.py",
    '''    return tuple(\n        (label, filename)\n        for label, filename in NAV_ITEMS\n        if (report_dir / filename).is_file() or filename == current\n    )\n''',
    '''    return tuple(\n        (label, filename)\n        for label, filename in CANONICAL_NAV_ITEMS\n        if (report_dir / filename).is_file() or filename == current\n    )\n''',
)
replace(
    "src/rasai/report_navigation.py",
    '''    final_generated_at = generated_at or datetime.now(BRASILIA_TIMEZONE)\n    _ensure_premium_css(report_dir)\n''',
    '''    global NAV_ITEMS\n    NAV_ITEMS = CANONICAL_NAV_ITEMS\n    final_generated_at = generated_at or datetime.now(BRASILIA_TIMEZONE)\n    _ensure_premium_css(report_dir)\n''',
)

# 3) Tests must assert the canonical contract, not mutable module state left by
# report installers. The prose-humanization expectation follows the user-facing
# requirement while preserving technical code/pre identifiers.
replace(
    "tests/test_report_navigation.py",
    "from rasai.report_navigation import NAV_ITEMS, normalize_report_navigation\n",
    "from rasai.report_contract import CANONICAL_NAV_ITEMS\nfrom rasai.report_navigation import normalize_report_navigation\n",
)
replace(
    "tests/test_report_navigation.py",
    "filenames = [filename for _, filename in NAV_ITEMS]",
    "filenames = [filename for _, filename in CANONICAL_NAV_ITEMS]",
)
replace(
    "tests/test_report_navigation.py",
    "expected = [(filename, label) for label, filename in NAV_ITEMS]",
    "expected = [(filename, label) for label, filename in CANONICAL_NAV_ITEMS]",
)
replace(
    "tests/test_report_navigation.py",
    '''            self.assertLess(hrefs.index("content-suggestions.html"), hrefs.index("accessibility.html"))\n            self.assertLess(hrefs.index("accessibility.html"), hrefs.index("web-performance.html"))\n''',
    '''            self.assertLess(hrefs.index("accessibility.html"), hrefs.index("web-performance.html"))\n            self.assertLess(hrefs.index("web-performance.html"), hrefs.index("content-suggestions.html"))\n''',
)
replace(
    "tests/test_report_presentation.py",
    '''        rendered = humanize_report_html(html, page_name="references.html")\n\n        self.assertEqual(rendered, html)\n''',
    '''        rendered = humanize_report_html(html, page_name="references.html")\n\n        self.assertIn("<p>Estado persistido: Indisponível.</p>", rendered)\n        self.assertIn("<code>NOT_CONSOLIDATED</code>", rendered)\n        self.assertIn('<pre>{"status": "FAILED", "reason_code": "HTTP_429"}</pre>', rendered)\n        self.assertIn("<td>BR-GEO-054</td>", rendered)\n        self.assertIn("<td>HTTP_429</td>", rendered)\n        self.assertIn("<td>SCORE-GEO-004</td>", rendered)\n''',
)
replace(
    "tests/test_consolidation_reporting_ux.py",
    'self.assertEqual(manifest["report_format_version"], "CONS-2")',
    'self.assertEqual(manifest["report_format_version"], "CONS-3")',
)

# 4) Current report tree in the reader guide must mirror the actual menu order.
report_guide = read("docs/REPORT_GUIDE.md")
old_tree = '''├─ mobile.html                 # condicional\n├─ desktop.html                # condicional\n├─ remediation.html\n├─ content-suggestions.html\n├─ crawling-discovery.html     # condicional\n├─ accessibility.html          # condicional\n├─ web-performance.html        # condicional\n├─ apdex.html                  # condicional\n├─ apdex-experience.html       # condicional\n├─ ai-visibility.html          # condicional\n├─ observability.html          # condicional\n├─ quality.html                # condicional\n├─ ai-usage.html\n├─ references.html\n'''
new_tree = '''├─ mobile.html                 # condicional\n├─ desktop.html                # condicional\n├─ crawling-discovery.html     # condicional\n├─ accessibility.html          # condicional\n├─ web-performance.html        # condicional\n├─ apdex.html                  # condicional\n├─ apdex-experience.html       # condicional\n├─ content-suggestions.html\n├─ remediation.html\n├─ ai-usage.html\n├─ ai-visibility.html          # condicional\n├─ observability.html          # condicional\n├─ quality.html                # condicional\n├─ references.html\n'''
if old_tree not in report_guide:
    raise RuntimeError("REPORT_GUIDE tree anchor not found")
report_guide = report_guide.replace(old_tree, new_tree, 1)
report_guide = report_guide.replace(
    "identificadores históricos de scoring",
    "identificadores de propostas anteriores de scoring usadas durante o desenvolvimento",
)
write("docs/REPORT_GUIDE.md", report_guide)

# 5) Consolidated validation documentation was tied to an implementation branch
# and CONS-2. Replace it with the current main/development contract.
write(
    "docs/CONSOLIDATED_REPORTING_VALIDATION.md",
    '''# Validação e reversibilidade - relatórios consolidados\n\n## Estado atual\n\nO relatório consolidado faz parte do baseline de desenvolvimento em `main`. Este documento descreve o contrato que deve permanecer verdadeiro antes da aprovação de uma versão publicável do RASAi; referências a branches/PRs usados durante a implementação não definem o comportamento do produto.\n\nFormato atual:\n\n```text\nCONS-3\n```\n\nA alteração do identificador de formato invalida dedupe de snapshots produzidos com estruturas anteriores de desenvolvimento quando a semântica do HTML/manifest não é equivalente. Isso é controle interno de reprodutibilidade, não histórico de releases públicas.\n\n## Fonte de verdade e escrita\n\nAs fontes são os `AUD-*/audit.db`, abertos em modo somente leitura (`SQLite mode=ro` e `PRAGMA query_only=ON`). A consolidação não recalcula auditorias e não grava nos bancos fonte.\n\nArtefatos derivados:\n\n```text\n.rasai/consolidated-index.db\nconsolidated/CONS-*/report.html\nconsolidated/CONS-*/manifest.json\n```\n\nO índice consolidado é reconstruível.\n\n## Contrato comportamental CONS-3\n\n- resumo executivo de SARI informa pontuação, Cobertura, Confiança e estado de Consolidação;\n- score não consolidado é identificado como pontuação parcial, não como SARI consolidado;\n- a dimensão atual mais fraca é lida do mesmo `audit_id` do Overall atual;\n- séries SARI exigem mesma `scoring_version` e mesmo fingerprint do universo completo de URLs;\n- filtro parcial de URL não recebe score calculado com URLs que ficaram fora do filtro;\n- mudança de método de scoring permanece segmentada e não é normalizada silenciosamente;\n- Lighthouse/lab e Core Web Vitals/field continuam domínios distintos;\n- Apdex só é agregado entre mesmo perfil e mesmo `T`, ponderado por amostras válidas;\n- grupos `small_group` sem grupo final permanecem diagnósticos de base insuficiente;\n- evolução de findings usa **ocorrências por URL auditada** como série comportamental; contagem bruta é apenas contexto;\n- dado ausente não vira zero;\n- extremos não são eliminados automaticamente por valor;\n- estados acionáveis seguem a mesma semântica visual dos relatórios individuais;\n- métodos anteriores encontrados em bases de teste são referências de desenvolvimento não comparáveis ao `SCORE-GEO-004`, salvo quando o próprio contrato de comparabilidade provar o contrário.\n\n## Estatística e comparabilidade\n\n### Readiness Search & AI\n\nUma série numérica é agregada somente na combinação compatível mais recente de:\n\n```text\nscoring_version\n+\nfingerprint do conjunto completo de URLs da auditoria\n```\n\n`scoring_version` é apresentado ao usuário como **Versão do método de pontuação**.\n\n### Média, mediana e extremos\n\n- média = média aritmética das observações elegíveis;\n- mediana = valor central das observações elegíveis;\n- mínimo/máximo são preservados;\n- não há trimming, winsorization nem descarte automático por IQR/desvio-padrão;\n- `NULL`/ausência de dado não é imputado como zero.\n\n### Desempenho Web\n\nPara estados Inicial/Atual de métricas por URL, a consolidação usa a média transversal da observação válida mais antiga/recente de cada URL elegível, evitando que a URL mais frequentemente auditada represente sozinha o domínio.\n\n### Apdex\n\nO agregado exige mesmo perfil sintético e mesmo limiar `T`. O valor é ponderado por amostras válidas. Coeficiente de variação é diagnóstico de estabilidade e não entra na fórmula Apdex. Consulte [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md).\n\n### Ocorrências\n\nFindings não recalculam SCORE-GEO. Para comparar auditorias de escopos diferentes, o gráfico comportamental usa `quantidade de findings / quantidade de URLs auditadas`. A contagem absoluta permanece disponível para dimensionar volume operacional.\n\n## Metodologia e transparência\n\nO HTML mostra somente versões realmente persistidas nas fontes selecionadas. `SCORE-GEO-004` é o contrato vigente para novas auditorias. Dados criados por propostas anteriores durante o desenvolvimento permanecem identificados por sua `scoring_version` e não são apresentados como versões públicas anteriormente lançadas.\n\nO consolidado não deve afirmar validação externa do SARI/SCORE-GEO como preditor de ranking/citação. Fontes públicas sustentam métricas/domínios específicos, não homologam o índice proprietário.\n\n## Dedupe\n\nExige igualdade de:\n\n```text\nreport_format_version\n+ filtros canônicos\n+ conjunto/fingerprint dos AUDs elegíveis\n```\n\nAssim:\n\n- mesma requisição + mesmas fontes: pode reutilizar;\n- novo AUD elegível: novo snapshot;\n- mudança de filtro: novo snapshot;\n- mudança de formato: novo snapshot.\n\n## Gates automatizados\n\nWorkflow principal da feature consolidada:\n\n```text\n.github/workflows/consolidated-reporting-ci.yml\n```\n\nO gate deve cobrir, no mínimo:\n\n- geração read-only e hash dos `audit.db` inalterado;\n- dedupe e invalidação por novo AUD/filtro/formato;\n- segregação de método e universo de URLs;\n- Snapshot com `N=1` sem falsa tendência;\n- série histórica somente quando comparável;\n- Apdex com regra de perfil + `T`;\n- findings normalizados por URL;\n- HTML/manifest com metodologia e limitações;\n- regressões do console/configuração;\n- contrato público de relatórios.\n\n## Smoke humano\n\nApós atualizar o checkout local de `main`:\n\n1. abrir `iniciar.cmd`;\n2. confirmar navegação normal do console;\n3. gerar consolidado com 1 AUD e confirmar **Snapshot**;\n4. gerar com 2 AUDs comparáveis e confirmar comparação sem afirmar tendência robusta;\n5. gerar com 3+ AUDs comparáveis e validar gráfico/matriz;\n6. conferir SARI, Cobertura, Confiança e Consolidação contra pelo menos um `audit.db`;\n7. validar Apdex e indicação de amostra pequena quando aplicável;\n8. validar evolução de ocorrências por URL e conferir o volume bruto contextual;\n9. testar pesquisa/paginação das auditorias consideradas;\n10. repetir mesmos filtros e confirmar dedupe;\n11. comparar hash do `audit.db` antes/depois;\n12. abrir o HTML com o console fechado e confirmar funcionamento estático.\n\n## Reversibilidade\n\nO consolidado é derivado. Em caso de falha, a reversão não exige migração dos `AUD-*`: os artefatos `consolidated/CONS-*` e o índice derivado podem ser reconstruídos a partir das fontes.\n\nVeja também [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md), [`REPORT_GUIDE.md`](REPORT_GUIDE.md), [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md).\n''',
)

# 6) Remove the one remaining public-doc framing that calls a development data
# store "Legacy". Technical source identifiers are deliberately not renamed.
replace(
    "docs/PRODUCT_PLATFORM_ARCHITECTURE.md",
    "### Legacy consolidated analytical cache",
    "### Cache analítico consolidado anterior de desenvolvimento",
    required=False,
)

# 7) Development-document guardrails.
for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
    text = path.read_text(encoding="utf-8")
    lowered = text.casefold()
    if "score-geo-003 permanece histórico" in lowered:
        raise RuntimeError(f"release-like scoring wording remains in {path}")
    if "cons-2" in lowered:
        raise RuntimeError(f"stale consolidated format remains in {path}")
    if "legacy consolidated analytical cache" in lowered:
        raise RuntimeError(f"legacy product framing remains in {path}")

print("RASAi report remediation follow-up applied successfully")
