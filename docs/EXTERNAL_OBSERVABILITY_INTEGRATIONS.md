# Integrações externas de observabilidade

## Objetivo

Este documento define as integrações externas do RASAi para ampliar análise histórica, experiência real e evidência pública sem transformar outcomes externos em substitutos da metodologia de `SARI-001` / `SCORE-GEO-004`.

Princípios obrigatórios:

- `audit.db` continua sendo a evidência imutável do audit;
- datasets externos permanecem em `artifacts/observability/observability.db` e demais artifacts de `artifacts/observability/`;
- falha, quota, indisponibilidade ou ausência de dados externos não transforma o website em falha e não deve invalidar uma auditoria já concluída;
- integrações observacionais não entram automaticamente em `SARI-001`, `SCORE-GEO-004` ou Apdex;
- a única exceção vigente é `BR-GEO-060`, uma corroboração positiva, bounded e de peso mínimo baseada em Common Crawl;
- escopo `ORIGIN`, `URL` e `DEVICE/FORM_FACTOR` permanece explícito; não existe média implícita entre granularidades diferentes;
- segredos não são persistidos em `rasai-console.ini`, `rasai-defaults.ini`, `AuditJob`, HTML ou artifacts sanitizados;
- serviços gratuitos sem credencial podem ser ligados por default somente quando a operação é read-only, bounded e protegida contra alvos privados/sensíveis;
- serviços com token/key permanecem condicionados à credencial e, quando a quota for particularmente restrita, exigem opt-in explícito.

## Catálogo vigente

| Integração | Estado | Custo de provider | Credencial | Default | Escopo | Device/form factor | Relação com SARI | Relatórios |
|---|---|---|---|---|---|---|---|---|
| CrUX History API | integrada | sem cobrança; quota Google | `RASAI_CRUX_API_KEY` | auto quando a key existe | `ORIGIN` | `ALL`, `PHONE`, `DESKTOP`, `TABLET` conforme dispositivos auditados | observacional; não pontua | `report-catalog/cat-04.html`, `report-catalog/metrics.html` |
| Microsoft Clarity Data Export | integrada | gratuito | `RASAI_CLARITY_API_TOKEN` | **off**; opt-in | `ORIGIN`/`URL` | `Device` quando solicitado | observacional; não pontua | `report-catalog/cat-07.html`, `report-catalog/cat-05.html`, `report-catalog/metrics.html` |
| Common Crawl CDX History | integrada | gratuito, sem key/token | nenhuma | **on** | `URL` | não possui dimensão de device | `BR-GEO-060` positive-only, máximo 0,45 ponto Overall | `report-catalog/cat-01.html`, `report-catalog/cat-05.html`, `report-catalog/sari.html`, `report-catalog/methodology.html` |
| Bing Webmaster Tools live | **não ativa no contrato atual** | gratuito | autenticado | n/a | Search owner data | depende do contrato oficial atual | não pontua | importação disponível |
| IndexNow submission | fora do contrato atual | gratuito | ownership key | off | `URL` | não aplicável | não pontua | n/a |

## CrUX History API

O collector `rasai observe crux-history` faz parte do contrato atual. A integração automática reutiliza esse contrato na finalização da auditoria quando `RASAI_CRUX_API_KEY` existe e a capacidade não foi desligada.

A coleta automática usa a origem auditada como target e preserva duas granularidades:

- origem sem filtro de form factor (`ALL`);
- origem + form factor para os dispositivos efetivamente observados no audit:
  - `mobile` -> `PHONE`;
  - `desktop` -> `DESKTOP`;
  - `tablet` -> `TABLET`.

CrUX History não é agregado silenciosamente com Lighthouse lab, CrUX current, Open Web Metrics ou Apdex. Os valores são apresentados como série de experiência real agregada por período/form factor.

CrUX History **não altera SARI**. Ele mede experiência real histórica e deve ser usado para análise longitudinal/before-after, não como proxy de readiness.

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

Clarity **não altera SARI**. Rage/dead click, engagement e scroll são comportamento/outcome e não devem ser convertidos em readiness estrutural.

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

### Relação com SARI: BR-GEO-060

A coleta Common Crawl ocorre antes do cálculo final de `SCORE-GEO-004` para permitir que uma observação positiva qualificada seja persistida como Evidence e RuleExecution normais do scoring.

Contrato:

```text
BR-GEO-060
Dimension = DISCOVERY_ACCESS
Group = EXTERNAL_CRAWL_CORROBORATION
Group Weight = 3% de DISCOVERY_ACCESS
Maximum Overall Impact = 0,45 ponto
Critical Gate = não
```

A regra é **positive-only**. Ela só é criada quando:

- a URL é segura para consulta pública;
- existe observação positiva nos índices recentes;
- pelo menos 50% da amostra bounded selecionada foi observada;
- sinais críticos atuais de Discovery não estão em `FAIL`.

Ausência de captura, erro da API, alvo inelegível ou amostra abaixo do threshold não cria `FAIL`, não cria zero, não reduz Coverage e não reduz Confidence.

A RuleExecution e a Evidence ficam persistidas no `audit.db` exclusivamente para tornar o score reprodutível sem nova chamada externa. O dataset bruto/normalizado continua no sidecar `artifacts/observability/observability.db`.

Contrato detalhado: [`SARI_EXTERNAL_CRAWL_CORROBORATION.md`](SARI_EXTERNAL_CRAWL_CORROBORATION.md).

### Segurança da consulta pública

Mesmo habilitado por default, o RASAi não consulta automaticamente Common Crawl para alvos com:

- localhost/hosts locais ou reservados;
- IP privado/reservado;
- userinfo;
- query string;
- fragment;
- protocolo diferente de HTTP/HTTPS.

Isso evita publicar inadvertidamente alvos internos ou parâmetros sensíveis em uma consulta a índice público.

Referências oficiais:

- <https://commoncrawl.org/get-started>
- <https://index.commoncrawl.org/collinfo.json>

## Bing Webmaster Tools

`BING_WEBMASTER` é origem suportada em Search Intelligence para dados importados do Bing Webmaster Tools.

A integração live não está ativa no contrato atual. O RASAi somente deve declarar suporte live quando o contrato REST oficial vigente estiver inequivocamente implementado e testável. Até lá, a superfície suportada permanece a importação evidence-bound, sem presumir endpoints ou formatos fora do contrato implementado.

Referência: <https://learn.microsoft.com/bingwebmaster/>

## IndexNow

IndexNow não integra o contrato atual porque é uma operação de escrita/submissão externa. Uma auditoria normal é read-only; eventual submissão IndexNow exige contrato próprio com opt-in, dry-run, ownership verificado, allowlist e proteção de ambientes não produtivos.

## Persistência e segurança

### `audit.db`

Datasets externos completos não são copiados para o core.

A exceção metodológica é `BR-GEO-060`: quando Common Crawl qualifica para SARI, o RASAi persiste somente a Evidence/RuleExecution mínima, com proveniência e referência ao artifact, necessária para reproduzir o score offline. O estado operacional também pode ser persistido em `standards_service_runs`.

CrUX History e Clarity continuam fora do scoring e não materializam regras SARI.

### `artifacts/observability/observability.db`

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

### Janela de reprocessamento de coletas live

Coletas externas classificadas como `LIVE_RECOLLECTION` podem ser reprocessadas dentro do mesmo `AUD-*` somente enquanto a observação permanecer temporalmente coerente. O limite é controlado por:

```text
RASAI_REPROCESS_LIVE_VALIDITY_MINUTES=1440
```

O runtime aceita valores entre 1 e 10080 minutos. O default de 1440 minutos representa 24 horas. Após o vencimento, uma nova coleta live não promove o AUD antigo a resultado final; deve ser criada uma nova auditoria para evitar mistura entre estados diferentes do site ou do provider. A configuração não altera evidências `REPLAY_SAFE`, que podem ser reanalisadas a partir dos dados persistidos da observação original.

Contrato completo: [`AUDIT_REPROCESSING.md`](AUDIT_REPROCESSING.md).

## Perfis de execução

Os perfis do console são overlays de sessão e não alteram automaticamente estas integrações.

Isso é intencional:

- `Completo seguro` não deve consumir a quota diária do Clarity apenas por ter sido selecionado;
- Common Crawl é governado pelo default/override da integração;
- CrUX History é credential-driven, independente da seleção de perfil;
- nenhuma integração muda termos SERP, IA, carga sintética ou análise profunda.

## Relatórios

### `cat-04.html`

Recebe resumo CrUX History por `target`, `scope`, `form factor`, métrica e período. Não mistura o histórico com Lighthouse lab ou Apdex.

### `cat-07.html`

Recebe painel **Observed Behavioral UX** do Clarity. O relatório declara que os agregados comportamentais complementam, mas não recalculam, o Apdex sintético.

### `cat-01.html`

Recebe histórico Common Crawl por URL: quantidade de capturas/collections e primeira/última captura observada.

### `report-catalog/cat-05.html` e `report-catalog/metrics.html`

Concentram a leitura de observabilidade aplicável à AUD, com datasets externos, métricas e proveniência persistida.

### `sari.html` e `methodology.html`

Exibem explicitamente o estado de `BR-GEO-060`, peso de 3% dentro de Discovery, impacto máximo de 0,45 ponto e a regra de que ausência/erro não penalizam o score.

### `report-catalog/cat-01.html`

Exibe o estado operacional dos serviços de padrões Web aplicáveis por meio de `standards_service_runs`.

## Falhas externas

O comportamento obrigatório para qualquer integração é:

```text
external provider/public API failure
        -> ERROR/PARTIAL/NO_DATA na integração
        -> website e score base preservados
```

Para Common Crawl especificamente:

```text
falha/no-data
        -> BR-GEO-060 não materializada
        -> nenhum FAIL
        -> nenhum zero
        -> nenhuma queda de Coverage/Confidence
```

Nunca:

```text
external provider/public API failure
        -> website FAIL
        -> SARI/SCORE reduzido
```
