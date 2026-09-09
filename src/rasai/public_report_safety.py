"""Safety boundary for RASAi-owned public report presentation.

Internal delivery identifiers are valid implementation details but are not part of
the public report contract. This module normalizes only exact strings previously
emitted by RASAi itself and validates RASAi-owned HTML markup. It deliberately
avoids a generic milestone replacement over visible page/evidence text so content
collected from an audited website is never rewritten merely because it resembles
an internal identifier.
"""
from __future__ import annotations

import re


_OWNED_PRESENTATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("M18/M20", "análise semântica e remediação textual"),
    ("M21/M22", "Web Performance e Acessibilidade"),
    ("M21 + M22 · domínio Web Performance", "Domínio Web Performance"),
    ("M23 · domínio Web Performance", "Domínio Synthetic Apdex"),
    ("Web Performance · M23", "Synthetic Apdex"),
    ("M23 · performance sintética transacional", "Performance sintética transacional"),
    ("M23 · metodologia", "Metodologia Synthetic Apdex"),
    ("M22 · domínio independente", "Domínio independente"),
    ("M22 · diagnóstico técnico", "Diagnóstico técnico"),
    ("M22 · fronteiras de domínio", "Fronteiras de domínio"),
    ("M20 · remediação opcional", "Remediação opcional"),
    ("Estado M23", "Estado"),
    ("Synthetic Apdex M23", "Synthetic Apdex"),
    ("M23 não chama", "Synthetic Apdex não chama"),
    ("regras conservadoras do M23", "regras conservadoras do Synthetic Apdex"),
    ("M20 é projeção auxiliar", "A remediação textual é uma projeção auxiliar"),
    ("Nenhuma chamada M20.", "Nenhuma chamada de remediação textual."),
    ("análise semântica M18", "análise semântica principal"),
    ("pelo M21", "pela coleta de Web Performance"),
    ("M22 Acessibilidade", "Acessibilidade automatizada"),
    ("M21/M23", "Web Performance/Synthetic Apdex"),
    ("M18 análise semântica", "Análise semântica por IA"),
    ("M20 remediação textual", "Remediação textual por IA"),
    ("M24-CD-001", "CRAWLING-DISCOVERY-001"),
    ("Rastreamento e descoberta M24", "Rastreamento e descoberta"),
    ("artifacts/m24/", ""),
    ("m20-no-eligible-note", "content-remediation-no-eligible-note"),
    ("m23-apdex-summary", "apdex-summary"),
    # Legacy HTML comment markers are RASAi-owned presentation metadata. They may
    # be normalized generically because audited page content is HTML-escaped and
    # therefore cannot become an active comment marker in the report document.
    ("rasai-m23-web-start", "rasai-apdex-web-start"),
    ("rasai-m23-web-end", "rasai-apdex-web-end"),
    ("m24-ai-usage:start", "crawling-discovery-ai-usage:start"),
    ("m24-ai-usage:end", "crawling-discovery-ai-usage:end"),
    ("m24-references:start", "crawling-discovery-references:start"),
    ("m24-references:end", "crawling-discovery-references:end"),
)

# Only active RASAi-owned markup is checked generically. Visible text is not:
# an audited website may legitimately contain a model/product name such as M25.
_MARKUP_MILESTONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<!--[^>]*(?<![A-Za-z0-9])m\d{1,3}(?![A-Za-z0-9])[^>]*-->", re.I),
    re.compile(
        r"\b(?:id|class|name|data-[\w:-]+)\s*=\s*(['\"])[^'\"]*"
        r"(?<![A-Za-z0-9])m\d{1,3}(?![A-Za-z0-9])[^'\"]*\1",
        re.I,
    ),
)


class PublicReportSafetyError(RuntimeError):
    """RASAi-owned presentation still exposes an internal delivery identifier."""


def public_report_markup_leaks(html: str) -> tuple[str, ...]:
    """Return residual internal delivery identifiers in active report markup.

    The function intentionally ignores ordinary visible text. This preserves
    evidence fidelity while still making internal IDs/comments/classes a hard
    public-contract violation.
    """
    leaks: list[str] = []
    for pattern in _MARKUP_MILESTONE_PATTERNS:
        for match in pattern.finditer(html):
            token = re.search(r"(?i)(?<![A-Za-z0-9])m\d{1,3}(?![A-Za-z0-9])", match.group(0))
            if token is not None:
                leaks.append(token.group(0).upper())
    return tuple(dict.fromkeys(leaks))


def assert_owned_public_report_safe(html: str) -> None:
    leaks = public_report_markup_leaks(html)
    if leaks:
        raise PublicReportSafetyError(
            "internal delivery identifier exposed in public report markup: "
            + ", ".join(leaks)
        )


def normalize_owned_public_report_text(html: str) -> str:
    """Normalize RASAi-owned labels and validate active public markup.

    Website evidence and customer-provided visible content remain unchanged unless
    they exactly equal a historical RASAi presentation fragment. Internal artifact
    paths may be shortened to their public basename while the canonical reference
    remains preserved in ``audit.db``.
    """
    for old, new in _OWNED_PRESENTATION_REPLACEMENTS:
        html = html.replace(old, new)
    assert_owned_public_report_safe(html)
    return html
