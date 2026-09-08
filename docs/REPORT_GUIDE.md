# Guia de leitura dos relatórios

O RASAi gera um mini-site HTML estático por auditoria. O report é projeção humana derivada da persistência; não recalcula scoring nem inventa dados ausentes.

## Entrada principal

```text
report/index.html
```

O dashboard é **multimetodológico**, mas não cria score combinado. Readiness, outcomes observados, Quality, Web Performance, acessibilidade e Apdex permanecem domínios diferentes.

Princípios obrigatórios:

- não somar/ponderar metodologias distintas em uma nota comum;
- mostrar somente dados materializados;
- ausência de dado permanece `NÃO DISPONÍVEL`, `INCOMPLETO`, `UNKNOWN`, `NOT_OBSERVED` ou equivalente;
- `NULL` de fonte externa não vira zero observado;
- cada domínio tem página canônica;
- páginas opcionais aparecem no menu somente quando existem;
- normalização posterior não pode remover do menu uma página opcional já materializada;
- identificadores de propostas anteriores de scoring usadas durante o desenvolvimento não podem ser reescritos como se fossem a versão vigente.

## Estrutura atual

```text
report/
├─ index.html
├─ readiness.html              # SARI-001
├─ scoring.html                # versão, fórmula e gates do scoring vigente
├─ score-geo-004.html          # alias de compatibilidade; não canônico
├─ mobile.html                 # condicional
├─ desktop.html                # condicional
├─ crawling-discovery.html     # condicional
├─ accessibility.html          # condicional
├─ web-performance.html        # condicional
├─ apdex.html                  # condicional
├─ apdex-experience.html       # condicional
├─ content-suggestions.html
├─ remediation.html
├─ ai-usage.html
├─ ai-visibility.html          # condicional
├─ observability.html          # condicional
├─ quality.html                # condicional
├─ references.html
└─ css/site.css
```

## SARI-001 / SCORE-GEO-004

```text
SARI-001       = Search & AI Readiness Index público
SCORE-GEO-004  = motor vigente para novas auditorias
```

`readiness.html` apresenta dimensões, Coverage, Confidence, Consolidation e limitações. `scoring.html` apresenta a versão efetivamente usada, fórmula, gates, rastreabilidade e interpretação do Overall.

O arquivo da metodologia é version-neutral por decisão de arquitetura. `scoring_version` permanece persistido no banco e visível no conteúdo. `score-geo-004.html` existe somente como alias para links produzidos durante o desenvolvimento; novas integrações devem apontar para `scoring.html`.

`SCORE-GEO-003` é uma proposta anterior de desenvolvimento preservada apenas para rastreabilidade técnica. Seu Overall dependia de model artifact validado e não deve ser confundido com o contrato determinístico vigente. Comparações entre versões preservam `scoring_version` e não normalizam contratos incompatíveis silenciosamente.

SARI-001 é metodologia proprietária, evidence-bound e reprodutível. Não representa nota oficial Google/Bing/OpenAI, probabilidade de ranking/citação ou certificação GEO/AEO.

## Propriedade analítica

| Domínio | Página canônica | Natureza |
|---|---|---|
| SARI-001 / dimensões | `readiness.html` | readiness proprietário |
| metodologia de scoring | `scoring.html` | contrato versionado; vigente `SCORE-GEO-004` |
| Crawling/discovery | `crawling-discovery.html` | diagnóstico técnico non-scoring |
| Core Web Vitals / Lighthouse | `web-performance.html` | lab + field data separados |
| Acessibilidade automatizada | `accessibility.html` | diagnóstico; não certificação WCAG |
| Synthetic Navigation Apdex | `apdex.html` | sintético |
| Synthetic User Experience Apdex | `apdex-experience.html` | sintético calibrável; não RUM |
| Observed Generative Visibility | `ai-visibility.html` | outcome observado/importado |
| Search & AI Observability | `observability.html` | outcomes externos + diagnósticos derivados |
| Quality & decisão | `quality.html` | qualidade da evidência/priorização operacional |
| Uso/custo de IA | `ai-usage.html` | telemetria operacional |

`index.html` pode repetir síntese necessária à navegação executiva, mas não funde metodologias em score comum.

## Observed Generative Visibility

`ai-visibility.html` permanece separado de readiness.

```text
Readiness
= condições inferidas/evidence-bound da auditoria

Observed Generative Visibility
= outcomes observados/importados sob fonte/protocolo declarado
```

A página pode mostrar source-reported metrics, URL activity, grounding queries, trend e controlled query-runs. Citation Presence Rate é calculada somente sobre runs válidos conforme contrato.

Observed Generative Visibility **não altera SARI-001/SCORE-GEO-004**.


Em auditorias de domínio, destinos internos observados apenas após rendering e que ficaram fora do universo auditado são expostos como limitação de cobertura (`RENDERED_DISCOVERY_GAP` ou limite equivalente). O relatório não deve apresentar uma homepage isolada como cobertura implícita de todo o domínio.

## Search & AI Observability

`observability.html` é a página canônica dos dados externos pós-auditoria e diagnósticos derivados.

Pode conter:

- datasets/proveniência;
- Search Console Search Analytics;
- Search Appearance;
- propriedades/sitemaps observados;
- URL Inspection;
- Indexability Reality Matrix;
- Google Generative AI Performance importado;
- estado GenAI `INCLUDE` / `EXCLUDE` / `INHERIT` observado;
- Bing imports;
- CrUX History;
- Query × Intent Alignment;
- Potential Search Cannibalization;
- Structured Data/entity/freshness/hreflang/retrieval diagnostics;
- template/root-cause clusters.

### Como ler datasets

O sidecar atual é `RASAI-OBS-002`. Cada linha pertence a `(dataset_id, record_id)`, permitindo histórico de coletas independentes sem colisão.

Search/Discover GenAI e Search Analytics/Search Appearance possuem provenance separada. Métrica inexistente na fonte permanece inexistente; por exemplo, um export GenAI de impressões não cria clicks/CTR/position artificiais.

### Leitura correta

- canonical local diferente do selected canonical externo = **divergência observada**, não prova automática de perda;
- múltiplas URLs para uma query = **candidato** de cannibalization, não erro comprovado;
- Query × Intent é matching lexical explicável, não keyword score;
- Product/Breadcrumb/Organization são checks documentais/advisory;
- CrUX History é field aggregate, separado de Lighthouse lab e Apdex;
- ausência de dado externo é limitação/suficiência, não aprovação nem falha;
- `~`/`-` ou zero exportado em GenAI deve ser interpretado com a metadata de supressão/rounding;
- publisher control `EXCLUDE` muda a interpretação da ausência de visibilidade, mas não é penalidade SARI.

### Freshness reprodutível

Checks de data usam o tempo persistido do AUD (`completed_at`, `started_at`, `created_at` ou snapshot). Regenerar o mesmo HTML meses depois não pode criar um novo conflito apenas porque o relógio da máquina avançou.

## Quality & decisão

`quality.html` responde se a própria evidência RASAi está em condição adequada para apoiar decisões.

### Audit Health

Verifica integridade/completude da coleta e artifacts. **Audit Health não é readiness score.**

### Evidence Confidence

`HIGH`, `MEDIUM` ou `LOW` por finding, com base em provenance, RuleExecution e evidence persistida. É diferente da Confidence das dimensões SARI.

### Operational Priority

`P0`-`P3` orienta ordem de remediação combinando severidade, escopo, confiança da evidência e esforço estimado. Não altera Severity nem SCORE-GEO.

### Coverage Map

Mostra URL/device × domínios de evidência. `NOT_OBSERVED` significa ausência de observação no escopo, não FAIL.

### Search & AI content controls

A página pode registrar:

- `nosnippet`;
- `max-snippet`;
- `data-nosnippet`;
- `X-Robots-Tag`.

São controles do publisher e não penalidades automáticas.

### Recommendation Validation

Valida referência/estado/confiança da recomendação contra a evidência persistida. Não substitui revisão humana da mudança proposta.

## RASAi Monitor

Monitoring não fica dentro de um único AUD:

```text
audits/monitoring/MON-*/report.html
                         manifest.json
                         impact.html     # quando solicitado
```

### `monitor compare`

Classifica regressão, melhoria, mudança neutra, new/resolved, unavailable ou non-comparable. Device, URL universe e `scoring_version` participam da comparabilidade.

### `monitor gate`

Default: regras determinísticas elegíveis + page state.

Somente entram por opt-in:

- regras semânticas/IA;
- Performance;
- Synthetic Apdex;
- aggregates de findings;
- deltas de score dimensions.

Isso evita que uma família não determinística bloqueie release indiretamente.

### `monitor impact`

Seleciona um dataset mais recente por source type em cada AUD; não soma históricos sobrepostos.

Janelas observacionais:

```text
ALIGNED_WINDOW
PARTIAL_OVERLAP
NON_OVERLAPPING
UNKNOWN_PERIOD
DATA_UNAVAILABLE
```

Associação temporal só pode ser emitida para `ALIGNED_WINDOW` ou `PARTIAL_OVERLAP`. Mesmo nesses casos, o relatório diz coocorrência/associação, não causalidade.

## Fix Verification

Saída standalone:

```text
audits/verification/VER-*/report.html
```

Estados principais:

```text
FIXED
PARTIALLY_FIXED
NOT_FIXED
NOT_VERIFIABLE
```

A leitura correta é “o estado persistido da regra mudou entre os dois AUDs”. Não significa que Search/AI já reagiu à correção.

## Evidence Timeline

Saída standalone:

```text
audits/quality/TIMELINE-*/report.html
```

Projeta histórico de AUDs sem regravá-los: data, versões, URL count, FAIL/WARNING, dimensões e page-state conforme evidência disponível.

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

`crawling-discovery.html` concentra robots/crawler policy, sitemaps, feeds, `llms.txt` experimental e evidências correlatas. Os diagnósticos auxiliares continuam advisory. Quando a IA técnica estiver habilitada e produzir avaliação evidence-bound válida de robots/sitemap, somente a classe bounded do recurso pode compartilhar o grupo de scoring correspondente, com fatores estáticos e sem bônus duplicado.

## Acessibilidade

`accessibility.html` apresenta somente automação/evidência disponível. Lighthouse accessibility não equivale a certificação WCAG integral.

## Web Performance

`web-performance.html` mantém Lighthouse lab e CrUX field separados. Synthetic Apdex não é derivado de LCP/INP/CLS/FCP/TBT.

## Synthetic Navigation Apdex

`apdex.html` apresenta T/4T, classificação Satisfied/Tolerating/Frustrated, samples e limitações.

## Synthetic User Experience Apdex

`apdex-experience.html` continua sintético e não RUM, mesmo quando calibrado contra configuração Dynatrace.

## Uso de IA

`ai-usage.html` apresenta provider/modelo, tentativa/status, tokens, reasoning configurado e custo estimado. Custo é estimativa operacional, não invoice nem sinal de qualidade.

## Conteúdo e JSON-LD

`content-suggestions.html` reúne sugestões advisory. Nenhuma proposta textual/JSON-LD vira fato observado ou alteração automática do website.

## Remediação

`remediation.html` preserva diferença entre evidence, finding/conclusão, selector/local quando confiável e receita de correção. Selector não deve ser inventado para findings document/set-level.

## Referências

`references.html` documenta metodologia/proveniência. Referência oficial sustenta o fenômeno externo; não homologa automaticamente a agregação proprietária RASAi.

## Consistência visual e navegação

Todas as páginas materializadas devem compartilhar:

- mesma ordem de menu;
- apenas item atual ativo;
- largura equilibrada;
- acabamento visual consistente;
- tabelas legíveis;
- footer no final do conteúdo;
- comportamento responsivo.

Ordem canônica:

```text
Visão geral
Readiness SARI
Metodologia de scoring
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
Quality & decisão
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

audit.db read-only
→ quality.html

2 x audit.db read-only
→ MON-*/report.html + manifest/impact
→ VER-*/report.html

N x audit.db read-only
→ TIMELINE-*/report.html
```

HTML nunca se torna segunda fonte de verdade para score, evidence, outcomes, tokens ou custos.

## Rastreabilidade dos inputs do SARI

A página **Search & AI Readiness** deve distinguir o **estado observado** do nome/objetivo da regra. Um critério como “interpretar sitemap quando disponível” não pode ser apresentado como se o recurso tivesse sido encontrado. Para sitemap, `robots.txt` e JSON-LD o report expõe estado observado, RuleExecution, `scoring_group`, peso, fator e contribuição efetiva persistida.

`llms.txt` continua sendo inspecionado em **Rastreamento e descoberta** como sinal experimental/advisory. Seu peso direto no `SARI-001` é `0`: presença, ausência ou erro não alteram `SCORE-GEO-004`.

JSON-LD é extraído de `script[type="application/ld+json"]`. No SCORE-GEO-004, ausência gera uma lacuna leve via `BR-GEO-034=WARNING`; markup inválido pode ser desfavorável; consistência semântica só é avaliada quando aplicável.

<!-- rasai-global-result-semantics-20260908 -->
## Semântica visual e linguagem pública

A normalização final dos relatórios aplica o mesmo contrato a todas as superfícies HTML. Estados conclusivos que aparecem em tabelas/listas recebem uma tag na célula e uma indicação discreta na linha: aprovado/consolidado em verde, alerta/parcial em amarelo, falha/erro em vermelho. Estados neutros não são promovidos artificialmente a erro.

Enums persistidos não são alterados no banco. A camada de apresentação traduz valores de máquina conhecidos para PT-BR e preserva identificadores dentro de `code`/`pre`. Isso evita expor ao usuário termos como `SINGLE_PROVIDER` ou `NOT_DETERMINABLE` sem perder rastreabilidade técnica.

A ordem canônica do menu segue a sequência de leitura: visão geral → SARI → metodologia → evidências por dispositivo → crawling/acessibilidade/performance/Apdex → conteúdo/remediação → telemetria e outcomes de IA → quality → referências.

Correlação: veja [`README.md`](README.md), [`SCORING_GUIDE.md`](SCORING_GUIDE.md), [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md) e [`docs/README.md`](README.md).
