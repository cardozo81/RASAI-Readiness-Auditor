# Issue #210 - elegibilidade para comparação de URLs distintas sob mesmo host

## Modos que não podem ser confundidos

**CONS longitudinal homologado** requer URL exata e mesmo dispositivo.
Permanece totalmente inalterado em `consolidation.selection.resolve_selection`.

**Comparativo por domínio** ainda NÃO está disponível no gerador CONS.
O novo `assess_same_domain_pair`, em
`consolidation/domain_preflight_210.py`, é apenas uma avaliação offline
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
