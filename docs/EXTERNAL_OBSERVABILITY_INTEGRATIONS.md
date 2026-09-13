# Integrações externas de observabilidade

## Objetivo

Este documento define as integrações externas adicionadas ao RASAi para ampliar análise histórica, experiência real e evidência pública sem alterar o contrato metodológico de `SARI-001` / `SCORE-GEO-004`.

Princípios obrigatórios:

- `audit.db` continua sendo a evidência imutável do audit;
- dados externos são persistidos em `observability.db` e `artifacts/observability`;
- falha, quota, indisponibilidade ou ausência de dados externos não transforma o website em falha e não deve invalidar uma auditoria já concluída;
- integrações observacionais não entram automaticamente em `SARI-001`, `SCORE-GEO-004` ou Apdex;
- escopo `ORIGIN`, `URL` e `DEVICE/FORM_FACTOR` permanece explícito; não existe média implícita entre granularidades diferentes;
- segredos não são persistidos em `rasai-console.ini`, `rasai-defaults.ini`, `AuditJob`, `audit.db`, HTML ou artifacts sanitizados;
- serviços gratuitos sem credencial podem ser ligados por default somente quando a operação é read-only e bounded;
- serviços com token/key permanecem condicionados à credencial e, quando a quota for particularmente restrita, exigem opt-in explícito.

## Catálogo vigente

| Integração | Estado | Custo de provider | Credencial | Default | Escopo | Device/form factor | Relatórios |
|---|---|---|---|---|---|---|---|
| CrUX History API | integrada | sem cobrança; quota Google | `RASAI_CRUX_API_KEY` | auto quando a key existe | `ORIGIN` | `ALL`, `PHONE`, `DESKTOP`, `TABLET` conforme dispositivos auditados | `web-performance.html`, `observability.html`, `standards.html` |
| Microsoft Clarity Data Export | integrada | gratuito | `RASAI_CLARITY_API_TOKEN` | **off**; opt-in | `ORIGIN`/`URL` | `Device` quando solicitado | `apdex-experience.html`, `observability.html`, `standards.html` |
| Common Crawl CDX History | integrada | gratuito, sem key/token | nenhuma | **on** | `URL` | não possui dimensão de device | `crawling-discovery.html`, `observability.html`, `standards.html` |
| Bing Webmaster Tools live | **não ativada nesta etapa** | gratuito | autenticado | n/a | Search owner data | depende do contrato oficial atual | importação existente continua disponível |
| IndexNow submission | fora desta etapa | gratuito | ownership key | off | `URL` | não aplicável | n/a |

## CrUX History API

O RASAi já possuía o collector `rasai observe crux-history`. A integração automática passa a reutilizar esse contrato na finalização da auditoria quando `RASAI_CRUX_API_KEY` existe e a capacidade não foi desligada.

A coleta automática usa a origem auditada como target e preserva duas granularidades:

- origem sem filtro de form factor (`ALL`);
- origem + form factor para os dispositivos efetivamente observados no audit:
  - `mobile` -> `PHONE`;
  - `desktop` -> `DESKTOP`;
  - `tablet` -> `TABLET`.

CrUX History não é agregado silenciosamente com Lighthouse lab, CrUX current, Open Web Metrics ou Apdex. Os valores são apresentados como série de experiência real agregada por período/form factor.

### Configuração

```text
RASAI_CRUX_HISTORY_ENABLED=true|false
RASAI_CRUX_API_KEY=<segredo>
```

`RASAI_CRUX_HISTORY_ENABLED` é credential-driven: sem override, a integração fica elegível quando `RASAI_CRUX_API_KEY` está disponível no processo/secret store.

A key não é gravada no INI.

Referência oficial: <https://developer.chrome.com/docs/crux/history-api/>

## Microsoft Clarity Data Export

O Clarity acrescenta dados de comportamento real, complementares às medições sintéticas. O RASAi persiste somente os agregados retornados pela Data Export API; não coleta nem persiste session replay, visitor/session IDs, keystrokes, conteúdo de formulários ou DOM de replay.

Métricas documentadas pela fonte incluem, entre outras:

- Scroll Depth;
- Engagement Time;
- Traffic;
- Dead Click Count;
- Excessive Scroll;
- Rage Click Count;
- Quickback Click;
- Script Error Count;
- Error Click Count.

A API permite até três dimensões. Para uso automático pelo RASAi, `URL` é obrigatória: sem URL não é possível provar que o agregado pertence ao domínio auditado. O default também usa `Device` para preservar a dimensão de dispositivo quando a fonte a fornece.

### Configuração

```text
RASAI_CLARITY_ENABLED=false
RASAI_CLARITY_API_TOKEN=<segredo>
RASAI_CLARITY_DAYS=1
RASAI_CLARITY_DIMENSIONS=URL,Device
```

`RASAI_CLARITY_ENABLED` é **false por default**, embora o serviço seja gratuito. A razão é operacional: a Data Export API permite no máximo **10 requests por projeto por dia**, cobre apenas as últimas 24/48/72 horas e retorna no máximo 1.000 linhas sem paginação. Uma auditoria não deve consumir quota limitada sem intenção explícita do operador.

Valores de `RASAI_CLARITY_DAYS`: `1`, `2` ou `3`.

Dimensões aceitas pelo contrato atual:

```text
Browser
Device
Country/Region
OS
Source
Medium
Campaign
Channel
URL
```

Até três dimensões podem ser informadas, separadas por vírgula, e `URL` deve estar presente.

O token é tratado como segredo pelo console e nunca entra no INI ou no `AuditJob`.

Referência oficial: <https://learn.microsoft.com/clarity/setup-and-installation/clarity-data-export-api>

## Common Crawl CDX History

Common Crawl fornece evidência histórica pública de crawling. A integração consulta apenas o índice CDX dos conjuntos mensais recentes e **não baixa conteúdo WARC**.

Default:

```text
RASAI_COMMON_CRAWL_ENABLED=true
RASAI_COMMON_CRAWL_MAX_URLS=3
RASAI_COMMON_CRAWL_INDEX_COUNT=2
```

A combinação default produz no máximo três URLs exatas contra os dois índices mensais mais recentes, além da consulta ao catálogo de collections. Existe throttling entre requests.

`RASAI_COMMON_CRAWL_MAX_URLS=0` desliga somente essa subcoleta.

A interpretação é estrita:

> presença no Common Crawl significa apenas que o corpus público registrou a URL naquela captura.

Não significa:

- indexação Google;
- indexação Bing;
- ranking;
- disponibilidade atual;
- visita por GPTBot/ClaudeBot/PerplexityBot;
- conhecimento por um modelo de IA.

Common Crawl não tem dimensão de device. O relatório não replica o mesmo dado como Mobile/Desktop/Tablet.

Referências oficiais:

- <https://commoncrawl.org/get-started>
- <https://index.commoncrawl.org/collinfo.json>

## Bing Webmaster Tools

O RASAi já possui contratos/importadores para dados exportados do Bing Webmaster Tools e `BING_WEBMASTER` já é origem suportada em Search Intelligence.

A integração live não foi ligada nesta etapa. Em 31 de agosto de 2026 a Microsoft aposentou as APIs SOAP e POX e orientou migração para REST. Parte da documentação pública de métodos ainda expõe exemplos legados `.svc/json`, portanto esta implementação não presume um endpoint live apenas por compatibilidade histórica.

A regra é deliberada: enquanto o contrato REST atual não estiver inequívoco e testável, o RASAi mantém importação evidence-bound em vez de afirmar suporte live incompleto.

Referência: <https://learn.microsoft.com/bingwebmaster/>

## IndexNow

IndexNow não faz parte deste pacote porque é uma operação de escrita/submissão externa. Uma auditoria normal é read-only; submissão IndexNow deve ser uma feature separada com opt-in, dry-run, ownership verificado, allowlist e proteção de ambientes não produtivos.

## Persistência e segurança

### `audit.db`

Não recebe os datasets externos. Pode receber apenas o estado operacional já existente em `standards_service_runs` para que o relatório mostre `DISABLED`, `NOT_CONFIGURED`, `SUCCESS`, `PARTIAL`, `NO_DATA` ou `ERROR`.

### `observability.db`

Mantém dados reconstruíveis:

- `crux_history` para CrUX History;
- `behavioral_observations` para agregados Clarity;
- `web_archive_observations` para Common Crawl.

### `artifacts/observability`

Mantém resposta sanitizada/proveniência necessária para auditoria do dataset. Credenciais não são copiadas para artifacts.

## Console interativo e INI default

O arquivo empacotado `src/rasai/config/rasai-defaults.ini` continua sendo uma baseline de produto e não um secret store.

A baseline inclui somente parâmetros não secretos:

```text
RASAI_COMMON_CRAWL_ENABLED=true
RASAI_COMMON_CRAWL_MAX_URLS=3
RASAI_COMMON_CRAWL_INDEX_COUNT=2
RASAI_CLARITY_ENABLED=false
RASAI_CLARITY_DAYS=1
RASAI_CLARITY_DIMENSIONS=URL,Device
```

CrUX History permanece AUTO por credencial e não materializa um hard-on/hard-off no INI default.

Segredos abaixo nunca são persistidos no INI:

```text
RASAI_CRUX_API_KEY
RASAI_CLARITY_API_TOKEN
```

Precedência permanece a vigente no produto:

```text
process/OS environment > rasai-console.ini > rasai-defaults.ini > fallback defensivo de código
```

## Perfis de execução

Os perfis do console continuam sendo overlays de sessão e não alteram automaticamente estas integrações.

Isso é intencional:

- `Completo seguro` não deve consumir a quota diária do Clarity apenas por ter sido selecionado;
- Common Crawl já é governed pelo default/override da integração;
- CrUX History é credential-driven, independente da seleção de perfil;
- nenhuma integração muda termos SERP, IA, carga sintética ou análise profunda.

## Relatórios

### `web-performance.html`

Recebe resumo CrUX History por `target`, `scope`, `form factor`, métrica e período. Não mistura o histórico com Lighthouse lab ou Apdex.

### `apdex-experience.html`

Recebe painel **Observed Behavioral UX** do Clarity. O relatório declara que os agregados comportamentais complementam, mas não recalculam, o Apdex sintético.

### `crawling-discovery.html`

Recebe histórico Common Crawl por URL: quantidade de capturas/collections e primeira/última captura observada.

### `observability.html`

Permanece a superfície detalhada dos datasets externos e proveniência.

### `standards.html`

Exibe o estado operacional das integrações por meio de `standards_service_runs`.

## Falhas externas

O comportamento obrigatório é:

```text
external provider/public API failure
        -> ERROR/PARTIAL/NO_DATA na integração
        -> audit e scoring preservados
```

Nunca:

```text
external provider/public API failure
        -> website FAIL
        -> SARI/SCORE reduzido
```
