# Modelo de progresso e ordenação de chamadas externas

## Objetivo

O console interativo apresenta duas medidas distintas durante uma execução:

- **andamento da etapa atual**: percentual medido somente quando existe uma unidade real contável, como `URL × device`, amostras sintéticas ou suboperações de uma integração;
- **progresso do pipeline**: projeção da posição no trabalho total planejado, ponderada pela carga configurada e pela carga efetivamente observada durante a execução.

O percentual geral **não é uma previsão de tempo restante**. Ele existe para evitar a distorção de tratar uma operação local de milissegundos e uma navegação Lighthouse/API de dezenas de segundos como fases de mesmo tamanho.

## Ponderação da execução

A projeção geral atribui mais peso a operações que normalmente dominam o tempo de parede:

- navegação/renderização Chromium por `URL × device`;
- análise por IA quando habilitada;
- PageSpeed/Lighthouse remoto por contexto;
- Synthetic User Experience Apdex conforme páginas e amostras;
- Synthetic Navigation Apdex conforme páginas, devices e amostras;
- Search Console quando efetivamente configurado;
- CrUX History e Microsoft Clarity quando efetivamente habilitados;
- Common Crawl na etapa de scoring, pois a corroboração `BR-GEO-060` é coletada antes do score e não é repetida depois;
- Search Intelligence conforme o número de termos.

Inicialização, scoring local, persistência e outras operações rápidas recebem peso menor.

Quando o número real de páginas/snapshots passa a estar disponível no `audit.db`, a projeção usa essa carga observada em vez de continuar supondo apenas a configuração máxima. Por isso o percentual global pode ajustar-se durante a execução; ele só chega a **100%** após a conclusão terminal.

## Informação exibida

Durante a execução, o console mantém:

```text
Operação    : operação técnica atualmente em andamento
Etapa       : fase funcional atual
Andamento   : percentual da etapa, quando medido
Executando  : descrição objetiva do trabalho em curso
Barra etapa : barra correspondente ao percentual medido da etapa
Pipeline    : barra e percentual geral projetado
```

Exemplos de operações:

```text
BROWSER:CHROMIUM_RENDER
LOCAL:DOM_EXTRACTION
LOCAL:DETERMINISTIC_RULES
API:<provider>
LOCAL:SARI_SCORE
API:PAGESPEED_INSIGHTS
API:GOOGLE_SEARCH_CONSOLE
API:CRUX_HISTORY
API:MICROSOFT_CLARITY
API:COMMON_CRAWL
API:SERP
```

Operações locais muito rápidas podem ocorrer entre duas atualizações visuais do terminal. Mesmo assim, seus marcos de início/fim são registrados no log operacional, preservando a sequência real da execução sem aumentar frequência de rede.

## Ordem obrigatória de coleta e APIs

O contrato de execução é **evidence-first**.

### Core da página

A ordem canônica é:

```text
descoberta / HTTP
→ navegação e renderização Chromium de todos os contextos selecionados
→ persistência dos snapshots
→ extração DOM/conteúdo/metadados/dados estruturados
→ regras determinísticas e análise JavaScript/SPA
→ consolidação da extração
→ análise semântica/IA
→ comparação de contextos
→ crawling/discovery e IA técnica opcional
→ integridade de evidências
→ SARI / Coverage / Confidence
→ recomendações
→ remediação por IA opcional
→ relatórios
```

A análise semântica não pode iniciar antes de concluídas a renderização e as etapas locais que formam seu contexto. A IA técnica opcional só pode executar após a comparação dos contextos. A remediação de conteúdo por IA só pode executar depois do scoring e da priorização de recomendações.

O runtime aplica um **gate de evidência** antes dessas chamadas. Uma violação de ordem bloqueia a chamada do provider e registra `API_EVIDENCE_GATE_BLOCKED`.

### Web Performance externo

PageSpeed e CrUX atual executam somente depois que o `run_audit` principal terminou e a evidência core foi persistida.

- PageSpeed/Lighthouse realiza uma navegação externa independente porque esse comportamento faz parte do contrato da própria métrica;
- CrUX é consulta de dados e não navega novamente no alvo;
- a observação do progresso não adiciona chamadas, retries ou polling externo.

### Finalização observacional

CrUX History e Microsoft Clarity só podem executar quando:

1. o audit está `COMPLETED`;
2. o `completion_status` é `COMPLETE` ou `COMPLETE_WITH_LIMITATIONS`;
3. havendo páginas auditadas, existe pelo menos um snapshot de browser persistido.

Se essas condições não forem verdadeiras, o runtime registra `EXTERNAL_OBSERVABILITY_EVIDENCE_GATE_BLOCKED` e **não chama a API externa**.

Common Crawl segue um contrato diferente porque pode contribuir positivamente para `BR-GEO-060`: sua consulta bounded ocorre antes do scoring, mas somente depois da renderização, extração, comparação e integridade das evidências necessárias. A coleta não é repetida na finalização.

Google Search Console permanece na finalização pós-audit e mantém progresso por Sitemaps, URL Inspection e Search Analytics.

Search Intelligence/SERP é pós-audit. Improvement Intelligence permanece terminal e usa apenas a evidência já materializada.

## Eventos operacionais

O progresso usa os eventos já existentes e acrescenta marcos secret-safe:

```text
AUDIT_PIPELINE_STEP_STARTED
AUDIT_PIPELINE_STEP_FINISHED
AUDIT_PIPELINE_AUX_STARTED
AUDIT_PIPELINE_AUX_FINISHED
API_EVIDENCE_GATE_BLOCKED
EXTERNAL_OBSERVABILITY_COLLECTION_STARTED
EXTERNAL_OBSERVABILITY_OPERATION_STARTED
EXTERNAL_OBSERVABILITY_OPERATION_FINISHED
EXTERNAL_OBSERVABILITY_COLLECTION_FINISHED
EXTERNAL_OBSERVABILITY_EVIDENCE_GATE_BLOCKED
```

Esses eventos não armazenam keys/tokens e não alteram scoring.

## Limites

Nenhum modelo de percentual consegue antecipar precisamente latência de rede, fila de provider, CDN, WAF ou tempo de resposta de uma IA. Por isso:

- **percentual da etapa** é marcado como medido apenas quando há contador real;
- **percentual geral** permanece identificado como projeção enquanto a execução estiver aberta;
- timeouts/deadlines são mostrados como limites operacionais, não como estimativa de conclusão;
- o relógio total mede tempo real de parede até a última etapa habilitada.
