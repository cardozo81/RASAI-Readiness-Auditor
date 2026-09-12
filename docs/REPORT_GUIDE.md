# Guia de leitura dos relatórios

O RASAi gera um mini-site HTML estático por auditoria. O report é uma projeção humana e de integração derivada da persistência; ele não recalcula scoring, não inventa dado ausente e não substitui `audit.db` + artifacts como fonte de verdade.

## Entrada principal

```text
report/index.html
```

O dashboard é multimetodológico, mas não cria um score combinado. Readiness, outcomes observados, Quality, Web Performance, acessibilidade, padrões, Apdex e Improvement Intelligence permanecem domínios analíticos distintos.

Princípios obrigatórios:

- não somar ou ponderar metodologias distintas em uma nota comum;
- mostrar apenas fatos, estados e resultados persistidos ou derivados deterministicamente deles;
- ausência de dado permanece `SEM DADOS`, `NÃO DISPONÍVEL`, `INCOMPLETO`, `UNKNOWN`, `NOT_OBSERVED` ou equivalente;
- `NULL` de fonte externa não vira zero observado;
- cada domínio usa filename canônico estável;
- após a finalização bem-sucedida de `rasai audit`, o menu e o conjunto de superfícies HTML canônicas são estáveis;
- a existência da página não significa que a capacidade correspondente foi habilitada, executada ou retornou dados;
- coletores, providers, APIs, IA e serviços externos continuam condicionados exclusivamente à configuração da execução; a estrutura HTML estática não dispara chamadas adicionais;
- quando uma capacidade não foi executada ou não materializou dados, sua página permanece disponível e apresenta estado neutro explícito, sem converter ausência em falha do website ou score zero;
- uma projeção especializada que possua dados substitui/enriquece o estado neutro da mesma superfície canônica, sem criar outro filename público.

## Estrutura canônica de uma auditoria normal

Após a finalização bem-sucedida de `rasai audit`, o conjunto canônico esperado é:

```text
report/
├─ index.html
├─ readiness.html                   # SARI-001
├─ scoring.html                     # fórmula, pesos e gates do scoring vigente
├─ context.html                     # topologia de captura URL/device; read-only
├─ crawling-discovery.html          # Domínio e descoberta; recursos ORIGIN
├─ mobile.html                      # dados Mobile ou estado SEM DADOS/NÃO APLICÁVEL
├─ desktop.html                     # dados Desktop ou estado SEM DADOS/NÃO APLICÁVEL
├─ accessibility.html               # diagnóstico ou estado explícito
├─ web-performance.html             # Lighthouse/CrUX ou estado explícito
├─ standards.html                   # W3C/MDN/WebDX/métricas derivadas ou estado explícito
├─ apdex.html                       # Synthetic Navigation Apdex ou estado explícito
├─ apdex-experience.html            # Synthetic User Experience Apdex ou estado explícito
├─ search-intelligence.html         # SERP/Search Intelligence ou estado explícito
├─ ai-visibility.html               # visibilidade generativa observada ou estado explícito
├─ observability.html               # observabilidade externa ou estado explícito
├─ ai-usage.html                    # telemetria de IA ou estado sem uso
├─ improvement-intelligence.html    # análise profunda ou estado não executado
├─ content-suggestions.html         # sugestões/JSON-LD ou estado sem IA
├─ remediation.html
├─ quality.html                     # Quality & decisão ou estado explícito
├─ references.html
├─ report-manifest.json
└─ css/site.css
```

### Gate de completude do HTML

Uma execução de URLs que terminou de persistir a auditoria não deve declarar sucesso pleno se o mini-site ficou estruturalmente incompleto. A finalização reconstrói as projeções audit-owned a partir do workspace já persistido, permite que os renderizadores especializados materializem conteúdo e, ao final, cria um estado neutro apenas para qualquer superfície canônica ainda ausente.

Depois dessa etapa, o conjunto esperado é estático e corresponde ao catálogo canônico do relatório. Se ainda faltar uma página, o comando retorna status de processo não zero e preserva `audit.db`. Assim, um problema de renderização não destrói a evidência, mas também não é ocultado como execução integralmente bem-sucedida.

O manifest registra:

```text
audit_expected_pages
audit_missing_pages
audit_report_complete
```

Em uma auditoria com projeção íntegra, `audit_expected_pages` contém todas as superfícies HTML canônicas, `audit_missing_pages` deve estar vazio e `audit_report_complete` deve ser `true`.

### Superfície estática não significa coleta obrigatória

A estabilidade do menu não altera a política operacional. Exemplos:

- `apdex.html` existe mesmo quando Synthetic Navigation Apdex não foi solicitado; nesse caso mostra estado neutro e nenhuma navegação sintética adicional é criada por causa do HTML;
- `search-intelligence.html` existe mesmo sem termos SERP, provider ou observações; o RASAi não inventa termos nem executa Search apenas para preencher a página;
- `ai-visibility.html`, `observability.html` e `quality.html` podem existir sem dataset/sidecar/processamento correspondente e informar ausência de dados;
- `mobile.html` e `desktop.html` permanecem URLs públicas estáveis mesmo quando um dos dispositivos não possui snapshot persistido;
- `standards.html` existe independentemente de W3C, MDN Observatory ou Web Platform Baseline terem retornado dados;
- páginas vazias não alteram SARI, SCORE-GEO, Coverage, Confidence, Consolidation ou findings.

Comandos especializados e processos pós-auditoria podem posteriormente materializar dados reais nessas superfícies ou produzir saídas standalone adicionais. Saídas comparativas e consolidadas também podem existir fora do diretório `report/` do AUD, por exemplo em `search-history/`, `monitoring/`, `verification/`, `quality/TIMELINE-*` e `consolidated/`.

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

A página sempre existe no mini-site final, mas sua existência não habilita serviços. Se uma integração estiver desabilitada, não configurada ou sem dado, o estado deve ser apresentado explicitamente. Em especial, Web Platform Baseline continua dependente do dataset versionado e das limitações documentadas; a mera presença de `RASAI_WEB_FEATURES_DATASET` não fabrica classificação de compatibilidade.

Esses sinais permanecem complementares/advisory, salvo quando existir mapeamento explícito de evidência para uma regra já contratada; não são um segundo score de readiness.

## Synthetic Navigation Apdex

`apdex.html` existe sempre como superfície canônica. Quando Synthetic Navigation Apdex foi habilitado e persistido, apresenta T/4T, classificação Satisfied/Tolerating/Frustrated, amostras, exclusões, perfil operacional e limitações. Quando não foi executado, apresenta estado neutro e não dispara navegações apenas para preencher o HTML.

É sintético, não RUM e não altera `SCORE-GEO-004`.

## Synthetic User Experience Apdex

`apdex-experience.html` existe sempre como superfície canônica. Quando a execução correspondente foi habilitada e persistida, apresenta a população sintética e continua sintético mesmo quando calibrado a partir de configuração Dynatrace. Quando não foi executado, apresenta estado neutro.

O mix Mobile/Desktop/Tablet distribui percentualmente a população de amostras/user actions e deve somar 100%. Ele não representa diretamente o número de requests HTTP de subrecursos, pois uma única amostra pode disparar vários requests.

## Improvement Intelligence

`improvement-intelligence.html` é audit-owned e sempre deve existir após uma auditoria bem-sucedida. Quando a análise profunda não foi solicitada, a página registra explicitamente esse estado sem disparar IA adicional apenas para produzir HTML.

Quando habilitada, a feature exige uma URL explícita e provider de IA explícito. Provider, modelo e esforço podem ser diferentes da IA padrão da auditoria, mas a credencial já configurada é reutilizada e não é duplicada no INI ou payload persistente.

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

Sem termos, provider ou observações persistidas, a página permanece disponível em estado neutro. O RASAi não inventa termos nem dispara Search para preencher HTML.

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
