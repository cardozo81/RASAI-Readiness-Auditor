"""Structural assurance gate for the catalog report.

Percentages in this module are deterministic control-coverage ratios. They are not
statistical probabilities that a website fact is true. External source outages or
legitimate NO_DATA states do not reduce structural assurance when they are persisted
and exposed truthfully.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape, unescape
import inspect
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.secret_safety import detect_secret_exposures

CATALOG_MATURITY_MIN = 95.0
HIGH_ASSURANCE_MIN = 99.5

_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|authorization|bearer|token|secret|password|passwd|cookie|client[_-]?secret)",
    re.I,
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_APIKEY_RE = re.compile(r"(?i)\b(?:sk|key|token)[-_][A-Za-z0-9._-]{12,}")
_EXTERNAL_LINK_RE = re.compile(r"<a\b([^>]*?)href=['\"]https?://[^'\"]+['\"]([^>]*)>", re.I)
_EVENT_HANDLER_RE = re.compile(r"\son[a-z]+\s*=", re.I)

_SPECIFIC_CONFIG_MARKERS: dict[str, tuple[str, ...]] = {
    "CAT-03": (
        "Perfil de risco",
        "Categoria YMYL",
        "Propósito da página",
        "Público pretendido",
        "Requisito de experiência",
        "Sensibilidade à atualização",
        "Origem do conteúdo",
    ),
    "CAT-04": (
        "Desempenho web",
        "Fonte de dados de campo",
        "Categorias Lighthouse",
    ),
    "CAT-05": (
        "Termos de busca",
        "Localidade",
        "Profundidade desejada",
        "Dispositivo",
        "Análise de concorrentes",
        "Comparação de conteúdo",
        "Máx. páginas concorrentes",
        "Timeout conteúdo",
        "Máx. bytes por página",
        "Máx. redirects",
        "IA competitiva",
        "Contexto YMYL da IA",
    ),
    "CAT-06": (
        "Limite para experiência satisfatória",
        "Amostras por contexto",
        "Máximo de tentativas",
    ),
    "CAT-07": (
        "Amostras por página",
        "Limite satisfatório",
        "Limite frustrado",
        "Erros afetam o Apdex",
        "Escopo de erros",
        "Sessão",
    ),
    "CAT-08": (
        "Domínios analisados",
        "Máximo de recomendações",
    ),
    "CAT-09": (
        "Enriquecimento de conteúdo",
        "Remediação técnica",
    ),
}

_ARTIFACT_PAIRS = (
    ("evidence_ref", "evidence_sha256"),
    ("raw_evidence_ref", "raw_evidence_sha256"),
    ("artifact_ref", "artifact_sha256"),
    ("artifact_reference", "artifact_sha256"),
    ("response_artifact_ref", "response_artifact_sha256"),
    ("report_artifact_ref", "report_artifact_sha256"),
)


def _check(code: str, axis: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"code": code, "axis": axis, "passed": bool(passed), "detail": detail}


def _score(checks: Sequence[Mapping[str, Any]], axis: str) -> float:
    selected = [row for row in checks if row.get("axis") == axis]
    if not selected:
        return 100.0
    return round(sum(1 for row in selected if row.get("passed")) * 100.0 / len(selected), 2)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _audit_rows(connection: sqlite3.Connection, table: str, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, table):
        return []
    cols = _columns(connection, table)
    if "audit_id" not in cols:
        return []
    try:
        return [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM {table} WHERE audit_id=? ORDER BY rowid", (audit_id,)
            ).fetchall()
        ]
    except sqlite3.Error:
        return []


def _safe_relative_file(root: Path, reference: Any) -> Path | None:
    raw = str(reference or "").strip().replace("\\", "/").split("#", 1)[0]
    if not raw or "://" in raw:
        return None
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _artifact_integrity(database: Path, audit_id: str, catalog_id: str) -> tuple[bool, str]:
    from rasai import catalog_report_catalog_state as state

    root = database.parent
    checked = 0
    failures: list[str] = []
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        for table, _label in state._catalog_source_specs(catalog_id):
            cols = _columns(connection, table)
            if not cols:
                continue
            rows = _audit_rows(connection, table, audit_id)
            for ref_col, hash_col in _ARTIFACT_PAIRS:
                if ref_col not in cols or hash_col not in cols:
                    continue
                for row in rows:
                    ref = row.get(ref_col)
                    expected = str(row.get(hash_col) or "").strip().casefold()
                    if not ref:
                        continue
                    path = _safe_relative_file(root, ref)
                    if path is None:
                        failures.append(f"{table}.{ref_col}: referência fora do workspace")
                        continue
                    if not expected:
                        failures.append(f"{table}.{ref_col}: SHA-256 não persistido")
                        continue
                    checked += 1
                    if not path.is_file():
                        failures.append(f"{table}.{ref_col}: arquivo ausente")
                        continue
                    actual = sha256(path.read_bytes()).hexdigest().casefold()
                    if actual != expected:
                        failures.append(f"{table}.{ref_col}: SHA-256 divergente")
    finally:
        connection.close()
    if failures:
        return False, "; ".join(failures[:8])
    return True, f"{checked} artefato(s) com hash verificável; nenhuma divergência encontrada"


def _secret_free_configuration(data: Any) -> tuple[bool, str]:
    failures: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if _SECRET_KEY_RE.search(str(key)):
                    if child not in (None, "", "[REDACTED]", "***"):
                        failures.append(child_path)
                    continue
                walk(child, child_path)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(getattr(data, "configuration", {}), "configuration")
    for index, item in enumerate(getattr(data, "work_items", ())):
        raw = item.get("configuration")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if parsed is not None:
            walk(parsed, f"work_items[{index}].configuration")
    if failures:
        return False, "valor sensível persistido em: " + ", ".join(failures[:8])
    return True, "snapshot e work items sem valores de credenciais em chaves sensíveis"


def _credential_output_failures(body: str) -> list[str]:
    exposures = detect_secret_exposures(
        unescape(body),
        path="catalog-report.html",
        strict=True,
    )
    return ["padrão de credencial detectado no HTML"] if exposures else []


def _safe_output(body: str) -> tuple[bool, list[str]]:
    failures: list[str] = _credential_output_failures(body)
    if re.search(r"href=['\"]\s*javascript:", body, re.I):
        failures.append("href javascript: detectado")
    if re.search(r"href=['\"]\s*data:text/html", body, re.I):
        failures.append("data:text/html detectado")
    if _EVENT_HANDLER_RE.search(body):
        failures.append("event handler inline detectado no corpo projetado")
    for match in _EXTERNAL_LINK_RE.finditer(body):
        attrs = (match.group(1) + " " + match.group(2)).casefold()
        if "target='_blank'" not in attrs and 'target="_blank"' not in attrs:
            failures.append("link externo sem target=_blank")
            break
        if "noopener" not in attrs or "noreferrer" not in attrs:
            failures.append("link externo sem rel=noopener noreferrer")
            break
    return not failures, failures


def _applicable_config_markers(data: Any, catalog_id: str) -> tuple[str, ...]:
    markers = _SPECIFIC_CONFIG_MARKERS.get(catalog_id, ())
    if catalog_id != "CAT-05":
        return markers
    # Competitive controls are only applicable when they exist in the frozen Search work item.
    for item in getattr(data, "work_items", ()):
        if str(item.get("component") or "").upper() != "SEARCH_INTELLIGENCE":
            continue
        raw = item.get("configuration")
        try:
            cfg = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            cfg = {}
        if isinstance(cfg, Mapping) and any(
            key in cfg
            for key in (
                "competitive", "compare_content", "max_content_pages",
                "content_timeout_seconds", "content_max_bytes",
                "content_max_redirects", "ai_competitive", "ymyl_mode",
            )
        ):
            return markers
    return tuple(marker for marker in markers if marker in {"Termos de busca", "Localidade", "Profundidade desejada", "Dispositivo"})


def _read_only_guard_present() -> tuple[bool, str]:
    try:
        from rasai import catalog_report_site as site
        owner = site.materialize_catalog_report_site
    except ImportError:
        return False, "não foi possível inspecionar o owner da materialização"

    required = (
        "before=_source_fingerprint(database)",
        "after=_source_fingerprint(database)",
        "if before!=after",
        "if _source_fingerprint(database)!=after",
    )
    visited: set[int] = set()
    sources: list[str] = []
    current = owner
    while callable(current) and id(current) not in visited:
        visited.add(id(current))
        try:
            sources.append(inspect.getsource(current))
        except (OSError, TypeError):
            pass
        original = getattr(current, "_rasai_original", None)
        if not callable(original):
            break
        current = original

    combined = "\n".join(sources)
    missing = [marker for marker in required if marker not in combined]
    return (
        not missing,
        "fingerprint antes/depois e antes da promoção verificado na cadeia do materializador"
        if not missing
        else "guardas ausentes: " + ", ".join(missing),
    )


def assess_catalog(database: Path, data: Any, catalog_id: str, body: str) -> dict[str, Any]:
    from rasai import catalog_report_page as page

    selected = catalog_id in getattr(data, "selected", set())
    status, _tone, detail = page._catalog_status(database, data, catalog_id)
    config_rows = list(page._configuration_rows(data, catalog_id))
    sources = list(page._catalog_sources(database, data, catalog_id))
    plan_ok = bool(
        getattr(data, "configuration", None)
        and getattr(data, "config_hash", "")
        and getattr(data, "computed_hash", "")
        and data.config_hash == data.computed_hash
    )
    body_security_ok, body_security_failures = _safe_output(body)
    persisted_secret_ok, persisted_secret_detail = _secret_free_configuration(data)
    artifact_ok, artifact_detail = _artifact_integrity(database, data.audit_id, catalog_id)
    read_only_ok, read_only_detail = _read_only_guard_present()

    checks: list[dict[str, Any]] = []

    # Configurability means applicable human/runtime controls are frozen and inspectable,
    # not that every CAT must expose arbitrary knobs.
    checks.extend([
        _check("CFG_PLAN_HASH", "configurability", plan_ok, "snapshot de configuração íntegro" if plan_ok else "snapshot ausente ou hash divergente"),
        _check("CFG_SELECTION", "configurability", bool(getattr(data, "config_hash", "")), "seleção de catálogo persistida no plano"),
        _check("CFG_SECTION", "configurability", "Configuração efetiva" in body, "seção de configuração projetada"),
        _check(
            "CFG_ORIGINS",
            "configurability",
            bool(config_rows) and all(len(row) >= 3 and str(row[2] or "").strip() for row in config_rows),
            f"{len(config_rows)} controle(s) com origem declarada",
        ),
    ])
    markers = _applicable_config_markers(data, catalog_id)
    missing_markers = [marker for marker in markers if marker not in body]
    checks.append(_check(
        "CFG_APPLICABLE_CONTROLS",
        "configurability",
        not missing_markers,
        "controles aplicáveis expostos" if not missing_markers else "faltam: " + ", ".join(missing_markers),
    ))

    source_labels = [str(label) for _table, label, count in sources if int(count or 0) > 0]
    hidden_sources = [label for label in source_labels if label not in body]
    status_resolved = str(status or "").upper() not in {"", "INDETERMINADO"}

    checks.extend([
        _check("GOV_STATUS", "governance", status_resolved, f"estado funcional: {status or '-'}"),
        _check("GOV_EVIDENCE", "governance", "Evidências" in body, "superfície de provenance presente"),
        _check("GOV_TECHNICAL", "governance", "Detalhes técnicos" in body, "detalhes técnicos disponíveis sem dominar o primeiro plano"),
        _check("GOV_REMEDIATION", "governance", "Remediações" in body, "roteamento de remediação explícito"),
        _check("GOV_LIMITATION", "governance", bool(str(detail or "").strip()), "estado/limitação acompanhado de explicação"),
    ])

    checks.extend([
        _check("REL_STATUS_TRUTH", "reliability", status_resolved, "estado derivado de configuração/evidência persistida"),
        _check("REL_RESULTS", "reliability", "Resultados" in body, "resultado funcional projetado"),
        _check("REL_ANALYSIS", "reliability", "Análise" in body, "interpretação separada da evidência"),
        _check("REL_NO_FALLBACK", "reliability", "Superfície sem projeção específica disponível." not in body, "renderer específico disponível"),
        _check("REL_SOURCE_EXPOSURE", "reliability", not hidden_sources, "fontes persistidas expostas" if not hidden_sources else "fontes ocultas: " + ", ".join(hidden_sources)),
    ])

    checks.extend([
        _check("INT_CONFIG_HASH", "integrity", plan_ok, "hash do plano confere"),
        _check("INT_ARTIFACTS", "integrity", artifact_ok, artifact_detail),
        _check("INT_SOURCE_INVENTORY", "integrity", not hidden_sources, "inventário persistido/projetado reconciliado"),
        _check("INT_READ_ONLY_CONTRACT", "integrity", read_only_ok, read_only_detail),
    ])

    checks.extend([
        _check("SEC_PERSISTED_CONFIG", "security", persisted_secret_ok, persisted_secret_detail),
        _check("SEC_OUTPUT_SECRETS", "security", body_security_ok or not any("credencial" in row for row in body_security_failures), "; ".join(body_security_failures) or "nenhum padrão de credencial"),
        _check("SEC_JAVASCRIPT_URL", "security", not any("javascript:" in row for row in body_security_failures), "sem links javascript:"),
        _check("SEC_EXTERNAL_LINKS", "security", not any("link externo" in row for row in body_security_failures), "links externos endurecidos"),
        _check("SEC_INLINE_EVENTS", "security", not any("event handler" in row for row in body_security_failures), "sem handlers inline vindos da projeção"),
    ])

    checks.extend([
        _check("EXP_CONFIG", "exposure", "Configuração efetiva" in body, "configuração em primeiro plano"),
        _check("EXP_RESULTS", "exposure", "Resultados" in body, "resultados em primeiro plano"),
        _check("EXP_EVIDENCE", "exposure", "Evidências" in body, "evidências/provenance em primeiro plano"),
        _check("EXP_SOURCES", "exposure", not hidden_sources, f"{len(source_labels)} fonte(s) materializada(s) conciliada(s)"),
        _check("EXP_TECHNICAL", "exposure", "Detalhes técnicos" in body, "dados técnicos disponíveis sob demanda"),
    ])

    axes = {
        axis: _score(checks, axis)
        for axis in ("configurability", "governance", "exposure", "reliability", "integrity", "security")
    }
    maturity = round(sum(axes.values()) / len(axes), 2)
    high_assurance = min(axes["reliability"], axes["integrity"], axes["security"])
    eligible = (not selected) or (
        maturity >= CATALOG_MATURITY_MIN and high_assurance >= HIGH_ASSURANCE_MIN
    )
    return {
        "catalog_id": catalog_id,
        "selected": selected,
        "functional_status": status,
        "configurability": axes["configurability"],
        "governance": axes["governance"],
        "exposure": axes["exposure"],
        "reliability": axes["reliability"],
        "integrity": axes["integrity"],
        "security": axes["security"],
        "maturity": maturity,
        "high_assurance": high_assurance,
        "closure_eligible": eligible,
        "checks": checks,
    }


def assess_catalogs(database: Path, data: Any, bodies: Mapping[str, str]) -> dict[str, Any]:
    from rasai.audit_catalog import CATALOGS
    from rasai.catalog_report_contract import CATALOG_PAGE_BY_ID

    catalogs: list[dict[str, Any]] = []
    for catalog in CATALOGS:
        filename = CATALOG_PAGE_BY_ID[catalog.id].filename
        catalogs.append(assess_catalog(database, data, catalog.id, str(bodies.get(filename) or "")))

    selected = [row for row in catalogs if row["selected"]]
    if not selected:
        selected = catalogs

    def avg(key: str) -> float:
        return round(sum(float(row[key]) for row in selected) / len(selected), 2) if selected else 100.0

    global_scores = {
        "reliability": avg("reliability"),
        "integrity": avg("integrity"),
        "security": avg("security"),
        "maturity": avg("maturity"),
        "configurability": avg("configurability"),
        "governance": avg("governance"),
        "exposure": avg("exposure"),
    }
    per_catalog_target = all(
        (not row["selected"]) or float(row["maturity"]) >= CATALOG_MATURITY_MIN
        for row in catalogs
    )
    high_assurance_target = all(
        (not row["selected"])
        or min(float(row["reliability"]), float(row["integrity"]), float(row["security"])) >= HIGH_ASSURANCE_MIN
        for row in catalogs
    )
    catalog_filenames = {CATALOG_PAGE_BY_ID[catalog.id].filename for catalog in CATALOGS}
    transversal_secret_failures: dict[str, list[str]] = {}
    for filename, body in bodies.items():
        if filename in catalog_filenames:
            continue
        failures = _credential_output_failures(str(body or ""))
        if failures:
            transversal_secret_failures[str(filename)] = failures
    global_output_security_ok = not transversal_secret_failures

    closure_eligible = bool(
        per_catalog_target and high_assurance_target and global_output_security_ok
    )
    return {
        "metric_semantics": "deterministic structural-control coverage; not statistical probability",
        "thresholds": {
            "catalog_maturity_min": CATALOG_MATURITY_MIN,
            "reliability_integrity_security_min": HIGH_ASSURANCE_MIN,
        },
        "catalogs": catalogs,
        "global": global_scores,
        "per_catalog_target_met": per_catalog_target,
        "high_assurance_target_met": high_assurance_target,
        "global_output_security": {
            "passed": global_output_security_ok,
            "failures": transversal_secret_failures,
        },
        "closure_eligible": closure_eligible,
    }


def _pct(value: Any) -> str:
    return f"{float(value or 0):.2f}%"


def catalog_assurance_html(row: Mapping[str, Any]) -> str:
    if not row.get("selected"):
        return (
            "<section class='section' id='assurance'><h2>Confiabilidade e governança estrutural</h2>"
            "<div class='notice'>Catálogo não solicitado nesta AUD; os percentuais de encerramento não são aplicáveis.</div></section>"
        )
    gate = "ATENDE" if row.get("closure_eligible") else "PENDENTE"
    failed = [item for item in row.get("checks", ()) if not item.get("passed")]
    detail = ""
    if failed:
        detail = (
            "<details><summary>Controles pendentes</summary><div class='detail-body'><ul>"
            + "".join(
                f"<li><code>{escape(str(item.get('code')))}</code> - {escape(str(item.get('detail') or ''))}</li>"
                for item in failed
            )
            + "</ul></div></details>"
        )
    return (
        "<section class='section' id='assurance'><h2>Confiabilidade e governança estrutural</h2>"
        "<p class='muted'>Percentuais abaixo medem cobertura de controles verificáveis da auditoria e da projeção; "
        "não representam probabilidade estatística de uma observação externa estar correta.</p>"
        "<div class='metric-grid'>"
        f"<div class='metric'><small>Configurabilidade</small><strong>{_pct(row.get('configurability'))}</strong></div>"
        f"<div class='metric'><small>Governança</small><strong>{_pct(row.get('governance'))}</strong></div>"
        f"<div class='metric'><small>Exposição</small><strong>{_pct(row.get('exposure'))}</strong></div>"
        f"<div class='metric'><small>Confiabilidade</small><strong>{_pct(row.get('reliability'))}</strong></div>"
        f"<div class='metric'><small>Integridade</small><strong>{_pct(row.get('integrity'))}</strong></div>"
        f"<div class='metric'><small>Segurança</small><strong>{_pct(row.get('security'))}</strong></div>"
        f"<div class='metric'><small>Maturidade estrutural</small><strong>{_pct(row.get('maturity'))}</strong></div>"
        f"<div class='metric'><small>Gate de encerramento</small><strong>{gate}</strong></div>"
        "</div>" + detail + "</section>"
    )


def assurance_matrix_html(result: Mapping[str, Any]) -> str:
    rows = []
    for row in result.get("catalogs", ()):
        if not row.get("selected"):
            gate = "Não aplicável"
        else:
            gate = "ATENDE" if row.get("closure_eligible") else "PENDENTE"
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('catalog_id') or '-'))}</td>"
            f"<td>{_pct(row.get('configurability'))}</td>"
            f"<td>{_pct(row.get('governance'))}</td>"
            f"<td>{_pct(row.get('exposure'))}</td>"
            f"<td>{_pct(row.get('reliability'))}</td>"
            f"<td>{_pct(row.get('integrity'))}</td>"
            f"<td>{_pct(row.get('security'))}</td>"
            f"<td>{_pct(row.get('maturity'))}</td>"
            f"<td>{gate}</td>"
            "</tr>"
        )
    global_scores = result.get("global", {})
    close = "ELEGÍVEL" if result.get("closure_eligible") else "PENDENTE"
    global_output = result.get("global_output_security", {})
    global_output_gate = "ATENDE" if global_output.get("passed", True) else "PENDENTE"
    return (
        "<section class='section' id='assurance-matrix'><h2>Matriz de encerramento estrutural</h2>"
        "<p class='muted'>Meta: cada catálogo selecionado com maturidade ≥95,00% e cada eixo de "
        "confiabilidade, integridade e segurança ≥99,50%. Falhas externas legítimas não reduzem a nota "
        "quando são persistidas, classificadas e expostas corretamente.</p>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>CAT</th><th>Configurabilidade</th><th>Governança</th><th>Exposição</th>"
        "<th>Confiabilidade</th><th>Integridade</th><th>Segurança</th><th>Maturidade</th><th>Gate</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        "<div class='metric-grid'>"
        f"<div class='metric'><small>Confiabilidade global</small><strong>{_pct(global_scores.get('reliability'))}</strong></div>"
        f"<div class='metric'><small>Integridade global</small><strong>{_pct(global_scores.get('integrity'))}</strong></div>"
        f"<div class='metric'><small>Segurança global</small><strong>{_pct(global_scores.get('security'))}</strong></div>"
        f"<div class='metric'><small>Maturidade global</small><strong>{_pct(global_scores.get('maturity'))}</strong></div>"
        f"<div class='metric'><small>Segurança das páginas transversais</small><strong>{global_output_gate}</strong></div>"
        f"<div class='metric'><small>Encerramento estrutural</small><strong>{close}</strong></div>"
        "</div></section>"
    )


__all__ = [
    "CATALOG_MATURITY_MIN",
    "HIGH_ASSURANCE_MIN",
    "assess_catalog",
    "assess_catalogs",
    "catalog_assurance_html",
    "assurance_matrix_html",
]
