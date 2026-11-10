"""One set of page-specific panels for new reports and private companions.

Public panels deliberately exclude arbitrary captured literals/URLs. Physical
text/attributes remain inspectable only in the private companion and its JSON.
"""
from collections import defaultdict
from html import escape
import re

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
                    content += "<details><summary>" + _t(occurrences[0]["text"] or "Texto não observado") + " · " + str(len(occurrences)) + " ocorrência(s)</summary>"
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


def contextual_panel(report, page, *, private=False):
    if page not in PAGES:
        return ""
    body = "<section class='panel' id='contextual-content'><h2>" + _e(PAGES[page]) + " — contexto GEO/SEO</h2>"
    body += "<p>Observações consultivas de capturas existentes, sem pontuação. Referência não autentica documento; Search API não prova citação generativa. IA desativada ou não autorizada.</p>"
    if page == "index.html":
        body += "<p>" + str(len(report["captures"])) + " captura(s) e " + str(len(report["recommendations"])) + " oportunidade(s) editorial(is) com vínculo físico.</p><ul>"
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
        for row in report["recommendations"]:
            body += "<details><summary>" + _e(row["problem"]) + "</summary><p>Hipótese editorial parcial, baseada em referência local observada; sem prioridade numérica.</p>"
            if private:
                body += "<p>Texto observado: " + _t(row["observed_text"]) + " · local: " + _t(row["scope"]) + " " + _t(row["location"]) + "</p><ul>"
                body += "".join("<li><a href='capture-context.html#" + _e(ref["occurrence_id"]) + "'>Ver ocorrência</a> · SHA-256 " + _t(ref["source_sha256"]) + "</li>" for ref in row["evidence_refs"]) + "</ul>"
            if page == "cat-09.html":
                body += "<p>Ajuste sugerido: " + _e(row["suggested_change"]) + "</p><p>Como validar: " + _e(row["expected_validation"]) + "</p>"
            else:
                body += "<p><a href='cat-09.html#contextual-content'>Ajuste sugerido e validação editorial</a></p>"
            body += _reasons(row["limitations"]) + "</details>"
    return body + "</section>"


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
