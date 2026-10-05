# Reporting de uso e comunicação de IA

`report-catalog/ai-integrations.html` é a superfície destinada a explicar consumo, falhas, roteamento e comunicação com provedores de IA durante uma auditoria.

O relatório deve distinguir:

- finalidade desabilitada/não solicitada;
- provider não configurado;
- tentativa externa realizada;
- resposta aceita pelo contrato RASAi;
- resposta recebida e posteriormente rejeitada por validação/contrato local;
- erro técnico de request/provider;
- provider removido da execução por condição terminal;
- provider removido pelo circuit breaker;
- tokens medidos e custo estimado quando o provider fornece dados suficientes;
- uso nativo não-token, quando aplicável, preservando unidade, quantidade, fonte da métrica e sem converter requisições/créditos em tokens.

Uma resposta rejeitada localmente ainda representa comunicação externa e pode ter consumido tokens/custo. Portanto, não deve ser escondida nem descrita como se nenhuma chamada tivesse ocorrido.

Ausência de dado de IA não deve ser convertida em finding do website. O estado deve indicar, conforme a evidência persistida, se a finalidade estava desabilitada, não configurada, foi executada sem saída utilizável, ficou parcial ou falhou/ficou indisponível.

## Transparência de custo e atribuição funcional

`report-catalog/ai-integrations.html` centraliza a telemetria financeira e operacional das tentativas de IA. As páginas CAT apresentam o resultado funcional produzido e não repetem tokens, request/response ou custo individual.

A página de IA e integrações apresenta, a partir da telemetria persistida:

- finalidade da chamada;
- aplicação funcional no relatório;
- provider e modelo;
- data/hora da tentativa no contrato canônico de timezone da apresentação;
- origem da execução, distinguindo **Processamento** de **Reprocessamento** quando a telemetria persistida permite vincular o evento a um `RPR-*`;
- estado da tentativa;
- tokens de entrada, cache, saída e raciocínio quando fornecidos;
- custo individual e moeda quando houver preço persistido;
- pricing rule aplicada (`pricing_rule_id`), contexto, versão e fonte oficial quando houver custo resolvido;
- condições runtime usadas no matching da tarifa (tier/modalidade/operação/região), sem segredo;
- roteamento, fallback e motivo técnico;
- request e response sanitizados quando disponíveis;
- custo técnico contabilizado por moeda, sem conversão cambial implícita;
- previsão pré-execução, quando persistida;
- outcome pós-execução persistido e desvio em relação ao forecast somente quando a cobertura monetária é comparável.

A atribuição é funcional e aditiva: cada tentativa externa é contada uma única vez no total da auditoria. Uma mesma evidência pode ser reutilizada por várias páginas sem duplicar custo.

Uso nativo é persistido em linhas filhas das tentativas, atualmente por `ai_provider_native_usage` e `content_remediation_native_usage`. O relatório humaniza unidades conhecidas, por exemplo `PERPLEXITY_SEARCH_REQUEST` como requisição de busca Perplexity e `MANUS_CREDIT` como crédito Manus. `REQUEST`/`CONSUMPTION` entram no total primário; `RECONCILIATION`, `REFUND` e `GRANT` permanecem rastreáveis, mas não são somados novamente como consumo.

No ledger SaaS, a chamada continua sendo um evento `AI_PROVIDER_CALL` de unidade `call`. Componentes nativos são projetados separadamente como `AI_NATIVE_USAGE`, `AI_NATIVE_RECONCILIATION` ou `AI_NATIVE_ADJUSTMENT`. Quando existe custo nativo, ele fica no evento da unidade nativa, não no evento de chamada, evitando dupla contabilização.

Mapeamentos públicos vigentes incluem:

- análise semântica por dispositivo -> contexto SARI e CATs que consomem o resultado persistido;
- crawling e remediação técnica de descoberta -> CAT-01;
- Search/Competitive Intelligence -> CAT-05;
- Perplexity Search API -> CAT-05 como **pesquisa externa**, com fontes/citações em provenance separada e sem promoção para SERP/evidência determinística;
- Improvement Intelligence -> CAT-08;
- remediação assistida de conteúdo -> CAT-09;
- Análise Direcionada -> página `directed-analysis.html`;
- demais finalidades -> contexto funcional explicitado na própria linha da tentativa.

Tentativas `RASAI-PERPLEXITY-SEARCH-1` usam `ai_provider_attempts` somente como envelope operacional de telemetria e `ai_provider_native_usage` para `PERPLEXITY_SEARCH_REQUEST`. Tokens permanecem ausentes. O conteúdo retornado e as fontes ficam em `perplexity_search_runs`/`perplexity_search_sources`, separados das tabelas SERP. Assim, a página de IA/integrações pode mostrar custo e estado sem reclassificar a pesquisa externa como evidência canônica.

Quando uma tentativa não possui telemetria suficiente ou nenhuma regra corresponde às condições runtime efetivas, o relatório mantém a tentativa e exibe **Não precificado**; ausência de preço não é convertida em custo zero. O mesmo vale para unidades nativas sem conversão monetária oficial, como `MANUS_CREDIT` nesta versão. A persistência conserva a regra, fonte e condições aplicadas quando a tarifa foi resolvida, permitindo reconstrução posterior sem reinterpretar a execução por preços correntes. Quando o custo persistido é explicitamente `0`, moeda e valor são exibidos em cinza claro e, na mesma tentativa, tokens de entrada/saída recebem o mesmo tratamento visual secundário. `reasoning_tokens`, quando presentes, são subconjunto dos tokens de saída e não são somados novamente ao total.

A regeneração do `report-catalog/` apenas reprojeta os dados persistidos. Ela não cria chamadas de IA adicionais para preencher a página.

## `AI=auto`, fallback e múltiplos providers no mesmo relatório

`AI=auto` não implica um único provider por relatório. Uma mesma finalidade pode ter mais de uma tentativa externa, por exemplo:

1. provider A responde, mas a resposta é rejeitada pelo contrato local;
2. o runtime executa fallback para provider B;
3. provider B produz a resposta aceita.

Se ambas as chamadas retornaram usage/custo, **ambas entram no custo do relatório proprietário**. Se a primeira chamada não retornou dados suficientes para estimativa, ela continua aparecendo como tentativa sem custo mensurável; o RASAi não assume custo zero nem inventa um valor.

A página `ai-integrations.html` separa explicitamente **resultado final** de **tentativas**. Quando existe `ai_task_id`, o estado final vem de `ai_tasks.status`; o provider efetivo é projetado a partir da tentativa bem-sucedida vinculada à mesma tarefa. Para contratos históricos sem task persistida, somente estados finais existentes em ledgers próprios — por exemplo `ai_audit_sessions`, `improvement_intelligence_runs` ou `content_remediation_runs` — podem sustentar a síntese. O renderer não deduz sucesso final a partir de texto de erro, nome do provider ou presença isolada de uma tentativa.

Assim, uma tarefa `COMPLETE` com OPENAI falhando e DEEPSEEK sucedendo é apresentada como **Concluído / Fallback bem-sucedido / provider efetivo DEEPSEEK**, mantendo a falha OPENAI e seu diagnóstico técnico na sequência. Uma tarefa persistida como `FAILED` continua sendo apresentada como **Falha final**, mesmo que existam múltiplas attempts.

Também é possível que URLs ou dispositivos diferentes do mesmo relatório sejam atendidos por providers distintos ao longo da execução. Por isso o relatório local e o totalizador sempre agregam por tentativa persistida, não por `effective_provider` da sessão.

## Total conciliado e drill-down em `ai-integrations.html`

Além dos indicadores existentes, `ai-integrations.html` contém o bloco **Total de IA e onde cada custo foi alocado**. O total usa as tentativas persistidas em:

- `ai_provider_attempts`;
- `content_remediation_attempts`.

A listagem de **Outras integrações** segue o mesmo contrato temporal: cada linha apresenta data/hora e origem da execução quando esses dados podem ser determinados a partir dos ledgers persistidos. A projeção converte timestamps UTC para o timezone de apresentação sem alterar a evidência original.

A página apresenta três níveis complementares:

1. **Mapa de alocação: relatório × provider/modelo** - mostra financeiramente em qual HTML cada provider/modelo ficou alocado;
2. **Consumo global por provider/modelo** - consolida o custo de cada provider/modelo independentemente da superfície;
3. **Detalhamento por relatório proprietário** - expande URL, dispositivo, contrato/finalidade, motivo da alocação, provider/modelo, status, tokens e custo.

A soma das páginas proprietárias deve fechar com o total da execução porque uma tentativa nunca é atribuída a duas superfícies. Páginas sem consumo direto são listadas separadamente e não entram novamente na soma. Totais monetários são conciliados **por moeda**; se a execução materializar mais de uma moeda, o relatório mantém os subtotais separados e recusa comparação cambial implícita com um forecast de moeda única.

O reporting distingue forecast, custo técnico derivado de usage, eventual custo monetário observado pelo provider e invoice. `estimated_cost` persistido em uma tentativa é uma estimativa técnica calculada depois do usage observado; não deve ser rotulado como cobrança/fatura observada. `observed_cost`, quando efetivamente presente, tem precedência apenas para a projeção monetária daquela tentativa. O renderer não inventa custo para tentativa não precificada. Se `total_tokens` estiver ausente mas input/output existirem, usa `input_tokens + output_tokens`; `reasoning_tokens` permanece breakdown de output e não é somado novamente.

O enriquecimento é idempotente: regerar/finalizar o mini-site substitui o bloco padronizado anterior em vez de duplicá-lo.

## Provider-neutral

O renderer não mantém uma allowlist visual de providers. Provider e modelo são projetados a partir da telemetria persistida. Assim, OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, Mistral, GitHub Copilot e futuros providers compatíveis com o registry usam a mesma superfície sem exigir uma variante específica do HTML.

Mistral e GitHub Copilot podem aparecer tanto por seleção explícita quanto pelo pool `AI=auto` quando configurados e aptos. O report usa apenas a telemetria efetivamente persistida, sem inferir a origem da seleção.

## Log de exchanges

Quando disponível, cada comunicação externa é apresentada em bloco expansível com provider/modelo, finalidade, página/snapshot, endpoint sanitizado, duração, status, request e response sanitizados, hashes e indicação de truncamento.

A partir do contrato de correlação pós-refatoração, exchanges novos podem persistir `attempt_id`, vinculando deterministicamente `ai_exchange_log` à tentativa correspondente em `ai_provider_attempts`. A identidade explícita tem precedência sobre qualquer inferência por provider/modelo/finalidade. Para bancos históricos sem `attempt_id`, o renderer permanece compatível e pode usar somente o fallback histórico existente; a leitura do banco antigo não depende de migração destrutiva.

A projeção HTML usa nomes públicos e funcionais para metadados, labels, títulos e estados. **O conteúdo persistido como request, response, payload, prompt, schema ou evidência bruta não passa por humanização semântica.** O HTML aplica apenas escaping seguro ao texto que já foi sanitizado na persistência. Assim, tokens técnicos como `SEMANTIC_READINESS` permanecem exatamente representados e não são substituídos por rótulos públicos.

Identidades canônicas de provider também são contexto técnico próprio: `OPENAI`, `GEMINI`, `DEEPSEEK`, `ANTHROPIC`, `MISTRAL`, `COHERE`, `KIMI` e demais providers do registry são exibidos como identidade do provider, sem passar pelo fallback genérico destinado a enums/condições internas.

O conteúdo dessa tabela pertence à telemetria técnica. Ele não altera regras, findings, `SCORE-GEO-004` ou `SARI-001`.

## AUTO

Quando `AI=auto`, o relatório também apresenta o estado de saúde observado de cada provider elegível durante a execução: tentativas, sucessos, falhas temporárias, falhas terminais, elegibilidade final e motivo de exclusão quando aplicável.

O conjunto AUTO é derivado do `provider_registry`; não existe cadeia fixa documentada pelo report. Todos os providers integrados atuais podem entrar no pool quando configurados/modelo elegível/saudáveis, respeitando exclusões explícitas.

A política completa está em [`AI_RUNTIME_ORCHESTRATION.md`](AI_RUNTIME_ORCHESTRATION.md) e o catálogo canônico em [`PROVIDER_REGISTRY.md`](PROVIDER_REGISTRY.md).


### Trilha de pricing por tentativa

Quando uma tarifa é resolvida, cada tentativa preserva no SQLite:
- `pricing_version`;
- `pricing_context`;
- `pricing_rule_id`;
- `pricing_source_reference`;
- `pricing_runtime_conditions` em JSON canônico;
- `estimated_cost` e `cost_currency`.

Esses campos permitem reconstruir por que uma tarifa foi aplicada. Se as condições efetivas do provider não corresponderem a nenhuma regra vigente, o custo permanece ausente/UNPRICED; o relatório não deve inferir preço de outra região, tier ou modalidade.

