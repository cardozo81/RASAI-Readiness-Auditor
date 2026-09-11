# Control plane PostgreSQL

**Estado:** backend PostgreSQL 18 implementado por configuração explícita. SQLite permanece o backend local padrão do control plane.

Esta capacidade altera apenas a persistência de produto. Não altera `SARI-001`, `SCORE-GEO-004`, coleta de auditoria, aritmética de scoring nem a evidência imutável `AUD-*/audit.db`.

## Limite de armazenamento

```text
estado relacional de produto/control plane
  SQLite      local/padrão
  PostgreSQL  alvo centralizado/hospedado

evidência imutável da auditoria
  AUD-*/audit.db
  relatórios
  artefatos
  evidência de providers
```

Quando selecionado, PostgreSQL é a autoridade relacional centralizada do estado de produto/control plane. `AUD-*/audit.db` permanece o formato imutável de evidência da execução e não é substituído por PostgreSQL.

## Instalação

O suporte PostgreSQL é opcional para que uma instalação local normal não adquira uma dependência de driver que não utiliza.

```powershell
python -m pip install -e ".[postgresql]"
```

O adapter usa Psycopg 3. O código da aplicação não é acoplado a Docker nem a um cloud provider específico.

## Seleção de backend

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_PLATFORM_DB_BACKEND` | `sqlite` | `sqlite`, `postgresql`; aliases aceitos pelo compositor: `postgres`, `pg` | documentar/configurar `sqlite` ou `postgresql`; preferir `postgresql` em control plane centralizado |
| `RASAI_PLATFORM_DATABASE_URL` | sem default | URL/DSN PostgreSQL válida quando backend PostgreSQL está selecionado | definir somente para PostgreSQL; manter como segredo; usar TLS em host remoto |
| `--platform-db` | raiz local padrão do SQLite quando omitido | caminho SQLite; não é aceito com PostgreSQL | usar apenas quando for necessário substituir o caminho SQLite local |

SQLite:

```text
RASAI_PLATFORM_DB_BACKEND=sqlite
```

Quando a variável de backend está ausente, SQLite é selecionado e o banco local do control plane é:

```text
audits/.rasai/platform.db
```

PostgreSQL:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
```

`postgres` e `pg` são aliases aceitos pelo runtime para o nome do backend; `postgresql` é o valor canônico recomendado na documentação/configuração.

`--platform-db` é exclusivo de SQLite. Backend PostgreSQL configurado exige `RASAI_PLATFORM_DATABASE_URL` e nunca faz fallback silencioso para SQLite. Isso evita autoridade dividida.

A senha do banco não é emitida pela saída de status. URLs de exibição são redigidas para preservar usuário/host/database sem expor senha nem parâmetros sensíveis de conexão.

## Alvos de conexão

O adapter PostgreSQL é independente do endpoint. O mesmo runtime pode se conectar a:

- container local PostgreSQL 18 em Docker para desenvolvimento;
- servidor PostgreSQL em outra máquina;
- serviço PostgreSQL gerenciado;
- provedor de hospedagem que exponha endpoint TCP compatível com PostgreSQL.

Exemplo local:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://rasai_app:<password>@127.0.0.1:5432/rasai_control_plane
```

Exemplo hospedado:

```text
RASAI_PLATFORM_DB_BACKEND=postgresql
RASAI_PLATFORM_DATABASE_URL=postgresql://rasai_app:<password>@db.example-host.net:5432/rasai_control_plane?sslmode=require&connect_timeout=10&application_name=rasai
```

Endpoints de pooler específicos do provider são aceitáveis quando expõem contrato de conexão compatível com PostgreSQL.

Para bancos remotos/hospedados:

- TLS deve estar habilitado; `sslmode=require` é o mínimo prático e `sslmode=verify-full` é preferível quando validação de hostname/CA está disponível;
- a conectividade de entrada precisa permitir o ambiente de execução do RASAi;
- o usuário do banco deve possuir as permissões exigidas pelas migrations explícitas de schema;
- credenciais permanecem segredos de runtime e não devem ser commitadas;
- caracteres especiais em credenciais na URL devem ser percent-encoded.

O RASAi não detecta “Docker versus hosting” para alterar a lógica e não ramifica comportamento por fornecedor. A localização do banco é representada pela URL de conexão e pela configuração de rede/TLS.

Se PostgreSQL for selecionado explicitamente e estiver indisponível, o control plane falha de forma fechada. Voltar para SQLite exige seleção explícita do backend.

## Migrations de schema

Mutação de schema PostgreSQL é explícita. Startup normal da aplicação e Search Monitoring não criam nem atualizam schema.

Consultar o estado:

```powershell
rasai platform database status
```

Aplicar migrations pendentes:

```powershell
rasai platform database migrate
```

O startup da aplicação exige que a versão do schema corresponda à versão suportada pelo runtime. Schema vazio, atrasado ou mais novo do que o suportado é rejeitado com diagnóstico explícito.

Migrations são ordenadas, transacionais e registradas em tabelas de migration. Reexecutar migration sobre schema já atualizado é idempotente.

## Escopo PostgreSQL atual

O control plane PostgreSQL cobre as entidades de domínio de produto necessárias à arquitetura atual, incluindo:

- organizations, users, memberships e workspaces;
- projects, properties e environments;
- catálogo de auditorias e vínculos de escopo da auditoria;
- milestones e golden baselines;
- page identities;
- comparisons;
- schedules, alert rules e notifications;
- metadados de integrações;
- catálogo/registros de datasets externos;
- usage events e consumption analytics;
- registro de queries de Search Monitoring e resumos das execuções;
- execution jobs duráveis;
- vínculos de identidade externa para resolução OIDC/JWT.

Search Monitoring, scheduling, contabilização de uso, identidade e execution jobs usam a mesma autoridade de control plane selecionada.

## Representação relacional atual

O schema PostgreSQL preserva a representação de domínio esperada pelos contratos atuais da aplicação:

- valores operacionais ISO-8601 usam texto canônico quando APIs expõem strings;
- payloads estruturados usam JSON canônico serializado como texto quando exigido pelo contrato do repository;
- booleanos sensíveis à paridade usam valores `0/1` com constraint quando esse é o contrato vigente;
- timestamps de auditoria de migration usam `TIMESTAMPTZ`.

Mudanças de representação, como adoção mais ampla de `jsonb`, `boolean` nativo PostgreSQL ou `timestamptz`, exigem migrations explícitas de schema e validação de paridade. Não são acopladas implicitamente à seleção do backend.

PostgreSQL usa UTF8 e a timezone da sessão RASAi é UTC.

## Comportamento transacional

O adapter PostgreSQL usa somente statements parametrizados.

- leituras normais usam autocommit para que tráfego somente leitura não permaneça em transações ociosas;
- gravações de domínio usam transações explícitas;
- escopos transacionais aninhados usam savepoints;
- falhas fazem rollback da transação afetada;
- erros de banco expostos a CLI/runtime são sanitizados e podem conter tipo da exceção/SQLSTATE, nunca senha, URL bruta da conexão nem statement SQL bruto.

## Desenvolvimento local e operação hospedada

Um container local PostgreSQL 18 em Docker é adequado para desenvolvimento e testes de paridade. A aplicação conecta pelo mesmo contrato `RASAI_PLATFORM_DATABASE_URL` usado no deployment hospedado.

Para operação SaaS, PostgreSQL gerenciado é o alvo recomendado de produção. A escolha do fornecedor permanece decisão de deployment; o contrato do repositório é cloud-neutral.

## Dados de desenvolvimento/teste

Conteúdo local do control plane SQLite criado durante desenvolvimento não é tratado como autoridade de produção. Um banco PostgreSQL limpo pode, portanto, ser inicializado por migrations explícitas e populado pelos contratos normais da aplicação.

Uma ferramenta de importação SQLite → PostgreSQL só é necessária quando uma instalação contém dados autoritativos que precisam ser promovidos. Esse processo deve validar identificadores, foreign keys, contagens de linhas, hashes e escopo de tenant antes do cutover.

## Contrato de CI

O suporte PostgreSQL é validado contra PostgreSQL 18 no GitHub Actions. A suíte de integração verifica pelo menos:

- migration de schema e idempotência;
- contrato UTF8/UTC;
- hierarquia e comportamento de escopo de tenant;
- persistência de schedules, uso e execution jobs;
- rollback transacional;
- Query Registry e histórico de Search Monitoring;
- perfis de conexão local e hospedada/TLS;
- ausência de mutação de `AUD-*/audit.db` por Search Monitoring recorrente;
- seleção explícita do backend e ausência de fallback silencioso;
- redação de credenciais.

Regressões SQLite permanecem nas suítes normais da Product Platform. Um gate portátil de segurança roda sem Psycopg/PostgreSQL para impedir que o suporte centralizado se torne dependência oculta da operação SQLite local.

## Limite SaaS

PostgreSQL é a fundação do banco do control plane. Um deployment SaaS hospedado completo ainda requer contexto de tenant autenticado, serviços Web/API, semântica de claim em fila/scheduler durável, object storage, secret management e workers stateless ou de vida curta.

Persistir schedules em PostgreSQL, isoladamente, não torna um scheduler com múltiplas réplicas horizontalmente seguro. Execução distribuída exige claims atômicos, leases/locks, idempotência, retries limitados e controles de concorrência por tenant/provider.
