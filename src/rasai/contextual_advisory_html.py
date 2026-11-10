"""One set of page-specific panels for new reports and private companions.

Public panels deliberately exclude arbitrary captured literals/URLs. Physical
text/attributes remain inspectable only in the private companion and its JSON.
"""
from collections import defaultdict
from html import escape
import re
from rasai.contextual_semantics import DISPLAY_LABELS, BASIS_LABELS

LABELS = dict(MAIN_CONTENT="Conteúdo principal", FAQ_QUESTION="FAQ — pergunta",
    FAQ_ANSWER="FAQ — resposta vinculada", COMMERCIAL_CANDIDATE="Sinal comercial",
    DOCUMENT_REFERENCE="Referência documental candidata", CTA="Chamada à ação",
    NAVIGATION="Navegação / menu", FOOTER="Rodapé", SOCIAL="Destino de rede social",
    FRAGMENT_ACTION="Fragmento / ação", TEXT_MENTION="Menção textual", UNKNOWN="Indeterminado")
PAGES = {"index.html": "Síntese consultiva", "capture-context.html": "Captura e contexto",
         "cat-03.html": "Conteúdo e FAQ", "cat-05.html": "Observações Search",
         "geo.html": "Evidências GEO", "cat-08.html": "Oportunidades consultivas",
         "cat-09.html": "Remediações editoriais"}


def _e(value):
    return escape("N/D" if value is None else str(value), quote=True)


def _quantity(count, singular, plural):
    return _e(count) + " " + (singular if count == 1 else plural)


def _t(value):
    """Wrap hostile long literals without injecting markup into attributes."""
    raw = "N/D" if value is None else str(value)
    return "<wbr>".join(_e(part) for part in re.split(r"(\S{32})", raw))


def _reasons(values):
    # Technical codes are disclosure details, never substituted for pt-BR copy.
    return "<details><summary>Razões e limitações técnicas</summary><ul>" + "".join(
        "<li><code>" + _e(v).replace("_", "_<wbr>") + "</code></li>" for v in values) + "</ul></details>"


def _inventory(report, *, private, semantic=False):
    content = ""
    for capture in report["captures"]:
        groups = defaultdict(list)
        for occurrence in capture["occurrences"]:
            if semantic and occurrence["category"] not in {"MAIN_CONTENT", "FAQ_QUESTION", "FAQ_ANSWER", "COMMERCIAL_CANDIDATE", "TEXT_MENTION"}:
                continue
            groups[occurrence["category"]].append(occurrence)
        content += "<section class='panel'><h3>Captura · " + _e(capture["device"]) + "</h3>"
        content += "<p>Ocorrências: " + _e(capture["counts"]["observed_occurrences"]) + " · destinos distintos: " + _e(capture["counts"]["distinct_destinations"])
        content += " · candidatos documentais: " + _e(capture["counts"]["potentially_documentary"]) + " · indeterminados: " + _e(capture["counts"]["unknown"]) + " · omitidos: " + _e(capture["counts"]["omitted"]) + ".</p>"
        content += _reasons(capture["limitations"])
        for category, rows in groups.items():
            content += "<details><summary>" + _e(LABELS[category]) + " · " + str(len(rows)) + "</summary>"
            if private:
                by_destination = defaultdict(list)
                for row in rows:
                    by_destination[row["resolved_url"] or row["href_literal"] or row["occurrence_id"]].append(row)
                for destination, occurrences in by_destination.items():
                    content += "<details><summary>" + _t(occurrences[0]["text"] or "Texto não observado") + " · " + _quantity(len(occurrences), "ocorrência", "ocorrências") + "</summary>"
                    for row in occurrences:
                        content += "<article id='" + _e(row["occurrence_id"]) + "'><h4>Ocorrência observada</h4><dl class='kv'>"
                        values = {"Texto literal extraído": row["text"], "Href literal": row["href_literal"],
                            "URL resolvida (não visitada)": row["resolved_url"], "Atributo aria-label": row["aria_label"],
                            "Texto alternativo capturado": row["alternative_text"], "Contexto": row["context"],
                            "Base da categoria": row["category_basis"], "Posição no HTML decodificado": row["text_range"],
                            "Pergunta vinculada": row["faq_question_ref"], "Evidência": row["occurrence_id"],
                            "Fonte": capture["source_ref"], "SHA-256": capture["source_sha256"],
                            "Snapshot": capture["snapshot_id"], "Página": capture["page_id"],
                            "Instante": capture["captured_at"], "Superfície": capture["surface"]}
                        content += "".join("<dt>" + _e(k) + "</dt><dd>" + _t(v) + "</dd>" for k, v in values.items())
                        content += "</dl>" + _reasons(row["limitations"]) + "</article>"
                    content += "</details>"
            else:
                content += "<p>Textos e URLs capturados disponíveis no companheiro privado. Sem inferência de entidades ou produtos autenticados.</p>"
            content += "</details>"
        content += "</section>"
    return content or "<p>N/D — nenhuma captura elegível disponível.</p>"


def _v1_panel(report, page, *, private=False):
    if page not in PAGES:
        return ""
    body = "<section class='panel' id='contextual-content'><h2>" + _e(PAGES[page]) + " — contexto GEO/SEO</h2>"
    body += "<p>Observações consultivas de capturas existentes, sem pontuação. Referência não autentica documento; Search API não prova citação generativa. IA desativada ou não autorizada.</p>"
    if page == "index.html":
        body += "<p>" + _quantity(len(report["captures"]), "captura", "capturas") + " e " + _quantity(len(report["recommendations"]), "hipótese técnica v1", "hipóteses técnicas v1") + " no histórico de compatibilidade.</p><ul>"
        body += "".join("<li><a href='" + filename + "#contextual-content'>" + label + "</a></li>" for filename, label in PAGES.items() if filename != page) + "</ul>"
    elif page in {"capture-context.html", "cat-03.html"}:
        body += _inventory(report, private=private, semantic=page == "cat-03.html")
    elif page in {"cat-05.html", "geo.html"}:
        body += "<p>N/D para equivalência contextual entre fontes: mercado, idioma, dispositivo e intenção precisam de comprovação física conjunta. Ausência de comparabilidade não equivale a zero.</p>"
        search = report["search"]
        body += _reasons([search["reason"], *search["limitations"]])
        for row in search["observations"]:
            body += "<details><summary>Consulta persistida · " + ("observação descritiva" if row["status"] == "DESCRIPTIVE_ONLY" else "N/D") + "</summary>"
            if private:
                body += "<p>Consulta: " + _t(row["query"]) + " · execuções: " + _t(row["source_run_ids"]) + " · evidências: " + _t(row["evidence_ids"]) + " · instantes: " + _t(row["timestamps"]) + "</p>"
            body += _reasons([row["reason"], *row["limitations"]]) + "</details>"
    else:
        if not report["recommendations"]:
            body += "<p>N/D — sem oportunidade determinística sustentada; não significa ausência de melhoria.</p>"
        history = {h["v1_recommendation_id"]: h for h in report.get("semantic_v2", {}).get("recommendation_history", [])}
        for row in report["recommendations"]:
            body += "<details><summary>" + _e(row["problem"]) + "</summary><p>Hipótese editorial parcial, baseada em referência local observada; sem prioridade numérica.</p>"
            if row["recommendation_id"] in history:
                disposition = history[row["recommendation_id"]]
                body += "<p>Qualificação v2: " + ("não acionável" if disposition["not_actionable"] else "somente contextual; ação N/D") + ". "
                body += " ".join(_e(BASIS_LABELS[b]) for b in disposition["basis"]) + "</p>"
            if private:
                body += "<p>Texto observado: " + _t(row["observed_text"]) + " · local: " + _t(row["scope"]) + " " + _t(row["location"]) + "</p><ul>"
                body += "".join("<li><a href='capture-context.html#" + _e(ref["occurrence_id"]) + "'>Ver ocorrência</a> · SHA-256 " + _t(ref["source_sha256"]) + "</li>" for ref in row["evidence_refs"]) + "</ul>"
            if page == "cat-09.html":
                body += "<p>Ajuste sugerido: " + _e(row["suggested_change"]) + "</p><p>Como validar: " + _e(row["expected_validation"]) + "</p>"
            else:
                body += "<p><a href='cat-09.html#contextual-content'>Ajuste sugerido e validação editorial</a></p>"
            body += _reasons(row["limitations"]) + "</details>"
    return body + "</section>"


def _v2_panel(report, page, *, private):
    overlay = report.get("semantic_v2")
    body = "<section class='panel' id='contextual-semantic-v2'><h2>Qualificação semântica v2</h2>"
    body += "<p>Complemento ao inventário e às hipóteses v1, preservados no histórico abaixo. Leitura do markup capturado; visibilidade computada e intenção editorial não autenticadas. Contexto qualificado não equivale a problema editorial, ganho GEO/SEO ou alteração de score.</p>"
    if overlay is None:
        return body + "<p>N/D - qualificação v2 indisponível; os registros v1 continuam disponíveis.</p></section>"
    counts = overlay["counts"]
    recs = overlay["recommendation_counts"]
    body += "<p>" + _quantity(len(report["captures"]), "captura", "capturas") + " · " + _quantity(counts["raw"], "ocorrência v1 preservada", "ocorrências v1 preservadas") + ".</p>"
    if counts["observed_v1"] is None:
        body += "<p>N/D - total de observações não comprovado. Os contadores v2 cobrem somente os registros v1 disponíveis; não comprovam ausência de conteúdo.</p>"
    elif counts["observed_v1"] != counts["raw"]:
        body += "<p>Projeção parcial: os limites v1 foram preservados. A qualificação cobre somente as ocorrências disponíveis, sem extrapolar os registros omitidos.</p>"
    body += "<dl class='kv'><dt>Observações com contexto qualificado</dt><dd>" + _e(counts["qualified"]) + "</dd><dt>Controles / navegação não acionáveis</dt><dd>" + _e(counts["not_actionable"]) + "</dd><dt>Função editorial N/D</dt><dd>" + _e(counts["nd"]) + "</dd></dl>"
    if page == "index.html":
        body += "<p>" + _quantity(recs["raw"], "hipótese técnica v1 preservada", "hipóteses técnicas v1 preservadas") + "; " + _quantity(recs["qualified"], "ação editorial v2 sustentada", "ações editoriais v2 sustentadas") + ". Sem prova adicional de lacuna, a indicação de melhoria permanece N/D.</p><ul>"
        body += "".join("<li><a href='" + name + "#contextual-semantic-v2'>" + label + "</a></li>" for name, label in PAGES.items() if name != page) + "</ul>"
    elif page in {"capture-context.html", "cat-03.html"}:
        body += "<p>FAQ editorial observada: " + _quantity(counts["faq_questions"], "pergunta", "perguntas") + " e " + _quantity(counts["faq_answers"], "resposta vinculada", "respostas vinculadas") + ". Pergunta sem resposta comprovada permanece N/D.</p>"
        groups = defaultdict(list)
        for diagnosis in overlay["diagnoses"]:
            groups[diagnosis["display_category_v2"]].append(diagnosis)
        literals = {o["occurrence_id"]: o for c in report["captures"] for o in c["occurrences"]} if private else {}
        for category, diagnoses in groups.items():
            body += "<details><summary>" + _e(DISPLAY_LABELS[category]) + " · " + _quantity(len(diagnoses), "ocorrência", "ocorrências") + "</summary><div class='detail-body'>"
            for code in sorted({b for d in diagnoses for b in d["basis"]}):
                body += "<p>" + _e(BASIS_LABELS[code]) + "</p>"
            if private:
                for diagnosis in diagnoses:
                    row = literals[diagnosis["occurrence_id"]]
                    body += "<details id='v2-" + _e(row["occurrence_id"]) + "'><summary>" + _t(row["text"] or "Texto não observado") + "</summary><div class='detail-body'><p>Classificação estrutural v1: " + _e(LABELS[row["category"]]) + ". Qualificação v2: " + _e(DISPLAY_LABELS[category]) + ".</p><p><a href='capture-context.html#" + _e(row["occurrence_id"]) + "'>Ver registro bruto v1, posição, contexto e hash</a></p>"
                    if diagnosis["faq_question_ref_v2"]:
                        body += "<p><a href='capture-context.html#v2-" + _e(diagnosis["faq_question_ref_v2"]) + "'>Pergunta fisicamente vinculada</a></p>"
                    body += "</div></details>"
            body += "</div></details>"
    elif page in {"cat-05.html", "geo.html"}:
        body += "<p>A qualificação v2 usa somente o contexto local. As observações Search e suas razões originais são preservadas abaixo; equivalência externa continua N/D. Search API não comprova citação generativa.</p>"
    else:
        body += "<dl class='kv'><dt>Hipóteses técnicas v1 preservadas</dt><dd>" + _e(recs["raw"]) + "</dd><dt>Ações editoriais v2 sustentadas</dt><dd>" + _e(recs["qualified"]) + "</dd><dt>Hipóteses não acionáveis</dt><dd>" + _e(recs["not_actionable"]) + "</dd><dt>Hipóteses somente contextuais / ação N/D</dt><dd>" + _e(recs["nd"]) + "</dd></dl>"
        body += "<p>N/D - não foi comprovada lacuna editorial adicional para gerar ação v2. Voltar ao topo, controles e âncoras interrogativas não são problemas GEO/SEO por si só. As hipóteses v1 continuam consultáveis, com sua disposição v2, no histórico.</p>"
    return body + "</section>"


def contextual_panel(report, page, *, private=False):
    if page not in PAGES:
        return ""
    # Existing engine/catalog bodies live outside this additive panel and are
    # never filtered. v1 facts/hypotheses stay in JSON and compatibility HTML.
    v1 = _v1_panel(report, page, private=private)
    v2 = _v2_panel(report, page, private=private)
    if page in {"cat-05.html", "geo.html"}:
        return v2 + v1  # Search retains its existing presentation and N/D reasons.
    return ("<section class='panel' id='contextual-qualification'>" + v2
        + "<details id='contextual-v1-history'><summary>Histórico técnico v1 e compatibilidade - hipóteses estruturais, não diagnóstico editorial validado</summary>"
        + "<div class='detail-body'>" + v1 + "</div></details></section>")


def companion_pages(report):
    from rasai.catalog_report_style import _CSS
    pages = {"css/site.css": _CSS}
    nav = "<aside class='app-nav'><div class='brand'>Companheiro privado</div><nav aria-label='Relatório companheiro'>" + "".join(
        "<a href='" + name + "'>" + label + "</a>" for name, label in PAGES.items()) + "</nav></aside>"
    for name, label in PAGES.items():
        pages[name] = ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
            "<link rel='stylesheet' href='css/site.css'><title>Companheiro privado · " + _e(label) + "</title></head><body>"
            + nav + "<main class='app-main'><h1>Companheiro privado — " + _e(label) + "</h1><p>Derivado externo; relatório histórico preservado. Não publicar: contém texto capturado não confiável.</p>"
            + contextual_panel(report, name, private=True) + "</main></body></html>")
    return pages
