# Monitoramento de Search Intelligence

**Estado:** contrato de monitoramento do control plane implementado, com SQLite como backend local/padrão e PostgreSQL por configuração explícita.

Contrato atual:

```text
SEARCH-MONITOR-001
```

Search Intelligence Monitoring transforma uma query de Search fornecida manualmente em um contexto de observação registrado e repetível. É uma capacidade operacional e longitudinal; não cria novo score de readiness e não altera `SARI-001` nem `SCORE-GEO-004`.

## Objetivo

Uma query registrada preserva o contexto necessário à observação repetível:

- Project, Property e Environment;
- texto da query;
- domínio de interesse;
- mecanismo de busca;
- país/mercado;
- região opcional;
- idioma;
- dispositivo;
- profundidade solicitada;
- provider de Search e modo de aquisição;
- controles da análise competitiva determinística;
- comparação opcional e limitada de conteúdo público;
- controles opcionais de Competitive AI vinculada a evidências;
- estado habilitado/desabilitado;
- agendamento recorrente opcional.

O contexto registrado é a unidade da comparação longitudinal. O RASAi não compara silenciosamente execuções que tenham mudado de provider ou de modo de dados.

## Autoridade dos dados e evidência imutável da auditoria

O monitoramento recorrente de Search não deve anexar observações a bancos históricos de auditoria.

No modo local/padrão, a divisão de autoridade é:

```text
AUD-*/audit.db
  evidência imutável da auditoria em um ponto no tempo

.rasai/platform.db
  metadados de produto/control plane em SQLite
  queries de Search registradas
  resumos longitudinais de execuções Search
  agendamentos

.rasai/search-monitoring/
  evidência bruta do provider de Search
  manifests de execução e metadados de integridade SHA-256
```

Quando PostgreSQL é selecionado explicitamente, a parte relacional passa a ser:

```text
PostgreSQL control plane
  estado relacional da Product Platform
  queries de Search registradas
  resumos longitudinais de execuções Search
  agendamentos

.rasai/search-monitoring/ ou object storage futuro
  evidência bruta do provider de Search
  manifests de execução e metadados de integridade SHA-256
```

PostgreSQL não altera o contrato de evidência imutável de `AUD-*/audit.db`.

## Persistência do control plane

As tabelas relacionais de monitoramento Search são:

```text
search_monitor_queries
search_monitor_runs
```

`search_monitor_queries` referencia a hierarquia já existente da Product Platform e o modelo de agendamento. Não cria uma hierarquia independente de Project/Domain.

`search_monitor_runs` armazena resumos longitudinais, incluindo:

- IDs da execução e da observação;
- timestamps de coleta;
- provider de Search e modo de dados;
- status do domínio e posição observada do cliente;
- quantidade de resultados;
- domínios observados à frente do cliente;
- referência da evidência bruta e SHA-256;
- estado da comparação determinística e códigos de gaps;
- sinais de cobertura do conteúdo do cliente, quando observados;
- contagem de palavras observada e tipos JSON-LD;
- estado/provider/modelo de Competitive AI e quantidade de oportunidades, quando habilitada;
- eventos de mudança em relação à execução anterior comparável;
- contadores de requests SERP/conteúdo/IA;
- referência do manifest da execução e SHA-256;
- estado de erro, quando aplicável.

O runtime opera por meio do contrato `SearchMonitoringRepository`. SQLite é o adapter local padrão e PostgreSQL implementa o mesmo comportamento de domínio para o control plane centralizado. A seleção do backend ocorre na composição, e não por verificações do engine do banco espalhadas pela lógica de monitoramento.

## Seleção do backend

A operação local padrão permanece em SQLite. PostgreSQL exige ativação explícita:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

Antes de iniciar Search Monitoring com PostgreSQL, o schema versionado deve estar atualizado. Comandos de Search Monitoring nunca disparam mudanças de schema. Use:

```powershell
rasai platform database status
rasai platform database migrate
```

Não existe fallback silencioso de PostgreSQL para SQLite.

## Evidência bruta

A evidência bruta do provider de Search é gravada em:

```text
audits/.rasai/search-monitoring/artifacts/serp/
```

Os manifests das execuções são gravados em:

```text
audits/.rasai/search-monitoring/runs/
```

Os payloads de evidência usam o sanitizador de evidência Search já existente. Credenciais do provider não são persistidas nas tabelas do control plane, manifests ou relatórios.

Em SaaS hospedado, a expectativa arquitetural é mover evidências/manifests imutáveis para object storage, mantendo no PostgreSQL a propriedade relacional, as referências e os hashes.

## CLI do registro de queries

A hierarquia da Product Platform deve existir antes do registro de uma query. Use `rasai platform` para indexar/criar Project, Property e Environment relevantes e obter seus IDs estáveis.

Registrar uma query manual:

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

Listar queries registradas:

```powershell
rasai search-monitor --audits-root audits query list
```

Habilitar ou desabilitar uma query:

```powershell
rasai search-monitor --audits-root audits query enable --query-id <query-id>
rasai search-monitor --audits-root audits query disable --query-id <query-id>
```

Desabilitar uma query registrada também desabilita seu agendamento local vinculado, quando existente.

## Execução manual

Executar uma query registrada:

```powershell
rasai search-monitor --audits-root audits run --query-id <query-id>
```

Estimar limites máximos de requests sem chamar providers:

```powershell
rasai search-monitor --audits-root audits run --query-id <query-id> --dry-run
```

O `dry-run` separa:

- teto de requests HTTP ao provider de Search;
- teto de tentativas HTTP diretas a conteúdo público;
- teto de chamadas ao provider de Competitive AI.

Execução por fixture é suportada para testes e validação local sem chamadas de rede ao provider:

```powershell
rasai search-monitor --audits-root audits run `
  --query-id <query-id> `
  --fixture test-serp.json
```

O modo fixture é manual e não pode ser associado a um agendamento live recorrente.

## Agendamentos recorrentes

O monitoramento reutiliza o scheduler da Product Platform. Não introduz um segundo scheduler nem executa strings arbitrárias de shell.

Exemplo por intervalo:

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

Exemplo diário:

```powershell
rasai search-monitor --audits-root audits query add `
  --project <project-id> `
  --property <property-id> `
  --environment <environment-id> `
  --query "seguro residencial" `
  --domain cliente.example `
  --mode live `
  --provider serpapi `
  --daily-time 07:00
```

O intervalo mínimo aceito por esta superfície de Search Monitoring é **60 minutos**, conforme validação do runtime. Esse é um limite de segurança do produto, não recomendação para consultar a cada hora. A cadência em produção deve considerar termos do provider, quota, custo, volatilidade do mercado e valor de negócio da query.

Executar somente agendamentos de Search Monitoring vencidos:

```powershell
rasai search-monitor --audits-root audits run-due
```

O scheduler atual ainda é um mecanismo de execução em uma única máquina. Persistir agendamentos em PostgreSQL, isoladamente, não torna o dispatch horizontalmente seguro; semântica de fila durável/claim pertence ao execution plane hospedado.

## Conteúdo competitivo e Competitive AI

Uma query registrada pode habilitar análise competitiva determinística e inspeção limitada de conteúdo.

Aquisição de conteúdo é explícita:

```text
--compare-content
--max-content-pages N
```

Competitive AI também é explícita e ocorre downstream de evidência determinística de conteúdo consolidada:

```text
--ai-competitive
--ai-provider openai
--ai-model <model-id>
--ymyl-mode AUTO|ON|OFF
```

Credenciais BYOK continuam sendo entradas de ambiente/runtime. Elas não são copiadas para agendamentos nem para o banco de monitoramento.

## Detecção de mudanças

Uma execução bem-sucedida é comparada apenas com a execução anterior do mesmo contexto de query registrada.

Estados de mudança atuais incluem:

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

`NOT_FOUND_WITHIN_DEPTH` nunca é convertido em posição zero, posição infinita ou rank absoluto fabricado.

Mudança de provider ou de modo de dados torna execuções adjacentes não comparáveis para deltas numéricos de ranking. O RASAi preserva a diferença de proveniência, em vez de normalizá-la silenciosamente.

## Limite de causalidade

Mudança cronológica é observação, não prova de causalidade de ranking.

Interpretação válida:

```text
A query registrada passou da posição observada 8 para a posição 4 entre duas execuções comparáveis.
Um gap determinístico de conteúdo observado na execução anterior não estava presente na execução atual.
```

Interpretação inválida:

```text
A alteração de conteúdo causou a melhora de quatro posições.
```

A evidência disponível não estabelece o mecanismo causal privado do mecanismo de busca.

## HTML longitudinal

O relatório longitudinal do control plane é:

```text
audits/platform-report/search-intelligence.html
```

Ele exibe linhas do tempo das queries registradas, posição/status mais recente, provider/modo de dados, domínios à frente, gaps determinísticos, estado de Competitive AI e mudanças materializadas na execução mais recente.

Ele é deliberadamente separado do relatório pontual da auditoria:

```text
audits/AUD-*/report/search-intelligence.html
```

O relatório da auditoria projeta evidência imutável pertencente a um workspace específico. O relatório da plataforma projeta observações operacionais recorrentes do backend de control plane selecionado. O relatório longitudinal não deve reescrever HTML histórico de auditoria nem `audit.db`.

## Relação com histórico de deploy

`SEARCH-HISTORY-001` permanece o contrato para comparar evidência Search entre workspaces de auditoria explícitos ou pares de auditorias selecionados ao redor de um milestone de deploy.

`SEARCH-MONITOR-001` tem outro propósito: observações contínuas de uma query registrada, independentemente de uma nova auditoria completa ter sido executada.

As duas superfícies podem ser correlacionadas temporalmente em dashboard futuro, mas nenhuma pode converter proximidade temporal com deploy em afirmação de causalidade de ranking.

## Limite PostgreSQL

A separação de armazenamento do monitoramento é concreta:

```text
domínio/runtime de Search Monitoring
        |
SearchMonitoringRepository
        |
        +-- adapter SQLite: local/padrão
        +-- adapter PostgreSQL: control plane centralizado
```

O adapter PostgreSQL usa a mesma autoridade de Project/Property/Environment e agendamento que o restante da Product Platform. Ele não substitui nem modifica evidência imutável de auditoria.

Detalhes de runtime estão em `POSTGRESQL_CONTROL_PLANE.md`; a estratégia de deployment permanece em `POSTGRESQL_MIGRATION_STRATEGY.md`.

## Política de testes e CI

Testes automatizados não devem consumir credenciais Search/IA de clientes nem fazer crawl de sites públicos de concorrentes.

Execução Search baseada em fixture continua obrigatória nos testes de paridade do repositório. Testes de persistência específicos de PostgreSQL executam contra serviço real PostgreSQL 18 em container.

Propriedades obrigatórias de regressão incluem:

- integridade do escopo Project/Property/Environment;
- rejeição de contexto de query duplicado;
- semântica exata de mudança de ranking;
- semântica do limite de profundidade observada;
- proteção de comparabilidade entre provider/modo de dados;
- persistência do control plane nos dois backends suportados;
- integridade da evidência bruta e do manifest da execução;
- ausência de gravação recorrente em `AUD-*/audit.db` históricos;
- geração de relatório;
- preservação dos contratos `SARI-001` e `SCORE-GEO-004`.
