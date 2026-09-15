# UX de configuração, execução e relatórios

## Objetivo

Este documento consolida o contrato de experiência do usuário para configuração local, SaaS Pilot Web, acompanhamento de execução e leitura dos relatórios HTML do RASAi.

A experiência preserva cinco princípios:

1. o usuário não precisa conhecer nomes de variáveis para concluir o fluxo comum;
2. defaults do runtime não devem ser materializados como overrides sem necessidade;
3. secrets permanecem separados de configuração persistente e de `AuditJob`;
4. percentuais e estados de execução distinguem medição real de projeção por marcos;
5. score numérico, força da medição e readiness operacional não são condensados em uma sinalização visual enganosa.

## Console interativo

O primeiro nível é orientado a tarefas:

```text
1. Preparar auditoria
2. Auditorias / histórico
3. Relatórios consolidados
4. Inteligência Artificial
5. Integrações e serviços
6. Todas as configurações
7. Sistema / restaurar padrões
H. Ajuda
Q. Sair
```

O fluxo recomendado é:

```text
Perfil da próxima auditoria, quando aplicável
  -> Escopo
  -> Análises / resultados desejados
  -> Resolver itens CONFIGURAR
  -> Revisar IA e integrações necessárias
  -> Salvar configuração, se desejar reutilização local
  -> Preflight
  -> Executar
  -> Relatórios / histórico
```

### Arquitetura de configuração

O usuário navega pela capacidade que deseja executar ou pelo catálogo técnico. A edição permanece vinculada ao **owner canônico** da configuração.

```text
capacidade / resultado
  -> dependências relacionadas
      -> ID canônico da configuração
          -> editor da variável
```

Uma configuração não é duplicada porque várias capacidades a consomem. A tela da capacidade referencia o mesmo owner e o mesmo ID numérico estável.

A visão técnica completa permite organizar o catálogo por owner funcional, ordem alfabética, estado, modificadas, pendentes ou busca por ID/nome/finalidade.

### Tela da variável

A tela canônica diferencia:

- **default do runtime**: nenhuma ação necessária;
- **override**: valor explícito que substitui o default;
- **secret**: credencial disponível em sessão ou escopo seguro suportado;
- **configuração não secreta**: pode ser persistida no `rasai-console.ini`;
- **origem**: sessão, arquivo, Windows/User, Windows/Machine, default ou não configurado.

A apresentação usa os blocos:

```text
INFORMAÇÃO
ESTADO ATUAL
DOMÍNIO / INPUT
AÇÕES
```

### Device e resultados derivados

`Device` é a autoridade para os relatórios Mobile/Desktop:

```text
mobile  -> Mobile INCLUÍDO; Desktop NÃO APLICÁVEL
desktop -> Mobile NÃO APLICÁVEL; Desktop INCLUÍDO
both    -> Mobile INCLUÍDO; Desktop INCLUÍDO
```

Os dois resultados não possuem seleção independente.

No Experience Apdex, o console projeta o mix herdado da próxima execução:

```text
mobile  -> mobile=100,desktop=0,tablet=0
desktop -> mobile=0,desktop=100,tablet=0
both    -> mobile=60,desktop=40,tablet=0
```

Esse comportamento é de configuração do console. O runtime/CLI preserva seus defaults canônicos quando não recebe a projeção do console. Tablet continua disponível apenas como override avançado da população de Experience Apdex.

### Search Intelligence

Termos, depth, região, device SERP e classificação competitiva são inputs da próxima execução, não variáveis de ambiente.

Durante o uso normal ficam na sessão. Quando o operador escolhe explicitamente **Salvar configuração**, esses inputs não sensíveis podem ser persistidos no `rasai-console.ini`. Provider, governança e credencial continuam pertencendo ao owner SERP; secrets nunca entram no INI.

### Integrações relacionadas a uma capacidade

Integrações como Google Search Console, PageSpeed/Lighthouse e CrUX são apresentadas pelo owner canônico do serviço. Quando uma análise precisa de parâmetros de mais de um serviço, a tela da análise mostra as dependências relacionadas e os IDs que levam ao editor correto.

Não existe necessidade de o usuário conhecer em qual categoria interna uma variável foi originalmente implementada.

## Persistência local

Precedência operacional:

```text
valor explícito presente no processo/Windows
> valor não secreto persistido no rasai-console.ini
> default do runtime
```

O `rasai-console.ini` armazena somente configuração não secreta permitida pelo catálogo canônico e inputs persistíveis da próxima execução. Campos sensíveis e nomes classificados como secret são excluídos.

Secrets podem ser mantidos apenas na sessão atual ou, no Windows e mediante confirmação explícita, em `Windows/User`. O produto não grava API keys, bearer tokens, passwords, OAuth secrets/tokens ou session secrets no INI.

`Windows/Machine` pode ser detectado como origem, mas não é administrado automaticamente.

## SaaS Pilot Web

A tela de nova auditoria combina controles de alto nível com configuração guiada.

### Paridade de composição

Os seguintes caminhos materializam o mesmo contrato não secreto de `AuditJob`:

```text
rasai api
rasai.web.pilot_app:app
rasai worker ...
python -m rasai.worker_cli ...
```

A composição direta do ASGI e do worker não depende de o usuário passar antes pelo roteador CLI principal. Standards/GSC, perfis sintéticos e Improvement Intelligence estendem o mesmo contrato de payload em qualquer desses caminhos.

Improvement Intelligence permanece secret-safe: o `AuditJob` armazena apenas escolhas não secretas; credenciais continuam no worker/deployment autorizado.

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
- relação com RASAi;
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

Secrets não aparecem como inputs do SaaS Pilot. OAuth/refresh/access tokens GSC e API keys PageSpeed/CrUX são resolvidos no worker/deployment autorizado.

O endpoint:

```text
GET /api/v1/audit-job-options
```

reflete extensões do `AuditJob`, incluindo Improvement Intelligence e perfis sintéticos, mesmo quando uma opção ainda não possui controle guiado próprio.

O JSON completo do `AuditJob` permanece disponível como área avançada sincronizada com os campos guiados. É escape hatch para parâmetros ainda sem controle visual, não a interface recomendada para configuração comum.

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

Todos os relatórios permanecem estáticos, self-contained e read-only sobre evidência persistida.

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

O enhancer não altera scores, métricas, Findings ou RuleExecutions. Filtros e paginação são apenas apresentação client-side.

### Leitura pública do SARI

`index.html` e `readiness.html` não usam a banda numérica do SARI como conclusão isolada.

A hierarquia visual é:

```text
1. Readiness / força da conclusão
   READY | ATTENTION | BLOCKED | UNKNOWN
   + Consolidation

2. Qualidade medida
   score 0-100 + banda Excelente/Alta/Moderada/Baixa/Crítica

3. Evidência explicativa
   Coverage + Confidence + Critical Gates + RuleExecutions/findings
```

Exemplo:

```text
96/100
qualidade medida: Excelente
readiness: BLOCKED
```

A apresentação correta é **Readiness bloqueada**, mantendo `96/100` como qualidade do universo medido. Não existe badge primária positiva que mascare o bloqueio de readiness.

Da mesma forma, `PARTIAL` ou `NOT_CONSOLIDATED` não aparecem visualmente como readiness positiva apenas porque o subconjunto medido obteve nota alta.

### Erros de integrações

Timeout, quota, erro de autenticação/provider/API ou falha de transporte aparecem como diagnóstico de integração/medição. Não são defeitos do target e não recebem penalidade SARI artificial.

Quando uma integração obtém finding técnico conclusivo sobre o website, ele só participa do SARI se existir regra BR-GEO equivalente e mapeamento explícito sem dupla pontuação.

## Critérios de aderência

A experiência está aderente quando:

- o fluxo comum pode ser concluído sem conhecer variáveis `RASAI_*`;
- cada configuração possui um owner canônico e ID estável;
- capacidades mostram somente dependências relacionadas;
- configuração técnica completa continua acessível;
- defaults, overrides, origens e secrets são distintos;
- `Device` governa os resultados Mobile/Desktop e o default herdado de Experience Apdex no console;
- Search inputs só persistem por ação explícita de salvar;
- secrets nunca são serializados no INI ou `AuditJob`;
- o SaaS Pilot não pede keys/tokens no browser;
- import ASGI direto e worker direto aceitam o mesmo contrato recente de `AuditJob` do roteador principal;
- progresso de etapa não é confundido com progresso global;
- percentuais estimados são rotulados como projeção;
- relatórios mantêm estrutura, busca, filtros e navegação local consistentes;
- SARI alto não mascara medição parcial/não consolidada nem Critical Gate bloqueado/indeterminado;
- erro operacional de integração não é apresentado como falha do website;
- melhorias externas permanecem sem impacto automático em `SARI-001` / `SCORE-GEO-004` sem mapeamento metodológico explícito.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md) e [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md).
