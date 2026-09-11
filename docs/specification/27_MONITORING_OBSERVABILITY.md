# RASAi Monitor & Search/AI Observability

**Estado no baseline de desenvolvimento:** aprovado / implementado / integrado à `main`  
**Natureza:** capacidades derivadas, somente leitura sobre a evidência de origem e, por default, fora do scoring.

## 1. Objetivo

Adicionar observabilidade longitudinal e outcomes externos sem transformar sinais heterogêneos em um score transversal nem alterar silenciosamente `SARI-001`/`SCORE-GEO-004`.

A capacidade responde separadamente:

1. o que mudou entre duas auditorias persistidas;
2. se a mudança é regressão, melhoria, alteração neutra, sinal novo ou não comparável;
3. se um release deve ser bloqueado por deterioração determinística ou por um par metodologicamente não comparável;
4. quais outcomes externos de Search/IA foram observados;
5. se há coocorrência temporal entre mudança técnica e outcome observado, sem afirmar causalidade.

## 2. Fronteira metodológica

- `SARI-001` é o índice público de readiness;
- `SCORE-GEO-004` é o scoring vigente para novas auditorias;
- Monitoring não cria novo score;
- Observability não entra automaticamente no SARI;
- Search Performance, URL Inspection, CrUX History, outcomes Bing/IA e diagnósticos derivados permanecem identificados por fonte/método;
- correlação/coocorrência não pode ser descrita como causalidade;
- dado ausente não é zero, `PASS` nem `FAIL`;
- mudança sem direção documental segura permanece `CHANGED`.

## 3. Persistência

Monitoring abre `AUD-*/audit.db` em SQLite somente leitura. Nenhuma operação derivada pode modificar a evidência de origem.

Dados externos pós-auditoria são persistidos em:

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

Contrato atual: `RASAI-OBS-002`.

Observações usam identidade `(dataset_id, record_id)`. Sidecars históricos são migrados preservando linhas/proveniência; `audit.db` não é migrado. Artefatos preservam SHA-256 e credenciais não são persistidas.

## 4. RASAi Monitor

### Comparação

```text
rasai monitor compare --baseline AUD-X --current AUD-Y
```

Classificações incluem `REGRESSED`, `IMPROVED`, `CHANGED`, `NEW`, `RESOLVED`, `UNCHANGED`, `DATA_UNAVAILABLE` e `NOT_COMPARABLE`.

Regras:

- `UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não viram `FAIL` arbitrariamente;
- score com `scoring_version` incompatível é não comparável para aquele sinal;
- Mobile/Desktop permanecem separados;
- diferenças de universo, conjunto de devices e ruleset são expostas;
- ausência do sinal atual é `DATA_UNAVAILABLE`, não resolução automática.

### Release Gate

```text
rasai monitor gate ...
```

Default: *fail-closed* e somente determinístico.

```text
0 PASS
1 BLOCKED_BY_DETERIORATION_OR_INCOMPARABILITY
2 EXECUTION_ERROR
```

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

Esses parâmetros alteram a política operacional do gate, não SARI/SCORE-GEO.

### Change Impact

```text
rasai monitor impact ...
```

- seleciona um dataset mais recente por fonte/`AUD-*`;
- históricos sobrepostos não são somados;
- associação temporal exige janelas comparáveis;
- `NULL` permanece indisponível;
- temporalidade não estabelece causalidade;
- fontes cuja direção não é segura permanecem `CHANGED`.

## 5. Search Console / CrUX / importações

Superfícies observacionais implementadas incluem, conforme credencial e fonte disponível:

```text
rasai observe gsc-sites
rasai observe gsc-sitemaps
rasai observe gsc-search
rasai observe gsc-appearance
rasai observe gsc-inspect
rasai observe crux-history
rasai observe import
rasai observe bing-import
rasai observe google-ai-import
rasai observe google-ai-control
```

Regras comuns:

- coleta limitada ao escopo auditado;
- segredos somente em runtime;
- fonte/método de captura/período/SHA do artefato explícitos;
- erro sistêmico de autenticação/quota/rede é operacional, não finding do website;
- dados inexistentes na fonte não são inventados;
- Search/Discover e superfícies distintas mantêm proveniência separada.

## 6. Diagnósticos observacionais

Podem ser materializados sem contribuição automática ao SARI:

- Indexability Reality Matrix;
- Query × Intent Alignment;
- Potential Search Cannibalization;
- verificações de documentação de Structured Data;
- consistência de entidades;
- atualização baseada em datas persistidas;
- `hreflang`, quando verificável;
- retrieval/chunkability;
- agrupamento por template/causa raiz;
- CrUX History;
- proveniência do dataset.

Divergência observada não é automaticamente fator de ranking nem causalidade.

## 7. Quality & Verification

Contrato detalhado: `28_AUDIT_QUALITY_VERIFICATION.md`.

`report/quality.html`, Fix Verification e Evidence Timeline ficam fora do scoring e operam somente leitura. Estados resolvidos/fechados permanecem no histórico sem entrar na fila operacional ativa.

## 8. Relação com scoring

A superfície atual de scoring é:

```text
rasai scoring inspect
```

Ela inspeciona o contrato `SCORE-GEO-004` e não executa fitting.

## 9. Relatórios

Por `AUD-*`:

```text
report/scoring.html
report/observability.html
report/quality.html
```

Independentes:

```text
monitoring/MON-*/report.html
monitoring/MON-*/manifest.json
monitoring/MON-*/impact.html
verification/VER-*/report.html
quality/TIMELINE-*/report.html
```

## 10. Segurança e isolamento de falhas

- collector externo não invalida auditoria principal;
- ausência de credencial bloqueia apenas a operação dependente;
- `observe report` funciona sem dataset externo;
- Monitoring permanece somente leitura;
- dados fora da origem auditada são rejeitados/excluídos;
- segredos não são persistidos;
- quotas/períodos são limitados;
- artefatos externos são entrada não confiável;
- sidecars/relatórios derivados não modificam evidências/regras/scores do `AUD-*`.

## 11. Gates automatizados

CI deve cobrir:

- compilação/importação dos módulos;
- leitura somente leitura e comparabilidade;
- gate determinístico/*fail-closed*;
- migration/identidade `OBS-002`;
- escopo dos collectors;
- ausência de segredos em artefatos;
- preservação de `NULL`;
- Quality/Fix Verification/Timeline;
- navegação canônica;
- preservação de `scoring_version`;
- `scoring.html` como página canônica da metodologia.
