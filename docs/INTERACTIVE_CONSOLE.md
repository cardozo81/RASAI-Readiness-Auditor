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
- listas múltiplas guiadas quando o runtime publica um conjunto finito de valores;
- variáveis relacionadas agrupadas por contexto/recurso sempre que possível;
- finalidade, dependências, impacto e referências exibidos antes da edição avançada;
- secrets nunca exibidos em claro nem gravados no INI;
- secrets recebem feedback visual mascarado por `*` quando o terminal suporta leitura segura caractere a caractere;
- providers sem credencial continuam configuráveis;
- disponibilidade para execução e possibilidade de configuração são estados distintos;
- persistência opcional de credenciais no Windows usa somente o escopo `User`;
- o console não exige execução como Administrador para persistir/remover credenciais em `Windows/User`;
- o escopo `Windows/Machine` é apenas observado pelo RASAi e nunca é alterado automaticamente;
- alterações de credencial recalculam imediatamente a aptidão do provider;
- integração externa indisponível não vira finding do website;
- Synthetic Apdex gera carga HTTP real e permanece separado de Web Performance/IA;
- Improvement Intelligence é opt-in, exige URL única e permanece advisory/non-scoring;
- relatórios consolidados são offline/read-only sobre auditorias persistidas.

O contrato detalhado dessa UX está em [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md).

## Arquivo INI

Arquivo padrão:

```text
rasai-console.ini
```

O INI armazena somente parâmetros não sensíveis. API keys, tokens, passwords e outros secrets não são gravados nele.

Precedência prática do console para as configurações gerais:

```text
valor já presente no processo/Windows
> configuração não sensível persistida no INI
> default do runtime
```

**Exceção deliberada:** dentro de `rasai-console`, o toggle de execução de Improvement Intelligence é controlado pelo item **13. Análise profunda URL**. O runtime neutraliza temporariamente `RASAI_IMPROVEMENT_INTELLIGENCE` durante a fase base para impedir execução invisível ou duplicada. As variáveis `RASAI_IMPROVEMENT_*` continuam válidas para CLI, worker/SaaS, automação e diagnóstico; no console interativo, a ativação efetiva vem do item 13 e da seção `[improvement_intelligence]`.

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
13. Análise profunda URL

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
| `APTO`, `DEFINIDO`, `ON`, credencial presente, incluído no AUTO | verde |
| `CONFIGURAR`, atenção ou ação necessária | amarelo |
| `INDISPONÍVEL`, erro ou bloqueio real | vermelho |
| `PADRÃO`, `OPCIONAL`, `DESABILITADA`, ausente, inativo ou excluído do AUTO | cinza/dim |
| informação contextual/breadcrumb | ciano |

Essa semântica vale também para a área de providers de IA, configuração avançada e indicação de prontidão da análise profunda.

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
copilot
```

Aliases:

```text
grok           -> xai
claude         -> anthropic
github-copilot -> copilot
```

`none` desabilita IA para a auditoria. `auto` usa o pool dinâmico de providers elegíveis.

GitHub Copilot é `explicit-only`: pode ser configurado e usado explicitamente, mas não participa do pool `AI=auto`. Essa separação evita consumo involuntário da assinatura Copilot.

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

A ação `A` aparece somente para providers `auto_eligible`; portanto não aparece para GitHub Copilot.

### Semântica das ações de Key

**Setar/alterar (`S`)**

- altera imediatamente a variável da sessão atual;
- não grava no INI;
- recalcula imediatamente a capability do provider;
- limpa bloqueios transitórios associados à configuração anterior;
- em terminal interativo compatível, cada caractere digitado/colado aparece somente como `*`.

O mascaramento é estritamente visual. O valor real continua sendo o valor validado e armazenado na sessão. Backspace remove o caractere real correspondente e o `*` visual. Se o terminal não suportar mascaramento seguro por caractere, o console usa entrada sem eco; nunca degrada para exibição em claro. O número de `*` pode revelar aproximadamente o comprimento da credencial, trade-off deliberado para fornecer feedback ao operador sem expor o conteúdo.

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

Providers `explicit-only` ficam fora desse pool por contrato, independentemente da existência de credencial. Atualmente, GitHub Copilot pertence a essa categoria.

O submenu AUTO permite alternar inclusão por provider elegível e exige pelo menos um provider `APTO` incluído antes de ativar `AI=auto`.

## Modelos, reasoning e timeout

Depois de escolher um provider `APTO`, o console permite selecionar modelo, esforço/profundidade quando suportado e timeout por tentativa.

Default de timeout:

```text
RASAI_AI_TIMEOUT_SECONDS=180
```

O timeout vale por tentativa de provider, não para a auditoria inteira.

Defaults de modelo/reasoning vêm do provider registry e da política runtime vigente. Não devem ser duplicados manualmente em outro contrato quando o registry já fornece a lista.

Para Copilot, o modelo público é `auto` e reasoning fica em `PROVIDER_DEFAULT`; a integração não cria variável de reasoning inexistente.

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

A navegação segue **categoria funcional → contexto/recurso → variável**. Isso mantém itens relacionados próximos mesmo quando, tecnicamente, alguns valores pertencem a registries ou mecanismos de persistência diferentes. Exemplos de contextos:

```text
Google Search Console
Google PageSpeed / Lighthouse
Google Chrome UX Report (CrUX)
SERP / Search Intelligence
IA / <provider>
Improvement Intelligence
Synthetic Navigation Apdex
Synthetic User Experience Apdex
Dynatrace / calibração Apdex
OIDC / Identity
Control plane / banco
```

Ao abrir uma variável, o console apresenta finalidade, tipo, valores aceitos, default efetivo, condição de obrigatoriedade, sensibilidade, custo/impacto, estado atual, exemplo, contexto e referências oficiais conhecidas.

Para campos com domínio fechado, o console apresenta lista de opções aceitas em vez de exigir texto livre. Isso inclui booleanos (`true`/`false`), enums e listas CSV fechadas. Campos dependentes são recalculados a partir do contexto atual: por exemplo, modelo e reasoning avançados da Improvement Intelligence usam o catálogo do provider selecionado.

Entrada livre permanece apenas para valores realmente abertos, como URL, path, property, token/secret, locale/tag BCP-47 ou número de faixa contínua.

As credenciais de IA e SERP mostram a URL oficial de documentação e de cadastro/login/geração de token quando conhecida pelo registry/catálogo. GSC, PageSpeed, CrUX e demais standards externos usam as referências oficiais cadastradas no service registry.

Secrets são exibidos em estado apenas como presença/origem, por exemplo:

```text
[SET] [SESSÃO]
[SET] [SO:USER]
[SET] [SO:MACHINE]
```

Durante a **edição** do secret, terminal compatível mostra somente `*`; depois da edição, o valor continua não sendo exibido.

O grupo **IA - análise profunda** inclui os overrides avançados de Improvement Intelligence. A configuração normal deve ser feita pelo item 13. `RASAI_IMPROVEMENT_INTELLIGENCE` não substitui visualmente esse item dentro de `rasai-console`; ele existe para CLI/worker/SaaS, automação e troubleshooting do contrato por ambiente.

Veja [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md) para o contrato normativo da interface e [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) para o contrato variável por variável.

## Perfis sintéticos configuráveis

Os perfis do Synthetic Apdex separam três dimensões independentes por população:

```text
client/device geometry
hardware/CPU envelope
network envelope
```

Mobile, Desktop e Tablet possuem opções próprias. Os valores permitidos e defaults vigentes estão em [SYNTHETIC_RUNTIME_PROFILES.md](SYNTHETIC_RUNTIME_PROFILES.md) e [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

O console apresenta esses campos como enums/listas e persiste os valores não sensíveis no INI. O catálogo de configuração avançada recebe a metadata dos mesmos presets canônicos usados pelo runtime, evitando descrição genérica ou digitação manual de IDs conhecidos.

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
modo de aquisição compartilhada/isolada
```

A execução gera tráfego HTTP real contra o alvo. O operador deve ajustar volume e concorrência de forma conservadora.

`RASAI_APDEX_ACQUISITION_MODE=auto|isolated` controla somente a aquisição física compartilhável entre Navigation Apdex e Experience Apdex. `auto` compartilha apenas quando URL, device, perfil, sessão e demais requisitos são compatíveis; `isolated` preserva navegações separadas. Scores, thresholds, targets e device mix permanecem independentes.

## Timezone de apresentação

A opção 12 controla apenas a apresentação de timestamps.

O runtime continua persistindo/processando tempo canônico em UTC. O valor configurado é um timezone IANA, por default:

```text
America/Sao_Paulo
```

## Opção 13 - Análise profunda URL

Improvement Intelligence é independente da IA padrão da opção 4. A opção 13 permite habilitar uma análise evidence-bound mais profunda sem obrigar toda a auditoria a usar o mesmo provider/modelo/esforço.

Requisitos de prontidão:

```text
Entrada = URL única
provider explícito selecionado
credencial do provider apta
modelo suportado
reasoning suportado
domínios de análise válidos
```

`AUTO` e `NONE` não são aceitos como provider da análise profunda. A feature reutiliza a key/token já configurada para o provider escolhido; não existe segunda cópia da credencial no INI.

Configurações persistidas na seção `[improvement_intelligence]`:

```text
enabled
provider
model
reasoning_effort
domains
max_recommendations
timeout_seconds
```

Domínios selecionáveis:

```text
TECHNICAL_HTML
SEMANTICS_STRUCTURE
CONTENT
SEARCH_RANKING
FILES_DISCOVERY
PERFORMANCE
ACCESSIBILITY
BEST_PRACTICES
SECURITY
AI_ACCESS
```

A análise ocorre após a auditoria normal e, quando Search Intelligence foi executado na mesma sessão, pode reutilizar a evidência SERP já persistida. Ela não cria um segundo crawler competitivo.

No console interativo, o item 13 é a única autoridade que decide se essa etapa será executada. O toggle de ambiente é neutralizado somente durante a auditoria base e restaurado em seguida; isso impede dupla chamada paga e mantém a UI coerente com o que efetivamente será executado.

Segurança é passiva: headers, cookies e achados já observados podem gerar recomendações, mas não há exploração, fuzzing ou pentest ativo. Search/SERP é contexto correlacional; o console não promete posição futura de ranking.

O relatório `improvement-intelligence.html` é sempre materializado. Quando a opção 13 está OFF, ele registra estado não executado. Quando ON, apresenta findings, recomendações priorizadas, evidências, HTML original versus sugerido quando aplicável e consumo da IA. Nenhum desses outputs altera `SARI-001`/`SCORE-GEO-004`.

O idioma preferencial das explicações/sugestões pode ser definido por `RASAI_AI_ANALYSIS_LANGUAGE`; `auto` usa o idioma da auditoria e não substitui a detecção real do idioma da página.

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

Quando a análise profunda está habilitada, aparece como fase terminal própria antes da conclusão, incluindo provider/modelo, estágio e percentual. A duração final inclui essa etapa.

A atualização usa estado local do subprocesso/SQLite/log e não cria polling HTTP adicional contra o website auditado.

## Histórico / relatórios consolidados

A opção `C` é offline. Ela lê auditorias persistidas e não executa IA, PageSpeed, CrUX ou Synthetic Apdex.

Os `AUD-*/audit.db` permanecem fonte de verdade; qualquer índice consolidado é derivado e reconstruível.

Improvement Intelligence permanece complementar no consolidado: suas recomendações não são promediadas dentro do SARI histórico. A validação de ganho pertence à nova auditoria/before-after.

## Segurança

- secrets não entram no INI;
- durante a entrada interativa, secrets são mascarados por `*` quando suportado e nunca exibidos em claro;
- em terminal incompatível com máscara por caractere, o fallback continua sem eco;
- reports e logs não devem registrar API keys;
- persistência Windows/User exige ação explícita;
- nenhuma operação normal de Key exige Administrador;
- credencial configurada não implica crédito/quota/modelo disponível;
- provider indisponível não é finding do website;
- remover do AUTO não apaga Key;
- alterar Key recalcula imediatamente a capability;
- Windows/Machine não é administrado automaticamente pelo RASAi;
- análise profunda não executa exploração ativa;
- recomendações de IA não alteram scoring nem são prova de ganho até nova medição.

## Documentos relacionados

- [CONFIGURATION.md](CONFIGURATION.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [AI_GUIDE.md](AI_GUIDE.md)
- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md)
- [SYNTHETIC_RUNTIME_PROFILES.md](SYNTHETIC_RUNTIME_PROFILES.md)
- [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md)
- [REPORT_GUIDE.md](REPORT_GUIDE.md)
