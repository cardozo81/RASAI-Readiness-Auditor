# Escopo consolidado — protótipos Web RASAi

## Objetivo

Validar visualmente e por interação a futura experiência Web do RASAi sem implementar backend. O resultado deve poder ser reaproveitado como base do frontend definitivo.

## Produtos

### RASAi Web

Aplicação dos clientes. Deve priorizar tarefas e não copiar o console literalmente.

- Dashboard operacional.
- Auditorias e wizard de execução.
- Central de execuções com fila, execução atual e histórico.
- Agendamentos recorrentes e próximas ocorrências.
- Relatórios e comparações.
- Search Intelligence.
- Integrações e BYOK.
- Configuração efetiva/herança.
- Multiusuário/RBAC.

### RASAi Backoffice

Aplicação exclusiva do proprietário da plataforma.

- Clientes/organizações e usuários.
- Consumo e custo global.
- Rastreabilidade por usuário, tenant, provider, job, audit, report e credencial lógica.
- Gestão de credenciais da plataforma.
- Defaults globais distribuídos.
- Saúde de providers e integrações.
- Auditoria administrativa.

## Design e UX

- layout funcional e responsivo;
- cores pastéis/equilibradas; cor semântica para sucesso, atenção e erro;
- contraste e acessibilidade preservados;
- menus, shells, cards, badges, tabelas, gráficos, drawers e estados reutilizados;
- nenhuma duplicação estrutural entre páginas;
- componentes de domínio compõem primitives compartilhados;
- dados mockados devem representar cenários reais do RASAi.

## Execução e tempo real

O protótipo deve diferenciar:

1. próximas ocorrências de schedule;
2. jobs materializados na fila;
3. jobs em execução;
4. concluídos/parciais/falhos.

O progresso detalhado é um contrato desejado do SaaS: estágio atual, percentual, unidades e eventos. O protótipo usa polling simulado; produção poderá usar polling ou SSE.

## Credenciais

Há três origens lógicas:

- `PLATFORM_SHARED`: paga/gerida pelo RASAi;
- `ORGANIZATION_SHARED`: compartilhada pelo cliente/organização;
- `USER_PRIVATE`: BYOK privada do usuário.

Secrets nunca são retornados ao browser. O frontend vê apenas a referência lógica e saúde.

Para todo uso registrar:

- usuário e tenant;
- project/property/environment;
- provider/model/operação;
- job/audit/report;
- credential reference/source;
- status;
- tokens/quantidade;
- provider cost estimate;
- platform cost;
- billable cost.

BYOK deve manter `provider_cost_estimate` para histórico, mas `platform_cost=0` e `billable_cost=0` quando a política determinar que o consumo não é cobrado pelo RASAi.

Não haverá fallback silencioso de BYOK falha para credencial paga pela plataforma.

## Variáveis e configuração

A Web não edita `os.environ` por usuário. Variáveis do console serão classificadas em:

- runtime interno;
- system/platform default;
- organização;
- projeto;
- property;
- environment;
- usuário;
- template;
- schedule;
- job;
- secret.

A UI deve apresentar nomes humanos, mantendo identificador técnico como rastreabilidade.

A configuração efetiva deve informar origem, herança e override.

## Compatibilidade do console

O console permanece uma interface paralela. Nenhuma feature Web pode tornar Node, React, FastAPI ou PostgreSQL obrigatórios para execução local. Regras compartilháveis devem residir no core/contratos Python e serem apenas renderizadas pelas interfaces.
