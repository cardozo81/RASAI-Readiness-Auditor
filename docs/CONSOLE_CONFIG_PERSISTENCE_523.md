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
somente como marcador e precedência `SESSION_OVERRIDES_INI`, quando aplicável.
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
