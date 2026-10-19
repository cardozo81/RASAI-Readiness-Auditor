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
