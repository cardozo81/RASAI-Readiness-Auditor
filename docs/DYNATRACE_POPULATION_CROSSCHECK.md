# #355 - Conferência local entre configuração Dynatrace e população USQL

O módulo `python -m rasai.dynatrace_population_crosscheck`
é um consumidor **offline, sem rede**, de dois JSONs já obtidos
por rotinas independentes:

1. `dynatrace_apdex_review_cli`: configurações KPM/thresholds
   para Load, XHR e Custom actions, provenientes de Settings API
   autenticada ou JSON fornecido pelo operador.
2. `dynatrace_rum_population`: resultado agregado de USQL
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
python -m rasai.dynatrace_population_crosscheck `
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
do backend; um arquivo anterior incompleto pode retornar N/D,
em vez de receber uma nova hipótese positiva. Sem novas chamadas
Dynatrace, sem modificação do perfil sintético M23/M25.


## Visualização humana offline (#355)

O contrato `RASAI-DYNATRACE-RUM-SETTINGS-COMPARISON-355-002`
agora pode ser apresentado por `--format html`, mantendo JSON
como formato padrão e sem executar qualquer nova chamada Dynatrace:

```powershell
python -m rasai.dynatrace_population_crosscheck `
  --settings-advisory-json .\settings_advisory.json `
  --rum-population-json .\rum_actions.json `
  --format html > revisao-dynatrace.html
```

A saída responsiva e imprimível, sem JavaScript, distingue
arquitetura declarada, KPM Load/XHR/Custom do export, contagens
USQL, nível de extrapolação, escopo de aplicação/URL/dispositivo/
janela e orientações legíveis para revisão operacional.

O relatório conserva explicitamente `N/D` para fontes
incomparáveis, nunca reinterpreta zero XHR como captura
desativada e não transforma contagens RUM em prontidão SPA.
Também nunca afirma autenticar o tenant com dois arquivos
JSON, nem sugere thresholds numéricos universais por arquitetura.
Nenhum score, perfil executável M23/M25, relatório de AUD
ou contrato de RUM é alterado. Os testes cobrem escaping de
campos arbitrários da exportação, estado N/D e integridade
byte a byte dos arquivos de entrada.


## Comando nativo offline para analistas RASAi (12/10/2026)

Para conferir os dois JSONs já coletados, sem consultar tenant,
carregar credenciais de integração nem executar M23/M25:

```powershell
rasai dynatrace-rum-crosscheck `
  --settings-advisory-json .\settings_advisory.json `
  --rum-population-json .\rum_actions.json `
  --format html > revisao-dynatrace.html
```

`rasai dynatrace-rum-review` é alias da mesma rotina; `--format json`
restitui exatamente a projeção consultiva versionada.
O despacho ocorre **antes** de inicializar a auditoria ou carregar
os segredos persistidos do console. Os arquivos locais continuam
somente leitura. Não há injeção no CAT-07 histórico nem afirmação
de mesma amostra RUM/Synthetic. A ausência de prova de
market/browser/tenant/sessão mantém os campos correspondentes falsos
ou N/D, sem criar recomendação numérica de thresholds.


## Normalização da identidade de tipos USQL (12/10/2026)

A resposta de `useraction` agregada por `type` é tratada
como evidência consultiva por classe `load`, `xhr`,
`custom` e `other`. Os rótulos são agora normalizados
com `strip().casefold()` **antes** de atribuir classe
e verificar duplicidades. Assim `" Load "` não se torna
equivocadamente `other`, e `"Load"` + `" load "`
não podem representar duas coortes físicas independentes:
a resposta é rejeitada com N/D, sem publicar soma parcial.
Rótulos vazios ou maiores que 80 caracteres também são
considerados inválidos.

A lógica mantém `USQL` opt-in e sem novas requisições,
não supõe amostra bruta sem extrapolação e não deduz
cobertura de XHR/soft navigation na aplicação SPA nem
equivalência entre RUM real e a auditoria Synthetic.


## Ingestao offline de evidencia JSON antes do smoke humano (12/10/2026)

O comando de comparacao de Settings 2.0 com RUM USQL usa apenas arquivos
locais fornecidos pelo operador. O leitor agora recusa chaves JSON
duplicadas (inclusive em objetos aninhados), constantes nao JSON
`NaN`/`Infinity` e qualquer divergencia entre tamanho fisico inicial,
bytes efetivamente lidos e tamanho final. A leitura e limitada a 1 MiB
para o advisory Settings e 256 KiB para a populacao RUM, inclusive se
o arquivo crescer durante a abertura. Os testes nao acessam Dynatrace,
nao autenticam o tenant, nao medem novas user actions e nao alteram
Apdex M23/M25 ou scores. A rejeicao permanece local e anterior a
qualquer pretensao de equivalencia da amostra.
