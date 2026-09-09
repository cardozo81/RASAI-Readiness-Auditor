"""Static Search Intelligence report built from persisted observation evidence.

The report is read-only. It projects provider SERP evidence, deterministic RASAi
classification/content evidence and, when present, persisted semantic-analysis records.
It never converts those observations into SARI-001 or SCORE-GEO-004.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from rasai.report_navigation import normalize_report_navigation, render_report_navigation


REPORT_FILE = "search-intelligence.html"

# This list is deliberately additive. The semantic implementation is evolving in a
# separate feature branch. The report can expose a compatible persisted table as soon
# as it lands without making that table a hard dependency of SERP Observation.
_SEMANTIC_TABLE_CANDIDATES = (
    "serp_competitive_semantic_analyses",
    "serp_semantic_competitive_analyses",
    "search_intelligence_semantic_analyses",
)


def write_search_intelligence_report(workspace_root: str | Path) -> Path | None:
    """Render Search Intelligence when at least one persisted SERP observation exists.

    Returning ``None`` is intentional when the workspace has no Search Intelligence
    evidence yet, keeping the report surface optional and the canonical navigation clean.
    """
    root = Path(workspace_root)
    database = root / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(f"audit database not found: {database}")
    data = _load(database)
    if not data["observations"]:
        return None

    report_dir = root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / REPORT_FILE
    path.write_text(_page(data, report_dir), encoding="utf-8", newline="\n")
    _enrich_index(report_dir, data)
    normalize_report_navigation(report_dir)
    return path


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _rows(
    connection: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _load(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "serp_observations"):
            return {
                "observations": [],
                "results": {},
                "competitive": {},
                "competitive_results": {},
                "competitive_pages": {},
                "semantic": {},
                "semantic_table": None,
            }

        observations = _rows(
            connection,
            """
            SELECT *
            FROM serp_observations
            ORDER BY collected_at DESC, observation_id DESC
            """,
        )
        results = _group(
            _rows(
                connection,
                """
                SELECT *
                FROM serp_results
                ORDER BY observation_id, position, url
                """,
            ),
            "observation_id",
        ) if _table_exists(connection, "serp_results") else {}

        competitive: dict[str, dict[str, Any]] = {}
        if _table_exists(connection, "serp_competitive_analyses"):
            competitive = {
                str(row["observation_id"]): row
                for row in _rows(connection, "SELECT * FROM serp_competitive_analyses")
            }
        competitive_results = _group(
            _rows(
                connection,
                """
                SELECT *
                FROM serp_competitive_results
                ORDER BY observation_id, position, url
                """,
            ),
            "observation_id",
        ) if _table_exists(connection, "serp_competitive_results") else {}
        competitive_pages = _group(
            _rows(
                connection,
                """
                SELECT *
                FROM serp_competitive_pages
                ORDER BY observation_id, role, domain, requested_url
                """,
            ),
            "observation_id",
        ) if _table_exists(connection, "serp_competitive_pages") else {}

        semantic_table = next(
            (name for name in _SEMANTIC_TABLE_CANDIDATES if _table_exists(connection, name)),
            None,
        )
        semantic: dict[str, list[dict[str, Any]]] = {}
        if semantic_table:
            columns = {
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({semantic_table})").fetchall()
            }
            if "observation_id" in columns:
                semantic = _group(
                    _rows(connection, f"SELECT * FROM {semantic_table}"),
                    "observation_id",
                )
    finally:
        connection.close()

    return {
        "observations": observations,
        "results": results,
        "competitive": competitive,
        "competitive_results": competitive_results,
        "competitive_pages": competitive_pages,
        "semantic": semantic,
        "semantic_table": semantic_table,
    }


def _group(rows: Iterable[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return dict(grouped)


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _page(data: dict[str, Any], report_dir: Path) -> str:
    observations: list[dict[str, Any]] = data["observations"]
    found = sum(str(row.get("domain_status")) == "FOUND" for row in observations)
    not_found = sum(
        str(row.get("domain_status")) == "NOT_FOUND_WITHIN_DEPTH"
        for row in observations
    )
    distinct_queries = len({str(row.get("query") or "") for row in observations})
    competitive_rows = data["competitive"]
    consolidated = sum(
        str(row.get("comparison_status")) == "CONSOLIDATED"
        for row in competitive_rows.values()
    )
    semantic_count = sum(len(rows) for rows in data["semantic"].values())
    providers = sorted(
        {str(row.get("provider") or "-") for row in observations},
        key=str.casefold,
    )
    latest = str(observations[0].get("collected_at") or "-") if observations else "-"
    nav = render_report_navigation(report_dir, REPORT_FILE)

    cards = "".join(_observation_card(row, data) for row in observations)
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Search Intelligence - RASAi - Search & AI Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Search Intelligence · evidência observacional e comparação não causal</div><h1>SERP Observation e Competitive Search Intelligence</h1><p class='lead'>Esta superfície reúne observações de resultados de busca, posição do domínio de interesse, classificação determinística de resultados, comparação limitada de conteúdo público e, quando materializada, análise semântica por IA. Cada camada mantém autoria, fonte técnica e limitações separadas. Nenhum indicador desta página altera SARI-001 ou SCORE-GEO-004.</p><div class='metric-grid'>{_metric('Observações persistidas', len(observations))}{_metric('Queries distintas', distinct_queries)}{_metric('Domínio encontrado', found)}{_metric('Não encontrado na depth', not_found)}{_metric('Comparações de conteúdo consolidadas', consolidated)}{_metric('Análises semânticas persistidas', semantic_count)}{_metric('Providers observados', ', '.join(providers) or '-')}{_metric('Observação mais recente', latest)}</div></header>
{_ownership_section(data)}
<section class='panel' id='search-intelligence-observations'><div class='kicker'>Evidência por consulta</div><h2>Observações persistidas</h2><p class='intro'>Cada bloco abaixo representa uma execução observada em um contexto específico de query, engine, mercado, idioma, device, provider e depth. Resultados de execuções diferentes não são tratados como se fossem a mesma medição.</p>{cards}</section>
{_methodology_section()}
<footer class='footer'>Search Intelligence é observacional e advisory. Ranking observado, diferenças de conteúdo e hipóteses de IA não constituem prova causal do algoritmo de busca e não alteram SARI-001/SCORE-GEO-004.</footer></main></body></html>"""


def _ownership_section(data: dict[str, Any]) -> str:
    semantic_table = data.get("semantic_table")
    semantic_source = (
        f"persistência detectada em <code>{escape(str(semantic_table))}</code>"
        if semantic_table
        else "nenhuma persistência semântica compatível detectada neste workspace"
    )
    return f"""<section class='panel' id='search-intelligence-provenance'><div class='kicker'>Proveniência e propriedade metodológica</div><h2>Quem produz cada dado</h2><p class='intro'>O RASAi organiza as camadas abaixo em uma única página, mas não atribui a si mesmo dados produzidos pelo provider de busca nem transforma uma inferência de IA em observação factual.</p><div class='table-wrap'><table><thead><tr><th>Camada/indicador</th><th>Responsável pela origem</th><th>Fonte técnica persistida</th><th>Interpretação permitida</th><th>Impacto em score</th></tr></thead><tbody>
<tr><td><strong>Posição e SERP observada</strong></td><td>Provider de Search configurado</td><td><code>serp_observations</code>, <code>serp_results</code> e artifact raw com hash quando disponível</td><td>Observação naquele engine/mercado/device/depth/data. NOT_FOUND_WITHIN_DEPTH não significa ausência de ranking fora da profundidade coletada.</td><td>Nenhum</td></tr>
<tr><td><strong>Classificação de resultados</strong></td><td>RASAi</td><td><code>serp_competitive_results</code></td><td>Heurística determinística para selecionar candidatos razoáveis de comparação. Não afirma equivalência comercial entre organizações.</td><td>Nenhum</td></tr>
<tr><td><strong>Conteúdo público observado</strong></td><td>Website observado + coletor RASAi</td><td><code>serp_competitive_pages</code> e artifact competitivo</td><td>Features extraídas do HTML recebido, com hash de conteúdo. HTML bruto não é persistido por esta camada.</td><td>Nenhum</td></tr>
<tr><td><strong>Gaps determinísticos</strong></td><td>RASAi</td><td><code>serp_competitive_analyses</code> / metodologia <code>DETERMINISTIC-CORRELATIONAL-001</code></td><td>Diferenças observadas contra páginas à frente. Não são fator causal de ranking nem recomendação automática.</td><td>Nenhum</td></tr>
<tr><td><strong>Análise semântica por IA</strong></td><td>RASAi + provider/modelo de IA explicitamente identificados</td><td>{semantic_source}</td><td>Hipóteses e recomendações devem permanecer evidence-bound e citar IDs/evidências persistidas. A IA não conhece o algoritmo privado do mecanismo de busca.</td><td>Nenhum</td></tr>
<tr><td><strong>SARI-001 / SCORE-GEO-004</strong></td><td>RASAi</td><td>contrato de scoring e evidências próprias da auditoria</td><td>Índices proprietários separados. Não são recalculados a partir de posição SERP, conteúdo competitivo ou análise semântica desta página.</td><td>Somente pelas regras do contrato próprio de scoring, fora desta superfície</td></tr>
</tbody></table></div></section>"""


def _observation_card(observation: dict[str, Any], data: dict[str, Any]) -> str:
    observation_id = str(observation.get("observation_id") or "")
    rows = data["results"].get(observation_id, [])
    comp = data["competitive"].get(observation_id)
    comp_results = data["competitive_results"].get(observation_id, [])
    comp_pages = data["competitive_pages"].get(observation_id, [])
    semantic_rows = data["semantic"].get(observation_id, [])
    classifications = {
        (int(row.get("position") or 0), str(row.get("url") or "")): row
        for row in comp_results
    }
    query = escape(str(observation.get("query") or "-"))
    status = escape(str(observation.get("domain_status") or "-"))
    position = observation.get("customer_position")
    position_text = "-" if position is None else str(position)
    region = observation.get("region") or "-"
    raw_ref = observation.get("raw_evidence_ref") or "-"
    raw_sha = observation.get("raw_evidence_sha256") or "-"

    result_rows = "".join(
        _result_row(item, classifications.get((int(item.get("position") or 0), str(item.get("url") or ""))))
        for item in rows
    ) or "<tr><td colspan='10'>Nenhum resultado normalizado persistido.</td></tr>"

    technical = _technical_metadata(observation)
    competitive = _competitive_section(comp, comp_results, comp_pages)
    semantic = _semantic_section(semantic_rows)
    return f"""<article class='page-card search-observation' data-observation-id='{escape(observation_id, quote=True)}'><div class='kicker'>Query observada</div><h3>{query}</h3><p class='page-url'>Observation ID: <code>{escape(observation_id)}</code> · Run ID: <code>{escape(str(observation.get('run_id') or '-'))}</code></p><div class='metric-grid'>{_metric('Status do domínio', status)}{_metric('Posição observada', position_text)}{_metric('Engine', observation.get('engine') or '-')}{_metric('Provider', observation.get('provider') or '-')}{_metric('Data mode', observation.get('data_mode') or '-')}{_metric('Mercado', observation.get('country') or '-')}{_metric('Região', region)}{_metric('Idioma', observation.get('language') or '-')}{_metric('Device', observation.get('device') or '-')}{_metric('Depth solicitada', observation.get('requested_depth') or '-')}{_metric('Resultados normalizados', observation.get('result_count') or 0)}{_metric('Coletado em', observation.get('collected_at') or '-')}</div>
<div class='notice'><strong>Leitura correta:</strong> posição e resultados pertencem à observação produzida pelo provider informado. O RASAi normaliza, persiste e contextualiza. <code>NOT_FOUND_WITHIN_DEPTH</code> significa apenas que o domínio não apareceu dentro da profundidade efetivamente coletada.</div>
<details><summary>Evidência raw e metadados técnicos</summary><div class='detail-body'><div class='metric-grid'>{_metric('Artifact raw', raw_ref)}{_metric('SHA-256 raw', raw_sha)}{_metric('Provider request ID', observation.get('provider_request_id') or '-')}{_metric('Query origin', observation.get('query_origin') or '-')}{_metric('Observation status', observation.get('observation_status') or '-')}{_metric('Erro', _error(observation))}</div>{technical}</div></details>
<div class='table-wrap'><table><thead><tr><th>Pos.</th><th>Domínio</th><th>Tipo</th><th>Classificação RASAi</th><th>Selecionado</th><th>Título</th><th>Snippet</th><th>Features SERP</th><th>URL</th><th>Proveniência</th></tr></thead><tbody>{result_rows}</tbody></table></div>
{competitive}
{semantic}
</article>"""


def _result_row(result: Mapping[str, Any], classified: Mapping[str, Any] | None) -> str:
    classification = classified.get("classification") if classified else "NÃO CLASSIFICADO"
    selected = (
        "Sim" if classified and int(classified.get("selected_for_content_comparison") or 0) else "Não"
    )
    features = _json(result.get("serp_features"), [])
    return "<tr>" + "".join((
        f"<td>{escape(str(result.get('position') or '-'))}</td>",
        f"<td>{escape(str(result.get('domain') or '-'))}</td>",
        f"<td>{escape(str(result.get('result_type') or '-'))}</td>",
        f"<td>{escape(str(classification))}</td>",
        f"<td>{escape(selected)}</td>",
        f"<td>{escape(str(result.get('title') or '-'))}</td>",
        f"<td>{escape(str(result.get('snippet') or '-'))}</td>",
        f"<td>{escape(', '.join(str(item) for item in features) if isinstance(features, list) and features else '-')}</td>",
        f"<td class='mono'>{escape(str(result.get('url') or '-'))}</td>",
        "<td>Provider Search para posição/SERP; RASAi apenas para classificação quando presente</td>",
    )) + "</tr>"


def _competitive_section(
    analysis: Mapping[str, Any] | None,
    classified_results: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> str:
    if analysis is None and not classified_results and not pages:
        return """<section class='notice' data-search-competitive='absent'><strong>Competitive Search Intelligence:</strong> nenhuma classificação/comparação competitiva foi persistida para esta observação. Isso não altera a validade da SERP observada.</section>"""

    comparison_status = str((analysis or {}).get("comparison_status") or "CLASSIFICATION_ONLY")
    methodology = str((analysis or {}).get("methodology") or "DETERMINISTIC-CORRELATIONAL-001")
    evidence_ref = (analysis or {}).get("evidence_ref") or "-"
    evidence_sha = (analysis or {}).get("evidence_sha256") or "-"
    gap_rows = _gap_rows((analysis or {}).get("gaps_json"))
    page_rows = "".join(_content_page_row(row) for row in pages) or (
        "<tr><td colspan='13'>Nenhuma página de conteúdo foi materializada; classificação de SERP pode existir sem coleta adicional.</td></tr>"
    )
    classified_count = len(classified_results)
    selected_count = sum(int(row.get("selected_for_content_comparison") or 0) for row in classified_results)
    return f"""<section class='panel' data-search-competitive='true'><div class='kicker'>Competitive Search & Content Intelligence</div><h4>Comparação determinística e não causal</h4><div class='metric-grid'>{_metric('Status da comparação', comparison_status)}{_metric('Metodologia', methodology)}{_metric('Resultados classificados', classified_count)}{_metric('Candidatos selecionados', selected_count)}{_metric('Artifact competitivo', evidence_ref)}{_metric('SHA-256 competitivo', evidence_sha)}</div><p class='intro'>A classificação e os gaps abaixo pertencem ao RASAi. As páginas candidatas são escolhidas a partir da SERP observada; quando o cliente foi encontrado, apenas resultados anteriores à primeira ocorrência do cliente são tratados como páginas observadas à frente. Diferença não significa causa de ranking.</p><div class='table-wrap'><table><thead><tr><th>Papel</th><th>Domínio</th><th>Fetch</th><th>HTTP</th><th>Título</th><th>Meta description</th><th>H1-H3</th><th>Words</th><th>Query body</th><th>Title terms</th><th>Heading terms</th><th>JSON-LD types</th><th>Content SHA-256</th></tr></thead><tbody>{page_rows}</tbody></table></div><div class='table-wrap'><table><thead><tr><th>Gap determinístico</th><th>Severidade</th><th>Valor cliente</th><th>Referência líderes</th><th>Evidências</th><th>Interpretação</th></tr></thead><tbody>{gap_rows}</tbody></table></div></section>"""


def _content_page_row(row: Mapping[str, Any]) -> str:
    query_terms = _json(row.get("query_terms_json"), [])
    body_terms = _json(row.get("query_terms_body_json"), [])
    title_terms = _json(row.get("query_terms_title_json"), [])
    heading_terms = _json(row.get("query_terms_headings_json"), [])
    headings = _json(row.get("headings_json"), [])
    jsonld = _json(row.get("jsonld_types_json"), [])
    coverage = "n/a"
    if isinstance(query_terms, list) and query_terms:
        coverage = f"{(len(body_terms) / len(query_terms)) * 100:.1f}%"
    return "<tr>" + "".join((
        f"<td>{escape(str(row.get('role') or '-'))}</td>",
        f"<td>{escape(str(row.get('domain') or '-'))}</td>",
        f"<td>{escape(str(row.get('fetch_status') or '-'))}</td>",
        f"<td>{escape(str(row.get('http_status') if row.get('http_status') is not None else '-'))}</td>",
        f"<td>{escape(str(row.get('title') or '-'))}</td>",
        f"<td>{escape(str(row.get('meta_description') or '-'))}</td>",
        f"<td>{escape(' | '.join(str(item) for item in headings[:8]) if isinstance(headings, list) and headings else '-')}</td>",
        f"<td>{escape(str(row.get('word_count') or 0))}</td>",
        f"<td>{escape(coverage)}</td>",
        f"<td>{escape(str(len(title_terms) if isinstance(title_terms, list) else 0))}</td>",
        f"<td>{escape(str(len(heading_terms) if isinstance(heading_terms, list) else 0))}</td>",
        f"<td>{escape(', '.join(str(item) for item in jsonld) if isinstance(jsonld, list) and jsonld else '-')}</td>",
        f"<td class='mono'>{escape(str(row.get('content_sha256') or '-'))}</td>",
    )) + "</tr>"


def _gap_rows(raw: Any) -> str:
    gaps = _json(raw, [])
    if not isinstance(gaps, list) or not gaps:
        return "<tr><td colspan='6'>Nenhum gap determinístico persistido para esta observação.</td></tr>"
    rendered = []
    for gap in gaps:
        if not isinstance(gap, Mapping):
            continue
        evidence_urls = gap.get("evidence_urls")
        evidence = ", ".join(str(item) for item in evidence_urls) if isinstance(evidence_urls, list) else "-"
        rendered.append(
            "<tr>"
            f"<td><code>{escape(str(gap.get('code') or '-'))}</code></td>"
            f"<td>{escape(str(gap.get('severity') or '-'))}</td>"
            f"<td>{escape(str(gap.get('customer_value') if gap.get('customer_value') is not None else '-'))}</td>"
            f"<td>{escape(str(gap.get('leader_reference') if gap.get('leader_reference') is not None else '-'))}</td>"
            f"<td class='mono'>{escape(evidence or '-')}</td>"
            f"<td>{escape(str(gap.get('message') or '-'))}</td>"
            "</tr>"
        )
    return "".join(rendered) or "<tr><td colspan='6'>Nenhum gap interpretável persistido.</td></tr>"


def _semantic_section(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return """<section class='notice' data-search-semantic='absent'><strong>Análise semântica por IA:</strong> não materializada para esta observação. O relatório não fabrica intenção, entidades, gaps ou recomendações quando não existe resultado de IA persistido.</section>"""
    cards = "".join(_semantic_record(row, index) for index, row in enumerate(rows, 1))
    return f"""<section class='panel' data-search-semantic='true'><div class='kicker'>Evidence-bound Semantic Competitive Analysis</div><h4>Análise semântica persistida</h4><div class='notice'><strong>Fronteira metodológica:</strong> conteúdo deste bloco é derivado por IA, não é observação direta do mecanismo de busca. Provider/modelo, status, evidências e limitações permanecem visíveis quando disponíveis. Afirmações sem evidência persistida não devem ser promovidas a recomendação confiável.</div>{cards}</section>"""


def _semantic_record(row: Mapping[str, Any], index: int) -> str:
    preferred = (
        "status", "provider", "model", "reasoning_profile", "methodology",
        "primary_intent", "intent", "confidence", "evidence_ids_json",
        "recommendations_json", "gaps_json", "hypotheses_json", "error_code",
        "error_message", "evidence_ref", "evidence_sha256", "created_at",
    )
    ordered = [key for key in preferred if key in row]
    ordered.extend(key for key in row.keys() if key not in ordered and key != "observation_id")
    metrics = []
    detail_rows = []
    for key in ordered:
        value = row.get(key)
        if key in {"provider", "model", "status", "methodology", "confidence", "reasoning_profile"}:
            metrics.append(_metric(_label(key), _compact_value(value)))
        else:
            detail_rows.append(
                f"<tr><th>{escape(_label(key))}</th><td>{_render_value(value)}</td></tr>"
            )
    return f"""<div class='page-card'><h5>Resultado semântico #{index}</h5><div class='metric-grid'>{''.join(metrics) if metrics else _metric('Status', 'Persistido')}</div><details><summary>Payload semântico persistido e evidências</summary><div class='table-wrap'><table><tbody>{''.join(detail_rows) if detail_rows else '<tr><td>Nenhum detalhe adicional.</td></tr>'}</tbody></table></div></details></div>"""


def _technical_metadata(observation: Mapping[str, Any]) -> str:
    config = _json(observation.get("config_metadata"), {})
    quality = _json(observation.get("quality_metadata"), {})
    return (
        "<div class='grid'>"
        + _json_card("Config metadata", config)
        + _json_card("Quality metadata", quality)
        + "</div>"
    )


def _json_card(title: str, value: Any) -> str:
    pretty = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) if value else "{}"
    return f"<div class='page-card'><h5>{escape(title)}</h5><pre><code>{escape(pretty)}</code></pre></div>"


def _methodology_section() -> str:
    return """<section class='panel' id='search-intelligence-methodology'><div class='kicker'>Contrato de interpretação</div><h2>Como ler estes indicadores</h2><div class='grid'><div class='page-card'><h3>SERP Observation</h3><p>É uma fotografia contextual. Engine, mercado, região, idioma, device, provider, depth e timestamp fazem parte da medição. Personalização, geolocalização, data centers, features de SERP e mudanças do mecanismo podem alterar resultados futuros.</p></div><div class='page-card'><h3>Competitive Search</h3><p>"Concorrente" nesta superfície significa candidato de comparação observado no conjunto de busca e classificado por heurística. O termo não prova concorrência empresarial, nem identidade de produto, nem equivalência de público.</p></div><div class='page-card'><h3>Conteúdo determinístico</h3><p>Title, meta description, headings, contagem aproximada de palavras, presença lexical da query e tipos JSON-LD são features observadas. Volume de texto não é qualidade; markup diferente não implica recomendação automática.</p></div><div class='page-card'><h3>Análise semântica por IA</h3><p>Quando habilitada e persistida, deve produzir hipóteses e recomendações evidence-bound. A IA não deve afirmar que conhece fatores privados do algoritmo, nem converter correlação em causalidade.</p></div></div><div class='notice'><strong>Separação de indicadores:</strong> Search Intelligence, Lighthouse/CrUX, Accessibility, SARI-001, SCORE-GEO-004 e visibilidade generativa observada são superfícies distintas. O relatório pode correlacionar contexto, mas não deve fundir metodologias sem um contrato explícito e validado.</div></section>"""


def _enrich_index(report_dir: Path, data: dict[str, Any]) -> None:
    path = report_dir / "index.html"
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    marker = "<section class='panel' id='search-intelligence-summary'"
    if marker in html:
        start = html.index(marker)
        end = html.find("</section>", start)
        if end >= 0:
            html = html[:start] + html[end + len("</section>"):]
    observations = data["observations"]
    found = sum(str(row.get("domain_status")) == "FOUND" for row in observations)
    latest = str(observations[0].get("collected_at") or "-") if observations else "-"
    section = (
        "<section class='panel' id='search-intelligence-summary'>"
        "<div class='kicker'>Search Intelligence</div><h2>Busca observada</h2>"
        "<p class='intro'>Resumo observacional independente do SARI-001/SCORE-GEO-004. Consulte a página dedicada para provider, contexto, resultados, classificação competitiva, conteúdo e eventual análise semântica.</p>"
        f"<div class='metric-grid'>{_metric('Observações', len(observations))}{_metric('Domínio encontrado', found)}{_metric('Última observação', latest)}</div>"
        f"<p><a href='{REPORT_FILE}'>Abrir Search Intelligence</a></p></section>"
    )
    html = html.replace("</header>", "</header>" + section, 1)
    path.write_text(html, encoding="utf-8", newline="\n")


def _metric(label: Any, value: Any) -> str:
    return (
        "<div class='metric'>"
        f"<small>{escape(str(label))}</small>"
        f"<strong>{escape(_compact_value(value))}</strong>"
        "</div>"
    )


def _compact_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _render_value(value: Any) -> str:
    if value is None:
        return "-"
    decoded = _json(value, value)
    if isinstance(decoded, (dict, list)):
        pretty = json.dumps(decoded, ensure_ascii=False, indent=2, sort_keys=True)
        return f"<pre><code>{escape(pretty)}</code></pre>"
    return f"<span>{escape(str(decoded))}</span>"


def _label(key: str) -> str:
    labels = {
        "provider": "Provider de IA",
        "model": "Modelo",
        "status": "Status",
        "reasoning_profile": "Reasoning profile",
        "methodology": "Metodologia",
        "primary_intent": "Intenção primária",
        "intent": "Intenção",
        "confidence": "Confiança",
        "evidence_ids_json": "Evidence IDs",
        "recommendations_json": "Recomendações",
        "gaps_json": "Gaps semânticos",
        "hypotheses_json": "Hipóteses",
        "error_code": "Código de erro",
        "error_message": "Erro",
        "evidence_ref": "Artifact de evidência",
        "evidence_sha256": "SHA-256 da evidência",
        "created_at": "Criado em",
    }
    return labels.get(key, key.replace("_", " ").strip().capitalize())


def _error(observation: Mapping[str, Any]) -> str:
    code = observation.get("error_code")
    message = observation.get("error_message")
    if code and message:
        return f"{code}: {message}"
    return str(code or message or "-")
