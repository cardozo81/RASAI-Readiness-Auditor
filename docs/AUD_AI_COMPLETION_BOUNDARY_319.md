# #319 - Separação pós-fato das chamadas IA pela janela física da AUD

O consumidor `python -m rasai.audit_ai_completion_boundary_319`
utiliza somente metadados já persistidos em `audit.db`. Nenhuma IA,
coletor, provider de pricing, report writer, SERP, RPR ou CONS é acionado.

As referências temporais físicas são `audits.started_at` e
`audits.completed_at`, ambas com timezone explícito, em ordem estrita,
com `status=COMPLETED` e `completion_status=COMPLETE`. Na ausência
de início confiável, o resultado inteiro abstém (N/D): apenas conhecer
a conclusão não prova que uma chamada antiga tenha ocorrido na AUD.
Cada linha de `ai_provider_attempts` e
`content_remediation_attempts` pertence a apenas um dos grupos:

- `DURING_AUD`: chamada começou no início ou depois e terminou até a conclusão.
- `AFTER_AUD`: chamada começou após a conclusão.
- `CROSSES_AUD_COMPLETION`: intervalo cruza o instante de término.
- `UNKNOWN_CLOCK`: timestamps ausentes, sem timezone ou invertidos.
- `BEFORE_AUD`: chamada terminou antes ou no instante de início.
- `CROSSES_AUD_START`: chamada começou antes da AUD e terminou após o início.

O contrato evoluiu de `RASAI-AUD-AI-TIME-ECONOMICS-319-001` para
`RASAI-AUD-AI-TIME-ECONOMICS-319-002`; essa correção impede que
requisições de auditorias anteriores inflem o custo/tempo da janela
atual. As chamadas que cruzam o começo ou o fim ficam separadas, sem
distribuição fictícia de custos entre estágios.

`DIRECTED_ANALYSIS` não é classificado por nome como pós-AUD: somente
o relógio observado determina o grupo. Custos de chamadas que cruzam
o marco não são arbitrariamente divididos entre antes/depois.
`provider_observed_cost_usd` e `posthoc_estimated_cost_usd` são
separados; moeda desconhecida, preço ausente ou custo inválido fica
em `unknown_price_attempts`, sem conversão presumida. As duas tabelas
são somadas uma vez, usando identidade da tentativa em seu domínio.

Somas de duração podem conter simultaneidade: `union_active_calls_ms`
representa apenas a união dos intervalos IA comprovados, não duração
física AUD nem medição de PSI, Playwright, extração, Apdex ou escrita
dos relatórios. Quando há intervalos desconhecidos, a união do grupo
é N/D, sem extrapolar. O documento não verifica invoice do fornecedor
nem demonstra que custos pós-AUD integraram o orçamento da AUD central.

Exemplo de uso sem rede:

```powershell
python -m rasai.audit_ai_completion_boundary_319 `
  --audit-db .\audits\AUD-EXEMPLO\audit.db --audit-id AUD-EXEMPLO
```

O banco é aberto somente em leitura com `mode=ro&immutable=1`, sem
sidecars nem links simbólicos; a operação não escreve no histórico.
Fixtures sintéticas comprovam duas chamadas IA paralelas durante a AUD,
chamadas estritamente anteriores ao início, chamadas cruzando seu começo,
Directed Analysis posterior, remediação cruzando a conclusão, relógios
sem timezone ou invertidos e preservação do SHA-256 da base. Isto é diagnóstico
pós-fato, não calibração da previsão ex ante, e não requer smoke geral.
