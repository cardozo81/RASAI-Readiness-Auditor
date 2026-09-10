"""Bounded llms.txt v2 discovery for M24.

The public llms.txt proposal allows a root file and scoped files below subpaths.
This module extends M24 without guessing arbitrary directories: the root
``/llms.txt`` is always checked and additional same-origin candidates are fetched
only when they are explicitly advertised by an audited resource using
``rel=describedby`` or by a clearly marked non-standard robots.txt hint.

robots.txt remains authoritative for Sitemap discovery, not llms.txt.  A custom
``LLMS:``/``LLMS-TXT:`` line is therefore treated only as an advisory discovery
hint and is surfaced as such in diagnostics.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable
from urllib.parse import urlsplit

from rasai.url_utils import is_same_origin, normalize_url


ROOT_LLMS_PATH = "/llms.txt"
MAX_LLMS_CANDIDATES = 32
MAX_DISCOVERY_HTML_BYTES = 2 * 1024 * 1024
_ROBOTS_LLMS_HINT_RE = re.compile(
    r"^\s*(?:llms(?:-txt)?|llms\.txt)\s*:\s*(\S+)\s*$",
    re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
_REL_RE = re.compile(
    r"(?:^|;)\s*rel\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^;\s,]+))",
    re.IGNORECASE,
)


class _DescribedByParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "link":
            return
        values = {str(key).casefold(): (value or "") for key, value in attrs}
        rel = {item.casefold() for item in values.get("rel", "").split() if item}
        href = values.get("href", "").strip()
        if href and "describedby" in rel:
            self.hrefs.append(href)


def install_llms_discovery_patch() -> None:
    """Install the v2 llms.txt analyzer into M24 exactly once."""
    from rasai import m24_crawling_discovery as m24

    if getattr(m24, "_rasai_llms_v2_discovery_installed", False):
        return
    m24._analyze_llms = analyze_llms_v2  # type: ignore[attr-defined]
    m24._rasai_llms_v2_discovery_installed = True  # type: ignore[attr-defined]


def analyze_llms_v2(*, origin: str, workspace: Any, client: Any):
    """Discover and acquire root/scoped llms.txt files without directory guessing."""
    from rasai.m24_crawling_discovery import M24Diagnostic

    candidates: dict[str, set[str]] = defaultdict(set)
    root_url = normalize_url(ROOT_LLMS_PATH, base_url=f"{origin}/")
    candidates[root_url].add("ROOT_CONVENTION")

    discovered, discovery_diagnostics = _discover_candidates(
        origin=origin,
        workspace=workspace,
    )
    for url, sources in discovered.items():
        candidates[url].update(sources)

    ordered = [root_url]
    ordered.extend(sorted(url for url in candidates if url != root_url))
    limited = ordered[:MAX_LLMS_CANDIDATES]
    diagnostics = list(discovery_diagnostics)
    if len(ordered) > MAX_LLMS_CANDIDATES:
        diagnostics.append(
            M24Diagnostic(
                code="M24-LLMS-DISCOVERY-LIMIT",
                category="AI_ACCESS",
                severity="INFO",
                title="Descoberta de llms.txt limitada por segurança operacional",
                scope_url=origin,
                observed={
                    "discovered_candidates": len(ordered),
                    "acquisition_limit": MAX_LLMS_CANDIDATES,
                    "skipped_candidates": ordered[MAX_LLMS_CANDIDATES:],
                },
                evidence_ids=(),
                remediation=(
                    "Nenhuma ação no website é inferida. O limite evita expansão de rede não controlada; "
                    "priorize rel=describedby explícito nas páginas relevantes."
                ),
            )
        )

    present_urls: list[str] = []
    absent_urls: list[str] = []
    unavailable_urls: list[str] = []
    for url in limited:
        sources = tuple(sorted(candidates[url]))
        acquisition = client.acquire(url)
        is_root = url == root_url
        if acquisition.network_error is not None:
            unavailable_urls.append(url)
            diagnostics.append(
                M24Diagnostic(
                    code="M24-LLMS-UNAVAILABLE" if is_root else "M24-LLMS-SCOPED-UNAVAILABLE",
                    category="AI_ACCESS",
                    severity="INFO",
                    title="llms.txt não pôde ser adquirido",
                    scope_url=url,
                    observed={
                        "state": "UNAVAILABLE",
                        "network_error": acquisition.network_error.kind.value,
                        "discovery_sources": list(sources),
                        "scope_path": _scope_path(url),
                    },
                    evidence_ids=(),
                    remediation=(
                        "Nenhuma correção obrigatória. llms.txt é uma proposta comunitária experimental, "
                        "não requisito de Search & AI."
                    ),
                )
            )
            continue

        if acquisition.status in {404, 410}:
            absent_urls.append(url)
            diagnostics.append(
                M24Diagnostic(
                    code="M24-LLMS-ABSENT" if is_root else "M24-LLMS-SCOPED-ABSENT",
                    category="AI_ACCESS",
                    severity="INFO" if is_root else "LOW",
                    title="llms.txt não encontrado",
                    scope_url=url,
                    observed={
                        "state": "ABSENT",
                        "http_status": acquisition.status,
                        "discovery_sources": list(sources),
                        "scope_path": _scope_path(url),
                    },
                    evidence_ids=(),
                    remediation=(
                        "Nenhuma ação obrigatória. A ausência do arquivo raiz não reduz score/readiness. "
                        "Para um arquivo scoped explicitamente anunciado, remova o anúncio quebrado ou publique o recurso."
                    ),
                )
            )
            continue

        if acquisition.status is None or not 200 <= acquisition.status <= 299:
            unavailable_urls.append(url)
            diagnostics.append(
                M24Diagnostic(
                    code="M24-LLMS-HTTP-UNAVAILABLE" if is_root else "M24-LLMS-SCOPED-HTTP-UNAVAILABLE",
                    category="AI_ACCESS",
                    severity="INFO" if is_root else "LOW",
                    title="llms.txt respondeu fora de 2xx",
                    scope_url=url,
                    observed={
                        "state": "UNAVAILABLE",
                        "http_status": acquisition.status,
                        "discovery_sources": list(sources),
                        "scope_path": _scope_path(url),
                    },
                    evidence_ids=(),
                    remediation=(
                        "Tratar somente se a organização optou por publicar llms.txt. Para recursos anunciados "
                        "via rel=describedby, mantenha o link e o destino coerentes."
                    ),
                )
            )
            continue

        present_urls.append(url)
        artifact_reference = _write_artifact(workspace, url, acquisition.body)
        text = acquisition.body.decode("utf-8-sig", errors="replace")
        first_content = next((line.strip() for line in text.splitlines() if line.strip()), "")
        same_origin_links, external_links = _markdown_links(text, base_url=url, origin=origin)
        diagnostics.append(
            M24Diagnostic(
                code="M24-LLMS-PRESENT",
                category="AI_ACCESS",
                severity="INFO",
                title=(
                    "llms.txt raiz presente - proposta comunitária experimental"
                    if is_root
                    else "llms.txt scoped presente - proposta comunitária experimental"
                ),
                scope_url=url,
                observed={
                    "state": "PRESENT",
                    "artifact_reference": artifact_reference,
                    "bytes": len(acquisition.body),
                    "root_file": is_root,
                    "scope_path": _scope_path(url),
                    "discovery_sources": list(sources),
                    "same_origin_links": same_origin_links[:100],
                    "external_links": external_links[:100],
                    "standard_status": "COMMUNITY_PROPOSAL_NOT_WEB_STANDARD",
                    "proposal_version": "v2",
                },
                evidence_ids=(),
                remediation=(
                    "Manter somente se houver objetivo editorial/operacional explícito. O arquivo pode existir "
                    "na raiz ou em subdiretórios e descreve o subtree correspondente; não substitui robots.txt, "
                    "sitemap, HTML semântico ou conteúdo acessível."
                ),
            )
        )
        if not first_content.startswith("# "):
            diagnostics.append(
                M24Diagnostic(
                    code="M24-LLMS-H1-MISSING",
                    category="AI_ACCESS",
                    severity="LOW",
                    title="llms.txt presente sem H1 inicial da proposta",
                    scope_url=url,
                    observed={
                        "first_content_line": first_content[:300],
                        "scope_path": _scope_path(url),
                    },
                    evidence_ids=(),
                    remediation=(
                        "Se a organização adota llms.txt, alinhar a estrutura à proposta comunitária vigente. "
                        "Isso continua sem impacto direto em scoring."
                    ),
                )
            )

    if len(present_urls) > 1:
        diagnostics.append(
            M24Diagnostic(
                code="M24-LLMS-MULTIPLE-SCOPES",
                category="AI_ACCESS",
                severity="INFO",
                title="Múltiplos llms.txt válidos observados",
                scope_url=origin,
                observed={
                    "count": len(present_urls),
                    "files": [
                        {"url": url, "scope_path": _scope_path(url)}
                        for url in present_urls
                    ],
                    "selection_rule": "MOST_SPECIFIC_PATH_APPLIES",
                },
                evidence_ids=(),
                remediation=(
                    "Informativo. Em llms.txt v2, arquivos scoped podem coexistir; o arquivo mais específico "
                    "é o aplicável às páginas sob seu caminho."
                ),
            )
        )

    diagnostics.append(
        M24Diagnostic(
            code="M24-LLMS-DISCOVERY-SUMMARY",
            category="AI_ACCESS",
            severity="INFO",
            title="Resumo de descoberta de llms.txt",
            scope_url=origin,
            observed={
                "strategy": "ROOT_PLUS_EXPLICIT_DISCOVERY",
                "root_checked": root_url,
                "candidate_count": len(limited),
                "present": present_urls,
                "absent": absent_urls,
                "unavailable": unavailable_urls,
                "directory_guessing": False,
                "robots_role": (
                    "Sitemap directives are standard; LLMS/LLMS-TXT is accepted only as an explicitly "
                    "labelled non-standard same-origin hint"
                ),
            },
            evidence_ids=(),
            remediation="Informativo; nenhum ajuste obrigatório é inferido apenas pela topologia dos arquivos.",
        )
    )

    if present_urls:
        return "PRESENT", diagnostics
    if unavailable_urls:
        return "UNAVAILABLE", diagnostics
    return "ABSENT", diagnostics


def _discover_candidates(*, origin: str, workspace: Any):
    from rasai.m24_crawling_discovery import M24Diagnostic

    candidates: dict[str, set[str]] = defaultdict(set)
    diagnostics: list[Any] = []
    database = Path(workspace.database)
    if not database.is_file():
        return candidates, diagnostics

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "evidence" in tables:
            _discover_from_http_evidence(connection, origin, candidates)
            robots_hints = _discover_from_robots(connection, origin, workspace, candidates)
            if robots_hints:
                diagnostics.append(
                    M24Diagnostic(
                        code="M24-LLMS-ROBOTS-NONSTANDARD-HINT",
                        category="AI_ACCESS",
                        severity="INFO",
                        title="robots.txt contém hint não padronizado para llms.txt",
                        scope_url=normalize_url("/robots.txt", base_url=f"{origin}/"),
                        observed={
                            "urls": sorted(robots_hints),
                            "standard_status": "NON_STANDARD_ROBOTS_DIRECTIVE",
                            "acquisition_policy": "SAME_ORIGIN_EXPLICIT_HINT_ONLY",
                        },
                        evidence_ids=(),
                        remediation=(
                            "Não dependa deste campo para interoperabilidade. robots.txt padroniza Sitemap, "
                            "Allow/Disallow e user-agents; para llms.txt scoped prefira rel=describedby "
                            "em HTML ou no cabeçalho HTTP Link."
                        ),
                    )
                )
        if "page_snapshots" in tables and "pages" in tables:
            _discover_from_snapshot_html(connection, origin, workspace, candidates)
    finally:
        connection.close()
    return candidates, diagnostics


def _discover_from_http_evidence(
    connection: sqlite3.Connection,
    origin: str,
    candidates: dict[str, set[str]],
) -> None:
    try:
        rows = connection.execute(
            """
            SELECT e.observed_value,p.normalized_url
            FROM evidence e LEFT JOIN pages p ON p.page_id=e.page_id
            WHERE e.evidence_type='HTTP_RESPONSE'
            ORDER BY e.captured_at,e.evidence_id
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return
    for row in rows:
        observed = _json_object(row["observed_value"])
        headers = observed.get("headers")
        if not isinstance(headers, list):
            continue
        base_url = str(
            observed.get("final_url")
            or observed.get("requested_url")
            or row["normalized_url"]
            or f"{origin}/"
        )
        for item in headers:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            if str(item[0]).casefold() != "link":
                continue
            for raw in _describedby_from_link_header(str(item[1])):
                _add_candidate(candidates, raw, base_url, origin, "HTTP_LINK_DESCRIBEDBY")


def _discover_from_snapshot_html(
    connection: sqlite3.Connection,
    origin: str,
    workspace: Any,
    candidates: dict[str, set[str]],
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(page_snapshots)").fetchall()
    }
    refs = [name for name in ("rendered_artifact_ref", "raw_artifact_ref") if name in columns]
    if not refs:
        return
    final_expr = "ps.final_url" if "final_url" in columns else "NULL"
    query = (
        "SELECT p.normalized_url," + final_expr + " AS final_url," +
        ",".join(f"ps.{name}" for name in refs) +
        " FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id ORDER BY p.normalized_url,ps.rowid"
    )
    try:
        rows = connection.execute(query).fetchall()
    except sqlite3.OperationalError:
        return
    seen_artifacts: set[str] = set()
    for row in rows:
        base_url = str(row["final_url"] or row["normalized_url"] or f"{origin}/")
        for ref_name in refs:
            reference = str(row[ref_name] or "").strip()
            if not reference or reference in seen_artifacts:
                continue
            seen_artifacts.add(reference)
            text = _read_artifact_text(workspace, reference)
            if text is None:
                continue
            parser = _DescribedByParser()
            try:
                parser.feed(text)
                parser.close()
            except (AssertionError, ValueError):
                continue
            for raw in parser.hrefs:
                _add_candidate(candidates, raw, base_url, origin, "HTML_LINK_DESCRIBEDBY")


def _discover_from_robots(
    connection: sqlite3.Connection,
    origin: str,
    workspace: Any,
    candidates: dict[str, set[str]],
) -> set[str]:
    try:
        row = connection.execute(
            """
            SELECT source,artifact_reference
            FROM evidence
            WHERE evidence_type='ROBOTS_RULE'
            ORDER BY captured_at DESC,evidence_id DESC LIMIT 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        return set()
    if row is None or not row["artifact_reference"]:
        return set()
    text = _read_artifact_text(workspace, str(row["artifact_reference"]))
    if text is None:
        return set()
    base_url = str(row["source"] or normalize_url("/robots.txt", base_url=f"{origin}/"))
    found: set[str] = set()
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        match = _ROBOTS_LLMS_HINT_RE.match(stripped)
        if match is None:
            continue
        before = set(candidates)
        _add_candidate(candidates, match.group(1), base_url, origin, "ROBOTS_NONSTANDARD_HINT")
        found.update(set(candidates) - before)
    return found


def _add_candidate(
    candidates: dict[str, set[str]],
    raw: str,
    base_url: str,
    origin: str,
    source: str,
) -> None:
    try:
        url = normalize_url(raw.strip().strip("<>"), base_url=base_url)
    except ValueError:
        return
    if not is_same_origin(url, origin) or not _is_llms_url(url):
        return
    candidates[url].add(source)


def _is_llms_url(url: str) -> bool:
    path = urlsplit(url).path.rstrip("/")
    return path.casefold().endswith("/llms.txt") or path.casefold() == "llms.txt"


def _scope_path(url: str) -> str:
    path = urlsplit(url).path
    if not path.casefold().endswith("llms.txt"):
        return "/"
    parent = path[: -len("llms.txt")]
    return parent if parent else "/"


def _describedby_from_link_header(value: str) -> tuple[str, ...]:
    output: list[str] = []
    for item in _split_link_header(value):
        match = re.match(r"\s*<([^>]+)>(.*)$", item)
        if match is None:
            continue
        params = match.group(2)
        rel_match = _REL_RE.search(params)
        if rel_match is None:
            continue
        rel_value = next((part for part in rel_match.groups() if part is not None), "")
        rels = {part.casefold() for part in rel_value.split() if part}
        if "describedby" in rels:
            output.append(match.group(1).strip())
    return tuple(dict.fromkeys(output))


def _split_link_header(value: str) -> list[str]:
    output: list[str] = []
    start = 0
    quote: str | None = None
    angle = 0
    for index, char in enumerate(value):
        if quote is not None:
            if char == quote and (index == 0 or value[index - 1] != "\\"):
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "<":
            angle += 1
        elif char == ">" and angle:
            angle -= 1
        elif char == "," and angle == 0:
            output.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    if tail:
        output.append(tail)
    return output


def _markdown_links(text: str, *, base_url: str, origin: str) -> tuple[list[str], list[str]]:
    same_origin: list[str] = []
    external: list[str] = []
    for raw in _MARKDOWN_LINK_RE.findall(text):
        token = raw.strip().strip("<>")
        try:
            normalized = normalize_url(token, base_url=base_url)
        except ValueError:
            continue
        bucket = same_origin if is_same_origin(normalized, origin) else external
        if normalized not in bucket:
            bucket.append(normalized)
    return same_origin, external


def _write_artifact(workspace: Any, url: str, body: bytes) -> str:
    artifact_dir = Path(workspace.artifacts) / "m24"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256(url.encode("utf-8")).hexdigest()[:16]
    artifact = artifact_dir / f"llms-{digest}.txt"
    artifact.write_bytes(body)
    return artifact.relative_to(Path(workspace.root)).as_posix()


def _read_artifact_text(workspace: Any, reference: str) -> str | None:
    root = Path(workspace.root).resolve()
    path = (Path(workspace.root) / reference).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_DISCOVERY_HTML_BYTES + 1)
    except OSError:
        return None
    return raw[:MAX_DISCOVERY_HTML_BYTES].decode("utf-8-sig", errors="replace")


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
