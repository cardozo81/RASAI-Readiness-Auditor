# Console interativo de execução

O RASAi oferece o console textual local:

```powershell
rasai-console
```

O console é uma camada de configuração, preflight, observabilidade, execução e operação sobre o mesmo pipeline da CLI. Ele não implementa um segundo motor de auditoria.

## Princípios de UX

- navegação de primeiro nível orientada a tarefas;
- uma tela lógica por vez;
- configuração explícita antes da execução;
- detalhes avançados disponíveis sem ocupar o primeiro nível;
- defaults seguros e visíveis;
- estados `APTO`, `CONFIGURAR` e `INDISPONÍVEL` apresentados junto da ação correspondente;
- perfis de execução como overlays temporários da sessão;
- listas guiadas para configurações com domínio fechado;
- variáveis relacionadas agrupadas por recurso/contexto;
- finalidade, dependências, impacto e referências exibidos antes da edição avançada;
- secrets nunca exibidos em claro nem gravados no INI ou snapshot de AUD;
- persistência opcional de credenciais no Windows limitada ao escopo `User`;
- `Windows/Machine` apenas observado, nunca alterado automaticamente;
- progresso da etapa e progresso geral do pipeline apresentados separadamente;
- integração externa indisponível não vira finding do website;
- relatórios consolidados continuam baseados em auditorias persistidas.

## Menu inicial

O primeiro nível apresenta as tarefas principais:

```text
INÍCIO

1. Nova auditoria / configurar e executar
2. Auditorias / histórico
3. Relatórios consolidados
4. Integrações / credenciais
5. Sistema / restaurar padrões
?. Ajuda
Q. Sair
```

Esse menu não substitui funções existentes. Ele organiza o acesso às superfícies já disponíveis e adiciona operações contextuais sobre `AUD-*`.

### 1. Nova auditoria / configurar e executar

Abre o dashboard completo de configuração da próxima auditoria. Nele permanecem acessíveis:

```text
Entrada
Projeto
Dispositivo
IA
Remediações por IA
Web Performance
max-pages
Web Performance max-pages
Idioma / mercado
Raiz de auditorias
Synthetic Apdex
Timezone de apresentação
Análise profunda de URL
Search Intelligence / termos SERP
Perfil da execução
Salvar configuração INI
Ajuda / custos
Variáveis de ambiente / credenciais
Relatórios consolidados
Executar
Abrir pasta/relatório da última auditoria
Carregar configuração de AUD
Restaurar padrões do RASAi
```

Extensões funcionais continuam usando suas próprias telas e validações. A reorganização do primeiro nível não cria contratos paralelos.

### 2. Auditorias / histórico

Lista os `AUD-*` que possuem `audit.db` na raiz configurada e permite selecionar uma auditoria específica.

A tela contextual mostra, quando disponíveis:

```text
Processamento
Score
Status do relatório
Elegibilidade para consolidação
Requisitos atendidos
Pendentes
Bloqueados
Quantidade de reprocessamentos
Último RPR
```

Ações do AUD selecionado:

```text
1. Reprocessar pendências desta auditoria
2. Carregar esta configuração para uma nova auditoria
3. Mostrar caminhos de artefatos
V. Voltar
```

#### Reprocessar pendências

O reprocessamento mantém o mesmo `AUD-*` e utiliza o motor seletivo de recovery. Antes da confirmação, o console mostra os requisitos ainda não resolvidos e a quantidade de sucessos que serão preservados quando o fulfillment já estiver projetado.

A confirmação exige a palavra:

```text
REPROCESSAR
```

Ao terminar, são apresentados:

```text
AUD
RPR
Processamento
Score
Relatório
Elegibilidade para consolidação
Itens tentados
Itens resolvidos
Sucessos preservados
Itens restantes
Itens temporalmente expirados, quando existirem
```

Uma auditoria já completa não tem seus sucessos repetidos; o motor retorna o estado atual sem criar trabalho desnecessário.

#### Carregar configuração

Carregar configuração inicia uma **nova execução**, não um reprocessamento.

Qualquer `AUD-*` com snapshot canônico íntegro pode fornecer configuração, independentemente de a observação estar completa, parcial, preliminar ou bloqueada. O novo AUD só será criado quando o usuário executar a configuração carregada.

O snapshot restaura parâmetros não secretos e inputs reproduzíveis, incluindo os termos e parâmetros de Search Intelligence quando aquela execução os utilizou.

Credenciais nunca são recuperadas do AUD. Depois do carregamento, o console reconcilia a configuração com o ambiente atual e alerta quando uma integração solicitada não possui key/token/configuração válida. O usuário pode corrigir a dependência antes do preflight.

O contrato completo está em [AUDIT_CONFIGURATION_REUSE.md](AUDIT_CONFIGURATION_REUSE.md).

### 3. Relatórios consolidados

Abre a superfície de relatórios históricos/consolidados já existente. A consolidação base lê `AUD-*/audit.db` e não executa coletas ou chamadas externas apenas para montar a visão consolidada.

Somente auditorias elegíveis pelo contrato de finalização participam das métricas consolidadas.

### 4. Integrações / credenciais

Abre a configuração avançada de integrações e variáveis. A navegação interna segue:

```text
categoria funcional -> contexto/recurso -> variável
```

Exemplos:

```text
Google Search Console
Google PageSpeed / Lighthouse
Google Chrome UX Report (CrUX)
SERP / Search Intelligence
IA / provider
IA - contexto editorial / YMYL
Synthetic Navigation Apdex
Synthetic User Experience Apdex
Dynatrace / calibração Apdex
OIDC / Identity
Control plane / banco
```

Para campos com domínio fechado, o console apresenta opções aceitas. Entrada livre permanece para valores realmente abertos, como URL, path, property, token/secret, locale ou números de faixa contínua.

### 5. Sistema / restaurar padrões

Abre a restauração da baseline atual do produto.

O usuário escolhe entre:

```text
Restaurar padrões e PRESERVAR credenciais
Restaurar padrões e REMOVER credenciais gerenciadas
```

No Windows, a remoção gerenciada alcança sessão e `Windows/User`. `Windows/Machine` nunca é alterado automaticamente. Auditorias, relatórios, `audit.db`, banco do control plane e arquivos do projeto não são apagados.

## Arquivo INI

Arquivo padrão:

```text
rasai-console.ini
```

O INI armazena parâmetros não sensíveis de configuração geral. API keys, tokens, senhas e outros secrets não são gravados nele.

Termos de Search Intelligence são inputs de execução e não pertencem ao INI geral. Eles são persistidos no snapshot do respectivo `AUD-*` para permitir reprodução daquela observação.

Precedência prática para configuração geral:

```text
valor explícito presente no processo/Windows
> configuração não sensível persistida no INI
> default do produto/runtime
```

Ao salvar, o console indica explicitamente que a operação é `SEM CHAVES`.

## Cores e estados

Cor é reforço visual, nunca a única informação:

| Estado | Semântica |
|---|---|
| `APTO`, `DEFINIDO`, `ON`, credencial presente | operação disponível |
| `CONFIGURAR`, atenção | ação necessária |
| `INDISPONÍVEL`, erro, bloqueio | operação não executável no estado atual |
| `PADRÃO`, `OPCIONAL`, `DESABILITADA`, ausente | estado neutro/inativo |

## IA

O console separa duas perguntas:

1. o provider pode ser configurado?
2. o provider está apto para executar agora?

**Providers sem credencial continuam configuráveis**; ficam indisponíveis apenas para execução até que a dependência necessária seja atendida.

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

Aliases suportados são resolvidos pelo `provider_registry`. `none` desabilita IA. `auto` utiliza somente providers elegíveis e aptos segundo a política vigente.

GitHub Copilot é `explicit-only`: pode ser selecionado explicitamente quando apto, mas não participa automaticamente do pool `AI=auto`.

### Credenciais de IA

A tela de provider mantém as ações canônicas:

```text
S. Setar/alterar Key na sessão
P. Persistir/remover Key no Windows/User
L. Limpar Key somente da sessão
X. Excluir Key da sessão e do Windows/User
A. Habilitar/desabilitar no AUTO sem apagar a Key
U. Usar este provider nesta auditoria
V. Voltar
```

A edição de secret usa mascaramento quando o terminal suporta leitura segura por caractere; caso contrário, usa entrada sem eco. O valor não é exibido em claro depois da edição.

Toda alteração de credencial recalcula imediatamente a capability do provider na mesma sessão. Uma Key válida pode tornar o provider `APTO` sem reiniciar o console quando não houver outro impedimento real.

## Windows/User e Windows/Machine

Persistência gerenciada de secrets no Windows usa:

```text
HKEY_CURRENT_USER\Environment
```

Essa operação não exige PowerShell ou `.ps1` executado como Administrador. O RASAi não modifica Windows/Machine ao gerenciar credenciais normais do console.

Uma credencial existente em `Windows/Machine` pode ser detectada e usada conforme a precedência do ambiente, mas não é criada, alterada ou removida automaticamente. Windows/Machine não é administrado automaticamente pelo RASAi.

Variáveis de ambiente não constituem um secret manager; processos com acesso ao mesmo perfil podem ler esses valores.

## Provider registry e AUTO

`AI=auto` **não é uma cadeia fixa OpenAI -> DeepSeek -> MiMo**. O pool é derivado dinamicamente do `provider_registry` e da política runtime.

O processo considera, entre outros fatores:

- elegibilidade para AUTO;
- credencial/configuração válida;
- exclusões configuradas pelo operador;
- disponibilidade atual;
- política de custo/roteamento;
- quarentena/circuit breaker.

Desabilitar um provider no AUTO não apaga sua credencial nem impede seleção explícita quando o provider suporta esse uso. Providers `explicit-only`, como GitHub Copilot, ficam fora do pool automático por contrato.

## Modelos, reasoning e timeout

Depois de escolher um provider apto, o console permite selecionar modelo, esforço/profundidade quando suportado e timeout por tentativa.

O timeout padrão de IA é definido pelo contrato runtime e vale por tentativa de provider, não pela auditoria inteira.

Modelos e opções de reasoning derivam do `provider_registry`; o console não mantém um catálogo concorrente.

## Remediações por IA

Remediação de conteúdo e remediação técnica são independentes e só ficam executáveis quando existe IA apta para a finalidade correspondente.

São advisory/evidence-bound. Não alteram automaticamente Score, Coverage, Confidence, RuleExecution ou Finding.

## Search Intelligence / SERP

Search Intelligence mantém separados:

- inputs da execução: termos, profundidade, região, device, análise competitiva;
- configuração de provider, limites e credencial.

Termos podem ser informados no dashboard da auditoria. Provider/credencial/limites ficam na área de integrações.

Ao carregar a configuração de um AUD, os inputs de execução SERP também são restaurados. Se a key/token atual do provider não estiver disponível, o console aponta a dependência antes da execução.

## Web Performance

Web Performance pode usar PageSpeed/Lighthouse e CrUX conforme configuração. O console mostra estado, fonte de field data, timeout e limites antes da execução.

Quando uma configuração carregada exige CrUX direto e a credencial atual não está disponível, o console apresenta alerta e o preflight impede execução incompatível.

## Synthetic Navigation Apdex

Synthetic Navigation Apdex gera tráfego real contra o alvo. A configuração inclui:

```text
threshold T
amostras válidas
máximo de tentativas
máximo de páginas
timeout
delay
concorrência
perfil client/hardware/network
modo de aquisição
```

`RASAI_APDEX_ACQUISITION_MODE` controla o modo de aquisição compartilhada, com valores `auto` e `isolated`. Essa escolha é operacional e não altera scoring por si só; `auto` permite reutilizar aquisição física quando isso for metodologicamente seguro e `isolated` força medições independentes.

O operador deve ajustar volume e concorrência de forma conservadora.

## Synthetic User Experience Apdex

A experiência sintética possui população, device mix, KPM, thresholds, tratamento de erros, sessão, settle/delay e demais parâmetros próprios. Esses parâmetros permanecem separados do Navigation Apdex mesmo quando uma aquisição física pode ser compartilhada com segurança.

## Dispositivo

O contexto de dispositivo aceita:

```text
mobile
desktop
both
```

`both` mantém Mobile e Desktop como contextos independentes; o relatório não cria média automática que esconda diferenças.

## Timezone de apresentação

Timezone altera somente a apresentação. Persistência e processamento temporal continuam canonicamente em UTC.

O valor configurado é um timezone IANA. O default de apresentação é:

```text
America/Sao_Paulo
```

## Análise profunda de URL

Improvement Intelligence é independente da IA padrão da auditoria. A tela própria define se a etapa será executada e permite escolher provider explícito, modelo, reasoning, domínios, limite de recomendações e timeout.

A análise exige URL única, credencial apta e configuração suportada. É advisory/non-scoring e não executa exploração ativa de segurança.

Quando Search Intelligence foi executado na mesma observação, a análise pode reutilizar evidência SERP já persistida.

## Perfis de execução

Perfis são overlays temporários para a próxima execução e não substituem os defaults persistentes.

Eles não gravam credenciais nem alteram variáveis do SO. Ajustes finos feitos depois no dashboard vencem o preset no domínio alterado.

## Progresso de execução

O modelo de progresso permanece orientado a duas escalas:

```text
Etapa atual
[####################----------] 68%

Pipeline geral
[###############---------------] ~49%

Executando
<operação real / URL / dispositivo / contexto>
```

O percentual da etapa representa avanço interno observado sempre que o executor fornece essa informação. O percentual global representa a posição da etapa no pipeline e pode ser uma projeção quando o total exato ainda depende do runtime.

O console também apresenta, conforme disponível:

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

A atualização usa estado local do subprocesso, banco e logs de execução. Não cria polling HTTP adicional contra o website apenas para atualizar a interface.

## Pós-execução

Depois de uma auditoria, o console mantém acesso a consumo/cobertura persistidos e ações sobre os artefatos da sessão.

Uma auditoria que permaneça incompleta pode ser aberta posteriormente em:

```text
Início > Auditorias / histórico
```

Nesse contexto o operador consegue revisar o estado e iniciar reprocessamento seletivo sem precisar conhecer o comando CLI correspondente.

## Segurança

- secrets não entram no INI nem no snapshot reutilizável do AUD;
- secrets não são exibidos em claro;
- reports e logs não devem registrar API keys/tokens;
- persistência Windows/User exige ação explícita;
- nenhuma operação normal de credencial exige Administrador;
- credencial configurada não implica quota/crédito/modelo disponível;
- provider indisponível não é finding do website;
- remover provider do AUTO não apaga sua Key;
- `Windows/Machine` não é administrado automaticamente;
- perfis de execução não persistem credenciais;
- análise profunda não executa exploração ativa;
- recomendações de IA não alteram scoring automaticamente;
- reprocessamento preserva sucessos e respeita a validade temporal das evidências.

## Documentos relacionados

- [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md)
- [AUDIT_CONFIGURATION_REUSE.md](AUDIT_CONFIGURATION_REUSE.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md)
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
