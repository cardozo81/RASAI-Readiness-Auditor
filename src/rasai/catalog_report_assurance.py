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
_NON_SECRET_CONFIGURATION_KEYS = frozenset({
    # Feature toggle: controls whether Set-Cookie attributes are analyzed. It never
    # contains a cookie header/value and must not be classified as credential material.
    "RASAI_SECURITY_COOKIES",
})
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
    "CAT-10": (
        "Segurança passiva",
        "Headers / CSP / CORS",
        "Cookies",
        "Scripts / recursos",
        "Recursos de terceiros",
        "Correlação em tempo de execução",
        "OSV",
        "CISA KEV",
        "Timeout externo",
        "MDN HTTP Observatory",
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
    if checked == 0:
        return True, "nenhum artefato-fonte com par referência + SHA-256 persistido neste catálogo; verificação de hash não aplicável"
    return True, f"{checked} artefato(s) com hash verificável; nenhuma divergência encontrada"


def _catalog_referential_integrity(
    database: Path,
    audit_id: str,
    catalog_id: str,
) -> tuple[bool, str]:
    """Validate persisted FK integrity only for audit-owned sources of this catalog."""
    from rasai import catalog_report_catalog_state as state

    failures: list[str] = []
    checked_tables = 0
    connection = sqlite3.connect(database)
    try:
        for table, _label in state._catalog_source_specs(catalog_id):
            columns = _columns(connection, table)
            if "audit_id" not in columns:
                continue
            checked_tables += 1
            try:
                violations = connection.execute(
                    f'PRAGMA foreign_key_check("{table}")'
                ).fetchall()
            except sqlite3.Error as exc:
                failures.append(
                    f"{table}: validação de FK indisponível ({exc.__class__.__name__})"
                )
                continue
            for violation in violations:
                rowid = violation[1]
                if rowid is None:
                    continue
                owner = connection.execute(
                    f'SELECT audit_id FROM "{table}" WHERE rowid=?',
                    (rowid,),
                ).fetchone()
                if owner is None or str(owner[0]) != audit_id:
                    continue
                failures.append(
                    f"{table}[rowid={rowid}] -> {violation[2]}"
                )
    finally:
        connection.close()

    if failures:
        return False, (
            f"{len(failures)} violação(ões) de integridade referencial nas fontes do catálogo: "
            + "; ".join(failures[:8])
        )
    return True, f"FKs verificadas em {checked_tables} tabela(s) audit-owned; nenhuma violação encontrada"


def _secret_free_configuration(data: Any) -> tuple[bool, str]:
    failures: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                normalized_key = str(key).strip().upper()
                if normalized_key not in _NON_SECRET_CONFIGURATION_KEYS and _SECRET_KEY_RE.search(str(key)):
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
    return True, "snapshot e itens de trabalho sem valores de credenciais em chaves sensíveis"


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


_INTERNAL_FAILURE_CLASSES = frozenset({"ORCHESTRATION", "INTERNAL", "PERSISTENCE"})
_INTERNAL_FAILURE_CODES = frozenset({
    "REQUESTED_NOT_EXECUTED",
    "CONTENT_REMEDIATION_EXECUTION_FAILURE",
})


_CANONICAL_RUN_TABLES = {
    "CAT-04": "web_performance_runs",
    "CAT-06": "synthetic_apdex_runs",
    "CAT-07": "synthetic_ux_apdex_runs",
    "CAT-08": "improvement_intelligence_runs",
    "CAT-09": "content_remediation_runs",
    "CAT-10": "passive_security_runs",
}


def _canonical_run_materialized(
    database: Path,
    audit_id: str,
    catalog_id: str,
) -> tuple[bool, str]:
    """Verify that selected execution-owning catalogs materialized their canonical run."""
    table = _CANONICAL_RUN_TABLES.get(catalog_id)
    if table is None:
        return True, "catálogo não exige tabela canônica de execução"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = _audit_rows(connection, table, audit_id)
    finally:
        connection.close()
    if rows:
        return True, f"execução canônica persistida em {table}"
    return False, f"execução canônica ausente em {table}"


def _internal_execution_gaps(data: Any, catalog_id: str) -> tuple[str, ...]:
    try:
        from rasai import catalog_report_page as page
        work = page._catalog_work(data, catalog_id)
    except Exception:
        work = []
    failures: list[str] = []
    for row in work:
        status = str(row.get("status") or "").upper()
        error_class = str(row.get("last_error_class") or "").upper()
        error_code = str(row.get("last_error_code") or "").upper()
        if (
            status == "REQUESTED_NOT_EXECUTED"
            or error_class in _INTERNAL_FAILURE_CLASSES
            or error_code in _INTERNAL_FAILURE_CODES
            or error_code.endswith("_EXECUTION_FAILURE")
        ):
            component = str(row.get("component") or "UNKNOWN")
            failures.append(f"{component}:{status or '-'}:{error_code or error_class or '-'}")
    return tuple(failures)


def _ai_attempt_provenance(
    database: Path,
    audit_id: str,
    catalog_id: str,
) -> tuple[bool, str]:
    table = None
    contract_column = None
    contract_prefix = None
    if catalog_id == "CAT-03":
        table = "ai_provider_attempts"
        contract_column = "semantic_contract_version"
        contract_prefix = "M18-SEMANTIC"
    elif catalog_id == "CAT-08":
        table = "ai_provider_attempts"
        contract_column = "semantic_contract_version"
        contract_prefix = "IMPROVEMENT-INTELLIGENCE"
    elif catalog_id == "CAT-09":
        table = "content_remediation_attempts"
        contract_column = "contract_version"
        contract_prefix = "M20-CONTENT-REMEDIATION"
    else:
        return True, "provenance de tentativa de IA não aplicável a este catálogo"

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, table):
            return True, "nenhuma tentativa aplicável persistida"
        columns = _columns(connection, table)
        required = {"operation", "ai_task_id", "ai_round_id", contract_column}
        if not required.issubset(columns):
            return False, "schema de tentativa sem campos de provenance task/round"
        rows = connection.execute(
            f"""SELECT operation,ai_task_id,ai_round_id
                FROM {table}
                WHERE audit_id=? AND UPPER(COALESCE({contract_column},'')) LIKE ?""",
            (audit_id, contract_prefix + "%"),
        ).fetchall()
        if not rows:
            return True, "nenhuma tentativa aplicável persistida"
        missing = [
            row for row in rows
            if not str(row["operation"] or "").strip()
            or not str(row["ai_task_id"] or "").strip()
            or not str(row["ai_round_id"] or "").strip()
        ]
        if missing:
            return False, f"{len(missing)}/{len(rows)} tentativa(s) sem operation/task/round"
        if not (_table_exists(connection, "ai_tasks") and _table_exists(connection, "ai_request_rounds")):
            return False, "task/round referenciados sem tabelas de governança"
        broken = 0
        for row in rows:
            task = connection.execute(
                "SELECT 1 FROM ai_tasks WHERE ai_task_id=? AND audit_id=?",
                (row["ai_task_id"], audit_id),
            ).fetchone()
            round_row = connection.execute(
                "SELECT 1 FROM ai_request_rounds WHERE ai_round_id=? AND ai_task_id=?",
                (row["ai_round_id"], row["ai_task_id"]),
            ).fetchone()
            if task is None or round_row is None:
                broken += 1
        if broken:
            return False, f"{broken}/{len(rows)} tentativa(s) com referência task/round órfã"
        return True, f"{len(rows)} tentativa(s) com provenance operation/task/round íntegra"
    finally:
        connection.close()


def _external_metrics_artifact_freshness(database: Path, audit_id: str) -> tuple[bool, str]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not (_table_exists(connection, "web_performance_runs") and _table_exists(connection, "web_performance_observations")):
            return True, "integridade externa não aplicável: M21 ausente"
        run = connection.execute("SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,)).fetchone()
        if run is None or not bool(run["enabled"]):
            return True, "integridade externa não aplicável: M21 não habilitado"
        observations = connection.execute(
            "SELECT * FROM web_performance_observations WHERE audit_id=? ORDER BY observation_id",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()

    artifact = database.parent / "artifacts" / "external-metrics-integrity.json"
    if not artifact.is_file():
        return False, "external-metrics-integrity.json ausente para M21 habilitado"
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "external-metrics-integrity.json inválido"
    if not isinstance(payload, Mapping) or str(payload.get("audit_id") or "") != audit_id:
        return False, "external-metrics-integrity.json pertence a outra AUD ou possui schema inválido"
    raw_contexts = payload.get("contexts")
    if not isinstance(raw_contexts, list):
        return False, "external-metrics-integrity.json sem contexts"
    contexts = {
        str(item.get("observation_id") or ""): item
        for item in raw_contexts
        if isinstance(item, Mapping) and str(item.get("observation_id") or "")
    }
    expected_ids = {str(row["observation_id"]) for row in observations}
    if set(contexts) != expected_ids:
        missing = len(expected_ids - set(contexts))
        stale = len(set(contexts) - expected_ids)
        return False, f"artifact de métricas externas fora do estado final: ausentes={missing}; obsoletos={stale}"
    mismatches = 0
    for row in observations:
        item = contexts[str(row["observation_id"])]
        expected_http = int(row["pagespeed_http_status"]) if row["pagespeed_http_status"] is not None else None
        observed_http = item.get("pagespeed_http_status")
        try:
            observed_http = int(observed_http) if observed_http is not None else None
        except (TypeError, ValueError):
            observed_http = None
        if (
            str(item.get("pagespeed_artifact") or "") != str(row["pagespeed_artifact_reference"] or "")
            or observed_http != expected_http
            or str(item.get("resulting_observation_status") or "") != str(row["status"] or "")
            or str(item.get("url") or "") != str(row["url"] or "")
            or str(item.get("device") or "") != str(row["device"] or "")
        ):
            mismatches += 1
    if mismatches:
        return False, f"{mismatches}/{len(observations)} contexto(s) divergente(s) entre M21 e artifact de integridade"
    return True, f"{len(observations)} contexto(s) M21 reconciliado(s) com external-metrics-integrity.json"


def _rpr_ai_override_provenance(database: Path, audit_id: str, catalog_id: str) -> tuple[bool, str]:
    if catalog_id != "CAT-08":
        return True, "override de IA no RPR não aplicável a este catálogo"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        required_tables = {"audit_reprocess_runs", "audit_fulfillment_attempts", "audit_fulfillment_work_items"}
        if not all(_table_exists(connection, name) for name in required_tables):
            return True, "nenhum ledger RPR aplicável ao CAT-08"
        runs = connection.execute(
            """SELECT DISTINCT r.*
               FROM audit_reprocess_runs r
               JOIN audit_fulfillment_attempts a ON a.reprocess_id=r.reprocess_id AND a.audit_id=r.audit_id
               JOIN audit_fulfillment_work_items w ON w.work_item_id=a.work_item_id AND w.audit_id=r.audit_id
               WHERE r.audit_id=? AND r.completed_at IS NOT NULL
                 AND UPPER(COALESCE(w.component,''))='IMPROVEMENT_INTELLIGENCE'
               ORDER BY r.started_at,r.rowid""",
            (audit_id,),
        ).fetchall()
        if not runs:
            return True, "nenhum RPR do CAT-08 persistido"
        if not _table_exists(connection, "ai_provider_attempts"):
            for run in runs:
                try:
                    cfg = json.loads(str(run["configuration"] or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    cfg = {}
                if isinstance(cfg, Mapping) and cfg.get("ai_used") is True:
                    return False, f"{run['reprocess_id']}: ledger declara ai_used sem ai_provider_attempts"
            return True, f"{len(runs)} RPR(s) CAT-08 sem execução de IA declarada"
        columns = _columns(connection, "ai_provider_attempts")
        if not {"semantic_contract_version", "started_at"}.issubset(columns):
            return False, "ai_provider_attempts sem contrato/tempo necessários para reconciliar o RPR"
        failures: list[str] = []
        reconciled = 0
        for run in runs:
            try:
                cfg = json.loads(str(run["configuration"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                cfg = {}
            declared = isinstance(cfg, Mapping) and cfg.get("ai_used") is True
            params: list[Any] = [audit_id, str(run["started_at"] or ""), str(run["completed_at"] or "")]
            operation_filter = ""
            if "operation" in columns:
                operation_filter = " AND UPPER(COALESCE(operation,''))='IMPROVEMENT_INTELLIGENCE'"
            attempt = connection.execute(
                """SELECT 1 FROM ai_provider_attempts
                   WHERE audit_id=? AND started_at>=? AND started_at<=?
                     AND UPPER(COALESCE(semantic_contract_version,'')) LIKE 'IMPROVEMENT-INTELLIGENCE%'"""
                + operation_filter + " LIMIT 1",
                tuple(params),
            ).fetchone()
            observed = attempt is not None
            if declared != observed:
                failures.append(f"{run['reprocess_id']}: ai_used={declared} versus tentativa_CAT08={observed}")
            elif observed:
                reconciled += 1
        if failures:
            return False, "; ".join(failures)
        return True, f"{len(runs)} RPR(s) CAT-08 reconciliado(s); {reconciled} com IA efetivamente executada"
    finally:
        connection.close()


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
    referential_ok, referential_detail = _catalog_referential_integrity(
        database,
        data.audit_id,
        catalog_id,
    )
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

    internal_gaps = _internal_execution_gaps(data, catalog_id)
    canonical_run_ok, canonical_run_detail = _canonical_run_materialized(
        database,
        data.audit_id,
        catalog_id,
    )
    canonical_run_ok = (not selected) or canonical_run_ok
    provenance_ok, provenance_detail = _ai_attempt_provenance(
        database,
        data.audit_id,
        catalog_id,
    )
    external_integrity_ok, external_integrity_detail = (
        _external_metrics_artifact_freshness(database, data.audit_id)
        if catalog_id == "CAT-04"
        else (True, "integridade externa não aplicável a este catálogo")
    )
    rpr_ai_ok, rpr_ai_detail = _rpr_ai_override_provenance(
        database,
        data.audit_id,
        catalog_id,
    )

    checks.extend([
        _check("GOV_INTERNAL_EXECUTION", "governance", not internal_gaps, "sem falha interna de orquestração/persistência" if not internal_gaps else "; ".join(internal_gaps)),
        _check("GOV_CANONICAL_RUN", "governance", canonical_run_ok, canonical_run_detail),
        _check("GOV_AI_ATTEMPT_PROVENANCE", "governance", provenance_ok, provenance_detail),
        _check("GOV_RPR_AI_OVERRIDE_PROVENANCE", "governance", rpr_ai_ok, rpr_ai_detail),
        _check("GOV_STATUS", "governance", status_resolved, f"estado funcional: {status or '-'}"),
        _check("GOV_EVIDENCE", "governance", "Evidências" in body, "superfície de provenance presente"),
        _check("GOV_TECHNICAL", "governance", "Detalhes técnicos" in body, "detalhes técnicos disponíveis sem dominar o primeiro plano"),
        _check("GOV_REMEDIATION", "governance", "Remediações" in body, "roteamento de remediação explícito"),
        _check("GOV_LIMITATION", "governance", bool(str(detail or "").strip()), "estado/limitação acompanhado de explicação"),
    ])

    checks.extend([
        _check("REL_INTERNAL_EXECUTION", "reliability", not internal_gaps, "execução interna sem lacuna estrutural conhecida" if not internal_gaps else "; ".join(internal_gaps)),
        _check("REL_CANONICAL_RUN", "reliability", canonical_run_ok, canonical_run_detail),
        _check("REL_STATUS_TRUTH", "reliability", status_resolved, "estado derivado de configuração/evidência persistida"),
        _check("REL_RESULTS", "reliability", "Resultados" in body, "resultado funcional projetado"),
        _check("REL_ANALYSIS", "reliability", "Análise" in body, "interpretação separada da evidência"),
        _check("REL_NO_FALLBACK", "reliability", "Superfície sem projeção específica disponível." not in body, "renderer específico disponível"),
        _check("REL_SOURCE_EXPOSURE", "reliability", not hidden_sources, "fontes persistidas expostas" if not hidden_sources else "fontes ocultas: " + ", ".join(hidden_sources)),
    ])

    checks.extend([
        _check("INT_AI_ATTEMPT_PROVENANCE", "integrity", provenance_ok, provenance_detail),
        _check("INT_RPR_AI_OVERRIDE_PROVENANCE", "integrity", rpr_ai_ok, rpr_ai_detail),
        _check("INT_DERIVED_ARTIFACT_FRESHNESS", "integrity", external_integrity_ok, external_integrity_detail),
        _check("INT_CONFIG_HASH", "integrity", plan_ok, "hash do plano confere"),
        _check("INT_REFERENTIAL_INTEGRITY", "integrity", referential_ok, referential_detail),
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
            gate = "ATENDE ESTRUTURA" if row.get("closure_eligible") else "PENDENTE"
        functional_status = escape(str(row.get("functional_status") or "NÃO DETERMINADO"))
        rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('catalog_id') or '-'))}</td>"
            f"<td>{functional_status}</td>"
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
    package_integrity = result.get("package_integrity", {}) if isinstance(result.get("package_integrity"), Mapping) else {}
    snapshot_gate = "ATENDE" if package_integrity.get("final_source_snapshot_match", True) else "PENDENTE"
    catalog_gate = "ATENDE" if all(
        (not row.get("selected")) or bool(row.get("closure_eligible"))
        for row in result.get("catalogs", ())
    ) else "PENDENTE"
    return (
        "<section class='section' id='assurance-matrix'><h2>Matriz de encerramento estrutural</h2>"
        "<p class='muted'>Meta: cada catálogo selecionado com maturidade ≥95,00% e cada eixo de "
        "confiabilidade, integridade e segurança ≥99,50%. Falhas externas legítimas não reduzem a nota "
        "quando são persistidas, classificadas e expostas corretamente. Este encerramento é estrutural: "
        "não equivale ao fechamento diagnóstico integral, que permanece pendente enquanto houver requisito "
        "funcional obrigatório não concluído.</p>"
        "<div class='notice'><strong>Como ler os eixos:</strong> "
        "<strong>CAT</strong> identifica o catálogo avaliado; "
        "<strong>Estado funcional</strong> mostra o resultado real da execução e permanece independente do assurance estrutural; "
        "<strong>Configurabilidade</strong> mede se os controles humanos/runtime aplicáveis foram congelados e expostos; "
        "<strong>Governança</strong> verifica estado, evidência, limitações e remediação com provenance; "
        "<strong>Exposição</strong> verifica se configuração, resultados, fontes e detalhes estão visíveis ao usuário; "
        "<strong>Confiabilidade</strong> confronta estado e resultado publicado com a evidência persistida sem fallback inventado; "
        "<strong>Integridade</strong> verifica hashes quando existe checksum persistido, integridade referencial, freshness dos artefatos derivados, inventário de fontes e contrato read-only; o gate final ainda exige igualdade lógica entre audit.db e o snapshot SQLite entregue; 100% não significa que todo artefato-fonte possua checksum persistido; "
        "<strong>Segurança</strong> verifica ausência de credenciais e padrões inseguros na projeção; "
        "<strong>Maturidade</strong> é a média determinística da cobertura desses eixos; "
        "<strong>Gate estrutural</strong> indica somente se o catálogo atingiu os thresholds estruturais de encerramento. "
        "Falhas externas legítimas, quando corretamente registradas e expostas, não reduzem por si só a cobertura; "
        "falhas internas de orquestração/persistência e perda de provenance reduzem os eixos correspondentes. "
        "Esses percentuais medem cobertura de controles, não probabilidade estatística de o conteúdo auditado estar correto.</div>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>CAT</th><th>Estado funcional</th><th>Configurabilidade</th><th>Governança</th><th>Exposição</th>"
        "<th>Confiabilidade</th><th>Integridade</th><th>Segurança</th><th>Maturidade</th><th>Gate estrutural</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        "<h3>Cobertura global dos eixos</h3>"
        "<p class='muted'>Os totalizadores abaixo seguem a mesma ordem e a mesma unidade percentual das colunas estruturais da matriz.</p>"
        "<div class='metric-grid' data-assurance-summary='coverage'>"
        f"<div class='metric'><small>Configurabilidade global</small><strong>{_pct(global_scores.get('configurability'))}</strong></div>"
        f"<div class='metric'><small>Governança global</small><strong>{_pct(global_scores.get('governance'))}</strong></div>"
        f"<div class='metric'><small>Exposição global</small><strong>{_pct(global_scores.get('exposure'))}</strong></div>"
        f"<div class='metric'><small>Confiabilidade global</small><strong>{_pct(global_scores.get('reliability'))}</strong></div>"
        f"<div class='metric'><small>Integridade global</small><strong>{_pct(global_scores.get('integrity'))}</strong></div>"
        f"<div class='metric'><small>Segurança global</small><strong>{_pct(global_scores.get('security'))}</strong></div>"
        f"<div class='metric'><small>Maturidade global</small><strong>{_pct(global_scores.get('maturity'))}</strong></div>"
        "</div>"
        "<h3>Estados de encerramento</h3>"
        "<p class='muted'>Estados de gate são qualitativos e ficam separados das métricas percentuais de cobertura.</p>"
        "<div class='metric-grid' data-assurance-summary='gates'>"
        f"<div class='metric'><small>Gate dos catálogos</small><strong>{catalog_gate}</strong></div>"
        f"<div class='metric'><small>Segurança das páginas transversais</small><strong>{global_output_gate}</strong></div>"
        f"<div class='metric'><small>Snapshot final da fonte</small><strong>{snapshot_gate}</strong></div>"
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
