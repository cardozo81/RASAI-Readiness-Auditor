"""Shared report contracts, persisted-data model and low-level readers."""
from rasai.catalog_report_style import *  # noqa: F401,F403
_STATUS_SUCCESS = {"SUCCESS","COMPLETE","COMPLETED","READY","MEASURED","FINAL","CONSOLIDATED","AVAILABLE","GENERATED"}
_STATUS_FAILURE = {"FAILED_RETRYABLE","FAILED_PERMANENT","FAILED_FATAL","BLOCKED","ERROR","FAILURE","UNAVAILABLE","CONTRACT_ERROR"}
_STATUS_PENDING = {"PENDING","RUNNING","WAITING_FOR_DATA","REQUESTED_NOT_EXECUTED","PROCESSING","PARTIAL"}
_STATUS_NEUTRAL = {"DISABLED","NOT_APPLICABLE","NOT_REQUESTED","SKIPPED","ABSENT"}

_COMPONENT_LABELS = {
    "CORE_AUDIT":"Auditoria principal",
    "SEMANTIC_AI":"Análise semântica assistida por IA",
    "TECHNICAL_AI":"Remediação técnica assistida por IA",
    "CONTENT_REMEDIATION_AI":"Remediação de conteúdo assistida por IA",
    "WEB_PERFORMANCE":"Web Performance",
    "SYNTHETIC_APDEX":"Apdex de navegação",
    "EXPERIENCE_APDEX":"Apdex de experiência",
    "HTTP_ACQUISITION":"Aquisição HTTP",
    "RENDER_CAPTURE":"Captura renderizada",
    "CONTENT_EXTRACTION":"Extração de conteúdo",
    "IMPROVEMENT_INTELLIGENCE":"Análise profunda e melhorias",
    "SEARCH_INTELLIGENCE":"Search Intelligence",
}
_SERVICE_LABELS = {
    "PAGESPEED_INSIGHTS":"PageSpeed Insights",
    "pagespeed":"PageSpeed Insights",
    "crux":"Chrome UX Report (CrUX)",
    "w3c-validator":"Validador HTML W3C",
    "w3c-css-validator":"Validador CSS W3C",
    "mdn-observatory":"MDN HTTP Observatory",
    "web-platform-baseline":"Web Platform Baseline",
    "open-web-metrics":"Métricas abertas do navegador",
    "google-search-console":"Google Search Console",
    "derived-readiness":"Métricas derivadas de prontidão",
    "retrieval-metrics":"Métricas de recuperação",
}
_AI_PURPOSE_LABELS = {
    "M18-SEMANTIC-22-V1":("Análise semântica","CAT-03"),
    "M24-TECHNICAL-REMEDIATION-V2":("Remediação técnica de descoberta","CAT-09"),
    "M20-CONTENT-REMEDIATION-V3":("Remediação de conteúdo","CAT-09"),
    "IMPROVEMENT-INTELLIGENCE-001":("Análise profunda e melhorias","CAT-08"),
    "COMPETITIVE-AI-001":("Inteligência competitiva por IA","CAT-05"),
}
_AI_EXCHANGE_PURPOSES = {
    "SEMANTIC_ANALYSIS":"Análise semântica",
    "TECHNICAL_REMEDIATION":"Remediação técnica",
    "CONTENT_REMEDIATION":"Remediação de conteúdo",
    "IMPROVEMENT_INTELLIGENCE":"Análise profunda e melhorias",
}
_DOMAIN_CATALOG = {
    "ACCESSIBILITY":"CAT-02",
    "PERFORMANCE":"CAT-04",
    "SEMANTICS_STRUCTURE":"CAT-03",
    "CONTENT":"CAT-03",
    "SEARCH_RANKING":"CAT-05",
    "FILES_DISCOVERY":"CAT-01",
    "TECHNICAL_HTML":"CAT-01",
    "BEST_PRACTICES":"CAT-01",
    "SECURITY":"CAT-01",
    "AI_ACCESS":"CAT-01",
}
_DIMENSION_CONTEXT = {
    "DISCOVERY_ACCESS":"CAT-01","TECHNICAL_ACCESSIBILITY":"CAT-01","INDEXABILITY":"CAT-01",
    "CONTENT_EXTRACTABILITY":"CAT-01","SEMANTIC_STRUCTURE":"CAT-03","ENTITY_CLARITY":"CAT-03",
    "STRUCTURED_DATA":"CAT-03","ANSWERABILITY":"CAT-03","CITATION_READINESS":"CAT-03",
    "EVIDENCE_TRUST":"CAT-03","INTENT_COVERAGE":"CAT-03","CONTENT_VALUE":"CAT-03",
}
_DIMENSION_LABELS = {
    "OVERALL_READINESS":"SARI · Search & AI Readiness","DISCOVERY_ACCESS":"Acesso e descoberta",
    "TECHNICAL_ACCESSIBILITY":"Acessibilidade técnica","INDEXABILITY":"Indexabilidade e canonicalização",
    "CONTENT_EXTRACTABILITY":"Renderização e extração","SEMANTIC_STRUCTURE":"Estrutura semântica",
    "ENTITY_CLARITY":"Clareza de entidades","STRUCTURED_DATA":"Dados estruturados",
    "ANSWERABILITY":"Capacidade de resposta","CITATION_READINESS":"Preparação para citação",
    "EVIDENCE_TRUST":"Evidência e confiança","INTENT_COVERAGE":"Cobertura de intenção",
    "CONTENT_VALUE":"Valor de conteúdo",
}
_WEB_METRICS = (
    ("performance_score","Lighthouse Performance","índice"),
    ("accessibility_score","Lighthouse Accessibility","índice"),
    ("best_practices_score","Lighthouse Best Practices","índice"),
    ("seo_score","Lighthouse SEO","índice"),
    ("agentic_browsing_score","Lighthouse · Navegação por agentes","índice"),
    ("fcp_lab_ms","FCP de laboratório","ms"),("speed_index_lab_ms","Speed Index","ms"),
    ("lcp_lab_ms","LCP de laboratório","ms"),("tbt_lab_ms","Total Blocking Time","ms"),
    ("cls_lab","CLS de laboratório",""),("lcp_ms","LCP","ms"),("inp_ms","INP","ms"),("cls","CLS",""),("ttfb_ms","TTFB","ms"),("lcp_p75_ms","LCP de campo (p75)","ms"),
    ("inp_p75_ms","INP de campo (p75)","ms"),("cls_p75","CLS de campo (p75)",""),
)
_SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|authorization|bearer|token|secret|password|passwd|cookie|client[_-]?secret)", re.I)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_APIKEY_RE = re.compile(r"(?i)\b(?:sk|key|token)[-_][A-Za-z0-9._-]{12,}")

_LIGHTHOUSE_A11Y_LABELS = {
    "aria-allowed-attr":"Atributos ARIA não permitidos para o papel informado",
    "aria-required-children":"Estrutura ARIA sem todos os elementos filhos obrigatórios",
    "aria-required-attr":"Papel ARIA sem todos os atributos obrigatórios",
    "aria-dialog-name":"Janela de diálogo sem nome acessível",
    "heading-order":"Hierarquia de títulos fora de sequência",
    "image-alt":"Imagem sem texto alternativo",
    "link-name":"Link sem nome acessível",
    "button-name":"Botão sem nome acessível",
    "color-contrast":"Contraste de cores insuficiente",
    "label":"Campo de formulário sem rótulo acessível",
    "html-has-lang":"Documento sem idioma principal declarado",
    "html-lang-valid":"Idioma declarado no documento não é válido",
}

_STRUCTURED_RULE_LABELS = {
    "BR-GEO-034":"JSON-LD sintaticamente interpretável",
    "BR-GEO-035":"Tipos e propriedades de dados estruturados identificáveis",
    "BR-GEO-036":"Consistência entre dados estruturados e conteúdo visível",
    "BR-GEO-037":"Consistência entre entidades do JSON-LD e da página",
}


class _Html(str):
    pass


@dataclass(slots=True)
class _ReportData:
    audit_id: str
    audit: dict[str, Any]
    configuration: dict[str, Any]
    config_hash: str
    computed_hash: str
    selected: set[str]
    catalog_items: dict[str, dict[str, Any]]
    tables: set[str]
    scores: list[dict[str, Any]]
    work_items: list[dict[str, Any]]
    fulfillment: dict[str, Any]
    targets: tuple[str, ...]


def _plain(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+","_",str(value or "").upper()).strip("_")


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _rows(connection: sqlite3.Connection, sql: str, params: Sequence[Any]=()) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql,tuple(params)).fetchall())
    except sqlite3.Error:
        return []


def _dict_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _audit_rows(connection: sqlite3.Connection, table: str, audit_id: str, *, order: str="rowid") -> list[dict[str, Any]]:
    if not _table_exists(connection, table):
        return []
    cols = _columns(connection, table)
    if "audit_id" in cols:
        suffix = f" ORDER BY {order}" if order else ""
        return _dict_rows(_rows(connection,f"SELECT * FROM {table} WHERE audit_id=?{suffix}",(audit_id,)))
    if table in {"entity_observations","semantic_assessments"} and {"snapshot_id"}.issubset(cols) and _table_exists(connection,"page_snapshots") and _table_exists(connection,"pages"):
        return _dict_rows(_rows(connection,f"""SELECT t.* FROM {table} t
            JOIN page_snapshots ps ON ps.snapshot_id=t.snapshot_id
            JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=? ORDER BY t.rowid""",(audit_id,)))
    return []


def _audit_count(connection: sqlite3.Connection, table: str, audit_id: str) -> int:
    return len(_audit_rows(connection,table,audit_id))


def _first(connection: sqlite3.Connection, table: str, audit_id: str) -> dict[str, Any]:
    rows = _audit_rows(connection,table,audit_id)
    return rows[0] if rows else {}


def _last(connection: sqlite3.Connection, table: str, audit_id: str) -> dict[str, Any]:
    rows = _audit_rows(connection,table,audit_id)
    return rows[-1] if rows else {}


def _load_configuration(connection: sqlite3.Connection, audit_id: str) -> tuple[dict[str, Any],str,str]:
    if not _table_exists(connection,"audit_execution_configurations"):
        return {}, "", ""
    cols = _columns(connection,"audit_execution_configurations")
    if "configuration_json" not in cols:
        return {}, "", ""
    hash_col = "configuration_hash" if "configuration_hash" in cols else "'' AS configuration_hash"
    rows = _rows(connection,f"SELECT configuration_json,{hash_col} FROM audit_execution_configurations WHERE audit_id=? LIMIT 1",(audit_id,))
    if not rows:
        return {}, "", ""
    parsed = _safe_json(rows[0]["configuration_json"],{})
    configuration = dict(parsed) if isinstance(parsed,Mapping) else {}
    persisted = str(rows[0]["configuration_hash"] or "")
    computed = configuration_hash(configuration) if configuration else ""
    return configuration,persisted,computed


def _targets(connection: sqlite3.Connection, configuration: Mapping[str, Any], audit_id: str) -> tuple[str,...]:
    raw = configuration.get("targets")
    if isinstance(raw,list):
        values = tuple(str(v).strip() for v in raw if str(v).strip())
        if values:
            return values
    if _table_exists(connection,"pages") and "audit_id" in _columns(connection,"pages"):
        cols = _columns(connection,"pages")
        col = "normalized_url" if "normalized_url" in cols else "url" if "url" in cols else None
        if col:
            values = tuple(str(r[0]).strip() for r in _rows(connection,f"SELECT {col} FROM pages WHERE audit_id=?",(audit_id,)) if r[0])
            return tuple(dict.fromkeys(values))
    return ()


def _load_data(audit_id: str, database: Path) -> _ReportData:
    connection=sqlite3.connect(database); connection.row_factory=sqlite3.Row
    try:
        tables={str(r[0]) for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        configuration,persisted,computed=_load_configuration(connection,audit_id)
        block=configuration.get("audit_catalog") if isinstance(configuration.get("audit_catalog"),Mapping) else {}
        selected={str(v).strip().upper() for v in block.get("selected",[]) if str(v).strip()} if isinstance(block,Mapping) else set()
        raw_items=block.get("items",[]) if isinstance(block,Mapping) else []
        items={}
        for item in raw_items:
            if not isinstance(item,Mapping):
                continue
            key=str(item.get("id") or item.get("catalog_id") or "").strip().upper()
            if key:
                items[key]=dict(item)
        audit_rows=_audit_rows(connection,"audits",audit_id)
        scores=_audit_rows(connection,"scores",audit_id)
        work=_audit_rows(connection,"audit_fulfillment_work_items",audit_id)
        fulfillment=_last(connection,"audit_fulfillment_contracts",audit_id)
        return _ReportData(audit_id, audit_rows[0] if audit_rows else {}, configuration,persisted,computed,selected,items,tables,scores,work,fulfillment,_targets(connection,configuration,audit_id))
    finally:
        connection.close()



def _ai_attempts(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:
        attempts=[]
        for table,contract_field in (("ai_provider_attempts","semantic_contract_version"),("content_remediation_attempts","contract_version")):
            for r in _audit_rows(con,table,audit_id):
                d=dict(r); contract=str(d.get(contract_field) or "")
                purpose,catalog=_AI_PURPOSE_LABELS.get(contract.upper(),(contract or "Chamada de IA",""))
                d["_source_table"]=table;d["purpose"]=purpose;d["catalog_id"]=catalog;d["contract"]=contract
                attempts.append(d)
        attempts.sort(key=lambda r:str(r.get("started_at") or ""))
        return attempts
    finally:con.close()



__all__ = [name for name in globals() if not name.startswith("__")]
