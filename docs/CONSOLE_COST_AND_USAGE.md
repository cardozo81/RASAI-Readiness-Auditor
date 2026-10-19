# Console - custo, quota e telemetria de execução

Este documento descreve como o `rasai-console` apresenta exposição prévia e consumo realmente persistido após uma auditoria.

## Regra de fonte única

O catálogo canônico de preços de IA é `src/rasai/ai_cost_policy.py`. O console não mantém preços próprios nem cria uma segunda contabilidade.

Depois da execução, o console lê os dados persistidos em `audit.db` e artifacts/logs correspondentes. A tabela `provider_pricing_catalog` é uma projeção auditável do catálogo canônico usado naquela execução, não uma fonte concorrente de regras.

| Finalidade | Fonte persistida | Dados principais |
|---|---|---|
| análise semântica por IA | `ai_provider_attempts` | provider/modelo, status, tokens, duração, custo estimado, pricing version |
| catálogo de preço IA | `provider_pricing_catalog` | preço unitário, moeda, versão e referência |
| remediação textual por IA | `content_remediation_attempts` | provider/modelo, tokens, status, custo quando estimável |
| Web Performance | `web_performance_attempts` | PageSpeed/CrUX, status, HTTP, duração, erro, artifact |
| Synthetic Apdex | `synthetic_apdex_runs` / `synthetic_apdex_samples` | tentativas, válidas/inválidas, duração/classificação |

## Antes da execução

A faixa financeira é uma heurística de exposição:

```text
NENHUM | BAIXO | MÉDIO | ALTO | EXCESSIVO
```

Ela considera, quando aplicável:

- quantidade conhecida/teto de páginas;
- quantidade de contextos de dispositivo;
- provider/modelo de IA;
- pool AUTO elegível e preços vigentes;
- reasoning/esforço configurado;
- remediação textual;
- PageSpeed/CrUX e limites externos.

A faixa não é invoice e não garante preço final.

Quando `AI=auto` está selecionado, a execução não usa a faixa qualitativa do console para escolher provider. O coordenador calcula o custo estimado de cada requisição específica com o catálogo canônico, o modelo/reasoning efetivo, input/output esperado, cache observado e o contexto tarifário do instante da chamada. A lógica detalhada está em [`AUTO_COST_AWARE_AI_ROUTING.md`](AUTO_COST_AWARE_AI_ROUTING.md).

## Esforço de IA

O default público usa o modelo mais simples e o menor esforço suportado. Selecionar modelo/esforço maiores pode aumentar latência, tokens e custo, por isso o console exibe esses parâmetros na opção 4.

No AUTO, o reasoning efetivamente configurado também participa da estimativa de custo da requisição. Isso não altera o scoring e não muda a política de quarentena/circuit breaker.

## Web Performance

O console contabiliza chamadas PageSpeed/CrUX como consumo de API/quota. Não inventa preço monetário quando não existe catálogo confiável no projeto.

O timeout configurável não representa custo por si só. Ele apenas determina quanto o cliente aguarda a chamada externa antes de registrar timeout.

## Synthetic Apdex

Synthetic Apdex é exibido separadamente da faixa financeira porque não possui API paga própria. A projeção é de **carga sintética**:

```text
páginas × devices × máximo de tentativas/contexto
```

Cada navegação pode gerar muitos requests de subrecursos, portanto a quantidade de navegações não equivale a requests HTTP.

## Depois da execução

O console pode mostrar:

```text
Tentativas IA / sucessos
Tokens input / cache / output / reasoning / total
Custo IA estimado
Chamadas Web Performance
PageSpeed sucesso/tentativas
CrUX sucesso/tentativas
Cobertura de Acessibilidade e motivo
Navegações Synthetic Apdex
Amostras válidas / inválidas
```

A estimativa pré-chamada usada para roteamento e o custo pós-chamada não são a mesma coisa. Antes da chamada, o AUTO pode assumir cache miss e usar heurísticas de tokens apenas para ordenar candidatos. Depois da chamada, custo monetário de telemetria só é materializado quando o usage nativo contém informação suficiente para aplicar a tarifa sem inventar a divisão entre input cacheado e não cacheado.

Se uma tentativa possui tokens mas não existe informação suficiente de pricing/usage, ela é apresentada como não estimável; nunca como custo zero artificial.

## Falhas e cobertura

Falha de integração é separada de finding do website. Exemplos:

```text
PageSpeed timeout
CrUX HTTP/quota
provider sem crédito
provider quarantined
artifact ausente
```

O console e o report devem explicar qual coleta foi afetada.

Quando havia estimativa monetária prévia para IA, mas a execução termina com **zero sucessos de IA** e sem consumo monetário materializado, o fechamento financeiro não classifica o resultado como `DENTRO DO ESPERADO`. O estado exibido é `NÃO CONSUMIDO`, o campo `Desvio vs esperado` permanece sem valor comparativo e a observação deixa explícito que a IA solicitada não produziu execução bem-sucedida/consumo tarifável. Quando existe uma tentativa de IA falha persistida, o bloco reutiliza somente o diagnóstico técnico estruturado já registrado (`provider/model`, `error_class` ou `status`, `error_code/error_type` e `HTTP` quando disponível). Se esse diagnóstico não estiver disponível, o bloco orienta consultar as pendências canônicas do AUD. Nenhuma nova classificação de erro de integração é criada pela camada financeira.

Menor custo não reativa provider em quarentena, não reduz contador de falhas e não modifica a classificação de erro. A seleção econômica altera somente a ordem dos candidatos ainda elegíveis no `AI=auto`.

## Reprocessamento seletivo

A preparação de um `RPR-*` não considera apenas os work-items de IA já pendentes. Uma recuperação de Web Performance, Search, evidência core ou outra fonte pode alterar o contexto persistido e tornar análises de IA dependentes obsoletas.

O console separa:

```text
IA diretamente pendente
= chamada já conhecida antes da confirmação

IA condicional
= chamada que só será necessária se a recuperação alterar evidência consumida
```

Quando existe IA diretamente pendente, a previsão financeira usa somente essa parcela seletiva e exclui sucessos preservados.

Quando existe apenas IA condicional, a interface deve exibir que o custo ainda não é determinável e **não pode apresentar custo zero como garantia**. Exemplos de superfícies potencialmente afetadas por mudança material incluem CAT-08 e Análise Direcionada. CAT-09 só é reavaliado quando sua dependência semântica ou técnica efetivamente muda.

Ao terminar o reprocessamento, o custo incremental é calculado pela diferença entre a telemetria persistida antes e depois do `RPR-*`. As tentativas anteriores permanecem preservadas e não são reprecificadas.

Consulte [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md) para a seleção de dependências e [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md) para o contrato de invalidação seletiva.

## Configuração INI

`rasai-console.ini` persiste somente parâmetros não sensíveis, inclusive modelo, esforço, timeouts e limites. Credenciais não são gravadas no INI.

## Segurança

- secrets aparecem somente como `[SET]`;
- API keys/tokens não entram no INI, report ou log;
- custos são estimativas técnicas;
- não assuma que key configurada implica quota/saldo;
- não confunda carga Synthetic Apdex com custo financeiro de API.


## Inspeção de tempos das análises por IA e requisições web (#319)

Para uma AUD persistida, `rasai audit-attempts <AUD>` expõe a
cronologia das tentativas de análise por IA e, quando comprovável, o campo
`observed_http_request_sums_ms` para `PAGESPEED_INSIGHTS` e
`CRUX_API`. Esses valores são **somas de durações HTTP individuais**,
não medem a duração física da fase, não podem ser adicionados ao
wall-clock da AUD e não se somam automaticamente ao tempo ativo IA.
Se houver tentativa sem duração válida para um serviço, a série daquele
serviço é omitida (N/D); AUDs distintas nunca são combinadas. A presença
ou ausência de telemetria é explícita via `http_request_telemetry`.
O comando não coleta, não faz cobrança, não recalcula relatórios ou custos
e mantém `non_ai_stages_measured=false` enquanto não existir cronômetro
físico da fase. O forecast ex ante e os indicadores homologados ficam
inalterados.


### Recorte de tentativas IA dentro e fora da sessão física verificada (#319)

`rasai audit-attempts <AUD>` traz
`ai_attempt_execution_scope` com quatro coortes independentes:
`WITHIN_VERIFIED_CONSOLE_SESSION`,
`AFTER_VERIFIED_CONSOLE_SESSION`,
`BEFORE_VERIFIED_CONSOLE_SESSION` e
`UNCERTAIN_TIME_OR_SCOPE`.

A única referência autorizada é a sessão física da AUD quando o registro
`console_execution_projections` comprova exatamente um intervalo íntegro,
offset-aware, logicamente `COMPLETED/COMPLETE`. As chamadas M18 e M20
são incluídas, sem dupla contagem dentro de cada ledger. O recorte
separa números de tentativas, soma descritiva de durações IA, união
temporal quando todos os relógios do grupo são válidos, custo
observado USD informado pelo provedor, estimativa USD pós-fato e
tentativas sem precificação. Nenhum desses campos equivale a fatura.

Uma tentativa posterior ao encerramento **não é automaticamente**
classificada como análise direcionada nem RPR: cronologia não comprova
finalidade. Tentativas que cruzam o limite de sessão, têm relógios
ingênuos/reversos ou não possuem prova de origem são não classificadas.
Sem sessão completa verificada, todas são `UNCERTAIN_TIME_OR_SCOPE`.
Essas coortes não ajustam a previsão ex ante, não identificam fases
físicas não instrumentadas e não alteram preços, scores, manifests ou
qualquer evidência original.


## Separação de uso generativo e Perplexity Search API (#319)

Quando a auditoria contém `perplexity_search_runs` verificáveis, o console
apresenta a pesquisa externa separadamente das tentativas generativas.
A tentativa `RASAI-PERPLEXITY-SEARCH-1` em `ai_provider_attempts` é
**envelope de telemetria**, não inferência LLM. Ela é descontada apenas da
**projeção visual** das tentativas e sucessos generativos, nunca do ledger.

- Pesquisas: requisições nativas `PERPLEXITY_SEARCH_REQUEST`, número de
  queries em `query_json`, fontes em `perplexity_search_sources` e custo
  observado da execução armazenado em `perplexity_search_runs`.
- Geração: tentativas, sucessos e tokens obtidos dos ledgers de IA, excluindo
  visualmente o envelope conhecido da Search API. O custo combinado continua
  indicado, junto do custo Search e da diferença monetária somente quando
  existir evidência suficiente.
- Sem `perplexity_search_runs`: a apresentação legada permanece inalterada.
  Sem schema/ledger para desagregação: o console indica que a separação não
  pode ser demonstrada, sem fabricar números.
- Consulta via SQLite somente leitura, restrita ao `audit_id`. Falhas e
  artefatos antigos não se tornam novos sucessos ou estimativas inventadas.

A correção altera exclusivamente a camada de apresentação. Não muda custos
canônicos, native ledgers, critérios de elegibilidade, datas, tokens,
orquestrador `AI=auto`, consentimento, motores SERP/Perplexity/GEO nem scoring.
A comparabilidade entre previsto e observado continua condicionada ao
fulfillment dos requisitos obrigatórios da auditoria.


## Telemetria de tempo/custo por operação (#319)

O relatório **IA e integrações > Tempos e custos por etapa** e a tela de
consumo pós-AUD no console leem as duas tabelas físicas M18 e M20,
sem executar nova auditoria e sem efetuar chamadas tarifáveis. São exibidas
tentativas por operação (Improvement, Análise Direcionada opcional, análise
semântica/técnica, conteúdo, concorrência e Search API opcional), custo USD
quando integralmente precificado, duração acumulada e **união temporal ativa**.

O leitor recusa arquivo ausente/symlink, WAL/SHM/journal pendente, tabela
ilegível, IDs de tentativa duplicados, populações excedentes e estágio
incontrolavelmente fragmentado. Nesse caso a interface exibe **N/D**;
ausência de informação não é custo zero nem prova de conclusão.

Os tempos de HTTP PageSpeed/CrUX apresentados são somas de requests, e
**não** tempo exclusivo da fase. Captura, Apdex, extração e montagem do
relatório continuam N/D para cronômetro exclusivo sem evidência física
comparável. Uma chamada Direcionada posterior não integra por inferência
o orçamento da auditoria inicial. Dados observados por provedor não
equivalem à fatura. A previsão histórica ex ante mantém sua metodologia,
incerteza e tratamento de tarefas opcionais.

## Tempos físicos de atividades de fulfillment - sem cronômetro exclusivo (#319)

A projeção financeira read-only mostra agora, quando houver registros atribuíveis,
as durações de `audit_fulfillment_attempts` vinculadas fisicamente à AUD e a
`audit_fulfillment_work_items`. Cada `component` apresenta a população de
tentativas, quantidade de intervalos de tempo comprovados, tentativas de
reprocessamento, soma de durações e união de intervalos simultâneos.

Essa população **não constitui medição exclusiva das fases técnicas**.
Um work-item pode ter englobado execução de IA, chamada HTTP, coleta ou
recuperação posterior. A soma dos work-items NÃO é tempo não-IA nem deve ser
somada ao total IA, duração HTTP ou wall-clock da AUD. Quando uma tentativa
não tem `finished_at` verificável, o tempo do componente é N/D e não zero
falso. O ledger pode estar ausente em AUDs antigas: a apresentação continua
funcionando sem criar tabela, reprocessar ou simular cronologia ausente.

Todos os dados são apresentados no mesmo bloco de telemetria existente,
sem alterar o modelo de duração do forecast, o índice Apdex ou preços.
Os registros têm identificação de AUD e work-item cruzada, leitura de
SQLite selado somente-leitura, orçamento de 10.000 tentativas e limite
de 32 componentes. O conjunto completo falha fechado se houver
identidade de AUD incongruente ou população truncada. O relatório deixa
a fronteira não exclusiva explícita no texto e no cabeçalho do resultado.


## Reconciliação de identidade e estados das tentativas (#319)

O leitor consultivo de atividades utiliza `LEFT JOIN` com a identidade
da AUD e do work-item. Tentativas órfãs, referências a outra AUD e
linhas multiplicadas por work-items duplicados invalidam o censo inteiro:
nenhuma tentativa desaparece silenciosamente do denominador.

Mesmo com `finished_at` presente, estados não terminais (`RUNNING`,
`PENDING` ou desconhecidos) e intervalos de duração zero permanecem
N/D, não prova de tempo físico. Somente estados terminais reconhecidos
pelo contrato canônico de fulfillment e intervalos positivos podem contar.
Uma falha terminal pode ter tempo medido sem equivaler a sucesso.
A existência de um intervalo inválido torna a soma e união do componente
N/D, com contadores de cobertura preservados.

O console e o HTML passam a explicitar a abstenção por identidade,
população ou schema; não a confundem com tempo zero. As regressões
isoladas incluem órfãos, junção duplicada, caracteres de controle,
estado não terminal com horário de fim e falha terminal. Nenhum
serviço externo, nova AUD ou motor de score é acionado nesse diagnóstico.


## Cobertura da estimativa inicial de chamadas IA (#319)

A prévia sem histórico já informa faixa heurística de ciclos modelados
por provider/contexto, mas **essa faixa não é limite global de tentativas
nem de custo**: Improvement Intelligence, Competitive, análises
direcionadas posteriores e operações de outras etapas podem gerar novas
tentativas, sujeitas a decisões, findings, retries e controles próprios.
O campo exibido passa a ser rotulado `IA - ciclos modelados`, em vez
de um total genérico potencialmente interpretado como máximo da AUD.

Como referência física **retrospectiva e não projeção para outros sites**,
a AUD de 08/10/2026 descrita na issue #319 registrou sete tentativas
`ai_provider_attempts` e uma `content_remediation_attempts` em uma
URL: oito tentativas distintas. O resultado não autoriza transportar o
mesmo número para outra URL, nem inferir tokens, tempo, custo ou
consentimento de chamadas futuras. A prévia continua sem calcular
custo total na ausência de consumo comparável, preservando o gate
financeiro anterior à AUD. Nenhum orquestrador ou preço foi modificado.
