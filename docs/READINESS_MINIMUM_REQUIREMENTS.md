# Requisitos mínimos e fundamentos de Readiness

**Estado:** vigente.

## Escopo

Este documento separa:

1. requisitos/práticas sustentadas por documentação oficial ou standards;
2. sinais complementares úteis;
3. heurísticas RASAi que não devem ser apresentadas como padrão GEO/AEO universal.

## Não existe um padrão GEO/AEO universal

O RASAi não assume que exista uma especificação normativa única denominada GEO/AEO.

O Google mantém um guia oficial para otimização de websites para recursos de IA generativa em Google Search:

<https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>

Esse material deve ser lido como orientação do Google para seus próprios recursos de Search. Ele não transforma GEO/AEO em standard universal nem homologa o SARI.

## Princípio do SARI

O SARI-001 não transforma toda recomendação externa em requisito de mesmo peso.

O contrato vigente separa:

- condições fundamentais de acesso, indexabilidade e extração;
- compreensão semântica;
- utilidade/intenção do conteúdo;
- evidência/confiança/citation readiness;
- Structured Data quando aplicável;
- métricas externas e resultados que permanecem fora da aritmética, salvo regra explicitamente score-eligible.

Por isso o SARI usa pesos diferentes e Critical Readiness Gates em vez de uma média uniforme entre dimensões.

## Requisitos/práticas fundamentais

### Discovery & Crawler Access

O conteúdo precisa ser tecnicamente recuperável e os controles de crawler precisam ser interpretáveis no escopo configurado.

Fontes relevantes:

- Google Search Essentials - requisitos técnicos, políticas e práticas fundamentais para participação em Google Search: <https://developers.google.com/search/docs/essentials>
- RFC 9110 - semântica e contrato do HTTP, incluindo status, métodos e comportamento de respostas: <https://www.rfc-editor.org/rfc/rfc9110.html>
- RFC 9309 - standard IETF para o Robots Exclusion Protocol e interpretação de `robots.txt`: <https://www.rfc-editor.org/rfc/rfc9309.html>
- documentação Google de `robots.txt` - comportamento do Googlebot e sintaxe suportada: <https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec>
- OpenAI Publishers and Developers FAQ - orientação atual sobre OAI-SearchBot, GPTBot e controles de publicação para superfícies OpenAI: <https://help.openai.com/en/articles/12627856-publishers-and-developers-faq>

No SARI, falhas materiais desta camada são expostas também pelo **Discovery Gate**.

### Indexabilidade e canonicalização

Diretivas de indexação, canonical e conflitos técnicos são avaliados separadamente de qualidade de conteúdo.

Referência primária do Google para canonicalização: <https://developers.google.com/search/docs/crawling-indexing/canonicalization>. O documento descreve sinais e práticas usados pelo Google para seleção de URL canônica; não define uma regra universal para todos os mecanismos.

No SARI, condições materiais desta camada aparecem também no **Indexability Gate**.

### Rendering e extractability

O conteúdo principal precisa permanecer recuperável e analisável no estado técnico relevante. JavaScript, SPA e lazy loading não são problemas por si só; tornam-se problema quando impedem recuperação do conteúdo necessário.

No SARI, condições materiais aparecem também no **Extraction Gate**.

### Conteúdo útil, confiável e orientado a pessoas

O Google recomenda conteúdo útil, confiável e people-first em sua documentação de criação de conteúdo: <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>.

O RASAi usa essa base conceitual, mas não a apresenta como uma fórmula oficial externa.

A dimensão `CONTENT_VALUE` é `RASAI_HEURISTIC` e mede somente sinais sustentados por evidência persistida:

- utilidade/especificidade não trivial;
- diferenciação, análise, experiência ou dados próprios explicitamente demonstrados quando alegados;
- profundidade/contexto proporcionais ao conteúdo disponível.

Ausência de prova de diferenciação/originalidade **não vira FAIL**; permanece `UNKNOWN` quando o auditor não consegue concluir defensavelmente.

### Estrutura compreensível

HTML semântico, headings, título e organização lógica ajudam usuários e sistemas. O WHATWG HTML Living Standard define a semântica dos elementos e a estrutura dos documentos: <https://html.spec.whatwg.org/dev/sections.html>.

Critérios de clareza/interpretabilidade adicionados pelo RASAi são identificados como heurística quando não existe regra normativa externa equivalente.

### Evidência e responsabilidade

Para claims em que atribuição, responsabilidade ou atualização são materialmente relevantes, o RASAi pode avaliar sinais de autoria/publisher, contexto factual, qualificadores, datas e suporte explícito.

Isso não cria um “E-E-A-T Score oficial”.

## O que NÃO é requisito universal

### Structured Data / JSON-LD

Structured Data não é requisito universal para recursos generativos e não existe markup especial obrigatório de IA.

A introdução oficial do Google a Structured Data explica como markup pode habilitar e qualificar recursos de apresentação em Google Search: <https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data>.

Schema.org mantém o vocabulário aberto utilizado por muitas implementações de dados estruturados: <https://schema.org/docs/documents.html>.

No SARI vigente:

- Structured Data representa **5%** do contrato quando aplicável;
- ausência legítima é tratada como não aplicável para a aritmética;
- markup existente inválido/contraditório pode ser desfavorável;
- propriedades não devem ser inventadas apenas para elevar o índice.

### Lighthouse score

Nenhum **category score** Lighthouse é requisito SARI:

- Performance;
- Accessibility;
- Best Practices;
- SEO.

Esses scores permanecem métricas externas independentes. Um audit técnico individual só pode atuar como evidência corroborativa quando existir mapeamento explícito para a mesma condição de uma BR-GEO, sem dupla pontuação.

### Core Web Vitals / CrUX

Core Web Vitals permanecem métricas externas de experiência. Não são convertidas diretamente em SARI. Se um problema de entrega impedir rendering/extraction, a consequência técnica é avaliada pela regra SARI correspondente, evitando dupla penalização.

### Common Crawl

Common Crawl não é fonte normativa de qualidade ou ranking. No contrato vigente, sua participação no SARI é restrita à `BR-GEO-060`, como corroboração externa **somente positiva** de descoberta observada. Ausência de registro, erro ou indisponibilidade não geram `FAIL`, zero ou redução de Coverage/Confidence.

Detalhes: [SARI_EXTERNAL_CRAWL_CORROBORATION.md](SARI_EXTERNAL_CRAWL_CORROBORATION.md).

### `llms.txt`

Não é blocker universal. Não deve ser promovido a requisito central sem evidência/contrato específico por engine.

### “GEO schema” especial

Não existe markup oficial universal obrigatório de GEO/AEO.

### Chunking artificial

Não existe requisito oficial universal para quebrar conteúdo em blocos artificiais apenas para modelos de IA.

### Reescrever conteúdo apenas para IA

O RASAi deve recomendar melhoria quando houver finding/evidência específica, não criar texto artificial apenas para elevar uma métrica interna.

## Heurísticas RASAi

Entre as famílias que contêm heurísticas internas estão:

- Entity Clarity;
- Answerability;
- Citation Readiness;
- Evidence & Trust;
- Intent Coverage;
- Content Value;
- pesos, thresholds, Coverage, Confidence, Consolidation e Critical Gates.

`report-catalog/methodology.html` deve expor a natureza metodológica e a função de cada indicador no SARI.

## Score, Confidence e Critical Gate são coisas diferentes

```text
Score         = qualidade do universo efetivamente medido
Coverage      = completude ponderada da medição
Confidence    = força da medição
Consolidation = suficiência para publicar a conclusão
Critical Gate = existência de condição fundamental PASS/WARNING/BLOCKED/UNKNOWN
```

Logo, um SARI alto pode coexistir com `BLOCKED` quando existe um problema crítico localizado, e um SARI baixo pode estar `CONSOLIDATED` quando a baixa qualidade foi medida com evidência suficiente.

## Mobile first operacional

A CLI usa Mobile por padrão:

```text
--device-context mobile
```

Isso é decisão operacional/custo do auditor, não afirmação de que Desktop seja irrelevante. Use `both` quando a comparação for necessária.

## Referências primárias principais

| Fonte | Função no RASAi | Link |
|---|---|---|
| Google - otimização para recursos generativos em Search | orientação específica do Google para Search com recursos de IA; não é standard universal GEO/AEO | <https://developers.google.com/search/docs/fundamentals/ai-optimization-guide> |
| Google Search Essentials | requisitos e práticas fundamentais do Google Search | <https://developers.google.com/search/docs/essentials> |
| Google SEO Starter Guide | orientação introdutória de SEO técnico/editorial do Google | <https://developers.google.com/search/docs/fundamentals/seo-starter-guide> |
| Google - conteúdo útil e people-first | princípios editoriais oficiais usados como referência conceitual, não como fórmula de scoring | <https://developers.google.com/search/docs/fundamentals/creating-helpful-content> |
| Google Structured Data | finalidade e regras gerais de Structured Data no Google Search | <https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data> |
| Google canonicalization | sinais e práticas de canonicalização no Google Search | <https://developers.google.com/search/docs/crawling-indexing/canonicalization> |
| Google robots.txt | sintaxe e comportamento documentados para crawlers Google | <https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec> |
| OpenAI Publishers and Developers FAQ | controles de crawler e publicação aplicáveis a OAI-SearchBot/GPTBot e superfícies OpenAI | <https://help.openai.com/en/articles/12627856-publishers-and-developers-faq> |
| Schema.org | vocabulário compartilhado de dados estruturados | <https://schema.org/docs/documents.html> |
| WHATWG HTML Living Standard | semântica e estrutura normativa do HTML | <https://html.spec.whatwg.org/dev/sections.html> |
| RFC 9309 | standard IETF do Robots Exclusion Protocol | <https://www.rfc-editor.org/rfc/rfc9309.html> |
| RFC 9110 | semântica HTTP e interpretação de respostas | <https://www.rfc-editor.org/rfc/rfc9110.html> |

As URLs e interpretações externas devem ser revisadas periodicamente. A fonte externa valida apenas o fenômeno no escopo documentado; não homologa o SARI composto.
