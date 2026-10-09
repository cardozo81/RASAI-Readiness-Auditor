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
