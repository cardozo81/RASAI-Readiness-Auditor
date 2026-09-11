# Reporting de uso e comunicação de IA

`report/ai-usage.html` é a superfície destinada a explicar consumo, falhas, roteamento e comunicação com provedores de IA durante uma auditoria.

O relatório deve distinguir:

- finalidade desabilitada/não solicitada;
- provider não configurado;
- tentativa externa realizada;
- resposta aceita pelo contrato RASAi;
- resposta recebida e posteriormente rejeitada por validação/contrato local;
- erro técnico de request/provider;
- provider removido da execução por condição terminal;
- provider removido pelo circuit breaker;
- tokens medidos e custo estimado quando o provider fornece dados suficientes.

Uma resposta rejeitada localmente ainda representa comunicação externa e pode ter consumido tokens/custo. Portanto, não deve ser escondida nem descrita como se nenhuma chamada tivesse ocorrido.

Ausência de dado de IA não deve ser convertida em finding do website. O estado deve indicar, conforme a evidência persistida, se a finalidade estava desabilitada, não configurada, foi executada sem saída utilizável, ficou parcial ou falhou/ficou indisponível.

## Provider-neutral

O renderer não mantém uma allowlist visual de providers. Provider e modelo são projetados a partir da telemetria persistida. Assim, OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, GitHub Copilot e futuros providers compatíveis com o registry usam a mesma superfície sem exigir uma variante específica do HTML.

GitHub Copilot é `explicit-only`; quando aparece no report, isso representa seleção explícita. Ele não deve aparecer como candidato/tentativa do pool `AI=auto`.

## Log de exchanges

Quando disponível, cada comunicação externa é apresentada em bloco expansível com provider/modelo, finalidade, página/snapshot, endpoint sanitizado, duração, status, request e response sanitizados, hashes e indicação de truncamento.

O conteúdo dessa tabela pertence à telemetria técnica. Ele não altera regras, findings, `SCORE-GEO-004` ou `SARI-001`.

## AUTO

Quando `AI=auto`, o relatório também apresenta o estado de saúde observado de cada provider elegível durante a execução: tentativas, sucessos, falhas temporárias, falhas terminais, elegibilidade final e motivo de exclusão quando aplicável.

O conjunto AUTO é derivado do `provider_registry`; não existe cadeia fixa documentada pelo report. Providers `explicit-only`, atualmente GitHub Copilot, permanecem fora desse pool.

A política completa está em [`AI_RUNTIME_ORCHESTRATION.md`](AI_RUNTIME_ORCHESTRATION.md) e o catálogo canônico em [`PROVIDER_REGISTRY.md`](PROVIDER_REGISTRY.md).
