# RASAi - contrato de persistência de configurações do console (#523)

## Escopo e fontes verificáveis

O inventário operacional de variáveis é derivado em tempo de execução de
`console_provider_environment.refresh_specs()`. Para cada variável, o nome,
a categoria, o default, a sensibilidade e a condição de uso vêm do registro
composto. Não há lista manual paralela autorizada a sobrepor esse registro.

Os valores não sensíveis persistidos provêm de
`console_settings._state_values(state)` (seções do estado) e de
`console_complete_persistence.persisted_environment_values(state)`
(registro de ambiente). A gravação usa `save_console_config`, a leitura
`load_console_config` e a aplicação ao executor
`sync_nonsecret_runtime_environment`.

| Escopo | Fonte | Destino | Sobrevive à nova sessão? | Autoriza nova execução? |
| --- | --- | --- | --- | --- |
| Geral, IA, modelos, Web Performance, CAT-06, CAT-07 e Dynatrace não secreto | Estado tipado do console | Seções específicas do INI e projeção do ambiente | Sim, se válido | Não; depende do plano/consentimento vigente |
| Variáveis públicas não secretas adicionais (SERP, GSC, providers, limites, catálogos, flags, relatórios) | Registro canônico de ambiente | `[environment]` no INI | Sim, respeitando precedência | Não |
| Termos/filtros de execução SERP | `SearchConsoleState`, extensão de persistência SERP | `[search_intelligence]` | Sim, conforme política SERP existente | Sujeito aos gates da AUD atual |
| Queries e WEB/FAST Perplexity | Pedido transitório + rascunho reutilizável de `SearchConsoleState` | `[perplexity_draft]` (somente dados, sem opt-in) | **Sim, somente rascunho** | **Nunca por restauração**; exige CAT-05 > P > 9 e confirmação financeira |
| Chaves, tokens, senhas, DSNs com credenciais | Secret store / ambiente protegido | **Não gravados no INI** | Conforme mecanismo seguro, independente do INI | Não |
| Seleção explícita de chamadas potencialmente faturáveis | Interação/autorização da AUD corrente | Controle de execução e evidências da AUD | Não transferível entre AUDs | Somente para a AUD autorizada |

## CAT-06 / CAT-07 - round-trip e execução efetiva

O teste isolado `tests/test_console_persistence_matrix.py` exercita
valores **não default** para os parâmetros de Navigation Apdex e Experience
Apdex, inclusive arquitetura `CSR_SPA`, perfil `DYNATRACE_GUIDED`, KPM,
Satisfied/Frustrated, erros JavaScript/XHR/Fetch/console, limiares,
concurrency, delay, settle, session mode e campos de configuração Dynatrace.

O procedimento automatizado é:

1. Criar estado tipado com valores não default e gravar INI em diretório temporário.
2. Limpar o ambiente do processo para simular abertura independente.
3. Carregar o INI em um estado novo, sem reutilizar o objeto anterior.
4. Comparar a serialização das seções com os valores originais.
5. Comparar a projeção efetiva de variáveis de Apdex e Dynatrace que
   o console disponibiliza ao executor.
6. Verificar exclusão de secrets e intenções Perplexity.
7. Verificar que o registro público não sensível é materializado por inteiro.

Nenhum teste executa coleta, navegador, integração Dynatrace live ou pesquisa
paga. Uma configuração representada no INI não equivale a medição real nem
comprova que o serviço externo está habilitado ou acessível.

## Precedência e limitações

- Os campos de estado tipado são reconstruídos pelas seções específicas do INI.
- `[environment]` preenche apenas variáveis ainda ausentes no ambiente.
  Overrides já existentes no processo têm prioridade nesse escopo.
- `sync_nonsecret_runtime_environment` aplica explicitamente a projeção
  do estado tipado para seus campos gerenciados; portanto não se deve tratar
  `[environment]` e o estado como duas fontes totalmente independentes
  da configuração efetiva.
- O caminho do arquivo é resolvido por `console_config_path` e
  `console_settings.resolve_config_path`; preservar o mesmo caminho nos
  testes de save/reopen e na análise de incidentes.
- A Perplexity não é provider do seletor generativo `AI=auto`.
  Ativação, credencial e filtros não representam solicitação de pesquisa;
  queries e WEB/FAST são transportados **somente como rascunho inerte** à nova sessão; solicitação e confirmação comercial não são restauradas.

## Limites de homologação

A matriz automatizada comprova serialização e leitura de configuração sem
serviços externos. **Não comprova por si só:** carga produtiva Dynatrace,
consentimento humano em ambiente Windows, equivalência de uma AUD histórica
ou consistência de medição sintética em uma página real. Esses são gates
distintos; não devem ser marcados como aprovados apenas por CI.

## Inventário completo do registro de variáveis (#523)

O comando local `python -m rasai.console_configuration_inventory`
gera JSON **somente de metadados**, utilizando o `EnvironmentSpec` real,
a lista de campos tipados do console e os inputs de execução conhecidos.
`--ini caminho/rasai-console.ini` permite observar um arquivo específico
sem editá-lo. Para reproduzir a seleção do boot sem fornecer caminho, o
comando consulta `RASAI_CONSOLE_INI` ou o caminho relativo ao diretório atual.

A matriz enumera **cada variável atualmente registrada** e destaca
categoria, sensibilidade, escopo, elegibilidade para INI, existência de valor
somente como marcador e diferença `SESSION_DIFFERS_FROM_INI_EFFECTIVE_PRIORITY_UNVERIFIED`, quando aplicável; a origem efetiva depende do consumidor.
Nunca contém valores, tokens, paths do operador, URLs concretas, queries ou
consentimento. Há seções adicionais para todos os campos tipados em
`console_settings._state_values` e para queries SERP/Perplexity.

**Limite declarado:** presença no registry não prova que a variável foi
consumida por um motor, que entrou no snapshot selado da AUD nem que foi
efetivamente respeitada pelo provider. Esses campos aparecem como
`NOT_PROVEN_BY_REGISTRY` ou `AUD_DEPENDENT_NOT_INFERRED`, em vez de
serem certificados por inferência. A comprovação por execução real permanece
um gate separado.

Testes isolados Linux/Windows verificam cardinalidade e unicidade do registro,
marcadores de segredo/INI, proteção de conteúdo sensível, shadowing, invocação
CLI somente-leitura e exclusão de autorização Perplexity.

## Inventário físico fornecido pelo operador (13/10/2026)

A execução local do inventário registrou 189 variáveis (165 públicas e
24 sensíveis), sendo 138 públicas presentes no INI e 27 sem valor efetivo.
Entre 71 campos tipados, somente
`synthetic_apdex_experience.device_mix` está ausente do INI.

Essa ausência é **derivada**, não perda comprovada: `device_mix` é calculado
via `canonical_single_device_mix(state.device)` tanto na projeção quanto
na restauração canônica. Não se deve restaurar um mix independente de um
INI antigo como autorização de dispositivo múltiplo.

O diagnóstico `typed_ini_coverage` separa campos derivados ausentes de
lacunas de campos não derivados. Ambas são apenas metadados; o inventário
não certifica uso pelo motor, integridade da AUD ou autorização comercial.
Fixture física reproduz a presença de 70 de 71 campos em teste offline.

## Prova de consumo físico do contrato M23/M25 (offline)

Teste direcionado `test_saved_apdex_inputs_are_consumed_by_real_m23_m25_config_adapters_without_aud`
verifica o trajeto `save INI -> load state -> sync runtime environment ->
argparse real -> configured_apdex -> M25 pending_config` em um ambiente
isolado. A asserção final examina **as estruturas efetivamente
consumidas** pelos adapters de M23/M25, não apenas igualdade de strings.
Abrange T, amostras, tentativas, timeout, delay, concorrência, device
canônico, KPM, thresholds, escopo e captura de erros JS/XHR/Fetch.

Arquitetura declarada `CSR_SPA` e modo `CUSTOM` também permanecem
disponíveis como inputs de calibração/advisory, mas **não são campos
nativos de `ExperienceApdexConfig`** e não devem ser descritos como
medidos pelo motor. O teste não invoca browser, Dynatrace, Search API,
IA nem gera AUD, e restaura o pending M25 depois de verificar o contrato.

## Diferença de valores não prova precedência (13/10/2026)

Um valor não secreto presente simultaneamente no processo e no INI com
textos distintos não garante que o processo seja o vencedor efetivo.
O consumidor pode re-projetar um campo tipado do INI ao preparar a execução.

Fixture: `RASAI_APDEX_EXPERIENCE_ARCHITECTURE` com processo `HYDRATED`,
seção `environment` do INI `STATIC_OR_SSR` e seção tipada da mesma
fonte `CSR_SPA`. O carregamento mantém inicialmente o processo, mas
`sync_nonsecret_runtime_environment` re-projeta o estado tipado e o
valor efetivo passa a `CSR_SPA`. Por isso, o resumo do console conta
**divergências de valores**, e não `overrides` cujo efeito não comprovou.

A mudança é apenas na linguagem/diagnóstico offline; não muda a
prioridade real nem o comportamento dos adapters e motores.

## Preflight de consumo Apdex sem auditoria (opt-in, 13/10/2026)

O comando `python -m rasai.console_configuration_inventory --verify-apdex`
habilita validação extra, **sem coletar dados**. O caminho de configuração
pode ser fornecido pelo argumento `--ini`; caso contrário, segue
`RASAI_CONSOLE_INI` ou o caminho canônico habitual.

A implementação:
1. verifica que a origem existe, não é symlink e mede no máximo 2 MB;
2. lê bytes e usa uma **cópia temporária própria**, para que a rotina de
   load nunca crie nem substitua um INI do operador durante uma corrida;
3. restaura estado tipado, projeta o ambiente e chama apenas
   `configured_apdex` + o handoff de `ExperienceApdexConfig`;
4. verifica o SHA-256 físico da fonte, retoma o ambiente original e **nunca grava nem limpa** o handoff
   M25 global; a configuração que o adapter tentaria entregar é capturada
   em um callback local somente durante a inspeção;
5. publica somente `status`, ativação M23/M25, device único coerente,
   quantidade de avisos e flags de limites metodológicos.

O valor `ADAPTERS_VALIDATED_OFFLINE` **não** equivale a execução de
coleta, tempo de página, validação Dynatrace live ou consumos cobrados.
`ADAPTERS_PARTIAL_LOAD_WARNINGS` significa que o adapter aceitou uma
configuração parcial/default; não garante restauração exata.
Arquivos ausentes ou inválidos devolvem N/D ou erro tipado, sem revelar
conteúdo de campos. O comando convencional **sem** `--verify-apdex`
mantém o comportamento anterior: inventário puramente de metadados.

## Proteção do handoff M25 em processo (13/10/2026)

Uma validação offline não pode sobrescrever nem limpar uma configuração
M25 de uma auditoria pendente. O preflight anterior invocava
`m23_cli.configured_apdex`, que tem o efeito colateral legítimo de
gravar a configuração M25 em `m25_runtime.set_pending_config`,
e por fim limpava o handoff global. Isso era incompatível com a
promessa de inspeção read-only quando a função era importada em
um processo que já mantinha M25 preparado.

O leitor agora intercepta **apenas no escopo da chamada** o ponto
de handoff do adapter, valida e captura as mesmas configurações em
memória local. Não grava nem reseta o estado global. Testes direcionados
preservam a **identidade** de uma configuração M25 preexistente nos
casos de sucesso, arquivo ausente e INI inválido; também falham caso
o setter global seja chamado. Não altera código de M23/M25 nem o
comportamento da auditoria normal.

A CLI de inventário é projetada para uso em processo separado do
console; não utilizar o diagnóstico para justificar concorrência
entre configuração e auditoria ativa no mesmo processo.

## Classificação das superfícies consumidoras M23/M25 (#523)

O inventário geral das `EnvironmentSpec` agora inclui a propriedade
`declared_adapter_surface`, calculada dinamicamente a partir das
constantes existentes dos módulos `m23_cli`, `m25_cli` e dos
perfis compartilhados de Apdex. Os grupos de classificação são:

- `M23_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF`: parâmetro conhecido
  da configuração de navegação.
- `M25_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF`: parâmetro conhecido
  da configuração de experiência.
- `SHARED_APDEX_PROFILE_INPUT_NOT_EXECUTION_PROOF`: preset de
  dispositivo potencialmente utilizado por ambos.
- `CAT07_DECLARATIVE_INPUT_NOT_M25_MEASUREMENT`: arquitetura informada
  e modo de calibração são declarações, não índices medidos pelo M25.
- `INERT_DEVICE_MIX_DERIVED_FROM_CONSOLE_DEVICE`: a mistura
  histórica não reativa dispositivo múltiplo.
- `NOT_MAPPED_NO_CONSUMER_INFERENCE`: nenhum consumidor foi identificado
  por este inventário de Apdex; **não** significa variável órfã.

O resumo `apdex_adapter_surface_coverage` informa quantas variáveis
do registro caem em cada universo, sem exibir valores nem credenciais.
`runtime_consumer=NOT_PROVEN_BY_REGISTRY` e a flag
`execution_or_aud_snapshot_coverage_proven=false` permanecem
intencionalmente: uma constante de interface **não prova** que o
parâmetro foi usado na AUD, nem que uma opção desabilitada participou
de uma coleta.

O comando opcional `--verify-apdex` valida os adapters com valores
efetivos em memória isolada, não altera essas flags como se fosse
telemetria executiva por variável. Credenciais externas e outras
categorias permanecem não mapeadas nesta etapa.

A mistura histórica inerte aparece nos contratos do adapter CLI, mas não
faz parte do conjunto atual de variáveis editáveis do registro do console.
Isso não configura falta de persistência e não deve ser introduzido no
INI apenas para satisfazer uma contagem estática do inventário.

## Estado fisico do arquivo e consentimento Perplexity (#523)

A inspeção offline `python -m rasai.console_configuration_inventory`
agora comunica `ini_source_status` sem imprimir o caminho nem os valores:
`SOURCE_PARSED_NO_RUNTIME_CONSUMER_PROOF`,
`SOURCE_NOT_FOUND_OR_NOT_A_FILE`, `SOURCE_TOO_LARGE`,
`SOURCE_SYMLINK_DISALLOWED`, `SOURCE_INVALID_INI`,
`SOURCE_UNREADABLE` ou `SOURCE_CHANGED_DURING_READ`.
Uma origem legível não prova que o console atual a carregou, que o
operador salvou alterações, nem que a AUD consumiu seus parâmetros.
O inspector verifica identidade/tamanho/mtime do arquivo, seu
descriptor aberto e a leitura limitada a 2 MB, recusando mudança
observável durante a leitura. Isso não é um selo criptográfico.

O quadro Perplexity na preparação da AUD diferencia explicitamente
as **queries e o modo**, que são transitórios da sessão e NÃO são
persistidos no INI, dos filtros globais, chave e habilitação. O aviso
"NÃO SOLICITADA" não demonstra perda de configurações globais.
O novo campo `per_aud_paid_consent_restored=false` esclarece que
a abertura de outra sessão nunca transfere autorização financeira de
nova pesquisa. A redação do console não inicia pesquisas.
Testes reproduzem INI válido, ausente, inválido, grande demais,
symlink e append concorrente, sem mostrar segredos ou alterar a AUD.


## Gate novo: save/reopen entre interpretadores independentes (#523)

O teste `tests/test_console_fresh_process_roundtrip.py` executa dois
processos Python distintos, com ambiente controlado e `RASAI_CONSOLE_INI`
apontando para um arquivo temporário descartável. O primeiro processo
configura CAT-06/CAT-07, arquitetura HYDRATED, perfil CUSTOM, SERP e
habilitação global Perplexity; grava o INI e encerra. O segundo processo
reabre a mesma fonte, compara a representação **de todos os campos tipados**
ao snapshot de salvamento, projeta os overrides não secretos e passa
a configuração real dos adapters M23/M25 ao preflight offline existente.

O teste calcula o conjunto completo de nomes públicos não secretos a partir
de `refresh_specs()` e verifica as chaves persistidas, sem cardinalidade
fixa. Garante que chave Perplexity fictícia e queries de consentimento
não entram no INI; ao iniciar outro processo, o modo transiente volta a
WEB e não existe solicitação paga herdada. O próprio INI não deve sofrer
nenhuma mutação na leitura. CI de configuração Linux e console Windows
incluem esse teste.

**Limites:** essa fixture demonstra o contrato do processo isolado, não
a identidade física do INI real usado no Windows, o consumo por coletores
remunerados, a amostra da AUD nem tenant Dynatrace. As flags do inventário
continuam `NOT_PROVEN_BY_REGISTRY` quando não houver evidência física de
consumo. Não dispensar o smoke humano consolidado de save/reopen no sistema
do operador; não solicitar AUD paga somente para reproduzir esse teste.


## Ponte fisica entre RESTORE e projeção console (#523, 13/10/2026)

A regressao `tests/test_console_fresh_process_roundtrip.py`
agora exercita **tres interpretadores Python independentes**:
(1) salvar configuracao do console em INI temporario,
(2) restaurar em processo novo e validar adapters M23/M25 offline,
(3) restaurar novamente em outro processo e executar apenas o writer
real `console_cost.persist_execution_projection` contra banco SQLite
sintetico temporario. O teste compara as flags CAT-06/CAT-07, numero
de amostras e arquitetura declarada HYDRATED com os mapas
`synthetic_apdex_workload` e `apdex_experience_workload` agora
gravados no JSON do console. O comparador de duracao #319 deve aceitar
os mesmos parametros e rejeitar alteracao do numero de amostras.

A fonte INI deve permanecer byte a byte igual e nenhum segredo de
Perplexity ou dados de credenciais Dynatrace pode entrar no objeto
gravado. O fixture pode criar uma AUD sintetica **somente no diretorio
temporario do teste**; nao executa browser, M23/M25, Search API,
Dynatrace live, orquestracao, scoring nem modificacao de auditorias
existentes. Essa validacao atesta compatibilidade offline de
serializacao, restauracao e writer console, nao realizacao efetiva
de amostras ou prova de consumidores externos live.


## Inventario de afinidade declarada SERP e Perplexity (#523, 13/10/2026)

A matriz offline console_configuration_inventory.py passa a
classificar, alem de M23/M25, as entradas de configuracao
declaradas em search_intelligence.config.SERP_ENV_NAMES e
SERP_PROVIDER_KEY_ENVS, mais a chave, a habilitacao e os filtros
reconhecidos pela camada de readiness Perplexity.

As classificacoes sao apenas **afinidades de codigo**:
SERP_CONFIG_INPUT_DECLARED_NOT_REQUEST_PROOF,
SERP_PROVIDER_SECRET_DECLARED_NOT_REQUEST_PROOF,
PERPLEXITY_KEY_READINESS_NOT_REQUEST_CONSENT,
PERPLEXITY_ACTIVATION_READINESS_NOT_PER_AUD_CONSENT e
PERPLEXITY_FILTER_READINESS_NOT_PROVIDER_USE_PROOF.
Nenhuma transforma uma variavel cadastrada no console em
requisicao SERP/Perplexity fisicamente observada, sucesso de integracao
ou opt-in faturavel transferido de outra AUD. O campo runtime_consumer
permanece NOT_PROVEN_BY_REGISTRY sem execucao rastreada,
e os controles per_aud_provider_consent_proven e
real_provider_request_coverage_proven permanecem falsos.

O campo search_adapter_surface_coverage conta mapeados e nao
mapeados contra o catalogo completo; a cobertura
apdex_adapter_surface_coverage segue **especifica de Apdex**
e nao infla contagem ao mapear variaveis de busca. O inventario
continua somente metadados: nao mostra strings de queries,
valores de filtros, credenciais, URL de tenant ou path do operador.
O teste focal usa um INI temporario com segredo ficticio, compara
bytes antes/depois, bloqueia chamadas HTTP e confirma que a
presenca de chave/ativacao nao herda consentimento Perplexity
nem prova consumo efetivo.

Isto reduz a lacuna de **inventario estatico** da #523; nao
substitui o gate de restore real Windows, nem a validacao de
consumo por coletor, nem uma decisao de produto sobre drafts
Perplexity nao autorizados.


## Escopo declarado GSC, OAuth e política Search Analytics (#523)

O inventário offline passou a mapear também os nomes
de ambiente efetivamente declarados por gsc_scope,
gsc_oauth e standards_gsc_policy, mantendo separado
o catálogo GSC de SERP e Perplexity.
A propriedade, o controle de ativação, a credencial
OAuth e os limites/janela de Search Analytics
possuem classificações distintas.

Estar declarado nesse código, no INI ou na sessão
**não** autentica uma propriedade GSC, token OAuth,
cobertura da URL, dados finalizados ou uma
consulta à API. Por isso, o resumo
gsc_adapter_surface_coverage informa
authenticated_property_coverage_proven=false e
actual_gsc_api_read_coverage_proven=false.
A coluna runtime_consumer continua
NOT_PROVEN_BY_REGISTRY. Se GSC for desabilitado
ou sem escopo de propriedade comprovado, não
se deve interpretar a presença de chave como
solicitação de dados.

Testes em fonte INI temporária verificam metadados
sem conteúdo de token, nenhuma consulta de API,
nenhum refresh de OAuth e bytes originais
inalterados. O patch não modifica a configuração
de GSC nem altera política de consentimento,
janela, provider, runtime ou AUD física.


## Transparencia CAT-05 na tela de escopo da AUD (#523, 13/10/2026)

A tela principal de escopo CAT-05 agora identifica, junto dos
inputs de Perplexity, que **queries e modo WEB/FAST pertencem
somente a sessao atual e NAO sao salvos no INI**. Informa
expressamente que a proxima sessao / proxima AUD exige
nova definicao e confirmacao. Esse contexto independe
de ter chave, habilitacao ou filtros globais presentes;
a tela nao interpreta configuracao tecnica como
consentimento faturavel.

O renderer ja existia, mas nao mostrava ali a politica
de persistencia conhecida pela tela especifica de
readiness e pelo ato de salvar. A alteracao somente
acrescenta informacao de UI, sem ler o arquivo do
operador, modificar politica de salvamento, copia de
SERP, selecionar provider, agendar consulta ou tocar
em motor de coleta.

Regressao isolada cria um INI temporario com SERP
reutilizavel e Perplexity configurada na sessao
original, reabre em novo state e verifica: SERP
permanece; queries e modo Perplexity voltam ao
estado nao solicitado; CAT-05 comunica a exclusao;
token e termos Perplexity nao vazam para INI/UI.
Bytes do arquivo continuam imutaveis no load/render.
O gate humano de caminho real Windows ainda e
necessario para homologacao da #523.


## Inventario INI: regravacao fisica de mesmo tamanho (#523)

O leitor **somente de metadados** ja conferia
`st_dev`, `st_ino`, `st_size` e `st_mtime_ns`
antes da leitura, no descritor realmente aberto
e apos a leitura. Em POSIX passa a conferir tambem
`st_ctime_ns`, para rejeitar regravacoes in-place
de **mesmo comprimento**, mesmo se o mtime
foi restaurado pelo processo concorrente.

Em Windows `st_ctime_ns` e creation time e nao
tem semantica/consistencia garantida entre
`Path.stat` e `os.fstat`; ele nao participa
da comparacao, preservando as protecoes portaveis
anteriores e evitando falso positivo.
O retorno continua `SOURCE_CHANGED_DURING_READ`
e `file_readable=false` quando o gate falha;
nenhum dado de configuracao pode ser apresentado
como inventariado a partir de uma fonte fisicamente
contraditoria.

A regressao POSIX em `tmp_path` altera somente
um parametro de SERP, mantendo bytes totais e
mtime, sem expor o secret ficticio da fixture.
A validacao nao le nem salva INI do operador,
nao inicia AUD, M23/M25, GSC ou chamadas externas;
como antes, estatisticas locais nao demonstram
consumo real da configuracao pelo runtime.


## Inventario declarado do bootstrap principal (#523)

A matriz offline agora identifica inputs diretamente
reconhecidos por `console_config.apply_environment_defaults`:
contexto de dispositivo, timeout, ciclos e delay de IA,
flags de remediacao, habilitacao e limites Web Performance,
fonte de campo, categorias Lighthouse e nomes declarados
para o contexto de conteudo. Cada entrada permanece
um **candidato de configuracao inicial**, nao comprovacao
de execucao do M21, de uma AI, de consumo de credito
ou de persistencia de snapshot da AUD.

A classificacao tem grupos distintos:
`CONSOLE_DEVICE_INPUT_NOT_EXECUTION_PROOF`,
`CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF`,
`CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF` e
`CONSOLE_CONTENT_CONTEXT_INPUT_NOT_AI_EXECUTION_PROOF`.
A coluna `runtime_consumer` continua
`NOT_PROVEN_BY_REGISTRY` e a nova contagem
`console_core_adapter_surface_coverage` expõe explicitamente
`runtime_device_or_provider_execution_proven=false`
e `actual_web_performance_or_ai_usage_proven=false`.

A fixture cobre os nomes publicos efetivamente
declarados no bootstrap e sua leitura pelo parser real
de defaults, sem rodar executor, provedor, crawler
ou Web Performance. A leitura do INI usa apenas
arquivo temporario e confirma que chave ficticia
do provider nao aparece no JSON, nem a fonte
e alterada. A lista de catalogo segue dinamica;
nomes que nao possuem comprovacao de afinidade
continuam classificados como nao mapeados, sem
forcar inferencia de consumer.

## Contrato atual: rascunho Perplexity opcional (#523, 14/10/2026)

Este contrato substitui afirmações históricas acima que diziam que queries e WEB/FAST não são gravados. Quando o operador salva o INI com uma solicitação Perplexity explicitamente configurada, a seção `[perplexity_draft]` persiste `queries` (1..5) e `search_type` (web/fast), assim como o SERP possui uma seção própria. A ausência da seção é compatível com INI anterior. Nenhum token, chave, consentimento, intenção comercial ou status `PENDING` é persistido neste bloco.

No **reboot**, `perplexity_queries=()`, `perplexity_search_type=web` e `perplexity_last_status=NOT_REQUESTED`. Somente `perplexity_draft_queries` e `perplexity_draft_search_type` são restaurados; a tela pode exibir rascunho disponível, mas não configura pesquisa. O operador usa **CAT-05 > P > 9 > R > S** para solicitar os termos previamente salvos na auditoria corrente e passa pelos gates financeiros normais. **Opção D** cancela só a intenção corrente; o rascunho permanece para reutilização. Para remover, **9 > C > S**, seguido de **Salvar configuração**; nenhuma operação dessas chama Search API.

Se o operador alterar uma query e salvar, o rascunho gravado será a query ativa recém-definida. Salvar outra configuração numa sessão reaberta sem autorizar pesquisa Perplexity conserva o rascunho existente. Valores inválidos de modo ou lista geram avisos no load e não habilitam requisições. Dados de queries são conteúdo local potencialmente sensível: não colocar credenciais/PII nesse rascunho e proteger acesso ao INI.

Testes de processo isolado, restauração não faturável, anterior, modos, leitura inválida, apagamento e confirmação explícita são gates técnicos; uma auditoria real não é necessária para homologar o save/reopen. As referências históricas à não persistência das queries neste documento permanecem apenas como registro do comportamento anterior.

## Leitura de readiness a partir de INI e sessão (#523)

A leitura do console é exclusivamente *read-only* e diferencia **viabilidade de configuração** de **solicitação de execução**. Em `console_perplexity_readiness.inspect_perplexity_readiness`, os termos ativos na sessão (`perplexity_queries`, `perplexity_search_type`) prevalecem na apresentação; se não houver solicitação ativa, a tela exibe os termos do `[perplexity_draft]` restaurados por `console_settings.load_console_config`. Credencial configurada, ativação habilitada, 1 a 5 queries válidas e WEB/FAST válido tornam a **configuração APTA PARA SOLICITAÇÃO**. É uma prontidão de parâmetros, não validação da credencial no endpoint nem concessão de consentimento.

A tela principal `INÍCIO > PREPARAR AUDITORIA`, o editor Perplexity do CAT-05 e `6. Todas as configurações` apresentam configuração, origem (sessão/INI), modo e queries disponíveis separadamente do estado `NÃO SOLICITADA` ou `SOLICITADA`. Um rascunho pronto informa a ação `CAT-05 > P > 9 > R > S`, sujeita à confirmação financeira. A simples leitura do INI nunca promove `perplexity_draft_queries` a `perplexity_queries`, nunca provoca Search API nem altera SERP. Configuração `APTA` não é garantia de sucesso de execução remota.

## Contrato de preparação automática com aceite no lançamento (#595, 14/10/2026)

Quando o console carrega `[perplexity_draft]` válido (1 a 5 queries, modo WEB/FAST), possui credencial Perplexity, integração habilitada e CAT-05 selecionado, o plano mostra **PREPARADA - CONFIRMAR PERPLEXITY AO EXECUTAR AUD**, com os termos disponíveis do INI e sem exigir passagem manual por `CAT-05 > P > 9 > R > S`. O carregamento sozinho não ativa `perplexity_queries`, não executa HTTP nem transmite autorização financeira.

Ao pressionar `R. Executar auditoria`, o console abre gate contextual antes do gate financeiro geral:

- `C`: inclui as queries do INI nesta AUD exclusivamente depois desse aceite explícito; a confirmação geral de custo/IA permanece obrigatória.
- `N`: continua a auditoria **sem** Perplexity.
- `V`: volta ao plano **sem** iniciar AUD.
  
Este gate é adicional e distinto de `C=usar IA` ou `N=não usar IA` da IA generativa, pois Perplexity Search API não é equivalente ao provider canônico de LLM e pode possuir preço desconhecido. Nenhuma decisão sobre custos da IA canônica aprova implicitamente Perplexity. Se a AUD for cancelada no gate geral, não há pesquisa Perplexity.

Os campos ativos `perplexity_queries`/`perplexity_search_type` são definidos **temporariamente durante o run autorizado**, restaurados no final, inclusive em erro; o próximo run exige novo aceite. A opção `D` no CAT-05 desabilita a proposta **na AUD corrente** e não apaga o rascunho salvo no INI; `9 > C` seguido de salvar remove o rascunho. Se uma solicitação explícita já foi feita na sessão (`9 > R > S` ou edição de query), não se oferece gate duplicado. Não altera motor Perplexity nem SERP, coleta, scoring, SQLite ou relatórios.

Referências anteriores neste documento ao caminho obrigatório `P > 9` deixam de representar o fluxo preferencial. A opção 9 continua disponível para controle manual, mas o caminho principal passa a ser **carregar INI → preparar AUD → R → confirmar Perplexity → confirmação financeira geral**.


## Proveniência secret-safe: indício de credencial indevida no INI (#523)

A inspeção somente de leitura `console_config_provenance.inspect_configuration` reporta a **quantidade** de entradas potencialmente secretas encontradas no inventário `[environment]` do INI, de acordo com o catálogo sensível e o predicado de segredo. Nunca imprime nome ou valor, não migra o segredo para o ambiente/registro Windows e não o preserva num relatório. A saída apresenta alerta de revisão local, não informação sensível. Caminhos simbólicos são recusados em vez de seguir apontamentos para arquivos privados arbitrários.

O indicador `private_entries_in_ini` tem semântica estrita: contagem de chaves com aparência/contrato de segredo em um arquivo existente, **não** prova que a credencial seja válida nem revela quem a inseriu. O campo não reautoriza Perplexity nem atualiza a execução em andamento. Testes usam fixture com valor sentinela e verificam ausência completa desse valor no texto renderizado.

## Reconciliacao de entradas operacionais historicas (15/10/2026)

O checkpoint Windows do operador, no HEAD anterior ao patch, leu com seguranca
um INI contendo 22 chaves publicas/desconhecidas pelo registry; todas estavam
preenchidas, todas possuíam referencias literais em Python e a leitura manteve
o SHA-256 da origem. Um nome foi intencionalmente mascarado pelo diagnostico.
Isso **nao** comprova por si so que cada runtime executou a funcionalidade.

No contrato atual, `load_console_config` rejeitava esses nomes da secao
`[environment]`; `save_console_config` reconstruia a secao exclusivamente a
partir do registry e poderia perder silenciosamente as entradas. O patch
reconcilia explicitamente entradas conhecidas de catálogos de modelos, precos
e perfis IA, Improvement Intelligence, OAuth GSC Client ID, timezone de
apresentacao e opcoes de seguranca passiva. Essa allowlist **nao** expande
secrets, consents, nem habilita provedores: valores continuam sendo
configuracoes, e nao comprovantes de execucao. A opcao de cookies de
seguranca e um booleano de analise, nao conteudo de cookies. Client ID de GSC
e publico; client secret e refresh token continuam fora do INI.

O loader continua rejeitando nomes fora do registry. Como defesa adicional,
o saver agora recusa sobrescrever um INI fisico que contem entradas de
`[environment]` nao reconhecidas ou nao persistiveis, inclusive secrets,
sem exibir nomes ou valores. A decisao e conservadora: preservar e
reconciliar uma copia segura antes de salvar a origem; nao promover chaves
futuras por prefixo. O novo teste de regressao usa apenas INIs
sinteticos temporarios, realiza `load -> consumer read-only -> save -> reopen`,
verifica o isolamento de sessao/INI, rejeicao de chaves desconhecidas,
validacao dos tipos e reabertura em interpretador separado. O catalogo de
modelos/precos/perfis e os consumidores de Improvement Intelligence,
seguranca passiva e estado OAuth sao verificados sem chamada externa.

O sucesso desses testes e da CI **nao substitui** o smoke Windows sobre uma
copia fisica da configuracao do operador na revisao ja corrigida. Um save
no INI original continua proibido enquanto sua politica de backup,
integridade, precedencia e ausencia de avisos nao tiver sido confirmada.

## Protecao contra substituicao destrutiva do INI (15/10/2026)

A proteção de save agora inclui **todas as seções e opções fisicamente
declaradas**, não apenas `[environment]`. Uma seção desconhecida,
opção tipada não reconhecida ou entrada `[DEFAULT]` não é descartada
silenciosamente: o save é bloqueado com mensagem genérica sem revelar
nome, caminho ou valor. A allowlist é derivada do serializador real
`_parser_for_state(state)` já composto pelos módulos do console, e
nunca da presença arbitrária de `RASAI_*`.

Para reduzir a janela de substituição incorreta, o writer compara antes
do commit o tamanho, identidade física (device/inode), mtime e SHA-256
da origem. Arquivo criado, removido, modificado ou substituído durante
o preparo causa recusa antes de `os.replace`. Para destinos novos o
contrato exige que continuem ausentes ate a etapa de commit.
A gravação é feita em arquivo temporário **único** no mesmo diretório
com nome não previsível e rename atômico; resíduos são removidos no
fim, inclusive após erro.

Essa proteção é uma verificação otimista, **não uma transação com lock**:
modificações durante a curta janela entre a rechecagem final e o
rename não podem ser totalmente excluídas sem um mecanismo de lock
específico por plataforma. O teste de regressão cobre entradas
desconhecidas em seções tipadas e `[DEFAULT]`, mudança da fonte
durante serialização e arquivo temporário de nome previsível já existente, usando
somente fixtures locais sem chamadas externas. O resultado não autoriza
salvar o INI original do operador sem o gate Windows consolidado.

## Compatibilidade de INI UTF-8 com BOM no Windows

A leitura do console e o inventário read-only reconhecem o prefixo UTF-8 BOM sem alterar o arquivo. O guard de `save_console_config` também interpreta o BOM para validar opções conhecidas e preservar as demais restrições: se houver seção, opção, segredo ou dado desconhecido, o save continua recusado. Um **save explícito** reserializa o INI no formato canônico UTF-8 sem BOM, após a validação de origem física. Isso não constitui evidência de round-trip no equipamento do operador; há fixtures temporárias separadas da fonte real.

## Gate de homologação de restauração em Windows

A prova automatizada `tests/test_console_fresh_process_roundtrip.py` executa
processos Python independentes em INI e SQLite **descartáveis** e valida o
consumo M23/M25 por seus adapters. Isso comprova o contrato offline de
serialização/restauração/projeção coberto pelas fixtures, **não** a identidade
do arquivo INI efetivamente usado em cada estação Windows ou o consumo de
todas as integrações externas.

A homologação física residual deve usar Python compatível com
`pyproject.toml` (`>=3.13,<3.14`), ambiente isolado funcional e configuração
não sensível **descartável** por meio de `RASAI_CONSOLE_INI` explícito.
Critério: identificar o arquivo efetivo sem expor dados sensíveis; salvar uma
configuração não default; encerrar o console; iniciar processo novo; comparar
arquivo, UI, estado restaurado e projeção efetiva; demonstrar precedência de
overrides e ausência de autorização Perplexity/serviços remunerados.
Não sobrescrever, corrigir ou migrar o INI real, Registry, secrets ou AUDs do
operador somente para satisfazer esse gate. O valor derivado
`synthetic_apdex_experience.device_mix` continua fora da matriz de campos
independentes a restaurar.

Resultados automatizados verdes não devem ser rotulados como homologação
Windows real; por outro lado, a inexistência desse smoke não invalida os
round-trips entre processos já executados com sucesso. Reportar as duas
provas como estados distintos até o aceite final.

## Gate adicional de restauração completa e atomicidade da sessão

A suíte `tests/test_console_registry_new_process_roundtrip.py` verifica em
**processo Python independente** todos os nomes públicos do catálogo vivo
`refresh_specs()`. Ela compara a cardinalidade do catálogo com todas as
chaves de `[environment]` persistidas, carrega novo estado sem herdar
variáveis RASAI/chaves de provedor da sessão anterior, confirma igualdade dos
valores públicos não vazios, restaura o input tipado CAT-07
`CSR_SPA/DYNATRACE_GUIDED` e mantém queries Perplexity somente como
rascunho **sem autorização de execução**. A fonte INI deve permanecer
inalterada em bytes. As variáveis de bootstrap do Python/Windows são
preservadas para evitar falsear falhas de importação no subprocesso.

A gravação `save_console_config` também passa a tratar a projeção do
**ambiente do próprio processo** como parte da operação de salvamento:
se a preparação, temporário ou `os.replace` falhar, a sessão restaura
cada variável projetada ao valor original, inclusive ausências anteriores.
O INI antigo permanece intacto e o arquivo temporário é removido. Isso
não afirma transação distribuída com Windows Registry, ambiente global
ou processos externos: somente `os.environ` no processo atual e escrita
atômica de um INI são cobertos.

**Fronteiras do aceite:** a prova integral do registro demonstra
`save -> new process -> load` e seus valores tipados, não invocação de
todos os consumidores reais: SERP, CAT-06/07 e demais adaptadores possuem
gates separados. Não inferir consentimento de integração paga nem
homologação de Dynatrace live a partir de uma variável em INI. O
inventário `console_configuration_inventory` deve continuar
indicando `NOT_PROVEN_BY_REGISTRY` onde não há teste de consumidor.

## Gate integrado de APDEX no novo processo

A regressão do registro público também compara os valores serializados de
todos os campos tipados `synthetic_apdex` e `synthetic_apdex_experience`
com os valores reconstituídos no processo Python isolado. A única exclusão
é `device_mix`, derivado do dispositivo canônico em vez de ser fonte de
verdade independente. A prova cobre save/load e integridade de valores, não
atesta a execução física de Dynatrace, navegador ou provedor externo.

## Aceite CAT-06/CAT-07 com parâmetros não-default

Um teste end-to-end isolado prepara uma sessão com valores não-default de
Web Performance e Apdex, grava INI temporário, inicia estado novo com ambiente
limpo e confronta integralmente seções tipadas de CAT-06/CAT-07 e a projeção
de ambiente do runner. Verifica que leitura não reescreve INI e que não
surge token de integração paga. Isso elimina a lacuna de testar só valores
default ou só alguns campos APDEX, sem alegar executar Dynatrace real.

## Prova adicional: consumo offline efetivo CAT-06/CAT-07 (#523)

A regressão em tests/test_console_registry_new_process_roundtrip.py
compara valores não-default restaurados do INI com objetos finais dos
adaptadores reais m23_cli.configured_apdex e m25_cli.configured_experience:
limites, tentativas, timeouts, concorrência, thresholds, dispositivo canônico,
flags de captura, impactos de erro e seus escopos. A única substituição é
o handoff global M25, capturado em memória para não modificar AUD real.

Um cenário independente desativa CAT-06 e confirma que CAT-07 permanece
configurável e ativo. Arquitetura declarada e modo de perfil permanecem
consultivos, sem alteração automática de fórmulas e metodologia do Apdex.

Escopo comprovável: resolução offline real dos adaptadores após save/load
em fixture temporária, sem navegação, serviço pago, IA, Dynatrace live ou
artefatos do operador. A execução física e o smoke Windows permanecem
gates distintos; não tratá-los como resultados já obtidos.

## Regressão de precedência no bootstrap real do console (#523)

O smoke Windows de 19/10/2026 evidenciou `DEVICE=mobile` no INI
temporário após a escolha anterior de `desktop`, enquanto CAT-06
`samples_per_context=7` e CAT-07 `architecture=CSR_SPA` foram gravados
corretamente. Essa evidência **reprova o gate de dispositivo Windows**;
não estabelece, isoladamente, em qual save o valor foi alterado.

Na análise do bootstrap, `interactive_console.main` detectava overrides
a partir de `os.environ` **depois** de `load_console_config`, que
materializa a seção `[environment]` do próprio INI nesse dicionário.
Assim, entradas antigas do inventário podiam ser tratadas incorretamente
como overrides explícitos de Windows/processo e substituir campos tipados
já restaurados de `[console]`, CAT-06 e CAT-07. Um save posterior
perpetuava os valores substituídos.

A correção captura a relação de variáveis externas **antes** do loader:
valores de ambiente efetivamente preexistentes continuam prioritários,
mas valores originados apenas do inventário do INI não sobrescrevem o
estado tipado. Os testes `tests/test_console_bootstrap_ini_precedence.py`
exercitam o bootstrap real com defaults de sistema, divergência física
controlada entre seções, ausência de override externo e override externo
explícito; não iniciam nenhuma AUD nem tráfego de rede.

**Aceite residual:** reiniciar o RASAi no Windows com INI temporário,
selecionar `desktop`, salvar, reabrir e confirmar persistência
(`[console] device=desktop`). Não classificar o smoke Windows como
aprovado até observar esse novo resultado.

## Correção do bloqueio Windows de save por device_mix derivado (#523, 19/10/2026)

A evidência do operador registrou um `ValueError` ao escolher salvar
o dispositivo `desktop` no INI temporário. O guard canônico impediu
substituir um INI que continha opções ausentes do schema corrente.

Foi identificado um mecanismo reproduzível na compatibilidade do
`synthetic_apdex_experience.device_mix`: o primeiro save podia conter
o campo de transporte; após a edição de device, `_ensure_mix` marca
o valor como derivado e o serializador deixa de gravá-lo. O guard
anterior tratava esse único campo conhecido como desconhecido e
bloqueava a transição. A inspeção física do arquivo Windows é
necessária somente se houver outros campos inesperados.

A correção reconhece **exclusivamente** `device_mix` na seção
`[synthetic_apdex_experience]`, valida o valor pelo parser canônico
e permite a migração no próximo save explícito. Device pertence apenas
a `[console].device`, e o mix da próxima AUD é recalculado em runtime.
Se houver outros campos/seções sem contrato, ou `device_mix` inválido,
a gravação continua bloqueada e a origem permanece intacta.

O esquema de compatibilidade do **primeiro save** é mantido para
não quebrar consumidores que inspecionam INIs de estado inicial.
O fluxo após a edição já não persiste `device_mix` como opção
operacional independente.

Cobertura focal: `tests/test_console_device_mix_migration.py`.
Não há execução de AUD, navegação, Dynatrace ou APIs. O smoke real
Windows deverá comprovar save de `desktop`, reabertura, CAT-06=7 e
CAT-07=CSR_SPA; até lá o gate #523 permanece pendente.

## Inventário de compatibilidade entre INI tipado e adapters (19/10/2026)

O inventário offline recebe agora o sinal `--reconcile-typed`, que compara
campos de `[console]`, `[ai]`, `[web_performance]`,
`[synthetic_apdex]` e `[synthetic_apdex_experience]` contra o
parser de estado tipado e a projeção declarativa de ambiente do console.
A inspeção **não carrega o INI no ambiente do processo** e não modifica o
arquivo do operador, nenhum secret store ou AUD. Exemplo:

```powershell
& ".\\.venv\\Scripts\\python.exe" -m rasai.console_configuration_inventory --ini ".\\rasai-console.ini" --reconcile-typed
```

A resposta acrescenta `typed_adapter_reconciliation`, com o contrato
`RASAI-CONSOLE-TYPED-RECONCILIATION-523-001`; cada campo tipado recebe
`DECLARED_RUNTIME_PROJECTION`, `ADAPTER_PARSED`,
`RUNTIME_PROJECTION_ABSENT`, `INVALID_TYPED_VALUE`,
`DERIVED_FROM_DEVICE`, `METADATA_NOT_RUNTIME_INPUT` ou
`NOT_PERSISTED`. Registros não reconhecidos são contabilizados apenas
em conjunto, sem divulgar seu nome ou conteúdo. Valor de URL, arquivo,
query, JSON, token e modelo jamais é impresso. Campos de execução
tarifável continuam sem herdar consentimento de uma AUD anterior.

A projeção em memória **não demonstra** passagem ao subprocesso dos
coletores, sucesso de navegação nem aceite do operador. Para isso permanece
o contrato de configuração efetiva e a prova existente de
save/novo processo/load/ambiente, incluindo o smoke Windows de
`SMOKE_523_INI_PASS` já reportado. O diagnóstico deste modo não solicita
reteste desse smoke. A presença de campo no registry não significa
consumo comprovado no motor; não alterar M23/M25 por causa de uma
divergência de preenchimento.


## Limpeza efetiva de opções tipadas opcionais (#523)

Ao limpar um threshold opcional de CAT-06/CAT-07, um campo Dynatrace
não secreto ou o modelo/reasoning do **provedor IA selecionado**, o console
passa a projetar um valor vazio intencional. A sincronização remove o
override residual de `os.environ`, em vez de deixar o valor da sessão
anterior disponível ao executor. A alteração não remove credenciais, nem
modifica configurações de outros provedores, contratos de scoring ou
parâmetros da AUD já persistidos.

No boot do console, os overrides externos reais devem ser aplicados ao
estado tipado via `apply_environment_defaults` e
`apply_m23_environment_defaults` antes da sincronização; o inventário
`[environment]` originado do INI não substitui essa precedência. O
diagnóstico `--reconcile-typed` diferencia uma chave vazia
(`RUNTIME_PROJECTION_EMPTY`) de projeção preenchida. Nenhuma dessas
classificações comprova uma medição real ou autoriza uma chamada paga.

### Diagnóstico de INI inválido sem eco do valor

Erros de conversão de campos tipados incluem apenas a identificação estável
da seção e da opção, sem expor o texto recebido ou a mensagem bruta de
`int()`/`float()` em avisos de console. A sessão permanece marcada para
reconciliação quando um campo é rejeitado. O leitor não altera a fonte.

### Transação do salvamento pelo menu do console

A ação interativa `_save_configuration` delega toda a sincronização ao
`save_console_config` canônico. Sincronizar o ambiente **antes** do writer
invalidava a proteção de rollback deste em caso de falha de gravação:
valores não salvos podiam ficar ativos no processo. O writer agora é o
único responsável por aplicar a projeção de runtime durante a transação,
restaurando o ambiente anterior se a escrita atômica falhar. O teste
focal injeta falha de disco usando INI descartável e verifica ambiente
inalterado, bytes preservados e mensagem de erro no menu.


### Paridade entre serialização CLI e consumidores M23/M25 (#523, 19/10/2026)

O diagnóstico opt-in `python -m rasai.console_configuration_inventory
--ini <caminho> --verify-apdex` agora, além de inspecionar o INI físico
em cópia descartável e invocar os adapters reais M23/M25, serializa
**em memória** o estado restabelecido via `console_m23.append_m23_command`.
O vetor de argumentos produzido é decodificado novamente pelo
`m23_cli.register_apdex_arguments` e `configured_apdex` efetivos;
as configurações tipadas resultantes de M23 e M25 devem coincidir
integralmente com as resolvidas apenas pelo ambiente da execução.
`cli_argv_parity_verified=true` prova somente esta paridade contratual.
Uma divergência retorna `CLI_ARGV_CONTRACT_MISMATCH` e não silencia o erro.

Parâmetros e argv potencialmente sensíveis (Dynatrace/base URL,
JSON e caminhos) ficam em memória e nunca são impressos. O handoff
global M25 continua intocado por captura local de `set_pending_config`,
e `os.environ` é restaurado integralmente. Nenhum collector, Playwright,
AUD, fornecedor nem processo de auditoria é executado. Portanto
`cli_argv_is_real_execution=false` e `collector_execution_verified=false`
continuam obrigatórios, mesmo com paridade positiva. O smoke Windows
`SMOKE_523_SAVE_REOPEN_PASS` já aprovado não foi repetido.


### Status pós-AUD da Search Intelligence sem criar ou editar SQLite (#523)

O adaptador de apresentação `console_governed_search_runtime._project_result`
passou a usar exclusivamente `sqlite3.connect(...?mode=ro, uri=True)` e
`PRAGMA query_only=ON`, recusando caminho symlink, AUD ID não canônico,
base inexistente ou desproporcional. A projeção pós-subprocesso pode ocorrer
antes do checkpoint WAL; **não** afirmar fonte congelada nem bloquear WAL
ativo, mas jamais solicitar permissão de escrita. Não há mais risco de
`sqlite3.connect(path)` recriar a base numa corrida entre `is_file()`
e o `connect()`. Erro de schema/conexão significa `UNAVAILABLE`, não
`NOT_REQUESTED` enganoso.

Estados não terminais (RUNNING, PENDING, desconhecidos) permanecem
`PENDING`, em vez de virar `COMPLETE_WITH_LIMITATIONS` por falta de
condição de término. Apenas SUCCESS ou estados terminais do contrato
fulfillment são concluídos. Mensagens brutas de erro armazenadas no banco
não são repassadas ao console, prevenindo vazamento acidental de token,
URL ou payload. O status do catálogo permanece ligado à mesma AUD.

Regras e testes sintéticos verificam banco ausente sem criação, estado
externo de outra AUD, RUNNING versus falha terminal versus SUCCESS,
symlink/caminho não canônico, erro de schema e imutabilidade. Não há
nova coleta, provedor, atualização de índice ou alteração do runtime
Search Intelligence do subprocesso.


### Gate offline de consumo Search + preservação de zero no snapshot (#523, 19/10/2026)

```powershell
.\.venv\Scripts\python.exe -m rasai.console_configuration_inventory `
  --ini "caminho\rasai-console.ini" --verify-search
```

O preflight opcional lê o INI físico regular com limite de 2 MiB e selo
SHA-256/identidade antes e depois, cria cópia descartável, recarrega
estado real pelo adapter tipado e monta o vetor de argumentos do console
via `console_governed_search_runtime._append_search_args`. O parser real
de `search_audit_runtime`/`cli_extensions` reinterpreta **localmente**
todos os campos: queries, profundidade, dispositivo, região, competitivo,
comparação HTTP, limites, IA competitiva e YMYL. Exige paridade integral
dos valores restaurados ou retorna `CLI_ARGUMENTS_MISMATCH`. Uma
combinação impossível (IA competitiva com comparação desligada) retorna
`SEMANTIC_CONFIGURATION_CONFLICT`. Quando não há query salva, informa
`NO_SEARCH_QUERY_INPUT`, não inventa intenção de Search API.
`state_to_cli_parity_verified` **não** comprova chamada, autorização
financeira, coleta, observações, reprocessamento nem resultados reais.

Foi corrigida também a geração do snapshot `resume_options.search_intelligence`
em `cli_extensions`: o padrão `int(value or default)` perdia os zeros
explicitamente configurados em `search_max_content_pages=0` e
`search_content_max_redirects=0`, convertendo-os indevidamente em
3 páginas adicionais e 5 redirects no plano de recuperação. Agora os
dois campos respeitam exatamente os zeros do CLI e preservam zeros
inválidos de outros knobs positivos para validação, em vez de reparar
silenciosamente. Isso evita ampliar o escopo de requests após um
complemento/reprocessamento; não modifica o motor Search nem habilita
recoleção. As fixtures cobrem zeros, flags, divergência deliberada de
serializador, INI inconsistente, confidencialidade e ausência de escrita.


### Gate isolado de consumo dos adaptadores centrais IA/Web (#523)

Com o mesmo INI físico de consulta da auditoria, sem reabrir menu nem
realizar nova AUD, o inventário passa a oferecer:

```powershell
.\.venv\Scripts\python.exe -m rasai.console_configuration_inventory `
  --ini "caminho\rasai-console.ini" --verify-core
```

O adaptador `console_core_consumer_preflight.inspect_core_consumers`
lê bytes com identidade/SHA-256 limitados, hidrata um estado de console
na cópia descartável, aplica sua projeção de variáveis **não secretas**,
serializa o comando canônico por `console_config.build_command` e compara
os campos AI/Web/escopo com `cli_extensions.build_parser`. Verifica
o consumer real `cli._configured_web_performance` sem chamar PageSpeed,
CrUX, navegador ou servidor; com IA selecionada, confirma somente a
interpretação do timeout no adapter `cli._configured_ai_timeout_seconds`,
**não a escolha efetiva de provider, modelo ou custo**.

Quando Web=ON e field_source=crux sem chave externa de CrUX, informa
`EXTERNAL_WEB_PREREQUISITE_UNVERIFIED`; não inventa chave API para
satisfazer o teste. Uma configuração sem URL de destino é validável
somente na camada CLI e retorna `CLI_PARITY_TARGET_NOT_SET` em vez de
fingir autorização para nova AUD. Os resultados não contêm modelo,
projeto, URL, argumentos do CLI, paths nem segredos; o INI original,
a AUD e o ambiente do processo são preservados. Para execução humana,
é possível compor `--verify-core --verify-search --verify-apdex` em um
único inventário offline; não há necessidade de repetir o smoke real
de save/reopen já aprovado. Testes novos cobrem Web/IA não-default,
CrUX sem credencial, destino não informado, mutação negativa de
serializador, INI ilegível e symlink. Nenhuma fixture constitui por si
prova de execução física de AI/M21/GSC ou contrato de consentimento.


### Gate de configuração GSC e política de amostragem (#523, 19/10/2026)

O inventário aceita `--verify-gsc`, opcional e combinável com
`--verify-core --verify-search --verify-apdex`. Lê o INI em cópia
descartável com identidade/digest físico, restabelece as entradas não
secretas do operador e chama as funções **reais** de
`gsc_scope.gsc_request_mode`, `gsc_scope.gsc_property_covers_url`,
`gsc_oauth.credential_state` e limites de
`standards_gsc_policy`. A conferência distingue configuração GSC
REQUIRED/AUTO/DISABLED, cobertura estrutural da property frente à URL,
OAuth bearer presente versus refresh credentials completos, e flags
de amostragem Search Analytics. O default do target ausente não é
promovido a escopo de property.

Uma property `sc-domain:` ou URL-prefix compatível **não prova**
a legitimidade do token ou que a conta possui aquela propriedade.
`LOCAL_SCOPE_AND_OAUTH_CONFIG_VERIFIED` significa **somente paridade
de configuração local**: `authenticated_property_access_verified=false`,
`real_gsc_api_usage_verified=false`, `gsc_data_finality_verified=false`
e `provider_requests=0` por contrato. Nenhum refresh token é trocado;
nenhuma credencial, URL de alvo, property ou valor específico de
configuração sai no JSON. A fonte e `os.environ` são preservados.

O gate `--verify-core` também testa agora as entradas
`RASAI_AI_MAX_CYCLES` e `RASAI_AI_CYCLE_DELAY_SECONDS` contra o
construtor canônico `AiExecutionPolicy`, não apenas timeout de IA.
Confirma validação do tipo/faixa, sem chamar provider nem esperar delay.
Fixtures com source GSC/OAuth sintéticos e política IA fora do default
foram adicionadas. Não requer nova AUD nem repetir smokes de 523.


### Correção do registro de entrada GSC e aderência real ao INI (#523)

A inspeção da implementação identificou uma lacuna concreta: o inventário
documentava `RASAI_GSC_ENABLED`, `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`
e os três limites da Search Analytics como consumidores GSC, mas
`console_provider_environment.refresh_specs()` não os incluía entre as
variáveis **não secretas persistíveis**. Assim, a seção `[environment]`
do INI ignorava esses ajustes durante a restauração e gerava avisos de
variável não reconhecida; o preflight GSC publicado anteriormente não
tinha como passar com um INI válido contendo essas chaves.

O mesmo contrato canônico agora inclui os **cinco nomes** e usa
diretamente os validadores de `standards_gsc_policy` para os limites
0–31 dias de análise, 1–50.000 linhas e 0–30 dias de atraso.
O valor zero permanece válido onde definido, sem ser convertido em
default positivo. A propriedade `sc-domain:` ou URL-prefix HTTP(S)
é verificada estruturalmente e seu campo não aceita userinfo,
querystrings ou fragments que poderiam conter tokens.

O `--verify-gsc` compara explicitamente as atribuições GSC do INI
com as que foram realmente restauradas no ambiente do adapter, recusando
`GSC_REGISTRY_INCOMPLETE` e `GSC_INI_ENV_NOT_RESTORED` quando cabível.
São provas de serialização/consumo **local**, nunca prova de OAuth válido
do lado Google, autorização de chamada, escopo de dados ou frescor GSC.
Fixtures novas verificam cobertura de registro, limites exatos,
segredos em URL rejeitados, gravação e restauração sem perda de zeros
e imutabilidade física do INI em cópia temporária.


### Validação fail-closed também na leitura/gravação INI real (#523)

O adapter `console_settings.load_console_config` agora reaproveita,
**somente para as cinco chaves GSC não secretas**, a validação canônica
do menu/consumer. Uma edição direta de INI fora dos limites (por
exemplo 50.001 linhas ou atraso de 31 dias), ou uma URL de propriedade
com userinfo/query/fragment, é recusada **antes da projeção no ambiente**,
com warning por nome técnico sem divulgar valor. O console fica com
`config_dirty=true` e não declara que a configuração foi restaurada
completamente. O operador pode reconciliar explicitamente o arquivo,
sem sobrescrever origem durante a leitura.

O adapter `save_console_config` verifica os overrides GSC presentes
na sessão **antes da transação de gravação**: valores inválidos não
apagam nem reserializam o INI original. Essa barreira não é aplicada
genericamente aos demais catálogos sem prova de necessidade e não
altera o modo de execução do GSC, tokens OAuth ou os motores.
Testes com SQLite inexistente não são necessários: o escopo é apenas
arquivo temporário INI, ambiente de processo e restauração segura.


### Aplicação coesa das preferências GSC durante o load (#523)

Se o INI contiver um conjunto de configurações GSC novo com qualquer
valor inválido (por exemplo, `REQUIRED=true` + propriedade válida
mas teto de linhas fora dos limites), a restauração deixa **todo o
grupo GSC novo inaplicado**, e não somente o campo recusado. Isso
evita ativação parcial de coleta que não corresponde à intenção salva.
É emitido warning por chave sem valores e aviso do grupo; outras
variáveis reconhecidas são processadas normalmente.

Overrides de sessão explicitamente presentes continuam prioritários:
um valor existente para determinada chave não é rebaixado pelo INI
anterior, e não participa da pré-validação do valor de INI que seria
ignorado. O preflight GSC segue sendo um diagnóstico **offline**, não
um autorizador de OAuth/Google. Testes incluem grupo inválido sem
ativação parcial, restauração física intacta, e override de sessão
preexistente, sem rede nem auditoria.


## Gate único offline por issue #523 — abrangência + sem consentimento implícito

O inventário possui agora um modo consolidado **opt-in**, evitando
repetir manualmente os cinco diagnósticos independentes:

```powershell
.\.venv\Scripts\python.exe -m rasai.console_configuration_inventory `
  --ini "C:\caminho\rasai-console.ini" --acceptance-523
```

Em **uma única invocação** o comando executa a reconciliação tipada,
confere o round-trip do rascunho Perplexity em estado fresco
(sem jamais reativar `perplexity_queries` ou STATUS de execução),
e chama os validadores reais dos adapters CAT-06/07, core AI/Web, SERP
e GSC. São utilizadas exclusivamente cópias INI efêmeras verificadas,
sem gravar AUD, chamar Search API/GSC/IA/CrUX ou transportar tokens.
Se também forem solicitados `--verify-core`, `--verify-search` etc.,
o resultado já calculado é reutilizado em vez de executar o mesmo
adapter duas vezes.

`acceptance_523.status` distingue
`OFFLINE_CONTRACTS_VERIFIED`,
`OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES`,
`EXTERNAL_PREREQUISITE_OR_TARGET_MISSING` e
`CONFIGURATION_CONTRACT_FAILURE`. Não se interpreta SERP sem queries
ou Perplexity sem rascunho como regressão; GSC REQUIRED sem credencial
continua dependente de decisão/configuração externa. O comando retorna
exit code **2** se houver erro contratual ou pré-requisito pendente;
caso contrário, **0** apenas para o gate **offline**. Em todos os casos,
`issue_523_final_acceptance_proven=false` e
`runner_execution_verified_by_this_run=false`: o smoke Windows real
anterior não é refeito automaticamente nem é falsamente atestado.

Foi corrigida outra perda efetiva de precedência no serializador
completo: uma variável pública **explicitamente limpa** no ambiente
da sessão (string vazia) não deve ressuscitar o default do registry
ao salvar. O campo persiste vazio no INI; seu consumidor pode decidir
o default no novo processo, mas o console não finge que o operador
salvou o valor antigo. Ausência e reset explícito são diferenciados,
mantendo defaults de knobs jamais configurados. Fixtures cobrem reset,
override não vazio, rascunho WEB/FAST restaurado sem pesquisa, falhas
reais vs pré-requisitos opcionais e exit code do gate isolado.


### Fonte física única e cobertura legada no gate #523

O comando opt-in `--acceptance-523` exige agora que **todos os
diagnósticos do lote** sejam atribuíveis à mesma geração de arquivo
INI: verifica antes e depois a identidade física/tempo/tamanho e
SHA-256 dos bytes originais, rejeitando `INI_SOURCE_CHANGED_DURING_GATE`
mesmo que cada adapter isolado tenha retornado um status de sucesso.
Symlink/arquivo ausente ou fora do limite retorna
`INI_SOURCE_UNVERIFIABLE` antes de qualquer adapter.

O inventário existente distingue valores legados ausentes de
configuração inválida. Se um arquivo antigo omite campos tipados
não derivados (ainda que os parsers apliquem defaults e não haja
falha funcional), o gate registra a quantidade e
`OFFLINE_LEGACY_TYPED_COVERAGE_PARTIAL` em vez de declarar cobertura
**completa** de round-trip. Os estados antigos continuam executáveis
conforme suas políticas; o diagnóstico não grava defaults no INI nem
ativa catálogos para forçar aprovação. Essa abstenção retorna exit 2,
solicitando reconciliação operacional se o objetivo é homologar toda a
matriz de inputs, sem confundir legado com erro de parser.

Os identificadores das variáveis ou valores faltantes não são
serializados no bloco de aceite, apenas contagem e classificação.
Compatibilidade com `--verify-*` foi preservada; resultados já
calculados na mesma invocação são reutilizados, não repetidos.


### Correlação dos checks de fonte e política de secrets no lote (#523)

A checagem do **mesmo INI físico** inclui agora o inventário, e não
apenas os adaptadores. O digest/identidade final é conferido **depois**
da inspeção de completude e da política de secrets, evitando declarar
sucesso se um arquivo foi alterado durante a própria varredura.

Um campo de credencial indevidamente presente em `[environment]`,
inclusive nome não registrado no registry atual, impede o status de
sucesso do gate (**`CONFIGURATION_CONTRACT_FAILURE`**), mesmo quando
um consumidor isolado foi aprovado. A saída revela apenas o booleano
`secret_ini_policy_violations_detected` e o identificador estático do
tipo de falha; jamais inclui chave desconhecida ou seu valor.
Conferência de fonte ausente foi alinhada a
`INI_SOURCE_UNVERIFIABLE`. O diagnóstico não apaga, migra nem exibe
o segredo, para preservar o arquivo do operador até reconciliação.


### Correção crítica: a segunda interpretação M23/M25 não pode afetar AUD pendente (#523)

A revisão do adapter `console_apdex_effective_validation.inspect_apdex_consumers`
encontrou uma regressão anterior: a primeira chamada de
`m23_cli.configured_apdex` usava captura local de
`set_pending_config`, mas a segunda chamada, que repetia o
parsing do vetor CLI, ocorria **após sair da proteção**. Além de
produzir falso `CLI_ARGV_CONTRACT_INVALID` (lista de capturas vazia),
a segunda execução podia atualizar a configuração pendente
process-global do CAT-07. Essa é uma violação do contrato read-only.

As **duas interpretações do mesmo consumo M23/M25** passaram a ficar
no **mesmo contexto temporário de interceptação** e cada uma exige
duas capturas (reset e experiência efetiva). O handoff global original
não é lido, consumido ou substituído. A alteração fica restrita ao
diagnóstico; não modifica os motores homologados nem o protocolo de
execução real. Um teste de regressão instala um setter global
deliberadamente proibido e confirma que tanto o parsing por
ambiente quanto o replay por argv terminam com paridade, sem
tocar a configuração pendente no processo.

Este ajuste é pré-requisito para confiar no agregado
`--acceptance-523`; nenhum resultado anterior do preflight
CAT-06/CAT-07 deve ser chamado de PASS sem a validação focal
desta correção.


### CAT-07 habilitado com limiares não informados: defaults canônicos (#523)

O smoke focal Windows da #523 registrou **13 PASS e 3 FAIL**,
todos em cenários CAT-07 habilitado com limiares de satisfação/frustração
não configurados no estado do console. O runtime `m25_cli.configured_experience`
aceita esse estado e aplica `DEFAULT_UX_SATISFIED_SECONDS` /
`DEFAULT_UX_FRUSTRATED_SECONDS`, porém
`console_m23.experience_from_state` ainda enviava `None` diretamente
para `ExperienceApdexConfig.validate()`, disparando exceção antes
da serialização dos argumentos. O diagnóstico mascarava a causa sob
`CONFIG_OR_ADAPTER_INVALID`. Isso representa **divergência operacional
de configuração**, não deficiência do pytest ou da instalação Windows.

O serializador do console agora utiliza os **mesmos valores canônicos
de defaults do CLI** quando os dois campos estão explicitamente
`None`, sem gravar esses defaults no INI, sem alterar valores
escolhidos pelo operador e sem habilitar o CAT-06. O handoff M25 segue
inteiramente interceptado durante os dois passes do preflight; nenhuma
chamada externa, navegação ou coleta é executada. A nova regressão
valida `experience_from_state`, argv e um INI real em cópia
temporária, comparando o resultado de M25 e a identidade do handoff
original. É necessária somente a repetição dos **três FAIL** do
smoke focal, não dos testes previamente aprovados.


### Estado válido PREPARAR sem URL: não bloquear aceite offline (#523)

O smoke humano de 19/10/2026 do **INI real**, usando
`--acceptance-523`, registrou `source_generation_consistent=true`,
`legacy_typed_fields_unavailable=0`, nenhum consumidor em
`failed_consumer_names`, mas `core=CLI_PARITY_TARGET_NOT_SET` e
`gsc=TARGET_NOT_PREPARED`. Os dois códigos resultam do **mesmo**
estado do operador: a URL de entrada ainda não foi informada.
Não demonstram perda de configuração nem exigem nova URL fictícia,
OAuth GSC ou chamadas comerciais para aprovar a persistência.

O classificador do gate distingue agora os dois estados em
`target_not_prepared_consumer_names=["core","gsc"]` e trata-os como
**preparação intencional incompleta**, em vez de
`external_prerequisite_consumer_names`. Isso permite
`OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES` (exit 0) quando
todos os demais consumidores persistidos estão coerentes, inclusive
Search/Perplexity não solicitados. Não altera os estados brutos
dos consumidores, nem atribui `target_scope_execution_verified`,
`issue_523_final_acceptance_proven` ou autorização de uso pago:
esses campos continuam false. Se uma URL existir e GSC REQUIRED
não tiver autenticação/property, o estado **continua bloqueante**;
`EXTERNAL_WEB_PREREQUISITE_UNVERIFIED` também permanece pendente.
Testes específicos exercitam tanto a classificação sem URL quanto
os adapters físicos sobre INI temporário sem URL, sem rede ou AUD.

Essa correção é metodológica no diagnóstico do save/load; não
adiciona requisito artificial de configurar o alvo antes de salvar.


### #523 — Gate dos snapshots de AUD reaproveitados e impossibilidade de reativar GSC inválido

A trilha `audit_configuration_reuse_console._apply_settings` permitia
aplicar integralmente a seção `[environment]` de uma AUD histórica
**sem os limites que já são exigidos no arquivo INI do console**.
Por exemplo, uma AUD antiga com `RASAI_GSC_ENABLED=true` e
`RASAI_GSC_SEARCH_MAX_ROWS=50001` poderia modificar a sessão antes
de consultar o verdadeiro policy consumer, apesar de o save/load
corrente rejeitar esse valor. O defeito só ocorria no caminho de
reuso de configuração, complementar à issue #523.

Agora `_validate_reused_environment` atua **antes de qualquer
mutação da sessão**: declarações secretas não podem ser importadas
de AUD anterior, os cinco inputs GSC reutilizáveis passam pelos
mesmos validadores do INI/menu, valores não textuais deixam de ser
coagidos silenciosamente e campos legados não reconhecidos permanecem
inertes. A geração de snapshots futuros (`_export_settings`) aplica
o mesmo gate antes de devolver o payload, com restauração do ambiente
de processo em `finally`. Na falha, erro mostra apenas coordenada
técnica de campo, nunca valores sensíveis ou o conteúdo de URLs.

Foi eliminada ainda a possibilidade de `warnings` de campos
tipados inválidos reproduzirem mensagens de `int()/float()/JSON`
que incluíam valores brutos da AUD histórica; avisos agora são
coordenadas de schema sem os valores. Inputs não secretos válidos
continuam reaproveitáveis sob escolha explícita, inclusive os
parâmetros CAT-07 `CSR_SPA`, Guided, limiares, captura de erros e
os limites GSC com zeros canônicos. Nenhum consentimento faturável
ou token histórico é transportado, e nenhum scorer, engine M23/M25,
SQLite canônico ou AUD antiga foi alterado.

O lote inclui regressões sintéticas para cinco GSC malformados,
três segredos históricos, export fail-closed, rollback da sessão,
arquitetura CAT-07 e GSC legítimo; **testes foram criados, ainda não
executados**. Mantida prioridade exclusiva da #523 e a estratégia
de executar somente o lote focal que acrescente evidência real
devido à alteração de contratos.


### Fail-closed de credenciais aninhadas no histórico de AUD (#523)

Além de chaves secretas indevidamente guardadas no grupo
`environment`, o reuso de uma AUD anterior também verifica **nomes
sensíveis em seções tipadas** e configurações Dynatrace JSON com
campos aninhados de credencial. A inspeção ocorre antes de tocar
a nova sessão, usando a mesma barreira
`console_settings._reject_secret_bearing_dynatrace_json` usada
na escrita INI. Se a fonte antiga contiver um token em JSON, não se
replica nem registra seu valor na nova AUD: erro de contrato
com coordenada estática, sem dados sensíveis.

Arquivos de auditoria selados e conteúdo histórico não são alterados.
O comportamento legítimo de `profile_mode=DYNATRACE_IMPORTED`
e arquivo JSON offline sem segredos permanece permitido; esta proteção
não faz chamada à API Dynatrace e não obriga o operador a instalar
pré-requisitos para outros catálogos.


### Diferença de representação e shadowing legítimo GSC (#523)

O gate `--verify-gsc` anteriormente comparava diretamente cada
texto do INI com a variável efetiva do adapter após a restauração.
Isso produzia falsa falha `GSC_INI_ENV_NOT_RESTORED` para limites
legítimos como `00042` linhas (normalizado para `42`) ou `00`
dias (normalizado para `0`), bem como quando o operador possuía
um **override explícito de sessão** com precedência sobre o INI.

A paridade GSC passa a comparar a saída efetiva com o valor que o
próprio validador canônico do menu/INI efetivamente reidrata,
respeitando overrides já presentes por chave. Os valores de origem
não são publicados; a auditoria, propriedade GSC e OAuth remoto não
são executados. Os status `GSC_DISABLED_BY_CONFIGURATION` e os
avisos de valores inválidos continuam preservados. Fixtures com
normalização numérica, propriedade sombreada e zero requests
foram acrescentadas, sem repetir os smokes anteriores.



### #523 — Caminho canônico INI e abrangência de campos desconhecidos

A resolução de `RASAI_CONSOLE_INI` agora normaliza somente o diretório-pai:
o último componente preserva sua identidade física para os guards já
existentes de leitura e gravação recusarem tanto *symlink* válido quanto
link pendente. Antes, o `Path.resolve()` implícito podia seguir o link
antes da inspeção, neutralizando a política de não modificar fontes do
operador. Não há migração nem edição de INIs anteriores.

A reconciliação `--reconcile-typed`, consumida por `--acceptance-523`,
deixa de limitar o schema a cinco seções: também avalia as seções
`presentation`, `search_intelligence` e `perplexity_draft` já
registradas pelo console, além das futuras seções declaradas por
`_state_values`. A validação de timezone é pura, sem tocar o ambiente
do processo. Entradas físicas sem owner em seções reconhecidas,
`environment`, `DEFAULT` ou seções desconhecidas bloqueiam o aceite
offline, sem ecoar nomes arbitrários nem valores. Campos opcionais
ausentes continuam tratados separadamente da divergência contratual.

Foram adicionadas regressões focais de symlink via resolução implícita,
cobertura SERP/rascunho/horário e recusa secret-safe de entradas
desconhecidas. A evidência de execução pertence ao registro do teste
focal, não a esta descrição de contrato. Nenhum smoke Windows
anteriormente aprovado deve ser repetido por rotina.
