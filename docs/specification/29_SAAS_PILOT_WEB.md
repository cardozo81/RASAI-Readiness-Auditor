# 29 - SaaS Pilot Web

**Estado:** vigente para a primeira superfície de navegador do RASAi.  
**Natureza:** Product Platform / Web API; não altera scoring.

## 1. Objetivo

Disponibilizar uma interface Web utilizável sobre o control plane e a execution queue existentes, mantendo o motor de auditoria, Search Intelligence e reports como fontes funcionais independentes da camada de apresentação.

## 2. Requisitos normativos

`WEB-PILOT-001` - o browser deve consumir a API tenant-aware; nenhuma regra de negócio relevante pode existir apenas em JavaScript.

`WEB-PILOT-002` - `SARI-001` e `SCORE-GEO-004` não podem ser recalculados, ajustados ou reinterpretados pela UI.

`WEB-PILOT-003` - requests HTTP de execução somente podem criar durable execution jobs. Crawling/auditoria permanecem em worker separado.

`WEB-PILOT-004` - a navegação deve respeitar `Organization -> Workspace -> Project -> Property -> Environment` e todo endpoint deve revalidar autorização no servidor.

`WEB-PILOT-005` - o catálogo HTTP de auditorias não pode expor `workspace_path`.

`WEB-PILOT-006` - quando reports forem servidos via HTTP, somente a árvore `AUD-*/report/**` do AUD autorizado pode ser disponibilizada. `audit.db`, secrets e artifacts fora da superfície pública não podem ser acessíveis pelo route boundary.

`WEB-PILOT-007` - traversal, symlink escape e extensão fora do allowlist de apresentação Web devem falhar fechado.

`WEB-PILOT-008` - o piloto não deve criar banco de senhas, token proprietário ou mecanismo de autenticação que seja apresentado como produção. O modo `trusted-header` continua exigindo gateway confiável quando houver exposição pública.

`WEB-PILOT-009` - conveniência de identidade no browser somente pode ser documentada como desenvolvimento em loopback; não deve ser usada como defesa de ambiente hospedado.

`WEB-PILOT-010` - a UI deve operar contra a mesma `store_factory` usada pela API e portanto deve preservar SQLite local/default e PostgreSQL opt-in.

`WEB-PILOT-011` - a instalação CLI local sem `.[web]` continua funcional. A UI não pode adicionar Node/npm/bundler como dependência obrigatória.

`WEB-PILOT-012` - Search Intelligence, Usage, Milestones e Deployment Pair devem permanecer projeções dos contratos existentes, sem segunda persistência Web.

`WEB-PILOT-013` - `/app`, `/app/operations`, a API de execution jobs, managed schedules e o worker devem derivar a configuração `AUDIT` do mesmo contrato canônico. A camada Web não pode manter um allowlist reduzido independente do runtime.

`WEB-PILOT-014` - durable payloads devem ser validados antes da persistência. Opção desconhecida, combinação inválida ou segredo inline não pode ser aceita para falhar apenas no worker.

`WEB-PILOT-015` - defaults de Synthetic User Experience Apdex expostos pelo SaaS devem ser os mesmos defaults do CLI/runtime. Omissão de thresholds padrão não pode ser interpretada como configuração inválida ou customização do usuário.

`WEB-PILOT-016` - configuração/credencial de provider externo que seja secret deve permanecer fora de `payload_json`. Em ambiente multi-tenant, eventual importação Dynatrace ou integração equivalente deve ser resolvida por referência tenant-scoped no worker autorizado.

`WEB-PILOT-017` - mudanças em contratos de auditoria, worker, Web ou runtime compartilhado devem acionar regressão de paridade PostgreSQL e SaaS/runtime no CI.

## 3. Superfícies mínimas

A primeira versão deve permitir:

- selecionar Organization, Workspace, Project, Property e Environment;
- visualizar auditorias do Project;
- abrir reports materializados de um AUD autorizado;
- criar `AUDIT` job com o payload canônico permitido pelo worker;
- editar a configuração não secreta completa exposta por `GET /api/v1/audit-job-options`;
- visualizar Query Registry e criar `SEARCH_MONITOR` job;
- acompanhar/cancelar execution jobs conforme role;
- visualizar milestones e resolver pair before/after;
- criar e administrar managed schedules;
- visualizar usage/cost e Consumption Analytics da Organization autorizada com filtros tenant-aware.

## 4. Autorização

A UI não é authority de tenancy.

Qualquer filtro visual é somente conveniência. A decisão de acesso ocorre novamente na API com `Principal` e memberships do control plane.

A enumeração de ID de outro tenant deve resultar em recusa, inclusive para milestones, usage, consumption, schedules e report assets.

## 5. Report boundary

São permitidos somente arquivos resolvidos dentro de:

```text
<Path persistido do AUD>/report/
```

O servidor deve normalizar/resolver o path e confirmar que o resultado permanece descendente do report root.

A existência de um `audit_id` não autoriza acesso ao workspace bruto.

## 6. Deployment comparison

A UI pode solicitar `AUTO` ou `GOLDEN` para resolução do pair, reutilizando `resolve_deployment_pair`.

A camada Web não deve inferir causalidade. Milestone estabelece cronologia; comparabilidade e limitações continuam vindo do contrato Product Platform/Monitoring.

## 7. Execution jobs e schedules

A criação de auditoria pela UI deve usar o mesmo contrato de execution jobs e o mesmo allowlist de payload do worker. `GET /api/v1/audit-job-options` é a projeção autenticada desse contrato para interfaces Web.

O destino deriva da Property/Environment registrada; shell command/argv arbitrário não faz parte do contrato HTTP.

Execution jobs e managed schedules devem preservar somente escolhas não secretas do usuário em `payload_json`. Defaults do runtime podem ser materializados na execução, mas sua origem não pode ser falsamente apresentada como customização do usuário.

O contrato de validação deve ser aplicado tanto ao backend SQLite quanto ao PostgreSQL antes da gravação do job/schedule.

## 8. Segurança de frontend

A página do piloto deve:

- funcionar sem recurso de CDN obrigatório;
- usar `Cache-Control: no-store`;
- usar CSP restritiva compatível com a implementação zero-build;
- não materializar secrets no HTML inicial;
- não armazenar API keys/provider tokens;
- tratar eventual `USR-*` local somente como identity hint de desenvolvimento.

## 9. Fora de escopo

Não fazem parte desta especificação:

- Identity Provider obrigatório/específico;
- billing;
- object storage definitivo;
- Kubernetes;
- queue externa obrigatória;
- multi-region/hubs;
- runner privado remoto;
- importação Dynatrace hosted sem vínculo de integração tenant-scoped;
- migração de `audit.db` para PostgreSQL;
- design system ou framework de frontend definitivo.

## 10. Evidência de validação

O contrato deve possuir regressão automatizada para:

- carregamento da shell sem dado de tenant embutido;
- tenant isolation das projeções aditivas;
- autorização do report boundary;
- bloqueio de tentativa de acesso fora de `report/`;
- preservação da API/execution queue já existente;
- igualdade dos defaults compartilhados entre CLI/runtime e SaaS;
- rejeição antecipada de payloads inválidos;
- paridade de persistência e comportamento sobre PostgreSQL real;
- regressão integral do produto via CI.

Documentação operacional: `../SAAS_PILOT_WEB.md`, `../WEB_API_FOUNDATION.md` e `../WEB_API_CLI.md`.