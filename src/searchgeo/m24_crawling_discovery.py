"""M24 — Crawling, Discovery & AI Access diagnostics.

This module is additive and non-scoring. It reads persisted audit evidence/artifacts,
adds deterministic technical diagnostics, optionally fetches same-origin /llms.txt,
and persists a reopenable M24 projection. It never creates RuleExecution, Finding,
ScoreContribution, Score, Coverage, Confidence or Consolidation changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import gzip
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib import robotparser
import xml.etree.ElementTree as ET

from searchgeo.acquisition import HttpClient
from searchgeo.persistence import AuditWorkspace
from searchgeo.url_utils import is_same_origin, normalize_url

M24_VERSION = "M24-CD-001"
SCORING_IMPACT = "NONE"
LLMS_PATH = "/llms.txt"
MAX_SITEMAP_BYTES = 50 * 1024 * 1024
MAX_SITEMAP_URLS = 50_000

_SEARCH_CRAWLERS = (
    "Googlebot",
    "Googlebot Smartphone",
    "Bingbot",
    "OAI-SearchBot",
)
_ASSET_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
)


@dataclass(frozen=True, slots=True)
class M24Diagnostic:
    code: str
    category: str
    severity: str
    title: str
    scope_url: str | None
    observed: dict[str, Any]
    evidence_ids: tuple[str, ...]
    remediation: str


@dataclass(frozen=True, slots=True)
class M24ExecutionResult:
    status: str
    diagnostics_count: int
    llms_state: str
    ai_enabled: bool
    ai_state: str
    external_sitemaps: tuple[str, ...]
    scoring_impact: str = SCORING_IMPACT


class _AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).casefold(): value or "" for key, value in attrs}
        tag_name = tag.casefold()
        if tag_name == "script":
            src = values.get("src", "").strip()
            if src:
                self.urls.append(src)
        elif tag_name == "link":
            rel = {item.casefold() for item in values.get("rel", "").split()}
            href = values.get("href", "").strip()
            if href and "stylesheet" in rel:
                self.urls.append(href)


def execute_m24(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    technical_ai: bool = False,
    semantic_provider: Any = None,
    http_client: HttpClient | None = None,
    allow_network: bool = True,
) -> M24ExecutionResult:
    """Execute deterministic M24 and optional evidence-bound technical AI.

    M24 is idempotent per audit. Re-running replaces only M24-owned rows/artifacts
    and does not mutate the core evaluated entities.
    """
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _initialize(connection)
        target = connection.execute(
            "SELECT * FROM audit_targets WHERE audit_id=? ORDER BY rowid LIMIT 1",
            (audit_id,),
        ).fetchone()
        if target is None:
            raise ValueError(f"audit target not found for {audit_id}")
        origin = str(target["normalized_origin"])
        target_type = str(target["target_type"])
        diagnostics: list[M24Diagnostic] = []

        robots = _robots_evidence(connection, audit_id)
        external_sitemaps = _external_sitemap_declarations(robots, origin)
        if external_sitemaps:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-ROBOTS-EXTERNAL-SITEMAP",
                    category="ROBOTS",
                    severity="INFO",
                    title="Sitemap externo declarado em robots.txt",
                    scope_url=str(robots["source"]) if robots is not None else None,
                    observed={
                        "external_sitemaps": list(external_sitemaps),
                        "acquisition_policy": "DECLARATION_PRESERVED_NOT_FETCHED",
                        "reason": "network scope / SSRF safety boundary",
                    },
                    evidence_ids=(str(robots["evidence_id"]),) if robots is not None else (),
                    remediation=(
                        "Nenhuma correção do website é inferida. A declaração é preservada como válida, "
                        "mas o auditor não expande automaticamente a coleta para outro origin."
                    ),
                )
            )

        diagnostics.extend(
            _robots_diagnostics(
                connection=connection,
                audit_id=audit_id,
                origin=origin,
                robots=robots,
                workspace=workspace,
            )
        )
        sitemap_info, sitemap_diagnostics = _sitemap_diagnostics(
            connection=connection,
            audit_id=audit_id,
            origin=origin,
            workspace=workspace,
        )
        diagnostics.extend(sitemap_diagnostics)
        diagnostics.extend(
            _cross_correlate_pages(
                connection=connection,
                audit_id=audit_id,
                origin=origin,
                robots=robots,
                sitemap_urls=frozenset(sitemap_info["page_urls"]),
                sitemap_evidence_ids=tuple(sitemap_info["evidence_ids"]),
                target_type=target_type,
            )
        )

        if allow_network:
            llms_state, llms_diagnostics = _analyze_llms(
                origin=origin,
                workspace=workspace,
                client=http_client or HttpClient(),
            )
            diagnostics.extend(llms_diagnostics)
        else:
            llms_state = "SKIPPED_SOURCE_BLOCKER"
            diagnostics.append(
                M24Diagnostic(
                    code="M24-LLMS-SKIPPED-SOURCE-BLOCKER",
                    category="AI_ACCESS",
                    severity="INFO",
                    title="llms.txt não consultado por bloqueio técnico da origem",
                    scope_url=origin,
                    observed={
                        "state": "SKIPPED_SOURCE_BLOCKER",
                        "additional_network_requests": 0,
                    },
                    evidence_ids=(),
                    remediation=(
                        "Resolver primeiro o bloqueio técnico da origem. llms.txt permanece opcional "
                        "e sem impacto em scoring."
                    ),
                )
            )

        diagnostics.append(
            M24Diagnostic(
                code="M24-DISCOVERY-INDEXNOW",
                category="DISCOVERY",
                severity="INFO",
                title="IndexNow não determinável com as evidências da auditoria",
                scope_url=origin,
                observed={
                    "state": "NOT_DETERMINABLE",
                    "reason": (
                        "IndexNow é um mecanismo de submissão/push; ausência de endpoint/key observável "
                        "não prova ausência de uso."
                    ),
                },
                evidence_ids=(),
                remediation=(
                    "Validar configuração IndexNow apenas quando houver evidência operacional explícita "
                    "(key, endpoint, logs ou configuração do CMS/CDN). Não tratar ausência de evidência como falha."
                ),
            )
        )

        _persist_diagnostics(connection, audit_id, diagnostics)

        ai_state = "DISABLED"
        if technical_ai:
            try:
                from searchgeo.m24_ai import maybe_remediate_m24

                ai_result = maybe_remediate_m24(
                    audit_id=audit_id,
                    workspace=workspace,
                    provider=semantic_provider,
                    diagnostics=tuple(diagnostics),
                )
                ai_state = ai_result.state.value
            except Exception as exc:
                ai_state = "UNAVAILABLE"
                _persist_ai_state(
                    connection,
                    audit_id=audit_id,
                    state=ai_state,
                    provider=None,
                    model=None,
                    reason=f"{type(exc).__name__}: {str(exc)[:300]}",
                    artifact_reference=None,
                )
        else:
            _persist_ai_state(
                connection,
                audit_id=audit_id,
                state="DISABLED",
                provider=None,
                model=None,
                reason="DEFAULT_OFF",
                artifact_reference=None,
            )

        status = "SUCCESS"
        high = sum(1 for item in diagnostics if item.severity == "HIGH")
        medium = sum(1 for item in diagnostics if item.severity == "MEDIUM")
        if high:
            status = "ATTENTION_REQUIRED"
        elif medium:
            status = "REVIEW_RECOMMENDED"

        with connection:
            connection.execute(
                """
                INSERT INTO m24_runs (
                    audit_id,version,status,scoring_impact,llms_state,ai_enabled,ai_state,
                    external_sitemaps,diagnostics_count,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    version=excluded.version,status=excluded.status,
                    scoring_impact=excluded.scoring_impact,llms_state=excluded.llms_state,
                    ai_enabled=excluded.ai_enabled,ai_state=excluded.ai_state,
                    external_sitemaps=excluded.external_sitemaps,
                    diagnostics_count=excluded.diagnostics_count,updated_at=excluded.updated_at
                """,
                (
                    audit_id,
                    M24_VERSION,
                    status,
                    SCORING_IMPACT,
                    llms_state,
                    1 if technical_ai else 0,
                    ai_state,
                    _dump(list(external_sitemaps)),
                    len(diagnostics),
                    _now(),
                ),
            )
        return M24ExecutionResult(
            status=status,
            diagnostics_count=len(diagnostics),
            llms_state=llms_state,
            ai_enabled=technical_ai,
            ai_state=ai_state,
            external_sitemaps=external_sitemaps,
        )
    finally:
        connection.close()


def _initialize(connection: sqlite3.Connection) -> None:
    with connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS m24_runs (
                audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                version TEXT NOT NULL,
                status TEXT NOT NULL,
                scoring_impact TEXT NOT NULL,
                llms_state TEXT NOT NULL,
                ai_enabled INTEGER NOT NULL,
                ai_state TEXT NOT NULL,
                external_sitemaps TEXT NOT NULL,
                diagnostics_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS m24_diagnostics (
                diagnostic_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                code TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                scope_url TEXT,
                observed_value TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                remediation TEXT NOT NULL,
                scoring_impact TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_m24_diagnostics_audit
                ON m24_diagnostics(audit_id,category,severity,code);

            CREATE TABLE IF NOT EXISTS m24_ai_results (
                audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                state TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                reason TEXT,
                artifact_reference TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )


def _robots_evidence(connection: sqlite3.Connection, audit_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM evidence
        WHERE audit_id=? AND evidence_type='ROBOTS_RULE'
        ORDER BY captured_at DESC,evidence_id DESC LIMIT 1
        """,
        (audit_id,),
    ).fetchone()


def _external_sitemap_declarations(
    robots: sqlite3.Row | None,
    origin: str,
) -> tuple[str, ...]:
    if robots is None:
        return ()
    observed = _json_value(robots["observed_value"])
    declared = observed.get("declared_sitemaps") if isinstance(observed, dict) else None
    if not isinstance(declared, list):
        return ()
    output: list[str] = []
    for raw in declared:
        try:
            normalized = normalize_url(str(raw))
        except ValueError:
            continue
        if not is_same_origin(normalized, origin) and normalized not in output:
            output.append(normalized)
    return tuple(output)


def _robots_diagnostics(
    *,
    connection: sqlite3.Connection,
    audit_id: str,
    origin: str,
    robots: sqlite3.Row | None,
    workspace: AuditWorkspace,
) -> list[M24Diagnostic]:
    diagnostics: list[M24Diagnostic] = []
    if robots is None:
        return [
            M24Diagnostic(
                code="M24-ROBOTS-EVIDENCE-MISSING",
                category="ROBOTS",
                severity="MEDIUM",
                title="Evidência de robots.txt não foi persistida",
                scope_url=origin,
                observed={"state": "UNKNOWN"},
                evidence_ids=(),
                remediation="Reexecutar a aquisição de robots.txt; não inferir permissões de crawler sem evidência.",
            )
        ]

    evidence_id = str(robots["evidence_id"])
    observed = _json_value(robots["observed_value"])
    state = str(observed.get("state") or "UNKNOWN") if isinstance(observed, dict) else "UNKNOWN"
    robots_url = str(robots["source"])
    if state == "ABSENT":
        return [
            M24Diagnostic(
                code="M24-ROBOTS-ABSENT",
                category="ROBOTS",
                severity="INFO",
                title="robots.txt não encontrado",
                scope_url=robots_url,
                observed={"state": state},
                evidence_ids=(evidence_id,),
                remediation=(
                    "Ausência de robots.txt não é falha por si só. Publicar somente se houver necessidade "
                    "de controles explícitos de crawling."
                ),
            )
        ]
    if state != "OBTAINED":
        return [
            M24Diagnostic(
                code=f"M24-ROBOTS-{state}",
                category="ROBOTS",
                severity="MEDIUM",
                title="robots.txt não pôde ser interpretado de forma confiável",
                scope_url=robots_url,
                observed={"state": state},
                evidence_ids=(evidence_id,),
                remediation="Resolver a falha de aquisição/interpretação antes de concluir sobre acesso de crawlers.",
            )
        ]

    crawler_access = observed.get("crawler_access") if isinstance(observed, dict) else None
    if isinstance(crawler_access, dict):
        for crawler in (*_SEARCH_CRAWLERS, "GPTBot"):
            blocked_urls: list[str] = []
            unresolved_urls: list[str] = []
            for url, per_crawler in crawler_access.items():
                if not isinstance(per_crawler, dict):
                    continue
                allowed = per_crawler.get(crawler)
                if allowed is False:
                    blocked_urls.append(str(url))
                elif allowed is None:
                    unresolved_urls.append(str(url))
            if blocked_urls:
                if crawler == "GPTBot":
                    diagnostics.append(
                        M24Diagnostic(
                            code="M24-ROBOTS-GPTBOT-BLOCKED",
                            category="AI_ACCESS",
                            severity="INFO",
                            title="GPTBot bloqueado em URLs auditadas",
                            scope_url=robots_url,
                            observed={"crawler": crawler, "blocked_urls": blocked_urls},
                            evidence_ids=(evidence_id,),
                            remediation=(
                                "Nenhuma penalidade de Search é aplicada. GPTBot está ligado a potencial uso "
                                "para treinamento; manter ou alterar o bloqueio é decisão de política do publisher."
                            ),
                        )
                    )
                else:
                    diagnostics.append(
                        M24Diagnostic(
                            code=f"M24-ROBOTS-{_code(crawler)}-BLOCKED",
                            category="ROBOTS" if crawler != "OAI-SearchBot" else "AI_ACCESS",
                            severity="HIGH",
                            title=f"{crawler} bloqueado em URLs auditadas",
                            scope_url=robots_url,
                            observed={"crawler": crawler, "blocked_urls": blocked_urls},
                            evidence_ids=(evidence_id,),
                            remediation=(
                                "Validar se o bloqueio é intencional. Se as URLs devem ser descobertas nesse "
                                "mecanismo, ajustar a regra específica sem abrir áreas privadas ou administrativas."
                            ),
                        )
                    )
            if unresolved_urls:
                diagnostics.append(
                    M24Diagnostic(
                        code=f"M24-ROBOTS-{_code(crawler)}-UNRESOLVED",
                        category="ROBOTS",
                        severity="MEDIUM",
                        title=f"Acesso de {crawler} não resolvido",
                        scope_url=robots_url,
                        observed={"crawler": crawler, "unresolved_urls": unresolved_urls},
                        evidence_ids=(evidence_id,),
                        remediation="Revalidar robots.txt antes de afirmar acesso permitido/bloqueado.",
                    )
                )

    parser = _robots_parser_from_artifact(workspace, robots)
    if parser is not None:
        audited_urls = [
            str(row["normalized_url"])
            for row in connection.execute(
                "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY normalized_url",
                (audit_id,),
            )
        ]
        google_extended_blocked = [
            url for url in audited_urls if not parser.can_fetch("Google-Extended", url)
        ]
        if google_extended_blocked:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-ROBOTS-GOOGLE-EXTENDED-BLOCKED",
                    category="AI_ACCESS",
                    severity="INFO",
                    title="Google-Extended bloqueado em URLs auditadas",
                    scope_url=robots_url,
                    observed={
                        "crawler_token": "Google-Extended",
                        "blocked_urls": google_extended_blocked,
                        "search_ranking_impact": "NONE",
                    },
                    evidence_ids=(evidence_id,),
                    remediation=(
                        "Google-Extended é um token de controle de usos específicos do Google/Gemini e não "
                        "deve ser tratado como requisito de inclusão/ranking no Google Search. A decisão é de política."
                    ),
                )
            )
        diagnostics.extend(
            _blocked_render_assets(
                connection=connection,
                audit_id=audit_id,
                origin=origin,
                parser=parser,
                robots_evidence_id=evidence_id,
                workspace=workspace,
            )
        )
    return diagnostics


def _robots_parser_from_artifact(
    workspace: AuditWorkspace,
    robots: sqlite3.Row,
) -> robotparser.RobotFileParser | None:
    reference = robots["artifact_reference"]
    if not reference:
        return None
    path = workspace.root / str(reference)
    if not path.is_file():
        return None
    parser = robotparser.RobotFileParser()
    parser.set_url(str(robots["source"]))
    parser.parse(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return parser


def _blocked_render_assets(
    *,
    connection: sqlite3.Connection,
    audit_id: str,
    origin: str,
    parser: robotparser.RobotFileParser,
    robots_evidence_id: str,
    workspace: AuditWorkspace,
) -> list[M24Diagnostic]:
    blocked: dict[str, set[str]] = {}
    rows = connection.execute(
        """
        SELECT ps.rendered_artifact_ref,p.normalized_url
        FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
        WHERE p.audit_id=? AND ps.rendered_artifact_ref IS NOT NULL
        ORDER BY p.normalized_url,ps.device
        """,
        (audit_id,),
    ).fetchall()
    for row in rows:
        path = workspace.root / str(row["rendered_artifact_ref"])
        if not path.is_file():
            continue
        parser_html = _AssetParser()
        try:
            parser_html.feed(path.read_text(encoding="utf-8", errors="replace"))
            parser_html.close()
        except (AssertionError, ValueError):
            continue
        page_url = str(row["normalized_url"])
        for raw in parser_html.urls:
            try:
                asset = normalize_url(raw, base_url=page_url)
            except ValueError:
                continue
            if not is_same_origin(asset, origin):
                continue
            if not asset.casefold().split("?", 1)[0].endswith(_ASSET_SUFFIXES):
                continue
            if not parser.can_fetch("Googlebot", asset):
                blocked.setdefault(asset, set()).add(page_url)
    if not blocked:
        return []
    return [
        M24Diagnostic(
            code="M24-ROBOTS-RENDER-ASSET-BLOCKED",
            category="ROBOTS",
            severity="HIGH",
            title="CSS/JavaScript same-origin bloqueado para Googlebot",
            scope_url=origin,
            observed={
                "blocked_assets": [
                    {"url": asset, "referenced_by": sorted(pages)}
                    for asset, pages in sorted(blocked.items())
                ]
            },
            evidence_ids=(robots_evidence_id,),
            remediation=(
                "Liberar somente os recursos necessários ao rendering/indexação quando o bloqueio não for "
                "intencional. Não remover controles de áreas privadas."
            ),
        )
    ]


def _sitemap_diagnostics(
    *,
    connection: sqlite3.Connection,
    audit_id: str,
    origin: str,
    workspace: AuditWorkspace,
) -> tuple[dict[str, Any], list[M24Diagnostic]]:
    rows = connection.execute(
        """
        SELECT * FROM evidence
        WHERE audit_id=? AND evidence_type='SITEMAP_ENTRY'
        ORDER BY captured_at,evidence_id
        """,
        (audit_id,),
    ).fetchall()
    diagnostics: list[M24Diagnostic] = []
    page_urls: list[str] = []
    evidence_ids: list[str] = []
    source_count = 0
    for row in rows:
        observed = _json_value(row["observed_value"])
        if not isinstance(observed, dict) or "state" not in observed:
            continue
        source_count += 1
        evidence_id = str(row["evidence_id"])
        evidence_ids.append(evidence_id)
        state = str(observed.get("state") or "UNKNOWN")
        source_url = str(row["source"])
        artifact = _analyze_sitemap_artifact(workspace, row, source_url, origin)
        if state != "OBTAINED":
            severity = "INFO" if state == "ABSENT" else "HIGH" if state == "INVALID" else "MEDIUM"
            diagnostics.append(
                M24Diagnostic(
                    code=f"M24-SITEMAP-{state}",
                    category="SITEMAP",
                    severity=severity,
                    title=f"Sitemap/feed em estado {state}",
                    scope_url=source_url,
                    observed={"state": state, "error": observed.get("error")},
                    evidence_ids=(evidence_id,),
                    remediation=(
                        "Corrigir o recurso quando ele for publicado/intencional. Ausência no caminho convencional "
                        "não é falha se outro sitemap válido for usado."
                    ),
                )
            )
            continue
        if artifact["format"] != "UNKNOWN":
            diagnostics.append(
                M24Diagnostic(
                    code=f"M24-SITEMAP-FORMAT-{artifact['format']}",
                    category="SITEMAP",
                    severity="INFO",
                    title=f"Formato de descoberta identificado: {artifact['format']}",
                    scope_url=source_url,
                    observed={
                        "format": artifact["format"],
                        "url_count": len(artifact["page_urls"]),
                        "child_count": len(artifact["child_sitemaps"]),
                        "image_elements": artifact["image_elements"],
                        "video_elements": artifact["video_elements"],
                        "news_elements": artifact["news_elements"],
                        "hreflang_links": artifact["hreflang_links"],
                    },
                    evidence_ids=(evidence_id,),
                    remediation="Informativo; nenhuma alteração é necessária apenas pelo formato.",
                )
            )
        page_urls.extend(item for item in artifact["page_urls"] if item not in page_urls)

        if artifact["duplicate_urls"]:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-SITEMAP-DUPLICATE-URL",
                    category="SITEMAP",
                    severity="LOW",
                    title="URLs duplicadas no sitemap/feed",
                    scope_url=source_url,
                    observed={"duplicate_urls": artifact["duplicate_urls"][:100]},
                    evidence_ids=(evidence_id,),
                    remediation="Remover entradas duplicadas para reduzir ruído operacional e facilitar manutenção.",
                )
            )
        if artifact["invalid_lastmod"]:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-SITEMAP-LASTMOD-INVALID",
                    category="SITEMAP",
                    severity="MEDIUM",
                    title="Valores lastmod inválidos",
                    scope_url=source_url,
                    observed={"invalid_lastmod": artifact["invalid_lastmod"][:100]},
                    evidence_ids=(evidence_id,),
                    remediation=(
                        "Emitir lastmod somente quando houver data válida da última alteração significativa da página."
                    ),
                )
            )
        if artifact["future_lastmod"]:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-SITEMAP-LASTMOD-FUTURE",
                    category="SITEMAP",
                    severity="MEDIUM",
                    title="lastmod no futuro",
                    scope_url=source_url,
                    observed={"future_lastmod": artifact["future_lastmod"][:100]},
                    evidence_ids=(evidence_id,),
                    remediation="Corrigir datas futuras e usar somente timestamps sustentados pelo processo de publicação.",
                )
            )
        if artifact["priority_count"] or artifact["changefreq_count"]:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-SITEMAP-IGNORED-HINTS",
                    category="SITEMAP",
                    severity="INFO",
                    title="priority/changefreq presentes como hints não utilizados pelo Google",
                    scope_url=source_url,
                    observed={
                        "priority_elements": artifact["priority_count"],
                        "changefreq_elements": artifact["changefreq_count"],
                    },
                    evidence_ids=(evidence_id,),
                    remediation=(
                        "Não priorizar otimização desses campos para Google Search. Preserve-os apenas se houver "
                        "consumidor interno/externo conhecido."
                    ),
                )
            )

    if source_count == 0:
        diagnostics.append(
            M24Diagnostic(
                code="M24-SITEMAP-NO-EVIDENCE",
                category="SITEMAP",
                severity="INFO",
                title="Nenhum sitemap/feed adquirido no universo da auditoria",
                scope_url=origin,
                observed={"state": "NO_ACQUIRED_SITEMAP"},
                evidence_ids=(),
                remediation=(
                    "Sitemap é recomendado para descoberta em sites maiores/complexos, mas ausência isolada "
                    "não prova impossibilidade de crawling."
                ),
            )
        )
    return {"page_urls": page_urls, "evidence_ids": evidence_ids}, diagnostics


def _analyze_sitemap_artifact(
    workspace: AuditWorkspace,
    row: sqlite3.Row,
    source_url: str,
    origin: str,
) -> dict[str, Any]:
    result = {
        "format": "UNKNOWN",
        "page_urls": [],
        "child_sitemaps": [],
        "duplicate_urls": [],
        "invalid_lastmod": [],
        "future_lastmod": [],
        "priority_count": 0,
        "changefreq_count": 0,
        "image_elements": 0,
        "video_elements": 0,
        "news_elements": 0,
        "hreflang_links": 0,
    }
    reference = row["artifact_reference"]
    if not reference:
        return result
    path = workspace.root / str(reference)
    if not path.is_file():
        return result
    payload = path.read_bytes()
    if source_url.casefold().endswith(".gz"):
        try:
            payload = gzip.GzipFile(fileobj=BytesIO(payload)).read(MAX_SITEMAP_BYTES + 1)
        except OSError:
            return result
    if len(payload) > MAX_SITEMAP_BYTES:
        return result
    stripped = payload.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not stripped.startswith(b"<"):
        result["format"] = "TEXT"
        seen: set[str] = set()
        for line in payload.decode("utf-8-sig", errors="replace").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                url = normalize_url(raw, base_url=source_url)
            except ValueError:
                continue
            if not is_same_origin(url, origin):
                continue
            if url in seen and url not in result["duplicate_urls"]:
                result["duplicate_urls"].append(url)
            seen.add(url)
            if url not in result["page_urls"]:
                result["page_urls"].append(url)
        return result
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return result
    root_name = _local_name(root.tag)
    if root_name == "urlset":
        result["format"] = "XML_URLSET"
        raw_locs: list[str] = []
        for url_node in list(root):
            if _local_name(url_node.tag) != "url":
                continue
            loc = ""
            for child in list(url_node):
                local = _local_name(child.tag)
                if local == "loc":
                    loc = (child.text or "").strip()
                elif local == "lastmod":
                    _record_lastmod(result, loc, (child.text or "").strip())
                elif local == "priority":
                    result["priority_count"] += 1
                elif local == "changefreq":
                    result["changefreq_count"] += 1
                else:
                    namespace = _namespace(child.tag)
                    if "image" in namespace:
                        result["image_elements"] += 1
                    if "video" in namespace:
                        result["video_elements"] += 1
                    if "news" in namespace:
                        result["news_elements"] += 1
                    if local == "link" and (child.attrib.get("hreflang") or "").strip():
                        result["hreflang_links"] += 1
            if loc:
                raw_locs.append(loc)
                _append_same_origin(result["page_urls"], loc, source_url, origin)
        normalized_raw = []
        for raw in raw_locs:
            try:
                norm = normalize_url(raw, base_url=source_url)
            except ValueError:
                continue
            if norm in normalized_raw and norm not in result["duplicate_urls"]:
                result["duplicate_urls"].append(norm)
            normalized_raw.append(norm)
    elif root_name == "sitemapindex":
        result["format"] = "XML_INDEX"
        for sitemap_node in list(root):
            if _local_name(sitemap_node.tag) != "sitemap":
                continue
            loc = next(
                (
                    (child.text or "").strip()
                    for child in list(sitemap_node)
                    if _local_name(child.tag) == "loc" and (child.text or "").strip()
                ),
                "",
            )
            _append_same_origin(result["child_sitemaps"], loc, source_url, origin)
    elif root_name == "rss":
        result["format"] = "RSS_2"
        for node in root.iter():
            if _local_name(node.tag) != "item":
                continue
            link = next(
                (
                    (child.text or "").strip()
                    for child in list(node)
                    if _local_name(child.tag) == "link" and (child.text or "").strip()
                ),
                "",
            )
            _append_same_origin(result["page_urls"], link, source_url, origin)
    elif root_name == "feed":
        result["format"] = "ATOM_1"
        for node in root.iter():
            if _local_name(node.tag) != "entry":
                continue
            for child in list(node):
                if _local_name(child.tag) != "link":
                    continue
                rel = (child.attrib.get("rel") or "alternate").casefold()
                href = (child.attrib.get("href") or "").strip()
                if rel in {"", "alternate"} and href:
                    _append_same_origin(result["page_urls"], href, source_url, origin)
                    break
    return result


def _record_lastmod(result: dict[str, Any], loc: str, value: str) -> None:
    if not value:
        result["invalid_lastmod"].append({"url": loc or None, "lastmod": value})
        return
    normalized = value.replace("Z", "+00:00")
    try:
        if len(value) == 10:
            instant = datetime.fromisoformat(value + "T00:00:00+00:00")
        else:
            instant = datetime.fromisoformat(normalized)
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
    except ValueError:
        result["invalid_lastmod"].append({"url": loc or None, "lastmod": value})
        return
    if instant.astimezone(timezone.utc) > datetime.now(timezone.utc):
        result["future_lastmod"].append({"url": loc or None, "lastmod": value})


def _cross_correlate_pages(
    *,
    connection: sqlite3.Connection,
    audit_id: str,
    origin: str,
    robots: sqlite3.Row | None,
    sitemap_urls: frozenset[str],
    sitemap_evidence_ids: tuple[str, ...],
    target_type: str,
) -> list[M24Diagnostic]:
    diagnostics: list[M24Diagnostic] = []
    robots_observed = _json_value(robots["observed_value"]) if robots is not None else {}
    crawler_access = robots_observed.get("crawler_access") if isinstance(robots_observed, dict) else {}
    pages = connection.execute(
        """
        SELECT p.page_id,p.normalized_url,
               (SELECT e.observed_value FROM evidence e
                WHERE e.audit_id=p.audit_id AND e.page_id=p.page_id
                  AND e.evidence_type='HTTP_RESPONSE'
                ORDER BY e.captured_at DESC LIMIT 1) AS http_observed
        FROM pages p WHERE p.audit_id=? ORDER BY p.normalized_url
        """,
        (audit_id,),
    ).fetchall()
    audited_urls = [str(row["normalized_url"]) for row in pages]

    if sitemap_urls:
        missing = [url for url in audited_urls if url not in sitemap_urls]
        if missing:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-DISCOVERY-AUDITED-NOT-IN-SITEMAP",
                    category="DISCOVERY",
                    severity="LOW",
                    title="URLs auditadas não presentes nos sitemaps adquiridos",
                    scope_url=origin,
                    observed={
                        "sample_scope_only": True,
                        "audited_url_count": len(audited_urls),
                        "missing_count": len(missing),
                        "urls": missing[:200],
                        "target_type": target_type,
                    },
                    evidence_ids=sitemap_evidence_ids,
                    remediation=(
                        "Revisar somente URLs canônicas/indexáveis que deveriam ser descobertas por sitemap. "
                        "O resultado é limitado ao universo auditado e não representa cobertura completa do domínio."
                    ),
                )
            )

    for row in pages:
        url = str(row["normalized_url"])
        http = _json_value(row["http_observed"]) if row["http_observed"] else {}
        status = http.get("status") if isinstance(http, dict) else None
        if url in sitemap_urls and status is not None:
            try:
                status_int = int(status)
            except (TypeError, ValueError):
                status_int = None
            if status_int is not None and not 200 <= status_int <= 299:
                diagnostics.append(
                    M24Diagnostic(
                        code="M24-SITEMAP-URL-NON-2XX",
                        category="SITEMAP",
                        severity="HIGH",
                        title="URL de sitemap respondeu fora de 2xx",
                        scope_url=url,
                        observed={"http_status": status_int},
                        evidence_ids=sitemap_evidence_ids,
                        remediation="Remover URL obsoleta do sitemap ou corrigir seu destino HTTP final.",
                    )
                )
        per_url = crawler_access.get(url) if isinstance(crawler_access, dict) else None
        if url in sitemap_urls and isinstance(per_url, dict):
            blocked = [
                crawler for crawler in _SEARCH_CRAWLERS
                if per_url.get(crawler) is False
            ]
            if blocked:
                combined_evidence = list(sitemap_evidence_ids)
                if robots is not None:
                    combined_evidence.append(str(robots["evidence_id"]))
                diagnostics.append(
                    M24Diagnostic(
                        code="M24-SITEMAP-ROBOTS-CONFLICT",
                        category="DISCOVERY",
                        severity="HIGH",
                        title="URL listada em sitemap está bloqueada para crawler de Search",
                        scope_url=url,
                        observed={"blocked_crawlers": blocked},
                        evidence_ids=tuple(dict.fromkeys(combined_evidence)),
                        remediation=(
                            "Alinhar intenção: se a URL deve ser descoberta, evitar publicá-la no sitemap enquanto "
                            "o mesmo crawler é explicitamente bloqueado."
                        ),
                    )
                )

    snapshots = connection.execute(
        """
        SELECT ps.*,p.normalized_url
        FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
        WHERE p.audit_id=? ORDER BY p.normalized_url,ps.device
        """,
        (audit_id,),
    ).fetchall()
    by_url: dict[str, list[sqlite3.Row]] = {}
    for snapshot in snapshots:
        by_url.setdefault(str(snapshot["normalized_url"]), []).append(snapshot)
    for url in sorted(sitemap_urls.intersection(by_url)):
        rows = by_url[url]
        noindex_devices = [
            str(item["device"])
            for item in rows
            if _contains_noindex(str(item["meta_robots"] or ""))
        ]
        if noindex_devices:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-SITEMAP-NOINDEX-CONFLICT",
                    category="DISCOVERY",
                    severity="HIGH",
                    title="URL de sitemap possui noindex observado",
                    scope_url=url,
                    observed={"devices": noindex_devices},
                    evidence_ids=sitemap_evidence_ids,
                    remediation=(
                        "Se a URL deve permanecer noindex, removê-la do sitemap. Se deve ser indexável, revisar "
                        "a diretiva somente após validar a intenção de negócio."
                    ),
                )
            )
        canonical_targets = {
            str(item["canonical"]).strip()
            for item in rows
            if item["canonical"] and str(item["canonical"]).strip()
        }
        normalized_targets: set[str] = set()
        for candidate in canonical_targets:
            try:
                normalized_targets.add(normalize_url(candidate, base_url=url))
            except ValueError:
                continue
        conflicting = sorted(target for target in normalized_targets if target != url)
        if conflicting:
            diagnostics.append(
                M24Diagnostic(
                    code="M24-SITEMAP-CANONICAL-CONFLICT",
                    category="DISCOVERY",
                    severity="MEDIUM",
                    title="URL de sitemap aponta canonical para outra URL",
                    scope_url=url,
                    observed={"canonical_targets": conflicting},
                    evidence_ids=sitemap_evidence_ids,
                    remediation=(
                        "Preferir no sitemap as URLs canônicas realmente desejadas. Não trocar canonical "
                        "automaticamente sem evidência da URL preferencial."
                    ),
                )
            )
    return diagnostics


def _analyze_llms(
    *,
    origin: str,
    workspace: AuditWorkspace,
    client: HttpClient,
) -> tuple[str, list[M24Diagnostic]]:
    url = normalize_url(LLMS_PATH, base_url=f"{origin}/")
    acquisition = client.acquire(url)
    evidence: list[M24Diagnostic] = []
    if acquisition.network_error is not None:
        return "UNAVAILABLE", [
            M24Diagnostic(
                code="M24-LLMS-UNAVAILABLE",
                category="AI_ACCESS",
                severity="INFO",
                title="llms.txt não pôde ser adquirido",
                scope_url=url,
                observed={
                    "state": "UNAVAILABLE",
                    "network_error": acquisition.network_error.kind.value,
                },
                evidence_ids=(),
                remediation=(
                    "Nenhuma correção obrigatória. llms.txt é uma proposta comunitária experimental, "
                    "não requisito de Search/GEO."
                ),
            )
        ]
    if acquisition.status in {404, 410}:
        return "ABSENT", [
            M24Diagnostic(
                code="M24-LLMS-ABSENT",
                category="AI_ACCESS",
                severity="INFO",
                title="llms.txt não encontrado",
                scope_url=url,
                observed={"state": "ABSENT", "http_status": acquisition.status},
                evidence_ids=(),
                remediation=(
                    "Nenhuma ação obrigatória. A ausência não reduz score/readiness; o arquivo não é web standard."
                ),
            )
        ]
    if acquisition.status is None or not 200 <= acquisition.status <= 299:
        return "UNAVAILABLE", [
            M24Diagnostic(
                code="M24-LLMS-HTTP-UNAVAILABLE",
                category="AI_ACCESS",
                severity="INFO",
                title="llms.txt respondeu fora de 2xx",
                scope_url=url,
                observed={"state": "UNAVAILABLE", "http_status": acquisition.status},
                evidence_ids=(),
                remediation="Tratar apenas se a organização optou explicitamente por manter llms.txt.",
            )
        ]

    artifact_dir = workspace.artifacts / "m24"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact = artifact_dir / "llms.txt"
    artifact.write_bytes(acquisition.body)
    text = acquisition.body.decode("utf-8", errors="replace")
    lines = [line.rstrip() for line in text.splitlines()]
    first_content = next((line.strip() for line in lines if line.strip()), "")
    links = re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", text)
    same_origin_links = []
    external_links = []
    for raw in links:
        try:
            normalized = normalize_url(raw)
        except ValueError:
            continue
        if is_same_origin(normalized, origin):
            same_origin_links.append(normalized)
        else:
            external_links.append(normalized)
    evidence.append(
        M24Diagnostic(
            code="M24-LLMS-PRESENT",
            category="AI_ACCESS",
            severity="INFO",
            title="llms.txt presente — proposta comunitária experimental",
            scope_url=url,
            observed={
                "state": "PRESENT",
                "artifact_reference": artifact.relative_to(workspace.root).as_posix(),
                "bytes": len(acquisition.body),
                "same_origin_links": same_origin_links[:100],
                "external_links": external_links[:100],
                "standard_status": "COMMUNITY_PROPOSAL_NOT_WEB_STANDARD",
            },
            evidence_ids=(),
            remediation=(
                "Manter somente se houver objetivo editorial/operacional explícito. Não usar como substituto "
                "de robots.txt, sitemap, HTML semântico ou conteúdo acessível."
            ),
        )
    )
    if not first_content.startswith("# "):
        evidence.append(
            M24Diagnostic(
                code="M24-LLMS-H1-MISSING",
                category="AI_ACCESS",
                severity="LOW",
                title="llms.txt presente sem H1 inicial da proposta",
                scope_url=url,
                observed={"first_content_line": first_content[:300]},
                evidence_ids=(),
                remediation=(
                    "Se a organização adota llms.txt, alinhar a estrutura à proposta comunitária vigente. "
                    "Isso continua sem impacto em scoring."
                ),
            )
        )
    return "PRESENT", evidence


def _persist_diagnostics(
    connection: sqlite3.Connection,
    audit_id: str,
    diagnostics: list[M24Diagnostic],
) -> None:
    with connection:
        connection.execute("DELETE FROM m24_diagnostics WHERE audit_id=?", (audit_id,))
        for index, item in enumerate(diagnostics, 1):
            diagnostic_id = f"M24D-{index:05d}-{audit_id[-8:]}"
            connection.execute(
                """
                INSERT INTO m24_diagnostics (
                    diagnostic_id,audit_id,code,category,severity,title,scope_url,
                    observed_value,evidence_ids,remediation,scoring_impact,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    diagnostic_id,
                    audit_id,
                    item.code,
                    item.category,
                    item.severity,
                    item.title,
                    item.scope_url,
                    _dump(item.observed),
                    _dump(list(item.evidence_ids)),
                    item.remediation,
                    SCORING_IMPACT,
                    _now(),
                ),
            )


def persist_ai_result(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    state: str,
    provider: str | None,
    model: str | None,
    reason: str | None,
    artifact_reference: str | None,
) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        _initialize(connection)
        _persist_ai_state(
            connection,
            audit_id=audit_id,
            state=state,
            provider=provider,
            model=model,
            reason=reason,
            artifact_reference=artifact_reference,
        )
    finally:
        connection.close()


def _persist_ai_state(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    state: str,
    provider: str | None,
    model: str | None,
    reason: str | None,
    artifact_reference: str | None,
) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO m24_ai_results (
                audit_id,state,provider,model,reason,artifact_reference,updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(audit_id) DO UPDATE SET
                state=excluded.state,provider=excluded.provider,model=excluded.model,
                reason=excluded.reason,artifact_reference=excluded.artifact_reference,
                updated_at=excluded.updated_at
            """,
            (
                audit_id,
                state,
                provider,
                model,
                reason,
                artifact_reference,
                _now(),
            ),
        )


def _contains_noindex(value: str) -> bool:
    tokens = {
        token.strip().casefold()
        for token in value.replace(";", ",").split(",")
        if token.strip()
    }
    return any(token == "noindex" or token.endswith(": noindex") for token in tokens)


def _append_same_origin(values: list[str], raw: str, base_url: str, origin: str) -> None:
    if not raw:
        return
    try:
        normalized = normalize_url(raw, base_url=base_url)
    except ValueError:
        return
    if is_same_origin(normalized, origin) and normalized not in values:
        values.append(normalized)


def _namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0].casefold()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _json_value(raw: Any) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")
