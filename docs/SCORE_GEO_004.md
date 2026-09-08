# SCORE-GEO-004

`SCORE-GEO-004` é o método de scoring vigente do RASAi.

O índice público é `SARI-001 - Search & AI Readiness Index`.

## Objetivo

O método fornece um índice operacional que pode ser calculado, auditado e reproduzido em uma auditoria individual sem depender de corpus externo, modelo estatístico ou artifact de calibração.

O contrato separa claramente:

- scoring de readiness do website;
- qualidade e completude da medição;
- métricas externas independentes;
- outcomes observados de Search e AI Search.

O Overall não representa probabilidade de ranking, resposta ou citação.

## Dimensões

O método possui dez dimensões:

1. `TECHNICAL_ACCESSIBILITY`
2. `INDEXABILITY`
3. `CONTENT_EXTRACTABILITY`
4. `SEMANTIC_STRUCTURE`
5. `ENTITY_CLARITY`
6. `STRUCTURED_DATA`
7. `ANSWERABILITY`
8. `CITATION_READINESS`
9. `EVIDENCE_TRUST`
10. `INTENT_COVERAGE`

Cada dimensão é calculada a partir de `RuleExecution` e evidências persistidas.

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00

Dimension Score = sum(weight x result_factor) / sum(weight evaluated) x 100
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos silenciosamente em `FAIL`.

## Overall

O contrato de agregação é:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Fórmula:

```text
Overall = soma dos scores das dimensões aplicáveis / quantidade de dimensões aplicáveis
```

Regras:

- cada dimensão aplicável possui o mesmo peso no Overall;
- dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero;
- dimensão aplicável sem valor ou em `NOT_CONSOLIDATED` bloqueia a publicação de Overall consolidado;
- nenhuma métrica externa é usada como contribuição implícita;
- nenhuma calibração externa é requisito ou input do score.

## Coverage

Coverage mede completude da análise, não qualidade do site.

Na dimensão:

```text
Coverage = evaluated applicable weight / total applicable weight
```

No Overall:

```text
Overall Coverage = média da Coverage das dimensões aplicáveis
```

## Confidence

A Confidence de cada dimensão depende de Coverage, presença de evidência e erros de execução.

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação, mas os critérios acima não foram satisfeitos
UNAVAILABLE Coverage <= 0
```

A Confidence do Overall é a menor Confidence entre as dimensões aplicáveis.

## Consolidation

Dimensão:

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          estado avaliável com Coverage >= 50% abaixo do gate completo
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

Overall `CONSOLIDATED` exige simultaneamente:

```text
todas as dimensões aplicáveis possuem valor
nenhuma dimensão aplicável = NOT_CONSOLIDATED
Overall Coverage >= 80%
Overall Confidence = HIGH ou MEDIUM
```

Se existe valor calculável, mas a medição não alcança o gate completo, o Overall pode ser `PARTIAL` quando a Coverage é de pelo menos 50% e a Confidence está disponível.

Estado insuficiente nunca é transformado em zero.

## Structured Data e aplicabilidade

Structured Data não é requisito universal.

Se `STRUCTURED_DATA` for legitimamente `NOT_APPLICABLE`, a dimensão sai do denominador do Overall e não recebe nota zero nem nota máxima.

Se a aplicabilidade estiver indefinida por pré-requisito bloqueado, o estado não pode ser promovido a `NOT_APPLICABLE` benigno.

## IA e baseline semântico determinístico

A fórmula do `SCORE-GEO-004` não chama IA e não depende de provider específico. O `ScoringEngine` calcula Score, Coverage, Confidence e Consolidation exclusivamente a partir de `RuleExecution` e evidências persistidas.

A partir da rule version 2 das regras semânticas `BR-GEO-028..049`, auditorias sem provider utilizam o baseline local versionado:

```text
SEMANTIC-BASELINE-001
```

Esse baseline é evidence-bound e conservador:

- usa apenas title, headings, conteúdo principal, links, Structured Data e demais evidências já persistidas no mesmo snapshot;
- não chama serviço externo;
- produz `PASS` somente quando existe evidência positiva suficiente;
- produz `NOT_APPLICABLE` somente quando a aplicabilidade pode ser resolvida de forma defensável;
- não converte ausência de evidência em `PASS`, `FAIL` ou `NOT_APPLICABLE` artificial;
- quando o critério continua irresolvido e não existe provider válido, o resultado permanece `UNKNOWN`.

Assim, **a ausência de IA deixa de bloquear mecanicamente a consolidação**. Uma auditoria `NO_AI` pode ser `CONSOLIDATED` quando todas as dimensões aplicáveis atingem os mesmos gates normais de Coverage e Confidence. Isso não significa que toda auditoria sem IA será consolidada.

Quando um provider semântico válido é configurado, ele pode aprofundar regras que exigem interpretação mais rica. A provenance da medição diferencia `DETERMINISTIC_BASELINE` de providers externos. Falha operacional de provider explicitamente configurado continua visível como degradação e não é atribuída ao website.

Detalhes: [`SEMANTIC_BASELINE.md`](SEMANTIC_BASELINE.md).

## Métricas externas independentes

Não entram no SARI-001/SCORE-GEO-004:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- tráfego, conversão e métricas de negócio;
- outcomes observados de AI visibility.

Essas medições possuem metodologias e páginas próprias. Indisponibilidade de PageSpeed/Lighthouse, por exemplo, não reduz o Overall do SARI-001.

## Reprodutibilidade

`BR-GEO-054` verifica que o scoring pode ser reconstruído a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- evidências persistidas;
- fórmula e thresholds versionados do `SCORE-GEO-004`.

Quando o baseline semântico é usado, sua provenance também é persistida por `provider=DETERMINISTIC_BASELINE`, `configuration_version=SEMANTIC-BASELINE-001` e capability de auditoria correspondente.

Não é necessário reexecutar website, IA ou APIs externas para reproduzir o cálculo persistido.

## Relatório

Cada nova auditoria materializa, quando aplicável:

```text
report/readiness.html
report/scoring.html
```

`readiness.html` é a página canônica do SARI-001.

`scoring.html` é a página canônica estável da metodologia de scoring e expõe a versão efetivamente usada, fórmula, Coverage, Confidence, Consolidation, rastreabilidade do Overall e critérios para interpretação.

A versão metodológica **não faz parte do nome canônico do arquivo**. Ela é persistida em `scoring_version` e exibida no conteúdo. Isso evita quebra de links e contratos de navegação quando uma futura versão substituir o 004.

`report/score-geo-004.html` pode ser materializado como alias de compatibilidade para links produzidos anteriormente; não é a rota recomendada para novas integrações.

## Relação com SCORE-GEO-003

`SCORE-GEO-003` permanece histórico. Seu Overall dependia de model artifact `VALIDATED` e infraestrutura de calibração externa. `SCORE-GEO-004` remove essa dependência operacional e usa um Overall determinístico de igual peso entre dimensões aplicáveis.

Preservar a referência histórica é necessário para comparabilidade e auditoria. Nenhuma normalização de HTML deve reescrever uma ocorrência histórica de `SCORE-GEO-003` como se ela fosse `SCORE-GEO-004`.

## Limite de validade

`SCORE-GEO-004` é uma metodologia proprietária, transparente, versionada e reproduzível do RASAi.

O baseline semântico também é proprietário e inclui heurísticas internas para critérios sem standard GEO/AEO universal. Ele não transforma essas heurísticas em recomendações oficiais de terceiros.

Não é um standard oficial de Google, Microsoft, OpenAI, Anthropic ou outro mantenedor e não garante ranking, tráfego, conversão, resposta ou citação futura.

## Refinamento pré-publicação: discovery, JSON-LD e fatores estáticos

- `robots.txt` e sitemap ausentes não recebem o mesmo fator de um recurso encontrado e utilizável; a ausência é uma lacuna pequena, não uma falha dura de crawling.
- Sitemap publicado porém inválido é desfavorável; falha de rede que impede avaliação continua `UNKNOWN` e reduz Coverage.
- `script[type="application/ld+json"]` é extraído do HTML. Ausência de JSON-LD é uma lacuna leve mensurável; JSON-LD inválido é desfavorável; consistência com conteúdo/entidades pode usar IA evidence-bound quando habilitada.
- A IA técnica não escolhe pesos. Ela só pode emitir classes contratadas e referenciadas por evidência; o runtime converte essas classes em `PASS/WARNING/FAIL` com fatores estáticos/versionados no mesmo `scoring_group`, sem bônus duplicado.
- Lighthouse, Core Web Vitals, Accessibility e Apdex continuam independentes da aritmética do SARI. Indisponibilidade de uma API externa não é tratada como falha do website.
- Faixas de interpretação e pesos do método são estáticos por versão. Não existe parâmetro por auditoria para alterar o conceito de excelência, preservando comparabilidade temporal.

## Regra de explicabilidade da medição

Toda projeção do SCORE-GEO-004 deve tornar auditável a diferença entre qualidade medida e força da medição. `PARTIAL` com score alto é válido quando o gate de Confidence não foi satisfeito; o relatório deve nomear a dimensão bloqueante, as RuleExecutions UNKNOWN/ERROR relevantes e a condição esperada para tornar a medição conclusiva. Limitações de configuração devem ser apresentadas como limites do escopo/amostra, sem conversão automática em falha do website.
