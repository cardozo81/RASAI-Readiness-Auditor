# GEO_MINIMUM_REQUIREMENTS.md

## Escopo

Este documento separa:

1. requisitos/práticas suportadas por documentação oficial ou standards;
2. reforços úteis do SearchGEO;
3. heurísticas internas que não devem ser apresentadas como padrão GEO universal.

## Não existe um padrão GEO/AEO universal

O SearchGEO não assume que exista uma especificação normativa única denominada GEO/AEO.

Em 2026, o Google publicou o guia oficial:

**Optimizing your website for generative AI features on Google Search**
<https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>

O guia deixa claro que AEO/GEO são termos utilizados pelo mercado e que, do ponto de vista do Google, otimização para recursos generativos continua baseada em SEO.

## Requisitos/práticas fundamentais

### Acesso técnico

O conteúdo precisa ser tecnicamente recuperável e elegível conforme o crawler/sistema em questão.

Fontes relevantes:

- Google Search Essentials;
- RFC 9110;
- RFC 9309;
- Google robots.txt specification;
- OpenAI Publishers and Developers FAQ para controles OAI-SearchBot/GPTBot.

### Conteúdo útil, confiável e orientado a pessoas

O Google continua recomendando conteúdo útil, confiável e people-first. O SearchGEO pode medir sinais de clareza, resposta, atribuição e evidência, mas não deve traduzir isso em uma fórmula oficial inexistente.

### Estrutura compreensível

HTML/heading structure, títulos claros e organização lógica ajudam mecanismos e usuários. WHATWG define semântica HTML; o SearchGEO adiciona heurísticas de legibilidade semântica sobre essa base.

### Indexabilidade/canonicalização

Diretivas, canonical e conflitos técnicos continuam relevantes conforme Google Search Central e protocolos web aplicáveis.

## O que NÃO é requisito universal

### Structured Data / JSON-LD

Structured Data não é requisito universal para recursos generativos do Google. O próprio guia de 2026 não exige marcação especial de IA.

No `SCORE-GEO-002`:

- ausência legítima pode resultar em `STRUCTURED_DATA = NOT_APPLICABLE`;
- a dimensão fica fora do Overall;
- markup existente, porém inválido/contraditório, pode ser avaliado negativamente.

### `llms.txt`

O Google informa que `llms.txt` não é necessário para seus recursos generativos e não é usado como sinal de ranking/visibilidade no Google Search.

O SearchGEO não deve tratá-lo como blocker obrigatório.

### “GEO schema” especial

Não existe markup especial oficial de GEO/AEO exigido pelo Google.

### Chunking artificial

Não existe exigência oficial de quebrar o conteúdo em blocos artificiais apenas para modelos de IA.

### Reescrever conteúdo apenas para IA

O Google não recomenda reescrever conteúdo para “falar com IA” em detrimento de pessoas. O SearchGEO deve orientar melhoria de clareza/utilidade/evidência quando um finding específico sustentar a necessidade, não produzir conteúdo artificial apenas para elevar uma métrica interna.

## Heurísticas SearchGEO

Dimensões como:

- Entity Clarity;
- Answerability;
- Citation Readiness;
- Evidence Trust;
- Intent Coverage;

são úteis como modelo operacional de readiness, mas parte de suas regras é `HEURISTIC`/baseline interna.

A página gerada:

```text
report/references.html
```

expõe essa distinção por regra.

## Confidence não é aderência textual

`Confidence LOW` no SCORE-GEO-002 significa baixa força da conclusão do auditor. Não significa que o conteúdo é semanticamente inválido.

Uma recomendação de conteúdo deve ser motivada por evidência/regra específica, não pela Confidence isolada.

## Mobile first operacional

A CLI usa Mobile por padrão:

```text
--device-context mobile
```

Isso é uma decisão operacional/custo do auditor, não uma afirmação de que Desktop é irrelevante para Search. Use `both` quando a análise comparativa for necessária.

## Referências primárias principais

- Google generative AI optimization guide: <https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>
- Google Search Essentials: <https://developers.google.com/search/docs/essentials>
- Google SEO Starter Guide: <https://developers.google.com/search/docs/fundamentals/seo-starter-guide>
- Google Structured Data: <https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data>
- Google canonicalization: <https://developers.google.com/search/docs/crawling-indexing/canonicalization>
- Google robots.txt: <https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec>
- OpenAI Publishers and Developers FAQ: <https://help.openai.com/en/articles/12627856-publishers-and-developers-faq>
- Schema.org: <https://schema.org/docs/documents.html>
- WHATWG sections: <https://html.spec.whatwg.org/dev/sections.html>
- RFC 9309: <https://www.rfc-editor.org/rfc/rfc9309.html>
- RFC 9110: <https://www.rfc-editor.org/rfc/rfc9110.html>

O catálogo do report site é versionado pela data de verificação do código. URLs devem ser revisitadas quando regras externas forem revisadas.
