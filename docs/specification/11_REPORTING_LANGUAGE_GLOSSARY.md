# REPORTING_LANGUAGE_GLOSSARY.md

**Estado no baseline de desenvolvimento:** vigente.

Este documento define a linguagem pública dos reports HTML do RASAi. Persistência, enums, IDs de regra e contratos internos permanecem canônicos no código/banco; a interface principal deve priorizar leitura humana.

## 1. Regra editorial

O texto explicativo destinado ao usuário é prioritariamente em português do Brasil.

Termos conceituais/técnicos consolidados permanecem em inglês quando a tradução reduzir precisão, criar nomenclatura artificial ou divergir do uso corrente da disciplina.

Exemplos que devem permanecer em inglês na leitura principal:

- Search & AI Readiness;
- Overall Readiness;
- Discovery & Crawler Access;
- Indexability;
- Rendering & Extractability;
- Semantic Structure;
- Entity Clarity;
- Structured Data;
- Answerability;
- Citation Readiness;
- Evidence & Trust;
- Intent Coverage;
- Content Value;
- Core Web Vitals;
- Lighthouse;
- Lighthouse Performance;
- CrUX / Chrome UX Report;
- Apdex;
- RUM;
- JSON-LD;
- canonical;
- robots.txt;
- Sitemap;
- SPA, SSR e CSR.

Estados operacionais, mensagens, ações e explicações permanecem em linguagem humana pt-BR.

## 2. Identificador interno x rótulo público

Enums internos não devem aparecer como rótulo visual principal.

Exemplos:

| Persistido/interno | Rótulo público principal |
|---|---|
| `DISCOVERY_ACCESS` | Discovery & Crawler Access |
| `INDEXABILITY` | Indexability |
| `CONTENT_EXTRACTABILITY` | Rendering & Extractability |
| `SEMANTIC_STRUCTURE` | Semantic Structure |
| `ENTITY_CLARITY` | Entity Clarity |
| `STRUCTURED_DATA` | Structured Data |
| `ANSWERABILITY` | Answerability |
| `CITATION_READINESS` | Citation Readiness |
| `EVIDENCE_TRUST` | Evidence & Trust |
| `INTENT_COVERAGE` | Intent Coverage |
| `CONTENT_VALUE` | Content Value |
| `OVERALL_READINESS` | Overall Readiness |

O mesmo princípio vale para `scoring_group`:

```text
PAGE_ACCESS                  -> Page Access
INDEX_DIRECTIVES             -> Index Directives
STRUCTURED_DATA_SYNTAX       -> Structured Data Syntax
STRUCTURED_DATA_CONSISTENCY  -> Structured Data Consistency
CONTENT_USEFULNESS           -> Content Usefulness
CONTENT_DIFFERENTIATION      -> Content Differentiation
CONTENT_DEPTH                -> Content Depth
```

Quando o ID técnico for útil para auditoria/rastreabilidade, ele pode aparecer de forma secundária em `<code>`, detalhes técnicos, tooltip ou metadado. O nome humano/conceitual continua sendo o texto principal.

## 3. Identificadores metodológicos

IDs como:

```text
SCORE-GEO-004
SARI-001
HIERARCHICAL_WEIGHTED_READINESS_V1
SARI_DIMENSION_WEIGHTS_V1
SARI_GROUP_WEIGHTS_V1
SARI_CRITICAL_GATES_V1
```

são válidos como versão, contrato, metadado ou rastreabilidade técnica.

Eles não devem substituir um título humano quando o contexto for de navegação/leitura. Exemplo:

```text
Hierarchical Weighted Readiness
```

pode ser o título; o ID canônico pode aparecer ao lado em `<code>`.

## 4. Estados operacionais

Estados persistidos devem ser apresentados em pt-BR quando aparecem como valor primário:

| Interno | Exibição |
|---|---|
| `PASS` | Aprovado |
| `FAIL` | Não aprovado / problema identificado conforme contexto |
| `WARNING` | Alerta |
| `UNKNOWN` | Não determinado |
| `NOT_APPLICABLE` | Não aplicável |
| `CONSOLIDATED` | Consolidado |
| `NOT_CONSOLIDATED` | Não consolidado |
| `PARTIAL` | Parcial |
| `UNAVAILABLE` | Indisponível |
| `BLOCKED` | Bloqueado |
| `ATTENTION` | Atenção |
| `READY` | Pronto |
| `DISABLED` | Desabilitado |
| `REGRESSED` | Regrediu |
| `IMPROVED` | Melhorou |
| `RESOLVED` | Resolvido |
| `NOT_OBSERVED` | Não observado |
| `DATA_UNAVAILABLE` | Dados indisponíveis |

`UNKNOWN`, `UNAVAILABLE` e `NOT_CONSOLIDATED` nunca devem ser transformados em zero ou `FAIL` artificial.

## 5. Blocos técnicos preservados

A camada de humanização não deve reescrever conteúdo destinado explicitamente à rastreabilidade, por exemplo:

- `<code>`;
- `<pre>`;
- IDs `BR-GEO-*`;
- nomes de variáveis como `RASAI_*`;
- nomes de campos persistidos;
- payloads/JSON de diagnóstico;
- versões/contratos quando apresentados como metadados;
- timestamps canônicos usados como exemplo técnico.

Isso permite uma UI humana sem destruir a capacidade de suporte/auditoria.

## 6. Semântica visual

Cor reforça o estado, mas nunca substitui texto.

Referência geral:

- sucesso/aprovado/resultado forte: verde;
- atenção/configuração necessária: amarelo;
- problema relevante: laranja quando a superfície usar essa gradação;
- erro/crítico/bloqueio: vermelho;
- não determinado/inativo/desabilitado: cinza;
- informação metodológica/contextual: azul/ciano conforme a superfície.

No console de IA, especificamente:

```text
APTO / ativo / incluído no AUTO -> verde
CONFIGURAR                       -> amarelo
INDISPONÍVEL                     -> vermelho
DESABILITADA / ausente / excluído do AUTO -> cinza/dim
```

## 7. Navegação e contraste

O menu dos reports usa navegação escura. Elementos `<details>` usados para agrupamento do menu devem receber estilo escopado ao contêiner de navegação.

Não alterar o `details` global apenas para corrigir o menu, porque outras seções do report usam o mesmo elemento em conteúdo claro.

Contrato visual:

```css
.app-nav .rasai-nav-group
```

ou seletor equivalente escopado à navegação.

## 8. Uma URL x múltiplas URLs

Com uma única URL, a apresentação deve permanecer simples.

Com duas ou mais URLs distintas, a camada comum pode ativar filtros/segmentação/paginação local. Essa UI não remove evidência do HTML e não altera o dado persistido.

## 9. Conceitos externos

Preservar nomes oficiais e não misturar metodologias:

- Lighthouse = laboratório;
- CrUX/Core Web Vitals = field data agregado quando disponível;
- Apdex = metodologia própria de satisfação temporal;
- Synthetic Apdex do RASAi = medição sintética, não RUM;
- PageSpeed Insights = transporte/API externa; não é provider de IA;
- Accessibility do Lighthouse = evidência automatizada, não certificação WCAG integral.

Nunca usar linguagem como:

```text
Score GEO Lighthouse
Google confirmou o Score GEO
Core Web Vitals determinou a nota GEO
```

## 10. Readiness, Coverage e Confidence

Manter separados:

### Overall Readiness

Resultado agregado do contrato SARI/SCORE vigente quando consolidável.

### Coverage

Quanto do universo aplicável da medição foi efetivamente avaliado. Não é substituto do Overall Readiness e não equivale automaticamente à cobertura do domínio inteiro.

### Confidence

Força da medição baseada na evidência disponível e nos gates do método.

### Consolidation

Indica se Coverage/Confidence são suficientes para apresentar o resultado como consolidado.

Um valor numérico pode existir e ainda permanecer `Partial`/`Not Consolidated` sem contradição.

## 11. Remediação

A sequência preferida é:

```text
Página
Dispositivo
Regra
Severidade
Prioridade
Área/conceito
Alvo/local quando confiável
Problema encontrado
Valor observado
Correção recomendada
Critério de aceite
Como revalidar
Evidências
```

Nunca rotular conteúdo sugerido como conteúdo observado.

## 12. IA

Quando IA não estiver disponível:

`Algumas avaliações semânticas não foram executadas porque não havia um provider de IA disponível/configurado. Essa limitação reduz a cobertura quando a regra dependia dessa análise e não representa um problema do website.`

Quando IA externa for usada, provider/modelo podem ser indicados sem revelar credenciais.

A IA não “dá a nota SARI”; o scoring final permanece sob o contrato determinístico vigente.

## 13. Linguagem orientada ao analista

O HTML é destinado a profissionais de análise de dados, Search, SEO, AI Search e performance, não a desenvolvedores do RASAi.

Regras:

- apresentar o conceito antes do identificador interno;
- preservar inglês quando o termo é conceitual/padrão da disciplina;
- explicar em pt-BR estados e consequências;
- evitar enums com underscore na leitura principal;
- manter identificadores técnicos em áreas de suporte/rastreabilidade;
- não expor nomes históricos de etapas internas de desenvolvimento como vocabulário de produto.

## 14. Contrato de regressão

A camada comum `report_presentation` é a autoridade visual final para estados e conceitos compartilhados.

Toda dimensão e todo `scoring_group` vigente devem possuir rótulo público. Se uma nova dimensão/grupo for criada sem rótulo, o CI deve falhar.

A normalização deve ser idempotente: executar mais de uma vez não pode duplicar traduções, labels ou markup.
