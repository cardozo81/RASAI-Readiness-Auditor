# WORKFLOWS.md

**Status:** APPROVED — reconciliado com RASAi/SARI-001, `SCORE-GEO-003`, device context configurável e REPORT-SITE-GEO-001

## 1. Princípios

- Evidence before conclusion.
- Failure isolation.
- Desktop/Mobile isolation quando ambos forem selecionados.
- Escopo explícito de dispositivo.
- AI optionality.
- Reliability disclosure.
- Actionable remediation must remain evidence-bound.
- Readiness, outcomes observados, performance/experience e acessibilidade permanecem metodologias separadas.

## 2. Catálogo

- WF-GEO-001 Execute Website Audit
- WF-GEO-002 Initialize Audit
- WF-GEO-003 Discover URLs
- WF-GEO-004 Acquire Page Snapshot
- WF-GEO-005 Execute Technical Analysis
- WF-GEO-006 Extract Page Content
- WF-GEO-007 Execute Semantic Analysis
- WF-GEO-008 Compare Desktop and Mobile
- WF-GEO-009 Consolidate Findings and Scores
- WF-GEO-010 Generate Recommendations and Remediation
- WF-GEO-011 Generate Static Actionable HTML Report Site
- WF-GEO-012 Complete Audit

Monitoramento histórico e observabilidade externa são workflows derivados, executados sobre um `AUD-*` já persistido, e não fazem parte do pipeline transacional de WF-GEO-001.

## 3. WF-GEO-001

Fluxo:

Initialize
→ Resolve Device Context
→ Discover
→ For each Page
→ Snapshot(s) dos dispositivos selecionados
→ Technical
→ Extract
→ Semantic/Fallback
→ Compare quando Desktop + Mobile estiverem no escopo
→ Findings
→ Scores
→ Priority
→ Remediation
→ Report Site
→ Complete

A CLI resolve `mobile|desktop|both`, com default `mobile`. Chamadas internas que não passam por essa configuração podem preservar comportamento legado definido pela arquitetura, desde que não alterem o contrato público da CLI.

## 4. WF-GEO-002 Initialize Audit

- validar target;
- gerar Audit ID;
- criar diretórios;
- inicializar persistência;
- detectar capabilities;
- determinar FULL / DEGRADED / NO_AI;
- resolver contexto de dispositivo efetivo.

Falha de BR-GEO-001 encerra a auditoria.

## 5. WF-GEO-003 Discover URLs

Fontes:

- seed;
- robots/sitemap;
- sitemap;
- internal links;
- redirects elegíveis.

Depois:

- normalize;
- deduplicate;
- apply scope;
- apply max_pages.

Se descobertas > max_pages, registrar total descoberto e total auditado.

O estado necessário para explicar discovery no relatório deve ser persistido como Page, Evidence e Audit limitation; WF-GEO-011 não depende do objeto Descoberta e aquisição HTTP em memória.

## 6. WF-GEO-004 Acquire Page Snapshot

Executar separadamente para cada dispositivo selecionado no audit:

- `MOBILE` quando `mobile` ou `both`;
- `DESKTOP` quando `desktop` ou `both`.

Passos:

1. HTTP acquisition;
2. RAW preservation;
3. browser render;
4. rendered DOM capture;
5. snapshot metadata.

Não produzir snapshot do dispositivo não selecionado apenas para manter simetria de relatório ou IA.

## 7. WF-GEO-005 Technical Analysis

Ordem:

Retrievability
→ HTTP
→ Redirect
→ HTML
→ Indexability
→ Canonical
→ Robots
→ Rendering
→ SPA/Routes

Sempre verificar applicability e dependencies antes da regra.

## 8. WF-GEO-006 Extract Page Content

Entrada:

- RAW;
- Rendered DOM dos contextos selecionados.

Saída:

- main content;
- metadata;
- headings;
- links;
- Dados Estruturados;
- evidence.

Distinguir falha do site de falha do extrator.

## 9. WF-GEO-007 Semantic Analysis

### FULL

Evidence
→ Input Builder
→ Semantic Provider
→ Strict schema validation
→ Evidence validation
→ SemanticAssessment
→ normalized RuleExecution/Finding

### NO_AI

Deterministic components
→ safe heuristics
→ semantic-only UNKNOWN

### DEGRADED

Provider falhou
→ fallback permitido pelo contrato do provider/routing
→ limitation codes
→ UNKNOWN quando necessário

Business Rules nunca dependem diretamente de provider específico.

O relatório reutiliza SemanticAssessment, reasoning_summary, entities, intents e evidence_ids já persistidos. Não existe segunda chamada livre de IA apenas para redigir recomendações.

O provider semântico só pode ser chamado para contexto de dispositivo efetivamente selecionado e materializado.

## 10. WF-GEO-008 Desktop × Mobile

Quando `both` estiver selecionado, compara resultados dos snapshots e avaliações.

Resultado:

- SAME;
- DIFFERENT;
- NOT_APPLICABLE;
- UNKNOWN.

Finding somente para diferença material.

Quando o audit for `mobile` ou `desktop`, BR-GEO-052 deve ser `NOT_APPLICABLE` com reason code `DEVICE_COMPARISON_DISABLED_BY_CONTEXT`. Isso representa ausência intencional de universo comparativo, não snapshot faltante nem falha de rendering.

## 11. WF-GEO-009 Findings and Scores

- validar BR-GEO-053;
- deduplicar efeitos de causa raiz;
- calcular contribuições determinísticas das dimensões;
- calcular score das dimensões;
- calcular Coverage;
- calcular Confidence;
- resolver Consolidation;
- aplicar `SCORE-GEO-003` ao Overall somente quando existir model artifact `VALIDATED` compatível;
- validar BR-GEO-054.

Baseline vigente para novas auditorias: `SCORE-GEO-003`.

As dez dimensões usam cálculo determinístico baseado em regras. O Overall `SCORE-GEO-003` é calibrado e não possui fallback silencioso para outro cálculo. Sem model artifact `VALIDATED`, o Overall permanece `NOT_CONSOLIDATED`.

Score, Coverage e Confidence têm semânticas diferentes. Confidence baixa qualifica a força da conclusão; não significa, isoladamente, baixa qualidade textual do website.

## 12. WF-GEO-010 Recommendations and Remediation

Fluxo aprovado:

```text
Finding evidence-backed
→ Root Cause
→ Remediation Group
→ Severity / Impact / Effort / Confidence
→ Priority
→ Remediation Recipe por rule_id
→ Recommendation persistida
```

A `RemediationRecipe` deve tentar responder, quando aplicável:

- alvo técnico;
- elemento/localização;
- ação;
- descrição;
- exemplo seguro;
- critérios de aceite;
- revalidação;
- decisão humana necessária.

Invariantes:

- recipe não altera score ou priority;
- recipe não cria evidence;
- example não é HTML observado;
- ausência de recipe específica usa fallback explícito;
- canonical, noindex, structured data, autoria, freshness e fontes não podem ser inventados ou alterados sem base suficiente.

Sem IA, recipes técnicas continuam funcionando.

## 13. WF-GEO-011 Actionable HTML Report Site

Ponto de entrada público:

`report/index.html`

Arquivos públicos complementares, conforme aplicabilidade/materialização:

```text
report/readiness.html             # SARI-001
report/score-geo-003.html         # método/modelo/dataset/gates
report/mobile.html                # quando Mobile foi auditado
report/desktop.html               # quando Desktop foi auditado
report/remediation.html
report/content-suggestions.html
report/crawling-discovery.html
report/accessibility.html
report/web-performance.html
report/apdex.html
report/apdex-experience.html
report/ai-visibility.html         # Observed Generative Visibility
report/observability.html         # Search/AI outcomes + diagnósticos derivados, quando materializado
report/ai-usage.html
report/references.html
report/css/site.css
```

Sem backend, servidor, CDN ou internet obrigatória para leitura local do resultado já materializado.

A projeção deve separar por domínio:

1. visão executiva e limitações em `index.html`;
2. SARI, Score/Coverage/Confidence/Consolidation em `readiness.html`;
3. contrato/calibração do `SCORE-GEO-003` em `score-geo-003.html`;
4. findings/evidências por dispositivo em `mobile.html` / `desktop.html`;
5. plano de correção por ocorrência em `remediation.html`;
6. métricas externas em suas páginas próprias;
7. outcomes observados em `ai-visibility.html` / `observability.html`, sem fusão automática ao SARI;
8. telemetria operacional de IA em `ai-usage.html`;
9. metodologia, classificação de fontes e referências técnicas em `references.html`.

Todos os HTMLs finais compartilham navegação e `report/css/site.css`. CSS inline/embutido não é contrato do report site final, exceto páginas derivadas standalone explicitamente documentadas (por exemplo `MON-*`).

### Regra de compatibilidade

`OVERALL_READINESS` somente é exibido como número quando o score persistido possui valor consolidável segundo a versão do método registrada no próprio AUD.

Para `SCORE-GEO-003`, isso exige model artifact compatível e `VALIDATED`. Quando não for consolidável:

```text
READINESS GERAL: NÃO CONSOLIDADA
```

Coverage não pode substituir a nota. Séries com contratos de scoring distintos não são misturadas silenciosamente.

### Regra de HTML observado

O report deve separar:

- HTML efetivamente persistido como evidência;
- exemplo de correção recomendado.

Se o trecho original não estiver persistido na Evidence:

```text
Trecho HTML original não persistido para esta evidência.
```

### Crawl

WF-GEO-011 reabre Pages, Audit limitations e Evidence de robots/sitemap/HTTP para explicar descoberta, max_pages, fontes e limitações de crawl. Não recebe `DiscoveryResult` em memória.

### Fonte de verdade

O report site é projeção para leitura humana. `audit.db` + artifacts persistidos continuam sendo a fonte de verdade do audit. `observability.db` é sidecar derivado para dados externos coletados/importados posteriormente e nunca reescreve a evidência do AUD.

## 14. WF-GEO-012 Complete Audit

Verificar:

- `report/index.html` reabrível;
- páginas condicionais coerentes com os dispositivos auditados;
- CSS compartilhado reabrível;
- metadata;
- finding integrity;
- score reproducibility;
- limitations;
- artifacts;
- ausência de HTML público legado na raiz após materialização bem-sucedida.

Resultados:

COMPLETED + COMPLETE

ou

COMPLETED + COMPLETE_WITH_LIMITATIONS

FAILED somente quando não foi possível executar auditoria funcional mínima.

## 15. Workflows derivados: Monitor e Observability

Após um AUD concluído, podem ser executados workflows independentes:

```text
AUD baseline + AUD atual
→ leitura read-only de audit.db
→ comparabilidade
→ ChangeEvents
→ release gate determinístico opcional
→ MON-*/report.html
→ impact.html opcional
```

```text
AUD existente
→ coleta/import de outcome externo documentado
→ observability.db + artifact preservado
→ Indexability Reality Matrix / Query × Intent / CrUX History / diagnósticos
→ report/observability.html
```

Falha nesses workflows derivados não altera status, scoring ou evidências do audit fonte.
