from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise RuntimeError(f"marker not found in {path}: {old[:160]!r}")
    write(path, text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1. Central presentation dictionary: internal enums remain persisted exactly
#    as before, but HTML receives user-facing labels. Technical identifiers
#    (rule IDs, profile IDs, evidence IDs, model names and values inside code/pre)
#    are deliberately preserved.
# ---------------------------------------------------------------------------
presentation = "src/rasai/report_presentation.py"
text = read(presentation)
if '"DEGRADED": "Execução com limitações"' not in text:
    marker = '    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",\n'
    addition = marker + '''    "DEGRADED": "Execução com limitações",\n    "FULL": "Execução completa",\n    "NO_AI": "Execução sem IA",\n    "CREATED": "Criado",\n    "INITIALIZING": "Inicializando",\n    "DISCOVERING": "Descobrindo URLs",\n    "ACQUIRING": "Coletando páginas",\n    "ANALYZING": "Analisando",\n    "COMPARING": "Comparando",\n    "SCORING": "Calculando pontuação",\n    "RECOMMENDING": "Gerando recomendações",\n    "REPORTING": "Gerando relatórios",\n    "CANCELLED": "Cancelado",\n    "SKIPPED": "Ignorado",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "NOT_COMPARABLE": "Não comparável",\n'
    addition = marker + '''    "URL_SET": "Conjunto de URLs",\n    "SEED": "URL inicial",\n    "INTERNAL_LINK": "Link interno",\n    "MANUAL": "Informado manualmente",\n    "OBTAINED": "Obtido",\n    "HTTP_ERROR": "Erro HTTP",\n    "NETWORK_ERROR": "Erro de rede",\n    "NOT_FOUND": "Não localizado",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "INVALID": "Inválido",\n'
    addition = marker + '''    "SAME": "Sem diferença material",\n    "DIFFERENT": "Diferente",\n    "REQUIRED_FIX": "Correção necessária",\n    "REVIEW_RECOMMENDED": "Revisão recomendada",\n    "OPTIONAL_IMPROVEMENT": "Melhoria opcional",\n    "NO_ACTION": "Nenhuma ação necessária",\n    "INSUFFICIENT_EVIDENCE": "Evidência insuficiente",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "INFO": "Informativa",\n'
    addition = marker + '''    "VERY_LOW": "Muito baixa",\n    "MINIMAL": "Mínimo",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "P3": "Baixa (P3)",\n'
    addition = marker + '    "P4": "Muito baixa (P4)",\n'
    text = text.replace(marker, addition, 1)

    marker = '    "QUARANTINED_FOR_AUDIT": "Indisponível nesta auditoria",\n'
    addition = marker + '''    "PROVIDER_DEFAULT": "Padrão do provedor",\n    "TECHNICAL_ERROR": "Erro técnico",\n    "BUSINESS_ERROR": "Erro operacional do provedor",\n    "QUARANTINED": "Isolado nesta auditoria",\n    "STANDBY": "Em espera",\n    "AUTH_ERROR": "Erro de autenticação",\n    "QUOTA_ERROR": "Quota indisponível",\n    "CREDIT_ERROR": "Crédito/saldo indisponível",\n    "RATE_LIMIT_ERROR": "Limite de requisições atingido",\n    "MODEL_ERROR": "Modelo indisponível ou incompatível",\n    "PERMISSION_ERROR": "Permissão insuficiente",\n    "TIMEOUT_ERROR": "Tempo limite excedido",\n    "SERVER_ERROR": "Erro no servidor do provedor",\n    "EMPTY_RESPONSE": "Resposta vazia",\n    "INVALID_RESPONSE": "Resposta inválida",\n    "UNKNOWN_PROVIDER_ERROR": "Erro não classificado do provedor",\n    "AI_PROVIDER_UNAVAILABLE": "Provedor de IA indisponível",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "MISSING_PROPOSED": "Proposta não gerada",\n'
    addition = marker + '''    "EXISTING_REVIEW": "Revisão do JSON-LD existente",\n    "NO_SAFE_SUGGESTIONS": "Nenhuma sugestão segura",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "VERY_HIGH": "Muito alta",\n'
    addition = marker + '''    "HTTP_RESPONSE": "Resposta HTTP",\n    "HTTP_HEADER": "Cabeçalho HTTP",\n    "ROBOTS_RULE": "Regra de robots.txt",\n    "SITEMAP_ENTRY": "Entrada de sitemap",\n    "HTML_ELEMENT": "Elemento HTML",\n    "DOM_ELEMENT": "Elemento do DOM",\n    "VISUAL_SNAPSHOT": "Captura visual",\n    "META_TAG": "Meta tag",\n    "MAIN_CONTENT": "Conteúdo principal",\n    "TEXT_EXCERPT": "Trecho de texto",\n    "AI_ANALYSIS": "Análise por IA",\n    "COMPARISON": "Comparação",\n    "STATIC_OR_SSR": "Estática ou renderizada no servidor (SSR)",\n    "HYDRATED": "Renderizada no servidor com hidratação",\n    "CSR_SPA": "SPA renderizada no cliente (CSR)",\n    "MIXED": "Mista",\n    "GLOBAL": "Global",\n    "PAGE": "Página",\n    "SNAPSHOT": "Captura",\n    "HEURISTIC": "Heurística",\n    "ORGANIZATION": "Organização",\n    "PERSON": "Pessoa",\n    "PRODUCT": "Produto",\n    "SERVICE": "Serviço",\n    "PLACE": "Local",\n    "BRAND": "Marca",\n    "TOPIC": "Tópico",\n    "OTHER": "Outro",\n'''
    text = text.replace(marker, addition, 1)

    marker = '    "THIRD_PARTY": "Terceiros",\n'
    addition = marker + '''    "CONNECTION": "Conexão",\n    "TIMEOUT": "Tempo limite excedido",\n    "PROTOCOL": "Erro de protocolo",\n    "REDIRECT_LOOP": "Loop de redirecionamento",\n    "TOO_MANY_REDIRECTS": "Redirecionamentos em excesso",\n    "INVALID_REDIRECT": "Redirecionamento inválido",\n    "BROWSER_UNAVAILABLE": "Navegador indisponível",\n    "NAVIGATION_TIMEOUT": "Tempo limite de navegação excedido",\n    "NAVIGATION_ERROR": "Erro de navegação",\n    "RENDERER_ERROR": "Erro de renderização",\n    "EXTRACTION_INPUT_UNAVAILABLE": "Conteúdo de entrada indisponível para extração",\n    "EXTRACTION_ERROR": "Erro de extração",\n    "NO_DEVICE_SNAPSHOTS": "Nenhuma captura de dispositivo disponível",\n    "ONE_DEVICE_SNAPSHOT_MISSING": "Captura ausente em um dos dispositivos",\n'''
    text = text.replace(marker, addition, 1)
    write(presentation, text)


# ---------------------------------------------------------------------------
# 2. JSON-LD: when a structured_data.json artifact exists, expose its persisted
#    content directly in content-suggestions.html, while retaining a link to the
#    full artifact. The view is bounded to 1 MiB to keep static reports usable.
# ---------------------------------------------------------------------------
m20 = "src/rasai/m20_reporting.py"
text = read(m20)
if "from rasai.report_presentation import public_label" not in text:
    text = text.replace(
        "from rasai.report_navigation import normalize_report_navigation, render_report_navigation\n",
        "from rasai.report_navigation import normalize_report_navigation, render_report_navigation\nfrom rasai.report_presentation import public_label\n",
        1,
    )

old_query = '''            SELECT j.*,p.normalized_url\n            FROM jsonld_remediation_suggestions j\n            JOIN pages p ON p.page_id=j.page_id\n            WHERE j.audit_id=? ORDER BY p.normalized_url,j.device,j.suggestion_id\n'''
new_query = '''            SELECT j.*,p.normalized_url,ps.structured_data_ref\n            FROM jsonld_remediation_suggestions j\n            JOIN pages p ON p.page_id=j.page_id\n            JOIN page_snapshots ps ON ps.snapshot_id=j.snapshot_id\n            WHERE j.audit_id=? ORDER BY p.normalized_url,j.device,j.suggestion_id\n'''
if old_query not in text:
    raise RuntimeError("M20 JSON-LD load query marker not found")
text = text.replace(old_query, new_query, 1)

old = '''    run_status = str(run["status"]) if run is not None else "UNAVAILABLE"\n    enabled = bool(run["enabled"]) if run is not None else False\n'''
new = '''    run_status = str(run["status"]) if run is not None else "UNAVAILABLE"\n    run_status_label = public_label(run_status)\n    enabled = bool(run["enabled"]) if run is not None else False\n'''
if old not in text:
    raise RuntimeError("M20 run status marker not found")
text = text.replace(old, new, 1)

start = text.index("    jsonld_cards = []\n")
end = text.index("\n    if not enabled:", start)
jsonld_block = '''    jsonld_cards = []\n    for row in data["jsonld"]:\n        improvements = "".join(f"<li>{escape(str(item))}</li>" for item in _json_list(row["improvements"]))\n        types = ", ".join(_json_list(row["existing_types"])) or "Nenhum tipo observado"\n        proposed = ""\n        if row["proposed_json"]:\n            proposed_obj = _json_value(row["proposed_json"])\n            proposed = f"<h5>JSON-LD baseline sugerido</h5><pre>{escape(json.dumps(proposed_obj, ensure_ascii=False, indent=2, sort_keys=True))}</pre>"\n        observed = _structured_data_artifact_html(report_dir.parent, row["structured_data_ref"])\n        device_label = public_label(str(row["device"]))\n        status_label = public_label(str(row["status"]))\n        jsonld_cards.append(f"""<article class='page-card'><div class='finding-head'><div><span class='badge'>{escape(device_label)}</span> <span class='badge info'>{escape(status_label)}</span></div><span class='badge'>{escape(types)}</span></div><h3 class='page-url'>{escape(str(row['normalized_url']))}</h3>{observed}{proposed}<h5>Revisão recomendada</h5><ul>{improvements}</ul></article>""")\n'''
text = text[:start] + jsonld_block + text[end:]

text = text.replace(
    "IA de conteúdo habilitada e chamada, mas o resultado foi degradado/rejeitado.",
    "IA de conteúdo habilitada e chamada, mas a etapa terminou com limitações ou teve respostas rejeitadas.",
)
text = text.replace("{_metric('Status',run_status)}", "{_metric('Status',run_status_label)}", 1)

helper_marker = "\ndef _attempt_error_summary(attempts: list[sqlite3.Row]) -> str:\n"
if "def _structured_data_artifact_html(" not in text:
    helper = r'''

_MAX_STRUCTURED_DATA_PREVIEW_BYTES = 1024 * 1024


def _structured_data_artifact_html(audit_root: Path, reference: Any) -> str:
    """Render a safe in-report preview of the persisted Structured Data artifact."""
    ref = str(reference or "").strip()
    if not ref:
        return ""
    root = audit_root.resolve()
    candidate = (root / ref).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return "<div class='notice warn'><strong>JSON-LD observado:</strong> referência de artifact fora do diretório da auditoria; visualização bloqueada por segurança.</div>"
    if not candidate.is_file():
        return "<div class='notice warn'><strong>JSON-LD observado:</strong> o arquivo persistido referenciado não está mais disponível para visualização.</div>"
    try:
        payload = candidate.read_bytes()
    except OSError:
        return "<div class='notice warn'><strong>JSON-LD observado:</strong> o arquivo persistido não pôde ser lido.</div>"

    truncated = len(payload) > _MAX_STRUCTURED_DATA_PREVIEW_BYTES
    preview_bytes = payload[:_MAX_STRUCTURED_DATA_PREVIEW_BYTES]
    preview = preview_bytes.decode("utf-8", errors="replace")
    if not truncated:
        try:
            preview = json.dumps(json.loads(preview), ensure_ascii=False, indent=2, sort_keys=True)
        except json.JSONDecodeError:
            pass

    href = "../" + ref.replace("\\", "/").lstrip("/")
    truncation = (
        f"<div class='notice warn'><strong>Pré-visualização limitada:</strong> o artifact possui {len(payload):,} bytes; "
        f"a tela mostra os primeiros {_MAX_STRUCTURED_DATA_PREVIEW_BYTES:,} bytes. Use o link para abrir o arquivo completo.</div>"
        if truncated else ""
    )
    return (
        "<details class='details jsonld-artifact'><summary>Visualizar JSON-LD observado nesta auditoria</summary>"
        "<div class='detail-body'><p class='intro'>O conteúdo abaixo vem do artifact de Structured Data persistido durante a coleta; "
        "não é uma reconstrução feita pelo relatório.</p>"
        f"<p><strong>Arquivo:</strong> <code>{escape(ref)}</code> · "
        f"<a href='{escape(href, quote=True)}'>abrir arquivo persistido completo →</a></p>{truncation}"
        f"<pre>{escape(preview)}</pre></div></details>"
    )
'''
    if helper_marker not in text:
        raise RuntimeError("M20 helper insertion marker not found")
    text = text.replace(helper_marker, helper + helper_marker, 1)

# Context values are configuration enums, not vocabulary the business user should decode.
if "_CONTEXT_VALUE_LABELS" not in text:
    marker = "_CONTEXT_HINTS = {\n"
    pos = text.index(marker)
    # Place the value map before _CONTEXT_HINTS.
    value_map = '''_CONTEXT_VALUE_LABELS = {\n    "auto": "Automático",\n    "standard": "Padrão",\n    "ymyl": "YMYL",\n    "none": "Nenhuma",\n    "health-safety": "Saúde e segurança",\n    "financial-security": "Segurança financeira",\n    "civic-societal": "Cívico e social",\n    "other-significant-welfare": "Outro impacto relevante no bem-estar",\n    "informational": "Informacional",\n    "transactional": "Transacional",\n    "product-service": "Produto ou serviço",\n    "review-comparison": "Avaliação ou comparação",\n    "news-editorial": "Notícia ou editorial",\n    "support-documentation": "Suporte ou documentação",\n    "forum-ugc": "Fórum ou conteúdo de usuário",\n    "other": "Outro",\n    "general": "Público geral",\n    "professional": "Profissional",\n    "mixed": "Misto",\n    "required": "Necessária",\n    "beneficial": "Benéfica",\n    "not-expected": "Não esperada",\n    "low": "Baixa",\n    "medium": "Média",\n    "high": "Alta",\n    "first-party": "Conteúdo próprio",\n    "third-party": "Conteúdo de terceiros",\n    "user-generated": "Conteúdo gerado por usuários",\n}\n\n'''
    text = text[:pos] + value_map + text[pos:]

old = '''        value = str(payload[field])\n        origin = "AUTO" if field in set(metadata.get("auto_fields") or ()) else "CONFIGURADO"\n        cards.append(\n            "<div class='metric'>"\n            f"<small title='{escape(_CONTEXT_HINTS[field], quote=True)}'>{escape(_CONTEXT_LABELS[field])} ⓘ</small>"\n            f"<strong>{escape(value)}</strong><span class='badge {'unknown' if origin == 'AUTO' else 'info'}'>{origin}</span></div>"\n        )\n'''
new = '''        raw_value = str(payload[field])\n        value = _CONTEXT_VALUE_LABELS.get(raw_value.casefold(), raw_value)\n        inferred = field in set(metadata.get("auto_fields") or ())\n        origin = "Inferido" if inferred else "Configurado"\n        cards.append(\n            "<div class='metric'>"\n            f"<small title='{escape(_CONTEXT_HINTS[field], quote=True)}'>{escape(_CONTEXT_LABELS[field])} ⓘ</small>"\n            f"<strong>{escape(value)}</strong><span class='badge {'unknown' if inferred else 'info'}'>{origin}</span></div>"\n        )\n'''
if old not in text:
    raise RuntimeError("M20 context value marker not found")
text = text.replace(old, new, 1)

write(m20, text)


# ---------------------------------------------------------------------------
# 3. Regression tests: explicit examples from the supplied reports + technical
#    identifiers that must remain intact for traceability.
# ---------------------------------------------------------------------------
test_path = "tests/test_user_facing_language_contract.py"
test = read(test_path)
if "test_common_report_machine_values_are_humanized" not in test:
    test += r'''


def test_common_report_machine_values_are_humanized() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<table><tr><td>INTERNAL_LINKS</td><td>PAGE_ACCESS</td><td>SPA_NAVIGATION</td>"
        "<td>SPA_ROUTE</td><td>DEGRADED</td><td>EXISTING_REVIEW</td>"
        "<td>AUTH_ERROR</td><td>NAVIGATION_TIMEOUT</td></tr></table>"
    )
    rendered = humanize_report_html(html)
    assert "Links internos" in rendered
    assert "Acesso à página" in rendered
    assert "Navegação SPA" in rendered
    assert "Rota SPA" in rendered
    assert "Execução com limitações" in rendered
    assert "Revisão do JSON-LD existente" in rendered
    assert "Erro de autenticação" in rendered
    assert "Tempo limite de navegação excedido" in rendered
    for raw in ("INTERNAL_LINKS", "PAGE_ACCESS", "SPA_NAVIGATION", "SPA_ROUTE", "DEGRADED", "EXISTING_REVIEW"):
        assert f">{raw}<" not in rendered


def test_technical_identifiers_remain_canonical_when_they_are_traceability_data() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<div><code>RASAI_AI_CONTENT_REMEDIATION</code>"
        "<span>BR-GEO-017</span><strong>RASAI_TABLET_CONTROLLED4G_V1</strong>"
        "<pre>DEGRADED SINGLE_PROVIDER</pre></div>"
    )
    rendered = humanize_report_html(html)
    assert "RASAI_AI_CONTENT_REMEDIATION" in rendered
    assert "BR-GEO-017" in rendered
    assert "RASAI_TABLET_CONTROLLED4G_V1" in rendered
    assert "<pre>DEGRADED SINGLE_PROVIDER</pre>" in rendered
'''
    write(test_path, test)

m20_test_path = "tests/test_m20_jsonld_artifact_view.py"
if not (ROOT / m20_test_path).exists():
    write(m20_test_path, r'''from __future__ import annotations

import json
from pathlib import Path

from rasai.m20_reporting import _structured_data_artifact_html


def test_structured_data_artifact_is_visible_in_html_and_keeps_full_file_link(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts/extraction/P1/mobile/S1/structured_data.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "index": 0,
                        "raw": '{"@context":"https://schema.org","@type":"Product","name":"Seguro"}',
                        "parsed": {"@context": "https://schema.org", "@type": "Product", "name": "Seguro"},
                        "parse_error": None,
                        "types": ["Product"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ref = artifact.relative_to(tmp_path).as_posix()
    rendered = _structured_data_artifact_html(tmp_path, ref)
    assert "Visualizar JSON-LD observado nesta auditoria" in rendered
    assert "Seguro" in rendered
    assert "Product" in rendered
    assert f"../{ref}" in rendered
    assert "não é uma reconstrução feita pelo relatório" in rendered


def test_structured_data_artifact_preview_blocks_path_traversal(tmp_path: Path) -> None:
    rendered = _structured_data_artifact_html(tmp_path, "../outside.json")
    assert "bloqueada por segurança" in rendered
''')


# ---------------------------------------------------------------------------
# 4. Documentation relevant to the new public behavior.
# ---------------------------------------------------------------------------
report_guide = "docs/REPORT_GUIDE.md"
doc = read(report_guide)
marker = "### Visualização do JSON-LD persistido"
if marker not in doc:
    doc += r'''

### Visualização do JSON-LD persistido

Em `content-suggestions.html`, quando a coleta produziu um `structured_data.json`, o card da respectiva URL/dispositivo oferece **Visualizar JSON-LD observado nesta auditoria**. A tela mostra o conteúdo persistido pelo runtime, com escaping HTML, e mantém um link para abrir o artifact completo. A pré-visualização em HTML é limitada a 1 MiB para não tornar o relatório estático excessivamente pesado; acima desse limite, o truncamento é informado e o arquivo integral continua acessível pelo link.

A visualização distingue claramente três coisas: o JSON-LD efetivamente observado na página, a análise/revisão determinística do RASAi e eventual baseline sugerido. O relatório não deve apresentar uma reconstrução ou sugestão como se fosse o markup coletado.

### Linguagem humana versus identificadores técnicos

Enums e estados internos não constituem linguagem pública. Valores como `DEGRADED`, `SINGLE_PROVIDER`, `INTERNAL_LINKS`, `PAGE_ACCESS`, `SPA_NAVIGATION`, classes de erro e demais estados operacionais são convertidos para rótulos claros em pt-BR quando aparecem como conteúdo de tela. Os valores canônicos continuam persistidos no banco e disponíveis para diagnóstico.

Identificadores que têm função real de rastreabilidade permanecem canônicos quando necessário, especialmente `BR-GEO-*`, IDs de auditoria/evidência, nomes de modelos/providers, IDs de perfis sintéticos e variáveis de ambiente. Exemplos técnicos e payloads dentro de `code`/`pre` também não são traduzidos, para não corromper comandos, contratos ou evidências.
'''
    write(report_guide, doc)

smoke = "docs/SMOKE_TEST.md"
doc = read(smoke)
marker = "JSON-LD observado na tela"
if marker not in doc:
    doc += r'''

## JSON-LD observado na tela e linguagem pública

Em uma auditoria que possua Structured Data/JSON-LD coletado:

1. abrir `content-suggestions.html`;
2. localizar a URL/dispositivo com JSON-LD existente;
3. abrir **Visualizar JSON-LD observado nesta auditoria**;
4. confirmar que o conteúdo persistido aparece no HTML e que o link para o artifact completo funciona;
5. confirmar que status operacionais aparecem em linguagem humana (por exemplo, **Execução com limitações**) e não como enums como `DEGRADED`;
6. confirmar que identificadores técnicos necessários, como `BR-GEO-*`, IDs de perfil e valores em blocos `code`/`pre`, permanecem inalterados.
'''
    write(smoke, doc)

outputs = "docs/OUTPUTS_AND_ARTIFACTS.md"
doc = read(outputs)
marker = "visualização inline do artifact Structured Data"
if marker not in doc:
    doc += r'''

### Structured Data / JSON-LD

Quando `artifacts/extraction/.../structured_data.json` existe, `report/content-suggestions.html` oferece visualização inline do artifact Structured Data e link relativo para o arquivo completo. O artifact permanece a fonte persistida; a página HTML é apenas uma projeção segura para leitura humana. A proposta/baseline de JSON-LD, quando existir, deve permanecer visualmente separada do conteúdo efetivamente coletado.
'''
    write(outputs, doc)

print("JSON-LD artifact view and public-language hardening applied")
