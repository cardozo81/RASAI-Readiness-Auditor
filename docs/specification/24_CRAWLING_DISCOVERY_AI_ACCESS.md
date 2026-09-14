# Rastreamento, descoberta e acesso de crawlers

**Estado:** INTEGRADO / VIGENTE  
**Natureza:** diagnóstico técnico determinístico por padrão e non-scoring  
**Fronteira de scoring:** `SARI-001` / `SCORE-GEO-004`

## 1. Objetivo

Aprofundar evidências de `robots.txt`, sitemaps, políticas de crawlers, feeds, `llms.txt` experimental e sinais de discovery sem permitir pesos arbitrários. Robots/sitemap usam fatores estáticos do método e a IA opcional só pode corroborar ou rebaixar esses mesmos grupos dentro do contrato evidence-bound das regras correspondentes.

A capacidade não cria score paralelo e não recalcula arbitrariamente `SARI-001` ou `SCORE-GEO-004`.

## 2. Invariantes

1. execução determinística é a fonte de verdade dos diagnósticos técnicos;
2. LLM não escolhe pesos, thresholds, Score, Coverage, Confidence ou Consolidation; somente saída evidence-bound válida pode ser convertida pelo runtime nas regras limitadas BR-GEO-055/056;
3. diagnósticos próprios permanecem advisory com `scoring_impact=NONE`; quando BR-GEO-055/056 são materializadas, o estado persistido registra `BOUNDED_AI_RESOURCE_ASSESSMENT` sem expor nome físico de tabela interna como contrato público;
4. falha desta camada é fail-open em relação ao audit principal;
5. ausência de `llms.txt` não reduz readiness;
6. políticas de crawlers com finalidades diferentes não são tratadas como equivalentes;
7. evidência não observada não é inferida como configurada ou ausente;
8. nenhum diagnóstico externo ou experimental entra silenciosamente no `SCORE-GEO-004`.

## 3. Fontes de evidência

A camada reutiliza estado persistido do AUD e faz aquisição adicional somente onde o contrato permite, incluindo:

- evidências de robots/sitemap;
- páginas, respostas HTTP e snapshots;
- canonical/meta robots;
- recursos same-origin observados;
- `/llms.txt` same-origin quando seguro;
- provider configurado apenas se a remediação técnica por IA estiver explicitamente habilitada.

## 4. `robots.txt` e política de crawlers

A análise preserva grupos, `Allow`, `Disallow`, `Sitemap`, estado de aquisição e sintaxe relevante. Ausência legítima de `robots.txt` não vira bloqueio artificial.

Declarações `Sitemap:` cross-origin são preservadas como evidência, mas não são seguidas automaticamente. Essa é uma fronteira de segurança/escopo, não um finding do website.

Tokens de crawler/policy devem permanecer semanticamente separados. Search crawling, controles de treinamento/produto e demais usos não podem ser fundidos em uma única conclusão.

## 5. Sitemaps

Formatos suportados pelo runtime incluem XML `urlset`/index, gzip, RSS 2.0, Atom 1.0 e texto plano conforme implementação.

A análise pode considerar validade de URL, duplicatas, limites documentados, `lastmod`, extensões observadas e cruzamentos com respostas/indexabilidade/canonical/robots dentro da amostra auditada.

Sitemap é sinal de discovery/preference, não garantia de crawl, indexação ou ranking.

## 6. `llms.txt`, feeds e IndexNow

`llms.txt` é tratado como proposta comunitária experimental, não requisito universal. Presença pode ser analisada e persistida; ausência é informativa e non-scoring.

Feeds RSS/Atom são sinais complementares de discovery, não requisitos universais.

IndexNow só pode ser afirmado como observado quando existir evidência verificável. Auditoria passiva não deve inferir submissão bem-sucedida apenas pelo HTML público.

## 7. Remediação técnica opcional por IA

Controles públicos:

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_AI_TECHNICAL_REMEDIATION` | `false` | booleano | `false`; habilitar somente quando orientação advisory por IA for necessária |

A IA recebe somente diagnóstico/evidências persistidos, não inventa URL, policy, canonical, data ou crawler token, não decide política organizacional de treinamento, exige revisão humana e não altera scoring.

### Provider e orquestração

A remediação técnica não possui provider especializado próprio. Ela consome a seleção principal de IA da execução e, quando `AUTO` é usado, preserva integralmente o orquestrador canônico: elegibilidade, ordenação por custo estimado, fallback, quarentena, circuit breaker, telemetria e limites de tentativas permanecem responsabilidade do core de IA.

Falha de validação do payload M24 não deve ser interpretada como defeito do algoritmo de seleção/fallback. O contrato funcional da feature continua responsável por definir qual saída é válida.

### Contrato de evidência por recurso

`ROBOTS` e `SITEMAP` possuem universos de evidência distintos. O runtime mantém a validação local fail-closed e, adicionalmente, projeta essa restrição no JSON Schema enviado ao provider.

Para cada `resource_assessment`:

- `resource=ROBOTS` só pode referenciar `evidence_ids` pertencentes ao conjunto ROBOTS persistido;
- `resource=SITEMAP` só pode referenciar `evidence_ids` pertencentes ao conjunto SITEMAP persistido;
- recurso sem conjunto de evidência elegível não recebe branch de assessment no schema;
- `diagnostic_code` e `evidence_ids` das ações também são restringidos aos valores efetivamente fornecidos;
- o validador local continua verificando a resposta mesmo quando o provider declara suporte a structured output.

A separação é estrutural, não apenas uma instrução em linguagem natural. Isso evita fallback/custo desnecessário causado por um provider misturar evidência válida de um recurso no assessment de outro recurso.

O identificador público/persistido do contrato permanece `M24-TECHNICAL-REMEDIATION-v2`, pois a forma de saída e os consumidores persistidos não mudaram; o endurecimento restringe apenas combinações que já eram inválidas pelo validador local.

## 8. Persistência e relatório

A capacidade usa persistência aditiva no `audit.db` para execução, diagnósticos e resultados técnicos opcionais de IA. Nomes físicos de tabelas e subdiretórios de artifacts são detalhes internos e não constituem contrato público quando não publicados explicitamente.

Página canônica:

```text
report/crawling-discovery.html
```

A telemetria de eventual uso de IA também pode aparecer em `report/ai-usage.html` sem misturar consumo de API e qualidade do website.

## 9. Bloqueios de fonte e segurança

Hard source blockers impedem aquisição adicional dependente do corpus. Expansão cross-origin não ocorre automaticamente. Evolução dessa política exige controles explícitos de SSRF, DNS/IP, redirects e autorização de escopo.

## 10. Critérios de aceite

- formatos suportados possuem regressão correspondente;
- sitemap externo declarado não dispara fetch automático;
- ausência de robots não cria falso bloqueio;
- `llms.txt` permanece experimental/non-scoring;
- remediação técnica permanece default OFF;
- `resource_assessments` não podem cruzar evidência ROBOTS/SITEMAP nem no schema enviado ao provider nem na validação local;
- falha contratual de M24 não altera regras de preço, AUTO, fallback, quarentena ou circuit breaker;
- execução não altera entidades de scoring fora do contrato BR-GEO-055/056;
- report usa navegação/CSS canônicos;
- source blocker evita aquisição adicional;
- CI cobre regressões relevantes.

## 11. Limite metodológico

Fontes externas sustentam fenômenos específicos de crawling/discovery; elas não homologam `SARI-001`, `SCORE-GEO-004`, severidades internas nem qualquer índice proprietário RASAi.

Quando outra documentação desta capacidade reproduzir literalmente texto protegido de fonte externa, deve aplicar a política de citação, tradução e direitos autorais definida em `../README.md`; referências técnicas simples e identificadores de protocolo não implicam reprodução do conteúdo-fonte.