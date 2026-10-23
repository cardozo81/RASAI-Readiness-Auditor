# Materialidade M3 e consumidores Search - contrato de correção

## Causa física reproduzida e contrato

A AUD física fornecida pelo operador (`AUD-12516653C86743ACA32FA177B26AE19D`, MOBILE) comprova HTTP 200, DOM extenso, `<main>` e `<h1>` sem texto, skeleton/lazy signals, recuperação M3 bounded esgotada e `capture_quality=INCOMPLETE`. A prévia `bounded_lazy_probe` declarava `NOT_REQUIRED` apesar da captura incompleta. Isso não comprova automaticamente que um timeout maior recuperaria o site.

O diagnóstico causal na main anterior: o preflight de lazy usa `bool(extractor.extract(html).main_content)`; texto estrutural pode tornar essa expressão verdadeira mesmo quando o gate físico de materialidade `render_materiality._strong_primary_content()` rejeita a página. Corrigir a decisão de recuperação do M3 **sem redefinir a regra BR-GEO-024 por retroação**.

## Contrato operacional após a correção

- `M3 MATERIALITY_GATE` mantém a recuperação original condicional (4 × 250 ms). Apenas se lazy signals persistirem e o conteúdo principal não for material, `SAME_PAGE_BOUNDED_SCROLL` executa até três passos de 250 ms **na mesma página Chromium**, antes de screenshot e congelamento do artefato.
- Para promoção, exigir materialidade física positiva após interação, não apenas texto extraído. Guardar SHA-256 anterior/aceito, `bounded_lazy_recovery`, `recovery` original e metadados de quantidade/tempo. O HTML promovido deve ser o mesmo que embasa screenshot, extração, hashes e consumidores. Sem materialização, preservar `INCOMPLETE`.
- `BR-GEO-024` permanece com seu algoritmo e métodos próprios já homologados; o gate M3 registra `legacy_extractor_content_recoverable` para diagnóstico. Isso impede que a discrepância seja escondida sem alterar a norma de pontuação.
- Os números de ciclos, duração e motivos são **política interna fixa do motor nesta versão** (`ENGINE_DEFAULT`); não são parâmetros disponíveis no INI. Não anunciar configuração de timeout inexistente. Qualquer controle futuro exigirá serialização tipada, defaults explícitos, snapshot de nova AUD, reuso fiel no RPR e isolamento de M23/M25.
- Competitividade: quando o M3 da URL/device auditados registra `INCOMPLETE/UNAVAILABLE`, o CAT-05 mantém SERP, candidatos e proveniência, mas a comparação ganha `CUSTOMER_CONTENT_NOT_COMPARABLE`, sem gaps. Não substituir silenciosamente o M3 por uma requisição `PUBLIC_WEB_HTTP`; não cobrar requests adicionais para resolver um pré-requisito inválido. Search observada continua SUCCESS independente da elegibilidade de conteúdo, e IA competitiva requer `CONSOLIDATED`.
- Na apresentação CAT-05: solicitação SERP (Top N) é distinta da profundidade realmente persistida; `acquisition_policy.customer_source` distingue `AUDIT_RENDERED_ARTIFACT`, `AUDIT_RENDERED_INCOMPLETE` e `PUBLIC_WEB_HTTP`. Exibir falhas como limitação, não descartar fonte.
- Perplexity: `[perplexity_draft]` é somente rascunho não autorizado. `C` no gate específico ativa intenção por uma AUD e é restaurado ao final. O resumo pós-AUD deve ler os fatos da tabela `perplexity_search_runs`, e não o estado de sessão vazio (`queries=0/WEB`). A comparação GEO só existe quando há escopo SERP idêntico e admissível: N/D é resultado verificável para queries diferentes.

## Linhagem dos parâmetros

| Origem | Congelamento | Execução | Apresentação |
| --- | --- | --- | --- |
| SERP - termos, região, device, profundidade, budgets, concorrentes e YMYL | `SEARCH_INTELLIGENCE` configuration na AUD | argumentos canônicos CLI → provider, requests e observações | CAT-05 requested/effective/observed |
| Perplexity - queries e FAST/WEB | pedido autorizado por AUD, nunca por restauração de INI | Search API na execução autorizada, run e custos separados | pós-run da execução persistida + GEO advisory |
| Captura M3 | política ENGINE_DEFAULT e contexto URL/device da captura | recovery e lazy probe same-session; resultado de materialidade | browser_metadata e source-quality; `INCOMPLETE` bloqueia IA |
| Reprocessamento | escopo/configuração não secreta da AUD original | apenas dependências elegíveis, respeitando RPR canônico | novo attempt vs sucessos preservados |

Nenhum item acima altera scores, classificação arquitetural M6, threshold Apdex M23/M25, credenciais ou cobranças. Não enviar queries/headers/cookies/HTML sensível em diagnóstico genérico.

## Gate focal - o mínimo necessário

1. Testes sintéticos de skeleton com nav extenso, conteúdo tardio materializado, shell persistente, SSR já pronto; nenhum site externo. Provar 0 waits indevidos e hash exato.
2. Fixture SQLite de snapshot M3 incompleto: `_rendered_customer_artifact` indisponível; comparação descritiva terminal `CUSTOMER_CONTENT_NOT_COMPARABLE`, candidatos preservados, 0 chamadas HTTP adicionais. READY conserva caminho original.
3. Console pós-run: query FAST persistida é exibida após limpeza de consentimento; não ativar nova API.
4. Humanização: estados específicos explicados, códigos de rastreabilidade preservados; pacote selado antigo não modificado.
5. RPR físico controlado será uma verificação posterior, **não executada** nesta mudança porque requer estação Windows/URL autorizada; a correção não assegura que o conteúdo externo esteja materializável dentro do limite.

As correções aqui são aditivas/consultivas fora do motor de scoring. Se a captura física continuar inconclusiva, a AUD permanece `PARTIAL_RETRYABLE` com razão rastreável; jamais elevar para COMPLETE por conveniência.
