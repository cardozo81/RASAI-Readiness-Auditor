"""Evidence-bound diagnostics that do not alter SARI/SCORE-GEO.

The analyzers use already persisted HTML/content/structured-data artifacts plus
optional observed sidecar data. Findings are advisory diagnostics, not new SARI
rules or Google/Bing scores.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

PRODUCT_DOC = "https://developers.google.com/search/docs/appearance/structured-data/product-snippet"
BREADCRUMB_DOC = "https://developers.google.com/search/docs/appearance/structured-data/breadcrumb"
ORGANIZATION_DOC = "https://developers.google.com/search/docs/appearance/structured-data/organization"
HREFLANG_DOC = "https://developers.google.com/search/docs/specialty/international/localized-versions"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    domain: str
    severity: str
    status: str
    title: str
    detail: str
    url: str | None = None
    device: str | None = None
    selector: str | None = None
    evidence: dict[str, Any] | None = None
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticBundle:
    audit_id: str
    generated_at: str
    diagnostics: tuple[Diagnostic, ...]
    template_clusters: tuple[dict[str, Any], ...]
    indexability_matrix: tuple[dict[str, Any], ...]
    query_intent_alignment: tuple[dict[str, Any], ...]
    cannibalization_candidates: tuple[dict[str, Any], ...]


class _HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.alternates: list[dict[str, str]] = []
        self.sections: list[tuple[int, str]] = []
        self.table_count = 0
        self.tables_without_th = 0
        self._in_table = False
        self._table_has_th = False
        self._heading_level: int | None = None
        self._heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        values = {key.casefold(): (value or "") for key, value in attrs}
        if name == "head":
            self.in_head = True
        elif name == "link" and self.in_head:
            rel = {part.casefold() for part in values.get("rel", "").split()}
            if "alternate" in rel and values.get("hreflang"):
                self.alternates.append({"hreflang": values.get("hreflang", ""), "href": values.get("href", "")})
        elif re.fullmatch(r"h[1-6]", name):
            self._heading_level = int(name[1])
            self._heading_text = []
        elif name == "table":
            self._in_table = True
            self._table_has_th = False
            self.table_count += 1
        elif name == "th" and self._in_table:
            self._table_has_th = True

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name == "head":
            self.in_head = False
        elif self._heading_level is not None and name == f"h{self._heading_level}":
            text = " ".join("".join(self._heading_text).split())
            if text:
                self.sections.append((self._heading_level, text))
            self._heading_level = None
            self._heading_text = []
        elif name == "table" and self._in_table:
            if not self._table_has_th:
                self.tables_without_th += 1
            self._in_table = False
            self._table_has_th = False

    def handle_data(self, data: str) -> None:
        if self._heading_level is not None:
            self._heading_text.append(data)


def analyze_workspace(audit_workspace: str | Path) -> DiagnosticBundle:
    workspace = Path(audit_workspace)
    connection = _ro(workspace / "audit.db")
    try:
        audit = connection.execute("SELECT audit_id FROM audits ORDER BY rowid LIMIT 1").fetchone()
        if audit is None:
            raise ValueError("audit metadata unavailable")
        audit_id = str(audit[0])
        analysis_date = _analysis_date(connection, audit_id)
        pages = {str(row[0]): str(row[1]) for row in connection.execute("SELECT page_id,normalized_url FROM pages WHERE audit_id=?", (audit_id,))}
        snapshots = _latest_snapshots(connection, audit_id)
        diagnostics: list[Diagnostic] = []
        structured_entities: list[dict[str, Any]] = []
        alternate_sets: dict[tuple[str, str], list[dict[str, str]]] = {}

        for row in snapshots:
            page_id = str(row["page_id"])
            url = pages.get(page_id)
            if not url:
                continue
            device = str(row["device"]).upper()
            structured = _load_json_artifact(workspace, row["structured_data_ref"])
            entities = _structured_entities(structured)
            structured_entities.extend({"url": url, "device": device, "entity": entity} for entity in entities)
            diagnostics.extend(_structured_diagnostics(url, device, entities))
            diagnostics.extend(_freshness_diagnostics(url, device, entities, analysis_date))

            html = _load_text_artifact(workspace, row["rendered_artifact_ref"] or row["raw_artifact_ref"])
            if html:
                parser = _HeadParser()
                try:
                    parser.feed(html)
                except Exception:
                    parser = _HeadParser()
                alternate_sets[(url, device)] = parser.alternates
                diagnostics.extend(_retrieval_diagnostics(url, device, parser, workspace, row["main_content_ref"]))

        diagnostics.extend(_hreflang_diagnostics(alternate_sets))
        diagnostics.extend(_entity_consistency_diagnostics(structured_entities))
        clusters = _template_clusters(connection, audit_id, pages)
        matrix = _indexability_matrix(workspace, pages, snapshots)
        alignment, cannibalization = _query_intent(connection, workspace, audit_id, pages)
        return DiagnosticBundle(
            audit_id=audit_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            diagnostics=tuple(diagnostics),
            template_clusters=tuple(clusters),
            indexability_matrix=tuple(matrix),
            query_intent_alignment=tuple(alignment),
            cannibalization_candidates=tuple(cannibalization),
        )
    finally:
        connection.close()


def _structured_diagnostics(url: str, device: str, entities: list[dict[str, Any]]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for entity in entities:
        types = _types(entity.get("@type"))
        if "Product" in types:
            missing: list[str] = []
            if not _text(entity.get("name")):
                missing.append("name")
            if not any(entity.get(key) not in (None, "", [], {}) for key in ("review", "aggregateRating", "offers")):
                missing.append("one of review / aggregateRating / offers")
            out.append(Diagnostic(
                code="SD-PRODUCT-DOC", domain="STRUCTURED_DATA_ELIGIBILITY",
                severity="HIGH" if missing else "INFO",
                status="INCOMPLETE" if missing else "COMPLETE_FOR_TOP_LEVEL_REQUIREMENTS",
                title="Product structured-data documentation completeness",
                detail=("Missing documented Product snippet requirement(s): " + ", ".join(missing)) if missing else "Top-level Product snippet requirements checked by this analyzer are present.",
                url=url, device=device, evidence={"types": sorted(types), "missing": missing}, reference=PRODUCT_DOC,
            ))
        if "BreadcrumbList" in types:
            items = entity.get("itemListElement")
            count = len(items) if isinstance(items, list) else 0
            complete = count >= 2 and all(isinstance(item, dict) and item.get("position") is not None and _text(item.get("name")) for item in (items or []))
            out.append(Diagnostic(
                code="SD-BREADCRUMB-DOC", domain="STRUCTURED_DATA_ELIGIBILITY",
                severity="MEDIUM" if not complete else "INFO",
                status="INCOMPLETE" if not complete else "COMPLETE_FOR_TOP_LEVEL_REQUIREMENTS",
                title="Breadcrumb structured-data documentation completeness",
                detail="BreadcrumbList requires itemListElement with at least two ordered ListItem entries with required fields." if not complete else "BreadcrumbList top-level documented requirements checked by this analyzer are present.",
                url=url, device=device, evidence={"list_items": count}, reference=BREADCRUMB_DOC,
            ))
        if _organization_type(types):
            present = [key for key in ("name", "alternateName", "url", "logo", "sameAs", "address", "telephone") if entity.get(key) not in (None, "", [], {})]
            out.append(Diagnostic(
                code="SD-ORGANIZATION-COMPLETENESS", domain="ENTITY_CONSISTENCY", severity="INFO", status="ADVISORY",
                title="Organization structured-data completeness",
                detail="Google documents no required Organization properties; this is a completeness observation only.",
                url=url, device=device, evidence={"observed_recommended_identity_fields": present}, reference=ORGANIZATION_DOC,
            ))
    return out


def _freshness_diagnostics(
    url: str,
    device: str,
    entities: list[dict[str, Any]],
    analysis_date: date | None,
) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for entity in entities:
        published = _parse_date(entity.get("datePublished"))
        modified = _parse_date(entity.get("dateModified"))
        if published and modified and modified < published:
            out.append(Diagnostic(
                code="FRESHNESS-DATE-CONFLICT", domain="FRESHNESS_EVIDENCE", severity="MEDIUM", status="CONFLICT",
                title="dateModified predates datePublished",
                detail=f"datePublished={published.isoformat()} and dateModified={modified.isoformat()} are chronologically inconsistent.",
                url=url, device=device, evidence={"datePublished": published.isoformat(), "dateModified": modified.isoformat()},
            ))
        if analysis_date is None:
            continue
        for label, parsed in (("datePublished", published), ("dateModified", modified)):
            if parsed and parsed > analysis_date:
                out.append(Diagnostic(
                    code="FRESHNESS-FUTURE-DATE", domain="FRESHNESS_EVIDENCE", severity="MEDIUM", status="CONFLICT",
                    title=f"{label} is in the future",
                    detail=f"{label}={parsed.isoformat()} is later than persisted audit analysis date {analysis_date.isoformat()}.",
                    url=url, device=device,
                    evidence={label: parsed.isoformat(), "analysis_date": analysis_date.isoformat(), "analysis_date_source": "AUDIT_PERSISTED_TIME"},
                ))
    return out


def _retrieval_diagnostics(url: str, device: str, parser: _HeadParser, workspace: Path, main_ref: Any) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    main = _load_text_artifact(workspace, main_ref) or ""
    if main and len(main) > 18_000 and len(parser.sections) <= 1:
        out.append(Diagnostic(
            code="RETRIEVAL-LONG-UNSECTIONED", domain="RETRIEVAL_CHUNKABILITY", severity="MEDIUM", status="ADVISORY",
            title="Long extracted content has little heading structure",
            detail="A long main-content artifact has zero/one observed heading. This may reduce human and machine-localizable context; it is not a ranking rule.",
            url=url, device=device, evidence={"characters": len(main), "headings": len(parser.sections)},
        ))
    questions = [text for _level, text in parser.sections if text.rstrip().endswith("?")]
    if questions and len(main) < 300:
        out.append(Diagnostic(
            code="RETRIEVAL-QUESTION-THIN", domain="RETRIEVAL_CHUNKABILITY", severity="LOW", status="ADVISORY",
            title="Question headings with very little extracted answer content",
            detail="Question-like headings are present while the extracted main content is very small; inspect whether explicit answers survive rendering/extraction.",
            url=url, device=device, evidence={"question_headings": questions[:10], "characters": len(main)},
        ))
    if parser.tables_without_th:
        out.append(Diagnostic(
            code="RETRIEVAL-TABLE-HEADERS", domain="RETRIEVAL_CHUNKABILITY", severity="MEDIUM", status="ADVISORY",
            title="Tables without header cells detected",
            detail="One or more HTML tables lack <th> cells, weakening explicit row/column relationships for accessibility and extraction.",
            url=url, device=device, evidence={"tables": parser.table_count, "tables_without_th": parser.tables_without_th},
        ))
    return out


def _hreflang_diagnostics(alternates: dict[tuple[str, str], list[dict[str, str]]]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    normalized_by_url: dict[tuple[str, str], dict[str, str]] = {}
    for (url, device), items in alternates.items():
        mapping: dict[str, str] = {}
        for item in items:
            lang = item.get("hreflang", "").strip()
            href = item.get("href", "").strip()
            parsed = urlsplit(href)
            if not href or parsed.scheme not in {"http", "https"} or not parsed.hostname:
                out.append(Diagnostic(
                    code="HREFLANG-ABSOLUTE-URL", domain="INTERNATIONAL_SEARCH", severity="MEDIUM", status="INVALID",
                    title="hreflang href is not a fully qualified URL", detail=f"hreflang={lang!r} href={href!r}",
                    url=url, device=device, evidence=item, reference=HREFLANG_DOC,
                ))
                continue
            if not _hreflang_syntax(lang):
                out.append(Diagnostic(
                    code="HREFLANG-CODE-SYNTAX", domain="INTERNATIONAL_SEARCH", severity="MEDIUM", status="INVALID",
                    title="hreflang language/region code fails the conservative syntax check",
                    detail=f"Observed hreflang={lang!r}. The analyzer accepts x-default and language[-Script][-REGION] shaped values; it does not replace registry validation.",
                    url=url, device=device, evidence=item, reference=HREFLANG_DOC,
                ))
            mapping[lang.casefold()] = href
        normalized_by_url[(url, device)] = mapping
        if items and not any(_same_url(target, url) for target in mapping.values()):
            out.append(Diagnostic(
                code="HREFLANG-SELF-REFERENCE", domain="INTERNATIONAL_SEARCH", severity="MEDIUM", status="INCOMPLETE",
                title="hreflang set has no self-reference",
                detail="Google's HTML hreflang guidance says each version should list all variants, including itself.",
                url=url, device=device, evidence={"alternates": mapping}, reference=HREFLANG_DOC,
            ))

    for (url, device), mapping in normalized_by_url.items():
        for lang, target in mapping.items():
            if lang == "x-default":
                continue
            target_key = next(((candidate, dev) for candidate, dev in normalized_by_url if dev == device and _same_url(candidate, target)), None)
            if target_key is None:
                continue
            reverse = normalized_by_url[target_key]
            if not any(_same_url(back, url) for back in reverse.values()):
                out.append(Diagnostic(
                    code="HREFLANG-RECIPROCITY", domain="INTERNATIONAL_SEARCH", severity="MEDIUM", status="INCOMPLETE",
                    title="Audited hreflang alternate does not link back",
                    detail=f"{target} is an audited alternate but its observed hreflang set has no reciprocal reference to {url}.",
                    url=url, device=device, evidence={"hreflang": lang, "target": target}, reference=HREFLANG_DOC,
                ))
    return out


def _entity_consistency_diagnostics(items: list[dict[str, Any]]) -> list[Diagnostic]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        entity = item["entity"]
        types = _types(entity.get("@type"))
        if not (_organization_type(types) or "Person" in types):
            continue
        identity = _text(entity.get("@id")) or _text(entity.get("url"))
        if identity:
            groups[identity].append(item)
    out: list[Diagnostic] = []
    for identity, group in groups.items():
        names = {_text(item["entity"].get("name")) for item in group if _text(item["entity"].get("name"))}
        if len(names) > 1:
            joined_names = ", ".join(sorted(str(name) for name in names if name))
            out.append(Diagnostic(
                code="ENTITY-NAME-CONFLICT", domain="ENTITY_CONSISTENCY", severity="MEDIUM", status="CONFLICT",
                title="Same structured entity identifier has conflicting names",
                detail=f"Entity {identity} is observed with multiple names: {joined_names}.",
                evidence={"identity": identity, "names": sorted(str(name) for name in names if name), "urls": sorted({item['url'] for item in group})},
                reference=ORGANIZATION_DOC,
            ))
        same_as_sets = {tuple(sorted(_string_list(item["entity"].get("sameAs")))) for item in group if item["entity"].get("sameAs")}
        if len(same_as_sets) > 1:
            out.append(Diagnostic(
                code="ENTITY-SAMEAS-DRIFT", domain="ENTITY_CONSISTENCY", severity="LOW", status="DRIFT",
                title="sameAs declarations drift for the same entity identifier",
                detail=f"Entity {identity} has inconsistent sameAs sets across audited pages/devices.",
                evidence={"identity": identity, "sameAs_sets": [list(value) for value in sorted(same_as_sets)]}, reference=ORGANIZATION_DOC,
            ))
    return out


def _template_clusters(connection: sqlite3.Connection, audit_id: str, pages: dict[str, str]) -> list[dict[str, Any]]:
    rows = connection.execute("SELECT rule_id,page_id,device,severity,title,observed_value,status FROM findings WHERE audit_id=?", (audit_id,)).fetchall()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if str(row["status"]).upper() in {"RESOLVED", "CLOSED", "DISMISSED"}:
            continue
        observed = _json(row["observed_value"], {})
        selector = _find_selector(observed)
        signature = selector or str(row["title"])
        key = (str(row["rule_id"]), signature)
        group = groups.setdefault(key, {
            "rule_id": str(row["rule_id"]), "signature": signature, "selector": selector,
            "title": str(row["title"]), "severity": str(row["severity"]), "urls": set(), "devices": set(), "occurrences": 0,
        })
        group["occurrences"] += 1
        if row["page_id"] and str(row["page_id"]) in pages:
            group["urls"].add(pages[str(row["page_id"])])
        if row["device"]:
            group["devices"].add(str(row["device"]))
    output: list[dict[str, Any]] = []
    for group in groups.values():
        if group["occurrences"] < 2:
            continue
        output.append({
            **{key: value for key, value in group.items() if key not in {"urls", "devices"}},
            "urls": sorted(group["urls"]), "devices": sorted(group["devices"]),
            "probable_shared_cause": bool(group["selector"] and len(group["urls"]) >= 2),
        })
    return sorted(output, key=lambda item: (-int(item["occurrences"]), str(item["rule_id"]), str(item["signature"])))


def _indexability_matrix(workspace: Path, pages: dict[str, str], snapshots: list[sqlite3.Row]) -> list[dict[str, Any]]:
    local: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshots:
        url = pages.get(str(row["page_id"]))
        if not url:
            continue
        local[(url, str(row["device"]).upper())] = {
            "url": url, "device": str(row["device"]).upper(), "http_status": row["http_status"],
            "meta_robots": row["meta_robots"], "declared_canonical": row["canonical"], "final_url": row["final_url"],
        }
    external = _external_rows(workspace, "index_observations")
    output: list[dict[str, Any]] = []
    for row in local.values():
        matching = [item for item in external if _same_url(str(item.get("url") or ""), row["url"])]
        if not matching:
            output.append({**row, "source": None, "verdict": None, "indexing_state": None, "selected_canonical": None, "canonical_alignment": "NOT_OBSERVED"})
            continue
        for item in matching:
            declared = row["declared_canonical"]
            selected = item.get("selected_canonical")
            alignment = "UNKNOWN"
            if declared and selected:
                alignment = "MATCH" if _same_url(str(declared), str(selected)) else "DIFFERENT"
            output.append({
                **row, "source": item.get("source"), "verdict": item.get("verdict"),
                "coverage_state": item.get("coverage_state"), "indexing_state": item.get("indexing_state"),
                "robots_txt_state": item.get("robots_txt_state"), "page_fetch_state": item.get("page_fetch_state"),
                "selected_canonical": selected, "canonical_alignment": alignment,
            })
    return sorted(output, key=lambda item: (item["url"], item["device"], str(item.get("source") or "")))


def _query_intent(connection: sqlite3.Connection, workspace: Path, audit_id: str, pages: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    search_rows = _external_rows(workspace, "search_performance")
    if not search_rows:
        return [], []
    intents = _intent_by_url(connection, audit_id, pages)
    alignment: list[dict[str, Any]] = []
    query_urls: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in search_rows:
        query = _text(row.get("query_text"))
        url = _text(row.get("url"))
        if not query or not url:
            continue
        page_intents = intents.get(url, [])
        best = max((_token_overlap(query, intent) for intent in page_intents), default=0.0)
        status = "INTENT_NOT_AVAILABLE" if not page_intents else ("ALIGNED" if best >= 0.60 else ("PARTIAL" if best >= 0.30 else "UNMATCHED"))
        alignment.append({
            "source": row.get("source"), "surface": row.get("surface"), "query": query, "url": url,
            "impressions": row.get("impressions"), "clicks": row.get("clicks"), "best_overlap": round(best, 4),
            "status": status, "audited_intents": page_intents,
        })
        query_urls[(str(row.get("source") or ""), query.casefold())].append(row)

    candidates: list[dict[str, Any]] = []
    for (source, query_key), rows in query_urls.items():
        per_url: dict[str, float] = defaultdict(float)
        display_query = _text(rows[0].get("query_text")) or query_key
        for row in rows:
            url = _text(row.get("url"))
            if url:
                per_url[url] += float(row.get("impressions") or 0.0)
        positive = {url: value for url, value in per_url.items() if value > 0}
        total = sum(positive.values())
        if len(positive) < 2 or total <= 0:
            continue
        shares = sorted(((url, value / total) for url, value in positive.items()), key=lambda item: -item[1])
        material = [item for item in shares if item[1] >= 0.20]
        if len(material) >= 2:
            candidates.append({
                "source": source, "query": display_query, "total_impressions": total,
                "urls": [{"url": url, "impressions_share": round(share, 4)} for url, share in shares],
                "status": "POTENTIAL_CANNIBALIZATION",
                "note": "Multiple URLs materially share the same observed query. This is a diagnostic candidate, not proof of harmful cannibalization.",
            })
    return alignment, sorted(candidates, key=lambda item: -float(item["total_impressions"]))


def _intent_by_url(connection: sqlite3.Connection, audit_id: str, pages: dict[str, str]) -> dict[str, list[str]]:
    rows = connection.execute(
        """SELECT rule_id,page_id,observed_value,rowid FROM rule_executions
           WHERE audit_id=? AND rule_id IN ('BR-GEO-038','BR-GEO-048') ORDER BY rowid""", (audit_id,),
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        if row["page_id"]:
            latest[(str(row["page_id"]), str(row["rule_id"]))] = row
    out: dict[str, list[str]] = defaultdict(list)
    for (page_id, _rule), row in latest.items():
        url = pages.get(page_id)
        if not url:
            continue
        observed = _json(row["observed_value"], {})
        values: list[str] = []
        primary = observed.get("primary_intent") if isinstance(observed, dict) else None
        if isinstance(primary, dict):
            values.extend(_flatten_text(primary))
        elif _text(primary):
            values.append(_text(primary) or "")
        secondary = observed.get("secondary_intents") if isinstance(observed, dict) else None
        if isinstance(secondary, list):
            for item in secondary:
                values.extend(_flatten_text(item) if isinstance(item, dict) else ([str(item)] if _text(item) else []))
        for value in values:
            clean = " ".join(value.split())
            if clean and clean not in out[url]:
                out[url].append(clean)
    return dict(out)


def _external_rows(workspace: Path, table: str) -> list[dict[str, Any]]:
    database = workspace / "observability.db"
    if not database.is_file():
        return []
    if table not in {"search_performance", "index_observations", "crux_history", "datasets"}:
        raise ValueError("unsupported observability table")
    connection = _ro(database)
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in tables:
            return []
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


def _latest_snapshots(connection: sqlite3.Connection, audit_id: str) -> list[sqlite3.Row]:
    rows = connection.execute(
        """SELECT s.* FROM page_snapshots s JOIN pages p ON p.page_id=s.page_id
           WHERE p.audit_id=? ORDER BY s.captured_at,s.rowid""", (audit_id,),
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["page_id"]), str(row["device"]).upper())] = row
    return list(latest.values())


def _analysis_date(connection: sqlite3.Connection, audit_id: str) -> date | None:
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(audits)").fetchall()}
    for column in ("completed_at", "started_at", "created_at"):
        if column not in columns:
            continue
        row = connection.execute(f"SELECT {column} FROM audits WHERE audit_id=?", (audit_id,)).fetchone()
        if row is not None and row[0]:
            parsed = _parse_date(row[0])
            if parsed is not None:
                return parsed
    try:
        row = connection.execute(
            """SELECT MAX(s.captured_at) FROM page_snapshots s
               JOIN pages p ON p.page_id=s.page_id WHERE p.audit_id=?""",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return _parse_date(row[0]) if row is not None and row[0] else None


def _structured_entities(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("blocks"), list):
        return []
    output: list[dict[str, Any]] = []
    for block in payload["blocks"]:
        if isinstance(block, dict) and not block.get("parse_error"):
            output.extend(_flatten_entities(block.get("parsed")))
    return output


def _flatten_entities(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        output: list[dict[str, Any]] = []
        for item in value:
            output.extend(_flatten_entities(item))
        return output
    if not isinstance(value, dict):
        return []
    output = [value] if value.get("@type") else []
    if isinstance(value.get("@graph"), list):
        for item in value["@graph"]:
            output.extend(_flatten_entities(item))
    return output


def _load_json_artifact(workspace: Path, reference: Any) -> Any:
    text = _load_text_artifact(workspace, reference)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _load_text_artifact(workspace: Path, reference: Any) -> str | None:
    if not reference:
        return None
    path = workspace / str(reference)
    try:
        resolved = path.resolve()
        resolved.relative_to(workspace.resolve())
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved.read_text(encoding="utf-8", errors="replace")


def _ro(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _types(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value if item}
    return set()


def _organization_type(types: set[str]) -> bool:
    return bool(types & {"Organization", "Corporation", "OnlineBusiness", "OnlineStore", "LocalBusiness", "InsuranceAgency", "FinancialService"})


def _hreflang_syntax(value: str) -> bool:
    if value.casefold() == "x-default":
        return True
    return bool(re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?", value))


def _same_url(left: str, right: str) -> bool:
    def normalized(value: str) -> tuple[str, str, int | None, str, str]:
        parsed = urlsplit(value)
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port, path, parsed.query
    try:
        return normalized(left) == normalized(right)
    except ValueError:
        return left == right


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if _text(item)]
    return []


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _find_selector(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("selector", "css_selector", "element_selector", "cssSelector"):
            selected = _text(value.get(key))
            if selected:
                return selected
        for nested in value.values():
            selected = _find_selector(nested)
            if selected:
                return selected
    elif isinstance(value, list):
        for nested in value:
            selected = _find_selector(nested)
            if selected:
                return selected
    return None


def _flatten_text(value: dict[str, Any]) -> list[str]:
    preferred = [value.get(key) for key in ("label", "name", "intent", "text", "description", "question")]
    output = [str(item) for item in preferred if _text(item)]
    if output:
        return output
    return [str(item) for item in value.values() if _text(item)]


def _token_overlap(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _tokens(value: str) -> set[str]:
    stop = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "por", "um", "uma", "the", "of", "and", "for", "to", "in"}
    return {token for token in re.findall(r"[\wÀ-ÿ]+", value.casefold()) if len(token) > 1 and token not in stop}
