"""M17 report-only precision for BR-GEO-051 duplicate-content findings.

This module does not alter the duplicate heuristic, RuleResult, scoring or
persisted evidence. It only replaces the conservative fallback remediation in
HTML projections when BR-GEO-051 already contains persisted duplicate matches.
"""

from __future__ import annotations

import re


_ROOT_BLOCK = re.compile(
    r'<section class="m16-root m17-precision">.*?</section>',
    re.DOTALL,
)
_GROUP_BLOCK = re.compile(
    r'<article class="group[^>]*>.*?</article>',
    re.DOTALL,
)
_RECOMMENDATION_BLOCK = re.compile(
    r'<article class="recommendation[^>]*>.*?</article>',
    re.DOTALL,
)
_TRACE_BLOCK = re.compile(
    r"<details class='m17-compat-trace'>.*?</details>",
    re.DOTALL,
)

_GENERIC_CHANGE = (
    "Ação: REVIEW_AND_CORRECT · Alvo: Condição registrada no finding · "
    "Atender à condição esperada registrada no finding usando somente a evidência persistida. "
    "Este é um fallback porque ainda não existe recipe específica para a regra."
)
_PRECISE_CHANGE = (
    "Ação: REVIEW_DUPLICATE_CONTENT · Alvo: conteúdo principal extraído das páginas relacionadas · "
    "Comparar as páginas apontadas em matches. Se elas tiverem finalidades distintas, tornar o conteúdo principal "
    "materialmente específico para cada página, preservando somente trechos realmente compartilhados. Se a duplicidade "
    "for intencional, documentar a estratégia de URL/canonicalização e tratar canonical ou redirect somente após decisão humana."
)
_GENERIC_ACCEPTANCE = "A condição esperada do finding é atendida sem criar conflito com outras regras."
_PRECISE_ACCEPTANCE = (
    "As páginas que devem permanecer distintas deixam de atingir o limiar de exact/near-duplicate da BR-GEO-051. · "
    "Conteúdo comum legítimo pode permanecer compartilhado. · "
    "Duplicidade intencional fica documentada e coerente com a estratégia de URL/canonicalização aprovada."
)
_GENERIC_VALIDATION = "Reexecutar BR-GEO-051 e revisar as evidence_ids associadas."
_PRECISE_VALIDATION = (
    "Reexecutar BR-GEO-051 no mesmo conjunto de URLs e comparar novamente os pares/similaridades persistidos. · "
    "Se houver decisão de canonicalização, revalidar BR-GEO-013, BR-GEO-014 e BR-GEO-015 sem presumir a URL preferencial."
)


def refine_br_geo_051_html(html: str) -> str:
    """Replace only BR-GEO-051 fallback copy with evidence-specific guidance."""

    html = _ROOT_BLOCK.sub(_refine_root_block, html)
    html = _GROUP_BLOCK.sub(_refine_group_block, html)
    html = _RECOMMENDATION_BLOCK.sub(_refine_recommendation_block, html)
    html = _TRACE_BLOCK.sub(_refine_trace_block, html)
    return html


def _is_br_051(block: str) -> bool:
    return "BR-GEO-051" in block


def _has_exact_match(block: str) -> bool:
    return (
        "EXACT_DUPLICATE_MAIN_CONTENT" in block
        or "&quot;similarity&quot;: 1.0" in block
        or '"similarity": 1.0' in block
    )


def _refine_root_block(match: re.Match[str]) -> str:
    block = match.group(0)
    if not _is_br_051(block):
        return block

    exact = _has_exact_match(block)
    reason = "EXACT_DUPLICATE_MAIN_CONTENT" if exact else "NEAR_DUPLICATE_MAIN_CONTENT"
    cause = (
        "A evidência persistida identifica conteúdo principal exatamente duplicado entre páginas do universo auditado."
        if exact
        else "A evidência persistida identifica conteúdo principal near-duplicate entre páginas do universo auditado."
    )

    block = block.replace(
        "<div><small>Causa</small><strong>RULE_CONDITION_MISMATCH</strong></div>",
        "<div><small>Causa</small><strong>DUPLICATE_MAIN_CONTENT</strong></div>",
    )
    block = block.replace(
        "<div><small>Motivo técnico</small><strong>NÃO DETERMINADO</strong></div>",
        f"<div><small>Motivo técnico</small><strong>{reason}</strong></div>",
    )
    block = block.replace(
        "<p><strong>Causa raiz:</strong> A condição observada não satisfaz a condição esperada da Business Rule para esta ocorrência.</p>",
        f"<p><strong>Causa raiz:</strong> {cause}</p>",
    )
    block = block.replace(
        "<strong>Recipe técnica:</strong> Remediar BR-GEO-051",
        "<strong>Recipe técnica:</strong> Revisar duplicidade do conteúdo principal",
    )
    block = block.replace(_GENERIC_CHANGE, _PRECISE_CHANGE)
    block = block.replace(
        f"<h5>Critério de aceite</h5><ul><li>{_GENERIC_ACCEPTANCE}</li></ul>",
        "<h5>Critério de aceite</h5><ul>"
        "<li>As páginas que devem permanecer distintas deixam de atingir o limiar de exact/near-duplicate da BR-GEO-051.</li>"
        "<li>Conteúdo comum legítimo pode permanecer compartilhado.</li>"
        "<li>Duplicidade intencional fica documentada e coerente com a estratégia de URL/canonicalização aprovada.</li>"
        "</ul>",
    )
    block = block.replace(
        f"<h5>Revalidação</h5><ol><li>{_GENERIC_VALIDATION}</li></ol>",
        "<h5>Revalidação</h5><ol>"
        "<li>Reexecutar BR-GEO-051 no mesmo conjunto de URLs e comparar novamente os pares/similaridades persistidos.</li>"
        "<li>Se houver decisão de canonicalização, revalidar BR-GEO-013, BR-GEO-014 e BR-GEO-015 sem presumir a URL preferencial.</li>"
        "</ol>",
    )
    decision = (
        "<div class='m16-decision'><strong>Decisão humana necessária</strong><br>"
        "Confirme se as páginas relacionadas deveriam representar conteúdos distintos ou se a duplicidade é intencional. "
        "O auditor não escolhe automaticamente uma URL canonical, não recomenda redirect sem essa decisão e não inventa conteúdo diferenciador."
        "</div>"
    )
    if decision not in block and "<h5>Critério de aceite</h5>" in block:
        block = block.replace("<h5>Critério de aceite</h5>", decision + "<h5>Critério de aceite</h5>", 1)
    return block


def _refine_group_block(match: re.Match[str]) -> str:
    block = match.group(0)
    if not _is_br_051(block):
        return block
    block = block.replace(
        "REVIEW_AND_CORRECT - Atender à condição esperada registrada no finding usando somente a evidência persistida. Este é um fallback porque ainda não existe recipe específica para a regra.",
        "REVIEW_DUPLICATE_CONTENT - Comparar os pares de páginas persistidos em matches e revisar se a duplicidade é intencional. Para páginas que deveriam ser distintas, tornar o conteúdo principal materialmente específico; para duplicidade intencional, alinhar a estratégia de URL/canonicalização somente após decisão humana.",
    )
    block = block.replace(_GENERIC_ACCEPTANCE, _PRECISE_ACCEPTANCE)
    return block


def _refine_recommendation_block(match: re.Match[str]) -> str:
    block = match.group(0)
    if not _is_br_051(block):
        return block
    block = block.replace(
        "Fallback de remediação. Atender à condição esperada registrada no finding usando somente a evidência persistida. Este é um fallback porque ainda não existe recipe específica para a regra.",
        "Revisar os pares exact/near-duplicate persistidos pela BR-GEO-051. Se as páginas tiverem finalidades distintas, diferenciar materialmente o conteúdo principal. Se a duplicidade for intencional, decidir e documentar a estratégia de URL/canonicalização antes de alterar canonical ou redirects.",
    )
    return block


def _refine_trace_block(match: re.Match[str]) -> str:
    block = match.group(0)
    if not _is_br_051(block):
        return block
    block = block.replace("Remediar BR-GEO-051", "Revisar duplicidade do conteúdo principal")
    block = block.replace(_GENERIC_ACCEPTANCE, _PRECISE_ACCEPTANCE)
    block = block.replace(_GENERIC_VALIDATION, _PRECISE_VALIDATION)
    return block
