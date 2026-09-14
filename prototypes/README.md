# Protótipos de UX Web do RASAi

Workspace frontend-only para validar arquitetura visual, UI, UX, nomenclatura, navegação, multiusuário e fluxos operacionais sem implementar backend nesta pasta.

## Produtos e fronteiras

- `apps/rasai-web`: aplicação protótipo voltada aos clientes RASAi.
- `apps/backoffice`: aplicação protótipo privada do proprietário da plataforma.
- `packages/ui`: design system compartilhado e neutro ao produto.
- `packages/contracts`: contratos TypeScript usados pelas duas aplicações.
- `packages/mocks`: implementação simulada desses contratos.

Os dois apps pertencem ao mesmo workspace e reutilizam a mesma base React/UI. O isolamento existe em rotas, permissões, dados e casos de uso.

## Autoridade do contrato

Os protótipos não são fonte normativa do produto. A autoridade continua em runtime, testes e documentação normativa do RASAi.

Um contrato TypeScript pode representar:

- uma capacidade que já existe na Web API, caso em que deve corresponder ao endpoint real;
- uma capacidade desejada exclusivamente para validação de UX, caso em que deve estar explicitamente identificada como gap e não pode ser apresentada como funcionalidade SaaS disponível.

Nenhum mock, botão ou fluxo visual cria comportamento de backend por si só.

O frontend não recria regra do core. Uma capacidade promovida ao produto deve ser atendida pelo core/control plane/API correspondente e reutilizada pelo console quando aplicável.

Referência dos endpoints vigentes: [`../docs/WEB_API_FOUNDATION.md`](../docs/WEB_API_FOUNDATION.md).

## RASAi Web - cliente

- dashboard e contexto Organization > Workspace > Project > Property > Environment;
- auditorias e criação guiada;
- central de execuções com próximas ocorrências, fila e progresso simulado;
- agendamentos e política `SKIP/QUEUE`;
- relatórios e comparações;
- Search Intelligence;
- integrações e BYOK;
- visualização de configuração efetiva e herdada;
- perfis multiusuário e RBAC simulados.

## Backoffice - proprietário da plataforma

- visão global de clientes e usuários;
- consumo/custos por tenant, usuário, provider, job, audit e credencial lógica;
- separação visual entre `provider_cost_estimate`, `platform_cost` e `billable_cost`;
- gestão visual de referências de credenciais da plataforma;
- defaults globais distribuídos;
- saúde de integrações;
- trilha administrativa.

Essas telas não significam que todos os endpoints administrativos globais existam no backend atual.

## Contratos SaaS existentes usados pelo protótipo

O SaaS atual oferece autenticação/tenancy, hierarquia organizacional, auditorias, execution jobs, schedules, próximas ocorrências, histórico/eventos de schedule, estimativa pré-execução para AUDIT, catálogo de serviços, reports autorizados e consumption analytics.

O mapeamento exato está em [`docs/SAAS_CONTRACT_MAP.md`](docs/SAAS_CONTRACT_MAP.md).

## Contratos desejados representados visualmente

Os gaps aceitos pelo protótipo são:

1. `ExecutionProgress` detalhado com estágio, unidades, percentual e eventos operacionais;
2. `CredentialReference` com owner/origem sem retorno do segredo;
3. separação persistida de `provider_cost_estimate`, `platform_cost` e `billable_cost`;
4. endpoints administrativos globais de backoffice fora da tenancy normal de cliente;
5. configuração/defaults hierárquicos com origem, herança, override e escopos permitidos;
6. catálogo estruturado adicional de relatórios e drill-down quando a API atual não fornecer a projeção necessária;
7. transporte de atualização opcional por SSE; polling permanece alternativa compatível.

Esses itens são contratos desejados de interface. Não devem ser usados como documentação de endpoint existente.

## Executar

```bash
cd prototypes
npm install
npm run dev:rasai
npm run dev:backoffice
```

Os protótipos não executam crawling, não calculam SARI/SCORE-GEO e não fazem chamadas reais a providers.
