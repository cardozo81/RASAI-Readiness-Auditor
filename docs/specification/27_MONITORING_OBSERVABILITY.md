# RASAi Monitor & Search/AI Observability

**Status:** IMPLEMENTED CANDIDATE - PR #82; CI obrigatória no head corrente e smoke humano requerido antes do merge.
**Natureza:** capacidades derivadas/complementares, read-only sobre a evidência de auditoria e non-scoring por padrão.

## 1. Objetivo

Adicionar ao RASAi observabilidade longitudinal e outcomes externos sem transformar sinais heterogêneos em um score transversal nem alterar silenciosamente `SARI-001`/`SCORE-GEO-003`.

A capacidade responde separadamente:

1. o que mudou entre duas auditorias persistidas;
2. se a mudança é regressão, melhoria, alteração neutra, sinal novo ou não comparável;
3. se um release deve ser bloqueado por deterioração determinística ou par metodologicamente não comparável;
4. quais outcomes externos Search/AI foram observados;
5. se há coocorrência temporal entre mudança técnica e outcome observado, sem afirmar causalidade.

## 2. Fronteira metodológica

- `SARI-001` permanece o índice público de readiness;
- `SCORE-GEO-003` permanece o scoring vigente para novas auditorias;
- Monitoring não cria novo score;
- Search/AI Observability não entra automaticamente no SARI;
- Search Performance, URL Inspection, CrUX History, Bing/AI outcomes e diagnósticos derivados permanecem identificados por fonte/método;
- correlação/coocorrência não pode ser descrita como causalidade;
- dado ausente não é zero, PASS ou FAIL;
- mudança sem direção documental segura permanece `CHANGED`.

## 3. Persistência

### 3.1 Audit fonte

Monitoring abre `AUD-*/audit.db` em SQLite `mode=ro`/`query_only`. Nenhuma operação derivada pode modificar a fonte apenas para produzir diagnóstico ou report.

### 3.2 Sidecar observacional

Dados externos coletados/importados após o audit são persistidos em:

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

Contrato atual: `RASAI-OBS-002`.

Regras:

- `observability.db` não substitui nem migra `audit.db`;
- observações usam PK composta `(dataset_id, record_id)`;
- sidecars OBS-001 com PK global de `record_id` são migrados preservando rows e provenance;
- o `format_version` de dataset histórico não é reescrito apenas por abrir/migrar o sidecar;
- artifacts mantêm SHA-256;
- token OAuth, API key e credencial não podem aparecer em SQLite, artifact, HTML ou log produzido pelos collectors.

## 4. RASAi Monitor

### 4.1 Compare

```text
rasai monitor compare --baseline AUD-X --current AUD-Y
```

Classificações:

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

Regras:

- `UNKNOWN`, `ERROR` ou `NOT_APPLICABLE` não viram `FAIL` arbitrariamente;
- scoring sem versão comum gera `NOT_COMPARABLE` para sinais SCORE;
- Mobile/Desktop permanecem separados;
- diferença de domain set torna o par globalmente não comparável;
- diferenças de URL universe, device set e ruleset são expostas como limitações;
- estado sem direção conhecida é `CHANGED`;
- ausência do sinal atual é `DATA_UNAVAILABLE`, não resolução automática.

### 4.2 Release gate

```text
rasai monitor gate ...
```

Default: **fail-closed** e deterministic-only.

```text
0 PASS
1 BLOCKED_BY_DETERIORATION_OR_INCOMPARABILITY
2 EXECUTION_ERROR
```

Escopo default:

- BR-GEO determinísticas suportadas;
- page-state determinístico;
- par baseline/current comparável;
- regressões materiais conforme severidade/threshold;
- sinais `NEW` materialmente ruins também elegíveis para bloqueio.

Ficam fora até opt-in explícito:

```text
--include-semantic
--include-performance
--include-synthetic
--include-finding-aggregates
--include-score-dimensions
```

Overrides deliberados:

```text
--allow-noncomparable
--allow-new-failures
```

Esses overrides não alteram SARI/SCORE-GEO; apenas mudam a política operacional do gate.

### 4.3 Change Impact

```text
rasai monitor impact ...
```

Regras:

- seleciona um dataset mais recente por `source_type`; históricos sobrepostos não são somados;
- associação temporal exige janelas idênticas ou parcialmente sobrepostas;
- janela não sobreposta ou sem período não gera associação;
- `NULL` permanece indisponível e nunca vira zero observado;
- a saída usa `TEMPORAL_ASSOCIATION_ONLY` e declara causalidade não estabelecida;
- Google Generative AI Performance export é não direcional no Change Impact porque valores indisponíveis/não numéricos podem aparecer como zero no download; a variação é `CHANGED`, não automaticamente `REGRESSED`/`IMPROVED`.

## 5. Google Search Console

Autenticação usa OAuth bearer token em runtime (`RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` por default da CLI). O token nunca é persistido.

### 5.1 Properties / Sites

```text
rasai observe gsc-sites ...
```

Consulta read-only de propriedades acessíveis para descoberta operacional.

### 5.2 Sitemaps

```text
rasai observe gsc-sitemaps --site-url ...
```

Consulta read-only. Campos deprecated não são usados como evidência atual.

### 5.3 Search Analytics / Search Appearance

```text
rasai observe gsc-search ...
rasai observe gsc-appearance ...
```

Regras:

- paginação bounded (`rowLimit <= 25000`) e `max_rows` como teto local real;
- dimensão `page` obrigatória para vincular row ao AUD;
- row cuja página não pertença a um `normalized_origin` auditado é excluída;
- row fora de escopo também é removida do artifact persistido;
- metadata registra `api_rows_seen` e `excluded_out_of_scope_rows`;
- se houver resposta mas nenhum row do origin auditado, a coleta falha como erro de escopo/configuração;
- `searchAppearance` usa provenance separada de Search Analytics convencional;
- a limitação de cobertura/top rows da fonte permanece explícita.

### 5.4 URL Inspection

```text
rasai observe gsc-inspect ...
```

Somente URLs persistidas no AUD são elegíveis. URL Inspection representa estado conhecido pelo índice, não live test.

Failure policy:

- erro potencialmente específico da URL pode ser persistido como `ERROR` e o lote continuar;
- HTTP 401/403/429, falha de rede e 5xx selecionados são tratados como sistêmicos e abortam o lote;
- falha sistêmica antes da persistência não cria sidecar parcial daquela coleta.

## 6. CrUX History

```text
rasai observe crux-history ...
```

Regras:

- `target_scope` é `url` ou `origin`;
- target HTTP(S) absoluto e do próprio `normalized_origin` do AUD;
- `origin` não admite path/query/fragment;
- scoping ocorre antes da chamada externa;
- `collectionPeriodCount` limitado a 40;
- API key não entra no artifact.

LCP, INP e CLS permanecem field/RUM aggregate evidence, separados de Lighthouse, Synthetic Apdex e SARI.

## 7. Imports e AI outcomes

### 7.1 Contrato genérico

`RASAI-OBS-IMPORT-001` aceita Search Performance, Index Observations e CrUX History normalizados.

Obrigatório:

- Search/Index URLs dentro do origin auditado;
- CrUX importado dentro do origin auditado;
- escopo `URL|ORIGIN` válido;
- `ORIGIN` sem path/query/fragment;
- períodos não invertidos;
- metadata como objeto JSON.

### 7.2 Bing Search Performance

Import-first quando não existe contrato direto implementado/documentado. O mesmo CSV pode coexistir por `--surface`; o surface participa da identidade/provenance, enquanto o SHA representa os bytes originais do artifact.

### 7.3 Google Generative AI Performance

Import-first, separado por Search/Discover.

- persiste apenas métricas realmente presentes;
- não inventa clicks, CTR, position, query ou citation count;
- tokens de indisponibilidade/supressão recebem semântica explícita;
- zero exportado não é prova isolada de zero visibility;
- impressões permanecem não direcionais no Change Impact.

### 7.4 Google GenAI control

```text
rasai observe google-ai-control --state INCLUDE|EXCLUDE|INHERIT
```

Persiste estado observado/declarado e provenance; `scoring_impact=NONE`.

## 8. Diagnósticos observacionais

Podem ser materializados, sem criar nova contribuição automática ao SARI:

- Indexability Reality Matrix;
- Query × Intent Alignment (`ALIGNED`, `PARTIAL`, `UNMATCHED`, `INTENT_NOT_AVAILABLE`);
- `POTENTIAL_CANNIBALIZATION` conservador;
- Structured Data documentation completeness;
- entity consistency;
- freshness/date conflicts com data persistida do AUD/snapshot;
- hreflang syntax/self-reference/reciprocity quando verificável;
- retrieval/chunkability;
- table header relationships;
- template/root-cause clustering.

Divergência observada não é automaticamente causalidade ou ranking factor.

## 9. RASAi Quality & Verification

Contrato detalhado: `28_AUDIT_QUALITY_VERIFICATION.md`.

`report/quality.html`, Fix Verification e Evidence Timeline são non-scoring. Top Operational Priorities contém apenas findings acionáveis; `RESOLVED`, `CLOSED` e `DISMISSED` permanecem no histórico, mas não entram na fila ativa P0/P1.

Leitura de artifact deve permanecer confinada ao workspace do AUD; referência `../`/path traversal não é seguida.

## 10. Calibration Dataset Manager

```text
rasai scoring dataset --dataset-version VERSION
```

Produz manifest/fingerprint e avalia suficiência pré-fit conforme SCORE-GEO-003. `READY_FOR_MODEL_FIT` não equivale a `VALIDATED`; AUC/Brier e gates pós-fit continuam necessários.

## 11. Reporting

### Per-audit

```text
report/observability.html
report/quality.html
```

### Monitoring / Verification / Timeline

```text
monitoring/MON-*/report.html
monitoring/MON-*/manifest.json
monitoring/MON-*/impact.html
verification/VER-*/report.html
quality/TIMELINE-*/report.html
```

## 12. Navegação HTML

O registry é canônico e condicionado à existência dos arquivos. Página opcional gerada depois não pode remover outra já materializada. Somente a página corrente fica ativa.

## 13. Failure isolation e segurança

- falha de collector externo não invalida auditoria principal;
- ausência de credencial bloqueia apenas o comando dependente;
- `observe report` funciona sem dataset externo;
- Monitoring permanece read-only;
- autenticação/quota/rede são erros operacionais, não findings do website;
- dados fora do origin auditado são rejeitados/excluídos;
- secrets não são persistidos;
- quotas e períodos são limitados;
- artifacts externos são untrusted input;
- relatórios/sidecars derivados não podem modificar evidence/rules/scores do AUD.

## 14. Critérios de aceite automatizados

CI deve cobrir pelo menos:

- compile dos módulos novos;
- leitura read-only e comparabilidade;
- gate determinístico/fail-closed e `NEW` failures;
- opt-outs explícitos;
- migração OBS-001→OBS-002 e identidade composta;
- coexistência de datasets/surfaces;
- scoping Search Analytics/CrUX;
- URL Inspection systemic failure policy;
- ausência de secrets em artifacts;
- GenAI non-directional no Change Impact;
- diagnostics evidence-bound;
- Quality actionable priorities e filesystem confinement;
- dataset pré-fit/calibration hardening;
- regressões de SCORE-GEO-003, crawling/discovery, Synthetic User Experience Apdex, Observed Generative Visibility, source quality e consolidated reporting;
- navegação canônica das páginas opcionais.

## 15. Critérios de smoke humano

Antes do merge:

1. `monitor compare` em dois AUDs reais comparáveis;
2. conferência de `MON-*/report.html`;
3. `monitor gate`, incluindo caso deliberado `NEW` ruim quando disponível;
4. `quality.html`, Fix Verification e Timeline;
5. `observe report` sem dataset externo;
6. com OAuth válido, `gsc-sites`, `gsc-sitemaps`, `gsc-search`, `gsc-appearance`, `gsc-inspect`;
7. CrUX History em URL/origin do AUD;
8. Bing/Google GenAI imports quando houver exports;
9. navegação de todas as páginas materializadas;
10. `SCORE-GEO-003` vigente e `002` somente histórico;
11. SHA-256 de `audit.db` inalterado antes/depois das operações derivadas;
12. ausência de secrets em `observability.db`, artifacts e HTML.
