# Escopo consolidado - protótipos Web RASAi

## Objetivo

Validar visualmente e por interação a experiência Web desejada do RASAi sem implementar backend nesta pasta. Os protótipos servem para avaliar UI, UX, navegação, organização de informação e viabilidade dos contratos de frontend.

Eles não constituem especificação normativa do core, da Web API ou do control plane.

## Produtos

### RASAi Web

Aplicação protótipo dos clientes. Deve priorizar tarefas e não copiar o console literalmente.

- dashboard operacional;
- auditorias e wizard de execução;
- central de execuções com fila, execução atual e histórico;
- agendamentos recorrentes e próximas ocorrências;
- relatórios e comparações;
- Search Intelligence;
- integrações e BYOK;
- configuração efetiva/herança;
- multiusuário/RBAC.

### RASAi Backoffice

Aplicação protótipo exclusiva do proprietário da plataforma.

- clientes/organizações e usuários;
- consumo e custo global;
- rastreabilidade por usuário, tenant, provider, job, audit, report e credencial lógica;
- gestão de referências de credenciais da plataforma;
- defaults globais distribuídos;
- saúde de providers e integrações;
- trilha administrativa.

As telas de Backoffice podem representar contratos desejados que ainda não possuem endpoint administrativo no SaaS atual. Esse estado deve permanecer explícito.

## Design e UX

- layout funcional e responsivo;
- cores pastéis/equilibradas;
- cor semântica reservada para estados relevantes;
- contraste e acessibilidade preservados;
- menus, shells, cards, badges, tabelas, gráficos, drawers e estados reutilizados;
- componentes compartilhados em vez de duplicação estrutural;
- dados mockados plausíveis, sem serem apresentados como dados reais.

## Execução e atualização de estado

A experiência deve diferenciar:

1. próximas ocorrências de schedule;
2. jobs materializados na fila;
3. jobs em execução;
4. jobs concluídos, parciais ou falhos.

Progresso detalhado por estágio, percentual, unidades e eventos é um **contrato desejado** e não um endpoint disponível no runtime atual. O protótipo usa polling simulado. Uma implementação SaaS pode usar polling e, se houver contrato de backend correspondente, SSE.

## Credenciais

O protótipo usa três origens lógicas desejadas:

```text
PLATFORM_SHARED
ORGANIZATION_SHARED
USER_PRIVATE
```

Secrets nunca devem ser retornados ao browser. A UI deve trabalhar apenas com referência lógica, owner/origem e estado sanitizado.

Atribuição desejada por uso:

- usuário e tenant;
- project/property/environment;
- provider/model/operação;
- job/audit/report;
- credential reference/source;
- status;
- tokens/quantidade;
- `provider_cost_estimate`;
- `platform_cost`;
- `billable_cost`.

A API vigente ainda não fornece todo esse contrato de credencial lógica e atribuição financeira. Por isso esses campos são mocks de UX, não documentação de persistência existente.

Não deve existir fallback silencioso de uma credencial BYOK com falha para credencial paga pela plataforma sem política explícita de backend.

## Variáveis e configuração

A Web não deve editar `os.environ` por usuário.

O protótipo representa uma classificação desejada de configuração por escopo:

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

A UI deve apresentar nome humano e identificador técnico. Origem, herança e override são parte do contrato desejado de configuração efetiva, ainda não uma API completa disponível.

## Compatibilidade com o console

O console permanece interface paralela do produto. Nenhuma decisão do protótipo pode tornar Node, React, FastAPI ou PostgreSQL obrigatórios para o runtime local.

Regras compartilháveis devem permanecer no core/contratos Python e ser apenas projetadas pelas interfaces.

## Referências

- [`../../docs/WEB_API_FOUNDATION.md`](../../docs/WEB_API_FOUNDATION.md) - endpoints atuais.
- [`../../docs/ENVIRONMENT_VARIABLES.md`](../../docs/ENVIRONMENT_VARIABLES.md) - configurações e defaults vigentes.
- [`../../docs/EXTERNAL_CREDENTIALS.md`](../../docs/EXTERNAL_CREDENTIALS.md) - credenciais reais e onboarding.
- [`SAAS_CONTRACT_MAP.md`](SAAS_CONTRACT_MAP.md) - separação entre contrato existente e desejado.
