"""Contexto editorial opcional para tornar análises de IA menos generalistas.

Os valores deste módulo condicionam a interpretação semântica e as sugestões de
conteúdo. Eles NÃO são fatores oficiais de ranking, não alteram SCORE-GEO-002 e
não transformam conceitos como E-E-A-T/YMYL em um score proprietário.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os
from typing import Any, Mapping


CONTENT_RISK_PROFILE_ENV = "RASAI_CONTENT_RISK_PROFILE"
YMYL_CATEGORY_ENV = "RASAI_YMYL_CATEGORY"
PAGE_PURPOSE_ENV = "RASAI_PAGE_PURPOSE"
INTENDED_AUDIENCE_ENV = "RASAI_INTENDED_AUDIENCE"
EXPERIENCE_REQUIREMENT_ENV = "RASAI_EXPERIENCE_REQUIREMENT"
FRESHNESS_SENSITIVITY_ENV = "RASAI_FRESHNESS_SENSITIVITY"
CONTENT_ORIGIN_ENV = "RASAI_CONTENT_ORIGIN"

CONTENT_CONTEXT_ENV_NAMES = (
    CONTENT_RISK_PROFILE_ENV,
    YMYL_CATEGORY_ENV,
    PAGE_PURPOSE_ENV,
    INTENDED_AUDIENCE_ENV,
    EXPERIENCE_REQUIREMENT_ENV,
    FRESHNESS_SENSITIVITY_ENV,
    CONTENT_ORIGIN_ENV,
)


class ContentRiskProfile(StrEnum):
    AUTO = "auto"
    STANDARD = "standard"
    YMYL = "ymyl"


class YmylCategory(StrEnum):
    AUTO = "auto"
    NONE = "none"
    HEALTH_SAFETY = "health-safety"
    FINANCIAL_SECURITY = "financial-security"
    CIVIC_SOCIETAL = "civic-societal"
    OTHER_SIGNIFICANT_WELFARE = "other-significant-welfare"


class PagePurpose(StrEnum):
    AUTO = "auto"
    INFORMATIONAL = "informational"
    TRANSACTIONAL = "transactional"
    PRODUCT_SERVICE = "product-service"
    REVIEW_COMPARISON = "review-comparison"
    NEWS_EDITORIAL = "news-editorial"
    SUPPORT_DOCUMENTATION = "support-documentation"
    FORUM_UGC = "forum-ugc"
    OTHER = "other"


class IntendedAudience(StrEnum):
    AUTO = "auto"
    GENERAL = "general"
    PROFESSIONAL = "professional"
    MIXED = "mixed"


class ExperienceRequirement(StrEnum):
    AUTO = "auto"
    REQUIRED = "required"
    BENEFICIAL = "beneficial"
    NOT_EXPECTED = "not-expected"


class FreshnessSensitivity(StrEnum):
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContentOrigin(StrEnum):
    AUTO = "auto"
    FIRST_PARTY = "first-party"
    THIRD_PARTY = "third-party"
    USER_GENERATED = "user-generated"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class ContentAnalysisContext:
    """Configuração de contexto enviada aos providers sem modificar scoring.

    ``AUTO`` significa que o provider pode usar uma classificação de trabalho
    apenas a partir da evidência visível da própria página. Essa inferência é
    deliberadamente menos confiável do que um override explícito.
    """

    risk_profile: ContentRiskProfile = ContentRiskProfile.AUTO
    ymyl_category: YmylCategory = YmylCategory.AUTO
    page_purpose: PagePurpose = PagePurpose.AUTO
    intended_audience: IntendedAudience = IntendedAudience.AUTO
    experience_requirement: ExperienceRequirement = ExperienceRequirement.AUTO
    freshness_sensitivity: FreshnessSensitivity = FreshnessSensitivity.AUTO
    content_origin: ContentOrigin = ContentOrigin.AUTO

    def validate(self) -> "ContentAnalysisContext":
        if self.risk_profile is ContentRiskProfile.STANDARD and self.ymyl_category not in {
            YmylCategory.AUTO,
            YmylCategory.NONE,
        }:
            raise ValueError("YMYL category cannot be forced when content risk profile is standard")
        if self.risk_profile is ContentRiskProfile.YMYL and self.ymyl_category is YmylCategory.NONE:
            raise ValueError("YMYL content risk profile cannot use ymyl-category=none")
        return self

    @property
    def configured_fields(self) -> tuple[str, ...]:
        pairs = (
            ("risk_profile", self.risk_profile.value),
            ("ymyl_category", self.ymyl_category.value),
            ("page_purpose", self.page_purpose.value),
            ("intended_audience", self.intended_audience.value),
            ("experience_requirement", self.experience_requirement.value),
            ("freshness_sensitivity", self.freshness_sensitivity.value),
            ("content_origin", self.content_origin.value),
        )
        return tuple(name for name, value in pairs if value != "auto")

    @property
    def auto_fields(self) -> tuple[str, ...]:
        all_fields = (
            "risk_profile",
            "ymyl_category",
            "page_purpose",
            "intended_audience",
            "experience_requirement",
            "freshness_sensitivity",
            "content_origin",
        )
        configured = set(self.configured_fields)
        return tuple(name for name in all_fields if name not in configured)

    @property
    def is_fully_auto(self) -> bool:
        return not self.configured_fields

    def provider_payload(self) -> dict[str, Any]:
        return {
            "risk_profile": self.risk_profile.value,
            "ymyl_category": self.ymyl_category.value,
            "page_purpose": self.page_purpose.value,
            "intended_audience": self.intended_audience.value,
            "experience_requirement": self.experience_requirement.value,
            "freshness_sensitivity": self.freshness_sensitivity.value,
            "content_origin": self.content_origin.value,
            "configured_fields": list(self.configured_fields),
            "auto_fields": list(self.auto_fields),
            "inference_policy": (
                "Explicit values are audit context. AUTO values are only working hypotheses "
                "that may be inferred from supplied visible evidence and must not be treated as facts."
            ),
            "analysis_policy": self.prompt_directive(),
        }

    def prompt_directive(self) -> str:
        """Return provider-neutral constraints for semantic and remediation prompts."""

        return (
            "Apply the supplied content_analysis_context before evaluating the page. "
            "These fields are analysis context, not official ranking factors and not a score. "
            "When risk_profile=ymyl, apply a materially higher trust/evidence bar for claims that can "
            "affect health, safety, financial stability/security, civic/societal welfare or comparable "
            "significant well-being. Treat trust as the central E-E-A-T consideration; experience, "
            "expertise and authoritativeness contribute only where the page purpose/topic makes them relevant. "
            "When any field is AUTO, infer only a provisional working context from supplied visible evidence, "
            "lower confidence when that inference matters, and never invent credentials, professional review, "
            "first-hand experience, source reputation, legal compliance, editorial process or hidden facts. "
            "Use page_purpose and intended_audience to judge what completeness and explanation are appropriate. "
            "Use experience_requirement to distinguish first-hand experience from subject-matter expertise instead "
            "of demanding both indiscriminately. When freshness_sensitivity=high, require stronger temporal "
            "qualification and internally consistent date/freshness evidence; never manufacture a fresher date. "
            "When content_origin is third-party, user-generated or mixed, distinguish the content creator/source "
            "from the hosting publisher and require clear responsibility/attribution when material. "
            "Language and market are context only and must not be used to assert jurisdictional or regulatory compliance."
        )

    def compact_summary(self) -> str:
        fields = self.provider_payload()
        return ";".join(
            f"{name}={fields[name]}"
            for name in (
                "risk_profile",
                "ymyl_category",
                "page_purpose",
                "intended_audience",
                "experience_requirement",
                "freshness_sensitivity",
                "content_origin",
            )
        )


def default_content_analysis_context() -> ContentAnalysisContext:
    return ContentAnalysisContext()


def build_content_analysis_context(
    *,
    risk_profile: str = "auto",
    ymyl_category: str = "auto",
    page_purpose: str = "auto",
    intended_audience: str = "auto",
    experience_requirement: str = "auto",
    freshness_sensitivity: str = "auto",
    content_origin: str = "auto",
) -> ContentAnalysisContext:
    try:
        context = ContentAnalysisContext(
            risk_profile=ContentRiskProfile(risk_profile.strip().casefold()),
            ymyl_category=YmylCategory(ymyl_category.strip().casefold()),
            page_purpose=PagePurpose(page_purpose.strip().casefold()),
            intended_audience=IntendedAudience(intended_audience.strip().casefold()),
            experience_requirement=ExperienceRequirement(experience_requirement.strip().casefold()),
            freshness_sensitivity=FreshnessSensitivity(freshness_sensitivity.strip().casefold()),
            content_origin=ContentOrigin(content_origin.strip().casefold()),
        )
    except ValueError as exc:
        raise ValueError(f"invalid content analysis context: {exc}") from exc
    return context.validate()


def configured_content_analysis_context(
    env: Mapping[str, str] | None = None,
) -> ContentAnalysisContext:
    environment = env if env is not None else os.environ

    def value(name: str) -> str:
        return (environment.get(name) or "auto").strip() or "auto"

    return build_content_analysis_context(
        risk_profile=value(CONTENT_RISK_PROFILE_ENV),
        ymyl_category=value(YMYL_CATEGORY_ENV),
        page_purpose=value(PAGE_PURPOSE_ENV),
        intended_audience=value(INTENDED_AUDIENCE_ENV),
        experience_requirement=value(EXPERIENCE_REQUIREMENT_ENV),
        freshness_sensitivity=value(FRESHNESS_SENSITIVITY_ENV),
        content_origin=value(CONTENT_ORIGIN_ENV),
    )
