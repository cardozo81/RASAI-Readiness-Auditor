"""Evidence-bound deep improvement analysis for one audited URL.

This domain is intentionally advisory. It correlates already-persisted RASAi evidence,
Lighthouse/PageSpeed artifacts, Search Intelligence, discovery files, HTML structure and
passive security posture. It never changes SARI/SCORE-GEO and never performs active
security exploitation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from rasai.ai_resilience import DECISION_RETRY, DECISION_STOP, DECISION_SUCCESS, DECISION_SUCCESS_AFTER_RETRY, MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, retry_policy
from rasai.domain import new_id
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderUsage,
    ResponsesSemanticProvider,
    _diagnostic_from_http as _core_diagnostic_from_http,
    _response_error,
    _usage_from_native,
    estimate_cost,
)
from rasai.m18_persistence import M18Persistence
from rasai.persistence import AuditWorkspace
from rasai.provider_extensions import (
    AnthropicProvider,
    GeminiProvider,
    IsolatedStructuredSemanticProvider,
    QwenProvider,
    XAIProvider,
    _diagnostic_from_http as _extension_diagnostic_from_http,
    gemini_wire_schema,
)
from rasai.provider_registry import get_provider_registration
from rasai.provider_runtime_policy import build_semantic_provider, provider_reasoning_env
from rasai.semantic import _extract_json_payload

CONTRACT_VERSION = "IMPROVEMENT-INTELLIGENCE-001"
REPORT_FILE = "improvement-intelligence.html"
AI_ANALYSIS_LANGUAGE_ENV = "RASAI_AI_ANALYSIS_LANGUAGE"
ENABLED_ENV = "RASAI_IMPROVEMENT_INTELLIGENCE"
PROVIDER_ENV = "RASAI_IMPROVEMENT_AI_PROVIDER"
MODEL_ENV = "RASAI_IMPROVEMENT_AI_MODEL"
REASONING_ENV = "RASAI_IMPROVEMENT_AI_REASONING"
DOMAINS_ENV = "RASAI_IMPROVEMENT_DOMAINS"
MAX_RECOMMENDATIONS_ENV = "RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS"
TIMEOUT_ENV = "RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS"

DEFAULT_DOMAINS: tuple[str, ...] = (
    "TECHNICAL_HTML",
    "SEMANTICS_STRUCTURE",
    "CONTENT",
    "SEARCH_RANKING",
    "FILES_DISCOVERY",
    "PERFORMANCE",
    "ACCESSIBILITY",
    "BEST_PRACTICES",
    "SECURITY",
    "AI_ACCESS",
)
DOMAIN_LABELS = {
    "TECHNICAL_HTML": "HTML e problemas técnicos",
    "SEMANTICS_STRUCTURE": "Semântica e estrutura",
    "CONTENT": "Conteúdo",
    "SEARCH_RANKING": "Busca orgânica / SERP",
    "FILES_DISCOVERY": "Arquivos de descoberta",
    "PERFORMANCE": "Performance",
    "ACCESSIBILITY": "Acessibilidade",
    "BEST_PRACTICES": "Melhores práticas",
    "SECURITY": "Segurança passiva",
    "AI_ACCESS": "Acesso e compreensão por IA",
}
_ALLOWED_DOMAINS = frozenset(DEFAULT_DOMAINS)
_SEVERITY_WEIGHT = {"CRITICAL": 100.0, "HIGH": 82.0, "MEDIUM": 58.0, "LOW": 34.0, "INFO": 15.0}
_IMPACT_KEYS = ("performance", "seo", "best_practices", "accessibility", "ai_access", "security")
_AI_HTML_LIMIT = 12000
_TEXT_CONTEXT_LIMIT = 24000
_ARTIFACT_LIMIT = 3 * 1024 * 1024


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().casefold() in {"1", "true", "yes", "on", "s", "sim"}


def validate_analysis_language(value: str) -> str:
    candidate = value.strip() or "auto"
    if candidate.casefold() == "auto":
        return "auto"
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", candidate):
        raise ValueError("idioma de análise deve ser 'auto' ou uma tag BCP-47 simples, ex.: pt-BR, en-US")
    pieces = candidate.split("-")
    if len(pieces) >= 2 and len(pieces[1]) == 2:
        pieces[1] = pieces[1].upper()
    pieces[0] = pieces[0].lower()
    return "-".join(pieces)


def configured_analysis_language(env: Mapping[str, str] | None = None, *, audit_language: str = "pt-BR") -> str:
    environment = os.environ if env is None else env
    configured = validate_analysis_language(environment.get(AI_ANALYSIS_LANGUAGE_ENV, "auto"))
    return audit_language if configured == "auto" else configured


def parse_domains(raw: str | Iterable[str] | None) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_DOMAINS
    if isinstance(raw, str):
        items = [item.strip().upper() for item in raw.replace(";", ",").split(",") if item.strip()]
    else:
        items = [str(item).strip().upper() for item in raw if str(item).strip()]
    unique = tuple(dict.fromkeys(items))
    if not unique:
        raise ValueError("selecione pelo menos um domínio para Improvement Intelligence")
    unknown = sorted(set(unique) - _ALLOWED_DOMAINS)
    if unknown:
        raise ValueError("domínios de análise desconhecidos: " + ", ".join(unknown))
    return unique


@dataclass(frozen=True, slots=True)
class ImprovementConfig:
    enabled: bool = False
    provider: str = ""
    model: str = ""
    reasoning: str = ""
    domains: tuple[str, ...] = DEFAULT_DOMAINS
    max_recommendations: int = 30
    timeout_seconds: float = 240.0
    language: str = "auto"

    def validate(self, env: Mapping[str, str] | None = None) -> "ImprovementConfig":
        environment = os.environ if env is None else env
        domains = parse_domains(self.domains)
        if self.max_recommendations < 1 or self.max_recommendations > 100:
            raise ValueError("Improvement Intelligence max_recommendations deve estar entre 1 e 100")
        if not math.isfinite(float(self.timeout_seconds)) or float(self.timeout_seconds) <= 0:
            raise ValueError("Improvement Intelligence timeout deve ser > 0")
        language = validate_analysis_language(self.language)
        provider = self.provider.strip().casefold()
        model = self.model.strip()
        reasoning = self.reasoning.strip().upper()
        if not self.enabled:
            return replace(self, provider=provider, model=model, reasoning=reasoning, domains=domains, language=language)
        if provider in {"", "none", "auto"}:
            raise ValueError("Improvement Intelligence exige um provider de IA explícito; AUTO/NONE não são permitidos")
        registration = get_provider_registration(provider)
        if registration is None:
            raise ValueError(f"provider de Improvement Intelligence desconhecido: {provider}")
        if not (environment.get(registration.key_env) or "").strip():
            raise ValueError(
                f"Improvement Intelligence requer {registration.key_env}; reutiliza a credencial já configurada para {registration.display_name}"
            )
        effective_model = model or registration.public_default_model
        if effective_model not in registration.supported_models:
            raise ValueError(
                f"modelo {effective_model!r} não é suportado por {registration.display_name}; use {', '.join(registration.supported_models)}"
            )
        effective_reasoning = reasoning or registration.reasoning_values[-1]
        if effective_reasoning not in registration.reasoning_values:
            raise ValueError(
                f"esforço {effective_reasoning!r} não é suportado por {registration.display_name}; use {', '.join(registration.reasoning_values)}"
            )
        return ImprovementConfig(
            enabled=True,
            provider=registration.id,
            model=effective_model,
            reasoning=effective_reasoning,
            domains=domains,
            max_recommendations=int(self.max_recommendations),
            timeout_seconds=float(self.timeout_seconds),
            language=language,
        )

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "ImprovementConfig":
        environment = os.environ if env is None else env
        try:
            maximum = int((environment.get(MAX_RECOMMENDATIONS_ENV) or "30").strip())
            timeout = float((environment.get(TIMEOUT_ENV) or "240").strip())
        except ValueError as exc:
            raise ValueError("Improvement Intelligence possui limite/timeout inválido") from exc
        return cls(
            enabled=_truthy(environment.get(ENABLED_ENV)),
            provider=environment.get(PROVIDER_ENV, ""),
            model=environment.get(MODEL_ENV, ""),
            reasoning=environment.get(REASONING_ENV, ""),
            domains=parse_domains(environment.get(DOMAINS_ENV) or DEFAULT_DOMAINS),
            max_recommendations=maximum,
            timeout_seconds=timeout,
            language=environment.get(AI_ANALYSIS_LANGUAGE_ENV, "auto"),
        ).validate(environment)

    def fingerprint(self) -> str:
        payload = {
            "contract": CONTRACT_VERSION,
            "provider": self.provider,
            "model": self.model,
            "reasoning": self.reasoning,
            "domains": self.domains,
            "max_recommendations": self.max_recommendations,
            "timeout_seconds": self.timeout_seconds,
            "language": self.language,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ImprovementResult:
    status: str
    target_url: str | None
    findings_count: int
    recommendations_count: int
    provider: str | None = None
    model: str | None = None
    reasoning: str | None = None
    reason: str | None = None
    reused: bool = False


@dataclass(frozen=True, slots=True)
class _TargetContext:
    page_id: str
    url: str
    input_url: str
    snapshot_id: str
    device: str
    snapshot_rows: tuple[sqlite3.Row, ...]
    audit_language: str
    market: str
    title: str | None
    description: str | None
    canonical: str | None
    html: str
    structured_data: Any


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.headings: list[dict[str, Any]] = []
        self.images_without_alt: list[dict[str, str]] = []
        self.anchors_without_href: list[dict[str, str]] = []
        self.buttons: list[dict[str, Any]] = []
        self.landmarks = {"main": 0, "nav": 0, "header": 0, "footer": 0}
        self.jsonld_count = 0
        self._heading: dict[str, Any] | None = None
        self._button_stack: list[dict[str, Any]] = []
        self._skip_depth = 0
        self.visible_text: list[str] = []

    @staticmethod
    def _signature(tag: str, attrs: dict[str, str]) -> str:
        if attrs.get("id"):
            return f"{tag}#{attrs['id']}"
        classes = [item for item in attrs.get("class", "").split() if item][:3]
        return tag + ("." + ".".join(classes) if classes else "")

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attrs = {str(key).casefold(): str(value or "") for key, value in attrs_list}
        original = (self.get_starttag_text() or f"<{tag}>")[:2000]
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "html":
            self.lang = attrs.get("lang") or None
        if tag in self.landmarks:
            self.landmarks[tag] += 1
        if tag == "script" and attrs.get("type", "").casefold() == "application/ld+json":
            self.jsonld_count += 1
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = {"level": int(tag[1]), "text": [], "html": original, "selector": self._signature(tag, attrs)}
        if tag == "img" and "alt" not in attrs:
            self.images_without_alt.append({"html": original, "selector": self._signature(tag, attrs)})
        if tag == "a" and not attrs.get("href"):
            self.anchors_without_href.append({"html": original, "selector": self._signature(tag, attrs)})
        if tag == "button":
            button = {"html": original, "selector": self._signature(tag, attrs), "text": [], "aria_label": attrs.get("aria-label", "")}
            self.buttons.append(button)
            self._button_stack.append(button)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self._heading["text"] = " ".join(" ".join(self._heading["text"]).split())[:1000]
            self.headings.append(self._heading)
            self._heading = None
        if tag == "button" and self._button_stack:
            button = self._button_stack.pop()
            button["text"] = " ".join(" ".join(button["text"]).split())[:500]
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._heading is not None:
            self._heading["text"].append(text)
        if self._button_stack:
            self._button_stack[-1]["text"].append(text)
        if self._skip_depth == 0:
            self.visible_text.append(text)


def _json_load(raw: Any, default: Any = None) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list, tuple, int, float, bool)):
        return raw
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).casefold() or "no such column" in str(exc).casefold():
            return []
        raise


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    rows = _many(connection, sql, params)
    return rows[0] if rows else None


def _read_artifact(workspace: AuditWorkspace, reference: str | None, *, limit: int = _ARTIFACT_LIMIT) -> str:
    if not reference:
        return ""
    path = workspace.root / str(reference)
    if not path.is_file():
        return ""
    try:
        raw = path.read_bytes()[:limit]
    except OSError:
        return ""
    if path.suffix.casefold() == ".gz":
        import gzip
        try:
            raw = gzip.decompress(raw)[:limit]
        except (OSError, EOFError):
            return ""
    return raw.decode("utf-8-sig", errors="replace")


def _target_context(connection: sqlite3.Connection, audit_id: str, workspace: AuditWorkspace) -> _TargetContext:
    targets = _many(connection, "SELECT * FROM audit_targets WHERE audit_id=? ORDER BY rowid", (audit_id,))
    if len(targets) != 1:
        raise ValueError(
            f"Improvement Intelligence exige exatamente uma URL de entrada; a auditoria possui {len(targets)} target(s)"
        )
    pages = _many(connection, "SELECT * FROM pages WHERE audit_id=? ORDER BY depth,page_id", (audit_id,))
    if not pages:
        raise ValueError("auditoria não possui página materializada para Improvement Intelligence")
    target = targets[0]
    input_url = str(target["input_url"])
    input_norm = input_url.rstrip("/").casefold()
    page = next(
        (row for row in pages if str(row["normalized_url"]).rstrip("/").casefold() == input_norm),
        pages[0],
    )
    page_id = str(page["page_id"])
    snapshots = _many(
        connection,
        "SELECT * FROM page_snapshots WHERE page_id=? ORDER BY CASE device WHEN 'MOBILE' THEN 0 WHEN 'DESKTOP' THEN 1 ELSE 2 END,captured_at",
        (page_id,),
    )
    if not snapshots:
        raise ValueError("URL alvo não possui snapshot para Improvement Intelligence")
    selected = next((row for row in snapshots if row["rendered_artifact_ref"]), snapshots[0])
    html = _read_artifact(workspace, selected["rendered_artifact_ref"] or selected["raw_artifact_ref"])
    if not html:
        raw_evidence = _one(
            connection,
            "SELECT artifact_reference FROM evidence WHERE audit_id=? AND page_id=? AND evidence_type='HTTP_RESPONSE' AND artifact_reference IS NOT NULL ORDER BY captured_at LIMIT 1",
            (audit_id, page_id),
        )
        html = _read_artifact(workspace, raw_evidence["artifact_reference"] if raw_evidence else None)
    audit = _one(connection, "SELECT primary_language,market FROM audits WHERE audit_id=?", (audit_id,))
    structured = _read_artifact(workspace, selected["structured_data_ref"])
    return _TargetContext(
        page_id=page_id,
        url=str(selected["final_url"] or page["normalized_url"]),
        input_url=input_url,
        snapshot_id=str(selected["snapshot_id"]),
        device=str(selected["device"]),
        snapshot_rows=tuple(snapshots),
        audit_language=str(audit["primary_language"] if audit else "pt-BR"),
        market=str(audit["market"] if audit else "BR"),
        title=str(selected["title"]) if selected["title"] else None,
        description=str(selected["description"]) if selected["description"] else None,
        canonical=str(selected["canonical"]) if selected["canonical"] else None,
        html=html,
        structured_data=_json_load(structured, structured if structured else None),
    )


def _impacts(**kwargs: int) -> dict[str, int]:
    return {key: max(0, min(3, int(kwargs.get(key, 0)))) for key in _IMPACT_KEYS}


def _finding(
    *, finding_id: str, domain: str, severity: str, title: str, observation: str,
    evidence_ids: Iterable[str], impacts: Mapping[str, int], source: str,
    selector: str | None = None, original_html: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "domain": domain,
        "severity": severity if severity in _SEVERITY_WEIGHT else "MEDIUM",
        "title": title[:500],
        "observation": observation[:4000],
        "evidence_ids": list(dict.fromkeys(str(item) for item in evidence_ids if str(item))),
        "impacts": _impacts(**dict(impacts)),
        "source": source,
        "selector": (selector or "")[:2000] or None,
        "original_html": (original_html or "")[:4000] or None,
        "details": dict(details or {}),
    }


def _existing_findings(connection: sqlite3.Connection, audit_id: str, context: _TargetContext) -> list[dict[str, Any]]:
    rows = _many(
        connection,
        "SELECT * FROM findings WHERE audit_id=? AND page_id=? ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END,finding_id",
        (audit_id, context.page_id),
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        category = str(row["category"] or "").upper()
        domain = "SEMANTICS_STRUCTURE"
        impacts = _impacts(seo=2, ai_access=2)
        if "ACCESS" in category:
            domain, impacts = "ACCESSIBILITY", _impacts(accessibility=3, best_practices=1)
        elif any(token in category for token in ("CRAWL", "DISCOVERY", "INDEX", "CANON")):
            domain, impacts = "TECHNICAL_HTML", _impacts(seo=3, ai_access=3, best_practices=1)
        elif any(token in category for token in ("CONTENT", "INTENT", "ANSWER", "TRUST", "CITATION")):
            domain, impacts = "CONTENT", _impacts(seo=2, ai_access=3)
        elif "STRUCTURED" in category or "ENTITY" in category or "SEMANTIC" in category:
            domain, impacts = "SEMANTICS_STRUCTURE", _impacts(seo=2, ai_access=3)
        observed = _json_load(row["observed_value"], row["observed_value"])
        output.append(_finding(
            finding_id=f"CORE:{row['finding_id']}", domain=domain, severity=str(row["severity"]),
            title=str(row["title"]), observation=json.dumps(observed, ensure_ascii=False) if not isinstance(observed, str) else observed,
            evidence_ids=_json_load(row["evidence_ids"], []) or [], impacts=impacts, source="RASAI_FINDING",
            details={"rule_id": row["rule_id"], "expected_condition": row["expected_condition"], "status": row["status"]},
        ))
    return output


def _structure_findings(context: _TargetContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parser = _StructureParser()
    try:
        parser.feed(context.html or "")
    except Exception:
        pass
    findings: list[dict[str, Any]] = []
    h1s = [item for item in parser.headings if item["level"] == 1]
    if len(h1s) != 1:
        findings.append(_finding(
            finding_id="HTML:H1_COUNT", domain="SEMANTICS_STRUCTURE", severity="HIGH" if not h1s else "MEDIUM",
            title="Estrutura H1 não possui exatamente um heading principal",
            observation=f"Foram observados {len(h1s)} elementos H1 na URL alvo.", evidence_ids=["HTML:STRUCTURE"],
            impacts=_impacts(seo=3, accessibility=2, ai_access=3), source="HTML_STRUCTURE",
            selector=h1s[0]["selector"] if h1s else None, original_html=h1s[0]["html"] if h1s else None,
        ))
    if not context.title:
        findings.append(_finding(
            finding_id="HTML:TITLE_MISSING", domain="SEARCH_RANKING", severity="HIGH", title="Elemento title ausente",
            observation="O snapshot não possui title observável.", evidence_ids=["SNAPSHOT:TITLE"],
            impacts=_impacts(seo=3, ai_access=2, accessibility=1), source="HTML_STRUCTURE", original_html="<head>…</head>",
        ))
    if not context.description:
        findings.append(_finding(
            finding_id="HTML:META_DESCRIPTION_MISSING", domain="CONTENT", severity="MEDIUM", title="Meta description ausente",
            observation="O snapshot não possui meta description observável.", evidence_ids=["SNAPSHOT:DESCRIPTION"],
            impacts=_impacts(seo=2, ai_access=1), source="HTML_STRUCTURE", original_html="<head>…</head>",
        ))
    if not context.canonical:
        findings.append(_finding(
            finding_id="HTML:CANONICAL_MISSING", domain="TECHNICAL_HTML", severity="MEDIUM", title="Canonical não observado",
            observation="O snapshot não possui link rel=canonical persistido.", evidence_ids=["SNAPSHOT:CANONICAL"],
            impacts=_impacts(seo=3, ai_access=1, best_practices=1), source="HTML_STRUCTURE", original_html="<head>…</head>",
        ))
    if not parser.lang:
        findings.append(_finding(
            finding_id="HTML:LANG_MISSING", domain="SEMANTICS_STRUCTURE", severity="MEDIUM", title="Idioma do documento não declarado em <html lang>",
            observation="O HTML analisado não declara atributo lang no elemento html.", evidence_ids=["HTML:STRUCTURE"],
            impacts=_impacts(accessibility=3, seo=1, ai_access=2), source="HTML_STRUCTURE", original_html="<html>", selector="html",
        ))
    if parser.landmarks["main"] == 0:
        findings.append(_finding(
            finding_id="HTML:MAIN_LANDMARK_MISSING", domain="SEMANTICS_STRUCTURE", severity="MEDIUM", title="Landmark <main> não observado",
            observation="O HTML rastreado não contém elemento main.", evidence_ids=["HTML:STRUCTURE"],
            impacts=_impacts(accessibility=3, ai_access=2, seo=1), source="HTML_STRUCTURE",
        ))
    previous = None
    for item in parser.headings:
        level = int(item["level"])
        if previous is not None and level > previous + 1:
            findings.append(_finding(
                finding_id=f"HTML:HEADING_JUMP:{len(findings)}", domain="SEMANTICS_STRUCTURE", severity="LOW",
                title="Hierarquia de headings apresenta salto de nível",
                observation=f"Heading H{previous} é seguido por H{level}: {item['text']!r}.", evidence_ids=["HTML:STRUCTURE"],
                impacts=_impacts(accessibility=2, seo=1, ai_access=2), source="HTML_STRUCTURE", selector=item["selector"], original_html=item["html"],
            ))
        previous = level
    if context.title and h1s:
        title_terms = {token for token in re.findall(r"\w+", context.title.casefold()) if len(token) > 2}
        h1_terms = {token for token in re.findall(r"\w+", str(h1s[0]["text"]).casefold()) if len(token) > 2}
        union = title_terms | h1_terms
        similarity = len(title_terms & h1_terms) / len(union) if union else 1.0
        if similarity < 0.2:
            findings.append(_finding(
                finding_id="HTML:TITLE_H1_LOW_COHERENCE", domain="CONTENT", severity="MEDIUM",
                title="Baixa coerência lexical entre title e H1",
                observation=f"Similaridade lexical simples title↔H1={similarity:.2f}; title={context.title!r}; H1={h1s[0]['text']!r}.",
                evidence_ids=["SNAPSHOT:TITLE", "HTML:STRUCTURE"], impacts=_impacts(seo=2, ai_access=2), source="SEMANTIC_COHERENCE",
                selector=h1s[0]["selector"], original_html=h1s[0]["html"],
            ))
    for index, item in enumerate(parser.images_without_alt[:25], 1):
        findings.append(_finding(
            finding_id=f"HTML:IMG_ALT:{index}", domain="ACCESSIBILITY", severity="MEDIUM", title="Imagem sem atributo alt",
            observation="Elemento img não possui atributo alt; conteúdo/decoração precisa ser classificado antes da correção.", evidence_ids=["HTML:STRUCTURE"],
            impacts=_impacts(accessibility=3, seo=1, ai_access=1), source="HTML_STRUCTURE", selector=item["selector"], original_html=item["html"],
        ))
    for index, item in enumerate(parser.buttons[:25], 1):
        if not str(item.get("text") or "").strip() and not str(item.get("aria_label") or "").strip():
            findings.append(_finding(
                finding_id=f"HTML:BUTTON_NAME:{index}", domain="ACCESSIBILITY", severity="HIGH", title="Botão sem nome acessível observável",
                observation="Elemento button não possui texto visível nem aria-label no HTML rastreado.", evidence_ids=["HTML:STRUCTURE"],
                impacts=_impacts(accessibility=3, best_practices=2, ai_access=1), source="HTML_STRUCTURE", selector=item["selector"], original_html=item["html"],
            ))
    for index, item in enumerate(parser.anchors_without_href[:25], 1):
        findings.append(_finding(
            finding_id=f"HTML:ANCHOR_HREF:{index}", domain="TECHNICAL_HTML", severity="LOW", title="Elemento <a> sem destino href",
            observation="Elemento de âncora não expõe destino rastreável via href.", evidence_ids=["HTML:STRUCTURE"],
            impacts=_impacts(seo=2, accessibility=2, ai_access=2), source="HTML_STRUCTURE", selector=item["selector"], original_html=item["html"],
        ))
    words = re.findall(r"\w+", " ".join(parser.visible_text), flags=re.UNICODE)
    summary = {
        "html_language": parser.lang,
        "heading_count": len(parser.headings),
        "h1_count": len(h1s),
        "headings": [{"level": item["level"], "text": item["text"]} for item in parser.headings[:80]],
        "landmarks": parser.landmarks,
        "jsonld_script_count": parser.jsonld_count,
        "visible_word_count": len(words),
        "visible_text_excerpt": " ".join(parser.visible_text)[:_TEXT_CONTEXT_LIMIT],
    }
    return findings, summary


def _header_map(connection: sqlite3.Connection, audit_id: str, page_id: str) -> tuple[dict[str, list[str]], list[str]]:
    rows = _many(connection, "SELECT evidence_id,observed_value FROM evidence WHERE audit_id=? AND page_id=? AND evidence_type='HTTP_HEADER' ORDER BY captured_at", (audit_id, page_id))
    headers: dict[str, list[str]] = {}
    evidence_ids: list[str] = []
    for row in rows:
        payload = _json_load(row["observed_value"], {}) or {}
        for pair in payload.get("headers", []) if isinstance(payload, dict) else []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            name, value = str(pair[0]).casefold(), str(pair[1])
            headers.setdefault(name, []).append(value)
        evidence_ids.append(str(row["evidence_id"]))
    return headers, evidence_ids


def _security_findings(connection: sqlite3.Connection, audit_id: str, context: _TargetContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    headers, evidence_ids = _header_map(connection, audit_id, context.page_id)
    findings: list[dict[str, Any]] = []
    scheme = urlsplit(context.url).scheme.casefold()
    ev = evidence_ids or ["HTTP:HEADERS_UNAVAILABLE"]
    if scheme != "https":
        findings.append(_finding(finding_id="SECURITY:HTTPS", domain="SECURITY", severity="HIGH", title="URL final não utiliza HTTPS", observation=f"Esquema observado: {scheme or 'desconhecido'}.", evidence_ids=ev, impacts=_impacts(security=3, best_practices=3, seo=1), source="PASSIVE_SECURITY"))
    if headers:
        csp = headers.get("content-security-policy", [])
        if not csp:
            findings.append(_finding(finding_id="SECURITY:CSP", domain="SECURITY", severity="MEDIUM", title="Content-Security-Policy não observado", observation="A resposta HTTP capturada não inclui header Content-Security-Policy. Isto é postura defensiva ausente, não prova exploração.", evidence_ids=ev, impacts=_impacts(security=3, best_practices=2), source="PASSIVE_SECURITY"))
        if scheme == "https" and "strict-transport-security" not in headers:
            findings.append(_finding(finding_id="SECURITY:HSTS", domain="SECURITY", severity="MEDIUM", title="Strict-Transport-Security não observado", observation="HTTPS foi observado, porém o header HSTS não consta na evidência HTTP persistida.", evidence_ids=ev, impacts=_impacts(security=3, best_practices=2), source="PASSIVE_SECURITY"))
        has_frame_ancestors = any("frame-ancestors" in value.casefold() for value in csp)
        if "x-frame-options" not in headers and not has_frame_ancestors:
            findings.append(_finding(finding_id="SECURITY:FRAME_ANCESTORS", domain="SECURITY", severity="MEDIUM", title="Proteção explícita contra framing não observada", observation="Não foi observado X-Frame-Options nem diretiva CSP frame-ancestors.", evidence_ids=ev, impacts=_impacts(security=2, best_practices=2), source="PASSIVE_SECURITY"))
        if "x-content-type-options" not in headers:
            findings.append(_finding(finding_id="SECURITY:NOSNIFF", domain="SECURITY", severity="LOW", title="X-Content-Type-Options não observado", observation="O header X-Content-Type-Options não consta na resposta HTTP persistida.", evidence_ids=ev, impacts=_impacts(security=1, best_practices=2), source="PASSIVE_SECURITY"))
        if "referrer-policy" not in headers:
            findings.append(_finding(finding_id="SECURITY:REFERRER_POLICY", domain="SECURITY", severity="LOW", title="Referrer-Policy não observado", observation="A política de referrer não foi explicitada na resposta HTTP capturada.", evidence_ids=ev, impacts=_impacts(security=1, best_practices=1), source="PASSIVE_SECURITY"))
        cookies = headers.get("set-cookie", [])
        for index, cookie in enumerate(cookies[:20], 1):
            lower = cookie.casefold()
            if scheme == "https" and "secure" not in lower:
                findings.append(_finding(finding_id=f"SECURITY:COOKIE_SECURE:{index}", domain="SECURITY", severity="HIGH", title="Cookie definido sem flag Secure em contexto HTTPS", observation=f"Set-Cookie #{index} não apresenta flag Secure. O valor do cookie não é reproduzido no relatório.", evidence_ids=ev, impacts=_impacts(security=3, best_practices=2), source="PASSIVE_SECURITY"))
            if "samesite" not in lower:
                findings.append(_finding(finding_id=f"SECURITY:COOKIE_SAMESITE:{index}", domain="SECURITY", severity="LOW", title="Cookie sem SameSite explícito", observation=f"Set-Cookie #{index} não apresenta atributo SameSite.", evidence_ids=ev, impacts=_impacts(security=1, best_practices=1), source="PASSIVE_SECURITY"))
        server = "; ".join(headers.get("server", []))
        if re.search(r"\d+(?:\.\d+)+", server):
            findings.append(_finding(finding_id="SECURITY:SERVER_VERSION", domain="SECURITY", severity="LOW", title="Header Server aparenta expor versão", observation="O header Server contém marcador de versão; revisar necessidade de exposição.", evidence_ids=ev, impacts=_impacts(security=1), source="PASSIVE_SECURITY"))
    return findings, {"mode": "PASSIVE_ONLY", "active_exploitation": False, "headers_available": bool(headers), "observed_header_names": sorted(headers), "https": scheme == "https", "note": "Ausências de headers indicam postura/configuração observada; não equivalem a vulnerabilidade explorável confirmada."}


def _lighthouse_findings(connection: sqlite3.Connection, audit_id: str, context: _TargetContext, workspace: AuditWorkspace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not _table_exists(connection, "web_performance_observations"):
        return [], []
    rows = _many(connection, "SELECT * FROM web_performance_observations WHERE audit_id=? AND page_id=? ORDER BY device", (audit_id, context.page_id))
    findings: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for row in rows:
        ref = str(row["pagespeed_artifact_reference"] or "")
        payload = _json_load(_read_artifact(workspace, ref), {}) or {}
        lh = payload.get("lighthouseResult", {}) if isinstance(payload, dict) else {}
        categories = lh.get("categories", {}) if isinstance(lh, dict) else {}
        audits = lh.get("audits", {}) if isinstance(lh, dict) else {}
        audit_categories: dict[str, set[str]] = {}
        for category_name, category in categories.items() if isinstance(categories, dict) else []:
            if isinstance(category, dict):
                for ref_item in category.get("auditRefs", []) or []:
                    if isinstance(ref_item, dict) and ref_item.get("id"):
                        audit_categories.setdefault(str(ref_item["id"]), set()).add(str(category_name))
        summaries.append({"device": row["device"], "status": row["status"], "performance_score": row["performance_score"], "accessibility_score": row["accessibility_score"], "best_practices_score": row["best_practices_score"], "seo_score": row["seo_score"], "agentic_browsing_score": row["agentic_browsing_score"], "lcp_lab_ms": row["lcp_lab_ms"], "tbt_lab_ms": row["tbt_lab_ms"], "cls_lab": row["cls_lab"], "lcp_p75_ms": row["lcp_p75_ms"], "inp_p75_ms": row["inp_p75_ms"], "cls_p75": row["cls_p75"], "cwv_assessment": row["cwv_assessment"], "artifact_reference": ref})
        if not isinstance(audits, dict):
            continue
        for audit_id_lh, audit in audits.items():
            if not isinstance(audit, dict):
                continue
            score = audit.get("score")
            mode = str(audit.get("scoreDisplayMode") or "")
            if not isinstance(score, (int, float)) or score >= 0.9 or mode in {"notApplicable", "manual", "informative"}:
                continue
            cats = audit_categories.get(str(audit_id_lh), set())
            impacts = _impacts(performance=3 if "performance" in cats else 0, accessibility=3 if "accessibility" in cats else 0, best_practices=3 if "best-practices" in cats else 0, seo=3 if "seo" in cats else 0, ai_access=2 if "agentic-browsing" in cats else 0, security=2 if str(audit_id_lh) in {"csp-xss", "is-on-https", "no-vulnerable-libraries", "inspector-issues"} else 0)
            domain = "PERFORMANCE" if impacts["performance"] else "ACCESSIBILITY" if impacts["accessibility"] else "BEST_PRACTICES" if impacts["best_practices"] else "SEARCH_RANKING" if impacts["seo"] else "AI_ACCESS"
            if impacts["security"] >= 2:
                domain = "SECURITY"
            details = audit.get("details") if isinstance(audit.get("details"), dict) else {}
            item = None
            for candidate in details.get("items", []) if isinstance(details, dict) else []:
                if isinstance(candidate, dict):
                    node = candidate.get("node")
                    if isinstance(node, dict) and (node.get("selector") or node.get("snippet")):
                        item = candidate; break
            node = item.get("node", {}) if isinstance(item, dict) else {}
            selector = str(node.get("selector") or node.get("path") or "") or None
            snippet = str(node.get("snippet") or "") or None
            savings = {key: details[key] for key in ("overallSavingsMs", "overallSavingsBytes") if isinstance(details, dict) and details.get(key) is not None}
            severity = "HIGH" if score < 0.5 else "MEDIUM" if score < 0.8 else "LOW"
            findings.append(_finding(finding_id=f"LIGHTHOUSE:{row['device']}:{audit_id_lh}", domain=domain, severity=severity, title=str(audit.get("title") or audit_id_lh), observation=str(audit.get("description") or "Auditoria Lighthouse não atingiu score máximo."), evidence_ids=[f"LIGHTHOUSE:{ref}:{audit_id_lh}"], impacts=impacts, source="LIGHTHOUSE", selector=selector, original_html=snippet, details={"audit_id": audit_id_lh, "device": row["device"], "score": score, "numericValue": audit.get("numericValue"), "numericUnit": audit.get("numericUnit"), "savings": savings, "artifact_reference": ref}))
    return findings[:100], summaries


def _discovery_context(connection: sqlite3.Connection, audit_id: str, workspace: AuditWorkspace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    rows = _many(connection, "SELECT evidence_id,evidence_type,source,observed_value,artifact_reference FROM evidence WHERE audit_id=? AND evidence_type IN ('ROBOTS_RULE','SITEMAP_ENTRY') ORDER BY captured_at,evidence_id", (audit_id,))
    for row in rows:
        resources.append({"evidence_id": row["evidence_id"], "type": row["evidence_type"], "source": row["source"], "observed": _json_load(row["observed_value"], {}) or {}, "content_excerpt": _read_artifact(workspace, row["artifact_reference"], limit=12000)[:12000]})
    diagnostics = _many(connection, "SELECT * FROM m24_diagnostics WHERE audit_id=? ORDER BY diagnostic_id", (audit_id,)) if _table_exists(connection, "m24_diagnostics") else []
    for row in diagnostics:
        severity = str(row["severity"] or "INFO").upper()
        if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            continue
        category = str(row["category"] or "").upper()
        domain = "AI_ACCESS" if category == "AI_ACCESS" else "FILES_DISCOVERY"
        findings.append(_finding(finding_id=f"DISCOVERY:{row['diagnostic_id']}", domain=domain, severity=severity, title=str(row["title"]), observation=str(row["remediation"] or row["observed_value"] or ""), evidence_ids=_json_load(row["evidence_ids"], []) or [], impacts=_impacts(seo=2 if domain == "FILES_DISCOVERY" else 1, ai_access=3, best_practices=1), source="CRAWLING_DISCOVERY", details={"code": row["code"], "category": category, "scope_url": row["scope_url"]}))
    run = _one(connection, "SELECT * FROM m24_runs WHERE audit_id=?", (audit_id,)) if _table_exists(connection, "m24_runs") else None
    return findings, {"resources": resources[:20], "run": dict(run) if run is not None else None, "policy": "llms.txt é experimental e sua ausência não é tratada como falha; robots/sitemap seguem os contratos técnicos existentes do RASAi."}


def _search_context(connection: sqlite3.Connection, audit_id: str, context: _TargetContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not _table_exists(connection, "serp_observations"):
        return [], {"available": False, "observations": []}
    observations = _many(connection, "SELECT * FROM serp_observations WHERE audit_id=? ORDER BY collected_at DESC LIMIT 20", (audit_id,))
    findings: list[dict[str, Any]] = []
    payload_observations: list[dict[str, Any]] = []
    for row in observations:
        obs = {"observation_id": row["observation_id"], "query": row["query"], "engine": row["engine"], "country": row["country"], "region": row["region"], "language": row["language"], "device": row["device"], "customer_position": row["customer_position"], "domain_status": row["domain_status"], "result_count": row["result_count"], "collected_at": row["collected_at"]}
        observation_id = str(row["observation_id"])
        competitive = _one(connection, "SELECT * FROM serp_competitive_analyses WHERE observation_id=?", (observation_id,)) if _table_exists(connection, "serp_competitive_analyses") else None
        gaps = _json_load(competitive["gaps_json"], []) if competitive is not None else []
        obs["competitive_gaps"] = gaps
        if _table_exists(connection, "serp_competitive_pages"):
            pages = _many(connection, "SELECT role,domain,requested_url,title,meta_description,headings_json,word_count,query_terms_json,query_terms_title_json,query_terms_description_json,query_terms_headings_json,query_terms_body_json,jsonld_types_json FROM serp_competitive_pages WHERE observation_id=? ORDER BY role,domain", (observation_id,))
            obs["competitive_pages"] = [{**dict(page), **{key: _json_load(page[key], []) for key in ("headings_json", "query_terms_json", "query_terms_title_json", "query_terms_description_json", "query_terms_headings_json", "query_terms_body_json", "jsonld_types_json")}} for page in pages[:15]]
        for index, gap in enumerate(gaps or [], 1):
            if isinstance(gap, dict):
                findings.append(_finding(finding_id=f"SERP:{observation_id}:{index}", domain="SEARCH_RANKING", severity=str(gap.get("severity") or "MEDIUM").upper(), title=f"Gap competitivo para '{row['query']}': {gap.get('code') or 'diferença observada'}", observation=str(gap.get("message") or "Diferença competitiva observada."), evidence_ids=[f"SERP:{observation_id}", *[str(item) for item in gap.get("evidence_urls", [])]], impacts=_impacts(seo=3, ai_access=2), source="SERP_COMPETITIVE_GAP", details={"query": row["query"], "position": row["customer_position"], "gap": gap, "causality_note": "Diferença observada não prova causalidade de ranking."}))
        payload_observations.append(obs)
    return findings, {"available": bool(observations), "observations": payload_observations}


def _dedupe_findings(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []; seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (str(item.get("domain")), str(item.get("selector") or ""), str(item.get("title") or "").casefold())
        if key not in seen:
            seen.add(key); result.append(item)
    result.sort(key=lambda item: (-_SEVERITY_WEIGHT.get(str(item.get("severity")), 0), str(item.get("domain")), str(item.get("title"))))
    return result[:180]


def _schema(findings: list[dict[str, Any]], maximum: int) -> dict[str, Any]:
    ids = [str(item["finding_id"]) for item in findings]
    evidence = sorted({str(ev) for item in findings for ev in item.get("evidence_ids", [])})
    return {"type": "object", "additionalProperties": False, "required": ["summary", "recommendations"], "properties": {"summary": {"type": "string", "maxLength": 4000}, "recommendations": {"type": "array", "maxItems": maximum, "items": {"type": "object", "additionalProperties": False, "required": ["finding_id", "title", "recommendation", "rationale", "evidence_ids", "confidence", "effort", "suggested_html", "suggested_text", "verification"], "properties": {"finding_id": {"type": "string", "enum": ids}, "title": {"type": "string", "maxLength": 500}, "recommendation": {"type": "string", "maxLength": 4000}, "rationale": {"type": "string", "maxLength": 4000}, "evidence_ids": {"type": "array", "uniqueItems": True, "maxItems": 20, "items": {"type": "string", "enum": evidence}}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "effort": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]}, "suggested_html": {"anyOf": [{"type": "string", "maxLength": 8000}, {"type": "null"}]}, "suggested_text": {"anyOf": [{"type": "string", "maxLength": 8000}, {"type": "null"}]}, "verification": {"type": "string", "maxLength": 2500}}}}}}


def _instructions(language: str, domains: tuple[str, ...]) -> str:
    labels = ", ".join(DOMAIN_LABELS[item] for item in domains)
    return ("You are the evidence-bound Deep Improvement Analysis specialist for RASAi. Analyze exactly one audited URL using only the supplied persisted evidence. Return JSON only and match the schema exactly. Do not score or alter SARI/SCORE-GEO. Do not claim that a change will cause a specific search ranking. SERP differences are correlational context only. Security is passive posture analysis only: do not propose exploitation, payloads, bypasses, credential attacks, or active scanning. Never invent facts, prices, credentials, statistics, testimonials, certifications, product properties or evidence. For technical findings with original_html, suggested_html should contain a concrete corrected element when the correction is safe. For content/search findings, propose precise people-first wording only when supported by page/competitive evidence; otherwise explain what information must be supplied. Cite only evidence_ids attached to the referenced finding. Human review is mandatory. " + f"Write all explanatory and suggested text in {language}. Selected domains: {labels}.")


def _provider_payload(provider: Any, *, instructions: str, user_text: str, schema: dict[str, Any]) -> dict[str, Any]:
    name = str(getattr(provider, "name", "")).upper(); model = str(getattr(provider, "model", ""))
    if isinstance(provider, ResponsesSemanticProvider):
        if provider.structured_mode == "json_object":
            instructions += "\nNormative local JSON Schema:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":")); fmt: dict[str, Any] = {"type": "json_object"}
        else:
            fmt = {"type": "json_schema", "name": "rasai_improvement_intelligence", "schema": schema}
            if name == "OPENAI": fmt["strict"] = True
        return {"model": model, "instructions": instructions, "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}], "reasoning": {"effort": str(provider.requested_reasoning_effort).casefold()}, "text": {"format": fmt}}
    if name == "COPILOT":
        return {"model": model, "prompt": instructions + "\n\nJSON Schema:\n" + json.dumps(schema, ensure_ascii=False) + "\n\n" + user_text}
    if isinstance(provider, XAIProvider):
        return {"model": model, "instructions": instructions, "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}], "reasoning": {"effort": str(getattr(provider, "reasoning_profile", "HIGH")).casefold()}, "text": {"format": {"type": "json_schema", "name": "rasai_improvement_intelligence", "schema": schema, "strict": True}}}
    if isinstance(provider, QwenProvider):
        return {"model": model, "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": user_text}], "response_format": {"type": "json_schema", "json_schema": {"name": "rasai_improvement_intelligence", "schema": schema, "strict": True}}}
    if isinstance(provider, GeminiProvider):
        return {"model": model, "input": instructions + "\n\n" + user_text, "response_format": {"type": "text", "mime_type": "application/json", "schema": gemini_wire_schema(schema)}}
    if isinstance(provider, AnthropicProvider):
        return {"model": model, "max_tokens": 16384, "system": instructions, "messages": [{"role": "user", "content": user_text}], "output_config": {"format": {"type": "json_schema", "schema": schema}}}
    raise ValueError(f"provider Improvement Intelligence incompatível: {type(provider).__name__}")


def _provider_extract(provider: Any, raw: Mapping[str, Any]) -> Any:
    return _extract_json_payload(dict(raw)) if isinstance(provider, ResponsesSemanticProvider) else provider._extract_payload(raw)


def _provider_usage(provider: Any, raw: Mapping[str, Any]) -> ProviderUsage | None:
    return _usage_from_native(raw) if isinstance(provider, ResponsesSemanticProvider) else provider._usage(raw)


def _provider_native_error(provider: Any, raw: Mapping[str, Any]) -> ProviderDiagnostic | None:
    return _response_error(raw) if isinstance(provider, ResponsesSemanticProvider) else provider._native_error(raw)


def _validate_ai_payload(payload: Any, findings: list[dict[str, Any]], maximum: int) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("recommendations"), list):
        raise ValueError("Improvement Intelligence AI response inválida")
    finding_map = {str(item["finding_id"]): item for item in findings}; recommendations: list[dict[str, Any]] = []; seen: set[str] = set()
    for raw in payload["recommendations"][:maximum]:
        if not isinstance(raw, Mapping): raise ValueError("recommendation must be object")
        finding_id = str(raw.get("finding_id") or "")
        if finding_id not in finding_map: raise ValueError(f"unknown finding_id {finding_id!r}")
        if finding_id in seen: continue
        seen.add(finding_id); finding = finding_map[finding_id]
        evidence_ids = [str(item) for item in raw.get("evidence_ids", []) if str(item)]
        if not set(evidence_ids).issubset(set(finding["evidence_ids"])): raise ValueError("evidence outside finding")
        confidence = float(raw.get("confidence")); effort = str(raw.get("effort") or "MEDIUM").upper()
        if not 0 <= confidence <= 1 or effort not in {"LOW", "MEDIUM", "HIGH"}: raise ValueError("invalid confidence/effort")
        recommendations.append({"recommendation_id": new_id("IIR"), "finding_id": finding_id, "domain": finding["domain"], "severity": finding["severity"], "title": str(raw.get("title") or finding["title"])[:500], "recommendation": str(raw.get("recommendation") or "")[:4000], "rationale": str(raw.get("rationale") or "")[:4000], "evidence_ids": evidence_ids, "confidence": confidence, "effort": effort, "selector": finding.get("selector"), "original_html": finding.get("original_html"), "suggested_html": str(raw["suggested_html"])[:8000] if raw.get("suggested_html") is not None else None, "suggested_text": str(raw["suggested_text"])[:8000] if raw.get("suggested_text") is not None else None, "verification": str(raw.get("verification") or "")[:2500], "impacts": dict(finding["impacts"]), "source": "AI"})
    return str(payload.get("summary") or "")[:4000], recommendations


def _priority_score(item: Mapping[str, Any]) -> tuple[int, str]:
    severity = _SEVERITY_WEIGHT.get(str(item.get("severity") or "MEDIUM"), 58.0); impacts = item.get("impacts") if isinstance(item.get("impacts"), Mapping) else {}
    impact = sum(max(0, min(3, int(impacts.get(key, 0)))) for key in _IMPACT_KEYS) / (3 * len(_IMPACT_KEYS)) * 100.0
    confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0))) * 100.0; effort_factor = {"LOW": 1.08, "MEDIUM": 1.0, "HIGH": 0.90}.get(str(item.get("effort") or "MEDIUM"), 1.0)
    score = int(round(min(100.0, (severity * 0.45 + impact * 0.35 + confidence * 0.20) * effort_factor)))
    return score, "CRITICAL" if score >= 90 else "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"


class ImprovementPersistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self.connection = sqlite3.connect(workspace.database); self.connection.row_factory = sqlite3.Row; self.connection.execute("PRAGMA foreign_keys = ON"); self._initialize()
    def close(self) -> None: self.connection.close()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, traceback): self.close()
    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS improvement_intelligence_runs (audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,contract_version TEXT NOT NULL,enabled INTEGER NOT NULL,status TEXT NOT NULL,target_page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,target_url TEXT,provider TEXT,model TEXT,reasoning TEXT,analysis_language TEXT,domains_json TEXT NOT NULL,max_recommendations INTEGER NOT NULL,config_fingerprint TEXT NOT NULL,evidence_fingerprint TEXT,findings_count INTEGER NOT NULL,recommendations_count INTEGER NOT NULL,ai_summary TEXT,reason TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS improvement_intelligence_findings (finding_id TEXT PRIMARY KEY,audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,domain TEXT NOT NULL,severity TEXT NOT NULL,source TEXT NOT NULL,title TEXT NOT NULL,observation TEXT NOT NULL,selector TEXT,original_html TEXT,evidence_ids_json TEXT NOT NULL,impacts_json TEXT NOT NULL,details_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_improvement_findings_audit ON improvement_intelligence_findings(audit_id,domain,severity);
                CREATE TABLE IF NOT EXISTS improvement_intelligence_recommendations (recommendation_id TEXT PRIMARY KEY,audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,finding_id TEXT NOT NULL REFERENCES improvement_intelligence_findings(finding_id) ON DELETE CASCADE,domain TEXT NOT NULL,severity TEXT NOT NULL,priority TEXT NOT NULL,priority_score INTEGER NOT NULL,confidence REAL NOT NULL,effort TEXT NOT NULL,title TEXT NOT NULL,recommendation TEXT NOT NULL,rationale TEXT NOT NULL,selector TEXT,original_html TEXT,suggested_html TEXT,suggested_text TEXT,verification TEXT NOT NULL,evidence_ids_json TEXT NOT NULL,impacts_json TEXT NOT NULL,source TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_improvement_recs_audit ON improvement_intelligence_recommendations(audit_id,priority_score DESC,domain);
            """)
    def existing(self, audit_id: str) -> sqlite3.Row | None: return self.connection.execute("SELECT * FROM improvement_intelligence_runs WHERE audit_id=?", (audit_id,)).fetchone()
    def persist(self, *, audit_id: str, context: _TargetContext, config: ImprovementConfig, status: str, findings: list[dict[str, Any]], recommendations: list[dict[str, Any]], ai_summary: str, evidence_fingerprint: str, reason: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat(); existing = self.existing(audit_id); created = str(existing["created_at"]) if existing is not None else now
        with self.connection:
            self.connection.execute("DELETE FROM improvement_intelligence_recommendations WHERE audit_id=?", (audit_id,)); self.connection.execute("DELETE FROM improvement_intelligence_findings WHERE audit_id=?", (audit_id,))
            self.connection.executemany("INSERT INTO improvement_intelligence_findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [(item["finding_id"], audit_id, context.page_id, item["domain"], item["severity"], item["source"], item["title"], item["observation"], item.get("selector"), item.get("original_html"), json.dumps(item["evidence_ids"], ensure_ascii=False), json.dumps(item["impacts"], ensure_ascii=False, sort_keys=True), json.dumps(item.get("details") or {}, ensure_ascii=False, sort_keys=True)) for item in findings])
            rows = []
            for item in recommendations:
                score, priority = _priority_score(item); item["priority_score"] = score; item["priority"] = priority
                rows.append((item["recommendation_id"], audit_id, context.page_id, item["finding_id"], item["domain"], item["severity"], priority, score, item["confidence"], item["effort"], item["title"], item["recommendation"], item["rationale"], item.get("selector"), item.get("original_html"), item.get("suggested_html"), item.get("suggested_text"), item["verification"], json.dumps(item["evidence_ids"], ensure_ascii=False), json.dumps(item["impacts"], ensure_ascii=False, sort_keys=True), item["source"]))
            if rows: self.connection.executemany("INSERT INTO improvement_intelligence_recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.connection.execute("""INSERT INTO improvement_intelligence_runs (audit_id,contract_version,enabled,status,target_page_id,target_url,provider,model,reasoning,analysis_language,domains_json,max_recommendations,config_fingerprint,evidence_fingerprint,findings_count,recommendations_count,ai_summary,reason,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(audit_id) DO UPDATE SET contract_version=excluded.contract_version,enabled=excluded.enabled,status=excluded.status,target_page_id=excluded.target_page_id,target_url=excluded.target_url,provider=excluded.provider,model=excluded.model,reasoning=excluded.reasoning,analysis_language=excluded.analysis_language,domains_json=excluded.domains_json,max_recommendations=excluded.max_recommendations,config_fingerprint=excluded.config_fingerprint,evidence_fingerprint=excluded.evidence_fingerprint,findings_count=excluded.findings_count,recommendations_count=excluded.recommendations_count,ai_summary=excluded.ai_summary,reason=excluded.reason,updated_at=excluded.updated_at""", (audit_id, CONTRACT_VERSION, 1 if config.enabled else 0, status, context.page_id, context.url, config.provider or None, config.model or None, config.reasoning or None, config.language, json.dumps(config.domains), config.max_recommendations, config.fingerprint(), evidence_fingerprint, len(findings), len(recommendations), ai_summary or None, reason, created, now))


def _evidence_fingerprint(findings: list[dict[str, Any]], search: Mapping[str, Any], lighthouse: list[dict[str, Any]]) -> str:
    return sha256(json.dumps({"findings": findings, "search": search, "lighthouse": lighthouse}, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _build_provider(config: ImprovementConfig, env: Mapping[str, str] | None = None) -> Any:
    environment = dict(os.environ if env is None else env); registration = get_provider_registration(config.provider)
    if registration is None: raise ValueError(f"provider desconhecido: {config.provider}")
    reasoning_env = provider_reasoning_env(registration.provider_name)
    if reasoning_env: environment[reasoning_env] = config.reasoning
    provider = build_semantic_provider(config.provider, model_override=config.model, env=environment)
    if hasattr(provider, "timeout"): provider.timeout = config.timeout_seconds
    return provider


def _persist_attempt(workspace: AuditWorkspace, audit_id: str, context: _TargetContext, attempt: ProviderAttempt) -> None:
    with M18Persistence(workspace) as store:
        store.add_attempt(attempt_id=new_id("AIA"), audit_id=audit_id, page_id=context.page_id, snapshot_id=context.snapshot_id, url=context.url, device=context.device, attempt=attempt)


def _ai_analyze(*, audit_id: str, workspace: AuditWorkspace, context: _TargetContext, config: ImprovementConfig, findings: list[dict[str, Any]], evidence_context: Mapping[str, Any], language: str, progress: Callable[[str, float, str], None] | None = None) -> tuple[str, list[dict[str, Any]], str | None]:
    provider = _build_provider(config)
    if not getattr(provider, "api_key", None): return "", [], "AI_NOT_CONFIGURED"
    schema = _schema(findings, config.max_recommendations)
    request_context = {"contract_version": CONTRACT_VERSION, "target": {"url": context.url, "input_url": context.input_url, "device_snapshot_used": context.device, "market": context.market}, "selected_domains": list(config.domains), "page": {"title": context.title, "description": context.description, "canonical": context.canonical}, "findings": findings, "supporting_context": evidence_context, "governance": {"sari_score_impact": "NONE", "security_mode": "PASSIVE_ONLY", "ranking_causality": "FORBIDDEN", "human_review_required": True}}
    user_text = "Persisted RASAi evidence for one URL:\n" + json.dumps(request_context, ensure_ascii=False, default=str); instructions = _instructions(language, config.domains); body = json.dumps(_provider_payload(provider, instructions=instructions, user_text=user_text, schema=schema), ensure_ascii=False, separators=(",", ":")).encode("utf-8"); payload_hash = sha256(body).hexdigest(); summary_text = f"contract={CONTRACT_VERSION};findings={len(findings)};domains={len(config.domains)};snapshot={context.snapshot_id}"; last_reason = None
    for ordinal in range(1, min(2, MAX_PROVIDER_ATTEMPTS_PER_CONTEXT) + 1):
        if progress: progress("AI_ANALYSIS", 72.0 + ordinal * 8.0, f"consultando {getattr(provider,'name',config.provider)} / {config.model}; tentativa {ordinal}/2")
        started_at = datetime.now(timezone.utc); started_perf = time.perf_counter(); diagnostic = None; usage = None; raw = None; status = AttemptStatus.TECHNICAL_ERROR
        try:
            candidate = provider._transport(provider.endpoint, provider._headers(), body, config.timeout_seconds)
            if not isinstance(candidate, Mapping): diagnostic = ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE)
            else:
                raw = candidate; usage = _provider_usage(provider, raw); diagnostic = _provider_native_error(provider, raw)
                if diagnostic is None: status = AttemptStatus.SUCCESS
        except HTTPError as exc: diagnostic = _core_diagnostic_from_http(exc) if isinstance(provider, ResponsesSemanticProvider) else _extension_diagnostic_from_http(exc)
        except TimeoutError: diagnostic = ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR)
        except (URLError, OSError): diagnostic = ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR)
        except Exception as exc: diagnostic = ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR, error_type=type(exc).__name__)
        finished_at = datetime.now(timezone.utc); duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000)); estimated, currency, pricing_version = estimate_cost(str(provider.name), str(provider.model), usage, finished_at)
        if status is AttemptStatus.SUCCESS and raw is not None:
            try: ai_summary, recommendations = _validate_ai_payload(_provider_extract(provider, raw), findings, config.max_recommendations)
            except Exception as exc: status = AttemptStatus.CONTRACT_ERROR; diagnostic = ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__, error_code="IMPROVEMENT_OUTPUT_INVALID")
            else:
                attempt = ProviderAttempt(provider=str(provider.name), model=str(provider.model), reasoning_profile=str(getattr(provider, "reasoning_profile", config.reasoning)), provider_rank=int(getattr(provider.policy, "rank", 999)), attempt_index=ordinal, snapshot_id=context.snapshot_id, url=context.url, started_at=started_at, finished_at=finished_at, duration_ms=duration_ms, status=AttemptStatus.SUCCESS, usage=usage, estimated_cost=estimated, cost_currency=currency, pricing_version=pricing_version, request_message_summary=summary_text, request_payload_hash=payload_hash, provider_qualification=str(getattr(provider.policy, "qualification", "PROVISIONAL")), provider_reliability_score=getattr(provider.policy, "reliability_score", None), semantic_contract_version=CONTRACT_VERSION, retry_eligible=False, decision=DECISION_SUCCESS_AFTER_RETRY if ordinal > 1 else DECISION_SUCCESS)
                _persist_attempt(workspace, audit_id, context, attempt); return ai_summary, recommendations, None
        policy = retry_policy(diagnostic.error_class if diagnostic else None, diagnostic.retry_after_seconds if diagnostic else None); decision = DECISION_RETRY if policy.eligible and ordinal < 2 else DECISION_STOP
        attempt = ProviderAttempt(provider=str(provider.name), model=str(provider.model), reasoning_profile=str(getattr(provider, "reasoning_profile", config.reasoning)), provider_rank=int(getattr(provider.policy, "rank", 999)), attempt_index=ordinal, snapshot_id=context.snapshot_id, url=context.url, started_at=started_at, finished_at=finished_at, duration_ms=duration_ms, status=status, diagnostic=diagnostic, usage=usage, estimated_cost=estimated, cost_currency=currency, pricing_version=pricing_version, request_message_summary=summary_text, request_payload_hash=payload_hash, provider_qualification=str(getattr(provider.policy, "qualification", "PROVISIONAL")), provider_reliability_score=getattr(provider.policy, "reliability_score", None), semantic_contract_version=CONTRACT_VERSION, retry_eligible=policy.eligible, decision=decision)
        _persist_attempt(workspace, audit_id, context, attempt); last_reason = diagnostic.reason if diagnostic else "AI_PROVIDER_UNAVAILABLE"
        if decision == DECISION_RETRY:
            if policy.delay_seconds > 0: time.sleep(policy.delay_seconds)
            continue
        break
    return "", [], last_reason or "AI_PROVIDER_UNAVAILABLE"


def collect_improvement_evidence(*, audit_id: str, workspace: AuditWorkspace, config: ImprovementConfig, progress: Callable[[str, float, str], None] | None = None) -> tuple[_TargetContext, list[dict[str, Any]], dict[str, Any], str]:
    connection = sqlite3.connect(workspace.database); connection.row_factory = sqlite3.Row
    try:
        context = _target_context(connection, audit_id, workspace)
        if progress: progress("EVIDENCE", 12.0, "carregando findings, HTML e evidências persistidas da URL alvo")
        existing = _existing_findings(connection, audit_id, context); structure, structure_summary = _structure_findings(context)
        if progress: progress("HTML", 28.0, "analisando semântica, headings, elementos HTML e coerência estrutural")
        security, security_summary = _security_findings(connection, audit_id, context)
        if progress: progress("SECURITY", 40.0, "avaliando postura de segurança passiva nos headers já capturados")
        lighthouse, lighthouse_summary = _lighthouse_findings(connection, audit_id, context, workspace)
        if progress: progress("METRICS", 52.0, "correlacionando Lighthouse/PageSpeed com elementos e métricas afetadas")
        discovery, discovery_summary = _discovery_context(connection, audit_id, workspace)
        if progress: progress("DISCOVERY", 60.0, "revisando robots.txt, sitemap, llms.txt e diagnósticos de descoberta")
        search, search_summary = _search_context(connection, audit_id, context)
        if progress: progress("SERP", 68.0, "correlacionando posição SERP e gaps competitivos quando disponíveis")
    finally: connection.close()
    findings = [item for item in _dedupe_findings([*existing, *structure, *security, *lighthouse, *discovery, *search]) if item["domain"] in set(config.domains)]
    supporting = {"structure": structure_summary, "security": security_summary, "lighthouse": lighthouse_summary, "discovery": discovery_summary, "search": search_summary, "raw_html_excerpt": context.html[:_AI_HTML_LIMIT], "structured_data": context.structured_data}
    return context, findings, supporting, _evidence_fingerprint(findings, search_summary, lighthouse_summary)


def execute_improvement_intelligence(*, audit_id: str, workspace: AuditWorkspace, config: ImprovementConfig | None = None, force: bool = False, progress: Callable[[str, float, str], None] | None = None) -> ImprovementResult:
    cfg = (config or ImprovementConfig.from_environment()).validate()
    if not cfg.enabled: return ImprovementResult("DISABLED", None, 0, 0, reason="IMPROVEMENT_INTELLIGENCE_DISABLED")
    context, findings, supporting, fingerprint = collect_improvement_evidence(audit_id=audit_id, workspace=workspace, config=cfg, progress=progress); cfg = replace(cfg, language=configured_analysis_language(audit_language=context.audit_language))
    with ImprovementPersistence(workspace) as store:
        existing = store.existing(audit_id)
        if not force and existing is not None and str(existing["status"]) == "COMPLETE" and str(existing["config_fingerprint"]) == cfg.fingerprint() and str(existing["evidence_fingerprint"] or "") == fingerprint:
            return ImprovementResult("COMPLETE", context.url, int(existing["findings_count"]), int(existing["recommendations_count"]), provider=str(existing["provider"] or "") or None, model=str(existing["model"] or "") or None, reasoning=str(existing["reasoning"] or "") or None, reused=True)
    if progress: progress("AI_PREP", 70.0, f"preparando análise evidence-bound; {len(findings)} finding(s) elegível(is)")
    if not findings:
        with ImprovementPersistence(workspace) as store: store.persist(audit_id=audit_id, context=context, config=cfg, status="COMPLETE", findings=[], recommendations=[], ai_summary="Nenhum finding elegível foi identificado nos domínios selecionados.", evidence_fingerprint=fingerprint, reason=None)
        return ImprovementResult("COMPLETE", context.url, 0, 0, provider=cfg.provider, model=cfg.model, reasoning=cfg.reasoning)
    ai_summary, recommendations, reason = _ai_analyze(audit_id=audit_id, workspace=workspace, context=context, config=cfg, findings=findings, evidence_context=supporting, language=cfg.language, progress=progress); status = "COMPLETE" if reason is None else "COMPLETE_WITH_LIMITATIONS"
    with ImprovementPersistence(workspace) as store: store.persist(audit_id=audit_id, context=context, config=cfg, status=status, findings=findings, recommendations=recommendations, ai_summary=ai_summary, evidence_fingerprint=fingerprint, reason=reason)
    if progress: progress("PERSIST", 96.0, f"persistindo {len(recommendations)} recomendação(ões) e preparando relatório")
    return ImprovementResult(status, context.url, len(findings), len(recommendations), provider=cfg.provider, model=cfg.model, reasoning=cfg.reasoning, reason=reason)


def _html_diff(original: str | None, suggested: str | None) -> tuple[str, str]:
    if not original or not suggested: return escape(original or "-"), escape(suggested or "-")
    matcher = SequenceMatcher(None, original, suggested); left = []; right = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old, new = escape(original[i1:i2]), escape(suggested[j1:j2])
        if tag == "equal": left.append(old); right.append(new)
        elif tag == "delete": left.append(f"<mark class='diff-del'>{old}</mark>")
        elif tag == "insert": right.append(f"<mark class='diff-add'>{new}</mark>")
        else: left.append(f"<mark class='diff-del'>{old}</mark>"); right.append(f"<mark class='diff-add'>{new}</mark>")
    return "".join(left), "".join(right)


def _impact_badges(raw: Any) -> str:
    impacts = _json_load(raw, {}) if not isinstance(raw, dict) else raw; labels = {"performance": "Performance", "seo": "SEO", "best_practices": "Best Practices", "accessibility": "A11y", "ai_access": "AI Access", "security": "Security"}
    return " ".join(f"<span class='chip'>{escape(labels[key])}: {int(impacts.get(key,0))}/3</span>" for key in _IMPACT_KEYS if int(impacts.get(key, 0)) > 0)


def write_improvement_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    from rasai import report_navigation
    report_dir = workspace.root / "report"; report_dir.mkdir(parents=True, exist_ok=True); path = report_dir / REPORT_FILE
    connection = sqlite3.connect(workspace.database); connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM improvement_intelligence_runs WHERE audit_id=?", (audit_id,)) if _table_exists(connection, "improvement_intelligence_runs") else None
        findings = _many(connection, "SELECT * FROM improvement_intelligence_findings WHERE audit_id=? ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END,domain,title", (audit_id,)) if run else []
        recs = _many(connection, "SELECT * FROM improvement_intelligence_recommendations WHERE audit_id=? ORDER BY priority_score DESC,domain,title", (audit_id,)) if run else []
        attempts = _many(connection, "SELECT * FROM ai_provider_attempts WHERE audit_id=? AND semantic_contract_version=? ORDER BY started_at,attempt_index", (audit_id, CONTRACT_VERSION)) if _table_exists(connection, "ai_provider_attempts") else []
    finally: connection.close()
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE); status = str(run["status"]) if run else "NOT_EXECUTED"; target = str(run["target_url"] or "-") if run else "-"; summary = str(run["ai_summary"] or "") if run else ""
    if run is None: content = "<section class='panel'><h2>Improvement Intelligence não executado</h2><p>Nenhum estado persistido existe para esta auditoria.</p></section>"
    else:
        finding_cards = "".join(f"<article class='page-card'><div class='panel-head'><div><div class='kicker'>{escape(str(row['domain']))} · {escape(str(row['source']))}</div><h3>{escape(str(row['title']))}</h3></div><span class='badge'>{escape(str(row['severity']))}</span></div><p>{escape(str(row['observation']))}</p>{('<p><strong>Selector:</strong> <code>'+escape(str(row['selector']))+'</code></p>') if row['selector'] else ''}<div>{_impact_badges(row['impacts_json'])}</div></article>" for row in findings)
        rec_cards = []
        for row in recs:
            old, new = _html_diff(row["original_html"], row["suggested_html"]); code = f"<div class='code-compare'><div><h4>HTML original observado</h4><pre><code>{old}</code></pre></div><div><h4>HTML sugerido pela IA</h4><pre><code>{new}</code></pre></div></div>" if row["original_html"] or row["suggested_html"] else ""; text = f"<div class='notice'><strong>Texto sugerido:</strong> {escape(str(row['suggested_text']))}</div>" if row["suggested_text"] else ""
            rec_cards.append(f"<article class='page-card'><div class='panel-head'><div><div class='kicker'>{escape(str(row['domain']))} · prioridade {int(row['priority_score'])}/100</div><h3>{escape(str(row['title']))}</h3></div><span class='badge'>{escape(str(row['priority']))}</span></div><p>{escape(str(row['recommendation']))}</p><p><strong>Justificativa:</strong> {escape(str(row['rationale']))}</p><p><strong>Confiança:</strong> {float(row['confidence']):.2f} · <strong>Esforço:</strong> {escape(str(row['effort']))}</p><div>{_impact_badges(row['impacts_json'])}</div>{('<p><strong>Elemento:</strong> <code>'+escape(str(row['selector']))+'</code></p>') if row['selector'] else ''}{code}{text}<p><strong>Como validar:</strong> {escape(str(row['verification']))}</p><details><summary>Evidências usadas</summary><pre>{escape(str(row['evidence_ids_json']))}</pre></details></article>")
        usage_rows = "".join(f"<tr><td>{escape(str(row['provider']))}</td><td>{escape(str(row['model'] or '-'))}</td><td>{escape(str(row['reasoning_profile']))}</td><td>{escape(str(row['status']))}</td><td>{row['input_tokens'] if row['input_tokens'] is not None else '-'}</td><td>{row['output_tokens'] if row['output_tokens'] is not None else '-'}</td><td>{row['reasoning_tokens'] if row['reasoning_tokens'] is not None else '-'}</td><td>{row['total_tokens'] if row['total_tokens'] is not None else '-'}</td><td>{row['estimated_cost'] if row['estimated_cost'] is not None else '-'}</td><td>{escape(str(row['cost_currency'] or '-'))}</td></tr>" for row in attempts) or "<tr><td colspan='10'>Nenhuma tentativa de IA persistida para este contrato.</td></tr>"
        content = f"<section class='notice'><strong>Fronteira:</strong> esta superfície é advisory/non-scoring. Segurança é passiva e não executa exploração. Recomendações SERP não implicam causalidade de ranking. O ganho real deve ser comprovado por nova auditoria/before-after.</section><section class='panel'><div class='kicker'>Síntese</div><h2>Estudo profundo da URL</h2><p>{escape(summary or 'A IA não produziu síntese; findings determinísticos permanecem disponíveis.')}</p><div class='metric-grid'><div class='metric'><span>Status</span><strong>{escape(status)}</strong></div><div class='metric'><span>Findings</span><strong>{len(findings)}</strong></div><div class='metric'><span>Recomendações IA</span><strong>{len(recs)}</strong></div><div class='metric'><span>Provider</span><strong>{escape(str(run['provider'] or '-'))}</strong></div><div class='metric'><span>Modelo</span><strong>{escape(str(run['model'] or '-'))}</strong></div><div class='metric'><span>Esforço</span><strong>{escape(str(run['reasoning'] or '-'))}</strong></div></div></section><section class='panel'><div class='kicker'>Backlog priorizado</div><h2>O que corrigir primeiro</h2>{''.join(rec_cards) if rec_cards else '<p>Nenhuma recomendação por IA foi materializada. Consulte o estado/limitação e os findings observados.</p>'}</section><section class='panel'><div class='kicker'>Evidência determinística</div><h2>Problemas e oportunidades observados</h2>{finding_cards or '<p>Nenhum finding elegível nos domínios selecionados.</p>'}</section><section class='panel'><div class='kicker'>Consumo</div><h2>IA usada por esta análise</h2><div class='table-wrap'><table><thead><tr><th>Provider</th><th>Modelo</th><th>Esforço</th><th>Status</th><th>Input</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Custo estimado</th><th>Moeda</th></tr></thead><tbody>{usage_rows}</tbody></table></div><p class='intro'>A mesma tentativa também integra a superfície canônica Uso de IA por meio de ai_provider_attempts.</p></section>"
    html = f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Improvement Intelligence - RASAi</title><link rel='stylesheet' href='css/site.css'><style>.code-compare{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}.code-compare pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.diff-del{{background:#ffd6d6;text-decoration:line-through}}.diff-add{{background:#d8f5df}}.chip{{display:inline-block;margin:3px;padding:4px 8px;border:1px solid #ccd5df;border-radius:999px;font-size:.8rem}}</style></head><body>{nav}<main class='app-main'><header class='hero'><div class='eyebrow'>Improvement Intelligence · {CONTRACT_VERSION}</div><h1>Análise profunda e plano de melhorias</h1><p class='lead'>URL única: {escape(target)}. Evidência técnica, HTML, semântica, conteúdo, SERP, arquivos de descoberta, segurança passiva, Lighthouse e acesso por IA são correlacionados sem alterar o SARI.</p></header>{content}<footer class='footer'>{CONTRACT_VERSION} · advisory/non-scoring · human review required</footer></main></body></html>"
    path.write_text(html, encoding="utf-8", newline="\n"); report_navigation.normalize_report_navigation(report_dir); return path
