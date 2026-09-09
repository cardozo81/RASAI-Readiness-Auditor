# READINESS_MINIMUM_REQUIREMENTS.md

## Escopo

Este documento separa:

1. requisitos/práticas sustentadas por documentação oficial ou standards;
2. sinais complementares úteis;
3. heurísticas RASAi que não devem ser apresentadas como padrão GEO/AEO universal.

## Não existe um padrão GEO/AEO universal

O RASAi não assume que exista uma especificação normativa única denominada GEO/AEO.

Em 2026, o Google publicou o guia oficial **Optimizing your website for generative AI features on Google Search**:

<https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>

O guia trata AEO/GEO como termos de mercado e mantém SEO, conteúdo útil e acesso técnico como fundamentos para recursos generativos do Google Search.

## Princípio do SARI

O SARI-001 não transforma toda recomendação externa em requisito de mesmo peso.

O contrato vigente separa:

- condições fundamentais de acesso, indexabilidade e extração;
- compreensão semântica;
- utilidade/intenção do conteúdo;
- evidência/confiança/citation readiness;
- Structured Data quando aplicável;
- métricas externas e outcomes que permanecem fora da aritmética.

Por isso o SARI usa pesos diferentes e Critical Readiness Gates em vez de uma média uniforme entre dimensões.

## Requisitos/práticas fundamentais

### Discovery & Crawler Access

O conteúdo precisa ser tecnicamente recuperável e os controles de crawler precisam ser interpretáveis no escopo configurado.

Fontes relevantes:

- Google Search Essentials;
- RFC 9110;
- RFC 9309;
- documentação Google para robots.txt;
- documentação OpenAI para controles de crawlers aplicáveis.

No SARI, falhas materiais desta camada são expostas também pelo **Discovery Gate**.

### Indexabilidade e canonicalização

Diretivas de indexação, canonical e conflitos técnicos são avaliados separadamente de qualidade de conteúdo.

No SARI, condições materiais desta camada aparecem também no **Indexability Gate**.

### Rendering e extractability

O conteúdo principal precisa permanecer recuperável e analisável no estado técnico relevante. JavaScript, SPA e lazy loading não são problemas por si só; tornam-se problema quando impedem recuperação do conteúdo necessário.

No SARI, condições materiais aparecem também no **Extraction Gate**.

### Conteúdo útil, confiável e orientado a pessoas

O Google recomenda conteúdo útil, confiável e people-first. O RASAi usa essa base conceitual, mas não a apresenta como uma fórmula oficial externa.

A dimensão `CONTENT_VALUE` é `RASAI_HEURISTIC` e mede somente sinais sustentados por evidência persistida:

- utilidade/especificidade não trivial;
- diferenciação, análise, experiência ou dados próprios explicitamente demonstrados quando alegados;
- profundidade/contexto proporcionais ao conteúdo disponível.

Ausência de prova de diferenciação/originalidade **não vira FAIL**; permanece `UNKNOWN` quando o auditor não consegue concluir defensavelmente.

### Estrutura compreensível

HTML semântico, headings, título e organização lógica ajudam usuários e sistemas. WHATWG fornece a base de semântica HTML; critérios de clareza/interpretabilidade adicionados pelo RASAi são identificados como heurística quando não existe regra normativa externa equivalente.

### Evidência e responsabilidade

Para claims em que atribuição, responsabilidade ou atualização são materialmente relevantes, o RASAi pode avaliar sinais de autoria/publisher, contexto factual, qualificadores, datas e suporte explícito.

Isso não cria um “E-E-A-T Score oficial”.

## O que NÃO é requisito universal

### Structured Data / JSON-LD

Structured Data não é requisito universal para recursos generativos do Google e não existe markup especial obrigatório de IA.

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

`report/references.html` deve expor a natureza metodológica e a função de cada indicador no SARI.

## Score, Confidence e Critical Gate são coisas diferentes

```text
Score       = qualidade do universo efetivamente medido
Coverage    = completude ponderada da medição
Confidence  = força da medição
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

- Google generative AI optimization guide: <https://developers.google.com/search/docs/fundamentals/ai-optimization-guide>
- Google Search Essentials: <https://developers.google.com/search/docs/essentials>
- Google SEO Starter Guide: <https://developers.google.com/search/docs/fundamentals/seo-starter-guide>
- Google helpful content guidance: <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>
- Google Structured Data: <https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data>
- Google canonicalization: <https://developers.google.com/search/docs/crawling-indexing/canonicalization>
- Google robots.txt: <https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec>
- OpenAI Publishers and Developers FAQ: <https://help.openai.com/en/articles/12627856-publishers-and-developers-faq>
- Schema.org: <https://schema.org/docs/documents.html>
- WHATWG sections: <https://html.spec.whatwg.org/dev/sections.html>
- RFC 9309: <https://www.rfc-editor.org/rfc/rfc9309.html>
- RFC 9110: <https://www.rfc-editor.org/rfc/rfc9110.html>

As URLs e interpretações externas devem ser revisadas periodicamente. A fonte externa valida apenas o fenômeno no escopo documentado; não homologa o SARI composto.