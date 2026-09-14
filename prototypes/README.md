# RASAi Web UX Prototypes

Workspace frontend-only para validar arquitetura visual, UI, UX, nomenclatura, navegação, multiusuário e fluxos operacionais antes da consolidação da Web definitiva.

## Produtos e fronteiras

- `apps/rasai-web`: produto usado pelos clientes RASAi.
- `apps/backoffice`: produto privado do proprietário da plataforma.
- `packages/ui`: design system compartilhado e neutro ao produto.
- `packages/contracts`: contratos TypeScript que representam o SaaS como provedor das duas aplicações.
- `packages/mocks`: implementação simulada desses contratos.

React não é duplicado conceitualmente: os dois apps pertencem ao mesmo workspace, usam a mesma versão e o pacote `ui` declara React como peer dependency. O isolamento existe em rotas, permissões, dados e casos de uso.

## Premissa arquitetural

O protótipo pode propor capacidades Web que ainda não existam no SaaS, desde que sejam tecnicamente viáveis e coerentes com o domínio. Nesses casos o frontend usa um contrato desejado e o gap é documentado para futura evolução do SaaS. Nenhum backend é implementado aqui.

O frontend nunca recria regra do core. Quando um gap for promovido a produto, a regra deve ser implementada no core/control plane/API e reutilizada pelo console quando aplicável.

## RASAi Web — cliente

- dashboard e contexto Organização > Workspace > Projeto > Property > Environment;
- auditorias e criação guiada;
- central de execuções: próximas ocorrências, fila e progresso simulado em tempo real;
- agendamentos e política `SKIP/QUEUE`;
- relatórios e comparações;
- Search Intelligence;
- integrações e credenciais próprias do usuário (BYOK);
- configurações efetivas e herdadas;
- perfis multiusuário e RBAC simulados.

## Backoffice — proprietário da plataforma

- visão global de clientes e usuários;
- consumo/custos por tenant, usuário, provider, job, audit e credencial lógica;
- separação entre `provider cost`, `platform cost` e `billable cost`;
- gestão de credenciais SaaS compartilhadas;
- histórico de qual credencial lógica foi usada, sem revelar segredo;
- defaults/variáveis globais distribuídos aos clientes;
- saúde das integrações;
- trilha de auditoria administrativa.

## Contratos SaaS já revisados

O SaaS atual já cobre, em boa parte, autenticação/tenancy, hierarquia de organização, auditorias, execution jobs, schedules, próximas ocorrências, histórico/eventos de schedule e consumo filtrável por organização, projeto, usuário, provider, job e audit.

### Gaps formais aceitos pelo protótipo

1. `ExecutionProgress`: estágio, unidades, percentual e eventos operacionais.
2. `CredentialReference`: owner/origem da credencial sem retorno do segredo.
3. `provider_cost_estimate`, `platform_cost` e `billable_cost` separados.
4. endpoints administrativos globais de backoffice, fora da tenancy normal de cliente.
5. configuração/defaults hierárquicos com origem, herança, override e escopos permitidos.
6. catálogo estruturado de relatórios e superfícies de drill-down.
7. opcionalmente SSE; polling continua fallback válido.

## Executar

```bash
cd prototypes
npm install
npm run dev:rasai
npm run dev:backoffice
```

Os protótipos não executam crawling nem fazem chamadas reais a providers.
