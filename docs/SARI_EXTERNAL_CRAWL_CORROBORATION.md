# SARI-001 - corroboração externa de discovery

## Estado metodológico vigente

Este documento faz parte do contrato vigente de `SARI-001` / `SCORE-GEO-004`.

O RASAi admite **uma única família de evidência externa observacional diretamente no SARI**: corroboração histórica positiva de discovery por Common Crawl, materializada como `BR-GEO-060`.

CrUX History, Microsoft Clarity, Google Search Console, SERP, AI Visibility e demais outcomes permanecem fora do cálculo do SARI.

## Motivo

O SARI mede readiness. A maioria das integrações externas mede consequência ou outcome:

- CrUX mede experiência de campo;
- Clarity mede comportamento real;
- GSC/Bing medem resultados observados de Search;
- SERP mede posição/competição;
- AI Visibility mede observação de mecanismos generativos.

Esses dados são valiosos para validar a utilidade do SARI, mas não devem tornar o índice circular.

Common Crawl é tratado de forma diferente somente porque uma observação positiva e recente nos índices consultados fornece uma evidência independente, diretamente relacionada a **descoberta/crawl de URL pública**.

Mesmo assim, o sinal é deliberadamente pequeno, positive-only e não crítico.

## BR-GEO-060

```text
Rule: BR-GEO-060
Dimension: DISCOVERY_ACCESS
Scoring group: EXTERNAL_CRAWL_CORROBORATION
Evidence role: EXTERNAL_CORROBORATIVE
Result materializado: PASS somente
Scope: audit/global
Device: nenhum; o mesmo sinal global pode participar dos scores por device
```

A regra é criada somente quando todas as condições abaixo são satisfeitas:

1. Common Crawl está efetivamente habilitado;
2. as URLs bounded selecionadas são seguras para consulta em índice público;
3. a coleta conclui sem erro de provider/transporte;
4. existe captura histórica positiva nos índices recentes consultados;
5. pelo menos 50% das URLs bounded selecionadas possuem observação positiva;
6. os sinais críticos atuais de Discovery usados pelo RASAi não estão em `FAIL`.

Se qualquer condição falhar, **nenhuma RuleExecution BR-GEO-060 é criada**.

Portanto:

```text
sem captura
provider indisponível
quota/erro de rede
URL privada/local
URL com query/fragment/userinfo
amostra abaixo do threshold
Discovery atual bloqueado

=> sem BR-GEO-060
=> sem FAIL
=> sem zero
=> sem redução de Coverage
=> sem redução de Confidence
```

## Peso

`DISCOVERY_ACCESS` continua pesando 15% do SARI.

O grupo `EXTERNAL_CRAWL_CORROBORATION` pesa 3% dentro de `DISCOVERY_ACCESS`.

Logo, seu impacto máximo teórico no Overall é:

```text
15% × 3% × 100 = 0,45 ponto
```

A regra não pode acrescentar mais de 0,45 ponto ao SARI Overall quando todas as dimensões aplicáveis estão presentes.

### Preservação exata do cálculo técnico quando a evidência externa não existe

Os sete grupos técnicos anteriores de `DISCOVERY_ACCESS` foram multiplicados por `0,97`, reservando exatamente 3% para a nova corroboração externa:

| Grupo | Peso vigente | Relação técnica anterior preservada quando BR-GEO-060 não existe |
|---|---:|---:|
| `PAGE_ACCESS` | 29,10% | 30% |
| `ROBOTS` | 14,55% | 15% |
| `SITEMAP` | 4,85% | 5% |
| `REDIRECT` | 9,70% | 10% |
| `SPA_ROUTE` | 9,70% | 10% |
| `SPA_NAVIGATION` | 9,70% | 10% |
| `INTERNAL_LINKS` | 19,40% | 20% |
| `EXTERNAL_CRAWL_CORROBORATION` | 3,00% | n/a |
| **Total** | **100%** | |

Quando BR-GEO-060 não existe, o motor normaliza apenas os grupos aplicáveis/evidenciados. Como os sete grupos técnicos são exatamente os pesos anteriores × 0,97, suas proporções retornam matematicamente a:

```text
30 / 15 / 5 / 10 / 10 / 10 / 20
```

Assim, **ausência de Common Crawl não altera o resultado técnico anterior nem Coverage**. A única mudança possível é um pequeno uplift quando existe evidência externa positiva qualificada.

## Critical Readiness Gates

BR-GEO-060 **não participa** do Discovery Gate.

O Discovery Gate continua restrito a:

```text
PAGE_ACCESS
ROBOTS
REDIRECT
```

Isso impede que evidência histórica externa compense:

- página atualmente inacessível;
- bloqueio atual por robots;
- redirect atualmente bloqueante.

Mesmo que BR-GEO-060 exista, um gate `BLOCKED` continua `BLOCKED`.

## Segurança da coleta automática

Como Common Crawl é gratuito e não exige credencial, a integração pode ficar habilitada por default. Porém, consultas automáticas são recusadas quando a URL selecionada contém ou representa:

- `localhost` ou host reservado/local;
- IP privado/reservado;
- userinfo (`usuario:senha@host`);
- query string;
- fragment;
- esquema diferente de HTTP/HTTPS.

O objetivo é não divulgar por default alvos internos ou parâmetros potencialmente sensíveis a um serviço público.

O default empacotado permanece bounded:

```text
RASAI_COMMON_CRAWL_ENABLED=true
RASAI_COMMON_CRAWL_MAX_URLS=3
RASAI_COMMON_CRAWL_INDEX_COUNT=2
```

Não existe key/token para Common Crawl.

## Reprodutibilidade

A chamada externa acontece **antes do M9**.

Quando a regra qualifica:

```text
Common Crawl sidecar dataset
        ↓
Evidence persistida no audit.db
        ↓
BR-GEO-060 RuleExecution persistida
        ↓
M9 / SCORE-GEO-004
        ↓
score_contributions
```

A reexecução do scoring usa a RuleExecution/Evidence persistida. Ela não chama Common Crawl novamente.

Assim, BR-GEO-054 continua podendo provar que o resultado é reconstruível offline a partir das evidências e contratos persistidos.

## Proveniência

A observação de captura é `RAW_OBSERVATION` proveniente do Common Crawl.

As decisões abaixo são `RASAI_HEURISTIC` e pertencem ao contrato versionado do RASAi:

- threshold mínimo de 50% das URLs bounded;
- uso positive-only;
- exclusão de Critical Gates;
- peso de 3% dentro de `DISCOVERY_ACCESS`;
- impacto máximo de 0,45 ponto no Overall;
- bloqueio do uplift quando sinais críticos atuais de Discovery estão em FAIL.

Common Crawl não homologa o SARI e uma captura não significa indexação em Google/Bing, ranking, disponibilidade atual ou conhecimento por IA.

## O que continua fora do SARI

### CrUX History

Permanece em `web-performance.html` / Observability como experiência real histórica. Não altera SARI.

### Microsoft Clarity

Permanece em `apdex-experience.html` / Observability como comportamento agregado real. Não altera SARI.

### Google Search Console / Bing Webmaster

São outcome/owner telemetry. Podem demonstrar alinhamento ou divergência entre readiness e resultado real, mas não alteram SARI automaticamente.

### SERP / AI Visibility

São outcomes observados e não entram no cálculo.

## Relatórios

`readiness.html` e `scoring.html` devem mostrar explicitamente:

- se BR-GEO-060 foi aplicada;
- peso do grupo;
- impacto máximo no Overall;
- razão de URLs observadas quando disponível;
- aviso de que ausência não penaliza;
- aviso de que o dado não prova indexação/ranking;
- aviso de que o grupo não integra Critical Gates.

`crawling-discovery.html` e `observability.html` mantêm o detalhamento das capturas Common Crawl.
