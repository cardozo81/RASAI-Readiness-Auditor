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
| Queries e modo WEB/FAST da Perplexity Search API | Entradas transitórias `SearchConsoleState` | **Não gravados** | **Não** | **Nunca por restauração** |
| Chaves, tokens, senhas, DSNs com credenciais | Secret store / ambiente protegido | **Não gravados no INI** | Conforme mecanismo seguro, independente do INI | Não |
| Seleção explícita de chamadas potencialmente faturáveis | Interação/autorização da AUD corrente | Controle de execução e evidências da AUD | Não transferível entre AUDs | Somente para a AUD autorizada |

## CAT-06 / CAT-07 - round-trip e execução efetiva

O teste isolado `tests/test_console_persistence_matrix_523.py` exercita
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
  queries e WEB/FAST não são transportados à nova AUD.

## Limites de homologação

A matriz automatizada comprova serialização e leitura de configuração sem
serviços externos. **Não comprova por si só:** carga produtiva Dynatrace,
consentimento humano em ambiente Windows, equivalência de uma AUD histórica
ou consistência de medição sintética em uma página real. Esses são gates
distintos; não devem ser marcados como aprovados apenas por CI.

## Inventário completo do registro de variáveis (#523)

O comando local `python -m rasai.console_configuration_inventory_523`
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

O comando `python -m rasai.console_configuration_inventory_523 --verify-apdex`
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

A inspeção offline `python -m rasai.console_configuration_inventory_523`
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

O teste `tests/test_console_fresh_process_roundtrip_523.py` executa dois
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

A regressao `tests/test_console_fresh_process_roundtrip_523.py`
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
