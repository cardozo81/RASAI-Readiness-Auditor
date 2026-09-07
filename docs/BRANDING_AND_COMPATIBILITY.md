# RASAi / SARI — identidade e compatibilidade

## Identidade pública

- **Marca:** RASAi
- **Acrônimo formal:** RASAI
- **Fundamento do acrônimo:** Readiness Assessment for Search & AI
- **Descriptor:** Search & AI Readiness Auditor
- **Framework:** RASAi Framework
- **Índice:** Search & AI Readiness Index — `SARI-001`

## Fundamento da grafia RASAi

`RASAI` é a composição formal de **R**eadiness **A**ssessment for **S**earch & **AI**. A marca é apresentada como **RASAi**. O `i` minúsculo é uma decisão tipográfica para dar identidade ao trecho final associado à inteligência artificial e tornar a marca visualmente distinta, sem criar uma segunda expansão do acrônimo.

Convenção de escrita:

- use **RASAi** em UI, console, relatórios, HTML, README e documentação;
- use **RASAI** quando o texto estiver explicando o acrônimo formal;
- preserve identificadores técnicos cuja grafia em caixa alta faça parte do contrato, como `RASAI-OBS-*`;
- comandos e arquivos executáveis permanecem em minúsculas, por exemplo `rasai` e `rasai-console`.

## Superfície operacional

A página principal do índice é `report/readiness.html`.

Os comandos preferenciais são `rasai`, `rasai-console`, `rasai audit`, `rasai visibility`, `rasai monitoring`, `rasai quality` e `rasai scoring`.

Por compatibilidade operacional, também são aceitos:

- `searchgeo` e `searchgeo-console`;
- namespace Python `src/searchgeo/`;
- variáveis de ambiente `SEARCHGEO_*`;
- arquivos de configuração suportados pelo runtime;
- nome de distribuição Python `searchgeo-readiness-auditor`;
- IDs normativos e persistidos como `BR-GEO-*`, `SCORE-GEO-*` e `RASAI-OBS-*`.

Esses elementos são contratos técnicos e não definem a marca exibida ao usuário.

## SARI e scoring

`SARI-001` identifica o **Search & AI Readiness Index**. A versão do índice e o `scoring_version` são metadados distintos.

O método de scoring aplicado às auditorias é `SCORE-GEO-003`. Lighthouse, Core Web Vitals, Acessibilidade, Synthetic Navigation Apdex, Synthetic User Experience Apdex e Observed AI Visibility permanecem metodologias independentes e não são combinadas silenciosamente no SARI.
