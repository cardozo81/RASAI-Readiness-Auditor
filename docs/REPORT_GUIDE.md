# Guia de leitura dos relatórios

O RASAi gera um mini-site HTML estático por auditoria. O report é uma projeção humana e de integração derivada da persistência; ele não recalcula scoring, não inventa dado ausente e não substitui `audit.db` + artifacts como fonte de verdade.

## Entrada principal

```text
report/index.html
```

O dashboard é multimetodológico, mas não cria um score combinado. Readiness, outcomes observados, Quality, Web Performance, acessibilidade e Apdex permanecem domínios analíticos distintos.

Princípios obrigatórios:

- não somar ou ponderar metodologias distintas em uma nota comum;
- mostrar apenas fatos, estados e resultados persistidos ou derivados deterministicamente deles;
- ausência de dado permanece `NÃO DISPONÍVEL`, `INCOMPLETO`, `UNKNOWN`, `NOT_OBSERVED` ou equivalente;
- `NULL` de fonte externa não vira zero observado;
- cada domínio usa filename canônico estável;
- o menu mostra somente arquivos que existem fisicamente;
- uma página pertencente à auditoria normal deve existir mesmo quando a capacidade opcional correspondente estiver desabilitada, registrando esse estado explicitamente;
- páginas especializadas pós-auditoria aparecem somente depois que sua própria capacidade as materializa.

## Estrutura de uma auditoria normal

Após `rasai audit`, o conjunto base esperado é:

```text
report/
├─ index.html
├─ readiness.html              # SARI-001
├─ scoring.html                # fórmula, pesos e gates do scoring vigente
├─ content-suggestions.html    # existe mesmo sem IA de conteúdo
├─ crawling-discovery.html
├─ accessibility.html          # existe mesmo sem Lighthouse disponível
├─ web-performance.html        # existe mesmo com coleta externa desabilitada
├─ remediation.html
├─ ai-usage.html               # existe mesmo sem chamadas de IA
├─ references.html
├─ mobile.html                 # quando houver snapshot Mobile
├─ desktop.html                # quando houver snapshot Desktop
├─ apdex.html                  # quando Synthetic Navigation Apdex estiver habilitado
├─ apdex-experience.html       # quando Synthetic User Experience Apdex estiver habilitado
├─ report-manifest.json
└─ css/site.css
```

### Gate de completude do HTML

Uma execução de URLs que terminou de persistir a auditoria não deve declarar sucesso pleno se o mini-site ficou incompleto. A finalização reconstrói as projeções audit-owned a partir do workspace já persistido e compara o conjunto esperado com os arquivos físicos.

Se ainda faltar uma página obrigatória daquela execução, o comando retorna status de processo não zero e preserva `audit.db`. Assim, um problema de renderização não destrói a evidência, mas também não é ocultado como execução integralmente bem-sucedida.

O manifest registra:

```text
audit_expected_pages
audit_missing_pages
audit_report_complete
```

Em uma auditoria com projeção íntegra, `audit_missing_pages` deve estar vazio e `audit_report_complete` deve ser `true`.

## Superfícies especializadas pós-auditoria

Os arquivos abaixo são canônicos, mas não fazem parte da promessa de toda execução simples de `rasai audit`:

```text
search-intelligence.html
ai-visibility.html
observability.html
quality.html
```

Eles são materializados quando sua capacidade especializada possui dados para o AUD. Portanto, a ausência desses arquivos em um workspace recém-gerado não significa, por si só, falha da auditoria base.

Saídas históricas, comparativas e consolidadas também podem existir fora do diretório `report/` do AUD, por exemplo em `search-history/`, `monitoring/`, `verification/`, `quality/TIMELINE-*` e `consolidated/`.

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
| metodologia de scoring | `scoring.html` | contrato versionado; vigente `SCORE-GEO-004` |
| Mobile | `mobile.html` | evidências/findings do contexto Mobile |
| Desktop | `desktop.html` | evidências/findings do contexto Desktop |
| Crawling/discovery | `crawling-discovery.html` | diagnóstico técnico e evidência de descoberta |
| Acessibilidade automatizada | `accessibility.html` | diagnóstico; não certificação WCAG |
| Core Web Vitals / Lighthouse | `web-performance.html` | lab + field data separados |
| Search Intelligence | `search-intelligence.html` | SERP observado e análise competitiva; non-scoring |
| Synthetic Navigation Apdex | `apdex.html` | sintético |
| Synthetic User Experience Apdex | `apdex-experience.html` | sintético calibrável; não RUM |
| Conteúdo e JSON-LD | `content-suggestions.html` | remediação advisory |
| Remediações | `remediation.html` | plano evidence-bound |
| Observed Generative Visibility | `ai-visibility.html` | outcome observado/importado |
| Search & AI Observability | `observability.html` | outcomes externos e diagnósticos derivados |
| Quality & decisão | `quality.html` | qualidade da evidência/priorização operacional |
| Uso/custo de IA | `ai-usage.html` | telemetria operacional |
| Referências | `references.html` | metodologia e proveniência |

`index.html` pode repetir sínteses necessárias à leitura executiva, mas não funde domínios complementares em um score comum.

## Configuração versus resultado obtido

O report deve distinguir estados de execução, por exemplo:

```text
não solicitado
configurado
desabilitado
executado
success
partial
unavailable
error
```

Timeout, quota, HTTP, falta de artifact ou ausência de dado da fonte não são convertidos em problema do website.

Essa distinção é especialmente importante em páginas que agora existem sempre na auditoria base: `content-suggestions.html`, `web-performance.html`, `accessibility.html` e `ai-usage.html`. Nelas, um estado desabilitado ou indisponível deve ser explícito; a presença do arquivo não significa que a coleta ou IA ocorreu.

## Crawling e descoberta

`crawling-discovery.html` concentra robots/crawler policy, sitemaps, feeds, `llms.txt` experimental e evidências correlatas. Quando artifacts textuais foram efetivamente capturados, o relatório pode exibir uma pré-visualização read-only sem fazer nova requisição de rede.

O peso direto de `llms.txt` no `SARI-001` é `0`: presença, ausência ou erro não alteram `SCORE-GEO-004`. O arquivo permanece um sinal experimental/advisory, não um requisito normativo de Search ou de sistemas generativos.

Diagnósticos auxiliares permanecem advisory. Quando IA técnica estiver habilitada e produzir avaliação evidence-bound válida de robots/sitemap, somente a classe bounded do mesmo recurso pode compartilhar o grupo de scoring correspondente, com fatores estáticos e sem bônus duplicado.

## Acessibilidade

`accessibility.html` apresenta automação/evidência disponível ou estado explícito de indisponibilidade/desabilitação. Lighthouse accessibility não equivale a certificação WCAG integral.

A página não altera `SCORE-GEO-004`.

## Web Performance

`web-performance.html` mantém Lighthouse lab e CrUX field separados. A página é materializada mesmo quando a coleta externa está desabilitada, justamente para deixar esse estado inequívoco.

Synthetic Apdex não é derivado de LCP, INP, CLS, FCP ou TBT. Web Performance não altera automaticamente SARI/SCORE.

## Synthetic Navigation Apdex

`apdex.html` existe somente quando a execução correspondente estiver habilitada e persistida. Apresenta T/4T, classificação Satisfied/Tolerating/Frustrated, amostras, exclusões e limitações.

É sintético, não RUM e não altera `SCORE-GEO-004`.

## Synthetic User Experience Apdex

`apdex-experience.html` existe somente quando a execução correspondente estiver habilitada e persistida. Continua sintético mesmo quando calibrado a partir de configuração Dynatrace.

O mix Mobile/Desktop/Tablet distribui percentualmente a população de amostras/user actions e deve somar 100%. Ele não representa diretamente o número de requests HTTP de subrecursos, pois uma única amostra pode disparar vários requests.

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

## Observed Generative Visibility

`ai-visibility.html` é uma superfície especializada e permanece separada de readiness:

```text
Readiness
= condições inferidas/evidence-bound da auditoria

Observed Generative Visibility
= outcomes observados/importados sob fonte e protocolo declarados
```

Pode mostrar métricas reportadas pela fonte, atividade de URLs, grounding queries, trends e controlled query-runs. Ausência de observação não vira score zero artificial. Observed Generative Visibility não altera `SARI-001/SCORE-GEO-004`.

## Search Intelligence

`search-intelligence.html` é uma superfície especializada point-in-time. Pode conter SERP Observation, posição observada, candidatos competitivos, comparação determinística de conteúdo e análise semântica evidence-bound quando explicitamente executada.

Ela permanece non-scoring. `NOT_FOUND_WITHIN_DEPTH` não deve ser transformado em posição numérica artificial.

Comparações históricas Search Intelligence pertencem ao par de AUDs e podem ser materializadas em saída standalone, preservando identidade de query, engine, mercado, idioma, device, profundidade e provider/data mode.

## Search & AI Observability

`observability.html` é a página especializada dos dados externos pós-auditoria. O sidecar atual é `RASAI-OBS-002`.

Pode conter Search Console, Search Appearance, properties/sitemaps, URL Inspection, CrUX History, imports generativos, publisher controls e diagnósticos derivados. Cada linha observacional pertence ao seu dataset e provenance.

Leitura correta:

- canonical local diferente do selected canonical externo é divergência observada, não prova automática de perda;
- múltiplas URLs para uma query são candidato de cannibalization, não erro comprovado;
- ausência de dado externo é limitação/suficiência, não aprovação nem falha;
- correlação temporal não é causalidade;
- métrica inexistente na fonte não é fabricada.

## Quality & decisão

`quality.html` é especializado e responde se a evidência RASAi está adequada para apoiar decisão. Pode expor Audit Health, Evidence Confidence, Operational Priority, Coverage Map, controles de conteúdo e Recommendation Validation.

Quality não cria um novo readiness score e não altera Severity nem `SCORE-GEO-004`.

## Monitoring, Verification e Timeline

Comparações entre auditorias são superfícies standalone e read-only sobre os AUDs fonte. Exemplos:

```text
audits/monitoring/MON-*/report.html
audits/verification/VER-*/report.html
audits/quality/TIMELINE-*/report.html
```

Comparabilidade deve considerar `scoring_version`, device e universo de URL quando aplicável. Mudança temporal ou proximidade de um deployment não prova causalidade de Search/AI.

## Consistência visual e navegação

Todas as páginas materializadas devem compartilhar navegação estável, apenas um item ativo, layout responsivo, tabelas legíveis e footer coerente.

A ordem canônica do contrato atual é:

```text
Visão geral
Readiness SARI
Metodologia de scoring
Relatório Mobile
Relatório Desktop
Rastreamento e descoberta
Acessibilidade
Web Performance
Search Intelligence
Apdex de navegação
Apdex de experiência
Conteúdo e JSON-LD
Remediações
Visibilidade em IA
Search & AI observados
Quality & decisão
Uso de IA
Referências e metodologia
```

Itens sem arquivo materializado são omitidos sem alterar a ordem relativa dos demais.

## Fonte de verdade

```text
audit.db + artifacts
→ report HTML audit-owned

observability.db + artifacts/observability
→ observability.html

audit.db read-only + capacidade especializada
→ quality.html / search-intelligence.html / ai-visibility.html quando aplicável

2 x audit.db read-only
→ relatórios comparativos

N x audit.db read-only
→ timelines/consolidações
```

HTML nunca se torna segunda fonte de verdade para score, evidence, outcomes, tokens ou custos.

## Semântica visual e linguagem pública

Enums persistidos não são alterados no banco. A camada de apresentação pode traduzir valores de máquina conhecidos para PT-BR sem modificar identificadores necessários à rastreabilidade, como `BR-GEO-*`, IDs de auditoria/evidência, providers/modelos, perfis sintéticos e variáveis de ambiente.

Estados visuais específicos do domínio prevalecem sobre decoradores genéricos. Cor nunca substitui texto, Score, Coverage, Confidence ou Consolidation.

## Contrato atual

O catálogo de superfícies e a validação de completude usam `REPORT-CONTRACT-002`. `scoring.html` é a única superfície canônica de metodologia durante a fase pré-publicação; a versão metodológica pertence a `scoring_version`, não ao filename.

Detalhes complementares: [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md), [SCORING_GUIDE.md](SCORING_GUIDE.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md) e [SCORE_GEO_004.md](SCORE_GEO_004.md).
