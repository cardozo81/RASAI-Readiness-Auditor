"""Persist per-sample browser/request error evidence for Synthetic UX Apdex.

The canonical M25 score remains unchanged. This additive layer records the concrete
request/HTTP/console/JavaScript events behind an error-forced FRUSTRATED sample so the
report can explain *which* external or first-party resources participated in the policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import sqlite3
import threading
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


_MAX_DETAILS_PER_SAMPLE = 100
_CAPTURE = threading.local()
_LOCK = threading.Lock()
_BY_MEASUREMENT: dict[int, tuple[dict[str, Any], ...]] = {}
_BY_SAMPLE: dict[str, tuple[dict[str, Any], ...]] = {}
_INSTALLED = False
_REPORT_WRAPPED = False


def _bounded(value: Any, maximum: int) -> str:
    text = str(value or "")
    return text if len(text) <= maximum else text[:maximum] + "…"


def _host(value: str | None) -> str:
    raw = str(value or "").strip().casefold().rstrip(".")
    if raw.startswith("www."):
        raw = raw[4:]
    return raw


def _is_first_party(candidate: str | None, target_host: str) -> bool | None:
    if not candidate:
        return None
    try:
        host = _host(urlsplit(str(candidate)).hostname)
    except Exception:
        return None
    return bool(host and target_host and host == target_host)


def _begin_capture(target_url: str) -> None:
    _CAPTURE.target_host = _host(urlsplit(target_url).hostname)
    _CAPTURE.details = []


def _append_detail(
    error_type: str,
    *,
    source_url: str | None = None,
    resource_type: str | None = None,
    http_status: int | None = None,
    message: str | None = None,
) -> None:
    details = getattr(_CAPTURE, "details", None)
    if not isinstance(details, list) or len(details) >= _MAX_DETAILS_PER_SAMPLE:
        return
    target_host = str(getattr(_CAPTURE, "target_host", "") or "")
    details.append(
        {
            "error_type": error_type,
            "source_url": _bounded(source_url, 2048) or None,
            "first_party": _is_first_party(source_url, target_host),
            "resource_type": _bounded(resource_type, 64) or None,
            "http_status": int(http_status) if http_status is not None else None,
            "message": _bounded(message, 1000) or None,
        }
    )


def _finish_capture() -> tuple[dict[str, Any], ...]:
    details = tuple(dict(item) for item in getattr(_CAPTURE, "details", []) if isinstance(item, Mapping))
    for name in ("details", "target_host"):
        try:
            delattr(_CAPTURE, name)
        except AttributeError:
            pass
    return details


class _PageProxy:
    def __init__(self, page: Any) -> None:
        self._page = page

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def on(self, event: str, handler: Any) -> Any:
        if event == "requestfailed":
            def wrapped(request: Any) -> None:
                try:
                    failure = getattr(request, "failure", None)
                    if callable(failure):
                        failure = failure()
                    _append_detail(
                        "REQUEST_FAILED",
                        source_url=str(getattr(request, "url", "") or ""),
                        resource_type=str(getattr(request, "resource_type", "") or ""),
                        message=failure,
                    )
                finally:
                    handler(request)
            return self._page.on(event, wrapped)
        if event == "response":
            def wrapped(response: Any) -> None:
                try:
                    status = int(getattr(response, "status", 0) or 0)
                    if status >= 400:
                        request = getattr(response, "request", None)
                        resource_type = getattr(request, "resource_type", "") if request is not None else ""
                        _append_detail(
                            "HTTP_ERROR",
                            source_url=str(getattr(response, "url", "") or ""),
                            resource_type=str(resource_type or ""),
                            http_status=status,
                        )
                finally:
                    handler(response)
            return self._page.on(event, wrapped)
        if event == "console":
            def wrapped(message: Any) -> None:
                try:
                    if str(getattr(message, "type", "")) == "error":
                        location = getattr(message, "location", None)
                        if callable(location):
                            location = location()
                        source_url = location.get("url") if isinstance(location, Mapping) else None
                        _append_detail(
                            "CONSOLE_ERROR",
                            source_url=str(source_url or ""),
                            message=str(getattr(message, "text", "") or ""),
                        )
                finally:
                    handler(message)
            return self._page.on(event, wrapped)
        if event == "pageerror":
            def wrapped(error: Any) -> None:
                try:
                    _append_detail("JAVASCRIPT_ERROR", message=str(error))
                finally:
                    handler(error)
            return self._page.on(event, wrapped)
        return self._page.on(event, handler)


class _ContextProxy:
    def __init__(self, context: Any) -> None:
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)

    def new_page(self) -> _PageProxy:
        return _PageProxy(self._context.new_page())


def _patch_m25_capture() -> None:
    from rasai import m25_apdex_experience as m25

    current_context = m25.PlaywrightSyntheticUxGateway._context
    if not getattr(current_context, "_rasai_error_evidence", False):
        def context(self: Any, *, device: str, profile: Any) -> tuple[Any, bool]:
            real, close_context = current_context(self, device=device, profile=profile)
            return _ContextProxy(real), close_context
        context._rasai_error_evidence = True
        context._rasai_original = current_context
        m25.PlaywrightSyntheticUxGateway._context = context

    current_measure = m25.PlaywrightSyntheticUxGateway.measure
    if not getattr(current_measure, "_rasai_error_evidence", False):
        def measure(self: Any, *, url: str, device: str, profile: Any, timeout_seconds: float, settle_seconds: float):
            _begin_capture(url)
            try:
                result = current_measure(
                    self,
                    url=url,
                    device=device,
                    profile=profile,
                    timeout_seconds=timeout_seconds,
                    settle_seconds=settle_seconds,
                )
            finally:
                details = _finish_capture()
            with _LOCK:
                _BY_MEASUREMENT[id(result)] = details
            return result
        measure._rasai_error_evidence = True
        measure._rasai_original = current_measure
        m25.PlaywrightSyntheticUxGateway.measure = measure

    current_persisted = m25._persisted_sample
    if not getattr(current_persisted, "_rasai_error_evidence", False):
        def persisted_sample(*args: Any, **kwargs: Any):
            item = kwargs.get("item")
            if item is None and len(args) >= 7:
                item = args[6]
            sample = current_persisted(*args, **kwargs)
            measurement = getattr(item, "measurement", None)
            with _LOCK:
                details = _BY_MEASUREMENT.pop(id(measurement), ()) if measurement is not None else ()
                if details:
                    _BY_SAMPLE[str(sample.sample_id)] = details
            return sample
        persisted_sample._rasai_error_evidence = True
        persisted_sample._rasai_original = current_persisted
        m25._persisted_sample = persisted_sample


def _patch_persistence() -> None:
    from rasai import m25_persistence as persistence

    current_initialize = persistence.M25Persistence._initialize
    if not getattr(current_initialize, "_rasai_error_evidence", False):
        def initialize(self: Any) -> None:
            current_initialize(self)
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS synthetic_ux_apdex_error_details (
                        sample_id TEXT NOT NULL REFERENCES synthetic_ux_apdex_samples(sample_id) ON DELETE CASCADE,
                        sequence_no INTEGER NOT NULL,
                        audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                        error_type TEXT NOT NULL,
                        source_url TEXT,
                        first_party INTEGER,
                        resource_type TEXT,
                        http_status INTEGER,
                        message TEXT,
                        captured_at TEXT NOT NULL,
                        PRIMARY KEY(sample_id, sequence_no)
                    );
                    CREATE INDEX IF NOT EXISTS idx_synthetic_ux_error_details_audit
                        ON synthetic_ux_apdex_error_details(audit_id, sample_id, sequence_no);
                    """
                )
        initialize._rasai_error_evidence = True
        initialize._rasai_original = current_initialize
        persistence.M25Persistence._initialize = initialize

    current_add = persistence.M25Persistence.add_sample
    if not getattr(current_add, "_rasai_error_evidence", False):
        def add_sample(self: Any, item: Any) -> None:
            current_add(self, item)
            with _LOCK:
                details = _BY_SAMPLE.pop(str(item.sample_id), ())
            if not details:
                return
            with self.connection:
                self.connection.execute(
                    "DELETE FROM synthetic_ux_apdex_error_details WHERE sample_id=?",
                    (item.sample_id,),
                )
                self.connection.executemany(
                    """
                    INSERT INTO synthetic_ux_apdex_error_details (
                        sample_id,sequence_no,audit_id,error_type,source_url,first_party,
                        resource_type,http_status,message,captured_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            item.sample_id,
                            index,
                            item.audit_id,
                            detail.get("error_type") or "UNKNOWN",
                            detail.get("source_url"),
                            None if detail.get("first_party") is None else int(bool(detail.get("first_party"))),
                            detail.get("resource_type"),
                            detail.get("http_status"),
                            detail.get("message"),
                            item.captured_at,
                        )
                        for index, detail in enumerate(details, 1)
                    ],
                )
        add_sample._rasai_error_evidence = True
        add_sample._rasai_original = current_add
        persistence.M25Persistence.add_sample = add_sample


def _error_details_html(database: Any, audit_id: str) -> str:
    from rasai import catalog_report_analysis as analysis

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='synthetic_ux_apdex_error_details'"
        ).fetchone()
        if not exists:
            return ""
        rows = [dict(row) for row in connection.execute(
            """
            SELECT d.*, s.run_index, s.device
            FROM synthetic_ux_apdex_error_details d
            LEFT JOIN synthetic_ux_apdex_samples s ON s.sample_id=d.sample_id
            WHERE d.audit_id=?
            ORDER BY s.run_index, d.sequence_no
            """,
            (audit_id,),
        ).fetchall()]
    finally:
        connection.close()
    if not rows:
        return ""
    table_rows: list[Sequence[Any]] = []
    labels = {
        "REQUEST_FAILED": "Requisição com falha",
        "HTTP_ERROR": "Resposta HTTP com erro",
        "CONSOLE_ERROR": "Erro de console",
        "JAVASCRIPT_ERROR": "Erro JavaScript",
    }
    for row in rows:
        first_party = "Sim" if row.get("first_party") == 1 else "Não" if row.get("first_party") == 0 else "Indeterminado"
        technical = row.get("http_status") or row.get("resource_type") or "—"
        source = row.get("source_url") or "—"
        if row.get("message"):
            source += " · " + _bounded(row.get("message"), 240)
        table_rows.append((
            row.get("run_index") or "—",
            analysis._device_label(row.get("device")),
            labels.get(str(row.get("error_type") or ""), row.get("error_type") or "—"),
            source,
            first_party,
            technical,
        ))
    return (
        "<details><summary>Ver eventos que podem forçar Apdex frustrado ("
        + str(len(rows))
        + ")</summary><div class='detail-body'><p class='section-lead'>"
        "Eventos persistidos por amostra. Permitem distinguir recursos próprios de terceiros e "
        "erros de console/JavaScript quando a política de erros participa do Apdex.</p>"
        + analysis._table(
            ("Amostra", "Dispositivo", "Tipo", "URL/fonte e mensagem", "Primeira parte", "HTTP/recurso"),
            table_rows,
            sortable=True,
            page_size=10 if len(table_rows) > 10 else None,
        )
        + "</div></details>"
    )


def _patch_report_projection() -> None:
    from rasai import catalog_report_analysis as analysis
    from rasai import catalog_report_page as page

    current = page._apdex_samples_html
    if getattr(current, "_rasai_error_evidence", False):
        return

    def apdex_samples_html(database: Any, data: Any, *, experience: bool) -> str:
        html = current(database, data, experience=experience)
        if experience:
            html += _error_details_html(database, data.audit_id)
        return html

    apdex_samples_html._rasai_error_evidence = True
    apdex_samples_html._rasai_original = current
    page._apdex_samples_html = apdex_samples_html
    analysis._apdex_samples_html = apdex_samples_html


def _wrap_report_install() -> None:
    global _REPORT_WRAPPED
    if _REPORT_WRAPPED:
        return
    from rasai import catalog_report_adherence as adherence

    current = adherence.install_catalog_report_adherence
    if getattr(current, "_rasai_error_evidence", False):
        _REPORT_WRAPPED = True
        return

    def install_catalog_report_adherence() -> None:
        current()
        _patch_report_projection()

    install_catalog_report_adherence._rasai_error_evidence = True
    install_catalog_report_adherence._rasai_original = current
    adherence.install_catalog_report_adherence = install_catalog_report_adherence
    _REPORT_WRAPPED = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_m25_capture()
    _patch_persistence()
    _wrap_report_install()
    _INSTALLED = True


__all__ = [
    "_PageProxy",
    "_begin_capture",
    "_finish_capture",
    "_error_details_html",
    "install",
]
