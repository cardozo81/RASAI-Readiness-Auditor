"""Capture context, overview, SARI and execution governance pages."""
from rasai.catalog_report_page import *  # noqa: F401,F403

import sqlite3
from contextlib import closing
from math import isfinite

from rasai.browser_render_failure import render_failure_public_detail


def _rpr_render_diagnostics(database: Path, audit_id: str) -> dict[str, dict]:
    """Latest causal RPR render diagnosis per snapshot, if the ledger exists."""
    output: dict[str, dict] = {}
    connection = sqlite3.connect(database)
    try:
        try:
            rows = connection.execute(
                """SELECT w.scope_key,a.metadata
                   FROM audit_fulfillment_attempts a
                   JOIN audit_fulfillment_work_items w ON w.work_item_id=a.work_item_id
                   WHERE a.audit_id=? AND w.component='RENDER_CAPTURE'
                   ORDER BY a.started_at DESC,a.rowid DESC""",
                (audit_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return output
        for scope, raw in rows:
            key = str(scope or "")
            if key in output:
                continue
            payload = _safe_json(raw, {})
            context = payload.get("render_failure_context") if isinstance(payload, Mapping) else None
            if isinstance(context, Mapping):
                output[key] = dict(context)
    finally:
        connection.close()
    return output


def _capture_context_body(database: Path, data: _ReportData) -> str:
    snaps=_capture_snapshots(database,data.audit_id)
    rpr_render_failures=_rpr_render_diagnostics(database,data.audit_id)
    rows=[];modals=[]
    for i,s in enumerate(snaps,1):
        meta=_safe_json(s.get("browser_metadata"),{})
        initial_failure=meta.get("render_failure_context") if isinstance(meta,Mapping) else None
        rpr_failure=rpr_render_failures.get(str(s.get("snapshot_id") or ""))
        profile=meta.get("profile") if isinstance(meta,Mapping) and isinstance(meta.get("profile"),Mapping) else {}
        browser=meta.get("browser_identity") if isinstance(meta,Mapping) and isinstance(meta.get("browser_identity"),Mapping) else {}
        viewport=profile.get("viewport") if isinstance(profile,Mapping) and isinstance(profile.get("viewport"),Mapping) else {}
        runtime=_runtime_items(s)
        mid=f"capture-{i}"
        rows.append((_device_label(s.get("device")),s.get("requested_url") or s.get("page_url") or "-",s.get("final_url") or "-",s.get("http_status") or "-",len(runtime),_modal_button(mid,"Ver captura")))
        visual_ref=meta.get("visual_artifact_ref") if isinstance(meta,Mapping) else None
        visual_path=_artifact_path(database.parent,visual_ref)
        artifact_rows=[
            ("Resposta HTTP",s.get("raw_artifact_ref") or "-"),("HTML renderizado",s.get("rendered_artifact_ref") or "-"),
            ("Conteúdo principal",s.get("main_content_ref") or "-"),("Dados estruturados",s.get("structured_data_ref") or "-"),
            ("Captura visual",visual_ref or "-"),
        ]
        body=_kv((("Identificador da página",s.get("page_id")),("Identificador da captura",s.get("snapshot_id")),("URL solicitada",s.get("requested_url") or s.get("page_url")),("URL final",s.get("final_url")),("Capturado em",s.get("captured_at")),("HTTP",s.get("http_status")),("Tipo de conteúdo",s.get("content_type")),("Renderização",s.get("rendering_mode")),("Arquitetura",_architecture_label(s.get("architecture_classification"))),("Dispositivo",_device_label(s.get("device"))),("Perfil",browser.get("descriptor") or profile.get("device") or "-"),("Área visível (viewport)",f"{viewport.get('width','-')} × {viewport.get('height','-')}"),("Escala de pixels (DPR)",profile.get("device_scale_factor") or "-"),("Navegador",f"{browser.get('channel','Chrome')} {browser.get('browser_version') or meta.get('browser_version','-')}"),("Idioma",browser.get("locale") or profile.get("locale") or "-"),("Diagnósticos da execução do navegador",len(runtime))))
        if initial_failure:
            body+="<h3>Diagnóstico da captura inicial</h3>"
            body+=f"<div class='notice warn'>{escape(render_failure_public_detail(dict(initial_failure)))}</div>"
        if rpr_failure:
            body+="<h3>Diagnóstico da última tentativa de recuperação</h3>"
            body+=f"<div class='notice warn'>{escape(render_failure_public_detail(rpr_failure))}</div>"
        body+="<h3>Arquivos e evidências</h3>"+_table(("Arquivo / evidência","Referência"),artifact_rows)
        if visual_path is not None and visual_ref:
            href="../"+str(visual_ref).replace("\\","/")
            body+="<h3>Captura visual</h3><p class='muted'>Imagem persistida no momento da captura; não é reconstruída pelo relatório.</p>"
            body+=f"<a class='capture-link' href='{escape(href)}' target='_blank' rel='noopener'><img class='capture-preview' src='{escape(href)}' alt='Captura visual da página auditada em {_device_label(s.get('device'))}'></a>"
        elif visual_ref:
            body+="<div class='notice warn'>A referência da captura visual foi persistida, mas o arquivo não está disponível junto aos artefatos desta cópia da auditoria.</div>"
        modals.append(_modal(mid,"Captura da página",f"{_device_label(s.get('device'))} · {s.get('final_url') or s.get('requested_url') or '-'}",body))
    body=_audit_hero(data,"Captura e contexto","Como a página foi capturada: URL, dispositivo, navegador, renderização e artefatos. Diagnósticos funcionais permanecem no catálogo responsável.")
    body+=_outline((("capture","Capturas"),("boundaries","Responsabilidades"),("technical","Detalhes técnicos")))
    body+=_section("capture","Capturas da auditoria",_table(("Dispositivo","URL solicitada","URL final","HTTP","Diagnósticos","Detalhe"),rows,empty="Nenhuma captura de navegador persistida.",sortable=bool(rows))+"".join(modals))
    body+=_section("boundaries","Responsabilidades","<div class='grid'><div class='card'><h3>Captura e contexto</h3><p>Identifica a captura, navegador, dispositivo, área visível, URL e arquivos de evidência.</p></div><div class='card'><h3>CAT-01</h3><p>Exibe erros/alertas do navegador e problemas técnicos observados.</p><p><a href='cat-01.html'>Abrir CAT-01</a></p></div><div class='card'><h3>CAT-06 / CAT-07</h3><p>Exibem suas próprias amostras sintéticas; não duplicam a captura base.</p></div></div>")
    body+=_section("technical","Detalhes técnicos","<details><summary>Como interpretar os identificadores</summary><div class='detail-body'><p>O identificador da página localiza o alvo auditado; o identificador da captura localiza uma execução específica por dispositivo/contexto. Os CATs referenciam esses identificadores sem criar cópias dos artefatos.</p></div></details>")
    return body


def _diagnostic_state_section(database: Path, data: _ReportData, integrity: str) -> str:
    """Render only the current unresolved diagnostic requirements.

    Historical failed attempts remain in provenance/technical surfaces. Once a required
    item is resolved it disappears from this current-state notice automatically.
    """
    from rasai.diagnostic_closure import current_pending

    pending = current_pending(database, data.audit_id)
    if not pending:
        return ""

    rows = [
        (
            item.catalog_id,
            item.integration,
            item.kind,
            item.state,
            item.reason,
            "Sim" if item.required_to_close else "Não",
        )
        for item in pending
    ]
    content = (
        "<div class='metric-grid'>"
        + _metric("Relatório", "Gerado")
        + _metric("Integridade do plano", integrity)
        + _metric("Fechamento integral", "Pendente")
        + "</div>"
        + "<div class='notice warn'>"
        + "O relatório foi materializado com os dados válidos disponíveis, mas existem "
          "integrações ou análises necessárias que ainda não concluíram. Nenhuma pendência "
          "abaixo foi convertida em sucesso. Reprocesse somente os requisitos necessários "
          "para concluir o diagnóstico."
        + "</div>"
        + _table(
            ("Fase/Catálogo", "Integração", "Tipo", "Estado", "Motivo", "Necessário para fechar"),
            rows,
            sortable=bool(rows),
        )
    )
    return _section("diagnostic", "Estado do diagnóstico", content)


def _overview_serp_depth(database: Path, audit_id: str) -> tuple[int, int] | None:
    """Scope a depth gap to precisely one persisted SERP observation."""
    # Read-only report projection: never create missing SQLite, cross-join
    # reused observation IDs, or trust a pending/uncheckpointed journal.
    try:
        source = Path(database)
        if (source.is_symlink() or not source.is_file() or any(
            Path(str(source) + ending).exists()
            for ending in ("-wal", "-shm", "-journal")
        )):
            return None
        with closing(sqlite3.connect(
            source.resolve().as_uri() + "?mode=ro", uri=True, timeout=2,
        )) as con:
            con.execute("PRAGMA query_only=ON")
            observed = con.execute(
                "SELECT observation_id,requested_depth FROM serp_observations "
                "WHERE audit_id=? LIMIT 2", (audit_id,),
            ).fetchall()
            if len(observed) != 1:
                return None
            observation_id, depth = observed[0]
            expected = int(depth)
            if not observation_id or not 0 < expected <= 1000:
                return None
            identities = con.execute(
                "SELECT audit_id FROM serp_observations "
                "WHERE observation_id=? LIMIT 2", (observation_id,),
            ).fetchall()
            if len(identities) != 1 or identities[0][0] != audit_id:
                return None
            measured = con.execute(
                "SELECT COUNT(*) FROM serp_results WHERE observation_id=?",
                (observation_id,),
            ).fetchone()
            returned = int(measured[0]) if measured else 0
            return (returned, expected) if 0 <= returned < expected else None
    except (sqlite3.Error, OSError, TypeError, ValueError, OverflowError):
        return None


def _overview_measurement_scope_notice(
    web: Mapping[str, Any] | None,
    catalog_statuses: Mapping[str, str],
    *,
    overall_scores: Sequence[Mapping[str, Any]] = (),
    serp_depth: tuple[int, int] | None = None,
) -> str:
    """Describe only persisted sampling/scope limitations, never re-score."""
    details: list[str] = []
    if (
        isinstance(web, Mapping)
        and str(web.get("field_scope") or "").strip().upper() == "ORIGIN"
        and any(web.get(key) is not None for key in ("lcp_p75_ms", "inp_p75_ms", "cls_p75"))
    ):
        details.append(
            "Os Core Web Vitals de campo exibidos para CAT-04 correspondem ao "
            "agregado da origem (ORIGIN), não necessariamente à URL auditada. "
            "Lighthouse de laboratório e CrUX de campo medem universos diferentes."
        )
    # A SARI score and a lab Lighthouse score measure different contracts.
    # Warn on a large documented divergence without changing either number.
    def bounded_score(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            converted = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return converted if isfinite(converted) and 0 <= converted <= 100 else None

    lab = bounded_score(web.get("performance_score")) if isinstance(web, Mapping) else None
    high_sari = any(
        isinstance(row, Mapping)
        and str(row.get("dimension") or "") == "OVERALL_READINESS"
        and (score := bounded_score(row.get("value"))) is not None
        and score >= 75
        for row in overall_scores
    )
    if lab is not None and lab <= 40 and high_sari:
        details.append(
            "O SARI acima de 75/100 coexiste com desempenho Lighthouse de laboratório "
            "baixo (até 40/100). São indicadores distintos: nota elevada no método "
            "de prontidão não representa aprovação global da experiência."
        )
    if str(catalog_statuses.get("CAT-06") or "").strip().casefold() in {"partial", "parcial"}:
        details.append(
            "O CAT-06 apresenta resultado parcial apesar da conclusão operacional "
            "da auditoria. Consulte amostras válidas e limite de população na "
            "página específica; pipeline concluído não significa amostra suficiente."
        )
    if serp_depth is not None:
        collected, requested = serp_depth
        if 0 <= collected < requested:
            details.append(
                f"A consulta SERP retornou {collected} de {requested} posições solicitadas. "
                "Essa profundidade parcial não representa participação de mercado, "
                "cobertura de todas as consultas nem posições não observadas."
            )
    if not details:
        return ""
    return (
        "<div class='notice warn' data-contract='OVERVIEW-SCOPE-600'>"
        "<strong>Limites de interpretação das medições:</strong> "
        + " ".join(details) + "</div>"
    )


def _experience_paths_633() -> str:
    """An ordered reading map of canonical evidence, never another report.

    The map does not synthesize findings or counts. All destinations belong to
    the existing report contract and preserve their original detailed content.
    """
    canonical = {page.filename for page in CATALOG_REPORT_PAGES}
    journeys = (
        ("01", "Entender o diagnóstico", "Situação, dimensões e critérios de leitura",
         ("Resumo e estado da auditoria", "index.html", "catalogs"),
         ("Indicadores e limites das medições", "metrics.html", None)),
        ("02", "Explorar objetivos", "Ler as ações conforme suas dimensões declaradas",
         ("Ações por objetivo", "directed-analysis.html", "objectives"),
         ("Plano e dependências", "directed-analysis.html", "roadmap")),
        ("03", "Examinar intervenções", "Conferir a ação persistida, seu alvo e a evidência",
         ("Ações e rastreabilidade", "directed-analysis.html", "actions"),
         ("Por URL / alvo", "directed-analysis.html", "targets"),
         ("Intervenções técnicas do CAT-09", "cat-09.html", None)),
        ("04", "Validar evidências", "Conferir origem, método e limitações",
         ("Captura e contexto", "capture-context.html", None),
         ("Evidências de execução", "execution-evidence.html", None)),
        ("05", "Interpretar Search e IA", "Separar observações, inferências e métricas",
         ("Resultados GEO", "geo.html", None),
         ("Integrações de IA", "ai-integrations.html", None)),
        ("06", "Conferir metodologia", "Localizar critérios e proveniência sem perder detalhes",
         ("Metodologia", "methodology.html", None),
         ("SARI", "sari.html", None)),
    )
    sections = []
    for number, title, description, *links in journeys:
        entries = []
        for label, filename, anchor in links:
            if filename not in canonical:
                raise ValueError("reading map points outside report contract")
            href = filename + ("#" + anchor if anchor else "")
            entries.append(
                "<li><a href='" + escape(href, quote=True) + "'>"
                + escape(label) + "</a></li>"
            )
        sections.append(
            "<li class='report-reading-step'><div class='report-reading-number'>"
            + number + "</div><div class='report-reading-content'><h3>"
            + escape(title) + "</h3><p>" + escape(description)
            + "</p><ul class='report-reading-links'>" + "".join(entries)
            + "</ul></div></li>"
        )
    return (
        "<p class='section-lead'>Percurso de interpretação: do estado observado "
        "às intervenções, evidências e limites de medição. Cada etapa abre "
        "exatamente as páginas canônicas; não cria resultados adicionais.</p>"
        "<ol class='report-reading-map'>" + "".join(sections) + "</ol>"
    )


def _snapshot_indicator_633(
    label: str, value: Any, note: str, destination: str, action_label: str,
    *, tone: str = "neutral",
) -> str:
    """Read-only summary with source-bound drill-down and existing result tone."""
    result_tone = tone if tone in {"good", "warn", "low", "bad", "neutral"} else "neutral"
    return (
        "<div class='metric report-snapshot-metric'>"
        "<small>" + escape(label) + "</small>"
        "<strong class='result-value " + result_tone + "'>" + _display_value(value) + "</strong>"
        "<small>" + escape(note) + "</small>"
        "<a class='report-snapshot-cta' href='" + escape(destination, quote=True) + "'>"
        + escape(action_label) + " <span aria-hidden='true'>→</span></a></div>"
    )


def _lighthouse_score_display_633(raw: Any) -> str:
    """Persisted Lighthouse scores are ALREADY on 0..100 (M21 contract).

    An observation with performance_score=1.0 means 1/100, not 100/100.
    The upstream PageSpeed raw API score 0..1 was scaled during collection;
    projection must never scale a persisted score a second time.
    """
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return str(raw) + "/100"
    if not isfinite(value):
        return str(raw) + "/100"
    return f"{value:g}/100"


def _decision_snapshot_poc_633(
    database: Path, data: _ReportData,
) -> str:
    """Independent persisted facts with traceable targets, never a new score."""
    from rasai.catalog_report_metrics import _web_observation

    metrics: list[str] = []
    overall = next(
        (row for row in data.scores
         if str(row.get("dimension") or "") == "OVERALL_READINESS"
         and row.get("value") is not None), None,
    )
    if overall is not None:
        metrics.append(_snapshot_indicator_633(
            "SARI · prontidão",
            _score_value(overall),
            "Índice próprio; não mede performance Lighthouse.",
            "sari.html#composition",
            "Ver dimensões e composição",
            tone=_sari_public_tone(overall),
        ))
    web = _web_observation(database, data.audit_id)
    if isinstance(web, Mapping) and web.get("performance_score") is not None:
        metrics.append(_snapshot_indicator_633(
            "Lighthouse · desempenho",
            _lighthouse_score_display_633(web["performance_score"]),
            "Score já persistido em 0–100; laboratório, distinto de SARI e CrUX.",
            "cat-04.html#metric-lighthouse-performance",
            "Ver resultado e evidências",
            tone=_catalog_metric_tone("CAT-04","Lighthouse · Desempenho",web["performance_score"]),
        ))
    if isinstance(web, Mapping) and web.get("lcp_p75_ms") is not None:
        raw_scope = str(web.get("field_scope") or "não declarado").upper()
        metrics.append(_snapshot_indicator_633(
            "CrUX · LCP p75",
            str(web["lcp_p75_ms"]) + " ms",
            "Métrica de campo, escopo " + raw_scope + "; não atribuir à URL quando ORIGIN.",
            "cat-04.html#metric-field-lcp-p75",
            "Ver medição e escopo",
            tone=_catalog_metric_tone("CAT-04","LCP de campo (p75)",web["lcp_p75_ms"]),
        ))
    counts: tuple[int, int, int] | None = None
    try:
        with sqlite3.connect(database) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='directed_analysis_actions'"
            ).fetchone()
            if exists:
                row = connection.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN priority='HIGH' THEN 1 ELSE 0 END),
                              SUM(CASE WHEN priority IS NULL OR priority='' THEN 1 ELSE 0 END)
                       FROM directed_analysis_actions WHERE audit_id=?""",
                    (data.audit_id,),
                ).fetchone()
                counts = tuple(int(value or 0) for value in row)
    except sqlite3.Error:
        counts = None
    if counts is not None:
        total, high, unspecified = counts
        metrics.extend((
            _snapshot_indicator_633(
                "Ações direcionadas", total,
                "Ocorrências registradas; não são problemas únicos.",
                "directed-analysis.html#actions", f"Ver {total} ações",
            ),
            _snapshot_indicator_633(
                "Prioridade alta", high,
                "Prioridade já persistida, não recalculada.",
                "directed-analysis.html?priority=HIGH#actions",
                f"Ver {high} ações de prioridade alta",
            ),
            _snapshot_indicator_633(
                "Prioridade não definida", unspecified,
                "Ausência de classificação não equivale a baixa prioridade.",
                "directed-analysis.html?priority=UNDEFINED#actions",
                f"Ver {unspecified} ações sem prioridade",
            ),
        ))
    if not metrics:
        return (
            "<div class='notice'>Não há métricas executivas correspondentes "
            "materializadas. A ausência não é convertida em zero ou aprovação.</div>"
        )
    return (
        "<p class='section-lead'>Indicadores independentes e ações já persistidas. "
        "Os números não compõem um novo índice nem certificam conformidade. "
        "Cada cartão oferece acesso ao detalhe correspondente, sem criar novos dados "
        "ou pontuações. Laboratório, campo e prontidão mantêm escopos próprios.</p>"
        "<div class='metric-grid report-snapshot-grid'>" + "".join(metrics) + "</div>"
        "<p class='section-lead'>"
        "<a href='directed-analysis.html#objectives'>Ler por objetivo</a>"
        " · <a href='methodology.html'>Ver método e limitações</a>"
        "</p>"
    )

def _overview_body(database: Path, data: _ReportData) -> str:
    rows=[]
    catalog_statuses: dict[str, str] = {}
    for catalog in CATALOGS:
        status,tone,detail=_catalog_status(database,data,catalog.id)
        catalog_statuses[catalog.id] = str(status)
        page=CATALOG_PAGE_BY_ID[catalog.id]
        rows.append((_Html(f"<a href='{escape(page.filename)}'><strong>{escape(catalog.id)} · {escape(catalog.label)}</strong></a>"),_Html(_badge(status,tone)),detail))
    indexes=[]
    for r in data.scores:
        dim=str(r.get("dimension") or "")
        label=public_label(dim) or _DIMENSION_LABELS.get(dim,dim.replace("_"," ").title())
        ctx="SARI" if dim=="OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dim,"")
        link="sari.html" if dim=="OVERALL_READINESS" else CATALOG_PAGE_BY_ID[ctx].filename if ctx in CATALOG_PAGE_BY_ID else "metrics.html"
        score_value=_score_value(r)
        tone = _sari_public_tone(r) if dim == "OVERALL_READINESS" else _score_result_tone(score_value)
        indexes.append((_Html(f"<a href='{link}'>{escape(label)}</a>"),_result_value(score_value,tone),_device_label(r.get("device")),"Índice",_confidence_label(r.get("confidence"))))
    for cid in ("CAT-04","CAT-06","CAT-07"):
        for name,value,kind in _catalog_metric_rows(cid,_catalog_metrics(database,data,cid)):
            indexes.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[cid].filename}'>{escape(str(name))}</a>"),value,CATALOG_BY_ID[cid].label,kind,"-"))
    integrity="Íntegro" if data.config_hash and data.computed_hash==data.config_hash else "Plano não encontrado" if not data.config_hash else "Integridade divergente"
    diagnostic=_diagnostic_state_section(database,data,integrity)
    outline=(("snapshot","Retrato da auditoria"),("decision-matrix","Matriz decisória de evidências"),("catalogs","Catálogos"),("indices","Índices"),("integrity","Integridade"))
    if diagnostic:
        outline=(("diagnostic","Estado do diagnóstico"),)+outline
    body=_audit_hero(data,"Visão geral por catálogos","Resumo do plano congelado e dos resultados persistidos, mantendo coleta, análise e remediação em responsabilidades distintas.")
    body+=_outline((("experience","Navegar por objetivo"),)+outline)
    body+=diagnostic
    body+=_section("snapshot","O retrato da auditoria",_decision_snapshot_poc_633(database,data))
    body+=_section("experience","Explore a auditoria por objetivo",_experience_paths_633())
    body+=_section("catalogs","Catálogos da auditoria",_table(("Catálogo","Estado","Interpretação"),rows,sortable=True))
    from rasai.catalog_report_metrics import _web_observation
    from rasai.report_decision_matrix import (
        decision_evidence_matrix, decision_evidence_matrix_html,
    )
    web_observation = _web_observation(database, data.audit_id)
    serp_depth = _overview_serp_depth(database, data.audit_id)
    body+=_overview_measurement_scope_notice(
        web_observation, catalog_statuses,
        overall_scores=data.scores, serp_depth=serp_depth,
    )
    from rasai.optional_seo_interpretation import optional_seo_penalties
    scope_matrix = decision_evidence_matrix(
        audit_id=data.audit_id, scores=data.scores,
        web=web_observation, catalog_statuses=catalog_statuses,
        serp_depth=serp_depth,
        optional_seo_discounts=optional_seo_penalties(database, data.audit_id),
    )
    body+=_section(
        "decision-matrix", "Matriz decisória de evidências",
        decision_evidence_matrix_html(scope_matrix),
    )
    body+=_section("indices","Índices e métricas evidentes",_table(("Indicador","Valor","Contexto","Tipo","Confiança"),indexes,empty="Nenhum índice ou métrica reconhecido foi persistido.",sortable=bool(indexes))+"<p class='muted'>O inventário metodológico completo está em <a href='metrics.html'>Índices e métricas</a>.</p>")
    from rasai.optional_seo_interpretation import optional_seo_notice_html
    body+=optional_seo_notice_html(database, data.audit_id)
    from rasai.optional_seo_evidence_matrix import optional_seo_evidence_matrix_html
    body+=optional_seo_evidence_matrix_html(database, data.audit_id)
    body+=_section("integrity","Integridade e proveniência",f"<div class='metric-grid'>{_metric('Plano da execução',integrity)}{_metric('Fonte de verdade','Dados persistidos da auditoria')}{_metric('Contrato do relatório',CATALOG_REPORT_CONTRACT_VERSION)}</div><div class='notice'>O relatório organiza dados já persistidos. Ele não executa nova captura, integração, IA ou cálculo de pontuação.</div>")
    return body



def _sari_public_tone(row: Any) -> str:
    """Use the persisted readiness gates, never numeric quality alone."""
    from rasai.sari_readiness_presentation import public_readiness_condition

    condition, _status, _quality = public_readiness_condition(row)
    return {
        "expected": "good",
        "near": "warn",
        "below": "low",
        "critical": "bad",
        "neutral": "neutral",
    }.get(condition, "neutral")


def _sari_coverage_public(value: Any) -> str:
    """Display SARI coverage in human units without changing the stored ratio."""
    if value is None or isinstance(value, bool):
        return "Não determinada"
    try:
        ratio = float(value)
    except (TypeError, ValueError, OverflowError):
        return "Não determinada"
    if not isfinite(ratio) or not 0.0 <= ratio <= 1.0:
        return "Não determinada"
    percentage = f"{ratio * 100:.1f}".replace(".", ",")
    # Keep the canonical fraction for traceability to the physical scores row.
    return f"{percentage}% (fração {ratio:.6f})"


def _sari_partial_dimension_notice(scores: Sequence[Mapping[str, Any]]) -> str:
    """Surface measured partial dimensions without modifying the overall score."""
    rows = []
    for row in scores:
        dimension = str(row.get("dimension") or "")
        if not dimension or dimension == "OVERALL_READINESS":
            continue
        confidence = str(row.get("confidence") or "").upper()
        consolidation = str(row.get("consolidation_status") or "").upper()
        coverage = _sari_coverage_public(row.get("coverage"))
        raw_coverage = row.get("coverage")
        try:
            fraction = (
                float(raw_coverage)
                if raw_coverage is not None and not isinstance(raw_coverage, bool)
                else None
            )
        except (TypeError, ValueError, OverflowError):
            fraction = None
        full_coverage = fraction is not None and isfinite(fraction) and fraction == 1.0
        if confidence != "LOW" and consolidation != "PARTIAL" and full_coverage:
            continue
        label = public_label(dimension) or _DIMENSION_LABELS.get(dimension, dimension)
        rows.append((
            label,
            _device_label(row.get("device")),
            coverage,
            _confidence_label(confidence),
            _status_label(consolidation),
        ))
    if not rows:
        return ""
    return (
        "<div class='notice warn' data-contract='SARI-PARTIAL-DIMENSIONS-600'>"
        "<strong>Dimensões com medição parcial ou confiança baixa:</strong> "
        "confiança alta no agregado não implica confiança alta em todas as "
        "dimensões. Priorize a leitura de cada contexto antes da decisão.</div>"
        + _table(
            ("Dimensão", "Dispositivo", "Cobertura", "Confiança", "Consolidação"),
            rows, sortable=bool(rows),
        )
    )


def _sari_body(data: _ReportData) -> str:
    from rasai.catalog_report_public_labels import public_contract_label
    overall=[r for r in data.scores if _norm(r.get("dimension"))=="OVERALL_READINESS"]
    cards="".join(
        _metric_result(
            f"Índice de Prontidão · {_device_label(r.get('device'))}",
            _score_value(r),
            _sari_public_tone(r),
            f"Cobertura {_sari_coverage_public(r.get('coverage'))} · Confiança {_confidence_label(r.get('confidence'))}",
        )
        for r in overall
    )
    limitations=[]
    for r in overall:
        parsed=_safe_json(r.get("limitations"),[])
        for item in parsed if isinstance(parsed,list) else []:
            limitations.append((_device_label(r.get("device")),public_contract_label(item)))
    versions=sorted({str(r.get("scoring_version")) for r in data.scores if r.get("scoring_version")})
    body=_audit_hero(data,"Search & AI Readiness Index - Índice de Prontidão Search & IA","Índice persistido de prontidão, versão pública 001, com cobertura, confiança, dimensões e limitações. ID técnico: SARI-001. O HTML não recalcula o índice.")
    body+=_outline((("result","Resultado"),("composition","Composição"),("scope","Universo medido"),("limitations","Limitações"),("method","Método")))
    body+=_section("result","Resultado geral",f"<div class='metric-grid'>{cards or _metric('Índice de Prontidão','Sem pontuação persistida')}</div><div class='notice'>O SARI é um índice proprietário do RASAi, calculado sobre o escopo efetivamente auditado. A confiança expressa a força da avaliação no contrato de regras, não um intervalo de confiança estatística, nem certificação de indexação, posição no Google, inclusão em respostas generativas, desempenho, conformidade WCAG ou conformidade regulatória. O valor deve ser lido junto de cobertura, estados de cada dimensão e condições de validação persistidas.</div>")
    body+=_section("composition","Composição e dimensões",_sari_partial_dimension_notice(data.scores)+_score_table(data,include_overall=False))
    from rasai.report_decision_matrix import (
        decision_evidence_matrix, decision_evidence_matrix_html,
    )
    body+=_section(
        "scope", "Universo medido e limites de comparação",
        decision_evidence_matrix_html(decision_evidence_matrix(
            audit_id=data.audit_id, scores=data.scores,
            include_external=False,
        ))
        + "<p class='muted'>Para o confronto entre SARI, CrUX, Lighthouse, "
        "Apdex, SERP e verificações externas, consulte a "
        "<a href='index.html#decision-matrix'>matriz decisória na visão geral</a>."
        "</p>",
    )
    body+=_section("limitations","Limitações e critérios críticos persistidos",_table(("Contexto","Limitação / gate"),limitations,empty="Nenhuma limitação serializada foi encontrada."))
    body+=_section("method","Método aplicado",f"<div class='metric-grid'>{_metric('Versão pública','001')}{_metric('Contrato técnico',', '.join(versions) or '-')}{_metric('Fonte do valor','Pontuação persistida da auditoria')}{_metric('Recalcula no HTML?','Não')}</div><p>Pesos, fórmulas e condições de validação pertencem ao Método de Pontuação de Prontidão persistido. Consulte <a href='methodology.html'>Método de Pontuação de Prontidão</a>.</p>")
    return body


def _execution_evidence_body(database: Path, data: _ReportData) -> str:
    rows=[]
    for c in CATALOGS:
        status,tone,detail=_catalog_status(database,data,c.id)
        rows.append((c.id,c.label,"Sim" if c.id in data.selected else "Não",_Html(_badge(status,tone)),detail))
    integrity="Íntegro" if data.config_hash and data.computed_hash==data.config_hash else "Plano não encontrado" if not data.config_hash else "Integridade divergente"
    work_rows=[];modals=[]
    for i,r in enumerate(data.work_items,1):
        mid=f"fulfillment-{i}"
        work_status=_technical_work_status(r.get("status"))
        work_rows.append((_friendly_component(r.get("component")),work_status,_attempt_count_label(r.get("attempt_count")),_modal_button(mid,"Ver etapa")))
        modals.append(_modal(mid,_friendly_component(r.get("component")),"Etapa técnica persistida da execução",_kv((("Conclusão da etapa",work_status),("Tentativas registradas na etapa",_attempt_count_label(r.get("attempt_count"))),("Obrigatória","Sim" if r.get("required") else "Não"),("Escopo técnico",r.get("scope_key") or "-"),("Resultado",r.get("effective_result_ref") or "-"),("Último erro",r.get("last_error_message") or r.get("last_error_code") or "-"),("Identificador",r.get("work_item_id") or "-")))))
    body=_audit_hero(data,"Evidências da execução","O que foi solicitado, o estado funcional de cada catálogo e as etapas técnicas persistidas.")
    body+=_outline((("matrix","Plano × execução"),("integrity","Plano congelado"),("technical","Etapas técnicas")))
    body+=_section("matrix","Plano × execução",_table(("Catálogo","Contexto","Selecionado","Estado funcional","Interpretação"),rows,sortable=True))
    body+=_section("integrity","Plano congelado",f"<div class='metric-grid'>{_metric('Integridade',integrity)}{_metric('Catálogos selecionados',len(data.selected))}{_metric('Etapas técnicas persistidas',len(data.work_items))}{_metric('Resultado lógico',_audit_state(data))}</div><p class='muted'>Ausência de plano é estado indeterminado; nunca é convertida em “não solicitado”.</p>")
    body+=_section("technical","Etapas técnicas",_table(("Etapa","Conclusão técnica","Tentativas","Detalhe"),work_rows,empty="Nenhuma etapa técnica persistida.",sortable=bool(work_rows))+"".join(modals)+"<p class='muted'>Conclusão técnica indica se a etapa executou. O estado funcional do catálogo pode permanecer parcial quando a própria metodologia considera a cobertura insuficiente, como em um grupo Apdex pequeno.</p>")
    return body


__all__ = [name for name in globals() if not name.startswith("__")]
