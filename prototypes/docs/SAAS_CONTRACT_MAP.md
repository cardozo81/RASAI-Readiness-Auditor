# SaaS como provedor dos protótipos

Este documento separa contratos disponíveis no runtime Web/API de contratos apenas desejados pela experiência dos protótipos. Um contrato desejado pode ser usado por mocks para validar UX, mas não deve ser apresentado como endpoint disponível.

Referência normativa de endpoints: [`../../docs/WEB_API_FOUNDATION.md`](../../docs/WEB_API_FOUNDATION.md).

## Contratos atuais aproveitáveis

| Experiência Web | Contrato SaaS atual | Observação |
|---|---|---|
| Estado de autenticação | `GET /auth/config` | informa modo e disponibilidade de login Web |
| Identidade atual | `GET /api/v1/me` | usuário interno, memberships e escopos acessíveis |
| Organizações | `GET /api/v1/organizations` | tenant-aware |
| Workspaces | `GET /api/v1/organizations/{organization_id}/workspaces` | tenant-aware |
| Projetos | `GET /api/v1/workspaces/{workspace_id}/projects` | tenant-aware |
| Properties | `GET /api/v1/projects/{project_id}/properties` | tenant-aware |
| Environments | `GET /api/v1/properties/{property_id}/environments` | tenant-aware |
| Auditorias | `GET /api/v1/projects/{project_id}/audits` | não expõe `workspace_path` |
| Relatórios do AUD | `GET /api/v1/audits/{audit_id}/reports` | lista superfícies autorizadas |
| Asset de relatório | `GET /api/v1/audits/{audit_id}/reports/{asset_path}` | limitado à árvore pública e extensões permitidas |
| Jobs | `GET/POST /api/v1/projects/{project_id}/execution-jobs` | criação é durável, não execução inline |
| Job | `GET /api/v1/execution-jobs/{job_id}` | consulta autorizada |
| Cancelamento | `POST /api/v1/execution-jobs/{job_id}/cancel` | exige permissão de gerenciamento |
| Opções canônicas AUDIT | `GET /api/v1/audit-job-options` | opções/defaults secret-free |
| Estimativa pré-execução | `POST /api/v1/projects/{project_id}/execution-cost-estimate` | estimador monetário disponível para `AUDIT` |
| Schedules | `GET/POST /api/v1/projects/{project_id}/schedules` | lista/cria schedules |
| Schedule | `GET/PATCH/DELETE /api/v1/schedules/{schedule_id}` | leitura, alteração e disable |
| Pause | `POST /api/v1/schedules/{schedule_id}/pause` | estado `PAUSED` |
| Resume | `POST /api/v1/schedules/{schedule_id}/resume` | estado `ACTIVE` |
| Duplicação | `POST /api/v1/schedules/{schedule_id}/duplicate` | novo schedule com nome informado |
| Histórico schedule | `GET /api/v1/schedules/{schedule_id}/runs` | runs do schedule |
| Eventos schedule | `GET /api/v1/schedules/{schedule_id}/events` | eventos do schedule |
| Próximas ocorrências | `GET /api/v1/schedules/{schedule_id}/next-occurrences` | `count` bounded |
| Usage summary | `GET /api/v1/organizations/{organization_id}/usage` | resumo da organização |
| Consumption analytics | `GET /api/v1/organizations/{organization_id}/consumption` | filtros por tenant, job, audit, provider e outros campos |
| Milestones | `GET /api/v1/projects/{project_id}/milestones` | milestones autorizados |
| Deployment pair | `GET /api/v1/milestones/{milestone_id}/deployment-pair` | `baseline_mode=AUTO|GOLDEN` |
| Search queries | `GET /api/v1/projects/{project_id}/search-queries` | queries do projeto |
| Search runs | `GET /api/v1/search-queries/{query_id}/runs` | histórico bounded |
| Serviços de standards | `GET /api/v1/standards/services` | nomes de variáveis e estado; nunca valores de secret |

A camada HTTP continua fina: tenancy e persistência pertencem ao control plane; auditorias e crawling são executados por workers, não dentro da requisição HTTP.

## Contratos desejados - cliente RASAi

### ExecutionProgress detalhado

Exemplo conceitual de mock:

```json
{
  "job_id": "JOB-*",
  "percent": 72,
  "current_stage": "CRUX",
  "message": "Coletando dados de campo",
  "stages": [
    {"id":"crawl","status":"done","completed_units":120,"total_units":120},
    {"id":"crux","status":"running","completed_units":17,"total_units":24}
  ],
  "updated_at": "..."
}
```

O endpoint de job atual não define esse contrato detalhado de estágio/unidades/percentual. A UI pode simulá-lo apenas para validação de experiência.

### Configuração efetiva e herança

Contrato desejado:

- key técnica;
- label;
- tipo;
- default;
- allowed values;
- scopes permitidos;
- indicador de secret;
- dependências;
- permissão necessária;
- valor efetivo;
- origem/proveniência;
- override.

`GET /api/v1/audit-job-options` e `GET /api/v1/standards/services` já fornecem partes desse problema, mas não constituem uma API geral de configuração hierárquica.

### CredentialReference

O browser nunca deve receber o secret. Contrato desejado:

```text
credential_id
provider
owner_type
owner_id
source = PLATFORM_SHARED | ORGANIZATION_SHARED | USER_PRIVATE
status
configured
last_used
```

A API atual expõe nomes das variáveis e hints de configuração em superfícies específicas, mas não possui esse catálogo geral de referências de credenciais.

## Contratos desejados - Backoffice

Esses contratos devem existir em fronteira administrativa própria e não devem ser confundidos com endpoints tenant-aware de cliente.

Contratos ainda não disponíveis como API global:

- clientes/organizações cross-tenant;
- usuários globais e memberships cross-tenant;
- consumo global cross-tenant;
- gestão de referências de credenciais da plataforma;
- defaults/policies globais;
- health administrativo de providers;
- trilha de auditoria administrativa.

As telas correspondentes no protótipo são mocks de UX.

## Atribuição financeira desejada

Cada evento externo deveria permitir distinguir:

```text
credential_id
credential_source
provider_cost_estimate
platform_cost
billable_cost
```

O runtime atual possui usage ledger e estimativa pré-execução, mas não deve ser interpretado como contrato completo desses três componentes financeiros por credencial lógica.

Responsabilidade financeira não pode ser inferida apenas pelo provider; depende da credencial/política efetivamente resolvida.

## Integração do protótipo com API real

As páginas dependem de `SaasClientContract`. `packages/mocks` fornece a implementação simulada.

Uma implementação HTTP deve mapear cada método somente para endpoints existentes listados acima. Métodos associados a contratos desejados devem continuar identificados como mock ou gap até que o backend correspondente exista.

A troca do mock por cliente HTTP não deve mover scoring, crawling, autorização ou resolução de secrets para o frontend.
