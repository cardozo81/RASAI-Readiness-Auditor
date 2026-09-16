"""Catalog report methodology, inventory and materialization entrypoint."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from typing import Any

from rasai.catalog_report_integrations import *  # noqa: F401,F403


def _methodology_body(data: _ReportData) -> str:
    versions=sorted({str(r.get("scoring_version")) for r in data.scores if r.get("scoring_version")})
    body=_audit_hero(data,"Metodologia e pontuação","Como distinguir observação, índice, interpretação e recomendação sem confundir medição com opinião de IA.")
    body+=_section("principles","Princípios de leitura","<div class='grid'><div class='card'><h3>Observação</h3><p>Fato capturado ou medido: HTTP, DOM, LCP, erro, arquivo, SERP.</p></div><div class='card'><h3>Índice</h3><p>Resultado agregado calculado por contrato, como SARI ou Apdex.</p></div><div class='card'><h3>Análise</h3><p>Interpretação/correlação persistida, determinística ou assistida por IA.</p></div><div class='card'><h3>Remediação</h3><p>Ação sugerida para corrigir ou melhorar um problema observado.</p></div></div>")
    body+=_section("scoring","Metodologia de pontuação persistida",f"<div class='metric-grid'>{_metric('Versão',', '.join(versions) or '—')}{_metric('Recalcula a pontuação?','Não')}{_metric('Fonte','Dados persistidos da auditoria')}</div>{_score_table(data)}")
    body+=_section("ai","IA e determinismo","<p>IA pode interpretar, correlacionar, priorizar e sugerir. Ela não escolhe pesos nem reescreve uma medição determinística nesta projeção.</p>")
    return body


def _metrics_body(database: Path, data: _ReportData) -> str:
    rows=[]
    for r in data.scores:
        dim=str(r.get("dimension") or "");label=_DIMENSION_LABELS.get(dim,dim.replace("_"," ").title())
        ctx="SARI" if dim=="OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dim,"Metodologia")
        link="sari.html" if dim=="OVERALL_READINESS" else CATALOG_PAGE_BY_ID[ctx].filename if ctx in CATALOG_PAGE_BY_ID else "methodology.html"
        rows.append((_Html(f"<a href='{link}'>{escape(label)}</a>"),"Índice",_score_value(r),_device_label(r.get("device")),"Índice persistido",r.get("scoring_version","—")))
    for cid in ("CAT-04","CAT-06","CAT-07"):
        for name,value,kind in _catalog_metrics(database,data,cid):
            rows.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[cid].filename}'>{escape(str(name))}</a>"),kind,value,CATALOG_BY_ID[cid].label,"Medição persistida","—"))
    definitions=(
        ("SARI","Índice","Prontidão agregada com cobertura, confiança e condições de validação."),
        ("Lighthouse","Índice","Pontuações laboratoriais por categoria quando coletadas."),
        ("LCP / INP / CLS","Métrica","Métricas de experiência/desempenho; o contexto diferencia laboratório e campo."),
        ("Apdex","Índice","Satisfação calculada a partir das amostras e limites persistidos."),
        ("SERP","Métrica","Posição observada em uma coleta de resultados de busca; não equivale à posição média do GSC."),
    )
    body=_audit_hero(data,"Índices e métricas","Inventário transversal dos números persistidos, com rótulos funcionais e referência ao catálogo proprietário.")
    body+=_section("inventory","Inventário desta auditoria",_table(("Indicador","Tipo","Valor","Contexto","Origem","Contrato"),rows,empty="Nenhum índice/métrica reconhecido foi persistido."))
    body+=_section("dictionary","Dicionário",_table(("Termo","Tipo","Como interpretar"),definitions))
    return body


def _source_fingerprint(database: Path) -> str:
    """Fingerprint the persisted audit database, including an active WAL when present."""
    digest=hashlib.sha256()
    paths=(database,database.with_name(database.name+"-wal"))
    found=False
    for path in paths:
        if not path.is_file():
            continue
        found=True
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024*1024),b""):
                digest.update(chunk)
        digest.update(b"\0")
    if not found:
        raise FileNotFoundError(database)
    return digest.hexdigest()


def catalog_report_is_fresh(*,audit_id: str,workspace: Any) -> bool:
    """Return True only when the published tree matches the current persisted audit."""
    report_dir=Path(workspace.root)/CATALOG_REPORT_DIR
    manifest_path=report_dir/"manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError,ValueError,json.JSONDecodeError):
        return False
    if str(manifest.get("audit_id") or "")!=audit_id:
        return False
    if str(manifest.get("freshness") or "")!="FINAL":
        return False
    expected=str(manifest.get("source_fingerprint") or "")
    if not expected:
        return False
    try:
        current=_source_fingerprint(Path(workspace.database))
    except OSError:
        return False
    return current==expected


def _discard_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path,ignore_errors=True)
    else:
        try:path.unlink()
        except OSError:pass


def materialize_catalog_report_site(*, audit_id: str, workspace: Any) -> Path:
    """Build a final, fresh ``report-catalog/`` tree from persisted audit state.

    The previous published tree is quarantined before rendering.  If rendering fails,
    the old tree is discarded instead of remaining available as if it represented the
    final database.  A successful build is promoted only when the source fingerprint
    is unchanged from the beginning to the end of the projection.
    """
    from rasai.catalog_report_adherence import install_catalog_report_adherence
    from rasai.catalog_report_final_refinements import install_catalog_report_refinements
    from rasai.catalog_report_label_refinements import install_catalog_human_labels

    install_catalog_human_labels()
    install_catalog_report_refinements()
    install_catalog_report_adherence()

    root=Path(workspace.root)
    report_dir=root/CATALOG_REPORT_DIR
    database=Path(workspace.database)
    token=uuid.uuid4().hex
    staging=root/f".{CATALOG_REPORT_DIR}.tmp-{token}"
    quarantine=root/f".{CATALOG_REPORT_DIR}.stale-{token}"
    before=_source_fingerprint(database)

    # Never let a previous tree survive a failed final materialization under the public
    # report-catalog path.  A stale report is worse than an explicit missing report.
    if report_dir.exists() or report_dir.is_symlink():
        report_dir.replace(quarantine)

    try:
        css_dir=staging/"css"
        css_dir.mkdir(parents=True,exist_ok=False)
        data=_load_data(audit_id,database)
        (css_dir/"site.css").write_text(_CSS.strip()+"\n",encoding="utf-8",newline="\n")
        bodies={
            "index.html":_overview_body(database,data),
            "sari.html":_sari_body(data),
            "capture-context.html":_capture_context_body(database,data),
            "execution-evidence.html":_execution_evidence_body(database,data),
            "ai-integrations.html":_ai_integrations_body(database,data),
            "methodology.html":_methodology_body(data),
            "metrics.html":_metrics_body(database,data),
        }
        for catalog in CATALOGS:
            bodies[CATALOG_PAGE_BY_ID[catalog.id].filename]=_catalog_body(database,data,catalog.id)
        for page in CATALOG_REPORT_PAGES:
            body=bodies.get(page.filename)
            if body is None:
                body=_audit_hero(data,page.label,"Superfície sem projeção específica disponível.")
            (staging/page.filename).write_text(_shell(page,audit_id,body),encoding="utf-8",newline="\n")

        after=_source_fingerprint(database)
        if before!=after:
            raise RuntimeError("catalog report source changed during materialization; refusing stale projection")

        manifest={
            "contract":CATALOG_REPORT_CONTRACT_VERSION,
            "projection_version":CATALOG_REPORT_CONTRACT_VERSION,
            "audit_id":audit_id,
            "source_audit":audit_id,
            "source_of_truth":"audit.db + artifacts + secret-free execution snapshot",
            "source_fingerprint":after,
            "source_fingerprint_algorithm":"sha256(audit.db + active WAL)",
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "freshness":"FINAL",
            "catalog_report_dir":CATALOG_REPORT_DIR,
            "pages":[{"id":p.id,"filename":p.filename,"label":p.label,"catalog_id":p.catalog_id} for p in CATALOG_REPORT_PAGES],
            "principles":{"read_only":True,"modal_scope":"contextual-atomic","human_labels":True,"cross_catalog_reference_not_duplication":True},
        }
        (staging/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")

        # Recheck after the manifest is complete; no source mutation is accepted between
        # rendering and promotion either.
        if _source_fingerprint(database)!=after:
            raise RuntimeError("catalog report source changed before promotion; refusing stale projection")
        staging.replace(report_dir)
        _discard_tree(quarantine)
    except Exception:
        _discard_tree(staging)
        _discard_tree(report_dir)
        _discard_tree(quarantine)
        raise

    if not catalog_report_is_fresh(audit_id=audit_id,workspace=workspace):
        _discard_tree(report_dir)
        raise RuntimeError("catalog report freshness verification failed after promotion")
    return report_dir/"index.html"


__all__ = [name for name in globals() if not name.startswith("__")]
