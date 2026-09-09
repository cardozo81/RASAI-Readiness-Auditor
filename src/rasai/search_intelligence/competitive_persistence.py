"""Additive persistence for deterministic Competitive Search & Content Intelligence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from .content import CompetitiveContentAnalysis, CompetitivePageFeatures
from .competitive import CompetitiveSelection


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _page_payload(page: CompetitivePageFeatures | None) -> dict[str, Any] | None:
    if page is None:
        return None
    return {
        "role": page.role,
        "domain": page.domain,
        "requested_url": page.requested_url,
        "final_url": page.final_url,
        "status": page.status.value,
        "http_status": page.http_status,
        "content_type": page.content_type,
        "content_sha256": page.content_sha256,
        "bytes_read": page.bytes_read,
        "title": page.title,
        "meta_description": page.meta_description,
        "headings": list(page.headings),
        "word_count": page.word_count,
        "query_terms": list(page.query_terms),
        "query_terms_in_title": list(page.query_terms_in_title),
        "query_terms_in_description": list(page.query_terms_in_description),
        "query_terms_in_headings": list(page.query_terms_in_headings),
        "query_terms_in_body": list(page.query_terms_in_body),
        "jsonld_types": list(page.jsonld_types),
        "error_code": page.error_code,
        "error_message": page.error_message,
        "redirects": list(page.redirects),
    }


def _selection_payload(selection: CompetitiveSelection) -> dict[str, Any]:
    return {
        "query": selection.query,
        "customer_domain": selection.customer_domain,
        "customer_result": (
            {
                "position": selection.customer_result.position,
                "domain": selection.customer_result.domain,
                "url": selection.customer_result.url,
            }
            if selection.customer_result is not None
            else None
        ),
        "classified_results": [
            {
                "position": item.result.position,
                "domain": item.result.domain,
                "url": item.result.url,
                "classification": item.classification.value,
                "eligible_for_content_comparison": item.eligible_for_content_comparison,
                "reason": item.reason,
            }
            for item in selection.classified_results
        ],
        "selected_candidates": [
            {
                "position": item.result.position,
                "domain": item.result.domain,
                "url": item.result.url,
                "classification": item.classification.value,
            }
            for item in selection.selected_candidates
        ],
    }


def analysis_payload(analysis: CompetitiveContentAnalysis) -> dict[str, Any]:
    return {
        "methodology": analysis.methodology,
        "comparison_status": analysis.comparison_status,
        "selection": _selection_payload(analysis.selection),
        "customer_page": _page_payload(analysis.customer_page),
        "competitor_pages": [_page_payload(item) for item in analysis.competitor_pages],
        "gaps": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "customer_value": item.customer_value,
                "leader_reference": item.leader_reference,
                "evidence_urls": list(item.evidence_urls),
            }
            for item in analysis.gaps
        ],
        "interpretation_policy": (
            "Observed deterministic differences are correlational context only; "
            "RASAI does not infer that a difference caused ranking position."
        ),
        "raw_html_persisted": False,
    }


class FilesystemCompetitiveEvidenceSink:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.root = self.workspace_root / "artifacts" / "search-intelligence" / "competitive"

    def write(self, observation_id: str, analysis: CompetitiveContentAnalysis) -> tuple[str, str]:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = _dump(analysis_payload(analysis)).encode("utf-8")
        digest = sha256(payload).hexdigest()
        path = self.root / f"{observation_id}.json"
        path.write_bytes(payload)
        return path.relative_to(self.workspace_root).as_posix(), digest


class CompetitiveIntelligenceRepository:
    """Persist competitive classification/content without touching scoring tables."""

    def __init__(self, database: Path, *, audit_id: str) -> None:
        self.database = Path(database)
        self.audit_id = audit_id
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "CompetitiveIntelligenceRepository":
        root = Path(workspace_root)
        database = root / "audit.db"
        if not database.is_file():
            raise FileNotFoundError(f"audit database not found: {database}")
        connection = sqlite3.connect(database)
        try:
            rows = connection.execute(
                "SELECT audit_id FROM audits ORDER BY created_at LIMIT 2"
            ).fetchall()
        finally:
            connection.close()
        if len(rows) != 1:
            raise ValueError(
                f"expected exactly one audit row in workspace {root}; found {len(rows)}"
            )
        return cls(database, audit_id=str(rows[0][0]))

    def __enter__(self) -> "CompetitiveIntelligenceRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS serp_competitive_analyses (
                    observation_id TEXT PRIMARY KEY
                        REFERENCES serp_observations(observation_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    methodology TEXT NOT NULL,
                    comparison_status TEXT NOT NULL,
                    customer_url TEXT,
                    candidate_count INTEGER NOT NULL,
                    observed_competitor_pages INTEGER NOT NULL,
                    gap_count INTEGER NOT NULL,
                    gaps_json TEXT NOT NULL,
                    evidence_ref TEXT,
                    evidence_sha256 TEXT
                );

                CREATE TABLE IF NOT EXISTS serp_competitive_results (
                    observation_id TEXT NOT NULL
                        REFERENCES serp_observations(observation_id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    eligible_for_content_comparison INTEGER NOT NULL,
                    selected_for_content_comparison INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    PRIMARY KEY (observation_id, position, url)
                );

                CREATE TABLE IF NOT EXISTS serp_competitive_pages (
                    observation_id TEXT NOT NULL
                        REFERENCES serp_observations(observation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    requested_url TEXT NOT NULL,
                    final_url TEXT,
                    fetch_status TEXT NOT NULL,
                    http_status INTEGER,
                    content_type TEXT,
                    content_sha256 TEXT,
                    bytes_read INTEGER NOT NULL,
                    title TEXT,
                    meta_description TEXT,
                    headings_json TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    query_terms_json TEXT NOT NULL,
                    query_terms_title_json TEXT NOT NULL,
                    query_terms_description_json TEXT NOT NULL,
                    query_terms_headings_json TEXT NOT NULL,
                    query_terms_body_json TEXT NOT NULL,
                    jsonld_types_json TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    redirects_json TEXT NOT NULL,
                    PRIMARY KEY (observation_id, role, requested_url)
                );

                CREATE INDEX IF NOT EXISTS idx_serp_competitive_analyses_audit
                    ON serp_competitive_analyses(audit_id, comparison_status);
                CREATE INDEX IF NOT EXISTS idx_serp_competitive_results_class
                    ON serp_competitive_results(classification, observation_id, position);
                CREATE INDEX IF NOT EXISTS idx_serp_competitive_pages_domain
                    ON serp_competitive_pages(domain, observation_id, role);
                """
            )

    def save(
        self,
        observation_id: str,
        analysis: CompetitiveContentAnalysis,
        *,
        evidence_ref: str | None = None,
        evidence_sha256: str | None = None,
    ) -> None:
        selected = {
            (item.result.position, item.result.url)
            for item in analysis.selection.selected_candidates
        }
        pages = tuple(
            item
            for item in ((analysis.customer_page,) + analysis.competitor_pages)
            if item is not None
        )
        observed_competitors = sum(
            item.role == "COMPETITOR_CANDIDATE" and item.status.value == "OBSERVED"
            for item in pages
        )
        customer_url = (
            analysis.customer_page.requested_url
            if analysis.customer_page is not None
            else (
                analysis.selection.customer_result.url
                if analysis.selection.customer_result is not None
                else None
            )
        )
        gaps_json = _dump(
            [
                {
                    "code": gap.code,
                    "severity": gap.severity,
                    "message": gap.message,
                    "customer_value": gap.customer_value,
                    "leader_reference": gap.leader_reference,
                    "evidence_urls": list(gap.evidence_urls),
                }
                for gap in analysis.gaps
            ]
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO serp_competitive_analyses (
                    observation_id,audit_id,methodology,comparison_status,customer_url,
                    candidate_count,observed_competitor_pages,gap_count,gaps_json,
                    evidence_ref,evidence_sha256
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    observation_id,
                    self.audit_id,
                    analysis.methodology,
                    analysis.comparison_status,
                    customer_url,
                    len(analysis.selection.selected_candidates),
                    observed_competitors,
                    len(analysis.gaps),
                    gaps_json,
                    evidence_ref,
                    evidence_sha256,
                ),
            )
            self.connection.execute(
                "DELETE FROM serp_competitive_results WHERE observation_id=?",
                (observation_id,),
            )
            self.connection.executemany(
                """
                INSERT INTO serp_competitive_results (
                    observation_id,position,domain,url,classification,
                    eligible_for_content_comparison,selected_for_content_comparison,reason
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        observation_id,
                        item.result.position,
                        item.result.domain,
                        item.result.url,
                        item.classification.value,
                        int(item.eligible_for_content_comparison),
                        int((item.result.position, item.result.url) in selected),
                        item.reason,
                    )
                    for item in analysis.selection.classified_results
                ],
            )
            self.connection.execute(
                "DELETE FROM serp_competitive_pages WHERE observation_id=?",
                (observation_id,),
            )
            self.connection.executemany(
                """
                INSERT INTO serp_competitive_pages (
                    observation_id,role,domain,requested_url,final_url,fetch_status,
                    http_status,content_type,content_sha256,bytes_read,title,meta_description,
                    headings_json,word_count,query_terms_json,query_terms_title_json,
                    query_terms_description_json,query_terms_headings_json,
                    query_terms_body_json,jsonld_types_json,error_code,error_message,
                    redirects_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        observation_id,
                        page.role,
                        page.domain,
                        page.requested_url,
                        page.final_url,
                        page.status.value,
                        page.http_status,
                        page.content_type,
                        page.content_sha256,
                        page.bytes_read,
                        page.title,
                        page.meta_description,
                        _dump(list(page.headings)),
                        page.word_count,
                        _dump(list(page.query_terms)),
                        _dump(list(page.query_terms_in_title)),
                        _dump(list(page.query_terms_in_description)),
                        _dump(list(page.query_terms_in_headings)),
                        _dump(list(page.query_terms_in_body)),
                        _dump(list(page.jsonld_types)),
                        page.error_code,
                        page.error_message,
                        _dump(list(page.redirects)),
                    )
                    for page in pages
                ],
            )
