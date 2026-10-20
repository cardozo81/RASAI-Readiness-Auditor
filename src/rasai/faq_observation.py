"""Read-only, bounded interpretation of FAQ accordion visibility (#601).

This diagnostic never clicks links, modifies the DOM, runs JavaScript or changes
SARI. A collapsed, unmounted panel is not proof the publisher omitted an answer,
and a response available only after a click is not proved accessible to crawlers.
"""
from __future__ import annotations

from contextlib import closing
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

_FAQ_CONTEXT = re.compile(r"faq|frequent(?:ly)?asked|perguntas?frequentes?|questions?", re.I)
_MAX_HTML_BYTES = 4_000_000
_MAX_SNAPSHOTS = 12
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})
_NON_CONTENT_TAGS = frozenset({"script", "style", "template", "noscript"})


class _AccordionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.id_counts: dict[str, int] = {}
        self.ids_with_dom_text: set[str] = set()
        self.controls: list[tuple[str, str]] = []
        self._open: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ids = [str(value).strip() for name, value in attrs
               if name == "id" and value is not None and str(value).strip()]
        # Duplicate id= attributes on the same node are as ambiguous as
        # distinct nodes reusing one IDREF; dict(attrs) loses that evidence.
        for candidate in ids:
            self.ids.add(candidate)
            self.id_counts[candidate] = (
                self.id_counts.get(candidate, 0)
                + (len(ids) if len(ids) > 1 else 1)
            )
        element_id = ids[0] if len(ids) == 1 else ""
        targets = [value for name, value in attrs if name == "aria-controls"]
        expanded_values = [value for name, value in attrs if name == "aria-expanded"]
        expanded = (
            str(expanded_values[0] or "").strip().lower()
            if len(expanded_values) == 1 else "ambiguous"
        )
        # One aria-controls attribute can contain multiple IDREFs. They do
        # not identify one uniquely attributable FAQ panel. Duplicate HTML
        # attributes are likewise ambiguous, never silently ignored.
        for raw in targets:
            parts = str(raw or "").split()
            for target in dict.fromkeys(parts):
                if _FAQ_CONTEXT.search(target):
                    state = expanded if len(targets) == 1 and len(parts) == 1 else "ambiguous"
                    self.controls.append((target, state))
        if tag not in _VOID_TAGS:
            self._open.append((tag, element_id))

    def handle_endtag(self, tag: str) -> None:
        # HTML can contain unbalanced nesting. Drop the nearest matching
        # frame and its descendants rather than attributing distant text
        # to a long-closed panel.
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index][0] == tag:
                del self._open[index:]
                break

    def handle_data(self, data: str) -> None:
        if not data.strip() or any(tag in _NON_CONTENT_TAGS for tag, _ in self._open):
            return
        for _tag, element_id in self._open:
            if element_id:
                self.ids_with_dom_text.add(element_id)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)


def inspect_faq_dom_states(html: str) -> dict[str, int]:
    parser = _AccordionParser()
    parser.feed(html)
    # A last-write-wins dictionary would invent a single truth if duplicate
    # controls disagree about expanded state or multiple nodes share an id.
    states: dict[str, set[str]] = {}
    control_counts: dict[str, int] = {}
    for target, expanded in parser.controls:
        states.setdefault(target, set()).add(expanded)
        control_counts[target] = control_counts.get(target, 0) + 1
    ambiguous = {
        target for target, expanded_states in states.items()
        if control_counts[target] != 1
        or len(expanded_states) != 1
        or not expanded_states.issubset({"true", "false"})
        or parser.id_counts.get(target, 0) > 1
    }
    collapsed = [
        target for target, values in states.items()
        if target not in ambiguous and values == {"false"}
    ]
    expanded = [
        target for target, values in states.items()
        if target not in ambiguous and values == {"true"}
    ]
    return {
        "controls": len(states),
        "ambiguous": len(ambiguous),
        "collapsed": len(collapsed),
        "unmounted": sum(target not in parser.ids for target in collapsed),
        "mounted": sum(target in parser.ids for target in collapsed),
        "mounted_with_text": sum(target in parser.ids_with_dom_text for target in collapsed),
        "mounted_without_text": sum(
            target in parser.ids and target not in parser.ids_with_dom_text
            for target in collapsed
        ),
        # Expanded panels are still merely DOM state at the captured instant;
        # they do not attest a physical click or that a crawler saw an answer.
        "expanded": len(expanded),
        "expanded_with_text": sum(
            target in parser.ids_with_dom_text for target in expanded
        ),
        "expanded_without_text": sum(
            target in parser.ids and target not in parser.ids_with_dom_text
            for target in expanded
        ),
        "expanded_unmounted": sum(
            target not in parser.ids for target in expanded
        ),
    }


def inspect_faq_html(html: str) -> dict[str, int]:
    """Original seven-field public contract retained for legacy callers."""
    observed = inspect_faq_dom_states(html)
    return {key: observed[key] for key in (
        "controls", "ambiguous", "collapsed", "unmounted", "mounted",
        "mounted_with_text", "mounted_without_text",
    )}



# FAQPage JSON-LD is a distinct, non-interactive source of structured claims.
# It is not proof that text is rendered, crawler-accessible or editorially true.
_MAX_JSONLD_SCRIPTS = 16
_MAX_JSONLD_CHARS = 128_000
_MAX_JSONLD_ENTRIES = 200


class _JsonLdInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.documents: list[str] = []
        self.active = False
        self.fragments: list[str] = []
        self.used = 0
        self.overflow = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        types = [value for name, value in attrs if name == "type"]
        self.active = (
            len(types) == 1 and isinstance(types[0], str)
            and types[0].split(";", 1)[0].strip().lower() == "application/ld+json"
        )
        self.fragments = []

    def handle_data(self, data: str) -> None:
        if self.active:
            self.used += len(data)
            if self.used > _MAX_JSONLD_CHARS:
                self.overflow = True
            else:
                self.fragments.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script":
            return
        if self.active:
            if len(self.documents) >= _MAX_JSONLD_SCRIPTS:
                self.overflow = True
            else:
                self.documents.append("".join(self.fragments))
        self.active = False
        self.fragments = []


def _unique_jsonld_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate JSON-LD key")
        result[name] = value
    return result


def _reject_jsonld_constant(value: str) -> None:
    raise ValueError("invalid JSON-LD numeric constant")


def inspect_faq_jsonld(html: str) -> dict[str, Any]:
    """Bounded markup inventory; no URL fetch, scoring or crawler assertion."""
    unavailable = {
        "status": "JSONLD_UNVERIFIABLE",
        "faqpage_entries": None,
        "question_entries": None,
        "answers_with_text": None,
    }
    if not isinstance(html, str) or len(html.encode("utf-8")) > _MAX_HTML_BYTES:
        return unavailable
    parser = _JsonLdInventory()
    try:
        parser.feed(html)
        parser.close()
        # A truncated JSON-LD script cannot be counted as "zero FAQPage".
        # A source whose structured payload was never closed is inconclusive.
        if parser.overflow or parser.active:
            return unavailable
        faqpages = questions = answers = 0
        for document in parser.documents:
            value = json.loads(
                document, object_pairs_hook=_unique_jsonld_pairs,
                parse_constant=_reject_jsonld_constant,
            )
            roots = value if isinstance(value, list) else [value]
            nodes: list[Any] = []
            for root in roots:
                nodes.append(root)
                if isinstance(root, dict) and "@graph" in root:
                    graph = root["@graph"]
                    if not isinstance(graph, list):
                        return unavailable
                    nodes.extend(graph)
                if len(nodes) > _MAX_JSONLD_ENTRIES:
                    return unavailable
            for item in nodes:
                if not isinstance(item, dict):
                    continue
                types = item.get("@type")
                declared = types if isinstance(types, list) else [types]
                if "FAQPage" not in declared:
                    continue
                faqpages += 1
                members = item.get("mainEntity") or []
                members = members if isinstance(members, list) else [members]
                if len(members) > _MAX_JSONLD_ENTRIES:
                    return unavailable
                for question in members:
                    if not isinstance(question, dict):
                        continue
                    type_ = question.get("@type")
                    if type_ != "Question" and (
                        not isinstance(type_, list) or "Question" not in type_
                    ):
                        continue
                    questions += 1
                    accepted = question.get("acceptedAnswer")
                    candidates = accepted if isinstance(accepted, list) else [accepted]
                    if any(
                        isinstance(answer, dict)
                        and isinstance(answer.get("text"), str)
                        and bool(answer["text"].strip())
                        for answer in candidates
                    ):
                        answers += 1
        return {
            "status": "JSONLD_PARSED",
            "faqpage_entries": faqpages,
            "question_entries": questions,
            "answers_with_text": answers,
        }
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return unavailable


def _safe_rendered_file(root: Path, ref: Any) -> Path | None:
    relative = str(ref or "").replace("\\", "/")
    if not relative.startswith("artifacts/rendered/"):
        return None
    source = root / relative
    candidate = source.resolve()
    if source.is_symlink() or not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return None
    if candidate.stat().st_size > _MAX_HTML_BYTES:
        return None
    return candidate


def faq_observation_html(database: Any, audit_id: str) -> str:
    """Only add a factually bounded, non-scoring CAT-03 diagnostic."""
    source = Path(database)
    root = source.parent
    if (source.is_symlink() or not source.is_file() or any(
        (source.parent / (source.name + suffix)).exists()
        for suffix in ("-wal", "-shm", "-journal")
    )):
        return ""
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            from rasai.faq_snapshot_scope import read_faq_snapshot_scopes
            rows, incomplete, source_status = read_faq_snapshot_scopes(
                connection, audit_id, limit=_MAX_SNAPSHOTS,
            )
    except sqlite3.Error:
        return ""
    if source_status == "AMBIGUOUS_SNAPSHOT_ID":
        return (
            "<div class='subsection' data-contract='FAQ-OBSERVATION-601-001'>"
            "<h3>FAQ interativo — N/D</h3>"
            "<p>Snapshot IDs ausentes ou duplicados: N/D. "
            "Não inferir ausência editorial.</p></div>"
        )
    if source_status != "OBSERVATIONAL_SCOPE_ONLY":
        return ""
    if not rows:
        return ""
    unreadable = 0
    no_controls = 0
    observations: list[dict[str, int]] = []
    sources: list[tuple[str, dict[str, int]]] = []
    jsonld_sources: list[dict[str, Any]] = []
    for record in rows:
        snapshot_id, ref = record.snapshot_id, record.artifact_ref
        try:
            rendered = _safe_rendered_file(root, ref)
            if rendered is None:
                unreadable += 1
                continue
            snapshot_html = rendered.read_text(encoding="utf-8")
            counts = inspect_faq_dom_states(snapshot_html)
            jsonld_sources.append(inspect_faq_jsonld(snapshot_html))
        except (OSError, UnicodeError, ValueError):
            unreadable += 1
            continue
        if counts["controls"]:
            observations.append(counts)
            sources.append((record, counts))
        else:
            no_controls += 1
    coverage = (
        f"{len(rows)} captura(s) examinada(s), máximo {_MAX_SNAPSHOTS}; "
        f"{len(observations)} com FAQ reconhecido; "
        f"{no_controls} sem controle reconhecido; "
        f"{unreadable} inacessível(is). "
        + ("Há capturas adicionais fora do limite; cobertura parcial da AUD."
           if incomplete else "Observação limitada aos snapshots físicos.")
    )
    structured_valid = all(
        record["status"] == "JSONLD_PARSED" for record in jsonld_sources
    )
    structured_counts = (
        (
            sum(item["faqpage_entries"] for item in jsonld_sources),
            sum(item["question_entries"] for item in jsonld_sources),
            sum(item["answers_with_text"] for item in jsonld_sources),
        )
        if jsonld_sources and structured_valid else None
    )
    structured_notice = (
        "<p data-contract='FAQ-JSONLD-601'>"
        "<strong>FAQPage JSON-LD (marcação estruturada):</strong> "
        + (
            f"{structured_counts[0]} entrada(s) FAQPage; "
            f"{structured_counts[1]} entrada(s) Question; "
            f"{structured_counts[2]} com texto acceptedAnswer na marcação."
            if structured_counts is not None else "N/D — marcação não verificável."
        )
        + " Esses números se referem exclusivamente às capturas legíveis "
        "examinadas, não ao universo da AUD. Marcação JSON-LD não comprova "
        "texto montado no DOM, resposta após clique, acesso pelo Googlebot, "
        "indexação ou correção editorial.</p>"
    )
    if not observations:
        return (
            "<div class='subsection' data-contract='FAQ-OBSERVATION-601-001'>"
            "<h3>FAQ interativo — N/D</h3><p>" + escape(coverage) + "</p>"
            + structured_notice +
            "<p>FAQ não identificável nesta amostra; não comprova "
            "ausência editorial ou ausência de resposta após clique.</p></div>"
        )
    total = sum(item["controls"] for item in observations)
    ambiguous = sum(item["ambiguous"] for item in observations)
    collapsed = sum(item["collapsed"] for item in observations)
    unmounted = sum(item["unmounted"] for item in observations)
    mounted = sum(item["mounted"] for item in observations)
    mounted_with_text = sum(item["mounted_with_text"] for item in observations)
    mounted_without_text = sum(item["mounted_without_text"] for item in observations)
    expanded = sum(item["expanded"] for item in observations)
    expanded_with_text = sum(item["expanded_with_text"] for item in observations)
    expanded_without_text = sum(item["expanded_without_text"] for item in observations)
    expanded_unmounted = sum(item["expanded_unmounted"] for item in observations)
    provenance = "".join(
        "<tr><td><code>" + escape(record.snapshot_id) + "</code></td>"
        + "<td><code>" + escape(record.page_id) + "</code></td>"
        + "<td>" + escape(record.device) + "</td>"
        + "<td>" + escape(record.requested_url) + "</td>"
        + "<td>" + escape(record.final_url) + "</td>"
        + f"<td>{counts['controls']}</td><td>{counts['ambiguous']}</td>"
        + f"<td>{counts['collapsed']}</td><td>{counts['unmounted']}</td>"
        + f"<td>{counts['mounted_with_text']}</td>"
        + f"<td>{counts['mounted_without_text']}</td>"
        + f"<td>{counts['expanded']}</td>"
        + f"<td>{counts['expanded_with_text']}</td>"
        + f"<td>{counts['expanded_unmounted']}</td></tr>"
        for record, counts in sources
    )
    return (
        "<div class='subsection' data-contract='FAQ-OBSERVATION-601-001'>"
        "<h3>FAQ interativo — limite da captura</h3>"
        "<p><strong>Cobertura física:</strong> " + escape(coverage) + "</p>"
        + structured_notice +
        "<p><strong>Capacidade sem interação:</strong> somente texto "
        "persistido no DOM inicial pode ser observado; nenhuma consulta "
        "a crawler foi realizada. <strong>Disponibilidade após clique:</strong> "
        "N/D quando não existe recibo autenticado de interação do mesmo "
        "contexto físico. Não equiparar esses dois resultados.</p>"
        f"<p>Foram identificados {total} alvo(s) distintos associados a FAQ, "
        f"{ambiguous} com estado/ID ambíguo(s) e {collapsed} recolhido(s) sem ambiguidade; "
        f"entre estes, {unmounted} painel(is) "
        f"não estavam presentes no DOM capturado e {mounted} tinham um alvo no DOM "
        f"({mounted_with_text} com texto recuperável no DOM e {mounted_without_text} sem texto recuperável). "
        f"Em estado expandido na captura havia {expanded} painel(is): "
        f"{expanded_with_text} com texto DOM, {expanded_without_text} sem texto DOM "
        f"e {expanded_unmounted} sem painel montado. Estado expandido não "
        "comprova gesto de clique nem visibilidade a mecanismos de busca.</p>"
        "<details><summary>Proveniência por captura</summary>"
        "<div class='table-wrap'><table><thead><tr><th>Snapshot ID</th>"
        "<th>Page ID</th><th>Dispositivo</th><th>URL solicitada</th>"
        "<th>URL final</th><th>FAQ</th>"
        "<th>Ambíguos</th><th>Recolhidos</th><th>Painéis ausentes</th><th>Com texto DOM</th>"
        "<th>Sem texto DOM</th><th>Expandidos</th>"
        "<th>Expandidos com texto</th><th>Expandidos sem painel</th>"
        "</tr></thead><tbody>"
        + provenance + "</tbody></table></div></details>"
        "<p class='muted'>IDs duplicados, estados contraditórios ou controles malformados "
        "são classificados como ambíguos e não entram nas contagens de painéis. "
        "A existência de texto em painel recolhido significa somente que ele "
        "estava no DOM desta captura; não comprova que fosse visível, indexado ou correto. "
        "Identidades de URL e dispositivo provêm somente do snapshot persistido; "
        "N/D indica legado/identidade ausente ou inválida, nunca prova de URL. "
        "A auditoria não abriu esses controles nesta observação. "
        "Painel não materializado não prova ausência editorial de resposta. "
        "Painel disponível após clique também não comprova acesso sem interação "
        "por robôs de busca. Esta leitura não altera BR-GEO-039, BR-GEO-049, "
        "SARI, evidências ou pontuações persistidas; os resultados semânticos "
        "devem ser interpretados à luz dessa limitação.</p></div>"
    )
