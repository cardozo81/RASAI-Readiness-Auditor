"""#646 F3: architecture eligibility inventory - advisory-only policy.

This is descriptive documentation for consumers, not an execution router. Only
the already approved F3 resolver's static allowlist is authorized to inherit a
physically observed architecture; documenting other consumers grants no rights.
"""
from __future__ import annotations

from dataclasses import dataclass

from rasai.architecture_context import APPROVED_ADVISORY_CONSUMERS

POLICY_VERSION = "architecture-consumer-eligibility-v1"


@dataclass(frozen=True)
class ConsumerEligibility:
    consumer: str
    category: str
    owner: str
    decision: str
    requires: str


_ROWS = (
    ConsumerEligibility("descriptive_report", "REPORT", "M24 / Relatório",
                        "ADVISORY_SAFE", "AUD + URL + device + snapshot M6 e escolha selada"),
    ConsumerEligibility("m6_read_only_diagnostic", "DISCOVERY", "M6 / Prévia",
                        "ADVISORY_SAFE", "evidência M6 no mesmo snapshot; nenhuma ação"),
    ConsumerEligibility("CAT-01", "CATALOG", "Dados e recursos", "INTERPRETATION_SAFE",
                        "sem herança automática; aprovação do contrato por catálogo"),
    ConsumerEligibility("CAT-02", "CATALOG", "Aquisição e rastreamento",
                        "PRE_COLLECTION_ONLY", "uma nova coleta autorizada"),
    ConsumerEligibility("CAT-03", "CATALOG", "Conteúdo e FAQ", "INTERPRETATION_SAFE",
                        "prova do DOM e interação no mesmo contexto, se aplicável"),
    ConsumerEligibility("CAT-04", "CATALOG", "Lighthouse / CrUX", "INAPPLICABLE",
                        "coortes e field_scope já têm contratos próprios"),
    ConsumerEligibility("CAT-05", "CATALOG", "SERP / GEO", "INAPPLICABLE",
                        "mercado, idioma, consulta e device externos independentes"),
    ConsumerEligibility("CAT-06", "CATALOG", "Apdex navegação M23",
                        "METHOD_CHANGE_REQUIRES_ADR", "golden/parity e decisão metodológica"),
    ConsumerEligibility("CAT-07", "CATALOG", "Apdex experiência M25",
                        "METHOD_CHANGE_REQUIRES_ADR", "parâmetros somente antes da coleta; sem retroação"),
    ConsumerEligibility("CAT-08", "CATALOG", "Improvement Intelligence",
                        "INTERPRETATION_SAFE", "rastrear fonte consultiva sem instruir motor"),
    ConsumerEligibility("CAT-09", "CATALOG", "Remediações", "INTERPRETATION_SAFE",
                        "citar contexto observado/declarado sem alterar regras"),
    ConsumerEligibility("CAT-10", "CATALOG", "Segurança passiva", "INAPPLICABLE",
                        "segurança HTTP/DOM não deriva da classe de arquitetura"),
    ConsumerEligibility("SARI", "SCORE", "Índice de prontidão",
                        "METHOD_CHANGE_REQUIRES_ADR", "versão, calibração, golden e aceite"),
    ConsumerEligibility("SCORE-GEO", "SCORE", "Pesos e regras GEO",
                        "METHOD_CHANGE_REQUIRES_ADR", "ADR, nova versão e paridade histórica"),
    ConsumerEligibility("M23", "COLLECTOR", "Synthetic Navigation",
                        "PRE_COLLECTION_ONLY", "sem alterar as amostras homologadas"),
    ConsumerEligibility("M25", "COLLECTOR", "Synthetic User Experience",
                        "PRE_COLLECTION_ONLY", "autorização de nova AUD e método independente"),
    ConsumerEligibility("IA", "PROVIDER", "Motores de IA existentes",
                        "INAPPLICABLE", "sem chamadas, custo ou reconfiguração implícitos"),
    ConsumerEligibility("Dynatrace RUM", "EXTERNAL", "Tenant externo",
                        "INAPPLICABLE", "integração e medição física independente"),
)


def architecture_consumer_eligibility() -> tuple[ConsumerEligibility, ...]:
    """Inventory is immutable and cannot expand the F3 resolver's allowlist."""
    approved = {r.consumer for r in _ROWS if r.decision == "ADVISORY_SAFE"}
    if approved != APPROVED_ADVISORY_CONSUMERS:
        raise RuntimeError("F3 advisory eligibility is inconsistent with resolver")
    return _ROWS


__all__ = ["architecture_consumer_eligibility", "ConsumerEligibility", "POLICY_VERSION"]
