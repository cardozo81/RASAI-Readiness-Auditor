"""Safety boundary for RASAi-owned public report presentation.

Internal delivery identifiers are valid implementation details but are not part of
the public report contract. This module normalizes only RASAi-owned presentation
and markup while preserving ordinary visible evidence text. A broad replacement
of ``M<number>`` across the document is deliberately forbidden because audited
content may legitimately contain a product/model name such as ``M25``.
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
)

# Historical implementation prefixes that may still be emitted by optional
# report enrichers. They are normalized only inside RASAi-owned HTML markup,
# comments and CSS selectors; ordinary visible evidence text is not touched.
_MARKUP_PREFIX_MAP: dict[str, str] = {
    "m14": "evidence-linking",
    "m15": "report-layout",
    "m16": "root-cause",
    "m17": "remediation",
    "m18": "ai-analysis",
    "m20": "content-remediation",
    "m21": "web-performance",
    "m22": "accessibility",
    "m23": "apdex",
    "m24": "crawling-discovery",
    "m25": "apdex-experience",
    "m26": "ai-visibility",
}

_MILESTONE_TOKEN_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])m(?P<number>\d{1,3})(?![A-Za-z0-9])"
)
_MILESTONE_PREFIX_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])m(?P<number>\d{1,3})-"
)
_ATTRIBUTE_RE = re.compile(
    r"\b(?P<name>id|class|name|data-[\w:-]+)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.I | re.DOTALL,
)
_COMMENT_RE = re.compile(r"<!--(?P<body>.*?)-->", re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.I | re.DOTALL)


class PublicReportSafetyError(RuntimeError):
    """RASAi-owned presentation still exposes an internal delivery identifier."""


def _functional_prefix(match: re.Match[str]) -> str:
    internal = f"m{match.group('number')}".casefold()
    replacement = _MARKUP_PREFIX_MAP.get(internal)
    if replacement is None:
        return match.group(0)
    return replacement + "-"


def _normalize_attribute(match: re.Match[str]) -> str:
    value = _MILESTONE_PREFIX_RE.sub(_functional_prefix, match.group("value"))
    return f"{match.group('name')}={match.group('quote')}{value}{match.group('quote')}"


def _normalize_comment(match: re.Match[str]) -> str:
    body = _MILESTONE_PREFIX_RE.sub(_functional_prefix, match.group("body"))
    return f"<!--{body}-->"


def _normalize_style(match: re.Match[str]) -> str:
    full = match.group(0)
    body = match.group("body")
    normalized = _MILESTONE_PREFIX_RE.sub(_functional_prefix, body)
    return full.replace(body, normalized, 1)


def _normalize_owned_markup(html: str) -> str:
    html = _COMMENT_RE.sub(_normalize_comment, html)
    html = _STYLE_RE.sub(_normalize_style, html)
    html = _ATTRIBUTE_RE.sub(_normalize_attribute, html)
    return html


def public_report_markup_leaks(html: str) -> tuple[str, ...]:
    """Return residual internal delivery identifiers in RASAi-owned markup.

    Ordinary visible text is intentionally ignored. Active attributes, HTML
    comments and CSS blocks are owned by the report generator and therefore may
    not contain an internal ``M<number>`` identifier.
    """
    leaks: list[str] = []

    for match in _ATTRIBUTE_RE.finditer(html):
        token = _MILESTONE_TOKEN_RE.search(match.group("value"))
        if token is not None:
            leaks.append(token.group(0).upper())

    for match in _COMMENT_RE.finditer(html):
        for token in _MILESTONE_TOKEN_RE.finditer(match.group("body")):
            leaks.append(token.group(0).upper())

    for match in _STYLE_RE.finditer(html):
        for token in _MILESTONE_TOKEN_RE.finditer(match.group("body")):
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
    """Normalize RASAi-owned public presentation without mutating evidence text."""
    for old, new in _OWNED_PRESENTATION_REPLACEMENTS:
        html = html.replace(old, new)
    html = _normalize_owned_markup(html)
    assert_owned_public_report_safe(html)
    return html
