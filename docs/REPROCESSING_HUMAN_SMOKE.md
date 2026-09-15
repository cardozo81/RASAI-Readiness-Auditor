# Smoke humano — reprocessamento seletivo no console Windows

Este roteiro valida a experiência final do operador depois dos testes automatizados. O foco é o console local Windows; não é um teste de SaaS.

## Pré-condições

- usar `main` atualizado;
- executar no Windows;
- possuir ao menos um `AUD-*` em estado `Parcial — pode reprocessar` com uma pendência recuperável;
- preferencialmente usar um AUD que tenha IA configurada e alguma tentativa/custo persistido, para validar a prévia monetária;
- manter as credenciais necessárias disponíveis na sessão/Windows User.

Antes do smoke:

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
git switch main
git pull --ff-only
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
   - bloco `PRÉVIA DE CUSTO - REPROCESSAMENTO SELETIVO` antes da confirmação;
   - `C. Confirmar e iniciar reprocessamento` e `V. Voltar sem reprocessar`.
4. Pressione `V`. Deve voltar sem executar, sem registrar entrada inválida como cancelamento técnico e sem exibir erro.
5. Entre novamente e pressione `C`.
6. Durante a execução, a tela deve atualizar periodicamente e mostrar etapa/progresso/atividade. O console não deve permanecer visualmente congelado durante uma chamada longa.
7. Ao concluir, valide na mesma superfície:
   - RPR gerado;
   - situação lógica do AUD;
   - itens tentados/resolvidos/preservados/restantes;
   - cada pendência restante com status, motivo, tentativas e próxima ação;
   - consumo adicional desta tentativa;
   - consumo acumulado do AUD, incluindo tentativas IA, tokens e custo estimado quando houver pricing/telemetria.
8. Valide as ações finais:
   - `P` abre a pasta do AUD;
   - `I` abre o relatório HTML quando materializado;
   - `V` retorna à auditoria selecionada;
   - `Q` mantém a confirmação normal de saída;
   - `R` aparece habilitado somente quando resta pendência recuperável.
9. Se `R` estiver habilitado, use-o. O console deve voltar para `PREPARAR REPROCESSAMENTO`, recalcular o escopo/custo sobre o estado atual e exigir nova confirmação explícita antes da segunda tentativa.
10. Após resolver todas as pendências aplicáveis, confirme que o AUD deixa de oferecer retry automático e que itens não aplicáveis não impedem conclusão.

## Critério de aprovação

O smoke é aprovado somente se não houver divergência entre o que o console informa e o que efetivamente ocorre: confirmação/cancelamento explícitos, atividade visível durante o RPR, custo antes/depois quando estimável, erros restantes explicados e ações finais operáveis sem `ENTER` intermediário ocultando o menu.

Se qualquer item falhar, registrar AUD, RPR, ação executada, texto exibido e `logs/audit.log` antes de abrir novo ajuste.
