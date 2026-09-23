# Relatório consolidado longitudinal

## Objetivo

O relatório consolidado longitudinal reúne auditorias `AUD-*` já concluídas para explicar a trajetória de uma mesma URL no mesmo dispositivo ao longo do tempo.

O consolidado não executa nova auditoria, não refaz crawl, não recalcula regras dos catálogos, não chama PageSpeed, CrUX ou outras fontes de aquisição. A fonte de verdade continua sendo cada `AUD-*/audit.db` e seus artifacts persistidos.

**Formato público:** **001**  
**Identificador técnico do formato:** `CONS-5`

O nome humano da superfície é **Relatório Consolidado Longitudinal**. O identificador técnico permanece disponível em manifestos e rastreabilidade.

Contratos associados:

```text
TEMPORAL-APDEX-001
CONSOLIDATED-EVOLUTION-001
CONSOLIDATED-SPECIALIST-001
CONSOLIDATED-LONGITUDINAL-001
CONSOLIDATED-CATALOG-LONGITUDINAL-006
CONSOLIDATED-EXECUTION-001
CONSOLIDATED-SOURCE-GOVERNANCE-003
CONSOLIDATED-DECISION-CONTEXT-002
CONSOLIDATED-AI-CONTEXT-001
CONSOLIDATED-MATERIALIZATION-003
```

## Compromisso funcional do relatório consolidado

O `CONS-*` se compromete a **comparar e explicar evolução longitudinal** usando somente auditorias `AUD-*` selecionadas e compatíveis, preservando metodologia e evidência de origem.

Ele deve:

- tratar cada AUD como observação independente e read-only;
- validar identidade de URL, dispositivo, metodologia, configuração comparável, integridade e conclusividade das fontes;
- preservar série temporal, marco inicial, marco final e auditorias intermediárias conforme o modo de seleção;
- reutilizar scores, métricas, estados, findings e evidências persistidos sem recalcular a auditoria de origem;
- distinguir melhora/regressão, correção verificada, indisponibilidade e não comparabilidade;
- comparar o **Índice de Prontidão Search & IA** somente quando `scoring_version` for metodologicamente compatível;
- consolidar Apdex a partir de amostras comparáveis, nunca pela média ingênua de percentis ou scores já agregados;
- manter IA facultativa: sem IA, o consolidado determinístico continua válido e a camada de IA aparece como não solicitada, não como falha;
- quando IA for usada, fornecer somente contexto governado/persistido e registrar tentativas, provider, modelo, tokens e custo;
- produzir pacote autocontido para inspeção dos dados materializados do próprio CONS, com manifest, hashes e rastreabilidade até as AUDs fonte. A navegação HTML para `AUD-*/report-catalog/` usa links relativos da árvore canônica `audits/` e, portanto, não é portátil quando o diretório `CONS-*` é copiado isoladamente.

O `CONS-*` não executa nova auditoria, não reabre o site, não refaz crawling, não recalcula o **Índice de Prontidão Search & IA** nem o **Método de Pontuação de Prontidão** das fontes (IDs técnicos `SARI-001`/`SCORE-GEO-004`) e não converte diferença temporal em causalidade.

## Pré-requisitos obrigatórios

O **Relatório Consolidado Longitudinal**, formato público **001** (`CONS-5` como ID técnico), exige:

- exatamente uma URL;
- exatamente um dispositivo;
- pelo menos duas auditorias elegíveis;
- URL idêntica entre os marcos e as intermediárias;
- dispositivo idêntico entre os marcos e as intermediárias;
- fontes `AUD-*` legíveis e preservadas em modo somente leitura.

O usuário escolhe duas auditorias sem atribuir papel temporal a nenhuma delas. O sistema ordena os dois marcos pelo **instante real de `event_time`**: a menor data/hora é sempre **BASE** e a maior data/hora é sempre **ATUAL**, independentemente da ordem em que foram selecionadas no console, CLI ou SaaS. Os offsets de timezone são normalizados antes da comparação; a ordenação não depende da representação textual do timestamp. Se houver auditorias compatíveis entre elas, a composição segue uma política explícita:

```text
ALL
SUCCESS_ONLY
MANUAL
```

`SUCCESS_ONLY` utiliza o estado canônico da governança das fontes; não equivale apenas a `status=COMPLETED`. Em `MANUAL`, BASE e ATUAL permanecem obrigatórias e o usuário escolhe somente as intermediárias.

O uso de IA é opcional. No console, a decisão final aparece como duas ações irmãs: **Gerar relatório consolidado com IA** e **Gerar relatório consolidado sem IA**. Ambas são formas válidas de materializar o consolidado; a ausência deliberada de IA permanece `NOT_REQUESTED`, não falha.

Mobile e Desktop nunca são combinados. Uma única auditoria não caracteriza série longitudinal.

## Reconhecimento e congelamento do conjunto efetivo

### Apresentação das listas no console

As superfícies `CONSOLIDADOS > HISTÓRICO` e `CONSOLIDADOS > GERAR > PRIMEIRO/SEGUNDO MARCO` seguem a mesma gramática tabular usada no histórico de auditorias, sem alterar a tela `AUDITORIAS / HISTÓRICO`. Datas e horas são convertidas para o fuso configurado em `RASAI_PRESENTATION_TIMEZONE`.

Na seleção de marcos, a coluna **ELEGÍVEL** significa fechamento diagnóstico apto a participar de uma consolidação conclusiva. Uma fonte íntegra que o contrato permita ler apenas de forma não conclusiva permanece selecionável quando aplicável, mas aparece explicitamente como **NÃO**. No console colorido:

- verde identifica fonte elegível/conclusiva e seleção elegível;
- amarelo identifica fonte não elegível ou seleção que introduz limitação não conclusiva;
- vermelho identifica falha/bloqueio;
- cinza identifica estado neutro/aguardando;
- ciano identifica contexto operacional/informativo.

Cores são somente apresentação; o texto continua sendo a fonte semântica para terminais sem ANSI/VT ou com `NO_COLOR`.

Antes de cruzar dados, o console executa uma fase explícita de **Reconhecendo auditorias**. Essa fase é somente de descoberta/qualificação: atualiza o índice reconstruível, contabiliza AUDs encontradas, elegíveis, excluídas e problemas de leitura, sem iniciar análise longitudinal nem chamar IA.

Depois de o operador definir BASE, ATUAL e a política de seleção, o conjunto efetivo é congelado pelos `audit_ids` selecionados. A partir desse ponto:

- somente essas AUDs alimentam preparação, cálculos, cruzamentos e contexto de IA;
- AUDs fora do conjunto não entram silenciosamente porque existem no diretório;
- a validação de fontes e artefatos ocorre antes do processamento analítico;
- mudança nas fontes/fingerprint durante a preparação invalida a execução e exige reinício, em vez de alterar a população no meio do cálculo.

A apresentação canônica do console usa a sequência:

```text
1. Reconhecendo auditorias
2. Validando fontes e artefatos
3. Preparando conjunto de análise
4. Análise complementar / IA
5. Gerando relatório
6. Validação e conclusão
```

A etapa **Gerando relatório** usa somente dados/evidências já persistidos, consolida os resultados, renderiza o HTML e grava os artefatos do `CONS-*`. Ela não reabre a URL, não executa novo crawl e não chama fontes de aquisição apenas para materializar o relatório.
## Fonte de verdade e arquitetura

Garantias:

- o consolidador nunca altera `AUD-*/audit.db`; cada leitura usa modo somente leitura;
- um RPR governado, executado fora do consolidador, pode materializar uma revisão posterior da mesma AUD; por isso o CONS identifica a revisão lógica usada em vez de presumir que o arquivo nunca muda;
- leitura SQLite usa modo somente leitura;
- nenhum schema de `audit.db` é migrado pelo consolidador;
- `.rasai/consolidated-index.db` é cache reconstruível;
- Monitoring e Fix Verification produzem deltas determinísticos;
- dados ausentes não viram zero;
- séries incompatíveis não são fundidas silenciosamente;
- a IA, quando solicitada, interpreta evidências sem alterar pontuações, achados, Índice de Prontidão Search & IA ou Método de Pontuação de Prontidão;
- cada AUD fonte recebe SHA-256 do `audit.db` e, quando presente, do WAL SQLite, sem escrita na origem;
- cada tentativa de geração cria uma **Execução de Consolidação** - **Consolidated Run** - identificada tecnicamente por `CONRUN-*`;
- o pacote final é autocontido para inspeção de seu conteúdo materializado;
- `manifest.json.source_navigation` declara a dependência da árvore canônica para links relativos às AUDs fonte; IDs, hashes e evidências do CONS permanecem válidos mesmo se esses links não puderem ser resolvidos fora dessa árvore;
- a navegação para `AUD-*/report-catalog/` é criada somente quando o manifest da fonte comprova freshness contra o `audit.db` vivo. Um relatório fonte ausente/desatualizado não invalida os dados do CONS, que continuam originados no SQLite, mas o link é suprimido e a condição aparece na governança.

Fluxo lógico:

```text
AUD-*/audit.db
    |
    +--> índice reconstruível
    +--> governança das fontes
    +--> Monitoring / Fix Verification
    +--> leitura estruturada dos CAT-*
    +--> intervalos consecutivos
    +--> BASE -> ATUAL
    |
    +--> consolidação determinística
            |
            +--> modo Determinístico
            |       + report.html
            |       + manifest.json
            |       + decision-context.json
            |       + longitudinal-evidence.json
            |       + execution.json
            |
            +--> modo Determinístico + IA
                    + perfil EVOLUTION
                    + specialist-analysis.json
                    + ai-exchanges.json
                    + artifacts determinísticos acima
```

`specialist-analysis.json` e `ai-exchanges.json` pertencem somente ao modo em que IA foi solicitada. `NOT_REQUESTED` é estado válido e neutro.

## Revisão temporal e identidade da fonte

Uma AUD continua sendo uma única observação longitudinal, mesmo quando recebe RPR. O CONS, porém, não confunde mais **tempo da observação** com **tempo da revisão**. A governança de cada fonte materializa:

```text
observation_at
revision_at
revision_mode
source_revision_id
source_revision_logical_sha256
post_observation_revision
temporal_revision_overlap
temporal_revision_overlap_with
temporal_revision_overlap_state
```

`source_revision_id` é derivado do digest lógico do SQLite e identifica exatamente a revisão de dados usada pelo CONS sem criar uma segunda persistência da AUD. RPR sem item materialmente resolvido não avança a revisão temporal.

Quando uma AUD anterior recebe RPR depois da observação da AUD seguinte:

- `REPLAY_SAFE_AFTER_NEXT_OBSERVATION`: a fonte continua utilizável como observação original, pois o RPR reutiliza evidência persistida; o CONS registra que parte do conteúdo derivado foi materializada posteriormente e trata a leitura como revisão posterior, não nova observação;
- `LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION`: a robustez longitudinal é reduzida e a comparação deve explicitar que dados afetados pela recoleta podem não representar o estado cronológico original;
- `UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION`: exige qualificação/revisão manual porque o modo temporal não foi comprovado.

Esses estados não recalculam SARI, SCORE-GEO ou Apdex e não mudam silenciosamente a elegibilidade da AUD. Eles qualificam a confiabilidade e a interpretação do CONS.

## Escopo longitudinal

Todas as auditorias elegíveis do filtro são ordenadas por `event_time`.

O relatório analisa:

1. cada intervalo consecutivo;
2. o marco inicial contra o marco final;
3. estados e métricas dos catálogos;
4. evidências persistidas alteradas;
5. Fix Verification;
6. estabilidade positiva;
7. problemas persistentes;
8. regressões;
9. novos sinais;
10. conflitos entre dimensões;
11. caminhos técnicos de evolução.

A estabilidade não é descartada. Itens estáveis dentro do esperado recebem menor destaque. Itens estáveis que continuam problemáticos permanecem visíveis como pendências persistentes.

## Catálogos

A camada `CONSOLIDATED-CATALOG-LONGITUDINAL-006` lê as fontes estruturadas usadas pelos relatórios de catálogo e compara, por intervalo:

Registros persistidos com dispositivo `BOTH` pertencem ao escopo de qualquer consolidação Mobile ou Desktop, pois representam evidência aplicável aos dois contextos. Eles não podem ser descartados pelo filtro longitudinal de dispositivo.

- estado do catálogo;
- métricas;
- configuração efetiva;
- contagem de fontes persistidas;
- diferenças em registros persistidos;
- disponibilidade de evidência.

O consolidado não depende da leitura do HTML dos catálogos.

A comparação preserva o escopo da URL e do dispositivo sempre que a própria fonte possui essas dimensões.

## Evolução determinística

`CONSOLIDATED-EVOLUTION-001` reutiliza Monitoring e Quality/Fix Verification.

Estados possíveis incluem:

```text
IMPROVED
RESOLVED
REGRESSED
NEW
CHANGED
DATA_UNAVAILABLE
NOT_COMPARABLE
FIXED
PARTIALLY_FIXED
NOT_FIXED
NOT_VERIFIABLE
```

Regras de interpretação:

```text
melhora observada != correção verificada
correção verificada != causalidade
associação temporal != prova de impacto
```

O relatório preserva valores anterior/posterior, delta, URL, dispositivo, regra e demais identificadores quando existirem na evidência persistida.

Quando uma métrica numérica admite comparação direta, a aritmética de evolução é:

```text
Delta absoluto = valor_final - valor_inicial

Variação percentual =
  (Delta absoluto / abs(valor_inicial)) x 100
```

A variação percentual fica indefinida quando `valor_inicial = 0`. O sinal do delta preserva a direção matemática; a interpretação de melhora ou piora depende da semântica da métrica, porque em algumas grandezas valores menores são melhores.

## Análise por IA

A IA é uma camada opcional do `CONS-5`. Quando não solicitada, o relatório permanece válido e registra:

```text
requested=false
required=false
status=NOT_REQUESTED
generation_mode=DETERMINISTIC
```

Quando solicitada, o consolidado usa o perfil canônico:

```text
EVOLUTION
```

A chamada ocorre somente depois que o contexto determinístico longitudinal foi preparado. A IA recebe uma projeção controlada da evidência já persistida; o corpus integral continua local em `longitudinal-evidence.json`.

A projeção usa `CONSOLIDATED-AI-CONTEXT-001` e respeita o limite de entrada configurado. A compactação afeta somente o contexto externo e não remove dados da consolidação determinística.

A análise por IA pode:

- interpretar cada intervalo consecutivo;
- relacionar dimensões e evidências;
- identificar picos, quedas e reversões;
- reconhecer estabilidade positiva e persistências problemáticas;
- apontar trade-offs;
- propor prioridades e caminhos de ação;
- declarar evidência insuficiente.

Níveis permitidos de evidência interpretativa:

```text
EVIDENCIA_DIRETA
ASSOCIACAO_FORTE
ASSOCIACAO_POSSIVEL
INDETERMINADO
```

A IA não pode inventar valores, seletores, vulnerabilidades, causas, resultados, URLs ou evidências. Tentativas externas históricas/superadas não podem ser descritas como estado final: a projeção informa explicitamente a tentativa efetiva representada pela observação persistida mais recente. Referências `AUD-*` produzidas pela IA devem corresponder exatamente a um ID canônico de `scope.audit_ids`; identificadores truncados ou inventados invalidam a resposta e não são promovidos ao relatório. Se a IA solicitada não concluir, os dados determinísticos permanecem preservados e auditáveis; o estado da camada de IA é explicitamente registrado.

## Seleção de provedor e custo

O consolidado reutiliza o roteamento canônico de IA do RASAi.

São aceitos:

- provedor explícito;
- modelo explícito quando suportado;
- reasoning configurado;
- `auto`, quando disponível no runtime.

`use_ai=false` é um modo válido e não exige provider: o relatório é gerado em modo determinístico. Quando `use_ai=true`, a camada de IA é solicitada, mas a indisponibilidade ou ausência de provider não impede a materialização determinística; nesse caso o estado da IA permanece explicitamente pendente/indisponível. No console, a seleção **Determinístico** equivale a não solicitar IA.

No console interativo, antes de iniciar a geração:

1. o conjunto longitudinal selecionado é validado e congelado;
2. quando IA é uma possibilidade, a projeção de contexto é montada localmente;
3. tokens são estimados;
4. o catálogo canônico de preços é consultado;
5. provedor/modelo e custo estimado são apresentados quando determináveis;
6. a própria escolha final define e autoriza o modo da geração.

A ação final é:

```text
1. Gerar relatório consolidado com IA
2. Gerar relatório consolidado sem IA
V. Voltar
```

Selecionar `1` autoriza a camada de IA para aquela geração; selecionar `2` inicia diretamente o modo determinístico. Não existe uma segunda pergunta para “autorizar chamada externa” seguida de outra para “confirmar geração”, porque ambas repetiriam a intenção já expressa. Se IA for solicitada mas estiver indisponível, a materialização determinística é preservada e a limitação fica explícita no CONS.

### Fallback e nova rodada

Na primeira rodada, cada provider elegível é tentado no máximo uma vez, respeitando a ordem e a saúde fornecidas pelo runtime existente.

Se a primeira cadeia inteira falhar e houver pelo menos um provider cuja falha seja transitória, o CONS-5 executa uma segunda e última rodada somente com candidatos ainda elegíveis e classificados como retryable.

Falhas transitórias aceitas para a nova rodada incluem rate limit, timeout, rede, erro temporário de servidor, resposta vazia/inválida, contrato de saída e falha não classificada do provider.

Não entram na segunda rodada erros terminais como autenticação, crédito/quota terminal, permissão e modelo inválido.

O consolidado executa a rodada inicial e, no máximo, 1 única rodada adicional de retry. Não existe terceira rodada nem loop indefinido.

Quando o adapter fornece `Retry-After`, o consolidado usa esse valor com teto local de 15 segundos. Para `RATE_LIMIT_ERROR` sem `Retry-After`, a única rodada adicional aguarda no mínimo 5 segundos; para outras falhas transitórias, a espera mínima é 1 segundo.

Essa regra é exclusiva da superfície do consolidado e não modifica o comportamento dos providers, adapters ou do orquestrador compartilhado do RASAi.

## SARI e SCORE-GEO

O consolidado não recalcula SARI nem SCORE-GEO.

Ele lê os valores persistidos de cada auditoria, incluindo:

- Score;
- Coverage;
- Confidence;
- Consolidation;
- `scoring_version`;
- demais dimensões persistidas.

Séries de readiness exigem compatibilidade metodológica e universo de URL coerente.

## Web Performance

Lighthouse e dados de campo permanecem separados.

Podem aparecer, conforme persistência disponível:

- Performance;
- Acessibilidade;
- Boas práticas;
- SEO;
- FCP;
- Speed Index;
- LCP;
- TBT;
- CLS;
- LCP p75;
- INP p75;
- CLS p75;
- avaliação de Core Web Vitals;
- fonte e escopo do dado de campo.

O consolidado não mistura laboratório e campo como se fossem a mesma população.

## Apdex temporal

Synthetic Navigation Apdex e Synthetic User Experience Apdex permanecem domínios separados.

Para séries comparáveis:

```text
Apdex_periodo =
  (sum Satisfied + 0,5 x sum Tolerating)
  / sum amostras_validas
```

Onde:

- `Satisfied` representa amostras classificadas como satisfatórias pelo limiar `T` vigente;
- `Tolerating` representa amostras entre `T` e o limite tolerável do contrato;
- cada amostra tolerável contribui com 0,5;
- amostras inválidas/excluídas não entram no denominador;
- o resultado fica entre 0 e 1 quando existe ao menos uma amostra válida.

Exemplo:

```text
80 Satisfied + 10 Tolerating + 10 Frustrated
Apdex = (80 + 0,5 x 10) / 100
      = 85 / 100
      = 0,85
```

Percentis são recalculados a partir das amostras brutas comparáveis quando a evidência necessária está disponível. Percentis já agregados não são somados ou mediados como se fossem amostras.

## Saída

```text
audits/consolidated/executions/CONRUN-*/
    execution.json
    ai-exchanges.json

audits/consolidated/CONS-*/
    report.html
    rules-reference.html          # quando houver Regras de Avaliação de Prontidão citadas
    manifest.json
    decision-context.json
    longitudinal-evidence.json
    specialist-analysis.json
    ai-exchanges.json
    execution.json
```

O HTML final é estático e organizado por propósito:

1. identificação e período;
2. cobertura de todos os catálogos;
3. marco inicial contra marco final;
4. alertas direcionados;
5. evolução completa por intervalo;
6. itens estáveis em blocos recolhidos, sem perda de auditabilidade;
7. análise longitudinal por IA, trade-offs e estratégia;
8. remediação técnica;
9. execução da IA, custos, tentativas e comunicações.

As tabelas de evolução e mudanças de catálogo não usam limite silencioso de linhas. O recolhimento visual de itens estáveis reduz ruído, mas os dados continuam presentes.

O `manifest.json` registra, entre outros:

- contrato e versão;
- URL;
- dispositivo;
- auditorias usadas;
- período;
- intervalos;
- estado da IA;
- perfil da IA;
- tentativas, rodadas e decisões de fallback/retry;
- custo previsto, observado e desvio;
- referência para o `CONRUN-*`;
- referência para o log de exchanges sanitizados;
- limitações.

`specialist-analysis.json` contém a evidência derivada da consolidação, a interpretação estruturada da IA, candidatos, exclusões, rodadas, tentativas e previsão de custo.

`ai-exchanges.json` preserva os envelopes sanitizados efetivamente enviados e recebidos em cada chamada: provider, modelo, endpoint, duração, resultado, request, response, hashes e indicação de truncamento. Credenciais, headers de autorização e raciocínio privado não são persistidos.

`longitudinal-evidence.json` preserva a base longitudinal integral derivada das AUDs selecionadas, incluindo intervalos, mudanças, verificações, estados de catálogo, remediação técnica e referências disponíveis. O arquivo recebe sanitização defensiva e SHA-256 registrado no manifesto.

`execution.json` é o log operacional do `CONRUN-*`. Ele registra estágios, escopo, previsão, execução de IA, conciliação previsão × observado, resultado final ou erro. Esse artifact permanece mesmo quando não existe `CONS-5`.

## Console interativo

O módulo possui duas visões:

```text
1. Gerar novo consolidado
2. Histórico de consolidados
```

Fluxo de geração:

1. listar/pesquisar auditorias por ID, domínio/URL ou dispositivo;
2. selecionar o primeiro marco;
3. restringir a lista à mesma URL e dispositivo;
4. selecionar o segundo marco;
5. definir BASE/ATUAL pela ordem temporal;
6. localizar intermediárias;
7. escolher `ALL`, `SUCCESS_ONLY` ou `MANUAL`;
8. revisar a composição;
9. escolher **Determinístico** ou **Determinístico + IA**;
10. mostrar prévia de IA/custo antes da ação final quando IA puder ser usada;
11. acompanhar a execução por etapas;
12. abrir o resultado ou voltar ao módulo.

O período é derivado das auditorias selecionadas e não é solicitado como entrada no fluxo normal.

O histórico mostra identidade do CONS, data de geração, URL, dispositivo, período, quantidade de auditorias, política de seleção, modo de geração, estado da IA e confiabilidade do conjunto.

Ações de artifact seguem o padrão geral do console:

```text
M. Ver linha de comando
I. Abrir relatório
P. Abrir pasta
V. Voltar
```

Depois que BASE, ATUAL e política de seleção estão resolvidos, a ação final escolhe gerar com IA ou sem IA. O comando efetivamente executado é registrado e continua acessível por `M. Ver linha de comando` na superfície de resultado/histórico. A projeção usa a CLI pública `rasai consolidate`, que chama os mesmos contratos de seleção e geração deste módulo; não existe um segundo motor longitudinal.

Os comandos Windows, Linux e macOS e as orientações para Task Scheduler, cron/systemd e launchd estão em [EXECUTION_SCHEDULING.md](EXECUTION_SCHEDULING.md).


## SaaS

O SaaS reutiliza o mesmo serviço canônico e a mesma regra de seleção.

Endpoint de criação:

```text
POST /api/v1/projects/{project_id}/consolidated-reports
```

O request informa:

- `property_id`;
- `environment_id`;
- `baseline_audit_id`;
- `current_audit_id`;
- `selection_mode=ALL|SUCCESS_ONLY|MANUAL`;
- `audit_ids` quando a seleção manual incluir intermediárias;
- `use_ai`;
- provider/modelo/reasoning/timeout somente quando aplicável;
- chave de idempotência opcional.

A API e o worker revalidam tenancy, escopo, mesma URL, mesmo dispositivo e composição autorizada. O browser não é fonte de confiança para os Audit IDs.

O job permanece `REPORT_REFRESH` com `surface=consolidated`; não há novo tipo de job nem alteração de schema. O worker não cria algoritmo paralelo, não recalcula scoring e não reexecuta coletores.

A materialização SaaS chama o mesmo `rasai.consolidation.service.generate` usado pelo domínio canônico. Por isso revisão temporal/source revision, freshness de `report-catalog`, supressão de links stale, comparabilidade `UNRELATED`, validação da saída da IA e semântica de forecast são aplicadas igualmente ao console e ao worker SaaS. A API não reinterpreta esses estados e não mantém uma segunda regra de governança.

O SaaS também expõe:

- candidatos elegíveis para a seleção;
- histórico de consolidados materializados;
- abertura segura de `report.html`.

Jobs representam execução operacional; histórico de CONS representa relatórios de produto.

## Dedupe

O fingerprint final inclui a identidade das fontes, filtros canônicos, política de seleção e modo de geração. A mesma composição com e sem IA produz fingerprints diferentes.

Um resultado só pode ser reutilizado quando o manifesto comprova:

- `report_format_version=CONS-5`;
- contrato de materialização vigente;
- mesmo fingerprint;
- contratos temporal, longitudinal, decisão e governança vigentes;
- hashes SHA-256 dos artifacts obrigatórios íntegros;
- compatibilidade entre `generation_mode` e estado da IA.

Modos aceitos:

```text
DETERMINISTIC      -> ai_status=NOT_REQUESTED
DETERMINISTIC_AI   -> ai_status=COMPLETE
```

No modo determinístico, artifacts exclusivos de IA não são obrigatórios. No modo com IA concluída, `specialist-analysis.json` e `ai-exchanges.json` integram o pacote reutilizável.

## Reversibilidade

O consolidado é derivado.

Remover:

```text
.rasai/consolidated-index.db
consolidated/CONS-*
consolidated/executions/CONRUN-*
```

não altera nenhum `AUD-*`.

## Gate de integração

A validação permanece direcionada ao código alterado:

- compilação dos módulos do consolidado/console/SaaS modificados;
- seleção `ALL/SUCCESS_ONLY/MANUAL`;
- BASE/ATUAL pela ordem temporal;
- rejeição de N=1, URL divergente e dispositivo divergente;
- geração determinística sem IA;
- geração com IA quando solicitada;
- `NOT_REQUESTED` neutro;
- fingerprint e dedupe por modo;
- payload SaaS e segregação de tenant;
- histórico/listagem;
- ausência de escrita em `AUD-*/audit.db`;
- preview/custo somente no modo com IA.

Não executar suíte completa ou cenários de coleta/scoring não modificados.

## Conclusividade das auditorias fonte

O CONS distingue `status=COMPLETED` de encerramento analítico comprovado. Para cada AUD selecionada, a camada read-only verifica, quando persistidos:

- `completion_status`;
- `audit_fulfillment_contracts.processing_status`;
- `report_status`;
- `consolidation_eligible`;
- itens obrigatórios pendentes, bloqueados, expirados ou retryable;
- necessidade de reprocessamento.

Uma AUD com processamento encerrado, mas fulfillment incompleto, pode permanecer no estudo histórico para transparência. Nesse caso, o consolidado é marcado como **não conclusivo** e a IA deve tratar tendências como leitura descritiva/contextual até reprocessamento.

## Confiança da estimativa de custo da IA

No forecast pré-execução do especialista longitudinal, disponibilidade de tarifa não é tratada como prova de alta precisão financeira. O custo continua sendo calculado pelo mesmo catálogo e pela mesma aritmética, mas a confiança qualifica também a incerteza de volume:

- pricing integral em moeda única: no máximo `MÉDIA` antes da execução;
- pricing parcial: `BAIXA`;
- sem pricing utilizável: `NENHUMA`.

`pricing_coverage` registra a fração de candidatos precificados e `confidence_basis` explica que tokens de entrada/saída continuam estimados antes da resposta real do provider. Isso não modifica preços nem custo observado.

Quando existe forecast persistido, o HTML humano também expõe **Confiança da previsão**, **Cobertura de preços** e **Base da confiança**, ao lado de custo esperado/observado e desvio. Esses campos não ficam restritos ao manifest.

## Comparabilidade de configuração e linguagem da IA

A classificação de configuração é incorporada ao `LongitudinalBundle` **antes** da prévia e de qualquer chamada externa. Assim, console e SaaS enviam à IA o mesmo estado determinístico usado pelo relatório.

Quando `configuration_comparability.pair_status=UNRELATED`, a interpretação deve usar **comparação contextual**. O contrato rejeita respostas que promovam esse par a “intervalo comparável”, “série comparável”, “marcos comparáveis” ou formulação equivalente de repetição controlada. A rejeição é tratada como erro de contrato da tentativa; o RASAi não reescreve silenciosamente a conclusão da IA.

Na projeção compactada enviada ao provider, a comparabilidade básica de Monitoring é denominada `scope_comparable`, enquanto a relação de configuração é enviada separadamente como `configuration_pair_status`. Assim, `scope_comparable=true` significa apenas que URL/dispositivo/escopo permitem construir o intervalo e nunca implica equivalência de configuração. O artifact longitudinal integral mantém sua evidência canônica local.

## Camada decisória e SARI

O `report.html` apresenta os dados consolidados e o contexto decisório derivado das fontes persistidas.

Sempre disponíveis:

1. estado de conclusividade da série;
2. trajetória do `SARI-001` usando somente `OVERALL_READINESS` persistido por `SCORE-GEO-004`;
3. marco inicial, marco final, Coverage e Confidence persistidos;
4. evolução, performance, experiência, correções técnicas e governança;
5. evidências e limitações da série.

Quando IA é usada, a camada decisória também pode incluir resumo interpretativo, prioridades P0-P3, correlações, diagnóstico contextual e ações sugeridas, sempre identificados como conteúdo assistido por IA e rastreáveis às evidências.

O CONS não recalcula SARI.

## Matriz de encerramento estrutural do CONS

A matriz não cria percentual sintético. Ela expõe estados independentes para:

- saúde das AUDs fonte;
- identidade URL/dispositivo;
- metodologia SARI;
- equivalência de configuração;
- cobertura dos catálogos;
- evidência longitudinal;
- integridade criptográfica das fontes;
- camada de IA;
- segurança da consolidação;
- pacote auditável.

Para IA:

```text
CONCLUÍDO      - IA solicitada e concluída
NÃO SOLICITADA - modo determinístico; estado neutro
INDISPONÍVEL   - IA solicitada e não concluída
```

`NÃO SOLICITADA` não reduz a confiabilidade do conjunto nem impede o encerramento do modo determinístico. O estado global pode ser `ENCERRADO`, `ENCERRADO COM RESSALVAS` ou `NÃO ENCERRADO` conforme os eixos efetivamente requeridos.

## Organização visual

`report.html` e `rules-reference.html` pertencem ao mesmo pacote e compartilham identidade de produto: tipografia, paleta discreta, cards, navegação e busca.

A camada corporativa de apresentação, governança de fontes, revisão temporal e referências BR-GEO é **independente do uso de IA**. O modo Determinístico recebe a mesma estrutura visual e `rules-reference.html` sempre que houver regras citadas; somente blocos interpretativos e navegação para **Análise por IA** dependem de IA efetivamente materializada. Links para seções inexistentes não são emitidos.

O fluxo principal prioriza decisão. Logs, hashes, custos, tentativas, solicitações/respostas de IA e artifacts ficam em **Governança, integridade e auditabilidade**, recolhidos por padrão.

A superfície humana usa pt-BR sempre que há tradução inequívoca. IDs, contratos e termos técnicos canônicos podem permanecer em inglês como informação secundária.

O layout principal é fluido: `main` não impõe largura máxima fixa em `report.html` nem em `rules-reference.html`, e o cabeçalho da página de regras também não limita `.rules-header-shell` por `max-width`. O espaçamento lateral continua responsivo. Blocos `details > summary` usam acabamento visual uniforme, com contorno, fundo, indicador de expansão, hierarquia tipográfica própria e texto alinhado à esquerda.

Na leitura humana, nomes de domínio, enums, variáveis de configuração e códigos operacionais não podem aparecer como rótulo principal quando houver forma inequívoca em pt-BR. Exemplos incluem `MOBILE` -> **Dispositivo móvel**, `WARNING` -> **Atenção**, `PERFORMANCE` -> **Desempenho**, `NAVIGATION_LOAD` -> **Carregamento da navegação**, `USER_ACTION_DURATION` -> **Duração da ação do usuário** e `MANUAL_CALIBRATION` -> **Calibração manual**.

No Apdex temporal, a superfície humana usa **Satisfeitas / Toleráveis / Frustradas**, descreve limiares, perfil, pacing e calibração em linguagem legível e não imprime IDs internos de perfil ou pares `chave=valor` como texto primário. Tokens canônicos permanecem disponíveis somente quando necessários para auditabilidade técnica.

Blocos de evidência técnica, especialmente `pre`/`code`, IDs `AUD-*`, `BR-GEO-*`, contratos, nomes padronizados de métricas/protocolos e payloads sanitizados não são traduzidos de forma que altere a evidência original.

IDs `AUD-*` exibidos como referência navegável na superfície humana apontam para `../../<AUD-ID>/report-catalog/index.html` e abrem em nova aba. O link é apenas uma conveniência de navegação para a auditoria fonte; IDs persistidos, payloads técnicos e evidências não são reescritos.


## Rótulos públicos e contadores do cabeçalho

Na superfície humana do CONS, rótulos técnicos ou de domínio devem ter forma legível em pt-BR sempre que houver tradução inequívoca. Nas tabelas e chips de resultado, o rótulo humano prevalece sem repetir o enum ou nome de domínio em inglês:

- `Answerability` -> **Capacidade de resposta**;
- `Citation Readiness` -> **Preparação para citação**;
- `Structured Data` -> **Dados estruturados**;
- `Evidence & Trust` -> **Evidências e confiabilidade**;
- `Mobile` -> **Dispositivo móvel**;
- `PASS` -> **Aprovado**;
- `WARNING` -> **Atenção**;
- `FAIL` -> **Não aprovado**.

IDs canônicos, contratos, métricas padronizadas e payloads técnicos permanecem inalterados nos artifacts e blocos de inspeção.

Os contadores do cabeçalho usam exclusivamente `initial_to_final.changes`, isto é, o recorte **marco inicial -> marco final**:

- `IMPROVED` + `RESOLVED` -> melhorias ou resoluções;
- `REGRESSED` + `NEW` -> regressões ou novos sinais;
- demais estados materiais, como `CHANGED` e `DATA_UNAVAILABLE`, -> alterações ou indisponibilidades a investigar.

Eles não contam todos os eventos intermediários e não devem ser interpretados como soma de todos os intervalos.

## Navegação para Regras de Avaliação de Prontidão

O arquivo principal do pacote CONS é `report.html`; não existe `index.html` dentro do snapshot consolidado.

Quando houver regras citadas, `report.html` deve expor **Regras de Avaliação de Prontidão** diretamente no menu principal, além dos links contextuais em cada ID `BR-GEO-*`. O destino é `rules-reference.html`, que pertence ao mesmo pacote e possui busca e navegação de retorno.


## Conclusividade das auditorias fonte

A consolidação distingue conclusão final de ausência absoluta de limitações:

- `CONCLUSIVE`: todas as AUDs estão finais, elegíveis e sem ressalva estrutural de conclusão;
- `CONCLUSIVE_WITH_LIMITATIONS`: todas as AUDs estão finais e elegíveis, sem requisito obrigatório pendente, mas uma ou mais registram limitações não bloqueantes;
- `NON_CONCLUSIVE`: existe AUD não final, não elegível ou com requisito obrigatório pendente.

`COMPLETE_WITH_LIMITATIONS` não implica reprocessamento quando fulfillment, score e relatório estão finais, a auditoria é elegível para consolidação e não existe item obrigatório pendente. Nesse cenário, as limitações permanecem explícitas no estudo, mas a série continua conclusiva com ressalvas.

## Confiabilidade da interpretação por IA

O CONS apresenta um grau de confiabilidade da interpretação assistida por IA. Esse indicador não altera scores persistidos e não representa probabilidade de sucesso de uma remediação.

A classificação considera, em conjunto:

- confiança numérica declarada pela IA para os tópicos analisados;
- cobertura de evidências citadas;
- conclusividade das AUDs fonte;
- comparabilidade das configurações entre os marcos analisados.

Os níveis humanos seguem a convenção usada nos relatórios de auditoria:

- **Muito alta**: confiança declarada >= 95%, sem rebaixamento estrutural;
- **Alta**: confiança declarada >= 75%, ou nível superior limitado por alguma ressalva estrutural;
- **Limitada**: confiança abaixo de 75% ou série não conclusiva;
- **Não determinada**: não há confiança numérica suficiente para classificar.

Mesmo com confiança alta, correlação temporal não deve ser apresentada como causalidade comprovada.

## Rótulos equivalentes aos relatórios de auditoria

Sempre que um score, dimensão, métrica, estado ou tipo de Apdex já possui rótulo público nos relatórios de auditoria, o CONS reutiliza a mesma denominação humana.

Exemplos:

- `MOBILE` -> **Dispositivo móvel**;
- `DISCOVERY_ACCESS` -> **Acesso e descoberta**;
- `INDEXABILITY` -> **Indexabilidade e canonicalização**;
- `EVIDENCE_TRUST` -> **Evidências e confiabilidade**;
- `CONTENT_VALUE` -> **Valor do conteúdo**;
- Apdex sintético de navegação -> **Apdex de navegação**;
- Apdex sintético de experiência -> **Apdex de experiência**;
- `performance_score` -> **Lighthouse Performance**;
- `accessibility_score` -> **Lighthouse Accessibility**;
- `best_practices_score` -> **Lighthouse Best Practices**;
- `fcp_lab_ms` -> **FCP de laboratório**;
- `tbt_lab_ms` -> **Total Blocking Time**.

A Matriz histórica das dimensões utiliza somente o rótulo pt-BR na coluna Dimensão. IDs canônicos permanecem disponíveis nos artifacts técnicos e áreas de inspeção.

A tabela **Índice de Prontidão Search & IA e dimensões de Busca e IA** segue a mesma regra. A confiança do Índice de Prontidão Search & IA é apresentada com rótulos humanos `Muito alta`, `Alta`, `Média`, `Baixa`, `Muito baixa`, `Indisponível`, `Não aplicável` ou `Não determinada`. Valores desconhecidos não são promovidos à interface como enums.

Em **Ocorrências persistidas**, categorias conhecidas são convertidas para pt-BR antes de compor os chips. A chave canônica continua preservada somente nos artifacts estruturados.

## Eficiência da preparação longitudinal

A geração interativa de um `CONS-5` novo prepara o universo longitudinal uma única vez por execução. O objeto transitório `LongitudinalPreparation` existe somente em memória e é vinculado ao diretório de auditorias, aos filtros canônicos e ao fingerprint das fontes.

A mesma preparação é reutilizada para:

- prévia de contexto, tokens e custo da IA;
- registro da prévia no `CONRUN-*`;
- chamada efetiva da IA;
- materialização da evidência integral em `longitudinal-evidence.json`.

A preparação não é persistida como cache e não sobrevive a outra execução do console. Se filtros ou fontes divergirem, a preparação é recusada antes da chamada externa.

Antes da preparação pesada, o serviço calcula o mesmo fingerprint canônico do `CONS-5` e executa a validação integral de reuso já vigente. Um pacote existente só é reutilizado se continuar atendendo contratos, IA completa e hashes obrigatórios.

Durante `build_longitudinal()` cada `AuditSnapshot` de Monitoring é carregado uma vez e reutilizado nas comparações consecutivas, na comparação inicial -> final e como metadado do snapshot de catálogo. `Fix Verification` recebe o `ComparisonResult` já produzido e não refaz a mesma comparação.

A leitura longitudinal dos registros-fonte dos catálogos mantém uma única conexão SQLite read-only por AUD durante esse snapshot. Nenhum dado, catálogo, intervalo ou evidência é removido para obter ganho de desempenho.

## Integridade e reuso do pacote CONS

Um pacote CONS só pode ser reutilizado quando os hashes SHA-256 dos artifacts materializados conferem com `package_integrity` do manifesto. Um pacote reutilizado é tratado como snapshot imutável: a camada de apresentação não deve reescrever `report.html` ou outros artifacts após a validação de integridade.

Se qualquer hash divergir ou o contrato de governança, decisão ou materialização estiver desatualizado, o snapshot não é reutilizado. Mudança de CSS, rótulo público, regra de exposição, cálculo derivado ou composição do `report.html` que altere a superfície vigente deve incrementar o contrato de materialização, evitando que um CONS íntegro porém produzido por uma revisão anterior seja reutilizado como se já contivesse a correção atual.


### Identidade semântica das evidências entre AUDs

A comparação longitudinal de registros persiste o conteúdo completo para rastreabilidade, mas exclui do fingerprint semântico identificadores efêmeros de cada AUD (`diagnostic_id`, `suggestion_id`, `recommendation_id`, `remediation_group_id`, `finding_id`, `summary_id`, `sample_id`, `assessment_id`, `entity_observation_id`, `interpretation_id`, `acquisition_id`, `group_id`, `governance_id`, `remediation_id`, `resource_id`, `source_audit_id`, `source_observation_id`, `source_id`, `evidence_ids`, `evidence_ids_json`, `source_evidence_json`, `affected_findings` e `affected_pages`). Mudança apenas nesses identificadores não caracteriza evolução do alvo. Alterações nos valores observados, estados, métricas, recomendações ou demais campos semânticos continuam produzindo mudança longitudinal.


### Paridade entre contagem de fonte e registros longitudinais

Os registros comparados pelo CONS devem usar o mesmo recorte semântico usado pela contagem pública da fonte no catálogo. No CAT-02, `web_performance_attempts` considera somente `PAGESPEED_INSIGHTS`, enquanto CrUX permanece fora dessa fonte específica; `web_performance_observations` só entra quando possui `accessibility_score`. A camada longitudinal não pode comparar linhas adicionais que o próprio catálogo não contabiliza naquela fonte.


Campos de instante operacional que apenas registram quando a mesma evidência foi recolhida ou materializada (`collected_at`, `materialized_at`, `consumed_at` e `lighthouse_fetch_time`) também ficam fora do fingerprint semântico. Valores funcionais, métricas, estados e hashes de conteúdo permanecem comparáveis.

## Consolidação com fontes parciais e IA indisponível

O CONS continua read-only em relação às AUDs fonte e não recolhe novamente APIs ou o alvo auditado.

`consolidation_eligible=true` continua significando fechamento integral da AUD. Separadamente, uma AUD fisicamente concluída e íntegra pode participar como fonte **não conclusiva** quando suas pendências são reprocessáveis e estão explicitamente classificadas.

A decisão de utilizar uma fonte parcial é feita em SQLite `mode=ro`, com `PRAGMA query_only=ON` e `PRAGMA quick_check`; o CONS não cria schema na AUD fonte.

O relatório consolidado determinístico também pode ser materializado quando a camada longitudinal de IA está ausente. Os estados permanecem distintos:

- `NOT_REQUESTED`: IA não solicitada;
- `NOT_CONFIGURED`: IA solicitada sem provider configurado/apto; nenhuma chamada é feita;
- `UNAVAILABLE`: provider configurado, mas a execução não concluiu;
- `COMPLETE`: camada de IA concluída.

Fontes AUD parciais e pendências da IA longitudinal aparecem no informativo de fechamento diagnóstico. Para pendência originada em uma AUD, a ação é reprocessar a AUD de origem, não recolher seus dados dentro do CONS.

Consulte [PARTIAL_DIAGNOSTIC_EXECUTION.md](PARTIAL_DIAGNOSTIC_EXECUTION.md).
