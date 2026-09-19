"""Safety gate for credential-free public observability collectors.

Common Crawl is enabled by the packaged safe baseline because it is free and requires
no credential. That default must never leak private/internal targets or URL parameters
into a public index lookup. This wrapper suppresses only Common Crawl for the current
finalization when the bounded candidate set is not safe for public disclosure.

The SARI corroboration installers are composed here for the top-level CLI. They perform
their own equivalent pre-scoring safety gate because scoring occurs before report
finalization, then explain any bounded contribution in readiness/scoring HTML.
"""
from __future__ import annotations

from contextlib import contextmanager
import ipaddress
import logging
import os
import sqlite3
from typing import Any, Iterator
from urllib.parse import urlsplit

from rasai.external_observability_policy import (
    COMMON_CRAWL_ENABLED_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
    common_crawl_max_urls,
)


_LOGGER = logging.getLogger(__name__)
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".example", ".invalid")


def install() -> None:
    """Wrap final reports and install the pre-scoring external corroboration gate."""
    from rasai import report_completion

    if not getattr(report_completion, "_rasai_external_observability_public_target_safety", False):
        original = report_completion.finalize_audit_report_site

        def finalize_with_public_target_safety(*, audit_id: str, workspace: Any, **kwargs: Any):
            reason = _common_crawl_block_reason(workspace=workspace, audit_id=audit_id)
            if reason is None:
                return original(audit_id=audit_id, workspace=workspace, **kwargs)
            _LOGGER.warning("Common Crawl skipped for audit %s: %s", audit_id, reason)
            with _temporary_environment(COMMON_CRAWL_ENABLED_ENV, "false"):
                return original(audit_id=audit_id, workspace=workspace, **kwargs)

        report_completion.finalize_audit_report_site = finalize_with_public_target_safety
        report_completion._rasai_external_observability_public_target_safety = True

    # Import late to keep metadata/configuration discovery side-effect free.
    # External SARI persists corroboration data; its retired HTML projection is not installed.
    from rasai.external_sari import install as install_external_sari
    install_external_sari()

    # Progress/evidence-ordering installers are also late: they must wrap the final
    # composed runtime and never affect metadata-only provider/service discovery.
    from rasai.audit_progress_runtime import install as install_audit_progress_runtime
    from rasai.external_observability_progress_runtime import install as install_external_progress_runtime
    install_audit_progress_runtime()
    install_external_progress_runtime()


def _common_crawl_block_reason(*, workspace: Any, audit_id: str) -> str | None:
    raw_enabled = (os.environ.get(COMMON_CRAWL_ENABLED_ENV) or "").strip().casefold()
    if raw_enabled in {"0", "false", "no", "off"}:
        return None
    limit = common_crawl_max_urls(os.environ.get(COMMON_CRAWL_MAX_URLS_ENV))
    if limit == 0:
        return None
    urls = _candidate_urls(workspace=workspace, audit_id=audit_id, limit=limit)
    if not urls:
        return None
    unsafe = [(url, _unsafe_reason(url)) for url in urls]
    unsafe = [(url, reason) for url, reason in unsafe if reason]
    if not unsafe:
        return None
    reasons = ", ".join(f"{reason}:{_redacted_url(url)}" for url, reason in unsafe[:3])
    return "PUBLIC_INDEX_TARGET_NOT_SAFE" + (f" ({reasons})" if reasons else "")


def _candidate_urls(*, workspace: Any, audit_id: str, limit: int) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid LIMIT ?",
            (audit_id, int(limit)),
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]) for row in rows if row and row[0])


def _unsafe_reason(url: str) -> str | None:
    try:
        parsed = urlsplit(str(url))
    except ValueError:
        return "INVALID_URL"
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return "NON_HTTP_TARGET"
    if parsed.username is not None or parsed.password is not None:
        return "USERINFO_PRESENT"
    if parsed.query:
        return "QUERY_PRESENT"
    if parsed.fragment:
        return "FRAGMENT_PRESENT"
    host = parsed.hostname.rstrip(".").casefold()
    if host in _BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        return "PRIVATE_OR_RESERVED_HOST"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    return None if address.is_global else "PRIVATE_OR_RESERVED_IP"


def _redacted_url(url: str) -> str:
    """Keep logs useful without copying query/credentials from an unsafe target."""
    try:
        parsed = urlsplit(str(url))
    except ValueError:
        return "<invalid-url>"
    host = parsed.hostname or "<no-host>"
    path = parsed.path or "/"
    if len(path) > 120:
        path = path[:117] + "..."
    return f"{parsed.scheme or '<scheme>'}://{host}{path}"


@contextmanager
def _temporary_environment(name: str, value: str) -> Iterator[None]:
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous
