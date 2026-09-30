# Gate canônico de coleta e encerramento da IA — AUD/RPR

Contrato incremental rastreado por #110 e implementado inicialmente em #111. Os
executores físicos M3, M21, M23, M25 e os adaptadores de serviços continuam sendo
as referências de coleta tanto na auditoria inicial quanto na recuperação seletiva.
O RPR é um plano de execução e provenance sobre o contrato original, não uma
metodologia independente de cálculo ou aquisição.

## Ordem causal obrigatória

1. Registrar o contrato solicitado e planejar os contextos.
2. Coletar a aquisição HTTP, captura renderizada, extração, serviços exigidos e
   medições live. Um requisito opcional só vira obrigatório quando selecionado.
3. Persistir e reconciliar estados por componente **e escopo**, sem tomar HTTP
   200 como prova de renderização ou falha de sub-recurso como falha do documento.
4. Avaliar `audit_collection_gate.evaluate_collection_readiness` após a
   reconciliação. O mesmo avaliador é chamado tanto por `audit_runner` quanto
   por `governed_reprocess_runtime`.
5. Selar a evidência. Só entrar na fase de IA quando o gate permitir e houver
   autorização específica do usuário. Quando faltar coleta, manter evidência
   parcial para diagnóstico/reprocessamento, sem chamada de provedor de IA.
6. Derivar, pontuar e publicar somente sobre a evidência efetiva, identificando
   corretamente estados parciais, preliminares e elegibilidade de consolidação.

O gate não confunde `FAILED_RETRYABLE`, `WAITING_FOR_DATA`, `RUNNING` e
`REQUESTED_NOT_EXECUTED` com coleta concluída. `SUCCESS`,
`NOT_APPLICABLE` e `DISABLED` são elegíveis. `CORE_AUDIT` e as
tarefas de IA não podem ser pré-requisitos do próprio gate: são derivadas
posteriormente. Um universo vazio de requisitos registrados **não libera IA**;
a reconciliação do contrato precisa materializar o planejamento antes.

## Contrato de compatibilidade

A auditoria inicial e o RPR mantêm funções físicas e fórmulas compartilhadas.
O RPR preserva `SUCCESS`, respeita janelas temporais, cria `RPR-*` e
registra somente as tentativas efetivamente executadas. A fase M24 de coleta
não pode chamar provedor de IA; a análise técnica M24 pertence à janela
governada posterior.

A implementação inicial do gate não conclui, sozinha, a refatoração integral
de coordenação. #107 trata diagnóstico causal da renderização, #108 unifica
contadores e evento de fechamento e #109 recupera humanização contextual sem
perda de significado. A aceitação integral do motor comum requer a matriz
de paridade e smoke real definidos em #110, #15 e #92.

## Testes

Executar exclusivamente o conjunto de gate e das superfícies diretamente
alteradas, definido em
`.github/workflows/shared-collection-ai-gate-targeted.yml`.
Um resultado verde de teste unitário não substitui o smoke com interrupção,
RPR, três coletores live, banco, logs, custos e relatórios.
