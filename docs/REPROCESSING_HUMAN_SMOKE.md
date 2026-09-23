# Smoke humano - reprocessamento seletivo no console Windows

Este roteiro valida a experiência final do operador depois dos testes automatizados. O foco é o console local Windows; não é um teste de SaaS.

## Pré-condições

- usar a branch de validação atualizada (`feat/canonical-processing-presentation`) antes do merge;
- executar no Windows;
- possuir ao menos um `AUD-*` em estado `Parcial - pode reprocessar` com uma pendência recuperável;
- preferencialmente usar um AUD que tenha IA configurada e alguma tentativa/custo persistido, para validar a prévia monetária;
- manter as credenciais necessárias disponíveis na sessão/Windows User.

Antes do smoke:

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
git fetch origin
git switch feat/canonical-processing-presentation
git pull --ff-only origin feat/canonical-processing-presentation
python -m pip install -e . pytest
pytest -q tests/test_console_reprocess_parity.py tests/test_console_reprocess_final_refinements.py
```

## Roteiro

1. Inicie `rasai-console` e acesse `Auditorias / histórico`.
2. Selecione um AUD parcial e escolha reprocessar pendências.
3. Na tela `PREPARAR REPROCESSAMENTO`, confirme visualmente:
   - situação atual do AUD;
   - requisitos atendidos;
   - pendências/bloqueios;
   - sucessos preservados;
   - itens `NOT_APPLICABLE`/`DISABLED`, quando existirem, fora da fila de pendências;
   - escopo da tentativa com status e motivo persistido;
   - bloco `PRÉVIA DE CUSTO - REPROCESSAMENTO SELETIVO`.
4. A etapa `SELEÇÃO DE ITENS PARA REPROCESSAMENTO` deve aparecer **uma única vez**. Informe `T` para selecionar todos ou números separados por vírgula. A entrada válida não pode gerar `ERRO` nem repetir o mesmo prompt.
5. Depois da seleção, a tela anterior deve ser substituída por `COMO EXECUTAR O REPROCESSAMENTO`, mantendo `RESUMO DAS ESCOLHAS` no topo:
   - `1` reprocessa os itens selecionados com IA quando aplicável;
   - `2` reprocessa os itens selecionados sem IA;
   - `V` volta sem executar.
   A prévia de custo deve refletir o escopo selecionado. Nenhum `ERRO` residual pode aparecer antes da entrada do operador.
6. Não deve existir uma segunda tela `CONFIRMAÇÃO DO REPROCESSAMENTO`. A escolha `1` ou `2` é a autorização final da tentativa não destrutiva e inicia o RPR.
7. Use `V` para voltar, confirme que as escolhas anteriores válidas permanecem preservadas e então selecione `1` ou `2` para executar.
8. Durante a execução, valide a superfície canônica: etapa anterior/atual/próxima, `X de Y`, andamento da etapa, pipeline total e atividade corrente. Sucessos preservados devem aparecer separados do trabalho desta tentativa. O console não deve permanecer visualmente congelado durante chamada longa ou durante consolidação/persistência/geração do relatório.
9. Ao concluir, valide na mesma superfície:
   - RPR gerado;
   - situação lógica do AUD;
   - itens tentados/resolvidos/preservados/restantes;
   - cada pendência restante com status, motivo, tentativas e próxima ação;
   - consumo adicional desta tentativa;
   - consumo acumulado do AUD, incluindo tentativas IA, tokens e custo estimado quando houver pricing/telemetria.
10. Valide as ações finais:
   - `P` abre a pasta do AUD;
   - `I` abre o relatório HTML quando materializado;
   - `V` retorna à auditoria selecionada;
   - `Q` mantém a confirmação normal de saída;
   - `R` aparece habilitado somente quando resta pendência recuperável.
11. Se `R` estiver habilitado, use-o. O console deve voltar para `PREPARAR REPROCESSAMENTO`, recalcular o escopo/custo sobre o estado atual e exigir nova escolha explícita de modo antes da segunda tentativa.
12. Após resolver todas as pendências aplicáveis, confirme que o AUD deixa de oferecer retry automático e que itens não aplicáveis não impedem conclusão.

13. Em uma auditoria recém-encerrada como `PARTIAL_RETRYABLE`, valide a tela `AÇÕES DA AUDITORIA DESTA SESSÃO`:
   - deve existir `R. Reprocessar pendências desta auditoria [APTO]` quando houver requisito obrigatório reprocessável;
   - ao pressionar `R`, o fluxo seletivo deve abrir já com o `Audit ID` dessa execução, sem pedir o ID novamente;
   - uma AUD integralmente concluída não deve oferecer esse atalho.

## Critério de aprovação

O smoke é aprovado somente se não houver divergência entre o que o console informa e o que efetivamente ocorre: escolha/cancelamento explícitos sem confirmação redundante, atividade visível durante o RPR, custo antes/depois quando estimável, erros restantes explicados e ações finais operáveis sem `ENTER` intermediário ocultando o menu.

Se qualquer item falhar, registrar AUD, RPR, ação executada, texto exibido e `logs/audit.log` antes de abrir novo ajuste.
