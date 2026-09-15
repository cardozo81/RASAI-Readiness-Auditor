# Console interativo de execução

O console local é iniciado por:

```powershell
rasai-console
```

O console é a camada de navegação, configuração, preflight, observabilidade e operação do RASAi. Ele usa o mesmo runtime da CLI. Pipeline de auditoria, scoring, coleta, retry, quarentena, circuit breaker, fulfillment, reprocessamento e geração de relatórios permanecem sob os contratos funcionais já existentes.

## Menu inicial

```text
INÍCIO

1. Preparar auditoria
2. Auditorias / histórico
3. Relatórios consolidados
4. Inteligência Artificial
5. Integrações e serviços
6. Todas as configurações
7. Sistema / restaurar padrões

H. Ajuda
Q. Sair
```

O primeiro nível separa tarefas do usuário de configuração técnica. Inteligência Artificial possui uma superfície própria porque é uma capacidade transversal consumida por diferentes análises. Integrações e serviços reúne dependências externas. Todas as configurações expõe o catálogo técnico completo.

## Preparar auditoria

A preparação permanece no contexto:

```text
INÍCIO > PREPARAR AUDITORIA
```

até `V. Voltar ao início` ou saída da aplicação.

A convenção visual é:

```text
número curto = item acionável da tela atual
ID numérico de 6 dígitos = identidade estável da configuração canônica
letra = ação ou navegação
- = resultado automático, derivado ou não selecionável
```

Um ID de configuração é derivado da chave canônica e não muda conforme o caminho usado para chegar à variável. O formato de 6 dígitos reduz o ruído visual do formato anterior de 8 dígitos; 4 dígitos não são usados porque o espaço de identificação seria pequeno demais para preservar com segurança o contrato de identidade estável conforme o catálogo cresce.

### Perfil da próxima auditoria

O perfil aparece no início da preparação:

```text
1. 000001  Perfil base : <perfil ou Personalizado>
```

Perfis são presets temporários da próxima execução. O contrato detalhado está em [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md).

### Escopo

```text
[ ESCOPO ]
2. 000002  Entrada
3. 000003  Projeto
4. 000004  Device
5. 000005  Idioma / mercado
6. 000006  Timezone apresentação
```

`Device` aceita `mobile`, `desktop` ou `both` e é a autoridade para os relatórios de contexto de dispositivo.

### Análises e resultados

A tela apresenta os resultados Mobile e Desktop como derivados de `Device`:

```text
Device=mobile   -> Relatório Mobile INCLUÍDO; Relatório Desktop NÃO APLICÁVEL
Device=desktop  -> Relatório Mobile NÃO APLICÁVEL; Relatório Desktop INCLUÍDO
Device=both     -> ambos INCLUÍDOS
```

Eles não possuem checkbox independente.

O catálogo de análises/resultados apresentado na preparação é:

| Capacidade/resultado | Natureza na preparação |
|---|---|
| Domínio e descoberta | incluído; configuração relacionada quando aplicável |
| Acessibilidade | incluído; pode receber evidência Lighthouse |
| Web Performance | configurável |
| Métricas e padrões | usa serviços configurados quando aplicável |
| Search Intelligence | configurável; depende de termos e contrato SERP |
| Apdex de navegação | configurável |
| Apdex de experiência | configurável; depende do Apdex de navegação |
| Visibilidade em IA | automático conforme fontes/evidências aplicáveis |
| Search & AI observados | automático conforme integrações observacionais configuradas |
| Análise profunda e melhorias | configurável; exige URL única e IA principal apta |
| Conteúdo e JSON-LD | resultado com enriquecimento por IA quando configurado |
| Remediações | determinísticas e, opcionalmente, enriquecidas por IA |
| Quality & decisão | derivado do conjunto de evidências |

A numeração curta dos itens acionáveis é contextual. O nome da capacidade e os IDs numéricos das configurações relacionadas são as referências estáveis.

### Resultados sistêmicos

```text
Visão geral
Readiness SARI
Metodologia de scoring
Contexto de captura
Uso de IA
Referências / metodologia
```

Esses resultados pertencem ao contrato de relatório e não possuem seleção independente na preparação.

### Ações

```text
R. Executar auditoria
S. Salvar configuração no arquivo [SEM SECRETS]
L. Carregar configuração de AUD [NOVA EXECUÇÃO]
E. Integrações e serviços
A. Todas as configurações
H. Ajuda / custos
C. Histórico / relatórios consolidados [OFFLINE]
V. Voltar ao início
Q. Sair
```

A execução usa o preflight e os handlers existentes. A camada de apresentação não cria uma política alternativa de elegibilidade.

## Inteligência Artificial

`INÍCIO > Inteligência Artificial` concentra configuração de IA e apresenta a seleção principal da execução.

Existe uma seleção principal de IA por execução. `none` desabilita IA quando nenhuma capacidade selecionada a exige. Seleção explícita usa o provider escolhido. `auto` usa o runtime canônico de elegibilidade, custo, disponibilidade, quarentena, circuit breaker e fallback.

O conjunto de providers é projetado dinamicamente pelo `provider_registry`; `AI=auto` não é uma cadeia fixa OpenAI -> DeepSeek -> MiMo. Providers marcados como `explicit-only` ficam fora do pool automático. GitHub Copilot é atualmente `explicit-only`, portanto a presença de `COPILOT_GITHUB_TOKEN` não o inclui automaticamente no AUTO.

Providers sem credencial continuam configuráveis. A ausência de credencial afeta readiness e elegibilidade de execução, mas não impede abrir o provider, revisar modelo/reasoning/endpoints ou gerenciar a própria credencial.

Na tela de um provider, as ações de credencial e participação são apresentadas sem duplicar o owner canônico:

```text
S. Setar/alterar Key na sessão
P. Persistir/remover Key no Windows/User
L. Limpar Key somente da sessão
X. Excluir Key da sessão e do Windows/User
A. Habilitar/desabilitar no AUTO sem apagar a Key
U. Usar este provider nesta auditoria
```

Depois de alterar credencial, habilitação ou seleção, o console recalcula imediatamente a capability e atualiza o readiness exibido.

Provider, modelo, reasoning, endpoint, credencial e demais parâmetros pertencem aos owners canônicos publicados pelo registry. Módulos consumidores não criam um segundo provider de produção.

## Integrações e serviços

A superfície mostra somente configurações de integrações e serviços externos, agrupadas por owner funcional. Cada variável pode ser acessada pelo mesmo ID numérico em qualquer contexto.

As ações do catálogo permitem:

```text
O. Por owner funcional
A. Ordem alfabética
E. Por estado
M. Somente modificadas
P. Somente pendentes
F. Localizar por ID / nome / finalidade
D. Diagnóstico técnico das integrações
V. Voltar
```

O diagnóstico é consultivo e está documentado em [INTEGRATION_DIAGNOSTICS.md](INTEGRATION_DIAGNOSTICS.md).

## Todas as configurações

Essa superfície expõe o catálogo completo de `EnvironmentSpec`, incluindo configurações de aplicação, integrações, IA e parâmetros avançados.

A tela de uma variável é organizada em blocos estáveis:

```text
INFORMAÇÃO
ESTADO ATUAL
DOMÍNIO / INPUT
AÇÕES
```

São exibidos, quando aplicáveis: finalidade, owner, contexto, necessidade, impacto, observações, valor, origem, estado, tipo, valores aceitos, default, referência e documentação.

Campos com domínio fechado usam seleção guiada. Ao escolher `S. Definir / alterar`, o console lista os valores técnicos aceitos, apresenta uma descrição curta em PT-BR quando a opção não é autoexplicativa e pede confirmação antes de aplicar. Listas fechadas aceitam seleção múltipla. Texto livre é reservado a valores realmente abertos, como URL, path, locale, property, identificador externo, secret ou número contínuo.

O identificador técnico permanece visível mesmo quando existe explicação amigável. Isso evita esconder do operador o valor efetivamente persistido no contrato (`auto`, `health-safety`, nomes de modelos, categorias Lighthouse etc.).

## Origem das configurações

A UI diferencia, conforme o caso:

```text
SESSÃO
ARQUIVO
WINDOWS/USER
WINDOWS/MACHINE
DEFAULT
NÃO CONFIGURADO
```

A origem é informação de diagnóstico e precedência. `Windows/Machine` pode ser observado, mas não é administrado automaticamente pelo console.

No Windows, persistência em escopo de usuário utiliza `HKEY_CURRENT_USER\Environment`. Esse fluxo não exige PowerShell ou `.ps1` executado como Administrador, não modifica Windows/Machine e preserva a regra de que Windows/Machine não é administrado automaticamente pelo RASAi.

## Persistência

O arquivo padrão é:

```text
rasai-console.ini
```

Ao editar uma configuração não sensível, o usuário escolhe entre manter a alteração somente na sessão ou salvar no arquivo. O comando `S. Salvar configuração` também persiste os inputs não sensíveis da próxima execução, incluindo os parâmetros de Search Intelligence configurados na sessão.

API keys, bearer tokens, passwords, client secrets, refresh tokens e demais secrets nunca são gravados no INI.

## Search Intelligence

Termos, profundidade, região, device SERP e classificação competitiva são inputs da próxima execução, não variáveis de ambiente. Ficam na sessão durante o uso normal. Ao escolher explicitamente salvar a configuração, esses inputs não sensíveis são gravados no INI e podem ser restaurados ao reabrir o console.

Provider, modo, credencial, limites e governança SERP permanecem no catálogo de integrações. Consulte [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md).

## Apdex de experiência e Device

Enquanto o mix de dispositivos do Experience Apdex estiver herdado, o console deriva:

```text
Device=mobile   -> mobile=100,desktop=0,tablet=0
Device=desktop  -> mobile=0,desktop=100,tablet=0
Device=both     -> mobile=60,desktop=40,tablet=0
```

`tablet` não é um `Device` da auditoria principal. Ele permanece disponível apenas como ajuste avançado do mix de Experience Apdex.

Alterar amostras, limites ou outros parâmetros do Apdex não transforma o mix herdado em override. O mix passa a ser personalizado somente quando o próprio mix é alterado. Um mix herdado não é materializado como override no INI.

`RASAI_APDEX_ACQUISITION_MODE` controla somente a estratégia compartilhada de aquisição do Apdex e não altera scoring. Os valores documentados são `auto` e `isolated`; a escolha de aquisição permanece separada dos thresholds e da metodologia de cálculo.

## Estados e cores

Cor reforça o estado, mas o texto é obrigatório:

| Estado | Uso |
|---|---|
| `APTO`, `INCLUÍDO`, `CONCLUÍDO`, `HABILITADO` | disponível/atendido |
| `CONFIGURAR`, `PARCIAL`, `APTO COM LIMITAÇÕES` | atenção ou dependência pendente |
| `ERRO`, `INDISPONÍVEL`, `BLOQUEADO` | falha ou impedimento |
| `AUTOMÁTICO`, `HERDADO`, `DERIVADO`, `PERSONALIZADO` | origem/composição do comportamento |
| `DESABILITADO`, `NÃO APLICÁVEL`, `PADRÃO` | estado neutro/inativo |

## Auditorias, reprocessamento e reutilização

`Auditorias / histórico` apresenta a lista recente em colunas explícitas:

```text
Nº  AUDITORIA  CONCLUSÃO LOCAL  SITUAÇÃO  REPROCESSAMENTO
```

`CONCLUSÃO LOCAL` usa o timezone de apresentação configurado e só é preenchida quando a auditoria atingiu conclusão efetiva. Estados técnicos como `COMPLETE`, `PARTIAL_RETRYABLE`, `PARTIAL_BLOCKED`, `FAILED_FATAL` e `EXPIRED_FOR_COMPLETION` continuam persistidos internamente, mas são apresentados ao usuário em PT-BR (`Concluída`, `Parcial — pode reprocessar`, `Parcial — há bloqueios`, `Falha definitiva`, `Expirada para conclusão`).

A coluna separada `relatório=PRELIMINARY|FINAL` não é repetida na listagem quando apenas duplica o estado operacional já comunicado. A tela detalhada mantém score, consolidação, requisitos e reprocessamentos quando essas informações acrescentam significado.

Auditorias concluídas não oferecem reprocessamento porque não possuem pendências a recuperar. Estados com pendências recuperáveis continuam oferecendo reprocessamento seletivo, preservando itens já bem-sucedidos por padrão.

`GERENCIAR AUDITORIAS / EXCLUSÃO SEGURA` segue a mesma estrutura tabular do histórico. A tabela adiciona `SEL`, `TAMANHO` e `DOMÍNIO`, usa data/hora local e calcula a largura da coluna `AUDITORIA` pelo tamanho real dos IDs para manter os cabeçalhos alinhados.

Carregar configuração de AUD não reutiliza credenciais persistidas no workspace. O ambiente atual resolve as credenciais e o preflight informa dependências ausentes.

Consulte [AUDIT_CONFIGURATION_REUSE.md](AUDIT_CONFIGURATION_REUSE.md).

## Sistema / restaurar padrões

`INÍCIO > Sistema / restaurar padrões` restaura a baseline versionada do produto. No Windows, o RASAi administra no máximo o escopo `Windows/User`; `Windows/Machine` nunca é removido automaticamente.

Consulte [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md) e [SYSTEM_DEFAULTS.md](SYSTEM_DEFAULTS.md).
