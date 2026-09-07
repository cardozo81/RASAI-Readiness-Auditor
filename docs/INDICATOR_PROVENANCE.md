# Proveniência dos indicadores

Este documento define como o SearchGEO deve declarar a origem metodológica de cada indicador, cálculo, classificação e recomendação exibidos nos relatórios.

## Objetivo

O usuário do relatório deve conseguir distinguir, sem inferência própria:

- o que é observação coletada;
- o que deriva de standard externo;
- o que deriva de orientação oficial de uma plataforma;
- o que é métrica definida por terceiro;
- o que é heurística do SearchGEO;
- o que é telemetria operacional;
- o que foi produzido por IA e exige revisão humana.

Uma referência externa não deve ser usada para sugerir homologação do produto inteiro. A fonte valida somente o fenômeno ou regra no escopo documentado.

## Taxonomia obrigatória

| Identificador | Rótulo para o usuário | Uso |
|---|---|---|
| `RAW_OBSERVATION` | Observação coletada | dado bruto ou diretamente observado, sem transformação normativa |
| `EXTERNAL_STANDARD` | Standard externo | especificação formal ou Recommendation aplicável ao fenômeno |
| `OFFICIAL_PLATFORM_GUIDANCE` | Orientação oficial de plataforma | regra, política ou orientação publicada pelo mantenedor da plataforma |
| `EXTERNAL_DEFINED_METRIC` | Métrica externa definida | fórmula, score, threshold ou curva definidos externamente |
| `SEARCHGEO_HEURISTIC` | Heurística SearchGEO | peso, threshold, classificação ou agregação definida internamente |
| `OPERATIONAL_TELEMETRY` | Telemetria operacional | tempo, chamadas, tokens, custo estimado, erros de integração e runtime |
| `AI_DERIVED_ADVISORY` | Análise/sugestão por IA | interpretação semântica ou texto proposto por LLM, sempre evidence-bound e advisory |

## Contrato obrigatório dos HTMLs

Cada página final do report deve informar a natureza metodológica dos indicadores centrais daquela tela.

A página `references.html` deve possuir uma seção consolidada **De onde vem cada indicador**, contendo no mínimo:

1. indicador/família;
2. classificação metodológica;
3. entidade/fonte;
4. link oficial quando existe fonte externa primária;
5. regra/fórmula externa aplicável;
6. parte específica implementada ou decidida pelo SearchGEO;
7. aviso quando a fonte não homologa o índice global.

As demais páginas devem mostrar um resumo compacto logo após o cabeçalho e um atalho para essa seção. Tooltip pode complementar a explicação, mas informação essencial não pode depender de hover.

## Página canônica por indicador

Para impedir dupla interpretação, cada família possui uma página analítica canônica:

| Família | Página |
|---|---|
| SearchGEO Readiness Index, dimensões, Coverage, Confidence, Consolidation | `searchgeo.html` |
| Evidências/findings Mobile | `mobile.html` |
| Evidências/findings Desktop | `desktop.html` |
| Core Web Vitals e Lighthouse Performance | `web-performance.html` |
| Lighthouse Accessibility e evidências automatizáveis WCAG | `accessibility.html` |
| Synthetic Navigation Apdex | `apdex.html` |
| Telemetria/custos de IA | `ai-usage.html` |

`index.html` é somente dashboard executivo. Pode resumir resultados finais, mas não deve republicar tabelas, percentis ou metodologia detalhada de uma página canônica.

## Inventário principal

### SearchGEO Readiness Index — SGRI-001

**Classificação:** `SEARCHGEO_HEURISTIC`.

Não existe score GEO/AEO 0–100 universal usado como fonte normativa desta saída. A média normalizada, fatores de resultado, pesos, agregação e faixas visuais são decisões versionadas do SearchGEO.

`SGRI-001` é a identidade pública da metodologia. Enquanto a fórmula não mudar, o banco continua registrando `SCORE-GEO-002` como versão do motor de cálculo persistido para preservar compatibilidade e comparabilidade histórica.

Essa mudança de nomenclatura não representa recalibração empírica.

Consulte também:

- `SEARCHGEO_READINESS_INDEX.md`;
- `SCORING_GUIDE.md`;
- `SCORING_VALIDATION.md`.

### Coverage / Confidence / Consolidation

**Classificação:** `SEARCHGEO_HEURISTIC`.

Coverage mede a parcela aplicável efetivamente avaliada. Os thresholds que produzem Confidence e Consolidation são internos, versionados e não representam thresholds oficiais de Google, OpenAI, Microsoft, W3C, NIST ou outra entidade.

Esses três indicadores aparecem analiticamente em `searchgeo.html` e não devem ser repetidos em `mobile.html`/`desktop.html`.

### BR-GEO-001..054

A natureza é individual por regra. Uma BR pode ser `OFFICIAL`, `STANDARD`, `HEURISTIC` ou executor interno de integridade. Quando existe referência primária aplicável, o relatório deve ligá-la à BR; a presença de uma fonte conceitual não promove automaticamente uma heurística a standard.

Consulte `RULES_GUIDE.md`.

### HTTP e redirects

**Classificação:** `EXTERNAL_STANDARD` para a semântica HTTP.

Fonte oficial: RFC 9110 — HTTP Semantics
https://www.rfc-editor.org/rfc/rfc9110.html

O SearchGEO adiciona regras próprias de materialidade, dependência e auditabilidade sobre a observação HTTP.

### robots.txt

**Classificação:** `EXTERNAL_STANDARD`.

Fonte oficial: RFC 9309 — Robots Exclusion Protocol
https://www.rfc-editor.org/rfc/rfc9309.html

Para comportamento específico do Google, o catálogo por regra também referencia a documentação oficial do Google Crawling Infrastructure.

### Core Web Vitals

**Classificação:** `EXTERNAL_DEFINED_METRIC`.

Fonte oficial: Chrome/web.dev — Web Vitals
https://web.dev/articles/vitals

LCP, INP e CLS de campo, avaliação no percentil 75 e thresholds recomendados são mantidos externamente. O SearchGEO preserva source/scope e não converte Core Web Vitals em `SGRI-001`.

### Lighthouse Performance

**Classificação:** `EXTERNAL_DEFINED_METRIC`.

Fonte oficial: Chrome for Developers — Performance scoring
https://developer.chrome.com/docs/lighthouse/performance/performance-scoring

Score, pesos e curvas pertencem ao Lighthouse e podem mudar entre versões. A versão materializada deve permanecer rastreável.

No dashboard, quando existem vários contextos, o SearchGEO deve preferir faixa/contextos válidos a inventar um único “Lighthouse do site”.

### Lighthouse Accessibility

**Classificação:** `EXTERNAL_DEFINED_METRIC`.

Fonte oficial: Chrome for Developers — Accessibility scoring
https://developer.chrome.com/docs/lighthouse/accessibility/scoring

O score automatizado do Lighthouse não é percentual de conformidade WCAG e não deve ser apresentado como certificação.

### WCAG 2.2

**Classificação:** `EXTERNAL_STANDARD`.

Fonte oficial: W3C Recommendation — WCAG 2.2
https://www.w3.org/TR/WCAG22/

O SearchGEO pode mapear falhas automatizáveis a critérios aplicáveis, mas uma avaliação automatizada não autoriza declarar conformidade integral WCAG.

### Synthetic Navigation Apdex

**Classificação:** `EXTERNAL_STANDARD` para fórmula, zonas e faixas qualitativas.

Fonte oficial: Apdex Technical Specification v1.1
https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf

A especificação define a fórmula, Satisfied/Tolerating/Frustrated, reporting qualitativo e tratamento de grupos com menos de 100 amostras. O threshold `T` é configurado pelo operador. Perfil Chromium, limites operacionais, delays e concorrência são configuração/implementação do SearchGEO e devem permanecer separados da parte normativa Apdex.

### E-E-A-T / YMYL / people-first

**Classificação:** `OFFICIAL_PLATFORM_GUIDANCE`.

Fonte oficial: Google Search Central — Creating helpful, reliable, people-first content
https://developers.google.com/search/docs/fundamentals/creating-helpful-content

O SearchGEO usa esses conceitos para contextualizar a análise semântica. Não produz `E-E-A-T Score` oficial nem transforma YMYL em probabilidade de ranking.

### Groundability

**Classificação atual:** conjunto de sinais SearchGEO; **não existe subscore próprio no SGRI-001**.

Nesta versão, o relatório destaca sem agregação adicional:

- Answerability;
- Citation Readiness;
- Evidence & Trust.

A ausência de média própria é deliberada: criar mais um número sem calibração aumentaria a camada heurística. Uma versão futura só deve criar subscore após fórmula, versionamento e validação próprios.

### Structured Data / JSON-LD

**Classificação:** `OFFICIAL_PLATFORM_GUIDANCE` para políticas do Google, com vocabulário Schema.org quando aplicável.

Fontes principais:

- https://developers.google.com/search/docs/appearance/structured-data/sd-policies
- https://schema.org/docs/documents.html

O SearchGEO deve preferir omissão a propriedades inventadas e não apresentar markup válido como garantia de rich result ou vantagem GEO.

### IA semântica e sugestões de conteúdo

**Classificação:** `AI_DERIVED_ADVISORY`.

Não existe homologação externa da conclusão produzida pelo LLM para uma página específica. O SearchGEO deve persistir provider, modelo, reasoning, evidências e contrato. Sugestões textuais exigem revisão humana e não alteram automaticamente scoring/findings.

### Tokens, duração e custo estimado de IA

**Classificação:** `OPERATIONAL_TELEMETRY`.

Esses valores descrevem execução do auditor, não qualidade do site. Tokens e duração podem vir do provider/runtime. Custo é estimativa local baseada em pricing conhecido/versionado quando disponível e não substitui invoice do provider.

## Regras de linguagem

Permitido:

> Core Web Vitals: métrica externa definida pelo programa Web Vitals; valor p75 coletado via CrUX.

> SGRI-001: índice heurístico interno, evidence-based e reprodutível do SearchGEO; motor persistido SCORE-GEO-002.

> WCAG 2.2: standard W3C; a automação cobre somente critérios tecnicamente verificáveis pela ferramenta.

Não permitido:

> SGRI oficial do Google/OpenAI.

> Lighthouse 96 = 96% de conformidade WCAG.

> E-E-A-T 87/100 segundo o Google.

> Apdex prova experiência real dos usuários quando a coleta foi sintética.

> Custo estimado de IA é o valor final faturado pelo provider.

> SGRI 85 significa 85% de chance de citação.

## Governança

Ao adicionar um novo indicador, o desenvolvimento deve atualizar simultaneamente:

1. implementação/coleta;
2. classificação metodológica;
3. fonte primária e link oficial quando existir;
4. página canônica do indicador;
5. documentação operacional;
6. `references.html`;
7. dashboard executivo quando houver resultado final legítimo para resumir;
8. testes que garantem que a classificação não desapareça do report e não seja duplicada em outra página analítica.

Referências externas deste catálogo foram revisadas em **2026-09-06**.
