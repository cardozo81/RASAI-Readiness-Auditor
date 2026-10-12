# #355 - Conferência local entre configuração Dynatrace e população USQL

O módulo `python -m rasai.dynatrace_population_crosscheck_355`
é um consumidor **offline, sem rede**, de dois JSONs já obtidos
por rotinas independentes:

1. `dynatrace_apdex_review_cli_355`: configurações KPM/thresholds
   para Load, XHR e Custom actions, provenientes de Settings API
   autenticada ou JSON fornecido pelo operador.
2. `dynatrace_rum_population_355`: resultado agregado de USQL
   para uma aplicação, URL, dispositivo e janela UTC informados,
   contendo contagens, estado de extrapolação e limitações de RUM.

A comparação exige formatos versionados, ID de aplicação declarada
idêntico, contagens por ação inteiras e consistentes com o total,
e natureza amostral de USQL corretamente representada.
Mesmo que ambos os arquivos afirmem origem live, **a leitura de dois
JSONs não permite autenticar tenant, conta ou assinatura**.
Portanto `application_scope_verified_across_sources=false` sempre.
A saída distingue escopo declarado de escopo que *afirma* ter
origem live, sem confundi-lo com prova criptográfica.

Regras de diagnóstico:

- Em SPA/hydrated/mixed, zero XHR reportado é convite a verificar
  escopo e instrumentação, não demonstra que XHR/Fetch esteja desligado.
- XHR reportado sem KPM XHR nos settings recebidos é oportunidade
  de revisão de configuração; não prova queda de Apdex ou ausência
  de navegação SPA.
- Load positivo não prova prontidão da rota soft navigation.
- Extrapolação `>1` é declarada; ausência de nível resulta em N/D.
- Nenhum score Apdex, KPM executável M25, threshold ou métrica do
  relatório RASAi é ajustado por este crosscheck.

```powershell
python -m rasai.dynatrace_population_crosscheck_355 `
  --settings-advisory-json .\settings_advisory.json `
  --rum-population-json .\rum_actions.json
```

Permanece obrigatório um teste com tenant autorizado para demonstrar
que ambas as fontes correspondem à mesma aplicação, e evidência física
de browser/URL/device/instante para compará-las à coleta RASAi.
A rotina não efetua novas consultas e não usa dados pessoais,
segredos, raw sessions ou qualquer chamada IA.

## Contrato v2: integridade do escopo declarado

O consumidor `RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-002`
agora recusa JSONs RUM sem a confirmação estrutural
`population_query_scoped_to_exact_url_device_window=true` ou
`rum_action_aggregate_returned=true`. Também exige:

- `target_url` HTTP(S) canônica inequívoca, no máximo 1024 caracteres;
- `declared_dynatrace_device_filter` sintaticamente válido;
- `application_id` no formato de entidade real aceito pelo coletor;
- `period_start_utc` e `period_end_utc` com offset UTC explícito,
  em ordem, janela maior que zero e de até 24 horas.

A ausência ou contradição gera `NOT_COMPARABLE` e
`RUM_EXACT_POPULATION_SCOPE_UNVERIFIABLE`, **sem inferir
mesmo browser, dispositivo real, tenant ou página**. Uma URL
sintaticamente válida ainda pode ser forjada pelo operador;
o crosscheck verifica coerência interna do material fornecido,
não autenticidade da fonte remota.

Os produtores de JSON RUM anteriores já expõem essas flags e UTC
do backend; um arquivo legado incompleto pode retornar N/D,
em vez de receber uma nova hipótese positiva. Sem novas chamadas
Dynatrace, sem modificação do perfil sintético M23/M25.
