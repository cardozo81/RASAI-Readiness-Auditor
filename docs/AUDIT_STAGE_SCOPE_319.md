# #319 - Tempo ativo, custo e escopo temporal M18/M20 (comprovação por sessão)

## Entrega técnica

O módulo de inspeção read-only `audit_attempt_inspection_319.py` passa a
devolver `ai_attempt_execution_scope.by_stage`: partição por etapa declarada
e posição temporal de cada tentativa em relação à única sessão do console
que pode ser comprovada como `COMPLETED/COMPLETE`. O relatório
`metrics.html` apresenta uma segunda tabela explicativa, **sem alterar
a tabela de IA existente**, o runtime, os ledgers ou scores.

As tentativas são consultadas em `ai_provider_attempts` e
`content_remediation_attempts`, sempre pelo `audit_id` corrente e
sem cruzar linhas de outras auditorias. Para cada estágio e classe temporal,
há quantidade, soma física das durações conhecidas, união dos intervalos
com timestamps válidos, eventual sobreposição, cobertura de custo
observado USD, valores estimados pós-uso e lacunas.

As classes temporais são:
`WITHIN_VERIFIED_CONSOLE_SESSION`,
`AFTER_VERIFIED_CONSOLE_SESSION`,
`BEFORE_VERIFIED_CONSOLE_SESSION`, e
`UNCERTAIN_TIME_OR_SCOPE`. Relógios inválidos, sobreposição
das bordas da sessão, AUD parcial, ausência de uma única janela
ou sessão sem clock verificável produzem escopo **não comprovável**,
não um falso status `AFTER` ou `WITHIN`.

**Aviso metodológico:** a classificação por relógio **não prova que uma
chamada foi solicitada como complemento ou RPR**, nem que seu custo
estava incluído na previsão central. Os valores de tentativas não são
cobrança confirmada. Não subtrair custos estimados de custos
observados como se fossem medidas da mesma base; não somar tempo
de IA sobreposta como se fosse wall-clock da auditoria.

## Evidência e segurança

Fixture SQLite isolada: 7 tentativas M18 e 1 M20; 2 Improvement
Intelligence com intervalos sobrepostos (240 s de soma, 180 s
de união e 60 s de overlap); 1 Directed Analysis posterior,
1 tentativa que cruza o fim da sessão, 1 tentativa sem clocks,
1 Content Remediation da própria auditoria e 1 tentativa
intrusa de outra AUD. Testes confirmam 8/8 registros atribuíveis,
custo por estágio, ausência de vazamento inter-AUD e SHA-256
de `audit.db` inalterado antes/depois de inspeção e
renderização. Cenário `PARTIAL_RETRYABLE` e ausência de
janela coerente preservam N/D em todas as fases.

Limites: o bloco de IA não prova duração física de captura,
renderização, PSI nem Apdex; esses dados continuam N/D se
não houver timestamps de estágio com mesma identidade.
A estimativa prévia segue histórica e independente do
observado, sem recalibração pós-fato. Não houve nova AUD,
requisição comercial, migração SQLite, mudança no motor
AI/AUTO, scoring ou reprocessamento.

## Projeção M21 observada na página metrics.html

A apresentação `metrics.html` agora reutiliza o inventário read-only de
`inspect_audit_attempts`, incluindo
`observed_http_request_sums_ms` somente para
`PAGESPEED_INSIGHTS` e `CRUX_API` da AUD corrente.

Uma nova seção **Tempos observados de requisições web  -  M21** apresenta
as somas de HTTP verificadas em segundos. Um serviço sem telemetria, ou
com qualquer tentativa de tempo inválido, exibe **N/D** em vez de zero,
mesmo quando outras tentativas desse serviço têm duração válida.
Requisições de AUDs alheias e de serviços desconhecidos não participam.

**Invariante:** soma de tempo HTTP não é relógio físico da etapa, não
comprova tempo de experiência do usuário e não pode ser adicionada ao
tempo ativo IA nem à duração física total da auditoria. O tempo físico de
etapas não-IA continua **N/D**. A mudança se limita à projeção de
relatório: nenhuma nova tabela, aquisição, fatura, IA, forecast, score
ou alteração do pacote de auditoria original.

## Incremento WKA: inventário de relógios operacionais não-IA

A tabela persistida `audit_fulfillment_attempts` possui `started_at` e
`finished_at` para tentativas de work-items relacionados a
`audit_fulfillment_work_items`. O relatório `metrics.html` agora pode
exibir os **intervalos entre os marcos das tentativas de fulfillment**
quando o ledger está disponível, sem alterar o contrato do motor.

O resultado de `inspect_audit_attempts` inclui
`fulfillment_attempt_temporal_evidence` com:
- componente efetivo do work-item, número de tentativas e cobertura;
- soma de intervalos completos, união temporal e sobreposição;
- colocação dentro/antes/depois/cruzando a única janela do console validada;
- classe separada `REPROCESS_ATTEMPT` quando há `reprocess_id`;
- `WINDOW_UNVERIFIED`, `N/D` e ausência de agregação completa
  caso faltem timestamps válidos.

A leitura exige identificação explícita da AUD em ambas as tabelas,
usa SQLite em `mode=ro` e não altera banco, artefato, amostras,
custo ou resultados históricos. AUD incompleta não recebe atribuição
positiva à sessão inicial, mesmo quando a tentativa tem timestamp.

**Limite metodológico fundamental:** o invólucro
`begin_attempt`/`finish_attempt` pode incluir chamadas aninhadas,
esperas, concorrência e operações de vários tipos; seus timestamps
não são cronômetros físicos exclusivos das fases M3/M21/M23/M25,
renderização, processamento determinístico ou relatório. Portanto
`non_ai_stages_measured=false` permanece. Não utilizar esses dados
para subtração residual, previsão por fase ou recalibração do Apdex.

Fixture focal: tentativas de extração sobrepostas (240 s de soma,
180 s de união, 60 s de sobreposição), reprocessamento separado,
tentativa posterior à sessão, clock ingênuo invalidado, AUD parcial,
entidade de outra AUD excluída e SHA-256 do banco preservado.
Não foi executado smoke com coleta nem API comercial.

Próxima dependência da #319: tempos físicos **da própria fase**
precisam de marcos instrumentados com `execution_id` e período de
execução inequívoco. O WKA não autoriza afirmar duração física exclusiva.
