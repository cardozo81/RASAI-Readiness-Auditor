"""Safety boundary for RASAi-owned public report presentation.

Internal delivery identifiers are valid implementation details but are not part of
the public report contract. This module normalizes only exact strings previously
emitted by RASAi itself. It deliberately avoids a generic milestone regex so
content collected from an audited website is never rewritten merely because it
resembles an internal identifier.
"""
from __future__ import annotations


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
)


def normalize_owned_public_report_text(html: str) -> str:
    """Normalize only report strings known to be owned by RASAi.

    The function intentionally does not replace arbitrary ``M<number>`` tokens.
    Website evidence and customer-provided content therefore remain byte-for-byte
    unchanged unless they exactly equal a historical RASAi presentation fragment.
    Internal artifact paths may be shortened to their public basename while the
    canonical reference remains preserved in ``audit.db``.
    """
    for old, new in _OWNED_PRESENTATION_REPLACEMENTS:
        html = html.replace(old, new)
    return html
