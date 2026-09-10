# Estratégia de migração para PostgreSQL

**Estado:** backend PostgreSQL 18 do control plane implementado como opção explícita. SQLite permanece o backend local padrão.

O contrato de scoring é `SCORE-GEO-004`. Esta estratégia altera apenas a arquitetura de persistência do produto; não redefine scoring, `SARI-001`, evidência de auditoria nem metodologia de relatório.

## Decisão

O limite PostgreSQL é o **control plane do produto**.

Ele inclui estado de produto e longitudinal, como:

- Organization / Workspace / Project;
- Property / Environment;
- users, memberships e roles;
- vínculos de identidade externa `(issuer, subject) -> USR-*`;
- catálogo de auditorias e vínculos de escopo;
- milestones e metadados de deployment;
- golden baselines;
- page identities;
- schedules e alert rules;
- metadados de integrações;
- catálogo de datasets externos;
- usage ledger e consumption analytics;
- queries registradas de Search Monitoring;
- resumos das execuções de Search Monitoring;
- execution jobs duráveis.

Estado mutável de produto não é gravado em `AUD-*/audit.db`, e PostgreSQL não é um formato alternativo de evidência de auditoria.

## Modelo de desenvolvimento e deployment

O alvo local de desenvolvimento PostgreSQL é PostgreSQL 18 em Docker. A aplicação é independente da localização do banco e conecta pelo contrato de configuração do control plane; o deployment hospedado usa o mesmo limite de repository/domínio contra endpoint PostgreSQL gerenciado.

Conteúdo SQLite de desenvolvimento não é tratado como autoridade de produção. Portanto, um banco PostgreSQL limpo pode ser inicializado assim:

```text
banco PostgreSQL vazio
        |
migrations versionadas explícitas
        |
dados de control plane criados pela aplicação
        |
validação de paridade / regressão
```

Uma ferramenta de importação SQLite → PostgreSQL só é necessária quando uma instalação contém dados autoritativos que precisam ser promovidos para PostgreSQL.

## Modelo de autoridade

Modelo hospedado de autoridade:

```text
PostgreSQL
  estado relacional autoritativo do produto/control plane
  users, memberships e vínculos de identidade externa

Object Storage
  bundles AUD imutáveis
  arquivos audit.db
  artefatos de evidência
  relatórios gerados
  evidência/manifests brutos de Search Monitoring

Queue / Scheduler
  dispatch da execução e estado de retry

Workers
  execuções stateless ou de vida curta de audit/integration/Search
```

`AUD-*/audit.db` permanece um formato autocontido de evidência da execução. Em operação hospedada, pode ser armazenado como objeto imutável, em vez de se tornar o banco transacional central.

Essa separação evita que o banco SaaS se torne uma segunda interpretação da evidência de auditoria.

## Arquitetura de adapters

A seleção do banco ocorre no limite de composição do control plane, não dentro da lógica de negócio.

```text
serviços Product/API
        |
contratos de store/repository do control plane
        |
        +-- SQLite
        |     local/padrão
        |
        +-- PostgreSQL
              alvo centralizado/hospedado explícito
```

Configuração do backend:

| Variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite` | `sqlite`, `postgresql`; aliases de runtime `postgres`, `pg` | usar os valores canônicos `sqlite` ou `postgresql` |
| `RASAI_PLATFORM_DATABASE_URL` | sem default | DSN PostgreSQL válida; necessária quando backend=`postgresql` | manter como segredo; usar conexão TLS no ambiente hospedado |

SQLite:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

PostgreSQL:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://...
```

Quando o backend não é configurado, SQLite é o default. `--platform-db` é override exclusivo de SQLite.

Selecionar PostgreSQL sem URL do banco, ou ocorrer falha de conexão PostgreSQL, é erro. O runtime nunca faz fallback silencioso para SQLite, porque isso criaria autoridade dividida.

Search Query Registry, Search Monitoring, scheduling, execution jobs e vínculos de identidade externa usam o mesmo backend de control plane selecionado. Não existe autoridade paralela específica para identidade ou Search.

## Driver e limite do banco

A implementação PostgreSQL usa Psycopg 3 como dependência opcional.

O adapter expõe o comportamento DB-API consumido pelos métodos de repository/domínio da Product Platform, enquanto composição do banco e migrations permanecem específicas de backend.

Requisitos incluem:

- SQL parametrizado;
- transações explícitas de escrita;
- savepoints para escopos transacionais aninhados;
- timezone UTC da sessão;
- encoding UTF8 do servidor;
- identidade do banco com senha redigida;
- falhas de banco sanitizadas, expondo tipo diagnóstico/SQLSTATE sem expor credenciais nem SQL bruto.

Connection pooling pertence à camada de deployment do serviço/API hospedado. Operação local via CLI não exige pool de requests no processo inteiro.

## Migrations de schema

Mutação de schema PostgreSQL é explícita:

```powershell
rasai platform database status
rasai platform database migrate
```

O control plane usa trilhas de migration para responsabilidades separadas:

```text
platform_schema_migrations              core da Product Platform
platform_execution_schema_migrations    fila durável de execução
platform_identity_schema_migrations     vínculos de Identity & Access
```

Startup normal da aplicação não cria nem atualiza schema PostgreSQL. Se uma trilha obrigatória estiver atrás da versão suportada pelo runtime, a operação PostgreSQL falha de forma fechada e orienta o operador a executar migration. Schema mais novo do que a aplicação em execução também é rejeitado.

Cada migration é aplicada transacionalmente, e a execução é idempotente.

## Persistência de Identity & Access

Senhas/tokens/segredos OIDC não são persistidos em PostgreSQL.

A extensão relacional de identidade armazena somente o mapeamento durável necessário para conectar uma identidade autenticada externamente ao modelo de autorização:

```text
external_identity_id
user_id
issuer
subject
email                 opcional/informativo
created_at
```

`UNIQUE(issuer, subject)` impede que uma identidade externa resolva para múltiplos usuários.

A autorização deriva de `users` e `memberships`. Uma identidade OIDC válida sem vínculo/membership RASAi não recebe acesso a tenant.

Client secrets, session secrets, access tokens, ID tokens e refresh tokens permanecem fora dessas linhas.

## Representação atual do schema

A implementação PostgreSQL separa **seleção do engine de banco** de **mudanças na representação de domínio**.

Contratos atuais da aplicação usam:

- texto ISO-8601 canônico quando APIs expõem timestamps operacionais como strings;
- texto JSON canônico quando contratos de repository exigem payload estruturado serializado;
- inteiros `0/1` com constraint em colunas booleanas sensíveis à paridade;
- `TIMESTAMPTZ` para timestamps de auditoria das migrations.

Mudanças para representações nativas PostgreSQL, como uso mais amplo de `jsonb`, `boolean` e `timestamptz`, exigem migrations explícitas e testes de paridade semântica. Não são efeitos colaterais implícitos da seleção de PostgreSQL.

Payloads grandes e imutáveis de evidência permanecem fora do control plane relacional.

## Identificadores

IDs opacos e estáveis fazem parte do contrato entre backends.

Não regenere identificadores apenas porque outro engine de banco foi selecionado, incluindo:

- organization IDs;
- workspace IDs;
- project/property/environment IDs;
- user IDs;
- external identity IDs;
- audit IDs;
- milestone IDs;
- schedule IDs;
- IDs de queries registradas de Search;
- IDs de execuções de Search Monitoring;
- execution job IDs;
- outros IDs do control plane referenciados externamente.

Isso mantém estáveis relatórios, manifests, referências de ciclo de vida e chaves de object storage.

## Foreign keys e unicidade

A integridade de tenant/escopo é aplicada tanto pela validação da aplicação quanto por constraints PostgreSQL.

Relações críticas incluem:

- Workspace → Organization;
- Project → Workspace;
- Property → Project;
- Environment → Property;
- memberships → organization/user válidos e escopo opcional de workspace/project;
- identidades externas → user interno válido e issuer/subject único;
- vínculos de escopo da auditoria → audit indexado + Property/Environment;
- milestones/schedules → escopo Project/Property/Environment válido;
- query de Search Monitor → Project/Property/Environment válidos;
- execução Search Monitor → query registrada;
- execution jobs → escopo Organization/Project/Property/Environment válido.

Testes específicos de PostgreSQL executam contra um service container PostgreSQL 18 real, não contra camada SQL simulada.

## Isolamento de tenant e autenticação

O backend PostgreSQL fornece integridade relacional de escopo, mas não substitui autenticação/autorização.

A Web/API inclui resolução de identidade OIDC/JWT independente de provider:

```text
OIDC issuer + subject
        |
vínculo de identidade externa
        |
Principal USR-*
        |
membership / role
        |
acesso de repository/API limitado ao tenant
```

`trusted-header` está disponível para gateway confiável/cenários de desenvolvimento local. Validação OIDC e integridade do banco são controles complementares.

Defense in depth pode adicionar PostgreSQL Row Level Security depois que o comportamento de política possuir testes dedicados de paridade. RLS não deve substituir contexto autenticado de tenant explícito na aplicação.

## Deployment do scheduler

Persistir estado de schedule em PostgreSQL, isoladamente, não torna scheduling horizontalmente seguro.

Modelo hospedado:

```text
estado schedule/query no PostgreSQL
        |
serviço Scheduler
        |
fila durável
        |
workers regionais/padrão
        |
persistência de resultado + evidência em objeto
```

Scheduling distribuído exige:

- claim lógico único de uma ocorrência vencida;
- semântica de lease/lock;
- chaves de idempotência;
- retries limitados;
- estado de falha/dead-letter;
- estado de agendamento em UTC, usando timezone de usuário/projeto apenas para schedules que dependem do horário civil;
- limites de concorrência e rate limit por tenant/provider;
- contabilização de uso.

`FOR UPDATE SKIP LOCKED` é um mecanismo viável de claim dirigido pelo banco, mas o desenho de fila durável permanece uma decisão do execution plane e não é implícito à persistência PostgreSQL.

## Credenciais de Search, IA e identidade

Segredos BYOK de providers e segredos de identidade permanecem fora de linhas normais do banco.

Deployments hospedados devem usar secret manager ou serviço de credenciais criptografado, persistindo apenas referências/metadados necessários à autorização e rotação.

Segredos não devem aparecer em:

- linhas do Query Registry;
- schedules;
- manifests de execução;
- relatórios;
- registros de uso;
- linhas de identidade externa;
- saída de status do banco.

## Object storage

Object storage hospedado é o destino de payloads imutáveis de execução:

```text
bundles AUD
evidência bruta de providers
artefatos competitivos
artefatos de evidência de Competitive AI
manifests de Search Monitoring
sites estáticos de relatório
```

PostgreSQL armazena propriedade, referências, hashes, metadados de ciclo de vida e índices relacionais necessários para localizar esses objetos.

## Promoção de dados

Migration de schema e promoção de dados são operações distintas.

Migrations de **schema** PostgreSQL são obrigatórias para operar PostgreSQL. Importação de **dados** vindos de SQLite é necessária somente quando a origem SQLite contém estado autoritativo que precisa ser preservado.

Um processo controlado de promoção deve validar IDs, contagens de linhas, foreign keys, valores serializados, vínculos de identidade, escopo de tenant e hashes das auditorias antes do cutover de autoridade.

Padrão recomendado de cutover quando existe estado SQLite autoritativo:

```text
congelar gravações no control plane de origem
        |
inicializar / validar autoridade PostgreSQL
        |
importar dados autoritativos
        |
validar escopo, identidade e integridade
        |
trocar autoridade da aplicação
        |
manter origem somente leitura até encerrar janela de rollback
```

No estado atual de desenvolvimento pré-publicação, PostgreSQL pode iniciar limpo porque dados locais são de teste/piloto, e não autoridade de produção.

## Topologia de deployment hospedado

Topologia SaaS recomendada:

```text
HTTPS Load Balancer / Reverse Proxy
        |
instâncias RASAi Web/API
        |
        +-- OIDC Identity Provider
        +-- PostgreSQL gerenciado
        +-- fila gerenciada
        +-- object storage
        +-- secret manager
        |
pool de workers
        +-- audit workers
        +-- Search monitoring workers
        +-- integration workers
```

Requisitos operacionais para PostgreSQL hospedado incluem:

- acesso por rede privada quando suportado;
- TLS;
- backups automatizados;
- point-in-time recovery;
- criptografia em repouso;
- monitoramento de saturação de conexões, locks, queries lentas e storage;
- credenciais separadas para migration/aplicação quando viável;
- procedimento de restore testado;
- migrations controladas durante deployments.

PostgreSQL gerenciado é recomendado em vez de auto-hospedar o banco de produção. O container Docker local é alvo de desenvolvimento.
