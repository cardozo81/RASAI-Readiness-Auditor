# UX de configuração, execução e relatórios

## Objetivo

Este documento consolida o contrato de experiência do usuário para configuração local, SaaS Pilot Web, acompanhamento de execução e leitura dos relatórios HTML do RASAi.

A experiência deve preservar quatro princípios:

1. o usuário não precisa conhecer nomes de variáveis para executar o fluxo comum;
2. defaults do runtime não devem ser materializados como overrides sem necessidade;
3. secrets permanecem separados de configuração persistente e de `AuditJob`;
4. percentuais e estados de execução devem distinguir medição real de projeção por marcos.

## Console interativo

O fluxo recomendado é:

```text
Entrada
  -> Projeto
  -> Dispositivo
  -> IA, quando necessária
  -> Web Performance, quando necessário
  -> Synthetic Apdex, quando necessário
  -> Variáveis / credenciais para integrações avançadas
  -> Salvar INI sem secrets
  -> Preflight
  -> Executar
  -> Relatórios / histórico
```

O menu avançado usa navegação por contexto:

```text
CONFIGURAÇÃO
  -> grupo funcional
      -> variável
          -> ação
```

Cada grupo deve explicar o contexto antes de listar variáveis. A tela da variável diferencia:

- **default do runtime**: nenhuma ação necessária;
- **override**: valor explícito que substitui o default;
- **secret**: credencial disponível apenas em sessão, ambiente do sistema ou secret store;
- **configuração não secreta**: pode ser persistida no `rasai-console.ini`.

O menu avançado permite filtrar somente itens definidos para facilitar revisão e troubleshooting.

### Orientação cruzada de integrações

Algumas integrações usam dados de mais de um contexto de configuração. O console deve explicar a relação sem obrigar o usuário a descobrir os vínculos manualmente.

Google Search Console:

```text
Search Intelligence / Observability
  -> OAuth token temporário/secret

Métricas e padrões
  -> property/siteUrl
  -> dias de Search Analytics
  -> máximo de returned rows
  -> defasagem para dados finalizados
```

PageSpeed e CrUX:

```text
Web Performance / Google APIs
  -> API keys

Métricas e padrões
  -> AUTO / ligado / desligado
  -> limite de URLs / timeout compartilhado da família quando aplicável
```

## Persistência local

Precedência operacional:

```text
valor já presente no processo/Windows
> valor não secreto persistido no rasai-console.ini
> default do runtime
```

O `rasai-console.ini` armazena somente configuração não secreta. O catálogo de `EnvironmentSpec` é a allowlist de persistência; campos sensíveis e nomes classificados como secret são excluídos.

Secrets podem ser mantidos apenas na sessão atual ou, no Windows e mediante confirmação explícita, em `Windows/User`. O produto não grava API keys, bearer tokens, passwords, OAuth tokens ou session secrets no INI.

## SaaS Pilot Web

A tela de nova auditoria combina controles de alto nível com configuração guiada.

### Controles principais

- máximo de páginas;
- dispositivo;
- provider de IA;
- Web Performance agregado em `Auto`, `Ligado` ou `Desligado`.

### Serviços de métricas e padrões

O catálogo vem de:

```text
GET /api/v1/standards/services
```

Cada serviço mostra:

- nome e finalidade;
- grau de relação com RASAi;
- escopo;
- estado (`READY`, `NOT_CONFIGURED`, `DISABLED` etc.);
- requisitos/configurações ausentes;
- controle do job.

Semântica do controle:

- **Padrão**: usa o default do registry para serviço sem credencial;
- **Auto**: omite override e deixa o worker resolver pela disponibilidade dos requisitos;
- **Ligado**: solicita explicitamente o serviço, ainda respeitando requisitos obrigatórios;
- **Desligado**: hard-off explícito para o job.

### Formulário guiado

Os campos não secretos mais usados não exigem edição do JSON:

- `standards_max_urls`;
- `standards_timeout_seconds`;
- `gsc_site_url`;
- `gsc_search_analytics_days`;
- `gsc_search_max_rows`;
- `gsc_final_data_lag_days`.

A property GSC aceita:

```text
sc-domain:example.com
```

ou uma propriedade URL-prefix absoluta:

```text
https://www.example.com/
```

Secrets não aparecem como inputs do SaaS Pilot. O OAuth token GSC e API keys PageSpeed/CrUX devem ser resolvidos no worker/deployment autorizado.

O JSON completo do `AuditJob` permanece disponível em uma área avançada e sincronizada com os campos guiados. Ele é uma escape hatch para parâmetros ainda sem controle visual, não a interface recomendada para configuração comum.

## Progresso de execução

A apresentação do console separa:

- **Andamento da etapa**: percentual medido quando existe unidade interna real;
- **Progresso geral**: posição no pipeline, medido somente quando tecnicamente possível e identificado com `~` quando for projeção;
- **Executando**: texto que explica a operação concreta atual.

A barra visual usa a mesma semântica do percentual geral:

```text
Pipeline : [####################----------------------] ~48%
```

Quando o percentual geral é projetado, a tela informa explicitamente que ele não representa tempo restante.

### Etapas com medição interna

Sempre que o runtime possui denominador real, o console projeta avanço medido, por exemplo:

- contextos Chromium de aquisição/renderização;
- contextos PageSpeed/CrUX externos;
- amostras/contextos de Synthetic Apdex;
- suboperações GSC de Sitemaps, URL Inspection e Search Analytics.

Google Search Console registra marcos operacionais secret-safe sem adicionar chamadas:

```text
GSC_COLLECTION_STARTED
GSC_OPERATION_STARTED
GSC_OPERATION_FINISHED
GSC_COLLECTION_FINISHED
```

Esses eventos servem apenas para observabilidade/progresso e não alteram scoring nem evidência do website.

## Relatórios HTML

Todos os relatórios continuam estáticos, self-contained e read-only sobre evidência persistida.

A camada comum de UX aplica:

- busca em tabelas/listas grandes;
- filtro por URL quando existem duas ou mais URLs distintas;
- filtro por contexto Mobile/Desktop quando aplicável;
- paginação client-side sem remover linhas do HTML fonte;
- grid responsivo para population cards;
- índice local `Neste relatório` quando a página possui três ou mais seções `h2`;
- anchors estáveis gerados no browser para navegação dentro da página;
- comportamento responsivo e print-safe.

A navegação local não substitui o menu canônico entre relatórios. Ela organiza somente as seções da página atual.

O enhancer não altera scores, métricas, Findings ou RuleExecutions. Ele também não remove itens do HTML; filtros e paginação são apenas apresentação client-side.

## Critérios de aderência

A experiência está aderente quando:

- o fluxo comum pode ser concluído sem conhecer variáveis `RASAI_*`;
- configuração avançada continua disponível para operadores técnicos;
- defaults, overrides e secrets são visualmente/semanticamente distintos;
- GSC/PageSpeed/CrUX explicam dependências cruzadas;
- secrets nunca são serializados no INI ou `AuditJob`;
- o SaaS Pilot não pede keys/tokens no browser;
- progresso de etapa não é confundido com progresso global;
- percentuais estimados são rotulados como projeção;
- suboperações externas longas indicam o serviço e a unidade em andamento;
- relatórios mantêm estrutura de seções, busca, filtros e navegação local consistentes;
- todas as melhorias permanecem sem impacto automático em `SARI-001` / `SCORE-GEO-004`.
