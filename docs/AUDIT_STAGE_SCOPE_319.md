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


## Projeção dos cronômetros operacionais na página metrics.html (13/10/2026)

A página final `metrics.html` passa a apresentar em seção própria os eventos
`pipeline_step_timer_evidence` **já inspecionados** pelo leitor read-only
`audit-attempts`. Cada linha apresenta fase declarada, operação, resultado,
duração monotônica observada do wrapper, posição temporal e timestamp UTC.
A projeção apenas lê o arquivo `logs/audit.log` da AUD atual: não dispara
coleta, não modifica logs/bancos, não acrescenta sensores e não recalcula
qualquer métrica física, previsão ou score.

O relatório diferencia a localização na janela da AUD COMPLETED/COMPLETE
(`WITHIN_VERIFIED_WINDOW_UNSEALED`) dos eventos cuja correspondência com
a sessão inicial **não foi provada**. Uma AUD parcial não recebe atribuição
positiva, ainda que o relógio do evento seja compatível com a janela de
outra execução.

Quando o log não existe, excede limites ou contém JSONL inválido, a seção
indica **N/D**, sem publicar durações parcialmente decodificadas. Eventos
com `audit_id` diferente não são incluídos. A tabela é estritamente
diagnóstica: o log é operacional, não selado; passos podem estar aninhados,
falhar, ocorrer em paralelo ou representar continuação/RPR. **Não somar
as durações nem calcular tempo exclusivo/residual por etapa.** A fonte
`pipeline_step_timer_evidence` não altera
`non_ai_stages_measured=false`.

Teste dirigido: `tests/test_audit_stage_scope_319.py`, quatro cenários
com evidência válida, JSONL corrompido após evento válido, log ausente
e estado lógico `PARTIAL_RETRYABLE`; confirma exclusão de outra AUD,
ausência de falso tempo físico e bytes originais intactos.

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


## Selo físico do leitor `audit-attempts` (12/10/2026)

Para a inspeção **offline** de uma única AUD, a cronologia econômica
M18/M20 passa a utilizar `read_audit_attempt_timeline(...,
sealed_source=True)`, abrindo a conexão com `mode=ro&immutable=1`
após rejeitar `-wal`, `-shm`, `-journal` e symlink. O leitor
reconfere os sidecars ao encerrar. Os consumidores que podem operar
sobre a AUD **em andamento** conservam explicitamente o modo
`mode=ro` anterior; nenhum motor ou console foi alterado.

A projeção `rasai audit-attempts` calcula SHA-256 do arquivo físico
(mais tamanho, até 1 GiB) **antes** de consultar metadados, ledgers,
fulfillment e timers e novamente após encerrar os readers. Se os
bytes mudam, a inspeção aborta e não publica resultados parciais ou
somatórios de custo. Os testes simulam WAL antes do read,
modificação de arquivo sem sidecar ao final, banco acima do limite
e a compatibilidade dos leitores legados. O hash detecta mutações
durante a inspeção, mas não constitui lock global ou autenticação
criptográfica prévia da origem do arquivo.


## Segundo leitor imutável do forecast histórico (#319)

O forecast ex ante consulta apenas AUDs locais **fisicamente
estabilizadas e logicamente completas**. Seu leitor principal já
abria `mode=ro&immutable=1`; agora a leitura secundária dos
ledgers M18/M20 usa
`read_audit_attempt_timeline(..., sealed_source=True)`,
herdando a rejeição de symlink e `audit.db-wal`,
`audit.db-shm` ou `audit.db-journal` antes e depois da leitura.
O forecast mantém ainda seu guard existente de identidade/mtime/
tamanho e ausência de sidecars após todos os consumidores.

Os testes de sidecar criado durante a leitura e de mudança de
mtime continuam isolados e foram adaptados para provar que
`sealed_source=True` é usado nos cinco históricos elegíveis.
Nenhum consumidor de AUD em andamento foi alterado. Isso evita
leitura física heterogênea, mas não autentica o provedor nem
converte wrappers em relógios exclusivos de etapa; a previsão
permanece histórica e não altera preços, timeout ou motores.


## Estados do fulfillment e legitimidade de intervalos (12/10/2026)

O leitor consultivo de tentativas `audit_fulfillment_timing_319` considera
intervalo temporal verificado somente se houver início/fim válidos **e** o
status persistido pertencer à lista fechada de resultados finais de tentativa:
`SUCCESS`, `FAILED_RETRYABLE`, `FAILED_PERMANENT` ou `BLOCKED`.
`RUNNING`, `PENDING`, `WAITING_FOR_DATA`, textos desconhecidos e variantes
malformadas não comprovam encerramento, mesmo quando existem timestamps.
Eles seguem em `WINDOW_UNVERIFIED`, com intervalos `N/D`, sem representar
cronômetro exclusivo de etapa ou alimentar forecast/custo. Testes offline
SQLite preservam as tentativas terminais e recusam as não comprovadas,
sem alterar ledger, writer, motor, preço ou execução.


## Unicidade física da AUD no forecast histórico (12/10/2026)

O leitor consultivo de duração histórica só admite no conjunto de treino
uma fonte cujo `audit.db` contenha **uma única linha física** na tabela
`audits`, com identidade igual ao diretório `AUD-*` e estado
`COMPLETED/COMPLETE`. Filtrar previamente pelo ID esperado ocultaria
outra linha de ciclo de vida estrangeira e poderia contaminar a amostra
usada para mediana, P90 e backtests. Um banco com duas linhas distintas
é excluído por completo; as demais AUDs permanecem elegíveis. Teste
isolado compara uma coorte de cinco AUDs válidas com quatro após inserir
uma linha estrangeira apenas em uma fonte, comprovando previsão N/D
quando o mínimo de cinco fontes íntegros deixa de ser atendido.
Esta verificação não altera os bancos fonte, o ledger de fulfillment,
o console operacional nem os preços ou tempos persistidos.


## Ambiguidade de escopo no JSON da configuração histórica (12/10/2026)

O forecast de duração somente aceita uma AUD histórica quando
`console_execution_projections.configuration` é um objeto JSON
inequívoco: **qualquer chave duplicada** invalida a elegibilidade
daquela fonte. O decoder padrão Python manteria silenciosamente
a última declaração, permitindo que parâmetros conflitantes como
`device`, `input_mode`, `web_max_pages` ou
`content_remediation` fossem mascarados por um valor comparável.
Uma coorte de cinco AUDs que contém uma configuração física ambígua
passa a ter apenas quatro fontes elegíveis, retornando previsão N/D
pelo limite mínimo do forecast, em vez de publicar P90 enganoso.
Quatro fixtures SQLite validam a exclusão seletiva, sem redes,
escritas do leitor, ajuste pós-fato de pricing ou alteração do
motor de auditoria.


## Validade dos valores monetarios no explicador (12/10/2026)

O explicador consultivo do forecast de custo somente considera
montantes finitos e nao negativos. Valores booleanos, negativos ou
infinitos nao representam despesas monetarias verificadas e devem
resultar em posicao de faixa N/D e ausencia de desvio percentual
calculado sobre esse valor. Um custo zero explicito permanece valido
quando o ledger comprova cobertura monetaria, e o rotulo de desvio
pontual continua distinto do intervalo historico. Testes isolados
nao recalculam precos, estimativas nem tokens e nao fazem consultas
a provedores.


## Interpretacao financeira na pagina final IA e integracoes (12/10/2026)

A pagina final `ai-integrations.html` agora inclui a leitura
observacional de custo ja disponivel em `audit_cost_explain.forecast_readout`.
Quando ha cobertura monetaria completa em uma unica moeda compativel
com a previsao, e o valor agregado das tentativas coincide com o
valor pos-execucao persistido, a pagina distingue o desvio frente
a estimativa pontual da posicao dentro/fora da faixa historica.
O rotulo de severidade persistido nao e recalculado.

Se ha varias moedas, total inconsistente, tentativas sem preco
ou analise direcionada/complementar cuja inclusao no escopo
pre-auditoria nao foi comprovada, a posicao na faixa permanece N/D
e nao se publica delta com atribuicao economica indevida. A pagina
mantem o custo e a moeda individuais, sem conversao cambial, sem
duplicar custo de chamadas direcionadas e sem sugerir invoice.
Testes locais exercitam moedas mistas, conciliacao, divergencia
persistida e escopo direcionado, sem alterar a base SQL original
durante a renderizacao e sem executar qualquer IA.


## Persisted finance validation in the final report (13/10/2026)

The final IA/integrations HTML now checks the finite, nonnegative
nature of forecast monetary totals and interval endpoints before
displaying them or claiming reconciliation. It preserves legitimate
negative *deviations* as signed arithmetic, while invalid/nonfinite
deviation values show N/D rather than `nan%` or `Infinity`.
A malformed `actual_cost` cannot be converted to zero and reported
as reconciled with an otherwise valid zero-valued ledger.
The original persisted forecast is never rewritten, no pricing rule
is recalculated and the raw technical artifacts remain unchanged.
