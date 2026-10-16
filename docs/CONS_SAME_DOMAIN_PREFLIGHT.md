# Issue #210 - elegibilidade para comparação de URLs distintas sob mesmo host

## Modos que não podem ser confundidos

**CONS longitudinal homologado** requer URL exata e mesmo dispositivo.
Permanece totalmente inalterado em `consolidation.selection.resolve_selection`.

**Comparativo por domínio** ainda NÃO está disponível no gerador CONS.
O novo `assess_same_domain_pair`, em
`consolidation/domain_preflight.py`, é apenas uma avaliação offline
**sem IO**, usando dois `AuditCandidate` previamente autorizados.
O retorno `ELIGIBLE_FOR_DESCRIPTIVE_SAME_HOST_REVIEW_ONLY` não concede
permissão de acesso nem implementa uma série temporal/score.

## Condições fail-closed do preflight

Somente admite auditorias distintas completas, cada qual anteriormente
demonstrada como single URL/device, URLs HTTP(S) com host **exato**
normalizado (IDNA/case/trailing dot), mesma origem scheme/port,
dispositivo MOBILE ou DESKTOP igual, documento requisitado diferente
(fragmentos #anchor não criam documento novo), relógios UTC-aware
e instantes diferentes. Não tratar `www.` e domínio raiz, ou subdomínios,
como mesma população só porque pertencem à mesma organização.
Domínio declarativo do índice não substitui parsing de URL.

Falha de qualquer condição gera `NOT_ELIGIBLE` e motivo tipado, sem
calcular deltas, sem gerar CONS ou tocar AUDs.

## Política por métrica (contrato metodológico)

| Área | Tratamento seguro para URLs distintas |
|---|---|
| Scores agregados da AUD | NÃO COMPARÁVEL; universos diferentes. Não publicar tendência percentual. |
| Web Performance / CrUX | Somente dentro da URL original e do mesmo escopo de dispositivo e origem dos dados. |
| Apdex M23/M25 | Somente dentro da URL, perfil, dispositivo e contexto comparáveis; nenhum delta cruzado. |
| GEO / SERP / Perplexity | Consulta, idioma, mercado, device e método precisam de provas próprias. Não inferir trend pela coincidência do host. |
| Findings | Listas descritivas independentes, não melhoria/regressão temporal comprovada. |
| Inventário do host | Contexto comum descritivo; não presume que as páginas tenham mesmo negócio/conteúdo/objetivo. |

O retorno contém essas classificações fixas e as flags explícitas
`metric_comparison_executed=false`,
`page_level_deltas_allowed=false`,
`audit_score_trend_allowed=false`,
`source_attestation_verified=false`.
Todos os consumidores futuros devem exigir um novo contrato e testes de
escopo, e jamais reinterpretar esse retorno como autorização de geração.

## Próximos gates

A integração no CONS exige desenho separado de UI, universo, identidade
de métricas, proveniência física de cada AUD e autorização do operador.
Não foi alterado índice, leitura de SQLite, score, seleção existente,
orquestrador, pipeline ou motor homologado. Os testes de elegibilidade
funcionam sem AUD, rede, IA, bancos ou credenciais reais.

## Identidade de rotas SPA e URL bruta (#210)

O preflight puramente consultivo agora diferencia `#secao` (ancora da
mesma pagina fisica) de `#/rota` e `#!/rota` (possiveis rotas SPA).
Duas URLs com rotas hash diferentes podem ser inventariadas como
universos de pagina distintos sob o mesmo host, mas **nao** como
observacoes longitudinais da mesma pagina. Mesmo nesses casos,
`source_attestation_verified=false`: somente renderizacao equivalente,
URL final e amostras fisicas poderiam provar o conteudo real da rota.

O parse recusa antecipadamente tabs, quebras de linha, controles,
backslash, whitespace nas bordas, URLs maiores que 2048 caracteres e
autoridades ambiguas com `@` ou percent-encoding. Isso evita que
`urlsplit` normalize caracteres que poderiam transformar URLs
distintas em uma origem aparentemente identica. A restricao nao
altera selecao nem geracao do CONS produtivo.

Testes direcionados cobrem SPA `#/...`, `#!/...`, ancoras comuns
e URLs adversariais, mantendo `new_cons_generated=false`, zero
provider requests e nenhum delta de score autorizado.


## Descoberta condicionada por conjunto explícito de AUDs autorizadas

`preview_authorized_same_host_candidates(index, reference_audit_id=..., allowed_audit_ids=(...), max_candidates=100)` usa o índice analítico existente para identificar **somente** outras AUDs de uma lista autorizada, com URL única e mesmo host/origem/dispositivo, mas páginas distintas. A origem é reconstruída da URL física indexada, jamais de equivalência por domínio organizacional, e cada par passa por `assess_same_domain_pair` com separação temporal.

O retorno é um **inventário descritivo, não uma seleção CONS**, e não executa comparação de score entre universos de página, cálculo de deltas de experiência, geração de CONS nem chamadas externas. O conjunto permitido precisa ser informado pelo consumidor (não há enumeração implícita de todas as AUDs). O resultado registra `source_attestation_verified=False`: índice sozinho **não é selo probatório** da origem física, que precisa de gate posterior antes de efetiva publicação. O modo longitudinal por URL idêntica continua estrito e sem modificações.

A validação offline usa índice sintético com uma referência, uma URL diferente do mesmo host, domínio externo e AUD não autorizada; exige ausência desta última até das leituras do índice e bloqueio de escopo ausente. #210 continua aberta para integração de UX/proveniência/controle de acesso físico e eventual modo CONS próprio, sem reclassificar isso como longitudinal homogêneo.
