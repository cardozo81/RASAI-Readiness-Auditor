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
- use **Search & AI Readiness** para o domínio funcional do produto; `Search/GEO` não é nomenclatura pública atual;
- preserve `GEO` apenas quando fizer parte de conceito explicitamente discutido, identificador normativo/histórico ou contrato persistido, como `BR-GEO-*` e `SCORE-GEO-*`;
- preserve identificadores técnicos cuja grafia em caixa alta faça parte do contrato, como `RASAI-OBS-*`;
- comandos e arquivos executáveis permanecem em minúsculas, por exemplo `rasai` e `rasai-console`.

## Superfície operacional

A página principal do índice é `report/readiness.html`.

Os comandos preferenciais são `rasai`, `rasai-console`, `rasai audit`, `rasai visibility`, `rasai monitor`, `rasai observe`, `rasai quality`, `rasai platform` e `rasai scoring`.

O arquivo canônico de configuração não secreta do console interativo é `rasai-console.ini`. Na primeira execução após a atualização, se `rasai-console.ini` ainda não existir e houver um `searchgeo-console.ini` legado no diretório de trabalho, o entrypoint público renomeia esse arquivo automaticamente para `rasai-console.ini`, preservando seu conteúdo. Se a variável `SEARCHGEO_CONSOLE_INI` estiver explicitamente configurada, seu caminho continua prevalecendo e nenhuma migração automática é feita. Se os dois arquivos existirem, `rasai-console.ini` prevalece e o arquivo legado não é apagado automaticamente, evitando perda de configurações divergentes.

O diretório oculto canônico de estado/runtime local é `.rasai`. Ele abriga sidecars e caches operacionais, por exemplo `audits/.rasai/platform.db`, `audits/.rasai/consolidated-index.db` e `.rasai/scoring/score-geo-003-model.json`. Quando somente `.searchgeo` legado existe, o runtime tenta migrá-lo para `.rasai` antes de abrir esses artifacts. Se os dois diretórios existirem, `.rasai` é autoritativo e somente entradas ausentes são movidas; conflitos são preservados no legado para evitar sobrescrita/perda de dados.

Por compatibilidade operacional, também são aceitos:

- `searchgeo` e `searchgeo-console`;
- namespace Python `src/searchgeo/`;
- variáveis de ambiente `SEARCHGEO_*`;
- `searchgeo-console.ini` somente como entrada de migração do nome legado quando não houver arquivo canônico nem override explícito;
- `.searchgeo` somente como fonte de migração de estado/runtime legado; novas gravações canônicas usam `.rasai`;
- outros arquivos de configuração suportados pelo runtime;
- nome de distribuição Python `searchgeo-readiness-auditor`;
- IDs normativos e persistidos como `BR-GEO-*`, `SCORE-GEO-*` e `RASAI-OBS-*`.

Esses elementos são contratos técnicos e não definem a marca exibida ao usuário.

## SARI e scoring

`SARI-001` identifica o **Search & AI Readiness Index**. A versão do índice e o `scoring_version` são metadados distintos.

O método de scoring aplicado às auditorias é `SCORE-GEO-003`. Lighthouse, Core Web Vitals, Acessibilidade, Synthetic Navigation Apdex, Synthetic User Experience Apdex e Observed AI Visibility permanecem metodologias independentes e não são combinadas silenciosamente no SARI.
