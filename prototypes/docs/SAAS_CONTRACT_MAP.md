# SaaS como provedor dos protótipos

Este documento separa contratos já existentes no SaaS de contratos desejados pela experiência Web. O protótipo pode usar contratos desejados quando tecnicamente viáveis; eles são backlog de evolução do SaaS e não backend implementado nesta pasta.

## Contratos atuais aproveitáveis

| Experiência Web | Contrato SaaS atual |
|---|---|
| Identidade atual | `GET /api/v1/me` |
| Organizações | `GET /api/v1/organizations` |
| Workspaces | `GET /api/v1/organizations/{organization_id}/workspaces` |
| Projetos | `GET /api/v1/workspaces/{workspace_id}/projects` |
| Properties | `GET /api/v1/projects/{project_id}/properties` |
| Environments | `GET /api/v1/properties/{property_id}/environments` |
| Auditorias | `GET /api/v1/projects/{project_id}/audits` |
| Jobs | `GET/POST /api/v1/projects/{project_id}/execution-jobs` |
| Job | `GET /api/v1/execution-jobs/{job_id}` |
| Cancelamento | `POST /api/v1/execution-jobs/{job_id}/cancel` |
| Opções canônicas AUDIT | `GET /api/v1/audit-job-options` |
| Schedules | `GET/POST /api/v1/projects/{project_id}/schedules` |
| Schedule CRUD/estado | `/api/v1/schedules/{schedule_id}` + pause/resume/duplicate |
| Histórico schedule | `GET /api/v1/schedules/{schedule_id}/runs` |
| Eventos schedule | `GET /api/v1/schedules/{schedule_id}/events` |
| Próximas ocorrências | `GET /api/v1/schedules/{schedule_id}/next-occurrences` |
| Consumption analytics | `GET /api/v1/organizations/{organization_id}/consumption` |

A API atual já segue o padrão correto: camada HTTP fina, enfileiramento durável e regras/tenancy fora do request process.

## Contratos desejados — cliente RASAi

### Execution progress

Exemplo conceitual:

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

Deve nascer de telemetria do core e poder ser renderizado também pelo console.

### Configuration definitions/effective config

O SaaS deverá, quando implementado, expor definição e resolução de configuração com:

- key técnica;
- label;
- tipo;
- default;
- allowed values;
- scopes permitidos;
- secret;
- dependências;
- permissão necessária;
- valor efetivo;
- origem/proveniência;
- override.

### Credentials

O browser nunca recebe secret. Contrato lógico:

- `credential_id`;
- provider;
- owner type/id;
- source (`PLATFORM_SHARED`, `ORGANIZATION_SHARED`, `USER_PRIVATE`);
- status/health;
- configured;
- last used.

## Contratos desejados — Backoffice

Devem existir em fronteira administrativa própria e não devem ser confundidos com endpoints tenant-aware de cliente.

- clientes/organizações globais;
- usuários globais e memberships;
- uso global cross-tenant;
- credenciais de plataforma;
- defaults/policies de plataforma;
- health de providers;
- trilha de auditoria administrativa.

## Atribuição financeira

Cada evento externo deverá suportar, além do custo técnico existente:

- `credential_id`;
- `credential_source`;
- `provider_cost_estimate`;
- `platform_cost`;
- `billable_cost`.

A responsabilidade financeira nunca deve ser inferida apenas pelo provider. Ela depende da credencial efetivamente resolvida para aquela chamada.

## Migração do mock para SaaS real

As páginas dependem de `SaasClientContract`. Hoje `packages/mocks` implementa esse contrato. A integração futura deve criar um `HttpSaasClient` com o mesmo contrato e substituir a injeção do mock. As páginas e o design system não devem ser reescritos.
