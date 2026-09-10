# BUSINESS_RULES.md

**Estado no baseline de desenvolvimento:** APROVADO / VIGENTE  
**Ruleset vigente:** `BR-GEO-001..059`

Este documento descreve o contrato funcional vigente das Business Rules do RASAi. Identificadores, enums, nomes de campos e valores persistidos permanecem na forma técnica canônica; títulos e explicações são apresentados em português do Brasil.

## 1. Contrato comum

Cada regra possui, conforme aplicável:

- `rule_id`;
- `version`;
- `name`;
- `description`;
- `dimension`;
- `category`;
- `execution_type`;
- `device_scope`;
- `architecture_scope`;
- `engine_scope`;
- `basis`;
- `applicability`;
- `dependencies`;
- `inputs`;
- `checks`;
- condições de resultado;
- requisitos de evidência;
- política de finding;
- severidade;
- metadados de scoring;
- política de fallback;
- metadados de rastreabilidade.

Resultados canônicos:

```text
PASS
FAIL
WARNING
NOT_APPLICABLE
UNKNOWN
ERROR
```

Invariantes:

```text
UNKNOWN != FAIL
ERROR != FAIL
NOT_APPLICABLE != FAIL
```

## 2. Aquisição

### BR-GEO-001 - O alvo da auditoria deve ser válido e normalizado

Valida o target e sua normalização. É global, determinística e bloqueadora da execução quando o alvo é inválido. Não cria contribuição de score por si só.

### BR-GEO-002 - Toda URL descoberta deve possuir proveniência rastreável

Toda `Page` deve registrar uma origem de descoberta suportada, como `SEED`, `SITEMAP`, `INTERNAL_LINK`, `REDIRECT` ou `MANUAL`. É requisito de integridade do auditor.

### BR-GEO-003 - Recursos de sitemap devem ser adquiridos e interpretados quando disponíveis

Avalia sitemap declarado ou encontrado, parsing e URLs observadas. Ausência de sitemap, isoladamente, não é convertida em `FAIL`.

### BR-GEO-004 - Artefatos de aquisição HTTP devem ser preservados para análise reproduzível

Preserva URL solicitada, dispositivo, timestamp, resultado de rede, status, headers, URL final, referência ao corpo e cadeia de redirects conforme o contrato de persistência.

## 3. Acessibilidade técnica

### BR-GEO-005 - A página deve ser tecnicamente recuperável

Avalia falhas de DNS, TLS, conexão, timeout ou ausência de resposta técnica utilizável.

### BR-GEO-006 - A resposta HTTP final deve ser utilizável para o conteúdo esperado

Avalia status final e adequação da resposta ao tipo de página esperado.

### BR-GEO-007 - Redirects devem resolver sem loops ou cadeias inválidas

Detecta loops e cadeias incapazes de atingir destino válido.

### BR-GEO-008 - Cadeias de redirect não devem introduzir problemas materiais de rastreamento ou acesso

Detecta cadeias excessivas ou problemáticas conforme critérios versionados.

### BR-GEO-009 - Documentos HTML esperados devem fornecer conteúdo analisável

Aplica-se a páginas que deveriam fornecer documento HTML utilizável.

### BR-GEO-010 - Falhas de renderização não devem impedir acesso ao conteúdo essencial

Somente falhas de rendering com impacto material sobre o conteúdo necessário geram problema do website.

## 4. Capacidade de indexação

### BR-GEO-011 - Diretivas de indexação devem ser resolvidas de forma consistente

Combina `meta robots`, `X-Robots-Tag` e diretivas observadas no estado renderizado.

### BR-GEO-012 - Diretivas explícitas `noindex` devem ser identificadas corretamente

Detecta `noindex` genérico ou específico de crawler conforme evidência disponível.

### BR-GEO-013 - Declarações canonical devem ser interpretáveis e não conflitantes

Detecta canonical ausente, inválida, múltipla ou conflitante. Ausência isolada não implica automaticamente severidade alta.

### BR-GEO-014 - O destino canonical deve ser tecnicamente válido e contextualmente plausível

Verifica target, status, redirects e plausibilidade contextual sem inventar a URL preferencial.

### BR-GEO-015 - JavaScript não deve introduzir conflitos inseguros de canonical/indexabilidade

Compara estados RAW e RENDERED para canonical e robots.

### BR-GEO-016 - Páginas com semântica de erro não devem se apresentar como páginas indexáveis válidas

Detecta soft 404 e estados equivalentes somente quando há evidência suficiente.

## 5. Robots e crawlers

### BR-GEO-017 - `robots.txt` deve ser interpretável quando presente

Ausência ou HTTP 404 do arquivo não significa, por si só, bloqueio do website.

### BR-GEO-018 - O acesso de crawlers deve ser resolvido independentemente por crawler configurado

Baseline de crawlers:

- Googlebot;
- Googlebot Smartphone;
- Bingbot;
- OAI-SearchBot;
- GPTBot.

OAI-SearchBot e GPTBot nunca devem ser tratados como equivalentes. Bloquear GPTBot, isoladamente, não deve penalizar Search readiness.

## 6. JavaScript, rendering e SPA

### BR-GEO-019 - Estados RAW e renderizado devem permanecer semanticamente consistentes

Compara título, descrição, canonical, robots, headings, conteúdo, links e Dados Estruturados.

### BR-GEO-020 - Conteúdo essencial deve continuar recuperável após a renderização JavaScript

Um shell RAW com conteúdo RENDERED completo pode ser válido. Conteúdo essencial não recuperável após rendering é problema.

### BR-GEO-021 - Rotas indexáveis client-side devem funcionar por acesso direto à URL

A rota relevante deve resolver quando acessada diretamente, não apenas após navegação interna da SPA.

### BR-GEO-022 - Navegação interna importante deve expor destinos rastreáveis

Links relevantes devem expor destinos tecnicamente recuperáveis.

### BR-GEO-023 - Roteamento client-side não deve criar estados enganosos de soft 404

Especialmente relevante para SPA.

### BR-GEO-024 - Lazy loading não deve impedir recuperação de conteúdo essencial

Interação limitada e previsível pode ser utilizada; conteúdo essencial não deve depender de comportamento arbitrário não reproduzível.

## 7. Extração de conteúdo

### BR-GEO-025 - O conteúdo principal deve ser identificável

Identifica conteúdo principal com DOM, landmarks, densidade e sinais complementares.

### BR-GEO-026 - A página deve conter conteúdo significativo além de navegação e boilerplate

Não utiliza um mínimo universal e arbitrário de palavras.

### BR-GEO-027 - Informações essenciais devem sobreviver à extração sem perda material

Preserva, quando aplicável, moeda, unidade, data, labels, relações e texto relevante.

## 8. Estrutura semântica

### BR-GEO-028 - O título da página deve existir e ser semanticamente representativo

Combina evidência determinística e, quando disponível, avaliação semântica.

### BR-GEO-029 - O conteúdo principal deve expor hierarquia semântica compreensível

Múltiplos H1 não são automaticamente tratados como erro universal.

### BR-GEO-030 - O tópico principal e as seções relevantes devem ser identificáveis

Regra semântica. Evidência insuficiente deve tender a `UNKNOWN`, não a `FAIL` inventado.

## 9. Clareza de entidades

### BR-GEO-031 - A entidade primária deve ser identificável quando aplicável

Tipos técnicos podem incluir `ORGANIZATION`, `PERSON`, `PRODUCT`, `SERVICE`, `PLACE`, `BRAND`, `TOPIC` e `OTHER`.

### BR-GEO-032 - Tipos e relações importantes entre entidades devem possuir contexto suficiente

Exemplos conceituais: Product → Brand e Person → Organization.

### BR-GEO-033 - Ambiguidade material de entidades deve ser detectável

Finding somente quando a ambiguidade puder ser sustentada por evidência material.

## 10. Dados Estruturados

### BR-GEO-034 - Dados Estruturados devem ser sintaticamente interpretáveis quando presentes

Avalia parsing, `@context`, `@type` e estrutura observada.

### BR-GEO-035 - Tipos e propriedades relevantes de Dados Estruturados devem ser identificáveis

Identifica tipos e propriedades persistidos.

### BR-GEO-036 - Dados Estruturados devem permanecer coerentes com o conteúdo visível

Compara markup com valores e conteúdo observável na página.

### BR-GEO-037 - Entidades dos Dados Estruturados devem ser coerentes com as entidades observadas

Compara entidades declaradas e observadas. Ausência de Dados Estruturados não implica `FAIL` automático.

## 11. Capacidade de resposta

### BR-GEO-038 - A intenção principal do usuário deve ser identificável

Classifica a intenção principal somente quando sustentada por evidência.

### BR-GEO-039 - Perguntas primárias relevantes devem receber resposta explícita quando aplicável

Estados técnicos:

```text
ANSWERED
PARTIALLY_ANSWERED
NOT_ANSWERED
UNKNOWN
```

### BR-GEO-040 - Respostas devem conter contexto suficiente

A resposta observada deve ser compreensível e contextualizada.

## 12. Preparação para citação

### BR-GEO-041 - Claims factuais materiais devem ser explicitamente identificáveis

Distingue afirmações factuais de frases puramente promocionais.

### BR-GEO-042 - Afirmações factuais devem conter contexto factual suficiente

Avalia quem, o quê, quanto, quando e demais qualificadores quando aplicáveis.

### BR-GEO-043 - Claims numéricos, temporais e quantitativos devem incluir qualificadores necessários

Avalia números, unidades, moeda, porcentagem, data, duração e período.

### BR-GEO-044 - Informações importantes devem ser compreensíveis sem inferência excessiva

Não exige que toda frase funcione isoladamente; exige contexto suficiente para a informação material.

## 13. Evidência e confiança

### BR-GEO-045 - Claims materiais devem expor atribuição ou evidência de suporte apropriada quando necessário

A aplicabilidade depende do tipo de claim e do contexto observado.

### BR-GEO-046 - Publicador, autor ou entidade responsável deve ser identificável quando relevante

A aplicabilidade depende do tipo e propósito da página; autoria não é requisito mecânico universal.

### BR-GEO-047 - Sinais de publicação e atualização devem permanecer internamente coerentes

Compara data visível, `datePublished`, `dateModified`, sitemap `lastmod` e HTTP `Last-Modified` sem presumir equivalência rígida entre fontes.

## 14. Cobertura de intenções

### BR-GEO-048 - Intenções primária e secundárias relevantes devem estar representadas

Baseline semântico atual:

- uma intenção primária;
- até cinco intenções secundárias.

### BR-GEO-049 - Lacunas materiais de cobertura de intenção devem ser sustentadas por evidência

Estados técnicos:

```text
COVERED
PARTIALLY_COVERED
NOT_COVERED
UNKNOWN
```

## 15. Links internos e duplicidade

### BR-GEO-050 - Links internos devem expor destinos tecnicamente utilizáveis

Avalia `href`, normalização, status e destino.

### BR-GEO-051 - Páginas materialmente duplicadas ou quase duplicadas devem ser identificáveis

A avaliação é limitada ao universo efetivamente auditado.

## 16. Desktop × Mobile

### BR-GEO-052 - Diferenças materiais entre Desktop e Mobile devem ser detectadas e classificadas explicitamente

Compara HTTP, redirects, canonical, robots, título, headings, conteúdo, links, Dados Estruturados, entidades e avaliações semânticas.

Estados técnicos:

```text
SAME
DIFFERENT
NOT_APPLICABLE
UNKNOWN
```

Diferença entre dispositivos não implica automaticamente problema.

## 17. Integridade do auditor

### BR-GEO-053 - Todo finding deve ser integralmente rastreável

Um finding válido deve possuir vínculo coerente com `RuleExecution`, Rule e Evidence.

### BR-GEO-054 - Todo score deve ser reproduzível e considerar confiabilidade

O score deve ser reconstruível a partir de ruleset, `scoring_version`, contribuições e evidências persistidas.

### BR-GEO-055 - Avaliação evidence-bound de sitemap pode refinar o grupo `SITEMAP`

Regra opcional, `HEURISTIC` e dependente de IA técnica explicitamente habilitada. Recebe somente IDs de evidência persistidos do recurso sitemap, produz verdict `POSITIVE`, `NEUTRAL` ou `NEGATIVE` e nunca escolhe peso numérico. Compartilha o grupo `SITEMAP` e o peso da BR-GEO-003; resultado positivo não soma bônus e baixa confiança do provider não pode produzir `PASS`/`FAIL` duro.

### BR-GEO-056 - Avaliação evidence-bound de robots pode refinar o grupo `ROBOTS`

Regra opcional, `HEURISTIC` e dependente de IA técnica explicitamente habilitada. Recebe somente IDs de evidência persistidos de `robots.txt`, produz verdict `POSITIVE`, `NEUTRAL` ou `NEGATIVE` e nunca escolhe peso numérico. Compartilha o grupo `ROBOTS` e o peso das BR-GEO-017/018; resultado positivo não soma bônus e baixa confiança do provider não pode produzir `PASS`/`FAIL` duro.

## 18. Content Value

As regras `BR-GEO-057..059` são materializadas pelo baseline `CONTENT-VALUE-BASELINE-001`, com `rule_version = 1`. Elas formam a dimensão `CONTENT_VALUE` e são classificadas como heurísticas internas do RASAi. Não medem “originalidade” ou “utilidade” como fatos universais; concluem somente o que pode ser sustentado pelo conteúdo principal persistido.

### BR-GEO-057 - Utilidade e especificidade do conteúdo

Sinais efetivamente usados pelo runtime incluem contagem de caracteres, sentenças, palavras e diversidade lexical.

Contrato vigente:

| Condição observada | Resultado | Reason code |
|---|---|---|
| conteúdo principal ausente | `UNKNOWN` | `CONTENT_VALUE_INPUT_UNAVAILABLE` |
| caracteres >= 800, sentenças >= 5, palavras >= 120 e diversidade lexical >= 0,22 | `PASS` | `BASELINE_USEFULNESS_SIGNALS_SUFFICIENT` |
| caracteres >= 300 e sentenças >= 2 | `WARNING` | `BASELINE_USEFULNESS_SIGNALS_LIMITED` |
| conteúdo disponível abaixo dos critérios anteriores | `WARNING` | `BASELINE_CONTENT_SUBSTANTIALLY_THIN` |

Esses limiares são **valores metodológicos fixos da implementação vigente**, não parâmetros configuráveis pelo usuário. Não devem ser descritos como requisito oficial de mecanismo de busca nem como mínimo universal de conteúdo.

### BR-GEO-058 - Diferenciação, experiência, análise ou dados first-party explicitamente demonstrados

O runtime procura sinais textuais explícitos de pesquisa, análise, metodologia, experiência, dados, estudo, teste, medição ou ações equivalentes em primeira pessoa, em português ou inglês.

Contrato vigente:

| Condição observada | Resultado | Reason code |
|---|---|---|
| existe sinal first-party explícito reconhecido | `PASS` | `EXPLICIT_FIRST_PARTY_DIFFERENTIATION_SIGNAL` |
| não é possível provar diferenciação pela evidência local | `UNKNOWN` | `DIFFERENTIATION_NOT_PROVABLE_FROM_LOCAL_EVIDENCE` |

A ausência de sinal explícito **não vira `FAIL`**. O RASAi não presume falta de originalidade, experiência ou diferenciação quando não pode demonstrá-la.

### BR-GEO-059 - Profundidade e contexto proporcionais

Sinais efetivamente usados pelo runtime incluem caracteres, sentenças e parágrafos do conteúdo principal persistido.

Contrato vigente:

| Condição observada | Resultado | Reason code |
|---|---|---|
| conteúdo principal ausente | `UNKNOWN` | `CONTENT_VALUE_INPUT_UNAVAILABLE` |
| caracteres >= 1.400, sentenças >= 8 e parágrafos >= 3 | `PASS` | `BASELINE_DEPTH_SIGNALS_SUFFICIENT` |
| caracteres >= 600 e sentenças >= 4 | `WARNING` | `BASELINE_DEPTH_SIGNALS_MODERATE` |
| conteúdo disponível sem base conclusiva pelos critérios anteriores | `UNKNOWN` | `DEPTH_NOT_CONCLUSIVELY_MEASURABLE_FROM_LOCAL_EVIDENCE` |

Esses limiares são **valores metodológicos fixos da versão vigente**, não recomendação universal de tamanho de texto nem configuração pública.

## 19. Dependências e bloqueios

Antes de executar uma regra, o pipeline deve resolver, conforme o contrato da família:

1. aplicabilidade;
2. dependências;
3. bloqueios/pré-requisitos;
4. execução;
5. persistência de `RuleExecution`.

Falha de pré-requisito não deve provocar múltiplos `FAIL` derivados sem evidência.

Exemplo:

```text
HTTP 500
→ finding técnico

regras semânticas dependentes
→ NOT_APPLICABLE bloqueado, UNKNOWN ou outro estado previsto pelo contrato
```

Nunca inferir automaticamente:

```text
HTTP 500 + sem entidade + sem resposta + sem intenção + baixa preparação para citação
```

## 20. IA e fallback

A análise semântica possui dois caminhos de evidência, preservando a mesma camada posterior de scoring:

```text
baseline local: SEMANTIC-BASELINE-001
provider externo: opcional
```

### `NO_AI` / provider não configurado

O baseline determinístico executa primeiro os critérios sustentáveis por evidência persistida do snapshot, como título, headings, conteúdo principal, links e Dados Estruturados.

Política:

- `PASS` somente com evidência positiva suficiente;
- `NOT_APPLICABLE` somente quando a aplicabilidade puder ser resolvida de forma defensável;
- ausência de evidência não vira `PASS`;
- ausência de evidência não vira `FAIL`;
- critério não resolvido permanece `UNKNOWN`.

`NO_AI` não significa automaticamente baixa Coverage. A auditoria pode ser consolidada sem IA quando os grupos aplicáveis forem suficientemente medidos e os gates do `SCORE-GEO-004` forem satisfeitos.

### Provider configurado

Uma resposta válida e evidence-bound pode aprofundar avaliação semântica. Fatos determinísticos fortes mantêm precedência. Falha do provider permanece estado operacional (`AI_PROVIDER_UNAVAILABLE`) quando não há resultado válido e nunca é convertida em `FAIL` do website.

### Proveniência

Avaliações do baseline semântico são persistidas com os identificadores técnicos definidos pelo runtime, incluindo:

```text
provider = DETERMINISTIC_BASELINE
configuration_version = SEMANTIC-BASELINE-001
rule_version = 2
```

A capability `semantic_baseline:SEMANTIC-BASELINE-001` identifica auditorias em que o baseline foi efetivamente utilizado.

## 21. Tipo de base metodológica

Toda regra deve indicar, quando aplicável, um tipo de base canônico:

```text
OFFICIAL
STANDARD
HEURISTIC
EXPERIMENTAL
```

Regras específicas de mecanismo devem indicar também `engine_scope`. O rótulo `HEURISTIC` identifica método interno do RASAi e não pode ser apresentado como requisito oficial de Google, OpenAI, Microsoft ou outro fornecedor.