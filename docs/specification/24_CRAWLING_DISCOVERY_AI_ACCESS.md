# Rastreamento, descoberta e acesso de crawlers

**Estado no baseline de desenvolvimento:** INTEGRATED BASELINE  
**Natureza:** diagnóstico técnico determinístico por padrão e non-scoring  
**Scoring boundary:** `SARI-001` / `SCORE-GEO-004`

## 1. Objetivo

Aprofundar evidências de `robots.txt`, sitemaps, políticas de crawlers, feeds, `llms.txt` experimental e sinais de discovery sem permitir pesos arbitrários: robots/sitemap usam fatores estáticos do método e a IA opcional só pode corroborar/rebaixar esses mesmos grupos por evidência validada.

Esta capacidade não cria novo score, não altera `SARI-001` e não recalcula `SCORE-GEO-004`.

## 2. Invariantes

1. execução determinística é fonte de verdade dos diagnósticos técnicos;
2. LLM não escolhe pesos, thresholds, Score, Coverage, Confidence ou Consolidation; somente uma saída evidence-bound válida pode ser convertida pelo runtime nas regras bounded BR-GEO-055/056;
3. diagnósticos próprios permanecem advisory com `scoring_impact=NONE`; quando BR-GEO-055/056 são materializadas, `m24_runs.scoring_impact=BOUNDED_AI_RESOURCE_ASSESSMENT`;
4. falha desta camada é fail-open em relação ao audit principal;
5. ausência de `llms.txt` não reduz readiness;
6. políticas de crawlers com finalidades diferentes não são tratadas como equivalentes;
7. evidência não observada não é inferida como configurada/ausente;
8. resultados não entram no `SCORE-GEO-004` sem uma nova metodologia explícita/versionada.

## 3. Evidence sources

A camada reutiliza estado persistido do AUD e faz aquisição adicional somente onde o contrato permite, incluindo:

- robots/sitemap evidence;
- páginas, respostas HTTP e snapshots;
- canonical/meta robots;
- recursos same-origin observados;
- `/llms.txt` same-origin quando seguro;
- provider configurado apenas se a remediação técnica por IA estiver explicitamente habilitada.

## 4. robots.txt and crawler policy

A análise preserva grupos, `Allow`, `Disallow`, `Sitemap`, estado de aquisição e sintaxe relevante. Ausência legítima de `robots.txt` não vira bloqueio artificial.

Declarações `Sitemap:` cross-origin são preservadas como evidência, mas não são seguidas automaticamente. Essa é uma fronteira de segurança/escopo, não um finding do website.

Crawler/policy tokens devem permanecer semanticamente separados. Search crawling, training/product controls e demais usos não podem ser fundidos em uma única conclusão.

## 5. Sitemaps

Formatos suportados pelo runtime incluem XML urlset/index, gzip, RSS 2.0, Atom 1.0 e texto plano conforme implementação.

A análise pode considerar validade de URL, duplicatas, limites documentados, `lastmod`, extensões observadas e cruzamentos com respostas/indexabilidade/canonical/robots dentro da amostra auditada.

Sitemap é sinal de discovery/preference, não garantia de crawl, indexação ou ranking.

## 6. `llms.txt`, feeds and IndexNow

`llms.txt` é tratado como proposta comunitária experimental, não requisito universal. Presença pode ser analisada e persistida; ausência é informativa e non-scoring.

Feeds RSS/Atom são sinais complementares de discovery, não requisitos universais.

IndexNow só pode ser afirmado como observado quando existir evidência verificável. Uma auditoria passiva não deve inferir submissão bem-sucedida apenas pelo HTML público.

## 7. Optional AI technical remediation

Public controls:

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

Default: OFF.

A IA recebe apenas diagnóstico/evidence persistidos, não inventa URL/policy/canonical/data/crawler token, não decide política organizacional de treinamento, exige revisão humana e não altera scoring.

## 8. Persistence and report

Tabelas aditivas próprias incluem:

```text
m24_runs
m24_diagnostics
m24_ai_results
```

Artifacts podem ser persistidos em `artifacts/m24/`.

Página canônica:

```text
report/crawling-discovery.html
```

A telemetria de eventual uso de IA também pode aparecer em `report/ai-usage.html` sem misturar consumo de API e qualidade do website.

## 9. Source blockers and security

Hard source blockers impedem aquisição adicional dependente do corpus. Cross-origin expansion não ocorre automaticamente. Evolução dessa política exige controles explícitos de SSRF, DNS/IP, redirects e autorização de escopo.

## 10. Acceptance criteria

- formatos suportados têm testes;
- sitemap externo declarado não dispara fetch automático;
- ausência de robots não cria falso bloqueio;
- `llms.txt` permanece experimental/non-scoring;
- remediação técnica permanece default OFF;
- execução não altera entidades de scoring;
- report usa navegação/CSS canônicos;
- source blocker evita aquisição adicional;
- CI cobre regressões relevantes.

## 11. Methodological limit

Fontes externas sustentam fenômenos específicos de crawling/discovery; elas não homologam `SARI-001`, `SCORE-GEO-004`, severidades internas ou qualquer índice proprietário RASAi.

`SCORE-GEO-003` permanece apenas como identificador histórico de auditorias antigas e não deve ser descrito como scoring vigente nesta especificação.
