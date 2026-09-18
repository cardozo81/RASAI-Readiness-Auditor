"""Web, Apdex and search metric projections."""
from rasai.catalog_report_catalog_state import *  # noqa: F401,F403

def _web_observation(database: Path, audit_id: str) -> dict[str,Any]:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:return _last(con,"web_performance_observations",audit_id)
    finally:con.close()


def _fmt_number(value: Any, unit: str="") -> str:
    if value is None:return "-"
    try:n=float(value)
    except (TypeError,ValueError):return str(value)
    if unit=="ms":return f"{n:,.0f} ms".replace(","," ")
    if unit=="percent":return f"{n:.1f}%"
    if n.is_integer():return str(int(n))
    return f"{n:.3f}".rstrip("0").rstrip(".")


def _web_metric_rows(database: Path, audit_id: str) -> list[Sequence[Any]]:
    row=_web_observation(database,audit_id); out=[]
    for field,label,unit in _WEB_METRICS:
        if field not in row or row[field] is None:continue
        value=row[field]
        if field.endswith("_score"):
            try:
                n=float(value); value=f"{n*100:.0f} / 100" if 0<=n<=1 else f"{n:.0f} / 100"
            except (TypeError,ValueError):value=str(value)
        else:value=_fmt_number(value,unit)
        out.append((label,value,"Medição persistida"))
    if row.get("cwv_assessment"):
        out.append(("Core Web Vitals",str(row["cwv_assessment"]).replace("_"," ").title(),"Dados de campo"))
    return out


def _apdex_summary(database: Path, audit_id: str, *, experience: bool) -> dict[str,Any]:
    table="synthetic_ux_apdex_summaries" if experience else "synthetic_apdex_summaries"
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        rows=_audit_rows(con,table,audit_id)
        if experience:
            for row in rows:
                if _norm(row.get("device"))=="POPULATION":return row
        return rows[-1] if rows else {}
    finally:con.close()


def _apdex_result_rows(database: Path, audit_id: str, *, experience: bool) -> list[Sequence[Any]]:
    row=_apdex_summary(database,audit_id,experience=experience)
    if not row:return []
    score=row.get("apdex_score",row.get("apdex"))
    rows=[
        ("Apdex",_fmt_number(score),"Índice"),
        ("Amostras válidas",row.get("valid_samples",row.get("sample_count","-")),"Contagem"),
        ("Satisfatórias",row.get("satisfied_count","-"),"Contagem"),
        ("Toleráveis",row.get("tolerating_count","-"),"Contagem"),
        ("Frustradas",row.get("frustrated_count","-"),"Contagem"),
    ]
    if experience:
        rows.extend([
            ("Frustradas por erro",row.get("error_forced_frustrated_count","-"),"Contagem"),
            ("Amostras com erro de requisição",row.get("request_error_samples","-"),"Contagem"),
            ("p75",_fmt_number(row.get("p75_ms"),"ms"),"Tempo"),
            ("p95",_fmt_number(row.get("p95_ms"),"ms"),"Tempo"),
        ])
    else:
        rows.extend([
            ("Limite satisfatório",f"{row.get('threshold_seconds','-')} s","Configuração"),
            ("Limite frustrado",f"{row.get('frustration_seconds','-')} s","Configuração"),
            ("Média",_fmt_number(row.get("mean_ms"),"ms"),"Tempo"),
            ("p95",_fmt_number(row.get("p95_ms"),"ms"),"Tempo"),
        ])
    return rows


def _serp_metric_rows(database: Path, audit_id: str) -> list[Sequence[Any]]:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        observations=_audit_rows(con,"serp_observations",audit_id)
        if not observations:return []
        observation_ids=[str(r.get("observation_id")) for r in observations if r.get("observation_id")]
        results=[]
        if observation_ids and _table_exists(con,"serp_results") and "observation_id" in _columns(con,"serp_results"):
            placeholders=",".join("?" for _ in observation_ids)
            results=_dict_rows(_rows(con,f"SELECT * FROM serp_results WHERE observation_id IN ({placeholders})",tuple(observation_ids)))
        positions=[]
        for r in results:
            try:positions.append(int(r.get("position")))
            except (TypeError,ValueError):pass
        rows=[("Consultas observadas",len(observations),"Contagem"),("Resultados coletados",len(results),"Contagem")]
        if positions:rows.append(("Faixa de posições observada",f"{min(positions)} a {max(positions)}","Posição SERP"))
        return rows
    finally:con.close()


def _search_intelligence_html(database: Path, data: _ReportData) -> str:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:
        observations=_audit_rows(con,"serp_observations",data.audit_id)
        result_cols=_columns(con,"serp_results")
        rows=[];modals=[]
        for i,obs in enumerate(observations,1):
            oid=obs.get("observation_id")
            results=[]
            if oid and _table_exists(con,"serp_results") and "observation_id" in result_cols:
                results=_dict_rows(_rows(con,"SELECT * FROM serp_results WHERE observation_id=? ORDER BY position",(oid,)))
            positions=[]
            for r in results:
                try:positions.append(int(r.get("position")))
                except (TypeError,ValueError):pass
            mid=f"serp-{i}"
            device=_device_label(obs.get("device")) if obs.get("device") else "-"
            position=f"{min(positions)} a {max(positions)}" if positions else "-"
            rows.append((obs.get("query") or "-",obs.get("region") or "-",device,len(results),position,_modal_button(mid,"Ver observação")))
            result_rows=[]
            for r in results[:50]:
                result_rows.append((r.get("position") or "-",r.get("title") or "-",r.get("url") or "-"))
            body=_kv((("Consulta",obs.get("query") or "-"),("Região",obs.get("region") or "-"),("Dispositivo",device),("Profundidade solicitada",obs.get("requested_depth") or "-"),("Resultados persistidos",len(results))))
            body+="<h3>Resultados persistidos</h3>"+_table(("Posição","Título","URL"),result_rows,empty="Nenhum resultado individual persistido para esta observação.")
            modals.append(_modal(mid,"Observação de busca",str(obs.get("query") or "Consulta SERP"),body))
        return _table(("Consulta","Região","Dispositivo","Resultados","Posições","Detalhe"),rows,empty="Nenhuma observação SERP persistida.")+"".join(modals)
    finally:con.close()


def _passive_security_metric_rows(database: Path, audit_id: str) -> list[Sequence[Any]]:
    con=sqlite3.connect(database); con.row_factory=sqlite3.Row
    try:
        run=_last(con,"passive_security_runs",audit_id)
        findings=_audit_rows(con,"passive_security_findings",audit_id)
        resources=_audit_rows(con,"passive_security_resources",audit_id)
        components=_audit_rows(con,"passive_security_components",audit_id)
    finally:
        con.close()
    if not run and not findings and not resources:
        return []
    severities={key:0 for key in ("CRITICAL","HIGH","MEDIUM","LOW","INFO")}
    for row in findings:
        key=_norm(row.get("severity"))
        if key in severities:
            severities[key]+=1
    rows=[
        ("Páginas analisadas",run.get("pages_analyzed","-") if run else "-","Contagem"),
        ("Recursos inventariados",len(resources),"Contagem"),
        ("Componentes identificados",len(components),"Contagem"),
        ("Findings de segurança",len(findings),"Contagem"),
    ]
    for key,label in (("CRITICAL","Críticos"),("HIGH","Altos"),("MEDIUM","Médios"),("LOW","Baixos"),("INFO","Informativos")):
        rows.append((f"Findings {label}",severities[key],"Contagem"))
    if run:
        rows.append(("Estado da análise",_status_label(run.get("status")),"Estado"))
    return rows


def _catalog_metrics(database: Path, data: _ReportData, catalog_id: str) -> list[Sequence[Any]]:
    if catalog_id in {"CAT-01","CAT-03"}:
        out=[]
        for row in data.scores:
            dim=str(row.get("dimension") or "")
            if _DIMENSION_CONTEXT.get(dim)==catalog_id:
                out.append((_DIMENSION_LABELS.get(dim,dim),_score_value(row),"Índice"))
        return out
    if catalog_id=="CAT-02":
        obs=_web_observation(database,data.audit_id)
        return [("Lighthouse Accessibility",f"{float(obs['accessibility_score']):.0f} / 100","Índice")] if obs.get("accessibility_score") is not None else []
    if catalog_id=="CAT-04":return _web_metric_rows(database,data.audit_id)
    if catalog_id=="CAT-05":return _serp_metric_rows(database,data.audit_id)
    if catalog_id=="CAT-06":return _apdex_result_rows(database,data.audit_id,experience=False)
    if catalog_id=="CAT-07":return _apdex_result_rows(database,data.audit_id,experience=True)
    if catalog_id=="CAT-10":return _passive_security_metric_rows(database,data.audit_id)
    return []



__all__ = [name for name in globals() if not name.startswith("__")]
