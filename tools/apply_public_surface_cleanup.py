"""One-shot contextual cleanup for public RASAi surfaces.

This script deliberately does NOT perform a repository-wide scoring-version
replacement. It removes obsolete milestone labels from user-facing surfaces and
updates only files/phrases whose current-runtime context has been reviewed.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

EXACT_REPLACEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "src/rasai/m24_ai.py": (
        ("Não altere severidade, scoring, SCORE-GEO-003 ou SARI-001.", "Não altere severidade, scoring, SCORE-GEO-004 ou SARI-001."),
        ("Diagnósticos técnicos M24 persistidos:", "Diagnósticos técnicos persistidos:"),
    ),
    "src/rasai/quality/analysis.py": (
        ("SCORE-GEO-003 and must not be interpreted as another readiness score.", "SCORE-GEO-004 and must not be interpreted as another readiness score."),
    ),
    "src/rasai/m22_quality_domains.py": (
        ("does not mutate SCORE-GEO-002", "does not mutate SCORE-GEO-004"),
        ("não altera SCORE-GEO-002", "não altera SCORE-GEO-004"),
        ("m22-performance-diagnostics", "performance-diagnostics"),
        ("m22-accessibility-summary", "accessibility-summary"),
        ("m21-performance-summary", "web-performance-summary"),
        ("m22-domain-methodology", "web-quality-domain-methodology"),
    ),
    "src/rasai/rasai_readiness_reporting.py": (
        ("m21-performance-summary", "web-performance-summary"),
        ("m22-accessibility-summary", "accessibility-summary"),
        ("rasai-m23-index-start", "rasai-apdex-index-start"),
        ("rasai-m23-index-end", "rasai-apdex-index-end"),
    ),
    "src/rasai/m23_reporting.py": (
        ("rasai-m23-index-start", "rasai-apdex-index-start"),
        ("rasai-m23-index-end", "rasai-apdex-index-end"),
        ("rasai-m23-references-start", "rasai-apdex-references-start"),
        ("rasai-m23-references-end", "rasai-apdex-references-end"),
        ("rasai-m23-web-start", "rasai-apdex-web-start"),
        ("rasai-m23-web-end", "rasai-apdex-web-end"),
    ),
    "src/rasai/m20_reporting.py": (
        ("m20-content-link", "content-suggestions-link"),
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
        ("ai-usage.html#m20-ai-telemetry", "ai-usage.html#remediation-ai-telemetry"),
        ("Confidence global do SCORE-GEO-002", "Confidence global do SCORE-GEO-004"),
        (
            "<h5>Texto proposto</h5><pre>{escape(str(row['proposed_text']))}</pre>",
            "<div class='notice ai-provenance'><strong>Output gerado por IA.</strong> "
            "Este texto foi produzido pelo provider/modelo identificado abaixo a partir do finding/regra persistidos, "
            "da URL e dispositivo desta ocorrência, dos evidence_ids exibidos e do contexto editorial persistido quando aplicável. "
            "O RASAi valida o contrato da resposta, mas o conteúdo continua advisory e exige revisão humana.</div>"
            "<h5>Texto proposto pela IA</h5><pre>{escape(str(row['proposed_text']))}</pre>",
        ),
    ),
    "src/rasai/report_navigation.py": (
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
        ("Verifica a reprodutibilidade do SCORE-GEO-002 persistido.", "Verifica a reprodutibilidade do SCORE-GEO-004 persistido."),
    ),
    "src/rasai/report_semantics.py": (
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
    ),
    "src/rasai/console_cost.py": (
        ("considerando M18, retry transitório limitado, fallback AUTO e M20 quando habilitado", "considerando análise semântica, retry transitório limitado, fallback AUTO e remediação de conteúdo quando habilitada"),
        ("M20 pode acrescentar tentativas apenas quando houver findings elegíveis.", "A remediação de conteúdo por IA pode acrescentar tentativas apenas quando houver findings elegíveis."),
        ("M21: entre {min_web} e {max_web} chamada(s) externas potenciais PageSpeed/CrUX.", "Web Performance: entre {min_web} e {max_web} chamada(s) externas potenciais PageSpeed/CrUX."),
    ),
    "src/rasai/console_m23.py": (
        (" + M25 até {m25_attempts} user action(s) sintética(s)", " + experiência sintética até {m25_attempts} ação(ões) de usuário"),
        ("navegação(ões) M23 ", "navegação(ões) Synthetic Navigation Apdex "),
        ("M25 Synthetic User Experience Apdex exige M23 Synthetic Apdex habilitado", "Synthetic User Experience Apdex exige Synthetic Navigation Apdex habilitado"),
    ),
    "tests/test_report_visual_contract.py": (("m20-ai-telemetry", "remediation-ai-telemetry"),),
    "tests/test_report_navigation.py": (("m20-ai-telemetry", "remediation-ai-telemetry"),),
    "tests/test_m12_stable_baseline.py": (("m20-ai-telemetry", "remediation-ai-telemetry"),),
    "tests/test_rasai_readiness_reporting.py": (
        ("m21-performance-summary", "web-performance-summary"),
        ("m22-accessibility-summary", "accessibility-summary"),
        ("rasai-m23-index-start", "rasai-apdex-index-start"),
        ("rasai-m23-index-end", "rasai-apdex-index-end"),
    ),
}

DOC_EXACT_REPLACEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "docs/INDICATOR_PROVENANCE.md": (
        (
            "`SARI-001` é a identidade pública da metodologia e `SCORE-GEO-003` é o método de scoring persistido. Provenance, model artifact, dataset e evidências permanecem rastreáveis.",
            "`SARI-001` é a identidade pública do índice e `SCORE-GEO-004` é o método de scoring vigente para novas auditorias. `SCORE-GEO-003` e versões anteriores permanecem históricas e são preservadas pela `scoring_version` original; model artifact/dataset pertencem ao histórico metodológico quando aplicável, não ao Overall 004.",
        ),
        (
            "> SARI-001: índice proprietário, evidence-based e reprodutível do RASAi; método de scoring persistido SCORE-GEO-003.",
            "> SARI-001: índice proprietário, evidence-based e reprodutível do RASAi; runtime vigente SCORE-GEO-004, com versões históricas preservadas por scoring_version.",
        ),
    ),
    "docs/SECURE_REDIRECT_RECOVERY.md": (
        ("extração, regras e `SCORE-GEO-003` podem prosseguir;", "extração, regras e `SCORE-GEO-004` podem prosseguir;"),
    ),
    "docs/specification/07_FUNCTIONAL_REQUIREMENTS.md": (
        ("+ SCORE-GEO-003 + SARI-001 +", "+ SCORE-GEO-004 + SARI-001 +"),
    ),
    "docs/specification/09_IMPLEMENTATION_PLAN.md": (
        ("preservar o contrato de scoring `SCORE-GEO-003`;", "preservar o contrato de scoring vigente `SCORE-GEO-004` e a leitura histórica por `scoring_version`;"),
    ),
    "docs/ENVIRONMENT_VARIABLES.md": (
        ("`SARI-001` nem na fórmula `SCORE-GEO-003`", "`SARI-001` nem na fórmula `SCORE-GEO-004`"),
    ),
}

DOC_STAGE_NAMES = {
    "M18": "análise semântica por IA",
    "M20": "remediação de conteúdo por IA",
    "M21": "Web Performance",
    "M22": "Acessibilidade e diagnósticos Web",
    "M23": "Synthetic Navigation Apdex",
    "M24": "Crawling e Discovery",
    "M25": "Synthetic User Experience Apdex",
    "M26": "Observed Generative Visibility",
}
_EVENT_DOMAIN = {
    "M18": "análise semântica por IA",
    "M20": "remediação de conteúdo por IA",
    "M21": "Web Performance",
    "M22": "Acessibilidade",
    "M23": "Synthetic Navigation Apdex",
    "M24": "Crawling e Discovery",
    "M25": "Synthetic User Experience Apdex",
    "M26": "Observed Generative Visibility",
}

_MILESTONE_RE = re.compile(r"(?<![A-Za-z0-9_])M\d{1,3}(?![A-Za-z0-9_])")
_EVENT_RE = re.compile(r"\b(M\d{1,3})_([A-Z][A-Z0-9_]*)\b")


def _event_description(match: re.Match[str]) -> str:
    domain = _EVENT_DOMAIN.get(match.group(1), "pipeline interno")
    suffix = match.group(2).replace("_", " ").casefold()
    return f"evento operacional de {domain} ({suffix})"


def _clean_doc(text: str) -> str:
    text = text.replace("M18/M20", "análise semântica/remediação de conteúdo por IA")
    text = text.replace("M21/M22", "Web Performance/Acessibilidade")
    text = text.replace("M21 + M22", "Web Performance e Acessibilidade")
    text = text.replace("M21/M23", "Web Performance/Synthetic Navigation Apdex")
    text = text.replace("M23/M25", "Synthetic Navigation/Synthetic User Experience Apdex")
    text = _EVENT_RE.sub(_event_description, text)

    def repl(match: re.Match[str]) -> str:
        return DOC_STAGE_NAMES.get(match.group(0), "etapa interna de implementação")

    return _MILESTONE_RE.sub(repl, text)


def _centralize_navigation(text: str) -> str:
    import_line = "from rasai.report_contract import CANONICAL_NAV_ITEMS\n"
    if import_line not in text:
        marker = "from rasai.report_semantics import SEMANTIC_CSS, enhance_report_html\n"
        text = text.replace(marker, import_line + marker, 1)
    pattern = re.compile(
        r"NAV_ITEMS: tuple\[tuple\[str, str\], \.\.\.\] = \(.*?\n\)\n\nBRASILIA_TIMEZONE",
        re.DOTALL,
    )
    return pattern.sub("NAV_ITEMS: tuple[tuple[str, str], ...] = CANONICAL_NAV_ITEMS\n\nBRASILIA_TIMEZONE", text, count=1)


def _current_doc_transform(relative: str, text: str) -> str:
    # These two specifications describe current non-scoring domains, not history.
    if relative == "docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md":
        text = text.replace("SCORE-GEO-003", "SCORE-GEO-004")
        text = text.replace(
            "**Dependências:** Análise semântica por IA, roteamento e telemetria + Sugestões e remediação de conteúdo por IA + `SCORE-GEO-004` + `REPORT-SITE-GEO-001`",
            "**Dependências:** report site + configuração opcional PageSpeed/CrUX; IA não é dependência obrigatória",
        )
    elif relative == "docs/specification/22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md":
        text = text.replace("SCORE-GEO-003", "SCORE-GEO-004")
    elif relative == "docs/specification/10_DECISIONS.md":
        marker = "## Restrições aprovadas adicionais"
        if marker in text:
            before, after = text.split(marker, 1)
            after = after.replace("`SARI-001`/`SCORE-GEO-003`", "`SARI-001`/`SCORE-GEO-004`")
            text = before + marker + after
        if "### D-042 - SCORE-GEO-004 e contrato público estável" not in text:
            text = text.rstrip() + """

### D-042 - SCORE-GEO-004 e contrato público estável

Esta decisão registra a evolução metodológica posterior às D-038, D-039 e D-040 sem reescrever retroativamente o contexto em que elas foram aprovadas.

1. `SCORE-GEO-004` substitui `SCORE-GEO-003` como **runtime de scoring vigente** para novas auditorias.
2. O Overall do `SCORE-GEO-004` é determinístico e não depende de model artifact, dataset de calibração ou fitting externo para existir.
3. As decisões anteriores de separação metodológica entre Readiness, Web Performance, Acessibilidade, crawling/discovery e outcomes observacionais continuam válidas.
4. D-038, D-039, D-040 e decisões correlatas são superseded **somente quanto à referência à versão vigente do scoring**; seu conteúdo histórico e suas fronteiras de domínio permanecem preservados.
5. Auditorias históricas continuam imutáveis e são abertas/comparadas pela respectiva `scoring_version`; o report não converte silenciosamente 002/003 para 004.
6. Nenhuma série histórica pode misturar `SCORE-GEO-002`, `SCORE-GEO-003` e `SCORE-GEO-004` como se fossem a mesma metodologia. Pares incompatíveis devem ser `NOT_COMPARABLE` para métricas de score.
7. A superfície pública canônica da metodologia passa a ser `report/scoring.html`, independente da versão. `report/score-geo-004.html` é somente alias de compatibilidade quando o AUD efetivamente usa 004 e não é item de navegação.
8. A identidade pública do índice permanece `SARI-001`.
9. Versão do produto, `ruleset_version`, `sari_version`, `scoring_version`, `report_contract_version` e `observability_contract_version` são eixos distintos e não devem ser colapsados em uma única versão.

D-042 não autoriza recalcular auditorias históricas nem alterar evidência persistida.
""" + "\n"
    return text


def main() -> int:
    changed: list[str] = []
    for relative, replacements in EXACT_REPLACEMENTS.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in replacements:
            updated = updated.replace(old, new)
        if relative == "src/rasai/report_navigation.py":
            updated = _centralize_navigation(updated)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(relative)

    for path in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]:
        if not path.is_file():
            continue
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in DOC_EXACT_REPLACEMENTS.get(relative, ()):
            updated = updated.replace(old, new)
        updated = _current_doc_transform(relative, updated)
        updated = _clean_doc(updated)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(relative)

    print(f"public surface cleanup: {len(changed)} file(s) changed")
    for item in sorted(changed):
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
