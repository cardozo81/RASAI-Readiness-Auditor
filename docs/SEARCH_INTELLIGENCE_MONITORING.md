# Monitoramento de Search Intelligence

**Estado:** contrato de monitoramento do control plane implementado, com SQLite como backend local/padrão e PostgreSQL por configuração explícita.

Contrato: `SEARCH-MONITOR-001`.

Search Intelligence Monitoring transforma uma query fornecida manualmente em um contexto de observação registrado e repetível. É uma capacidade operacional e longitudinal; não cria novo score de readiness e não altera `SARI-001` nem `SCORE-GEO-004`.

## Objetivo

Uma query registrada preserva Project/Property/Environment, query, domínio de interesse, engine, mercado, região, idioma, dispositivo, profundidade, provider Search/modo de aquisição, controles competitivos, conteúdo público opcional, Competitive AI opcional, estado e agendamento.

O contexto registrado é a unidade da comparação longitudinal. O RASAi não compara silenciosamente execuções com proveniência Search incompatível.

## Autoridade dos dados

```text
AUD-*/audit.db
  evidência imutável de auditoria

.rasai/platform.db ou PostgreSQL
  control plane
  queries registradas
  resumos longitudinais
  agendamentos

.rasai/search-monitoring/
  evidência bruta Search
  manifests e SHA-256
```

PostgreSQL não altera o contrato de evidência imutável de `AUD-*/audit.db`.

## Persistência

Tabelas relacionais:

```text
search_monitor_queries
search_monitor_runs
```

`search_monitor_queries` referencia a hierarquia existente da Product Platform. `search_monitor_runs` persiste resumo da observação, posição/status, proveniência Search, gaps determinísticos, sinais de conteúdo, estado/provider/modelo efetivos da Competitive AI, contadores de requests, mudanças, manifest e erros.

O runtime opera por `SearchMonitoringRepository`; SQLite e PostgreSQL implementam o mesmo contrato de domínio.

## Backend

Default local: SQLite.

PostgreSQL exige configuração explícita:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

Antes de executar com PostgreSQL:

```powershell
rasai platform database status
rasai platform database migrate
```

Não existe fallback silencioso de PostgreSQL para SQLite.

## Evidência bruta

Evidência Search:

```text
audits/.rasai/search-monitoring/artifacts/serp/
```

Manifests:

```text
audits/.rasai/search-monitoring/runs/
```

Credenciais não são persistidas nas tabelas, manifests ou relatórios.

## Registro e execução

Registrar:

```powershell
rasai search-monitor --audits-root audits query add `
  --project <project-id> `
  --property <property-id> `
  --environment <environment-id> `
  --query "seguro auto" `
  --domain cliente.example `
  --country BR `
  --language pt-BR `
  --device desktop `
  --depth 20
```

Listar:

```powershell
rasai search-monitor --audits-root audits query list
```

Executar:

```powershell
rasai search-monitor --audits-root audits run --query-id <query-id>
```

Dry-run:

```powershell
rasai search-monitor --audits-root audits run --query-id <query-id> --dry-run
```

O dry-run separa teto SERP, tentativas de conteúdo e chamadas de IA.

Fixtures continuam disponíveis apenas para testes/validação manual sem rede.

## Agendamento

O monitoramento reutiliza o scheduler da Product Platform. O intervalo mínimo da superfície é 60 minutos; a cadência real deve considerar quota, custo, termos do provider, volatilidade e valor de negócio.

Exemplo:

```powershell
rasai search-monitor --audits-root audits query add `
  --project <project-id> `
  --property <property-id> `
  --environment <environment-id> `
  --query "seguro auto" `
  --domain cliente.example `
  --mode live `
  --provider serpapi `
  --interval-minutes 1440
```

Executar vencidos:

```powershell
rasai search-monitor --audits-root audits run-due
```

Fixture não é aceita em agendamento live recorrente.

## Conteúdo competitivo e Competitive AI

Aquisição de conteúdo é explícita:

```text
--compare-content
--max-content-pages N
```

Competitive AI também é explícita e somente ocorre downstream de evidência determinística consolidada:

```text
--ai-competitive
--ai-provider <provider-canônico|auto>
--ai-model <model-id>       # somente provider explícito
--ymyl-mode AUTO|ON|OFF
```

O campo `ai_provider` da query registrada representa a seleção canônica solicitada para futuras execuções: `none`, provider do registry ou `auto`. Ele não cria um cadastro paralelo de IA.

Quando `ai_provider=auto`, cada execução reutiliza a política central do RASAi para a necessidade `COMPETITIVE_INTELLIGENCE`: elegibilidade, custo estimado, ordenação, quarentena, circuit breaker e fallback. Modelo único não pode sobrescrever `AUTO`; cada provider usa sua configuração principal.

`fixture` é aceito somente para teste/manual e não é provider de produção.

Credenciais BYOK permanecem no ambiente/secret boundary e não são copiadas para agendamentos nem banco de monitoramento.

## Mudanças longitudinais

Estados incluem:

- `POSITION_IMPROVED`;
- `POSITION_REGRESSED`;
- `POSITION_UNCHANGED`;
- `ENTERED_OBSERVED_DEPTH`;
- `LEFT_OBSERVED_DEPTH`;
- `DOMAIN_STATUS_CHANGED`;
- `COMPETITOR_AHEAD_ADDED`;
- `COMPETITOR_AHEAD_REMOVED`;
- `CONTENT_SIGNAL_CHANGED`;
- `CONTENT_VOLUME_CHANGED`;
- `STRUCTURED_DATA_CHANGED`;
- `DETERMINISTIC_GAP_ADDED`;
- `DETERMINISTIC_GAP_RESOLVED`;
- `NOT_COMPARABLE`.

`NOT_FOUND_WITHIN_DEPTH` nunca vira posição zero/infinita ou rank fabricado.

Mudança de provider Search ou modo de dados torna execuções adjacentes não comparáveis para deltas numéricos de ranking.

## Limite causal

Mudança cronológica é observação, não prova causal.

Válido:

```text
A query passou da posição observada 8 para 4 entre execuções comparáveis.
Um gap determinístico anterior não estava presente na execução atual.
```

Inválido:

```text
A alteração de conteúdo causou a melhora de quatro posições.
```

## HTML longitudinal

Relatório do control plane:

```text
audits/platform-report-catalog/cat-05.html
```

Relatório pontual da auditoria:

```text
audits/AUD-*/report-catalog/cat-05.html
```

O longitudinal não reescreve HTML histórico nem `audit.db`.

## Relação com histórico de deploy

`SEARCH-HISTORY-001` compara evidência Search entre workspaces/pontos de auditoria. `SEARCH-MONITOR-001` observa continuamente uma query registrada. As duas superfícies podem ser correlacionadas temporalmente, mas não convertem proximidade com deploy em causalidade de ranking.

## PostgreSQL

```text
Search Monitoring
        |
SearchMonitoringRepository
        |
        +-- SQLite: local/padrão
        +-- PostgreSQL: control plane centralizado
```

Detalhes: `POSTGRESQL_CONTROL_PLANE.md` e `POSTGRESQL_MIGRATION_STRATEGY.md`.

## Testes e CI

Testes automatizados não devem consumir credenciais reais, chamar Search/IA live ou fazer crawl público de concorrentes.

Cobertura obrigatória inclui escopo Project/Property/Environment, duplicidade, mudanças de ranking, profundidade, comparabilidade, ambos os backends, integridade de evidência/manifest, ausência de escrita recorrente em `AUD-*/audit.db`, seleção canônica de IA, `AUTO` e preservação de `SARI-001`/`SCORE-GEO-004`.
