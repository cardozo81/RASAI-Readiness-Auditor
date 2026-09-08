"""One-shot contextual cleanup for public RASAi surfaces.

This script deliberately does NOT perform global scoring-version replacement.
It only removes obsolete milestone labels from user-facing surfaces and fixes
known current-runtime strings whose context is unambiguously current.
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
    ),
    "src/rasai/report_navigation.py": (
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
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
    ),
    "tests/test_report_visual_contract.py": (
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
    ),
    "tests/test_report_navigation.py": (
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
    ),
    "tests/test_m12_stable_baseline.py": (
        ("m20-ai-telemetry", "remediation-ai-telemetry"),
    ),
    "tests/test_rasai_readiness_reporting.py": (
        ("m21-performance-summary", "web-performance-summary"),
        ("m22-accessibility-summary", "accessibility-summary"),
        ("rasai-m23-index-start", "rasai-apdex-index-start"),
        ("rasai-m23-index-end", "rasai-apdex-index-end"),
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

# Most documentation before the named domain stages only needs to stop exposing
# internal milestone numbering. Unknown milestone numbers are intentionally
# rendered as a neutral implementation-stage term rather than guessed.
_MILESTONE_RE = re.compile(r"(?<![A-Za-z0-9_])M\d{1,3}(?![A-Za-z0-9_])")


def _clean_doc(text: str) -> str:
    # Replace compound labels first so wording remains readable.
    text = text.replace("M18/M20", "análise semântica/remediação de conteúdo por IA")
    text = text.replace("M21/M22", "Web Performance/Acessibilidade")
    text = text.replace("M21 + M22", "Web Performance e Acessibilidade")
    text = text.replace("M21/M23", "Web Performance/Synthetic Navigation Apdex")
    text = text.replace("M23/M25", "Synthetic Navigation/Synthetic User Experience Apdex")

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return DOC_STAGE_NAMES.get(token, "etapa interna de implementação")

    return _MILESTONE_RE.sub(repl, text)


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
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(relative)

    for path in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated = _clean_doc(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(str(path.relative_to(ROOT)))

    print(f"public surface cleanup: {len(changed)} file(s) changed")
    for item in sorted(changed):
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
