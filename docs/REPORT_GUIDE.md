# Guia de leitura dos relatórios

O RASAi mantém HTML como projeção de leitura sobre dados persistidos; HTML não recalcula scoring, não inventa dado ausente e não substitui `audit.db` + artifacts como fonte de verdade.

## Entrada principal da auditoria

```text
report-catalog/index.html
```

`<AUD>/report/`, `<AUD>/report.html` e `<AUD>/remediation.html` não pertencem ao contrato HTML de uma execução `rasai audit`.

## Estrutura suportada

A projeção audit-owned suportada é `report-catalog/`. Ela preserva:

- visão geral e SARI;
- CAT-01 ... CAT-10 conforme contrato da auditoria;
- captura/contexto;
- evidências da execução;
- IA e integrações;
- metodologia/scoring;
- índices e métricas;
- manifest e assets próprios.

O catálogo é read-only sobre a evidência final. Sua materialização não deve disparar collector, API, provider, IA, SERP, scoring ou workload sintético.

## Dados funcionais independentes da projeção HTML

A remoção do HTML convencional não remove ou reduz:

- `findings`, `evidence` e `recommendations`;
- `root_cause_analyses`;
- `root_cause_precision`;
- scores e contribuições;
- resultados de Search Intelligence, GSC, Clarity, Web Performance, W3C, Apdex e demais integrações;
- telemetria, custo e provenance de IA;
- estados de fulfillment e reprocessamento.

Esses dados continuam disponíveis ao `report-catalog/` e a outras capacidades que os consumam.

## Saídas fora do report da AUD

Relatórios standalone, como monitoring, verification, timelines, históricos e consolidações, possuem contratos próprios e ficam fora da projeção audit-owned de `report-catalog/`.

## SARI-001 / SCORE-GEO-004

```text
SARI-001       = Search & AI Readiness Index público
SCORE-GEO-004  = motor vigente para novas auditorias
```

`readiness.html` apresenta dimensões, Coverage, Confidence, Consolidation, Overall e limitações. `scoring.html` apresenta a versão efetivamente usada, pesos, grupos, gates, rastreabilidade e interpretação do Overall.

O Overall vigente usa agregação hierárquica ponderada (`HIERARCHICAL_WEIGHTED_READINESS_V1`), não média simples de igual peso entre todas as dimensões.

SARI-001 é metodologia proprietária, evidence-bound e reprodutível. Não representa nota oficial de Google, Bing ou OpenAI, nem probabilidade de ranking/citação ou certificação GEO/AEO.

## Propriedade analítica das páginas

| Domínio | Página canônica | Natureza |
|---|---|---|
| visão executiva | `index.html` | síntese de dados persistidos |
| SARI-001 / dimensões | `readiness.html` | readiness proprietário |
| metodologia de scoring | `scoring.html` | contrato vigente `SCORE-GEO-004` |
| contexto de captura | `context.html` | escopo URL/device, variância de documento e runtime; read-only |
| Evidências da execução | `execution-evidence.html` | matriz do que foi solicitado/executado, estado, falhas e configuração faltante; sem recalcular scoring |
| Mobile | `mobile.html` | evidências/findings do contexto Mobile quando disponíveis |
| Desktop | `desktop.html` | evidências/findings do contexto Desktop quando disponíveis |
| Domínio e descoberta | `crawling-discovery.html` | superfície canônica de `ORIGIN`: robots, sitemaps, llms.txt e controles de crawler |
| Acessibilidade automatizada | `accessibility.html` | diagnóstico; não certificação WCAG |
| Core Web Vitals / Lighthouse | `web-performance.html` | lab + field data separados |
| Métricas e padrões | `standards.html` | W3C HTML/CSS, MDN Observatory, WebDX/Baseline e métricas derivadas quando disponíveis; advisory |
| Search Intelligence | `search-intelligence.html` | SERP observado e análise competitiva; non-scoring |
| Synthetic Navigation Apdex | `apdex.html` | sintético quando executado |
| Synthetic User Experience Apdex | `apdex-experience.html` | sintético calibrável quando executado; não RUM |
| Uso/custo de IA | `ai-usage.html` | telemetria operacional |
| Improvement Intelligence | `improvement-intelligence.html` | análise profunda advisory/evidence-bound de uma URL; non-scoring |
| Conteúdo e JSON-LD | `content-suggestions.html` | remediação advisory |
| Remediações | `remediation.html` | plano evidence-bound |
| Observed Generative Visibility | `ai-visibility.html` | outcome observado/importado quando disponível |
| Search & AI Observability | `observability.html` | outcomes externos e diagnósticos derivados quando disponíveis |
| Quality & decisão | `quality.html` | qualidade da evidência/priorização operacional quando processada |
| Referências | `references.html` | metodologia e proveniência |

`index.html` pode repetir sínteses necessárias à leitura executiva, mas não funde domínios complementares em um score comum.

## Escopo de captura e não duplicação

O contrato `CONTEXT-SCOPE-001` separa quatro níveis:

```text
ORIGIN
URL
DEVICE_SNAPSHOT
PROFILE_MEASUREMENT
```

`robots.txt`, sitemaps, `llms.txt` e demais fatos globais pertencem a `ORIGIN`. Eles são apresentados detalhadamente em **Domínio e descoberta** e não devem ser replicados por URL em Mobile, Desktop ou `context.html`.

HTTP/HTML bruto e redirects pertencem à URL. DOM renderizado, erros JavaScript/runtime e Lighthouse pertencem ao snapshot/dispositivo. Apdex pertence ao perfil sintético executado.

`context.html` existe para mostrar essa topologia, comparar documentos recebidos por Mobile/Desktop e apresentar erros de runtime por snapshot. Ele não recalcula score e não realiza nova chamada de rede ou IA.

## Múltiplas URLs

Com uma única URL, o layout permanece simples e linear.

Quando uma coleção de resultados possui **duas ou mais URLs distintas**, a camada comum de apresentação oferece, conforme aplicável:

- filtro por URL;
- filtro Mobile/Desktop quando ambos estiverem presentes;
- busca textual;
- quantidade de itens por página;
- paginação local.

Um item pode representar mais de uma URL, como uma remediação agrupada. Nesse caso todas as URLs presentes no item são indexadas para o filtro.

Os filtros são client-side e não removem evidência do HTML gerado. A impressão continua podendo expor a coleção completa.

Improvement Intelligence é uma exceção operacional deliberada: a análise profunda só executa quando existe exatamente uma URL de entrada explícita. O crawler pode coletar páginas auxiliares, mas o estudo profundo não mistura URLs alvo distintas no mesmo contexto de IA.

## Configuração versus resultado obtido

O report deve distinguir estados de execução, por exemplo:

```text
não solicitado
configurado
desabilitado
sem dados
executado
success
partial
unavailable
error
```

Timeout, quota, HTTP, falta de artifact ou ausência de dado da fonte não são convertidos em problema do website.

Essa distinção se aplica a **todas** as superfícies canônicas. Uma página pode existir estruturalmente e ainda indicar que a capacidade correspondente não foi solicitada, não estava configurada, não era aplicável ou não retornou dado. A presença do arquivo nunca deve ser usada como prova de que uma coleta, provider ou IA ocorreu.

## Domínio e descoberta

`crawling-discovery.html` concentra robots/crawler policy, sitemaps, feeds, `llms.txt` experimental e evidências correlatas no escopo `ORIGIN`. Quando artifacts textuais foram efetivamente capturados, o relatório pode exibir uma pré-visualização read-only sem fazer nova requisição de rede.

O peso direto de `llms.txt` no `SARI-001` é `0`: presença, ausência ou erro não alteram `SCORE-GEO-004`. O arquivo permanece um sinal experimental/advisory, não um requisito normativo de Search ou de sistemas generativos.

Diagnósticos auxiliares permanecem advisory. Quando IA técnica estiver habilitada e produzir avaliação evidence-bound válida de robots/sitemap, somente a classe bounded do mesmo recurso pode compartilhar o grupo de scoring correspondente, com fatores estáticos e sem bônus duplicado.

## Acessibilidade

`accessibility.html` apresenta automação/evidência disponível ou estado explícito de indisponibilidade/desabilitação. Lighthouse accessibility não equivale a certificação WCAG integral.

A página não altera `SCORE-GEO-004`.

## Web Performance

`web-performance.html` mantém Lighthouse lab e CrUX field separados. A página é materializada mesmo quando a coleta externa está desabilitada, justamente para deixar esse estado inequívoco.

Mobile e Desktop permanecem observações distintas. O relatório não cria média única automática entre os dois contextos.

Synthetic Apdex não é derivado de LCP, INP, CLS, FCP ou TBT. Web Performance não altera automaticamente SARI/SCORE.

## Métricas e padrões

`standards.html` é a superfície canônica de serviços e métricas complementares de padrões. Pode consolidar W3C Nu HTML Checker, W3C CSS Validator, MDN HTTP Observatory, Web Platform Baseline/WebDX e métricas derivadas quando cada capacidade estiver disponível.

A página sempre existe no mini-site final, mas sua existência não habilita serviços. Se uma integração estiver desabilitada, não configurada ou sem dado, o estado deve ser apresentado explicitamente. Em especial, Web Platform Baseline usa o dataset WebDX versionado congelado no próprio `AUD-*` e materializa somente features vinculadas a sinais diretamente observáveis nos artifacts persistidos. A presença de `RASAI_WEB_FEATURES_DATASET` não fabrica classificação: assets externos não são refeitos apenas para WebDX e ausência de sinal mapeável permanece `NO_DATA`, não falha do website.

Esses sinais permanecem complementares/advisory, salvo quando existir mapeamento explícito de evidência para uma regra já contratada; não são um segundo score de readiness.

## Synthetic Navigation Apdex

`apdex.html` existe sempre como superfície canônica. Quando Synthetic Navigation Apdex foi habilitado e persistido, apresenta T/4T, classificação Satisfied/Tolerating/Frustrated, amostras, exclusões, perfil operacional e limitações. Quando não foi executado, apresenta estado neutro e não dispara navegações apenas para preencher o HTML.

É sintético, não RUM e não altera `SCORE-GEO-004`.

## Synthetic User Experience Apdex

`apdex-experience.html` existe sempre como superfície canônica. Quando a execução correspondente foi habilitada e persistida, apresenta a população sintética e continua sintético mesmo quando calibrado a partir de configuração Dynatrace. Quando não foi executado, apresenta estado neutro.

O mix Mobile/Desktop/Tablet distribui percentualmente a população de amostras/user actions e deve somar 100%. Ele não representa diretamente o número de requests HTTP de subrecursos, pois uma única amostra pode disparar vários requests.

## Improvement Intelligence

`improvement-intelligence.html` é audit-owned e sempre deve existir após uma auditoria bem-sucedida. Quando a análise profunda não foi solicitada, a página registra explicitamente esse estado sem disparar IA adicional apenas para produzir HTML.

Quando habilitada, a feature exige uma URL explícita e uma **IA principal apta** na execução. Provider, modelo e reasoning pertencem à seleção principal da auditoria e não são configurados novamente para Improvement Intelligence. A seleção principal pode ser um provider explícito ou `AUTO`; em `AUTO`, a análise profunda reutiliza o mesmo coordenador central de custo, elegibilidade, quarentena, circuit breaker e fallback. Credenciais continuam fora do INI e do payload persistente.

A análise pode correlacionar:

- findings, RuleExecutions e Evidences persistidos;
- HTML bruto/renderizado, headings, landmarks e estrutura semântica;
- Lighthouse/PageSpeed e Core Web Vitals quando já coletado;
- SERP/Search Intelligence competitivo quando já observado;
- robots, sitemap, `llms.txt` e arquivos de discovery;
- headers/cookies observados para postura de segurança passiva;
- acessibilidade, performance e best practices como sinais complementares.

O output separa finding observado de recomendação gerada por IA, pode mostrar HTML original versus HTML sugerido e prioriza ações por impacto potencial, confiança e esforço. Segurança é somente passiva: ausência de header ou configuração é postura observada, não prova automática de vulnerabilidade explorável; não há pentest ativo, fuzzing ou exploração.

Search/SERP é contexto observacional e não sustenta promessa causal de ranking. Nenhuma recomendação altera `SARI-001`, `SCORE-GEO-004`, Coverage, Confidence ou gates. O ganho efetivo só pode ser afirmado depois de deploy e nova auditoria/before-after.

Detalhes: [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md).

## Conteúdo e JSON-LD

`content-suggestions.html` é audit-owned e sempre deve existir após uma auditoria bem-sucedida. Quando remediação por IA estiver desabilitada ou indisponível, o relatório registra esse estado sem fabricar uma sugestão.

Quando existe `structured_data.json` persistido, a página pode oferecer visualização segura do JSON-LD observado e referência ao artifact completo. O conteúdo observado deve permanecer visualmente separado de qualquer baseline ou sugestão.

Nenhuma proposta textual/JSON-LD vira fato observado ou alteração automática do website.

## Remediação

`remediation.html` preserva a diferença entre evidence, finding/conclusão, selector/local quando confiável e receita de correção. Selector não deve ser inventado para findings document/set-level.

Aplicar uma recomendação exige nova auditoria para medir novo estado; o report não muta a página alvo.

## Uso de IA

`ai-usage.html` é audit-owned e sempre deve existir. Quando não houve IA, a página representa esse estado. Quando houve chamadas, deve preservar provider/modelo, tentativa/status, tokens, reasoning configurado quando disponível e custo estimado.

Custo é estimativa operacional, não invoice nem sinal de qualidade. A página não cria chamadas adicionais de IA.

Tentativas da análise profunda usam `semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001`, o que permite separar o custo de Improvement Intelligence das demais finalidades de IA sem criar uma segunda telemetria paralela.

A política de eficiência prioriza uma chamada estruturada por snapshot para o conjunto contratado de regras semânticas, em vez de uma chamada por regra, e evita repetir análise de recursos globais somente porque existem dois dispositivos.

## Observed Generative Visibility

`ai-visibility.html` é uma superfície canônica e permanece separada de readiness:

```text
Readiness
= condições inferidas/evidence-bound da auditoria

Observed Generative Visibility
= outcomes observados/importados sob fonte e protocolo declarados
```

Pode mostrar métricas reportadas pela fonte, atividade de URLs, grounding queries, trends e controlled query-runs quando houver observação. Na ausência de dataset/import, a página mostra estado neutro; ausência de observação não vira score zero artificial. Observed Generative Visibility não altera `SARI-001/SCORE-GEO-004`.

## Search Intelligence

`search-intelligence.html` é uma superfície canônica point-in-time. Pode conter SERP Observation, posição observada, candidatos competitivos, comparação determinística de conteúdo e análise semântica evidence-bound quando explicitamente executada.

Sem termos, provider SERP ou observações persistidas, a página permanece disponível em estado neutro. O RASAi não inventa termos nem dispara Search para preencher HTML.

Quando Competitive AI é solicitada, ela usa a seleção principal de IA da execução; não existe provider de IA específico de Search no contrato vigente.

Ela permanece non-scoring. `NOT_FOUND_WITHIN_DEPTH` não deve ser transformado em posição numérica artificial.

Comparações históricas Search Intelligence pertencem ao par de AUDs e podem ser materializadas em saída standalone, preservando identidade de query, engine, mercado, idioma, device, profundidade e provider/data mode.

## Search & AI Observability

`observability.html` é a superfície canônica dos dados externos pós-auditoria. O sidecar atual é `RASAI-OBS-002`.

Pode conter Search Console, Search Appearance, properties/sitemaps, URL Inspection, CrUX History, imports generativos, publisher controls e diagnósticos derivados. Cada linha observacional pertence ao seu dataset e provenance. Sem sidecar/dados observacionais, a página apresenta estado neutro.

Leitura correta:

- canonical local diferente do selected canonical externo é divergência observada, não prova automática de perda;
- múltiplas URLs para uma query são candidato de cannibalization, não erro comprovado;
- ausência de dado externo é limitação/suficiência, não aprovação nem falha;
- correlação temporal não é causalidade;
- métrica inexistente na fonte não é fabricada.

## Quality & decisão

`quality.html` é uma superfície canônica e responde, quando processada, se a evidência RASAi está adequada para apoiar decisão. Pode expor Audit Health, Evidence Confidence, Operational Priority, Coverage Map, controles de conteúdo e Recommendation Validation. Sem processamento especializado, a página permanece disponível em estado neutro.

Quality não cria um novo readiness score e não altera Severity nem `SCORE-GEO-004`.

## Monitoring, Verification e Timeline

Comparações entre auditorias são superfícies standalone e read-only sobre os AUDs fonte. Exemplos:

```text
audits/monitoring/MON-*/report.html
audits/verification/VER-*/report.html
audits/quality/TIMELINE-*/report.html
```

Comparabilidade deve considerar `scoring_version`, device e universo de URL quando aplicável. Mudança temporal ou proximidade de um deployment não prova causalidade de Search/AI.

Improvement Intelligence produz hipótese priorizada. A comprovação de efeito pertence à comparação entre auditorias e deve preservar metodologia, URL/device e demais condições de comparabilidade.

## Consistência visual e navegação

Todas as páginas canônicas devem compartilhar navegação estável, apenas um item ativo, layout responsivo, tabelas legíveis e footer coerente.

Após a finalização de uma auditoria, o menu é estruturalmente estático e deriva do catálogo canônico; habilitar ou desabilitar uma funcionalidade altera o **conteúdo/estado da página**, não a existência do link.

A navegação é agrupada em submenus:

```text
Visão e readiness
  Visão geral
  Readiness SARI
  Metodologia de scoring

Coleta e dispositivos
  Contexto de captura
  Domínio e descoberta
  Relatório Mobile
  Relatório Desktop
  Acessibilidade
  Web Performance
  Métricas e padrões
  Apdex de navegação
  Apdex de experiência

Search e IA
  Search Intelligence
  Visibilidade em IA
  Search & AI observados
  Uso de IA

Ações e referência
  Análise profunda e melhorias
  Conteúdo e JSON-LD
  Remediações
  Quality & decisão
  Referências e metodologia
```

O SaaS Pilot Web usa o mesmo catálogo canônico do mini-site para listar superfícies; não mantém uma segunda lista independente de filenames/rótulos. Interfaces podem indicar estado de disponibilidade dos dados, mas não devem redefinir o catálogo público.

## Fonte de verdade

```text
audit.db + artifacts
-> report HTML audit-owned e superfícies canônicas em estado real ou neutro

observability.db + artifacts/observability
-> dados que enriquecem observability.html quando disponíveis

audit.db read-only + capacidades especializadas
-> dados que enriquecem quality.html / search-intelligence.html / ai-visibility.html quando aplicável

2 x audit.db read-only
-> relatórios comparativos

N x audit.db read-only
-> timelines/consolidações
```

HTML nunca se torna segunda fonte de verdade para score, evidence, outcomes, tokens ou custos. Um placeholder `SEM DADOS` é apenas estado de apresentação e nunca cria evidência persistida.

## Semântica visual e linguagem pública

Enums persistidos não são alterados no banco. A camada de apresentação pode traduzir valores de máquina conhecidos para PT-BR sem modificar identificadores necessários à rastreabilidade, como `BR-GEO-*`, IDs de auditoria/evidência, providers/modelos, perfis sintéticos e variáveis de ambiente.

Estados visuais específicos do domínio prevalecem sobre decoradores genéricos. Cor nunca substitui texto, Score, Coverage, Confidence ou Consolidation.

## Contrato atual

O catálogo de superfícies e a validação de completude usam `REPORT-CONTRACT-002`. `scoring.html` é a única superfície canônica de metodologia; a versão metodológica pertence a `scoring_version`, não ao filename. A regra estrutural vigente é: **toda superfície canônica possui HTML no mini-site final; dados e capacidades continuam opcionais conforme seus próprios contratos**.

Detalhes complementares: [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md), [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md), [SCORING_GUIDE.md](SCORING_GUIDE.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md), [SCORE_GEO_004.md](SCORE_GEO_004.md) e [CAPTURE_CONTEXT_MODEL.md](CAPTURE_CONTEXT_MODEL.md).
