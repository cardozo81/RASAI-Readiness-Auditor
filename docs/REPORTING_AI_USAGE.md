# Reporting de uso e comunicação de IA

`report/ai-usage.html` é a superfície destinada a explicar consumo, falhas, roteamento e comunicação com provedores de IA durante uma auditoria.

O relatório deve distinguir:

- tentativa externa realizada;
- resposta aceita pelo contrato RASAi;
- resposta recebida e posteriormente rejeitada por validação/contrato local;
- erro técnico de request/provider;
- provider removido da execução por condição terminal;
- provider removido pelo circuit breaker;
- tokens medidos e custo estimado quando o provider fornece dados suficientes.

Uma resposta rejeitada localmente ainda representa comunicação externa e pode ter consumido tokens/custo. Portanto, não deve ser escondida nem descrita como se nenhuma chamada tivesse ocorrido.

## Log de exchanges

Quando disponível, cada comunicação externa é apresentada em bloco expansível com provider/modelo, finalidade, página/snapshot, endpoint sanitizado, duração, status, request e response sanitizados, hashes e indicação de truncamento.

O conteúdo dessa tabela pertence à telemetria técnica. Ele não altera regras, findings, `SCORE-GEO-004` ou `SARI-001`.

## AUTO

Quando `AI=auto`, o relatório também apresenta o estado de saúde observado de cada provider durante a execução: tentativas, sucessos, falhas temporárias, falhas terminais, elegibilidade final e motivo de exclusão quando aplicável.

A política completa está em [`AI_RUNTIME_ORCHESTRATION.md`](AI_RUNTIME_ORCHESTRATION.md).
