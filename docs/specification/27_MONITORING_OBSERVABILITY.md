# RASAI Monitor & Search/AI Observability

**Status:** IMPLEMENTED CANDIDATE — PR #82; CI obrigatória no head corrente e smoke humano requerido antes do merge.
**Natureza:** capacidades derivadas/complementares, read-only sobre a evidência de auditoria e non-scoring por padrão.

## 1. Objetivo

Adicionar ao RASAI observabilidade longitudinal e outcomes externos sem transformar sinais heterogêneos em um score transversal nem alterar silenciosamente `SARI-001`/`SCORE-GEO-003`.

A capacidade responde separadamente:

1. o que mudou entre duas auditorias persistidas;
2. se a mudança é regressão, melhoria, alteração neutra, sinal novo ou não comparável;
3. se um release deve ser bloqueado por deterioração determinística ou par metodologicamente não comparável;
4. quais outcomes externos Search/AI foram observados;
5. se há coocorrência temporal entre mudança técnica e outcome observado, sem afirmar causalidade.

## 2. Fronteira metodológica

- `SARI-001` permanece o índice público de readiness;
- `SCORE-GEO-003` permanece o scoring vigente para novas auditorias;
- `SCORE-GEO-002` permanece histórico;
- Monitoring não cria novo score;
- Search/AI Observability não entra automaticamente no SARI;
- Search Performance, URL Inspection, CrUX History, Bing/AI outcomes e diagnósticos derivados permanecem identificados por fonte/método;
- correlação/coocorrência não pode ser descrita como causalidade;
- dado ausente não é zero, PASS ou FAIL;
- mudança sem direção documental segura permanece `CHANGED`.

## 3. Persistência

### 3.1 Audit fonte

Monitoring abre `AUD-*/audit.db` em modo SQLite read-only/query-only. Nenhuma operação `compare`, `gate`, `impact`, `quality`, `observe` pós-auditoria ou calibração derivada pode modificar a fonte apenas para produzir diagnóstico/report.

### 3.2 Sidecar observacional

Dados externos coletados/importados após o audit são persistidos em:

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

Contrato atual do sidecar: `RASAI-OBS-002`.

Regras:

- `observability.db` não substitui nem migra `audit.db`;
- observações usam identidade namespaced por dataset, com PK composta `(dataset_id, record_id)` nas tabelas de observação;
- sidecars `RASAI-OBS-001` com PK global de `record_id` são migrados preservando rows/dataset provenance;
- o `format_version` de datasets históricos não é sobrescrito apenas por abrir/migrar o sidecar;
- artifacts mantêm SHA-256 do conteúdo fonte preservado;
- bearer token, API key ou credencial não podem aparecer em SQLite, artifact, HTML ou log produzido por esses collectors.

## 4. RASAI Monitor

### 4.1 Compare

```text
rasai monitor compare --baseline AUD-X --current AUD-Y
```

Classificações admitidas:

```text
REGRESSED
IMPROVED
CHANGED
NEW
RESOLVED
UNCHANGED
DATA_UNAVAILABLE
NOT_COMPARABLE
```

Regras obrigatórias:

- `UNKNOWN`, `ERROR` ou `NOT_APPLICABLE` não podem ser convertidos arbitrariamente em `FAIL`;
- versões de scoring sem sobreposição geram `NOT_COMPARABLE` para sinais SCORE, sem conversão entre métodos;
- Mobile/Desktop permanecem separados;
- diferença de domain set torna o par globalmente não comparável;
- mudança de URL universe, device set e ruleset deve ser exposta como limitação quando aplicável;
- alterações de estado sem direção conhecida são `CHANGED`, não regressão inventada;
- ausência do sinal no AUD atual é `DATA_UNAVAILABLE`, não resolução automática.

### 4.2 Release gate

```text
rasai monitor gate ...
```

Default operacional é **fail-closed** e deterministic-only.

```text
0 PASS
1 BLOCKED_BY_DETERIORATION_OR_INCOMPARABILITY
2 EXECUTION_ERROR
```

Escopo default:

- regras BR-GEO determinísticas suportadas;
- page state determinístico;
- par baseline/current deve ser comparável;
- regressões materiais bloqueiam conforme severidade/threshold;
- sinais `NEW` materialmente ruins também são elegíveis para bloqueio;
- performance, Synthetic Apdex, aggregates de findings e dimensões SCORE permanecem fora do gate até opt-in explícito.

Overrides deliberados:

```text
--allow-noncomparable
--allow-new-failures
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
```

`--allow-noncomparable` e `--allow-new-failures` são escapes operacionais explícitos, não defaults e não mudam SARI/SCORE-GEO.

### 4.3 Change Impact

```text
rasai monitor impact ...
```

Pode comparar mudanças técnicas com Search Performance, estado/canonical observado via URL Inspection, CrUX History e outros outcomes suportados.

Regras:

- seleciona um dataset mais recente por `source_type`; datasets históricos sobrepostos não são somados;
- janelas devem ser idênticas ou parcialmente sobrepostas para emitir associação temporal;
- janelas não sobrepostas/sem período não geram associação;
- `NULL` permanece indisponível e nunca vira zero observado;
- a saída usa `TEMPORAL_ASSOCIATION_ONLY`/equivalente e declara causalidade não estabelecida;
- Google Generative AI Performance export é tratado como **não direcional** no Change Impact, porque valores não numéricos/indisponíveis do relatório podem aparecer como zero no download; a variação é exibida como `CHANGED`, não automaticamente como `REGRESSED`/`IMPROVED`.

## 5. Google Search Console

Autenticação usa OAuth bearer token em runtime (`GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` por default da CLI). O token nunca é persistido.

### 5.1 Properties / Sites

```text
rasai observe gsc-sites ...
```

Consulta read-only de propriedades acessíveis para descoberta operacional. Não altera property, sitemap ou Search Console.

### 5.2 Sitemaps

```text
rasai observe gsc-sitemaps --site-url ...
```

Consulta read-only de sitemaps. Campos deprecated não devem ser ressuscitados como evidência atual; o RASAI persiste apenas o subset normalizado suportado e mantém o response externo como provenance quando apropriado.

### 5.3 Search Analytics

```text
rasai observe gsc-search ...
rasai observe gsc-appearance ...
```

Coleta via API oficial Search Analytics, com paginação bounded (`rowLimit <= 25000`) e `max_rows` local.

Regras de escopo:

- a dimensão `page` é obrigatória no collector RASAI para vincular cada row ao AUD;
- rows cuja `page` não pertença a um `normalized_origin` auditado são excluídos;
- rows fora de escopo também são removidos do artifact persistido daquele AUD;
- metadata informa `api_rows_seen` e `excluded_out_of_scope_rows`;
- se a API retornar dados, mas nenhum row pertencer ao origin auditado, a coleta falha como erro de escopo/configuração e não cria sidecar enganoso;
- `searchAppearance` é source/surface separada de Search Analytics convencional.

Clicks, impressions, CTR e average position permanecem métricas reportadas pela fonte. Search Analytics pode retornar top rows em vez de todas as linhas existentes na property; essa limitação deve permanecer explícita.

### 5.4 URL Inspection

```text
rasai observe gsc-inspect ...
```

Somente URLs já persistidas no AUD podem ser solicitadas. `--max-urls` limita quota.

Campos observáveis podem incluir verdict/coverage/indexing state, robots state, fetch state, last crawl, crawled-as, user-declared canonical, Google-selected canonical e referring/sitemap URLs quando retornados.

URL Inspection representa estado conhecido pelo índice; não é live test.

Failure policy:

- erro potencialmente específico da URL pode ser persistido como observação `ERROR` e o lote continua;
- HTTP 401/403/429, falha de rede e 5xx selecionados são sistêmicos: o lote aborta imediatamente, evitando repetir a mesma falha para todas as URLs;
- falha sistêmica antes da persistência não cria sidecar parcial dessa coleta.

## 6. CrUX History

```text
rasai observe crux-history ...
```

A coleta usa o endpoint oficial CrUX History quando habilitada.

Regras:

- `target_scope` é `url` ou `origin`;
- target deve ser HTTP(S) absoluto e pertencer exatamente a um `normalized_origin` do AUD;
- `origin` não admite path/query/fragment e é normalizado antes da request;
- validação de escopo ocorre antes da chamada externa;
- `collectionPeriodCount` é bounded a 40;
- API key não entra no artifact.

LCP, INP e CLS permanecem field/RUM aggregate evidence e não são fundidos com Lighthouse lab, Synthetic Navigation Apdex, Synthetic User Experience Apdex ou SARI. Ausência de CrUX é insuficiência de campo, não finding do website.

## 7. Imports e AI outcomes

### 7.1 Contrato genérico

`RASAI-OBS-IMPORT-001` aceita arrays normalizados de Search Performance, Index Observations e CrUX History.

Hardening obrigatório:

- URLs de Search/Index devem pertencer ao origin auditado;
- CrUX importado também deve respeitar origin do AUD e `URL|ORIGIN` válidos;
- `ORIGIN` não aceita path/query/fragment;
- períodos invertidos são rejeitados;
- metadata deve ser objeto JSON quando declarada.

### 7.2 Bing Search Performance

Opera import-first quando não existe contrato direto implementado/documentado para a superfície. O mesmo CSV pode ser importado com `--surface` explícito sem colisão: o surface passa a participar da identidade/source type do dataset, enquanto o SHA do artifact continua representando os bytes originais do CSV.

### 7.3 Google Generative AI Performance

Opera import-first sobre export oficial, separado por `search` e `discover`.

- preserva somente métricas efetivamente presentes;
- não inventa clicks, CTR, position, query ou citation count;
- tokens como `~`, `-`/equivalentes de indisponibilidade/supressão são registrados com semântica explícita;
- zero exportado não é interpretado isoladamente como prova de zero visibility;
- no Change Impact, essas impressões são non-directional conforme §4.3.

### 7.4 Google GenAI control

```text
rasai observe google-ai-control --state INCLUDE|EXCLUDE|INHERIT
```

Persiste apenas o estado observado/declarado e provenance; `scoring_impact=NONE`.

## 8. Indexability Reality Matrix

A projeção pode cruzar HTTP/final URL local, meta robots, canonical declarado e estados externos observados via URL Inspection.

Divergência de canonical é fato observado; não se torna automaticamente finding causal de tráfego.

## 9. Query × Intent Alignment

Queries observadas podem ser comparadas com intents já persistidas pelas regras RASAI. O matching é lexical, explicável e conservador.

```text
ALIGNED
PARTIAL
UNMATCHED
INTENT_NOT_AVAILABLE
```

Essa saída não é ranking factor, keyword score nem contribuição de SARI.

## 10. Potential Search Cannibalization

Pode ser emitido candidato quando pelo menos duas URLs dividirem materialmente a mesma query/fonte. Na implementação inicial, cada URL material deve representar pelo menos 20% das impressões observadas daquela query/fonte.

O diagnóstico permanece `POTENTIAL_CANNIBALIZATION`: múltiplas URLs não provam dano.

## 11. Diagnósticos complementares

Observability pode materializar diagnósticos advisory sem criar BR-GEO adicional:

- Structured Data documentation completeness;
- entity consistency;
- freshness/date conflicts;
- hreflang syntax/absolute URL/self-reference/reciprocity quando verificável;
- retrieval/chunkability;
- table header relationships;
- template/root-cause clustering.

Regras:

- não inventar Rich Results API/score;
- não marcar `Organization` inválido por ausência de propriedade que a documentação não define como obrigatória;
- freshness usa timestamp persistido do AUD/snapshot, não wall clock da regeneração do report;
- reciprocity hreflang só é concluída contra variantes observadas no universo auditado;
- selector só sustenta provável causa compartilhada quando confiável; agrupamento por título sem selector é apenas cluster.

## 12. RASAI Quality & Verification

A qualidade da própria auditoria é tratada em especificação separada: `28_AUDIT_QUALITY_VERIFICATION.md`.

`report/quality.html`, Fix Verification e Evidence Timeline são non-scoring. No HTML executivo, Top Operational Priorities inclui apenas findings acionáveis; `RESOLVED`, `CLOSED` e `DISMISSED` permanecem no histórico de Evidence Confidence, mas não contam como fila ativa P0/P1.

Leituras de artifact usadas por Quality devem permanecer confinadas ao workspace do AUD; referência `../`/path traversal não é seguida.

## 13. Calibration Dataset Manager

```text
rasai scoring dataset --dataset-version VERSION
```

Avalia suficiência pré-fit e produz manifest/fingerprint determinístico conforme `SCORE-GEO-003`. `READY_FOR_MODEL_FIT` não equivale a `VALIDATED`; AUC/Brier e demais gates pós-fit continuam necessários.

## 14. Reporting

### Per-audit

```text
report/observability.html
report/quality.html
```

Observability contém provenance/datasets, matriz de indexabilidade, diagnósticos complementares, Query × Intent, cannibalization candidates, clusters, CrUX History, referências e fronteira non-scoring/non-causal.

Quality descreve Audit Health, Evidence Confidence, Operational Priority acionável, Coverage Map, content controls e Recommendation Validation sem recalcular SARI.

### Monitoring / Verification / Timeline

```text
monitoring/MON-*/report.html
monitoring/MON-*/manifest.json
monitoring/MON-*/impact.html
verification/VER-*/report.html
quality/TIMELINE-*/report.html
```

## 15. Navegação HTML

O registry final é canônico e condicionado à existência dos arquivos. Página opcional gerada posteriormente não pode remover outra já materializada. A página corrente é o único item ativo.

## 16. Failure isolation

- falha de collector externo não invalida auditoria principal;
- ausência de credencial só bloqueia o comando dependente;
- `observe report` funciona sem dataset externo e produz empty state;
- Monitoring permanece read-only;
- erros de autenticação/quota/rede são operacionais, não findings do website;
- dados fora do origin auditado são rejeitados/excluídos, não incorporados silenciosamente.

## 17. Segurança

- validar/sanitizar URLs e inputs externos;
- preservar scoping do AUD antes de persistir;
- não persistir secrets;
- limitar quotas (`max_rows`, `max_urls`, períodos);
- artifacts externos são untrusted input;
- leituras de artifact devem permanecer dentro do workspace;
- sidecar e relatórios derivados não podem modificar evidence/rules/scores do AUD.

## 18. Critérios de aceite automatizados

CI dedicada deve cobrir pelo menos:

- compile dos módulos novos;
- leitura read-only e comparabilidade;
- gate determinístico e fail-closed;
- blocking de `NEW` failures materiais;
- opt-outs explícitos;
- migração OBS-001→OBS-002 e identidade composta;
- coexistência de datasets/surfaces sem colisão;
- scoping de Search Analytics e CrUX;
- URL Inspection systemic failure policy;
- ausência de secrets em artifacts;
- GenAI export non-directional no Change Impact;
- diagnostics evidence-bound;
- Quality actionable priorities e filesystem confinement;
- dataset pré-fit/calibration hardening;
- regressões SCORE-GEO-003, M24, M25, M26 e consolidated reporting;
- navegação canônica das páginas opcionais.

## 19. Critérios de smoke humano

Antes do merge:

1. executar `monitor compare` sobre dois AUDs reais comparáveis;
2. abrir `MON-*/report.html` e conferir classificações/URLs/devices;
3. executar `monitor gate` e confirmar exit esperado; testar deliberadamente um caso `NEW` ruim se disponível;
4. gerar `quality.html`, Fix Verification e Timeline;
5. executar `observe report` sem dataset externo e conferir empty state;
6. com credencial válida, testar `gsc-sites`, `gsc-sitemaps`, `gsc-search`, `gsc-appearance` e `gsc-inspect`;
7. quando elegível, validar CrUX History para URL/origin do próprio AUD;
8. validar Bing e Google GenAI import-first quando houver exports;
9. abrir todas as páginas materializadas e conferir menu/order/active state;
10. confirmar `SCORE-GEO-003` vigente e `002` somente histórico;
11. confirmar hash de `audit.db` inalterado antes/depois de monitor/observe/quality;
12. confirmar que secrets não aparecem em `observability.db`, artifacts ou HTML.
