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

## Durações monotônicas de wrappers do pipeline - evidência consultiva

O runtime `audit_progress_runtime._wrap_step` já emite eventos
`AUDIT_PIPELINE_STEP_FINISHED` no arquivo operacional `logs/audit.log`.
O inspetor `rasai audit-attempts AUD-DIR` agora projeta
`pipeline_step_timer_evidence`, somente quando o JSONL local
contém duração monotônica `duration_ms` válida, ID da AUD e timestamp
com fuso. Limites: 8 MiB, 4.000 eventos; não gera arquivos,
não chama provedores e recusa symlinks ou registro corrompido.

Cada linha é **somente o tempo observado de um wrapper de
execução**, com possibilidade de sobreposição, etapas aninhadas,
falha, continuação ou RPR. O log não é evidência selada:
`operational_log_sealed_evidence=false`,
`exclusive_stage_wall_clock_proven=false` e
`non_ai_stages_measured=false`. Mesmo um evento dentro da sessão
física verificada recebe `WITHIN_VERIFIED_WINDOW_UNSEALED`,
não é convertido em cronômetro exclusivo de captura/Apdex ou
parcela somável à duração física da AUD.

Este recorte usa instrumentos já existentes, sem novos hooks,
mas não homologa overhead de sensor de conteúdo nem previsão
ex ante de custos e tempos por etapa.


## Replay cronologico pre-execucao de P90 (#319)

A prévia de `audit_duration_forecast_319.py` mantém o backtest
retrospectivo leave-one-out como descritor secundário, sem alterar
preço, orquestrador, motor de coleta, cálculo de tempo histórico nem
o contrato já materializado. Um **segundo diagnóstico**,
`forward_p90_backtest`, avalia as AUDs cronologicamente, em janela
expansiva: para cada início físico do console, o P90 é calculado
**exclusivamente** com AUDs comparáveis, completas e terminadas
até esse início. Auditorias em andamento, iniciadas simultaneamente
ou encerradas no futuro não entram na amostra daquele instante.

Critérios: mínimo de oito AUDs físicas elegíveis no total, mínimo
de cinco AUDs anteriores **já concluídas** por janela avaliada e
pelo menos três janelas realmente avaliáveis. Se esses requisitos
não forem demonstráveis, `forward_p90_backtest=None` (N/D),
mesmo que o leave-one-out retrospectivo ainda exista. A ordenação
é pelos relógios persistidos da execução; a data de modificação do
arquivo pode limitar quais AUDs são inspecionadas, mas **não** pode
determinar a posição temporal de um fold.

O console mostra a fração de execuções cuja duração observada ficou
dentro do P90 conhecido *antes* da execução, com ressalva explícita
de que se trata de observações locais, não homologação prospectiva
em produção, previsão individual ou SLA de 90%. Os testes cobrem
crescimento da duração que estoura o P90 disponível no passado,
execuções simultâneas, ordenação de mtime invertida, AUD parcial
excluída da janela e preservação dos arquivos físicos. Sem requisições
externas e sem alteração de scores.


## Imutabilidade do histórico usado para previsão (#319)

A previsão de duração recusa uma AUD física que contenha
`audit.db-wal`, `audit.db-shm` ou `audit.db-journal`, mesmo
que a coluna lógica de conclusão tenha valor COMPLETE. Esses
arquivos podem indicar transação ou snapshot SQLite ainda não
consolidado; consultá-los como histórico estável produziria um P90
sem representação fiel nos bytes de `audit.db`.

A leitura do arquivo principal passou a `mode=ro&immutable=1`
e `PRAGMA query_only=ON`; nenhuma transação, checkpoint, migração
ou gravação de metadados é iniciada. Esse gate afeta somente
a **elegibilidade** da amostra histórica. Com menos de cinco
AUDs restantes, a previsão fica N/D, em vez de reutilizar
a fonte possivelmente em uso. A rejeição é conservadora e
não tenta inferir se o WAL pendente é válido ou encerrado.

## Classificação CRÍTICO versus faixa provável de custo

A aderência financeira existente usa **dois comparadores independentes**:
o estado `CRÍTICO` decorre exclusivamente de desvio superior a 5%
contra a **estimativa monetária pontual**, enquanto a posição histórica
é calculada contra `likely_low/likely_high/potential`.
Logo, uma AUD pode ser `CRÍTICO` e, simultaneamente,
`dentro da faixa provável histórica` sem contradição.

O console e as notas persistidas da aderência agora explicam
explicitamente essa condição quando ela ocorre. A mudança não ajusta
threshold de alerta, pricing, unidade monetária, estimativa,
P90, fatura, score nem motor de IA. Para estado CRÍTICO acima da faixa,
a informação não afirma erroneamente que a observação ficou dentro.


## Inspeção de AUD com SQLite estável (12/10/2026)

O comando público read-only `rasai audit-attempts AUD-DIR` passou a
recusar `audit.db-wal`, `audit.db-shm` e `audit.db-journal` antes de
consultar os ledgers e novamente após a segunda leitura do timeline.
A primeira conexão de metadados usa `mode=ro&immutable=1` com
`PRAGMA query_only=ON`; nenhuma leitura realiza DDL, checkpoint ou
remoção de sidecar.

A presença desses arquivos pode indicar transação ainda não
consolidada; a interpretação deve abortar, em vez de confiar no arquivo
principal isolado. Fixtures simulam sidecars antes e durante a leitura,
com preservação dos bytes de todas as fontes. Isso não constitui lock
global ou assinatura criptográfica da AUD e não torna os tempos de
wrappers cronômetros exclusivos por fase.


## Identificadores físicos de tentativas IA/M20 (12/10/2026)

Os leitores consultivos de M18/M20 e do recorte de escopo #319
não podem mais descartar silenciosamente uma linha cujo
`attempt_id` repete outro dentro **do mesmo ledger e AUD**.
Isso escondia execuções e subestimava tempo físico observado,
custo USD e contagens por fase. Identificador ausente ou repetido
resulta em erro explícito de evidência ambígua, nunca em
soma parcial publicada. IDs iguais em AUDs diferentes são
admitidos se cada leitura está fisicamente limitada à AUD
selecionada; M18 e M20 continuam universos distintos.

Fixtures SQLite sem chave única simulam fonte legada anômala,
contém tentativas duplicadas com custos diferentes e comprovam
preservação byte a byte. Nenhum preço, duração, timeout,
seletor AUTO, sensor M23/M25, estrutura de ledger ou
previsão ex ante foi modificado.
