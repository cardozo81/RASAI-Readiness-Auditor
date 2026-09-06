"""M26 — importação e métricas de Observed Generative Visibility.

O módulo não acessa mecanismos de busca nem portais de webmaster. Ele importa
evidência local normalizada, preserva o artifact original e calcula somente
métricas cuja semântica está explícita no contrato.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from searchgeo.m26_persistence import (
    GroundingQuery,
    M26Persistence,
    PageCitation,
    QueryRun,
    TrendPoint,
    VisibilityImport,
)
from searchgeo.persistence import AuditWorkspace
from searchgeo.url_utils import normalized_origin

FORMAT_VERSION = "OGV-IMPORT-001"
SOURCE_BING = "BING_WEBMASTER_TOOLS_AI_PERFORMANCE"
SOURCE_CONTROLLED = "CONTROLLED_QUERY_RUNS"
SUPPORTED_SOURCES = (SOURCE_BING, SOURCE_CONTROLLED)


@dataclass(frozen=True, slots=True)
class VisibilityImportResult:
    import_id: str
    source_type: str
    period_start: str
    period_end: str
    page_observations: int
    grounding_queries: int
    trend_points: int
    query_runs: int
    valid_query_runs: int
    cited_query_runs: int
    citation_presence_rate: float | None
    citation_presence_ci95_low: float | None
    citation_presence_ci95_high: float | None
    artifact_path: Path


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion (default 95%)."""
    if total <= 0:
        return None
    if successes < 0 or successes > total:
        raise ValueError("successes must be between 0 and total")
    p = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denominator
    half = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def import_visibility_file(*, audit_id: str, workspace: AuditWorkspace, path: str | Path) -> VisibilityImportResult:
    source_path = Path(path)
    try:
        raw = source_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"não foi possível ler arquivo de visibilidade {source_path}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("arquivo de visibilidade deve ser JSON UTF-8 válido") from exc
    if not isinstance(payload, dict):
        raise ValueError("raiz do arquivo de visibilidade deve ser um objeto JSON")

    digest = hashlib.sha256(raw).hexdigest()
    parsed = _parse_payload(audit_id=audit_id, workspace=workspace, payload=payload, digest=digest)

    artifact_dir = workspace.artifacts / "m26"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"observed-generative-visibility-{digest[:16]}.json"
    if not artifact_path.exists() or artifact_path.read_bytes() != raw:
        artifact_path.write_bytes(raw)

    imported_at = datetime.now(timezone.utc).isoformat()
    item = VisibilityImport(
        import_id=parsed["import_id"],
        audit_id=audit_id,
        format_version=FORMAT_VERSION,
        source_type=parsed["source_type"],
        source_label=parsed["source_label"],
        period_start=parsed["period_start"],
        period_end=parsed["period_end"],
        market=parsed["market"],
        language=parsed["language"],
        source_total_citations=parsed["source_total_citations"],
        source_average_cited_pages=parsed["source_average_cited_pages"],
        artifact_path=str(artifact_path.relative_to(workspace.root)),
        artifact_sha256=digest,
        metadata=parsed["metadata"],
        imported_at=imported_at,
    )
    with M26Persistence(workspace) as persistence:
        persistence.replace_import(
            item,
            pages=parsed["pages"],
            queries=parsed["queries"],
            trend=parsed["trend"],
            query_runs=parsed["query_runs"],
        )

    valid = [run for run in parsed["query_runs"] if run.status == "VALID"]
    cited = sum(run.cited is True for run in valid)
    interval = wilson_interval(cited, len(valid))
    rate = (cited / len(valid)) if valid else None
    return VisibilityImportResult(
        import_id=item.import_id,
        source_type=item.source_type,
        period_start=item.period_start,
        period_end=item.period_end,
        page_observations=len(parsed["pages"]),
        grounding_queries=len(parsed["queries"]),
        trend_points=len(parsed["trend"]),
        query_runs=len(parsed["query_runs"]),
        valid_query_runs=len(valid),
        cited_query_runs=cited,
        citation_presence_rate=rate,
        citation_presence_ci95_low=(interval[0] if interval else None),
        citation_presence_ci95_high=(interval[1] if interval else None),
        artifact_path=artifact_path,
    )


def _parse_payload(*, audit_id: str, workspace: AuditWorkspace, payload: dict[str, Any], digest: str) -> dict[str, Any]:
    if payload.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"format_version deve ser {FORMAT_VERSION}")
    _require_audit(workspace, audit_id)
    origins = _audit_origins(workspace, audit_id)
    if not origins:
        raise ValueError(f"auditoria {audit_id} não possui normalized_origin persistido")

    source = _object(payload.get("source"), "source")
    source_type = _text(source.get("type"), "source.type")
    if source_type not in SUPPORTED_SOURCES:
        raise ValueError(f"source.type deve ser um de: {', '.join(SUPPORTED_SOURCES)}")
    source_label = _optional_text(source.get("label")) or (
        "Bing Webmaster Tools AI Performance" if source_type == SOURCE_BING else "Controlled query-runs"
    )
    period_start = _iso_date(source.get("period_start"), "source.period_start")
    period_end = _iso_date(source.get("period_end"), "source.period_end")
    if date.fromisoformat(period_start) > date.fromisoformat(period_end):
        raise ValueError("source.period_start não pode ser posterior a source.period_end")
    market = _optional_text(source.get("market"))
    language = _optional_text(source.get("language"))
    metadata = source.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("source.metadata deve ser objeto JSON")

    metrics = source.get("reported_metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError("source.reported_metrics deve ser objeto JSON")
    total_citations = _optional_nonnegative_int(metrics.get("total_citations"), "source.reported_metrics.total_citations")
    average_cited_pages = _optional_nonnegative_float(metrics.get("average_cited_pages"), "source.reported_metrics.average_cited_pages")
    if source_type != SOURCE_BING and (total_citations is not None or average_cited_pages is not None):
        raise ValueError("reported_metrics do Bing só podem ser usados com source.type BING_WEBMASTER_TOOLS_AI_PERFORMANCE")

    import_id = f"OGV-{digest[:16].upper()}"
    pages = tuple(
        _page_item(import_id, audit_id, origins, item, index)
        for index, item in enumerate(_list(payload.get("page_citations"), "page_citations"), 1)
    )
    queries = tuple(
        _query_item(import_id, audit_id, origins, item, index)
        for index, item in enumerate(_list(payload.get("grounding_queries"), "grounding_queries"), 1)
    )
    trend = tuple(
        _trend_item(import_id, audit_id, item, index)
        for index, item in enumerate(_list(payload.get("trend"), "trend"), 1)
    )
    query_runs = tuple(
        _run_item(import_id, audit_id, origins, item, index)
        for index, item in enumerate(_list(payload.get("query_runs"), "query_runs"), 1)
    )
    if not (pages or queries or trend or query_runs or total_citations is not None or average_cited_pages is not None):
        raise ValueError("arquivo M26 não contém nenhuma observação ou métrica reportada")

    return {
        "import_id": import_id,
        "source_type": source_type,
        "source_label": source_label,
        "period_start": period_start,
        "period_end": period_end,
        "market": market,
        "language": language,
        "metadata": metadata,
        "source_total_citations": total_citations,
        "source_average_cited_pages": average_cited_pages,
        "pages": pages,
        "queries": queries,
        "trend": trend,
        "query_runs": query_runs,
    }


def _page_item(import_id: str, audit_id: str, origins: set[str], raw: Any, index: int) -> PageCitation:
    item = _object(raw, f"page_citations[{index}]")
    url = _same_origin_url(item.get("url"), origins, f"page_citations[{index}].url")
    citations = _nonnegative_int(item.get("citations"), f"page_citations[{index}].citations")
    observed_date = _optional_iso_date(item.get("date"), f"page_citations[{index}].date")
    return PageCitation(f"{import_id}-P{index:05d}", import_id, audit_id, url, citations, observed_date)


def _query_item(import_id: str, audit_id: str, origins: set[str], raw: Any, index: int) -> GroundingQuery:
    item = _object(raw, f"grounding_queries[{index}]")
    query = _text(item.get("query"), f"grounding_queries[{index}].query")
    citations = _optional_nonnegative_int(item.get("citations"), f"grounding_queries[{index}].citations")
    url = None if item.get("url") is None else _same_origin_url(item.get("url"), origins, f"grounding_queries[{index}].url")
    observed_date = _optional_iso_date(item.get("date"), f"grounding_queries[{index}].date")
    return GroundingQuery(f"{import_id}-Q{index:05d}", import_id, audit_id, query, citations, url, observed_date)


def _trend_item(import_id: str, audit_id: str, raw: Any, index: int) -> TrendPoint:
    item = _object(raw, f"trend[{index}]")
    observed_date = _iso_date(item.get("date"), f"trend[{index}].date")
    citations = _nonnegative_int(item.get("citations"), f"trend[{index}].citations")
    return TrendPoint(f"{import_id}-T{index:05d}", import_id, audit_id, observed_date, citations)


def _run_item(import_id: str, audit_id: str, origins: set[str], raw: Any, index: int) -> QueryRun:
    item = _object(raw, f"query_runs[{index}]")
    engine = _text(item.get("engine"), f"query_runs[{index}].engine")
    surface = _optional_text(item.get("surface"))
    query = _text(item.get("query"), f"query_runs[{index}].query")
    observed_at = _iso_datetime(item.get("observed_at"), f"query_runs[{index}].observed_at")
    status = _text(item.get("status"), f"query_runs[{index}].status").upper()
    if status not in {"VALID", "INVALID"}:
        raise ValueError(f"query_runs[{index}].status deve ser VALID ou INVALID")
    cited_raw = item.get("cited")
    if status == "VALID":
        if not isinstance(cited_raw, bool):
            raise ValueError(f"query_runs[{index}].cited deve ser booleano quando status=VALID")
        cited: bool | None = cited_raw
    else:
        if cited_raw is not None:
            raise ValueError(f"query_runs[{index}].cited deve ser null/ausente quando status=INVALID")
        cited = None

    cited_urls_raw = item.get("cited_urls") or []
    if not isinstance(cited_urls_raw, list) or any(not isinstance(value, str) for value in cited_urls_raw):
        raise ValueError(f"query_runs[{index}].cited_urls deve ser lista de URLs")
    cited_urls = tuple(_same_origin_url(value, origins, f"query_runs[{index}].cited_urls") for value in cited_urls_raw)
    if status == "VALID" and cited is True and not cited_urls:
        raise ValueError(f"query_runs[{index}] citado deve informar ao menos uma URL do origin auditado")
    if status == "VALID" and cited is False and cited_urls:
        raise ValueError(f"query_runs[{index}] não citado não pode informar cited_urls")

    rank = item.get("rank")
    source_rank = None if rank is None else _positive_int(rank, f"query_runs[{index}].rank")
    ranking_semantics = _optional_text(item.get("ranking_semantics"))
    if source_rank is not None and not ranking_semantics:
        raise ValueError(f"query_runs[{index}].ranking_semantics é obrigatório quando rank é informado")

    return QueryRun(
        query_run_id=f"{import_id}-R{index:05d}", import_id=import_id, audit_id=audit_id,
        engine=engine, surface=surface, query_text=query, observed_at=observed_at,
        market=_optional_text(item.get("market")), language=_optional_text(item.get("language")),
        status=status, cited=cited, cited_urls=cited_urls, source_rank=source_rank,
        ranking_semantics=ranking_semantics, notes=_optional_text(item.get("notes")),
    )


def _require_audit(workspace: AuditWorkspace, audit_id: str) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute("SELECT 1 FROM audits WHERE audit_id=?", (audit_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError(f"auditoria não encontrada no workspace: {audit_id}")


def _audit_origins(workspace: AuditWorkspace, audit_id: str) -> set[str]:
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute("SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=?", (audit_id,)).fetchall()
    finally:
        connection.close()
    return {str(row[0]).rstrip("/") for row in rows if row[0]}


def _same_origin_url(value: Any, origins: set[str], field: str) -> str:
    text = _text(value, field)
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} deve ser URL HTTP(S) absoluta")
    try:
        origin = normalized_origin(text).rstrip("/")
    except ValueError as exc:
        raise ValueError(f"{field} possui URL inválida") from exc
    if origin not in origins:
        raise ValueError(f"{field} pertence a origin diferente da auditoria: {origin}")
    return text


def _list(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} deve ser lista JSON")
    return value


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} deve ser objeto JSON")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("campo textual opcional deve ser string")
    text = value.strip()
    return text or None


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} deve ser inteiro >= 0")
    return value


def _positive_int(value: Any, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result <= 0:
        raise ValueError(f"{field} deve ser inteiro > 0")
    return result


def _optional_nonnegative_int(value: Any, field: str) -> int | None:
    return None if value is None else _nonnegative_int(value, field)


def _optional_nonnegative_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} deve ser número >= 0")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field} deve ser número finito >= 0")
    return result


def _iso_date(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} deve usar YYYY-MM-DD") from exc


def _optional_iso_date(value: Any, field: str) -> str | None:
    return None if value is None else _iso_date(value, field)


def _iso_datetime(value: Any, field: str) -> str:
    text = _text(value, field)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} deve ser timestamp ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} deve conter timezone/offset")
    return parsed.isoformat()
