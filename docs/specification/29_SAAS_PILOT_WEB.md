# 29 - SaaS Pilot Web

**Estado:** VIGENTE para a primeira superfície de navegador do RASAi.  
**Natureza:** Product Platform / Web API; não altera scoring.

## 1. Objetivo

Disponibilizar uma interface Web utilizável sobre o control plane e a execution queue existentes, mantendo o motor de auditoria, Search Intelligence e reports como fontes funcionais independentes da camada de apresentação.

## 2. Requisitos normativos

`WEB-PILOT-001` - o browser deve consumir a API tenant-aware; nenhuma regra de negócio relevante pode existir apenas em JavaScript.

`WEB-PILOT-002` - `SARI-001` e `SCORE-GEO-004` não podem ser recalculados, ajustados ou reinterpretados pela UI.

`WEB-PILOT-003` - requests HTTP de execução somente podem criar durable execution jobs. Crawling/auditoria permanecem em worker separado.

`WEB-PILOT-004` - a navegação deve respeitar `Organization -> Workspace -> Project -> Property -> Environment` e todo endpoint deve revalidar autorização no servidor.

`WEB-PILOT-005` - o catálogo HTTP de auditorias não pode expor `workspace_path`.

`WEB-PILOT-006` - quando reports forem servidos via HTTP, somente a árvore `AUD-*/report/**` do AUD autorizado pode ser disponibilizada. `audit.db`, secrets e artifacts fora da superfície pública não podem ser acessíveis pelo limite de rota.

`WEB-PILOT-007` - path traversal, symlink escape e extensão fora do allowlist de apresentação Web devem falhar fechado.

`WEB-PILOT-008` - o piloto não deve criar banco de senhas, token proprietário ou mecanismo de autenticação apresentado como produção. O modo `trusted-header` exige gateway confiável quando houver exposição pública.

`WEB-PILOT-009` - conveniência de identidade no browser somente pode ser documentada como desenvolvimento em loopback; não deve ser usada como defesa de ambiente hospedado.

`WEB-PILOT-010` - a UI deve operar contra a mesma `store_factory` usada pela API e preservar SQLite local/default e PostgreSQL opt-in.

`WEB-PILOT-011` - a instalação CLI local sem `.[web]` continua funcional. A UI não pode adicionar Node/npm/bundler como dependência obrigatória.

`WEB-PILOT-012` - Search Intelligence, Usage, Milestones e Deployment Pair devem permanecer projeções dos contratos existentes, sem segunda persistência Web.

## 3. Superfícies vigentes

A superfície Web deve permitir, conforme autorização e capacidade materializada:

- selecionar Organization, Workspace, Project, Property e Environment;
- visualizar auditorias do Project;
- abrir reports materializados de um AUD autorizado;
- criar job `AUDIT` com payload permitido pelo worker;
- visualizar Query Registry e criar job `SEARCH_MONITOR`;
- acompanhar/cancelar execution jobs conforme role;
- visualizar milestones e resolver par before/after;
- visualizar usage/cost agregado da Organization autorizada.

## 4. Autorização

A UI não é autoridade de tenancy.

Qualquer filtro visual é apenas conveniência. A decisão de acesso ocorre novamente na API com `Principal` e memberships do control plane.

Enumeração de ID pertencente a outro tenant deve resultar em recusa, inclusive para milestones, usage e report assets.

## 5. Limite de acesso aos reports

São permitidos somente arquivos resolvidos dentro de:

```text
<Path persistido do AUD>/report/
```

O servidor deve normalizar/resolver o path e confirmar que o resultado permanece descendente do report root.

A existência de um `audit_id` não autoriza acesso ao workspace bruto.

## 6. Comparação de deployment

A UI pode solicitar `AUTO` ou `GOLDEN` para resolução do par, reutilizando `resolve_deployment_pair`.

A camada Web não deve inferir causalidade. Milestone estabelece cronologia; comparabilidade e limitações continuam vindo do contrato Product Platform/Monitoring.

## 7. Execution jobs

A criação de auditoria pela UI deve usar o mesmo endpoint de execution jobs e o mesmo allowlist de payload do worker.

O destino deriva da Property/Environment registrada; shell command/argv arbitrário não faz parte do contrato HTTP.

## 8. Segurança de frontend

A página do piloto deve:

- funcionar sem recurso de CDN obrigatório;
- usar `Cache-Control: no-store`;
- usar CSP restritiva compatível com a implementação zero-build;
- não materializar secrets no HTML inicial;
- não armazenar API keys/provider tokens;
- tratar eventual `USR-*` local somente como identity hint de desenvolvimento.

## 9. Fora de escopo desta especificação

Esta especificação não define:

- billing definitivo;
- object storage definitivo;
- Kubernetes;
- queue externa obrigatória;
- multi-region/hubs;
- runner privado remoto;
- migração de `audit.db` para PostgreSQL;
- design system ou framework de frontend definitivo.

Identity & Access hospedada **não é mais um gap genérico do produto**: o contrato de autenticação OIDC/JWT, sessão e vínculo de identidade é definido separadamente em `30_IDENTITY_AND_ACCESS.md`. Esta especificação apenas não redefine essa camada.

## 10. Evidência de validação

O contrato deve possuir regressão automatizada para:

- carregamento da shell sem dado de tenant embutido;
- tenant isolation das projeções aditivas;
- autorização do limite de reports;
- bloqueio de tentativa de acesso fora de `report/`;
- preservação da API/execution queue já existente;
- regressão integral do produto via CI.

Documentação operacional: `../SAAS_PILOT_WEB.md`, `../WEB_API_FOUNDATION.md`, `../WEB_API_CLI.md` e `30_IDENTITY_AND_ACCESS.md`.