"""Catalog report methodology, inventory and materialization entrypoint."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid
from typing import Any

from rasai.catalog_report_integrations import *  # noqa: F401,F403
from rasai.search_intelligence.freshness import require_valid_serp_freshness


def _methodology_body(data: _ReportData) -> str:
    versions=sorted({str(r.get("scoring_version")) for r in data.scores if r.get("scoring_version")})
    body=_audit_hero(data,"Metodologia e pontuação","Como distinguir observação, índice, interpretação e recomendação sem confundir medição com opinião de IA.")
    body+=_section("principles","Princípios de leitura","<div class='grid'><div class='card'><h3>Observação</h3><p>Fato capturado ou medido: HTTP, DOM, LCP, erro, arquivo, SERP.</p></div><div class='card'><h3>Índice</h3><p>Resultado agregado calculado por contrato, como SARI ou Apdex.</p></div><div class='card'><h3>Análise</h3><p>Interpretação/correlação persistida, determinística ou assistida por IA.</p></div><div class='card'><h3>Remediação</h3><p>Ação sugerida para corrigir ou melhorar um problema observado.</p></div></div>")
    body+=_section("scoring","Metodologia de pontuação persistida",f"<div class='metric-grid'>{_metric('Versão',', '.join(versions) or '-')}{_metric('Recalcula a pontuação?','Não')}{_metric('Fonte','Dados persistidos da auditoria')}</div>{_score_table(data)}")
    body+=_section("ai","IA e determinismo","<p>IA pode interpretar, correlacionar, priorizar e sugerir. Ela não escolhe pesos nem reescreve uma medição determinística nesta projeção.</p>")
    return body


def _metrics_body(database: Path, data: _ReportData) -> str:
    rows=[]
    for r in data.scores:
        dim=str(r.get("dimension") or "");label=_DIMENSION_LABELS.get(dim,dim.replace("_"," ").title())
        ctx="SARI" if dim=="OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dim,"Metodologia")
        link="sari.html" if dim=="OVERALL_READINESS" else CATALOG_PAGE_BY_ID[ctx].filename if ctx in CATALOG_PAGE_BY_ID else "methodology.html"
        rows.append((_Html(f"<a href='{link}'>{escape(label)}</a>"),"Índice",_score_value(r),_device_label(r.get("device")),"Índice persistido",r.get("scoring_version","-")))
    for cid in ("CAT-04","CAT-06","CAT-07"):
        for name,value,kind in _catalog_metrics(database,data,cid):
            rows.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[cid].filename}'>{escape(str(name))}</a>"),kind,value,CATALOG_BY_ID[cid].label,"Medição persistida","-"))
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


def _sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprint(database: Path) -> str:
    """Fingerprint the live audit state for freshness checks during materialization.

    This live fingerprint may include an active WAL. It is deliberately distinct from
    the package integrity fingerprint, which is calculated from a stable SQLite backup
    physically included in ``report-catalog/integrity``.
    """
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


def _snapshot_sqlite_database(source: Path, destination: Path) -> None:
    """Create one consistent standalone SQLite database including committed WAL state."""
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        destination.unlink()
    source_uri=f"file:{source.resolve().as_posix()}?mode=ro"
    source_connection=sqlite3.connect(source_uri,uri=True,timeout=10.0)
    target_connection=sqlite3.connect(destination,timeout=10.0)
    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    if not destination.is_file() or destination.stat().st_size<=0:
        raise RuntimeError("catalog report SQLite snapshot was not materialized")


def _packaged_file_records(root: Path) -> list[dict[str,Any]]:
    records=[]
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name!="manifest.json"):
        relative=path.relative_to(root).as_posix()
        records.append({"path":relative,"sha256":_sha256_file(path),"size_bytes":path.stat().st_size})
    return records


def verify_catalog_report_package(report_dir: str|Path) -> tuple[bool,tuple[str,...]]:
    """Verify integrity using only files delivered inside ``report-catalog``."""
    root=Path(report_dir)
    manifest_path=root/"manifest.json"
    if not manifest_path.is_file():
        return False,("manifest.json ausente",)
    try:
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError,ValueError,json.JSONDecodeError):
        return False,("manifest.json inválido",)
    records=manifest.get("packaged_files")
    if not isinstance(records,list) or not records:
        return False,("manifest sem packaged_files",)
    errors=[]
    for raw in records:
        if not isinstance(raw,dict):
            errors.append("registro de arquivo inválido")
            continue
        relative=str(raw.get("path") or "")
        expected=str(raw.get("sha256") or "")
        if not relative or not expected:
            errors.append("registro de arquivo incompleto")
            continue
        candidate=(root/relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            errors.append(f"caminho fora do pacote: {relative}")
            continue
        if not candidate.is_file():
            errors.append(f"arquivo ausente: {relative}")
            continue
        if _sha256_file(candidate)!=expected:
            errors.append(f"hash divergente: {relative}")
    snapshot=manifest.get("audit_snapshot")
    if not isinstance(snapshot,dict) or not snapshot.get("path") or not snapshot.get("sha256"):
        errors.append("audit_snapshot ausente do manifest")

    assurance=manifest.get("assurance")
    if not isinstance(assurance,dict):
        errors.append("assurance ausente do manifest")
    else:
        assurance_ref=str(assurance.get("artifact") or "")
        if not assurance_ref:
            errors.append("artifact de assurance ausente do manifest")
        else:
            assurance_path=(root/assurance_ref).resolve()
            try:
                assurance_path.relative_to(root.resolve())
            except ValueError:
                errors.append("artifact de assurance fora do pacote")
            else:
                if not assurance_path.is_file():
                    errors.append("artifact de assurance ausente")
                else:
                    try:
                        assurance_payload=json.loads(assurance_path.read_text(encoding="utf-8"))
                    except (OSError,ValueError,json.JSONDecodeError):
                        errors.append("artifact de assurance inválido")
                    else:
                        if bool(assurance_payload.get("closure_eligible")) != bool(assurance.get("closure_eligible")):
                            errors.append("closure_eligible divergente entre manifest e assurance")
                        if assurance_payload.get("thresholds") != assurance.get("thresholds"):
                            errors.append("thresholds divergentes entre manifest e assurance")
                        if assurance_payload.get("global") != assurance.get("global"):
                            errors.append("scores globais divergentes entre manifest e assurance")
    return not errors,tuple(errors)


def catalog_report_is_fresh(*,audit_id: str,workspace: Any) -> bool:
    """Return True only when the published tree is internally valid and matches live state."""
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
    package_ok,_errors=verify_catalog_report_package(report_dir)
    if not package_ok:
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
    """Build a final, fresh and self-verifiable ``report-catalog/`` tree."""
    from rasai.ai_dependency_reporting import install as install_ai_dependency_reporting
    from rasai.catalog_report_adherence import install_catalog_report_adherence
    from rasai.catalog_report_final_refinements import install_catalog_report_refinements
    from rasai.catalog_report_label_refinements import install_catalog_human_labels
    from rasai.catalog_report_search_trust import install as install_catalog_search_trust
    from rasai.catalog_state_trust import install as install_catalog_state_trust
    from rasai.recommendation_governance_reporting import install as install_recommendation_governance_reporting
    from rasai.semantic_coherence_reporting import install as install_semantic_coherence_reporting
    from rasai.catalog_report_assurance import (
        assess_catalogs,
        assurance_matrix_html,
        catalog_assurance_html,
    )

    install_catalog_human_labels()
    install_catalog_report_refinements()
    install_catalog_report_adherence()
    # Final trust/report layers are installed explicitly here so report materialization
    # does not depend on whether the console or worker imported an unrelated runtime hook.
    install_catalog_state_trust()
    install_catalog_search_trust()
    install_semantic_coherence_reporting()
    install_recommendation_governance_reporting()
    install_ai_dependency_reporting()

    root=Path(workspace.root)
    report_dir=root/CATALOG_REPORT_DIR
    database=Path(workspace.database)
    # Freshness is a publication invariant. A stale observation may be used only when
    # explicitly persisted as REUSED_EVIDENCE with source/reason provenance.
    require_valid_serp_freshness(database,audit_id)
    # CAT-09 governance is materialized by the canonical report-model phase before
    # HTML projection. From this point onward report generation is strictly read-only.
    token=uuid.uuid4().hex
    staging=root/f".{CATALOG_REPORT_DIR}.tmp-{token}"
    quarantine=root/f".{CATALOG_REPORT_DIR}.stale-{token}"
    before=_source_fingerprint(database)

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
        raw_catalog_bodies={}
        for catalog in CATALOGS:
            filename=CATALOG_PAGE_BY_ID[catalog.id].filename
            raw_catalog_bodies[filename]=_catalog_body(database,data,catalog.id)
            bodies[filename]=raw_catalog_bodies[filename]
        assurance=assess_catalogs(database,data,bodies)
        assurance_by_catalog={row["catalog_id"]:row for row in assurance["catalogs"]}
        for catalog in CATALOGS:
            filename=CATALOG_PAGE_BY_ID[catalog.id].filename
            bodies[filename]=raw_catalog_bodies[filename]+catalog_assurance_html(assurance_by_catalog[catalog.id])
        bodies["index.html"]+=assurance_matrix_html(assurance)
        for page in CATALOG_REPORT_PAGES:
            body=bodies.get(page.filename)
            if body is None:
                body=_audit_hero(data,page.label,"Superfície sem projeção específica disponível.")
            (staging/page.filename).write_text(_shell(page,audit_id,body),encoding="utf-8",newline="\n")

        after=_source_fingerprint(database)
        if before!=after:
            raise RuntimeError("catalog report source changed during materialization; refusing stale projection")

        snapshot_path=staging/"integrity"/"audit-snapshot.db"
        _snapshot_sqlite_database(database,snapshot_path)
        assurance_path=staging/"integrity"/"catalog-assurance.json"
        assurance_path.write_text(
            json.dumps(assurance,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8",
            newline="\n",
        )
        if _source_fingerprint(database)!=after:
            raise RuntimeError("catalog report source changed while creating integrity snapshot")
        snapshot_hash=_sha256_file(snapshot_path)
        packaged_files=_packaged_file_records(staging)

        manifest={
            "contract":CATALOG_REPORT_CONTRACT_VERSION,
            "projection_version":CATALOG_REPORT_CONTRACT_VERSION,
            "audit_id":audit_id,
            "source_audit":audit_id,
            "source_of_truth":"audit.db + artifacts + secret-free execution snapshot",
            "source_fingerprint":after,
            "source_fingerprint_algorithm":"sha256(live audit.db + active WAL); runtime freshness only",
            "audit_snapshot":{"path":"integrity/audit-snapshot.db","sha256":snapshot_hash,"algorithm":"sha256","standalone_sqlite":True},
            "package_integrity_algorithm":"sha256(each packaged file; manifest excluded)",
            "packaged_files":packaged_files,
            "assurance":{
                "metric_semantics":assurance["metric_semantics"],
                "thresholds":assurance["thresholds"],
                "global":assurance["global"],
                "per_catalog_target_met":assurance["per_catalog_target_met"],
                "high_assurance_target_met":assurance["high_assurance_target_met"],
                "closure_eligible":assurance["closure_eligible"],
                "artifact":"integrity/catalog-assurance.json",
            },
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "freshness":"FINAL",
            "catalog_report_dir":CATALOG_REPORT_DIR,
            "pages":[{"id":p.id,"filename":p.filename,"label":p.label,"catalog_id":p.catalog_id} for p in CATALOG_REPORT_PAGES],
            "principles":{
                "read_only":True,
                "modal_scope":"contextual-atomic",
                "human_labels":True,
                "cross_catalog_reference_not_duplication":True,
                "self_verifiable_package":True,
                "serp_freshness_guard":True,
                "catalog_result_requires_materialized_data":True,
                "recommendation_governance":True,
                "ai_dependency_provenance":True,
            },
        }
        (staging/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
        package_ok,package_errors=verify_catalog_report_package(staging)
        if not package_ok:
            raise RuntimeError("catalog report package integrity failed: "+"; ".join(package_errors))
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
        raise RuntimeError("catalog report freshness/integrity verification failed after promotion")
    return report_dir/"index.html"


__all__ = [name for name in globals() if not name.startswith("__")]
