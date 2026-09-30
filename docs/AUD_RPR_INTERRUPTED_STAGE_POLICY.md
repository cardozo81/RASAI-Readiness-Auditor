# Política de retomada: reinício de etapa interrompida

Decisão do operador em 30/09/2026. Rastreio: #127, #126, #15 e #110.

## Unidade de recuperação

A unidade efetiva de checkpoint é **uma etapa concluída com evidência final válida**, por componente e escopo contratual. Eventos de progresso, contagens parciais e amostras isoladas não conferem conclusão à etapa.

Se uma etapa é **interrompida**, a próxima execução da mesma AUD reinicia essa etapa **do início**. Não é obrigatório reaproveitar amostras parciais. Os componentes/escopos anteriores que já possuem checkpoint final íntegro são preservados; a AUD mantém o mesmo ID e a nova tentativa recebe RPR próprio.

Uma tentativa `RUNNING` reconciliada após falha do processo não significa automaticamente que o componente é incompleto: se seu resultado final e evidência materializada já foram confirmados antes do encerramento, reconciliar SUCCESS sem repetir serviço, preservando o custo e o histórico da tentativa.

Quando existem evidências parciais antigas já persistidas na projeção efetiva, elas precisam ser **arquivadas com provenance RPR antes do reset**. Somente dados pertencentes à nova tentativa de etapa são elegíveis para métricas/score efetivos; logs e artefatos de auditoria originais não devem ser apagados. O programa deve manter separação entre execução operativa de RPR finalizada e requisito de AUD ainda pendente.

## Distinções importantes

- Interrupção (Ctrl+C, kill, sessão órfã): etapa inacabada reinicia desde o primeiro item; não misturar tentativas.
- Etapa terminada, mas com déficit/falha parcial normal: política específica de retentativa do componente continua aplicável, inclusive reaproveitamento seletivo somente quando isso não mistura conjuntos metodologicamente incompatíveis. Não classificar todo `PARTIAL` como interrupção.
- Etapa já concluída: não repetir automaticamente. A mudança material do upstream poderá invalidar dependentes, com arquivo histórico e recomputação explícita.
- Consolidação, derivados e relatório interrompidos: reexecutar derivação determinística a partir das evidências efetivas, **sem reaquisição física ou chamada de IA desnecessária**. Atualizar o fingerprint somente após encerrar o ledger e a sessão.
- Chamadas externas anteriores a uma interrupção podem ter consumido quota/custo. Preservar esse histórico; uma etapa reiniciada que usa terceiros demanda autorização e política de custo vigentes, nunca declarar a repetição como gratuita.

## Aplicação implementada nesta entrega

- **M25 (experiência)**: se a AUD for interrompida durante o lote antes de persistir o resultado M25, o RPR sem run prévio chama o executor M25 original com configuração congelada. O executor limpa exclusivamente as projeções M25 antigas e começa pelo índice 1. As oito medições apenas registradas no log da AUD `AUD-871BB9D605B242E28AB8E218B88977FC` são históricas, **não** numerador/denominador efetivo do novo M25. Teste dirigido de interrupção e nova execução comprova o comportamento; nenhum retrofit no ZIP original.
- **M23 (navegação)**: antes desta decisão, o RPR reutilizava checkpoint de amostra mesmo após run `RUNNING` abandonado. Agora, exclusivamente para run `RUNNING`, arquiva run, amostras e resumos prévios com provenance do novo RPR, reseta a projeção M23 e chama o executor original com orçamento/perfis/limiares congelados. O status estatístico `PARTIAL` por amostragem menor que 100 não é convertido em `SUCCESS` estatístico; a elegibilidade operacional depende do alvo contratado.
- **Outros componentes e consolidações**: o escopo transversal de #127 ainda precisa demonstrar, componente por componente, que todos os checkpoints, arquivos e dependências seguem a mesma política. A presente entrega NÃO homologa integralmente a convergência #110 nem a prontidão RC #92.

## Smoke humano mínimo após merge

1. Criar uma nova AUD MOBILE sem IA com uma página, ativar M25 e M23, acompanhar eventos. Interromper **durante** o M25. Na retomada da MESMA AUD, escolher todos os pendentes sem IA.
2. Conferir que M25 reinicia no índice 1, mede a meta integral no novo RPR, mantém perfil/threshold/mix/concorrência originais; M21/render/extraction concluídos conservam suas provas anteriores e não são recoletados.
3. Em nova AUD de teste, interromper **durante** M23; verificar arquivo histórico das amostras do run abandonado, novo run começando no índice 1 e ausência de mistura entre tentativas no resumo final. Não exigir a opção antiga de reaproveitamento de amostras M23.
4. Em ambos os cenários, confrontar `audit_reprocess_runs`, `audit_fulfillment_attempts`, `audit.log`, banco e manifesto. O fechamento deve ser coerente e haver um só evento final RPR. Não executar IA nesse smoke.
