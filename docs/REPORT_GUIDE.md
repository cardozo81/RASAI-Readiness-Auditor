# Guia de leitura dos relatórios

O RASAI gera um mini-site HTML estático por auditoria. O report é projeção humana derivada da persistência; não recalcula scoring nem inventa dados ausentes.

## Entrada principal

```text
report/index.html
```

O dashboard é **multimetodológico**, mas não cria score combinado. Readiness, outcomes observados, Web Performance, acessibilidade e Apdex permanecem domínios diferentes.

Princípios obrigatórios:

- não somar/ponderar metodologias distintas em uma nota comum;
- mostrar somente dados materializados;
- ausência de dado permanece `NÃO DISPONÍVEL`, `INCOMPLETO`, `UNKNOWN` ou estado equivalente;
- cada domínio tem página canônica para detalhes/metodologia;
- páginas opcionais aparecem no menu somente quando existem;
- normalização posterior não pode remover do menu uma página opcional já materializada.

## Estrutura atual

```text
report/
├─ index.html
├─ readiness.html              # SARI-001
├─ score-geo-003.html          # modelo/dataset/gates do scoring vigente
├─ mobile.html                 # condicional
├─ desktop.html                # condicional
├─ remediation.html
├─ content-suggestions.html
├─ crawling-discovery.html     # condicional/materializado
├─ accessibility.html          # condicional
├─ web-performance.html        # condicional/materializado
├─ apdex.html                  # condicional
├─ apdex-experience.html       # condicional
├─ ai-visibility.html          # condicional
├─ observability.html          # condicional
├─ ai-usage.html
├─ references.html
└─ css/site.css
```

## SARI-001 / SCORE-GEO-003

Identidade atual:

```text
SARI-001       = Search & AI Readiness Index público
SCORE-GEO-003  = motor vigente para novas auditorias
SCORE-GEO-002  = histórico
```

`readiness.html` apresenta dimensões, Coverage, Confidence, Consolidation e limitações. `score-geo-003.html` apresenta método/model artifact/dataset/gates e o estado do Overall.

A transição `002 -> 003` é quebra metodológica. O Overall atual não deve ser substituído pela antiga média simples do `002` quando o modelo `003` não é validado/elegível. Nesses casos, o report expõe `NOT_CONSOLIDATED`/limitação em vez de inventar nota.

### Groundability

Groundability continua conjunto de sinais, não subscore adicional não calibrado. Answerability, Citation Readiness e Evidence/Trust são apresentados separadamente.

### Limite de validade

SARI-001 é metodologia proprietária, evidence-bound e reprodutível. Não representa nota oficial de Google/Bing/OpenAI, probabilidade estatística de ranking/citação ou certificação GEO/AEO.

## Evidências Mobile/Desktop

`mobile.html` e `desktop.html` mostram snapshots, RuleExecutions, findings e evidências dos contextos efetivamente auditados. Não são a fonte canônica do Overall/dimensões SARI.

## Propriedade analítica

| Domínio | Página canônica | Natureza |
|---|---|---|
| SARI-001 / dimensões | `readiness.html` | readiness proprietário |
| SCORE-GEO-003 | `score-geo-003.html` | scoring/model calibration |
| Crawling/discovery | `crawling-discovery.html` | diagnóstico técnico non-scoring |
| Core Web Vitals / Lighthouse | `web-performance.html` | lab + field data separados |
| Acessibilidade automatizada | `accessibility.html` | diagnóstico; não certificação WCAG |
| Synthetic Navigation Apdex | `apdex.html` | sintético |
| Synthetic User Experience Apdex | `apdex-experience.html` | sintético calibrável; não RUM |
| Observed Generative Visibility | `ai-visibility.html` | outcome observado/importado |
| Search & AI Observability | `observability.html` | outcomes externos + diagnósticos derivados |
| Uso/custo de IA | `ai-usage.html` | telemetria operacional |

`index.html` pode repetir apenas síntese necessária à navegação executiva.

## Observed Generative Visibility

`ai-visibility.html` é separado de readiness.

```text
Readiness
= condições inferidas/evidence-bound da auditoria

Observed Generative Visibility
= outcomes observados/importados sob fonte/protocolo declarado
```

A página pode mostrar source-reported metrics, URL activity, grounding queries, trend e controlled query-runs. Citation Presence Rate é calculada apenas sobre runs `VALID` e, quando aplicável, apresenta `n` e Wilson 95%.

Observed Generative Visibility **não altera SARI-001/SCORE-GEO-003** e não converte citações em ranking/autoridade/GEO score.

## Search & AI Observability

`observability.html` é a página canônica dos dados externos pós-auditoria e diagnósticos derivados.

Pode conter:

- datasets/proveniência;
- Search Console Search Performance;
- URL Inspection;
- Indexability Reality Matrix;
- CrUX History;
- Query × Intent Alignment;
- Potential Search Cannibalization candidates;
- Structured Data documentation checks;
- entity consistency;
- freshness/date conflicts;
- hreflang;
- retrieval/chunkability;
- template/root-cause clusters.

### Leitura correta

- canonical local diferente do selected canonical externo = **divergência observada**, não prova automática de perda;
- múltiplas URLs para uma query = **candidato** de cannibalization quando passa o threshold conservador, não erro comprovado;
- Query × Intent usa matching lexical explicável, não keyword score;
- checks de Product/Breadcrumb/Organization são checks documentais/advisory, não um Rich Results score;
- CrUX History é field/RUM aggregate, separado de Lighthouse lab e Apdex;
- ausência de dado externo é limitação/suficiência, não aprovação nem falha do website.

## RASAI Monitor

Monitoring não fica dentro do `report/` de um único AUD. Ele compara dois workspaces e gera:

```text
audits/monitoring/MON-*/report.html
                         manifest.json
                         impact.html     # quando solicitado
```

### `monitor compare`

Classifica mudanças como regressão, melhoria, mudança neutra, new/resolved, unavailable ou non-comparable conforme o sinal. Device, URL universe e `scoring_version` fazem parte da comparabilidade.

### `monitor gate`

Gate de release determinístico por padrão. Regras semânticas/LLM só bloqueiam se explicitamente incluídas na política.

### `monitor impact`

Cruza mudança técnica com outcomes observados. Linguagem correta: **associação temporal/coocorrência**. O report não deve afirmar causalidade sem evidência adicional.

## Configuração × resultado obtido

O report deve diferenciar:

```text
não solicitado
configurado
executado
success
partial
unavailable
error
```

Timeout, quota, HTTP, ausência de artifact ou falta de dado da fonte não são convertidos em problema do website.

## Crawling/discovery

`crawling-discovery.html` concentra robots/crawler policy, sitemaps, feeds, `llms.txt` experimental e evidências correlatas. `scoring_impact=NONE`; não altera `SCORE-GEO-003`.

## Acessibilidade

`accessibility.html` apresenta somente automação/evidência disponível. Lighthouse accessibility não equivale a certificação WCAG integral.

## Web Performance

`web-performance.html` mantém Lighthouse lab e CrUX field separados. Synthetic Apdex não é derivado de LCP/INP/CLS/FCP/TBT.

## Synthetic Navigation Apdex

`apdex.html` apresenta T/4T, classificação Satisfied/Tolerating/Frustrated, samples, score, percentis/dispersão e limitações de small-group quando aplicáveis.

## Synthetic User Experience Apdex

`apdex-experience.html` pode usar KPM, thresholds, error policy, session mode e device mix. Mesmo calibrado contra configuração Dynatrace, continua sintético e não RUM.

## Uso de IA

`ai-usage.html` apresenta provider/modelo, tentativa/status, tokens, reasoning configurado e custo estimado quando persistidos. Custo é estimativa operacional, não invoice nem sinal de qualidade.

## Conteúdo e JSON-LD

`content-suggestions.html` reúne sugestões advisory. Nenhuma proposta textual/JSON-LD deve ser tratada como alteração automática do website ou como fato observado quando não há evidence correspondente.

## Remediação

`remediation.html` deve preservar diferença entre:

- evidence observada;
- finding/conclusão;
- selector/local quando confiável;
- exemplo/receita de correção.

Selector não deve ser inventado para findings document/set-level.

## Referências

`references.html` documenta metodologia/proveniência. Referência oficial sustenta o fenômeno externo; não homologa automaticamente a agregação proprietária RASAI.

## Consistência visual e navegação

Todas as páginas materializadas devem compartilhar:

- mesma ordem de menu;
- apenas item atual ativo;
- largura de conteúdo equilibrada;
- acabamento visual consistente;
- tabelas legíveis;
- footer no final do conteúdo principal;
- comportamento responsivo.

Ordem canônica:

```text
Visão geral
Readiness SARI
SCORE-GEO-003
Relatório Mobile
Relatório Desktop
Remediações
Conteúdo e JSON-LD
Rastreamento e descoberta
Acessibilidade
Web Performance
Apdex de navegação
Apdex de experiência
Visibilidade em IA
Search & AI observados
Uso de IA
Referências e metodologia
```

Itens sem arquivo materializado são omitidos sem alterar a ordem dos demais.

## Fonte de verdade

```text
audit.db + artifacts
→ report HTML

observability.db + artifacts/observability
→ observability.html

2 x audit.db read-only
→ MON-*/report.html + manifest/impact
```

HTML nunca deve se tornar segunda fonte de verdade para score, evidence, outcomes, tokens ou custos.

## Linguagem para o analista

O HTML deve explicar fenômeno, impacto, evidence, fonte e limitação sem exigir conhecimento de Python/SQLite/módulos internos. Termos técnicos públicos podem permanecer quando pertinentes; identificadores internos devem ser rastreabilidade secundária, não leitura principal.
