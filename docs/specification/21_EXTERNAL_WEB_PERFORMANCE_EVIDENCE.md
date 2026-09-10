# Web Performance externo - Evidência Externa de Web Performance: Core Web Vitals + Lighthouse

**Estado:** IMPLEMENTADO
**Domínio:** `Web Performance externo`
**Dependências:** report site + configuração opcional PageSpeed/CrUX; IA não é dependência obrigatória
**Natureza:** evidência externa aditiva; sem impacto no scoring por padrão

## 1. Objetivo

O Web Performance externo adiciona à auditoria RASAi evidências de Web Performance fundamentadas em documentação externa oficial, sem remover, substituir ou recalibrar silenciosamente o `SCORE-GEO-004`.

Quando explicitamente habilitado, o recurso pode coletar:

- scores de laboratório do Lighthouse por meio da PageSpeed Insights API v5;
- categorias Performance, Accessibility, Best Practices, SEO e Agentic Browsing experimental;
- métricas de laboratório FCP, Speed Index, LCP, Total Blocking Time e CLS;
- Core Web Vitals de campo provenientes do CrUX quando disponíveis;
- LCP, INP e CLS no percentil 75 (`p75`);
- telemetria de cada chamada externa;
- payloads JSON brutos de respostas bem-sucedidas;
- log operacional persistente e sanitizado da auditoria.

O Web Performance externo responde a uma pergunta diferente daquela respondida pelo `SCORE-GEO-004`:

```text
SCORE-GEO-004
→ índice heurístico interno de prontidão baseado nas RuleExecutions do RASAi

Web Performance externo Lighthouse
→ medição e scores de laboratório definidos externamente

Web Performance externo CrUX / Core Web Vitals
→ experiência agregada de usuários reais em campo quando existe amostra CrUX suficiente
```

Essas saídas devem permanecer distinguíveis na persistência, no HTML, na CLI e na documentação.

## 2. Contrato não destrutivo de scoring

O Web Performance externo **não altera**:

- Business Rules;
- resultados de RuleExecution;
- Findings;
- Recommendations;
- prioridade;
- pesos das regras;
- `PASS = 1.00`, `WARNING = 0.50`, `FAIL = 0.00`;
- scores das dimensões;
- Coverage;
- Confidence;
- Consolidation;
- Overall Readiness;
- `scoring_version = SCORE-GEO-004`.

Nenhum valor de Lighthouse, PageSpeed ou Core Web Vitals é convertido automaticamente em contribuição para `SCORE-GEO-004`.

## 3. Fundamentação externa oficial

### 3.1 PageSpeed Insights API v5

Referências oficiais:

- <https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed>
- <https://developers.google.com/speed/docs/insights/v5/get-started>

O RASAi usa PageSpeed Insights para executar Lighthouse sobre a URL auditada. Categorias solicitadas por default pelo Web Performance externo:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

As cinco categorias são solicitadas na mesma chamada PageSpeed de cada contexto. `agentic-browsing` é tratada como categoria experimental; sua ausência isolada não transforma em falha as categorias estáveis válidas da mesma execução.

Referência primária do Agentic Browsing no Lighthouse:

- <https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js>

### 3.2 Chrome UX Report API

Referências oficiais:

- <https://developer.chrome.com/docs/crux/api/>
- <https://developer.chrome.com/docs/crux/guides/crux-api>

Endpoint direto utilizado:

```text
POST https://chromeuxreport.googleapis.com/v1/records:queryRecord
```

Métricas solicitadas:

```text
largest_contentful_paint
interaction_to_next_paint
cumulative_layout_shift
```

Mapeamento de dispositivo:

```text
RASAi MOBILE  → CrUX PHONE
RASAi DESKTOP → CrUX DESKTOP
```

### 3.3 Core Web Vitals

Referência oficial:

- <https://web.dev/articles/vitals>

Thresholds de boa experiência utilizados pela implementação:

```text
LCP <= 2500 ms
INP <= 200 ms
CLS <= 0.10
```

A avaliação usa valores p75 devolvidos pela fonte externa.

Estados da avaliação CWV por contexto:

```text
PASS
FAIL
INCOMPLETE
UNAVAILABLE
```

`INCOMPLETE` significa que existe field data utilizável, mas uma ou mais métricas requeridas não estão presentes. `UNAVAILABLE` significa ausência de field data utilizável. Nenhum dos dois estados representa automaticamente falha do website.

### 3.4 Lighthouse Performance

Referência oficial:

- <https://developer.chrome.com/docs/lighthouse/performance/performance-scoring>

Lighthouse Performance é score externo de 0 a 100. Pesos e curvas são mantidos pelo projeto Lighthouse e podem evoluir entre versões.

O RASAi persiste a versão Lighthouse retornada e nunca apresenta Lighthouse como `GEO Score`.

## 4. Ativação e política de rede

A coleta externa é **OFF por padrão**.

Controles:

```text
--web-performance
--no-web-performance
RASAI_WEB_PERFORMANCE
```

Precedência:

1. flag CLI explícita;
2. variável de ambiente;
3. `false`.

Quando desabilitado:

- nenhuma chamada PageSpeed;
- nenhuma chamada CrUX;
- nenhuma chamada LLM adicional;
- estado `DISABLED` persistido para rastreabilidade;
- `SCORE-GEO-004` continua normal.

## 5. Controles de consumo

### 5.1 Limite de páginas

```text
--web-performance-max-pages N
RASAI_WEB_PERFORMANCE_MAX_PAGES
```

Default:

```text
10
```

Regras:

- `N > 0`: primeiras N páginas auditadas, em ordem determinística;
- `0`: todas as páginas auditadas são elegíveis;
- o limite é aplicado a páginas lógicas;
- com `--device-context both`, cada página pode gerar uma chamada PageSpeed Mobile e uma Desktop.

### 5.2 Timeout

```text
--web-performance-timeout-seconds SECONDS
RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS
```

Default:

```text
120
```

O timeout vale por requisição externa. Não há retry automático após timeout, evitando consumo implícito duplicado quando o estado real da primeira chamada é desconhecido.

O valor de 120 segundos é default operacional, não garantia de que PageSpeed responderá nesse intervalo. Em sites ou condições de rede mais lentas, o operador pode elevar explicitamente o limite, por exemplo:

```powershell
--web-performance-timeout-seconds 180
```

Um timeout PageSpeed com CrUX bem-sucedido deve produzir estado Web Performance externo `PARTIAL`, preservando os dados CrUX obtidos.

### 5.3 Categorias Lighthouse

```text
--lighthouse-categories performance,accessibility,best-practices,seo,agentic-browsing
RASAI_LIGHTHOUSE_CATEGORIES=performance,accessibility,best-practices,seo,agentic-browsing
```

O default solicita as cinco categorias na mesma chamada PageSpeed por contexto. Agentic Browsing permanece experimental e não entra no `SARI-001`/`SCORE-GEO-004`.

## 6. Credenciais

### 6.1 PageSpeed

```text
RASAI_PAGESPEED_API_KEY
```

Opcional para PageSpeed conforme política/quota do serviço.

### 6.2 CrUX

```text
RASAI_CRUX_API_KEY
```

Obrigatória quando `--web-performance-field-source crux` é utilizado.

### 6.3 Isolamento

As credenciais Web Performance externo são independentes das credenciais dos providers de IA.

Chaves não podem ser:

- persistidas em SQLite;
- escritas nos artifacts de resposta;
- mostradas no HTML;
- registradas no log operacional;
- registradas como parte de URL com query string de credencial;
- reutilizadas como credencial de IA.

O log pode registrar apenas booleanos como `pagespeed_api_key_configured=true` e `crux_api_key_configured=true`.

## 7. Política de field data

Controle:

```text
--web-performance-field-source auto|pagespeed|crux|none
RASAI_WEB_PERFORMANCE_FIELD_SOURCE
```

Default: `auto`.

### `auto`

1. PageSpeed é chamado para Lighthouse;
2. se a resposta contiver field data CrUX utilizável, ele é usado;
3. se field data estiver ausente e houver chave CrUX, a API CrUX direta é chamada;
4. se nenhuma fonte produzir field data, o resultado permanece `UNAVAILABLE`/`INCOMPLETE` sem penalidade ao website.

### `pagespeed`

Usa somente field data presente na resposta PageSpeed. Não faz chamada CrUX direta.

### `crux`

Field data é obtido pela CrUX API direta. Exige `RASAI_CRUX_API_KEY`. PageSpeed continua sendo chamado para Lighthouse de laboratório.

### `none`

Desabilita field data. PageSpeed continua sendo usado para Lighthouse.

## 8. Política de IA

Web Performance externo adiciona **zero** chamadas a LLM.

Não chama provider de IA para produzir os scores Lighthouse/CrUX nem para alterar a medição-fonte.

Qualquer interpretação futura por IA deverá ser opt-in, contabilizada separadamente e incapaz de alterar medições-fonte ou `SCORE-GEO-004` sem novo contrato explicitamente aprovado.

## 9. Posicionamento e fail-open

Web Performance externo executa após o pipeline principal da auditoria e depois da materialização do report site.

Objetivos:

- não bloquear RuleExecution/scoring por indisponibilidade Google;
- preservar a auditoria principal se PageSpeed/CrUX falhar;
- manter a causa atribuída ao serviço externo, não ao website;
- permitir relatório parcial com evidência disponível.

Uma exceção operacional na camada Web Performance externo é capturada pela CLI, registrada quando possível e não invalida o resultado principal já concluído.

## 10. Semântica dos estados operacionais Web Performance externo

Estados:

```text
DISABLED
NO_CONTEXTS
SUCCESS
PARTIAL
UNAVAILABLE
```

### `DISABLED`

Web Performance externo não foi habilitado; nenhuma chamada externa foi feita.

### `NO_CONTEXTS`

Web Performance externo foi habilitado, mas não existia snapshot/dispositivo elegível para medição externa.

### `SUCCESS`

Todos os contextos selecionados possuem evidência externa útil e nenhum componente estável solicitado falhou naquele contexto. A ausência isolada de Agentic Browsing experimental não invalida `SUCCESS` quando as categorias estáveis requeridas e os demais componentes configurados são válidos.

### `PARTIAL`

Existe pelo menos um contexto com evidência útil, porém:

- um componente externo estável solicitado falhou; ou
- um contexto ficou sem evidência útil; ou
- houve timeout, erro HTTP ou indisponibilidade de uma das fontes enquanto outra fonte retornou resultado.

Exemplo normativo:

```text
PageSpeed Desktop → TIMEOUT
CrUX Desktop      → HTTP 200 + field data

contexto          → PARTIAL
execução Web Performance externo → PARTIAL
```

O fato de `successful_contexts == context_attempts` **não autoriza `SUCCESS`** se um ou mais contextos estiverem `PARTIAL`.

### `UNAVAILABLE`

Nenhum contexto selecionado produziu evidência externa útil.

`PARTIAL` e `UNAVAILABLE` qualificam a coleta; não reduzem `SCORE-GEO-004` e não criam Finding do website.

## 11. Persistência SQLite

Tabelas:

```text
web_performance_runs
web_performance_observations
web_performance_attempts
```

### `web_performance_runs`

Resumo da execução Web Performance externo, incluindo enabled, status, field source, page limit, páginas consideradas, contextos tentados, contextos com evidência útil, sucessos PageSpeed, sucessos CrUX, categorias e reason.

### `web_performance_observations`

Uma observação por snapshot/dispositivo selecionado, com:

- URL/device/strategy;
- status do contexto;
- versão/fetch time Lighthouse;
- `performance_score`;
- `accessibility_score`;
- `best_practices_score`;
- `seo_score`;
- `agentic_browsing_score` quando materializado;
- métricas lab;
- field source/scope;
- LCP/INP/CLS p75;
- assessments CWV;
- HTTP status;
- referências a artifacts;
- resumo sanitizado de erro.

### `web_performance_attempts`

Uma linha por chamada externa efetivamente tentada, com:

- serviço;
- URL auditada;
- device/snapshot;
- `SUCCESS`/`ERROR`;
- HTTP status quando existente;
- duração;
- error code/message sanitizados;
- referência de artifact quando existente.

## 12. Log operacional persistente

Cada auditoria mantém um log operacional independente de scoring e de evidência:

```text
audits/<AUD-ID>/logs/audit.log
```

Formato: **JSON Lines (JSONL)**, uma ocorrência por linha.

Eventos produzidos devem permitir rastrear o ciclo de vida da auditoria e da coleta Web Performance, incluindo início, tentativa externa, conclusão, geração do report e falha de runtime quando aplicável.

Para Web Performance externo, o log deve permitir diagnosticar:

- PageSpeed versus CrUX;
- Mobile versus Desktop;
- sucesso versus erro;
- HTTP status quando disponível;
- duração;
- timeout/error code sanitizado;
- artifact produzido;
- status agregado final.

O log é **fail-open**: falha de escrita do próprio log não pode mudar o resultado da auditoria.

O log nunca pode conter API keys, Authorization headers, tokens, passwords, credentials ou request URLs com chave.

## 13. Artefatos brutos

Respostas externas bem-sucedidas são gravadas em:

```text
artifacts/web-performance/
```

Exemplos:

```text
WPE-....pagespeed.json
WPE-....crux.json
```

Nenhuma nova chamada externa é necessária para reabrir os resultados persistidos.

## 14. Contrato HTML

Web Performance externo materializa:

```text
report/web-performance.html
```

A página deve distinguir visivelmente:

1. as categorias Lighthouse de laboratório, incluindo Agentic Browsing como experimental;
2. CrUX/Core Web Vitals de campo;
3. source e URL/origin scope;
4. indisponibilidade/incompletude;
5. telemetria das tentativas externas;
6. política de consumo/credenciais;
7. separação explícita de `SCORE-GEO-004`.

`report/index.html` pode mostrar resumo Web Performance externo, incluindo Performance, Accessibility, Best Practices, SEO técnico e Agentic Browsing experimental, mas nunca recalcular Overall Readiness.

`report/references.html` deve manter referências às fontes externas utilizadas.

A navegação do report site segue o core canônico compartilhado do projeto e não deve ser montada independentemente pelo Web Performance externo.

## 15. Saída CLI

Quando Web Performance externo estiver habilitado, o encerramento da CLI deve expor no mínimo:

- status agregado Web Performance externo;
- páginas consideradas;
- contextos com evidência útil / contextos tentados;
- sucessos/tentativas PageSpeed;
- sucessos/tentativas CrUX.

Quando o status for `PARTIAL`, a CLI deve avisar que houve falha ou indisponibilidade de componente externo e indicar o relatório/log operacional como fonte de diagnóstico.

Ao existir, o caminho de `logs/audit.log` deve ser apresentado ao operador.

## 16. Segurança e privacidade

Web Performance externo não persiste:

- API keys;
- Authorization headers;
- cookies do website auditado para serviços Google;
- request URLs contendo chaves;
- secrets do ambiente local.

Somente URL alvo, resposta externa permitida, telemetria sanitizada, métricas derivadas e indicadores booleanos de configuração são persistidos/logados.

## 17. Comportamento com o recurso desabilitado

Com:

```text
RASAI_WEB_PERFORMANCE=false
```

não existem chamadas PageSpeed/CrUX.

O log operacional pode ser criado independentemente do Web Performance externo para rastrear o ciclo de vida da auditoria, sem introduzir serviço externo e sem alterar scoring.

Com Web Performance externo desabilitado, os demais comandos continuam válidos e `SCORE-GEO-004` permanece como contrato vigente de scoring.

## 18. Critérios mínimos de aceitação

A implementação Web Performance externo deve provar por regressão que:

1. default OFF faz zero chamadas PageSpeed/CrUX;
2. run desabilitada é persistida;
3. PageSpeed bem-sucedido persiste Lighthouse;
4. as cinco categorias Lighthouse configuradas são solicitadas na mesma chamada por contexto;
5. Agentic Browsing é persistido separadamente quando materializado e sua ausência isolada não degrada categorias estáveis válidas;
6. field data persistido mantém source/scope;
7. CrUX direto funciona no modo `crux`/fallback aplicável;
8. Mobile→PHONE e Desktop→DESKTOP são determinísticos;
9. métrica CWV ausente produz `INCOMPLETE`, não website FAIL;
10. ausência de field data não altera scoring;
11. resposta externa bem-sucedida gera artifact bruto;
12. credenciais não aparecem no SQLite, HTML ou log;
13. `web-performance.html` explica separação metodológica;
14. menu final continua canônico em todas as páginas;
15. **PageSpeed timeout + CrUX success produz observação `PARTIAL` e run Web Performance externo `PARTIAL`;**
16. `successful_contexts == context_attempts` não mascara componente externo falho;
17. log operacional registra eventos Web Performance externo sem secrets;
18. falha de escrita do log não invalida a auditoria principal;
19. CLI mostra contadores por serviço e caminho do log;
20. `SCORE-GEO-004` não é removido nem recalculado por esta camada.

## 19. Evolução futura de scoring

Web Performance externo continua sendo camada de evidência e possível insumo de estudos empíricos. Não é `SCORE-GEO-004`.

Qualquer futura incorporação quantitativa de Web Performance ao scoring exige decisão humana explícita, novo contrato/versionamento de scoring e protocolo de validação.
