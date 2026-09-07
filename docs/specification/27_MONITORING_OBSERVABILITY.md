# RASAI Monitor & Search/AI Observability

**Status:** APPROVED CANDIDATE — implemented in PR #82; automated gates green; human smoke required before merge.
**Natureza:** capacidades derivadas/complementares, read-only sobre a evidência de auditoria e non-scoring por padrão.

## 1. Objetivo

Adicionar ao RASAI observabilidade longitudinal e outcomes externos sem transformar sinais heterogêneos em um score transversal nem alterar silenciosamente `SARI-001`/`SCORE-GEO-003`.

A capacidade deve responder separadamente:

1. o que mudou entre duas auditorias persistidas;
2. se a mudança é regressão, melhoria, alteração neutra ou não comparável;
3. se um release deve ser bloqueado por regressões determinísticas configuradas;
4. quais outcomes externos Search/AI foram observados;
5. se há coocorrência temporal entre mudança técnica e outcome observado, sem afirmar causalidade.

## 2. Fronteira metodológica

- `SARI-001` permanece o índice público de readiness;
- `SCORE-GEO-003` permanece o scoring vigente para novas auditorias;
- `SCORE-GEO-002` permanece histórico;
- Monitoring não cria novo score;
- Search/AI Observability não entra automaticamente no SARI;
- Search Performance, URL Inspection, CrUX History, Bing/AI outcomes e diagnósticos derivados permanecem explicitamente identificados por fonte/método;
- correlação/coocorrência não pode ser descrita como causalidade.

## 3. Persistência

### 3.1 Audit fonte

Monitoring abre `AUD-*/audit.db` em modo somente leitura. Nenhuma operação `compare`, `gate` ou `impact` pode modificar schema, rows ou artifacts do AUD fonte.

### 3.2 Sidecar observacional

Dados coletados/importados após o audit são persistidos em:

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

`observability.db` é sidecar separado. Ele não substitui `audit.db`, não migra o banco fonte e deve preservar proveniência/fingerprint dos artifacts externos.

Credenciais, bearer tokens e API keys não podem ser persistidos.

## 4. RASAI Monitor

### 4.1 Compare

Superfície:

```text
rasai monitor compare --baseline AUD-X --current AUD-Y
```

Classificações admitidas conforme o tipo de sinal:

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
- versões de scoring diferentes devem gerar limitação/quebra de comparabilidade;
- Mobile/Desktop permanecem separados;
- mudanças de URL universe/ruleset/auditor version devem ser expostas quando materialmente relevantes;
- alterações de estado sem direção conhecida devem ser `CHANGED`, não regressão inventada.

### 4.2 Release gate

Superfície:

```text
rasai monitor gate ...
```

Default: deterministic-only.

Códigos de saída:

```text
0 PASS
1 BLOCKED_BY_REGRESSION
2 EXECUTION_ERROR
```

Regras semânticas/LLM somente participam quando o usuário habilita explicitamente essa política. Thresholds configuráveis não alteram scoring; apenas definem política de release.

### 4.3 Change Impact

Superfície:

```text
rasai monitor impact ...
```

Pode comparar mudanças técnicas com:

- Search Performance;
- estado/canonical observado via URL Inspection;
- CrUX History;
- outros outcomes observacionais suportados.

A saída deve usar formulação de associação temporal/coocorrência e declarar `causality_not_established`/equivalente. Nunca afirmar “X causou Y” apenas porque os sinais mudaram no mesmo período.

## 5. Search Console

### 5.1 Search Analytics

Coleta via API oficial. Registros podem incluir, conforme resposta/dimensões solicitadas:

- date;
- query;
- page/URL;
- device;
- country;
- search type/surface;
- clicks;
- impressions;
- CTR;
- average position.

Paginação deve ser bounded e `max_rows` configurável.

### 5.2 URL Inspection

Coleta via API oficial para URLs do audit, bounded por `max_urls`.

Campos observáveis podem incluir:

- verdict/coverage/indexing state;
- robots state;
- fetch state;
- last crawl;
- crawled-as;
- user-declared canonical;
- Google-selected canonical;
- referring/sitemap URLs quando retornados.

URL Inspection representa estado conhecido pelo índice e não deve ser apresentada como live test.

## 6. CrUX History

A coleta histórica usa o contrato oficial CrUX History quando habilitada.

LCP, INP e CLS permanecem field/RUM aggregate evidence e não devem ser fundidos com:

- Lighthouse lab;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- SARI.

Ausência de dados CrUX é indisponibilidade/suficiência de campo, não finding do website.

## 7. Bing e AI outcomes

Quando não existe endpoint direto documentado/implementado para a superfície desejada, o RASAI opera `import-first` sobre export normalizado. Não fazer scraping do portal nem inventar API.

A importação deve preservar source/capture method, período e artifact SHA-256.

## 8. Indexability Reality Matrix

A projeção pode cruzar:

- HTTP/local final URL;
- meta robots;
- canonical declarado;
- sitemap/links quando disponíveis;
- external indexing verdict;
- external selected canonical.

Divergência de canonical é um fato observado. Não se torna automaticamente finding causal de tráfego.

## 9. Query × Intent Alignment

Queries observadas podem ser comparadas com intents já persistidas pelas regras RASAI. O matching deve ser explicável e conservador.

Estados atuais:

```text
ALIGNED
PARTIAL
UNMATCHED
INTENT_NOT_AVAILABLE
```

Essa saída não é ranking factor, keyword score ou contribuição de SARI.

## 10. Potential Search Cannibalization

Pode ser emitido candidato quando pelo menos duas URLs dividirem materialmente a mesma query/fonte segundo threshold versionado/documentado. Na implementação inicial, cada URL material deve representar pelo menos 20% das impressões observadas da query/fonte.

O diagnóstico deve permanecer `POTENTIAL_*`: múltiplas URLs para a mesma query não provam dano.

## 11. Diagnósticos complementares

Observability pode materializar diagnósticos advisory sem criar BR-GEO adicional:

- Structured Data documentation completeness para tipos suportados;
- entity consistency;
- freshness/date conflicts;
- hreflang syntax/absolute URL/self-reference/reciprocity quando verificável;
- retrieval/chunkability observations;
- table header relationships;
- template/root-cause clustering.

Regras:

- não inventar Rich Results API/score;
- não marcar `Organization` como inválido por ausência de propriedade que a documentação não define como obrigatória;
- reciprocity hreflang só pode ser concluída contra variantes efetivamente observadas no universo auditado;
- selector só sustenta causa compartilhada quando é confiável; agrupamento por título sem selector é apenas cluster de ocorrências.

## 12. Calibration Dataset Manager

Superfície:

```text
rasai scoring dataset --dataset-version VERSION
```

Objetivo: avaliar suficiência **pré-fit** e produzir manifest/fingerprint determinístico.

Gates mínimos são herdados do contrato SCORE-GEO-003 vigente, incluindo domínio, holdout possível, engines, queries, repetições, dias e observações.

`READY_FOR_MODEL_FIT` não equivale a `VALIDATED`. AUC/Brier e demais gates pós-fit continuam necessários.

## 13. Reporting

### Per-audit

```text
report/observability.html
```

Deve conter:

- proveniência/datasets;
- matriz de indexabilidade;
- diagnósticos complementares;
- Query × Intent;
- candidates de cannibalization;
- clusters;
- CrUX History;
- referências públicas;
- declaração clara de non-scoring/non-causality.

### Monitoring

```text
monitoring/MON-*/report.html
monitoring/MON-*/manifest.json
monitoring/MON-*/impact.html   # quando solicitado
```

## 14. Navegação HTML

O registry final deve ser canônico e condicionado à existência dos arquivos. Uma página opcional gerada depois não pode remover do menu outra página opcional já materializada.

A página corrente deve ser o único item ativo.

## 15. Failure isolation

- falha de collector externo não invalida auditoria principal;
- ausência de credencial só bloqueia o comando que dela depende;
- `observe report` deve funcionar sem dataset externo e produzir empty state coerente;
- Monitoring deve continuar read-only;
- erros devem produzir exit/status operacional distinto de finding do website.

## 16. Segurança

- sanitizar URLs/inputs externos;
- preservar scoping do audit;
- não persistir secrets;
- limitar quotas (`max_rows`, `max_urls`, períodos);
- artifacts externos são untrusted input;
- sidecar e relatórios derivados não podem modificar evidence/rules/scores do AUD.

## 17. Critérios de aceite automatizados

- compile dos novos módulos;
- testes read-only e comparabilidade;
- gate determinístico;
- import sidecar/idempotência;
- collectors com HTTP mockado;
- diagnostics evidence-bound;
- dataset pre-fit;
- regressão SCORE-GEO-003;
- regressão M25/M26;
- navegação canônica de páginas opcionais.

## 18. Critérios de smoke humano

Antes do merge:

1. executar `monitor compare` sobre dois AUDs reais comparáveis;
2. abrir `report.html` e verificar classificação/URLs/devices;
3. executar `monitor gate` e confirmar exit esperado;
4. executar `observe report` sem dataset externo;
5. quando houver credencial, validar Search Analytics e URL Inspection reais;
6. quando elegível, validar CrUX History real;
7. validar import Bing/AI export quando houver dataset;
8. abrir `observability.html` e todas as páginas materializadas, verificando menu/order/active state;
9. confirmar `SCORE-GEO-003` como vigente e `002` somente histórico;
10. confirmar hash de `audit.db` inalterado antes/depois de monitor/observe.
