# Console interativo de execução

O RASAi mantém `rasai audit` como interface estável e oferece o console textual opcional:

```powershell
rasai-console
```

O console é uma camada de configuração, preflight, observabilidade e execução sobre o mesmo pipeline da CLI. Ele não implementa um segundo motor de auditoria.

## Princípios

- uma tela lógica por vez;
- configuração explícita antes da execução;
- defaults seguros e visíveis;
- listas guiadas para configurações com domínio fechado;
- secrets nunca exibidos em claro nem gravados no INI;
- providers sem credencial continuam configuráveis;
- disponibilidade para execução e possibilidade de configuração são estados distintos;
- persistência opcional de credenciais no Windows usa somente o escopo `User`;
- o console não exige execução como Administrador para persistir/remover credenciais em `Windows/User`;
- o escopo `Windows/Machine` é apenas observado pelo RASAi e nunca é alterado automaticamente;
- alterações de credencial recalculam imediatamente a aptidão do provider;
- integração externa indisponível não vira finding do website;
- Synthetic Apdex gera carga HTTP real e permanece separado de Web Performance/IA;
- relatórios consolidados são offline/read-only sobre auditorias persistidas.

## Arquivo INI

Arquivo padrão:

```text
rasai-console.ini
```

O INI armazena somente parâmetros não sensíveis. API keys, tokens, passwords e outros secrets não são gravados nele.

Precedência prática do console:

```text
valor já presente no processo/Windows
> configuração não sensível persistida no INI
> default do runtime
```

Ao salvar, o console mostra explicitamente que a operação é `SEM CHAVES`.

## Menu principal vigente

```text
1. Entrada
2. Projeto
3. Dispositivo
4. IA
5. Remediações IA
6. Web Performance
7. max-pages
8. WebPerf max-pages
9. Idioma / mercado
10. Raiz auditorias
11. Synthetic Apdex
12. Timezone apresentação

S. Salvar configuração INI [SEM CHAVES]
H. Ajuda / custos
E. Variáveis de ambiente / credenciais
C. Histórico / relatórios consolidados [OFFLINE - sem APIs]
R. Executar [APTO|INDISPONÍVEL]
Q. Sair
```

Quando existe auditoria anterior disponível, o console também oferece atalhos para abrir a pasta e o último relatório.

## Cores e estados do console

O console usa cor como reforço visual, nunca como única informação:

| Estado | Cor esperada |
|---|---|
| `APTO`, ativo, credencial presente, incluído no AUTO | verde |
| `CONFIGURAR`, atenção ou ação necessária | amarelo |
| `INDISPONÍVEL`, erro ou bloqueio real | vermelho |
| `DESABILITADA`, ausente, inativo ou excluído do AUTO | cinza/dim |
| informação contextual | ciano |

Essa semântica vale também para a área de providers de IA.

## Opção 4 - IA

A opção 4 separa duas perguntas:

1. **o provider pode ser configurado?** - sim, qualquer provider registrado pode ser selecionado;
2. **o provider está apto para executar agora?** - depende de credencial/configuração válida e de bloqueios runtime.

Portanto, um provider sem Key não fica bloqueado para configuração. Ele aparece como `CONFIGURAR` e pode ser aberto normalmente.

Providers canônicos atuais:

```text
openai
deepseek
mimo
xai
qwen
gemini
anthropic
```

Aliases:

```text
grok   -> xai
claude -> anthropic
```

`none` desabilita IA para a auditoria. `auto` usa o pool dinâmico de providers elegíveis.

### Gerenciamento por provider

Ao selecionar um provider concreto, o console mostra:

```text
Estado execução
Motivo
Variável de credencial
Sessão atual
Windows / User
Windows / Machine
Pool AUTO, quando aplicável
```

Ações:

```text
S. Setar/alterar Key na sessão
P. Persistir/remover Key no Windows/User
L. Limpar Key somente da sessão
X. Excluir Key da sessão e do Windows/User
A. Habilitar/desabilitar no AUTO sem apagar a Key
U. Usar este provider nesta auditoria
V. Voltar
```

A ação `A` aparece somente para providers `auto_eligible`.

### Semântica das ações de Key

**Setar/alterar (`S`)**

- altera imediatamente a variável da sessão atual;
- não grava no INI;
- recalcula imediatamente a capability do provider;
- limpa bloqueios transitórios associados à configuração anterior.

**Persistir/remover Windows/User (`P`)**

- exige confirmação explícita;
- grava/remove somente no perfil do usuário Windows;
- não usa `HKEY_LOCAL_MACHINE`;
- não exige PowerShell ou `.ps1` executado como Administrador;
- remover a persistência User mantém a Key já carregada na sessão atual;
- após a operação, a capability é recalculada imediatamente.

**Limpar sessão (`L`)**

- remove apenas a variável do processo atual;
- não apaga uma eventual persistência em Windows/User;
- novos processos ainda podem herdar a credencial persistida.

**Excluir Key (`X`)**

- remove a Key da sessão;
- remove a persistência Windows/User quando existir;
- não modifica Windows/Machine;
- se existir uma Key em Machine, o console informa que ela continua presente e que sua remoção é uma operação administrativa externa ao RASAi.

**Usar provider (`U`)**

- só conclui a seleção quando o provider está `APTO`;
- provider sem configuração válida permanece configurável, mas não executável.

### Reavaliação imediata de aptidão

Toda alteração de credencial invalida bloqueios runtime antigos do provider. Assim, após definir ou persistir uma Key válida, o status deve voltar a `APTO` na mesma sessão quando não existir outro impedimento real.

Não é necessário fechar/reabrir o console para atualizar esse estado.

## Windows/User x Windows/Machine

O RASAi persiste secrets somente em:

```text
HKEY_CURRENT_USER\Environment
```

Essa operação não exige elevação administrativa.

O RASAi pode detectar uma credencial já existente em `Machine`, mas não a cria, altera ou remove. O produto não deve solicitar execução como Administrador apenas para gerenciar suas credenciais normais.

Variáveis de ambiente não são um secret manager. Processos com acesso ao mesmo perfil podem ler esses valores.

## Provider registry e AUTO

`AI=auto` **não é uma cadeia fixa OpenAI -> DeepSeek -> MiMo**.

O pool AUTO é derivado do `provider_registry` atual:

1. considera providers com `auto_eligible=true`;
2. exige credencial/configuração válida para execução;
3. aplica exclusões configuradas pelo operador;
4. mantém a credencial mesmo quando o provider é excluído do AUTO;
5. usa a política de roteamento/fallback do runtime;
6. um provider pode continuar sendo selecionado explicitamente mesmo quando está excluído do AUTO.

O submenu AUTO permite alternar inclusão por provider e exige pelo menos um provider `APTO` incluído antes de ativar `AI=auto`.

## Modelos, reasoning e timeout

Depois de escolher um provider `APTO`, o console permite selecionar modelo, esforço/profundidade quando suportado e timeout por tentativa.

Default de timeout:

```text
RASAI_AI_TIMEOUT_SECONDS=180
```

O timeout vale por tentativa de provider, não para a auditoria inteira.

Defaults de modelo/reasoning vêm do provider registry e da política runtime vigente. Não devem ser duplicados manualmente em outro contrato quando o registry já fornece a lista.

## Remediações IA

A opção 5 só fica disponível quando a opção 4 possui IA ativa e apta.

As duas finalidades são independentes:

```text
conteúdo
crawling/discovery técnico
```

Ambas são advisory/evidence-bound e podem gerar chamadas/custo adicionais. Não alteram automaticamente Score, Coverage, Confidence, RuleExecution ou Finding.

## Variáveis de ambiente / credenciais

O menu `E` continua disponível para configuração avançada e para integrações que não passam pelo gerenciador específico de provider.

Grupos funcionais:

```text
Aplicação e execução
IA - credenciais
IA - modelos e reasoning
IA - endpoints avançados
IA - contexto editorial / YMYL
Web Performance / Google APIs
Synthetic Apdex
Browser / Playwright
```

Para campos com domínio fechado, o console apresenta lista de opções aceitas em vez de exigir texto livre quando essa lista é conhecida pelo runtime.

Secrets são exibidos apenas como presença/origem, por exemplo:

```text
[SET] [SESSÃO]
[SET] [SO:USER]
[SET] [SO:MACHINE]
```

## Perfis sintéticos configuráveis

Os perfis do Synthetic Apdex separam três dimensões independentes por população:

```text
client/device geometry
hardware/CPU envelope
network envelope
```

Mobile, Desktop e Tablet possuem opções próprias. Os valores permitidos e defaults vigentes estão em [SYNTHETIC_RUNTIME_PROFILES.md](SYNTHETIC_RUNTIME_PROFILES.md) e [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

O console apresenta esses campos como enums/listas e persiste os valores não sensíveis no INI.

Os defaults são baselines controladas de laboratório, não médias estatísticas da população real. RAM física, GPU, térmica e scheduler do sistema operacional não são simulados como hardware real.

## Dispositivo

`RASAI_DEVICE_CONTEXT` aceita:

```text
mobile
desktop
both
```

`both` mantém Mobile e Desktop como contextos independentes; o relatório não cria média automática que esconda diferenças.

## Web Performance

A opção 6 configura PageSpeed/Lighthouse e CrUX.

Default operacional do timeout:

```text
120 segundos
```

PageSpeed controla seu próprio perfil Lighthouse remoto. Os perfis sintéticos do RASAi não são enviados como CPU/rede/viewport customizados à API pública PageSpeed.

## Synthetic Navigation Apdex

A opção 11 controla a carga sintética. O console solicita/expõe:

```text
T
amostras válidas
máximo de tentativas
máximo de páginas
timeout
delay
concorrência
perfis client/hardware/network
```

A execução gera tráfego HTTP real contra o alvo. O operador deve ajustar volume e concorrência de forma conservadora.

## Timezone de apresentação

A opção 12 controla apenas a apresentação de timestamps.

O runtime continua persistindo/processando tempo canônico em UTC. O valor configurado é um timezone IANA, por default:

```text
America/Sao_Paulo
```

## Progresso de execução

Durante a auditoria o console exibe, conforme disponível:

```text
Status
URL
Dispositivo
Operação
Início
Fim
Duração
Etapa
Progresso
Detalhe
```

A atualização usa estado local do subprocesso/SQLite/log e não cria polling HTTP adicional contra o website auditado.

## Histórico / relatórios consolidados

A opção `C` é offline. Ela lê auditorias persistidas e não executa IA, PageSpeed, CrUX ou Synthetic Apdex.

Os `AUD-*/audit.db` permanecem fonte de verdade; qualquer índice consolidado é derivado e reconstruível.

## Segurança

- secrets não entram no INI;
- reports e logs não devem registrar API keys;
- persistência Windows/User exige ação explícita;
- nenhuma operação normal de Key exige Administrador;
- credencial configurada não implica crédito/quota/modelo disponível;
- provider indisponível não é finding do website;
- remover do AUTO não apaga Key;
- alterar Key recalcula imediatamente a capability;
- Windows/Machine não é administrado automaticamente pelo RASAi.

## Documentos relacionados

- [CONFIGURATION.md](CONFIGURATION.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [AI_GUIDE.md](AI_GUIDE.md)
- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md)
- [SYNTHETIC_RUNTIME_PROFILES.md](SYNTHETIC_RUNTIME_PROFILES.md)
- [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md)
- [REPORT_GUIDE.md](REPORT_GUIDE.md)
