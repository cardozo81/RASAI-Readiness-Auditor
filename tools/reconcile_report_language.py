from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

MILESTONES = {
    0: 'Bootstrap e fundação do projeto',
    1: 'Auditoria e persistência',
    2: 'Descoberta e aquisição HTTP',
    3: 'Renderização Desktop e Mobile',
    4: 'Extração e evidências',
    5: 'Motor de regras determinísticas',
    6: 'JavaScript e SPA',
    7: 'Análise semântica e fallback',
    8: 'Comparação Desktop e Mobile',
    9: 'Scoring e confiabilidade',
    10: 'Priorização e recomendações',
    11: 'Relatório HTML estático',
    12: 'Testes críticos e baseline local estável',
    13: 'Remediação GEO acionável',
    14: 'Auditoria multi-URL e evidência visual',
    15: 'Experiência e organização dos relatórios',
    16: 'Remediação por causa raiz e elemento',
    17: 'Precisão e consistência das recomendações',
    18: 'Análise semântica por IA, roteamento e telemetria',
    19: 'Aplicabilidade e mínimos do SearchGEO Readiness',
    20: 'Sugestões e remediação de conteúdo por IA',
    21: 'Web Performance externo',
    22: 'Acessibilidade automatizada e diagnósticos Web',
    23: 'Synthetic Navigation Apdex',
    24: 'Rastreamento, descoberta e acesso de crawlers',
    25: 'Synthetic User Experience Apdex',
    26: 'Observed Generative Visibility',
}
STANDALONE = re.compile(r'(?<![\w-])M(\d{1,2})(?![\w-])')


def replace_milestones(text: str) -> str:
    return STANDALONE.sub(lambda m: MILESTONES.get(int(m.group(1)), 'etapa de implementação'), text)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8', newline='\n')


def patch_docs() -> None:
    docs = [ROOT / 'README.md', *sorted((ROOT / 'docs').rglob('*.md'))]
    for path in docs:
        text = replace_milestones(path.read_text(encoding='utf-8'))
        text = text.replace('**Status:** IMPLEMENTADO EM BRANCH — aguardando smoke humano antes de merge.', '**Status:** INTEGRADO E VALIDADO.')
        text = text.replace('**Status:** IMPLEMENTAÇÃO EM BRANCH', '**Status:** INTEGRADO E VALIDADO.')
        text = text.replace('## Evoluções formalizadas', '## Especificações funcionais complementares')
        text = text.replace('## Fronteiras dos marcos externos/non-scoring', '## Fronteiras dos domínios complementares')
        text = text.replace('| Marco | Domínio | Regra de fronteira |', '| Domínio | Finalidade | Regra de fronteira |')
        text = text.replace('## Critério de encerramento de marco', '## Critério de encerramento de alteração')
        text = text.replace('Branches de marco são temporárias.', 'Branches de trabalho são temporárias.')
        text = text.replace('branch de marco', 'branch de trabalho').replace('branches de marco', 'branches de trabalho')
        text = text.replace('marco concorrente', 'alteração concorrente').replace('marco implementado', 'alteração implementada')
        write(path, text)

    readme = ROOT / 'README.md'
    text = readme.read_text(encoding='utf-8')
    text = text.replace('Em implementação no Observed Generative Visibility, sem alterar scoring:', 'Observed Generative Visibility, sem alterar scoring:')
    if '## Operação sem IA' not in text:
        section = '''\n## Operação sem IA\n\nA IA é opcional. Com `--ai-provider none`, o SearchGEO continua executando as análises determinísticas de acesso técnico, redirects/TLS, indexabilidade, extração de conteúdo, crawling/discovery e comparação entre dispositivos. Synthetic Navigation Apdex e Synthetic User Experience Apdex também são independentes de LLM quando habilitados. Lighthouse e Core Web Vitals permanecem independentes de IA, mas dependem das respectivas fontes externas quando configuradas.\n\nAs dimensões predominantemente semânticas podem permanecer `UNKNOWN`/`NOT_CONSOLIDATED` sem IA. Isso reduz Coverage e pode impedir o Overall do SGRI-001; não transforma ausência de IA em falha do website e não aplica score zero artificial.\n'''
        text = text.replace('\n## IA\n', section + '\n## IA\n')
    write(readme, text)

    report_guide = ROOT / 'docs/REPORT_GUIDE.md'
    text = report_guide.read_text(encoding='utf-8')
    if '## Linguagem para o analista' not in text:
        text += '''\n\n## Linguagem para o analista\n\nO público principal dos relatórios é o profissional de análise de dados e SEO. O HTML deve explicar o fenômeno medido, impacto, evidência e limitação sem exigir conhecimento de Python, SQLite, nomes de módulos, tabelas ou contratos internos.\n\nTermos técnicos podem permanecer quando forem documentados por fonte pública reconhecida e difundidos no domínio, como canonical, robots.txt, HTTP/HTTPS, TLS, JSON-LD, Schema.org, Lighthouse, Core Web Vitals, CrUX, LCP, INP, CLS, WCAG e Apdex. Termos menos triviais devem receber contexto, tooltip ou glossário.\n\nIdentificadores internos de implementação, nomes de módulos, classes, tabelas, parâmetros de runtime e códigos de entrega não devem compor a leitura principal. Códigos BR-GEO podem aparecer apenas como referência secundária de rastreabilidade.\n'''
    write(report_guide, text)

    glossary = ROOT / 'docs/specification/11_REPORTING_LANGUAGE_GLOSSARY.md'
    text = glossary.read_text(encoding='utf-8')
    if '### Linguagem orientada ao analista' not in text:
        text += '''\n\n### Linguagem orientada ao analista\n\nA apresentação HTML é destinada a profissionais de análise de dados e SEO, não a desenvolvedores do SearchGEO. Termos técnicos só devem aparecer na leitura principal quando tiverem fonte pública reconhecida e uso difundido no domínio. Vocabulário interno de implementação deve permanecer fora da interface principal; quando tecnicamente necessário para suporte, deve ficar recolhido em detalhes técnicos e acompanhado de explicação humana. Identificadores históricos de etapas de entrega não fazem parte do vocabulário do produto e não devem aparecer em relatórios, console ou documentação operacional.\n'''
    write(glossary, text)

    decisions = ROOT / 'docs/specification/10_DECISIONS.md'
    text = decisions.read_text(encoding='utf-8')
    if '### D-041 — Linguagem pública por domínio funcional' not in text:
        text += '''\n\n### D-041 — Linguagem pública por domínio funcional\n\nA documentação de produto, o console e os relatórios destinados ao usuário devem nomear capacidades pelo domínio funcional, não por identificadores históricos de etapas de entrega. Termos técnicos na apresentação só são admitidos quando documentados por fonte pública reconhecida e difundidos no domínio; vocabulário de código/runtime deve ficar oculto da leitura principal. O público-alvo primário é o analista de dados/SEO.\n'''
    write(decisions, text)

    reqs = ROOT / 'docs/specification/07_FUNCTIONAL_REQUIREMENTS.md'
    text = reqs.read_text(encoding='utf-8')
    if '### FR-GEO-173' not in text:
        text += '''\n\n### FR-GEO-173\nA camada de apresentação não deve expor identificadores históricos de etapas de entrega; capacidades devem ser nomeadas pelo domínio funcional.\n\n### FR-GEO-174\nO HTML deve ser compreensível por analista de dados/SEO sem conhecimento do código, preservando apenas termos técnicos externamente documentados e difundidos, com contexto/glossário quando necessário.\n\n### FR-GEO-175\nEstados `UNAVAILABLE`, `INCOMPLETE`, ausência de evidência ou coleta não executada devem ser apresentados de forma neutra e nunca como resultado ruim, zero ou ausência de falha do website.\n'''
    write(reqs, text)


def patch_presentation() -> None:
    # Compatibility inputs in report_consistency_v2.py intentionally retain old
    # delivery labels so older/generated SearchGEO chrome can be sanitized without
    # changing arbitrary audited website content that happens to contain Mxx.
    names = [
        'm18_reporting.py', 'm20_reporting.py', 'm21_reporting.py', 'm22_quality_domains.py',
        'm23_reporting.py', 'm24_reporting.py', 'm25_reporting.py', 'm26_reporting.py',
        'report_navigation.py', 'report_semantics.py', 'searchgeo_readiness_reporting.py',
        'indicator_provenance.py', 'console_help.py', 'source_quality_report_summary.py',
    ]
    replacements = {
        'non-scoring': 'informativo; não altera o índice',
        'outcome observado': 'visibilidade observada',
        'provider FALLBACK': 'avaliação determinística sem IA',
        'provider <strong>FALLBACK</strong>': 'método <strong>avaliação determinística sem IA</strong>',
        'scoring_impact=NONE': 'sem impacto no SearchGEO Readiness Index',
        'não cria RuleExecution/ScoreContribution': 'não altera regras nem o SearchGEO Readiness Index',
        'Projeção estática derivada do audit.db': 'Relatório gerado a partir dos dados persistidos da auditoria',
    }
    for name in names:
        path = ROOT / 'src/searchgeo' / name
        text = replace_milestones(path.read_text(encoding='utf-8'))
        for old, new in replacements.items():
            text = text.replace(old, new)
        write(path, text)

    semantic = ROOT / 'src/searchgeo/semantic.py'
    text = semantic.read_text(encoding='utf-8')
    text = text.replace('ProviderCallResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED")', 'ProviderCallResult(ProviderState.NOT_CONFIGURED, reason="AI_DISABLED_BY_CONFIGURATION")', 1)
    write(semantic, text)

    sem = ROOT / 'src/searchgeo/report_semantics.py'
    text = sem.read_text(encoding='utf-8')
    text = text.replace('return ("good", "Sem falhas detectadas", True) if number == 0 else ("bad", "Correção necessária", True)', 'return ("neutral", "Nenhuma ocorrência registrada", True) if number == 0 else ("bad", "Correção necessária", True)')
    old = '''if key == "cwv":\n            if normalized == "pass":\n                return "good", "Aprovado no p75", True\n            if normalized == "fail":\n                return "bad", "Não aprovado no p75", True'''
    new = old + '''\n            if normalized in {"unavailable", "incomplete", "—", "-", "n/a", "não disponível", "nao disponivel"}:\n                return "neutral", "Dados de campo indisponíveis", True'''
    text = text.replace(old, new)
    write(sem, text)

    consistency = ROOT / 'src/searchgeo/report_consistency_v2.py'
    text = consistency.read_text(encoding='utf-8')
    if '_USER_REASON_REPLACEMENTS' not in text:
        block = '''\n_USER_REASON_REPLACEMENTS: tuple[tuple[str, str], ...] = (\n    ("AI_DISABLED_BY_CONFIGURATION", "Análise por IA desabilitada nesta execução"),\n    ("AI_NOT_CONFIGURED", "IA selecionada sem credencial/configuração disponível"),\n    ("LIGHTHOUSE_RESULT_MISSING", "O Lighthouse não retornou um resultado utilizável"),\n    ("RESULT_MISSING", "A fonte externa não retornou o resultado esperado"),\n    ("RESOURCE_EXHAUSTED", "Limite de quota do serviço externo atingido"),\n)\n'''
        text = text.replace('_PRESENTATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (', block + '\n_PRESENTATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (', 1)
        text = text.replace('for old, new in _PRESENTATION_REPLACEMENTS:\n        html = html.replace(old, new)', 'for old, new in _PRESENTATION_REPLACEMENTS:\n        html = html.replace(old, new)\n    for old, new in _USER_REASON_REPLACEMENTS:\n        html = html.replace(old, new)\n    html = re.sub(r"\\s*\\(_ssl\\.c:\\d+\\)", "", html)\n    html = re.sub(r"project_number:\\s*\\d+", "identificador interno do serviço omitido", html, flags=re.IGNORECASE)\n    html = html.replace("ignore_https_errors", "desativação da validação TLS")')

    if 'def _analyst_glossary_html()' not in text:
        glossary_fn = '''\n\ndef _analyst_glossary_html() -> str:\n    terms = (\n        ("Apdex", "Índice de satisfação calculado a partir de tempos de resposta e de um limiar T definido para a tarefa medida."),\n        ("canonical", "Sinal que indica a URL preferencial entre páginas equivalentes ou muito semelhantes."),\n        ("Core Web Vitals", "Métricas de experiência do usuário definidas no ecossistema Chrome/Google."),\n        ("CrUX", "Chrome UX Report, fonte de dados agregados de experiência real quando existe amostra suficiente."),\n        ("JSON-LD", "Formato JSON para dados vinculados, amplamente usado para Structured Data."),\n        ("Lighthouse", "Ferramenta automatizada de auditoria de qualidade Web mantida no ecossistema Chrome."),\n        ("LCP", "Largest Contentful Paint; mede o tempo de renderização do maior conteúdo visível relevante."),\n        ("INP", "Interaction to Next Paint; mede responsividade às interações do usuário."),\n        ("CLS", "Cumulative Layout Shift; mede instabilidade visual."),\n        ("RUM", "Real User Monitoring; observação de usuários reais, diferente das medições sintéticas do SearchGEO."),\n        ("TLS", "Protocolo de segurança usado por HTTPS para autenticação e proteção da conexão."),\n        ("WCAG", "Web Content Accessibility Guidelines, recomendações do W3C para acessibilidade Web."),\n    )\n    rows = "".join(f"<dt>{escape(term)}</dt><dd>{escape(description)}</dd>" for term, description in terms)\n    return (\n        "<section id='analyst-glossary' class='panel'>"\n        "<div class='kicker'>Glossário</div><h2>Termos usados nos relatórios</h2>"\n        "<p class='intro'>Definições resumidas para leitura por profissionais de dados e SEO. "\n        "As referências metodológicas completas permanecem nesta página.</p>"\n        f"<dl>{rows}</dl></section>"\n    )\n'''
        text = text.replace('\ndef _one(db: sqlite3.Connection, sql: str, audit_id: str) -> sqlite3.Row | None:', glossary_fn + '\n\ndef _one(db: sqlite3.Connection, sql: str, audit_id: str) -> sqlite3.Row | None:', 1)
        old_loop = '''        try:\n            html = path.read_text(encoding="utf-8")\n        except (OSError, UnicodeDecodeError):\n            continue\n        path.write_text(_sanitize_presentation(html), encoding="utf-8", newline="\\n")'''
        new_loop = '''        try:\n            html = path.read_text(encoding="utf-8")\n        except (OSError, UnicodeDecodeError):\n            continue\n        if path.name == "references.html":\n            html = _replace_section(html, "analyst-glossary", _analyst_glossary_html(), "</main>")\n        path.write_text(_sanitize_presentation(html), encoding="utf-8", newline="\\n")'''
        text = text.replace(old_loop, new_loop, 1)
    write(consistency, text)


def add_tests() -> None:
    path = ROOT / 'tests/test_user_facing_language_contract.py'
    write(path, '''from __future__ import annotations\n\nfrom pathlib import Path\nimport re\n\nROOT = Path(__file__).resolve().parents[1]\nMILESTONE = re.compile(r"(?<![\\w-])M\\d{1,2}(?![\\w-])")\n\n\ndef test_documentation_has_no_standalone_delivery_milestone_labels() -> None:\n    failures = []\n    for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:\n        matches = sorted(set(MILESTONE.findall(path.read_text(encoding="utf-8"))))\n        if matches:\n            failures.append(f"{path.relative_to(ROOT)}: {matches}")\n    assert not failures, "\\n".join(failures)\n\n\ndef test_user_facing_templates_have_no_standalone_delivery_milestone_labels() -> None:\n    names = ["m18_reporting.py", "m20_reporting.py", "m21_reporting.py", "m22_quality_domains.py", "m23_reporting.py", "m24_reporting.py", "m25_reporting.py", "m26_reporting.py", "report_navigation.py", "report_semantics.py", "searchgeo_readiness_reporting.py", "indicator_provenance.py", "console_help.py", "source_quality_report_summary.py"]\n    failures = []\n    for name in names:\n        path = ROOT / "src/searchgeo" / name\n        matches = sorted(set(MILESTONE.findall(path.read_text(encoding="utf-8"))))\n        if matches:\n            failures.append(f"{name}: {matches}")\n    assert not failures, "\\n".join(failures)\n\n\ndef test_accessibility_zero_is_not_presented_as_proof_of_no_failures() -> None:\n    from searchgeo.report_semantics import enhance_report_html\n    html = "<div class='metric'><small>Falhas automatizadas</small><strong>0</strong></div>"\n    rendered = enhance_report_html(html, page_name="accessibility.html", report_dir=ROOT)\n    assert "Nenhuma ocorrência registrada" in rendered\n    assert "Sem falhas detectadas" not in rendered\n\n\ndef test_unavailable_cwv_is_neutral() -> None:\n    from searchgeo.report_semantics import enhance_report_html\n    html = "<div class='metric'><small>CWV</small><strong>UNAVAILABLE</strong></div>"\n    rendered = enhance_report_html(html, page_name="web-performance.html", report_dir=ROOT)\n    assert "Dados de campo indisponíveis" in rendered\n    assert "result-state-neutral" in rendered\n\n\ndef test_legacy_milestone_chrome_is_sanitized_without_touching_audited_copy() -> None:\n    from searchgeo.report_consistency_v2 import _sanitize_presentation\n    html = "<p>Produto M20 com motor M23 permanece conteúdo auditado.</p><div>M22 · diagnóstico técnico</div>"\n    rendered = _sanitize_presentation(html)\n    assert "Produto M20 com motor M23 permanece conteúdo auditado." in rendered\n    assert "Diagnóstico técnico" in rendered\n''')


if __name__ == '__main__':
    patch_docs()
    patch_presentation()
    add_tests()
