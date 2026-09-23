# Console interativo

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado.

## Inicialização

No Windows, a partir da raiz do projeto:

```powershell
.\abrir-rasai-console.cmd
```

O launcher valida/prepara Python 3.13, `.venv`, dependências declaradas, Chromium/Playwright e executa o entrypoint `rasai-console`.

Quando o ambiente já estiver preparado e ativado, o mesmo console pode ser iniciado diretamente:

```powershell
rasai-console
```

Menu principal:

```text
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

## Cabeçalho do console

O cabeçalho exibe somente contexto operacional útil da tela. A listagem de variáveis efetivas do processo não é apresentada visualmente.

O snapshot completo e sanitizado do ambiente é registrado em:

```text
<audits_root>/.rasai/logs/console.log
```

Secrets são registrados apenas como referência configurada, nunca com seu conteúdo. Um novo evento é gravado quando o conjunto efetivo de variáveis ou a raiz de auditorias muda.

## Navegação, edição e atalhos

Toda tela navegável abaixo de `INÍCIO` expõe uma ação explícita de retorno:

```text
V. Voltar
```

Quando a tela altera um valor, o prompt identifica o campo imediatamente antes do cursor e oferece cancelamento sem commit. O formato de referência é:

```text
Descrição do campo [valor atual] [V=voltar sem salvar]:
```

Regras:

- `V` abandona a edição antes de aplicar ou persistir o novo valor;
- em telas com vários campos relacionados, o cancelamento restaura o conjunto anterior e impede alteração parcial;
- menus de seleção fechada exibem `V. Voltar` junto das opções;
- confirmações destrutivas exibem explicitamente `V. Voltar sem excluir/resetar`;
- `ENTER para continuar` é somente pausa de leitura e não representa edição de dado.

### Confirmação de ações

O console diferencia **escolha operacional**, **confirmação adicional necessária** e **ação sensível/destrutiva**.

Uma ação explícita não é confirmada novamente apenas para repetir a mesma intenção. Quando a operação pode seguir com IA ou sem IA, as variantes aparecem como ações irmãs na mesma lista e a escolha do modo é a autorização final da operação não destrutiva:

```text
1. Executar/gerar com IA
2. Executar/gerar sem IA
V. Voltar
```

A prévia de custo e o contexto efetivo são exibidos antes dessa escolha quando aplicáveis. Uma confirmação adicional `C/V` só é usada quando existe consequência material que ainda não foi explicitada pela própria ação. Ações sensíveis/destrutivas continuam exigindo confirmação específica.

Para ação sensível/destrutiva, a tela mostra a frase exigida como conteúdo visível antes do cursor:

```text
CONFIRMAÇÃO OBRIGATÓRIA
Ação            : ...
Digite exatamente: EXCLUIR
V. Voltar sem excluir
Confirmação:
```

Frases usadas conforme o contexto incluem `EXCLUIR`, `EXCLUIR TODOS OS AUDS`, `RESETAR`, `RESTAURAR`, `PERSISTIR`, `REMOVER` e `DESCARTAR`.

Regras:

- `ENTER` vazio nunca confirma uma ação;
- texto incorreto não executa a ação e mantém a tela de confirmação;
- `V` abandona a confirmação sem aplicar a mutação;
- a instrução necessária para confirmar não depende somente do prompt/cursor;
- persistência/removal de credencial em Windows/User exige frase explícita;
- descartar configuração não salva ao sair exige `DESCARTAR`.

Atalhos operacionais são uniformes nas telas de AUD e CONS:

```text
I. Abrir relatório HTML
P. Abrir pasta/diretório
V. Voltar
```

A letra `I` fica reservada para abrir relatório nas superfícies de resultado/detalhe. Busca direta de Audit ID usa `B`.

### Entrada visual de dados sensíveis

Campos classificados como secret, API key, token, client secret ou credencial equivalente usam entrada mascarada no console local.

Durante digitação ou colagem no terminal interativo:

```text
Chave de API - Provider [V=voltar sem salvar]: ****************
```

Cada caractere recebido é representado visualmente por `*`. O asterisco existe somente na camada de apresentação: o valor real permanece em memória para validação e, quando o operador escolher persistir, é gravado integralmente no destino permitido.

Regras:

- o conteúdo real nunca é ecoado no terminal;
- colagem recebe a mesma máscara da digitação, com um `*` por caractere;
- backspace remove o último caractere real e o respectivo `*` visual;
- o valor armazenado não contém os asteriscos da máscara;
- secrets continuam proibidos no `rasai-console.ini`;
- em terminal sem suporte seguro à máscara interativa, o fallback oculta totalmente a entrada em vez de exibi-la em claro.

## Semântica de cores do console

A cor é usada somente como reforço visual de informações relevantes; o texto continua sendo a fonte semântica e o console permanece legível sem ANSI/VT ou com `NO_COLOR`.

A convenção operacional é:

- **verde**: conclusão, sucesso, elegibilidade, disponibilidade ou resultado apto;
- **amarelo**: execução ativa, atenção, parcialidade, pendência, retry ou item selecionado que exige cuidado;
- **vermelho**: falha, bloqueio, indisponibilidade crítica ou ação destrutiva;
- **cinza**: informação neutra, aguardando, indisponibilidade não crítica ou item não selecionado;
- **ciano**: título/breadcrumb e contexto operacional.

A aplicação é deliberadamente restrita. Tabelas, menus e descrições não são integralmente coloridos; somente estados, ações e valores que precisam orientar a atenção do operador recebem cor.

Confirmações destrutivas seguem a mesma regra. Em `Digite exatamente: EXCLUIR`, por exemplo, somente `EXCLUIR` recebe destaque destrutivo; a frase ao redor permanece neutra.

As telas que listam ou definem **variáveis, credenciais, secrets, origem de configuração e valores técnicos de configuração** preservam sua identidade visual própria. Esta semântica operacional não reinterpreta nem substitui as cores desses componentes.

## Apresentação canônica de processamento

O bloco `PROGRESSO DO PIPELINE` pertence exclusivamente a superfícies de execução ou ao resumo final imediatamente relacionado à execução. Ao retornar para `INÍCIO`, configuração, histórico ou outros menus operacionais, o estado visual de progresso é limpo e não deve ser reapresentado como se ainda houvesse processamento ativo.


Auditoria, reprocessamento e consolidado usam a mesma gramática visual de execução. O console redesenha a tela corrente em vez de acumular etapas antigas no terminal e mantém o histórico cronológico completo nos logs.

A superfície de execução mostra, quando o plano é conhecido:

```text
Etapa        : X de Y [previstas, quando o total ainda puder mudar]
Anterior     : ...
Atual        : ...
Próxima      : ...
Andamento    : percentual medido da etapa, quando existe unidade real
Pipeline     : projeção da posição no trabalho total
Executando   : atividade/subprocesso atual
```

Percentual medido e projeção são conceitos distintos. Latência de rede/provider não é convertida em ETA ou percentual fictício. Etapas com unidade própria expõem seus contadores. Synthetic Apdex, por exemplo, pode mostrar amostras válidas, inválidas, alvo, tentativas e limite máximo. Chamadas externas podem mostrar integração, requisição/tentativa, estado e timeout quando esses dados existem.

O fim de uma coleta não implica conclusão visual imediata da etapa. Consolidação, cálculo, persistência, materialização de artefatos e geração de HTML permanecem visíveis enquanto ocorrerem. **Gerando relatório** significa ler resultados/evidências já persistidos, compor o HTML e gravar os arquivos; essa fase não recolhe a URL para satisfazer a apresentação.

## Paridade entre Console e SaaS

Console local e SaaS utilizam os mesmos contratos de produto para auditorias e consolidados. A diferença é apenas a superfície de operação e persistência.

- auditorias e consolidados podem ser listados e ter o respectivo relatório aberto em ambas as superfícies;
- o consolidado usa BASE/ATUAL por Audit ID, mesma URL, mesmo dispositivo e políticas `ALL`, `SUCCESS_ONLY` ou `MANUAL`;
- IA é opcional no consolidado em ambas as superfícies;
- Console executa localmente; SaaS cria jobs duráveis e o worker executa o mesmo domínio;
- secrets locais usam sessão/Windows User; SaaS usa o mecanismo de secrets do control plane;
- nenhuma superfície recalcula o **Índice de Prontidão Search & IA** ou o **Método de Pontuação de Prontidão**, nem reexecuta catálogos apenas para abrir/listar relatórios; IDs técnicos `SARI-001`/`SCORE-GEO-004` permanecem apenas para rastreabilidade.

## Relatórios consolidados

O item `3. Relatórios consolidados` trabalha com duas superfícies independentes:

```text
1. Gerar novo consolidado
2. Histórico de consolidados
```

Um consolidado longitudinal usa exatamente uma URL, exatamente um dispositivo e pelo menos duas auditorias. O usuário seleciona duas auditorias; a mais antiga torna-se **BASE** e a mais recente torna-se **ATUAL**, independentemente da ordem dos cliques.

Depois dos dois marcos, o console identifica as auditorias compatíveis existentes entre eles e, quando houver intermediárias, oferece:

- **Todas do intervalo** - inclui todas as AUDs elegíveis entre BASE e ATUAL;
- **Somente concluídas com sucesso** - usa o estado canônico da governança das fontes;
- **Seleção manual** - mantém BASE/ATUAL e permite escolher as intermediárias.

A primeira seleção restringe a lista à mesma URL e ao mesmo dispositivo. A listagem e o histórico aceitam pesquisa por Audit ID/CONS ID, domínio/URL ou dispositivo. O período é derivado dos marcos selecionados; o fluxo normal não solicita data inicial ou final.

Após definir as auditorias, o console reconhece e valida o conjunto, congela os `AUD-*` efetivamente selecionados e apresenta a decisão final no mesmo menu:

```text
1. Gerar relatório consolidado com IA
2. Gerar relatório consolidado sem IA
V. Voltar
```

O modo sem IA materializa somente dados e análises já persistidos. O modo com IA conclui primeiro a preparação determinística e depois acrescenta interpretação multidimensional, correlações, estratégia e orientação para ação. Provider/modelo, previsão de tokens e custo são exibidos antes da escolha final quando determináveis; selecionar a opção inicia a geração sem uma segunda pergunta "confirmar geração".

A tela de execução usa a apresentação canônica comum a AUD/RPR/CONS: etapa anterior, atual e próxima; `X de Y`; andamento da etapa; progresso total; atividade corrente; integrações/IA e contadores reais quando disponíveis. O consolidado não recoleta a URL, não reexecuta catálogos e não altera `audit.db`.

Antes do cruzamento existe a etapa **Reconhecendo auditorias**. Ela contabiliza fontes encontradas/elegíveis e somente depois congela o conjunto efetivo. Auditorias e artefatos fora da seleção não alimentam cálculos nem IA. A etapa **Gerando relatório** consome os dados já persistidos, renderiza o HTML e grava os artefatos em disco; ela não abre nova coleta da URL.

O histórico mostra, no mínimo:

- CONS ID;
- data de geração;
- URL;
- dispositivo;
- período;
- quantidade de auditorias;
- política de seleção;
- modo de geração;
- estado da IA;
- confiabilidade determinística do conjunto.

Ausência deliberada de IA é `NOT_REQUESTED` e não constitui falha nem torna o relatório incompleto.

Ao selecionar um CONS no histórico, a tela de detalhe oferece **M. Ver linha de comando**, **I. Abrir relatório** e **P. Abrir pasta** para o artifact materializado daquele item.


## Execução externa / linha de comando

O atalho canônico para AUD, RPR e CONS é:

```text
M. Ver linha de comando
```

A superfície permite alternar entre Windows, Linux e macOS, copiar o comando executável, abrir o log humano de comandos e abrir a pasta contextual. Secrets aparecem somente como placeholders comentados `**********`; o valor real nunca é impresso nem gravado.

Antes da execução, o comando é **PLANEJADO**. Depois de AUD/RPR/CONS, o comando registrado é **EXECUTADO** e o log fica em:

```text
<audits_root>/.rasai/logs/execution-commands/
```

Esse log é texto UTF-8 para operação humana e é diferente do `console.log` técnico estruturado. Ele fica fora dos workspaces e pacotes de relatório e não altera `audit.db`, manifests, hashes ou HTMLs.

A documentação completa de Task Scheduler, cron, systemd timer, launchd, clipboard e override de credenciais está em [EXECUTION_SCHEDULING.md](EXECUTION_SCHEDULING.md).

## Preparar auditoria

A preparação é orientada por catálogo:

```text
ESCOPO
CATÁLOGO DA AUDITORIA
PLANO DA PRÓXIMA AUDITORIA
EXECUÇÃO / ARMAZENAMENTO
AÇÕES
```

O operador seleciona um ou mais itens `CAT-*`. A seleção abre imediatamente as opções do item; não existe wizard obrigatório de `Avançar`.

A tela `PREPARAR AUDITORIA` contém somente ações ligadas ao plano corrente. Os acessos globais ficam exclusivamente no menu `INÍCIO`; portanto a preparação não repete atalhos para Inteligência Artificial, Integrações e serviços, Todas as configurações, Ajuda, Histórico/Consolidados ou Sair.

### Diagnóstico de integrações e IA

A superfície global de integrações expõe o diagnóstico canônico pelo caminho:

```text
INÍCIO
→ 5. Integrações e serviços
→ T. Validar integrações e IAs configuradas
```

O diagnóstico cobre providers de IA, SERP/Search Intelligence e serviços externos configurados. A ação `T` valida em lote somente integrações elegíveis a testes seguros; integrações com `safe_for_bulk=False` permanecem disponíveis para teste individual. O diagnóstico é consultivo e não altera provider routing, AUTO, scoring, fulfillment, reprocessamento ou a URL auditada.


Ações contextuais da preparação:

```text
R. Executar auditoria
U. Executar com/sem IA        # somente quando aplicável ao plano
M. Ver linha de comando
S. Salvar configuração no arquivo [SEM SECRETS]
L. Carregar configuração de AUD [NOVA EXECUÇÃO]
V. Voltar ao início
```

Configurações diretamente relacionadas ao catálogo selecionado continuam editáveis no próprio contexto quando necessárias para completar aquele item. Isso não cria um segundo acesso global de configuração.

Catálogos atuais:

```text
CAT-01 Fundamentos técnicos e descoberta
CAT-02 Acessibilidade
CAT-03 Conteúdo, semântica e dados estruturados
CAT-04 Web Performance
CAT-05 Search & AI Intelligence
CAT-06 Apdex de navegação
CAT-07 Apdex de experiência
CAT-08 Análise profunda e melhorias
CAT-09 Remediações
CAT-10 Segurança passiva
```

`Quality & decisão` é derivado pelo sistema e não é selecionável.

## Submenu de catálogo

Todo item apresenta:

```text
ESTADO
CAPACIDADES / FONTES
CONFIGURAÇÃO EFETIVA
USO DE IA
RESULTADO ESPERADO
CONFIGURAÇÕES RELACIONADAS
PERSISTÊNCIA
AÇÕES
```

IDs canônicos de configurações podem ser usados diretamente para abrir o editor correspondente.

O submenu de catálogo também não oferece atalho para a configuração global de provider/modelo de IA. Quando essa configuração for necessária, a orientação aponta para `INÍCIO > Inteligência Artificial`. A ação `U` permanece local ao plano porque decide somente se o enriquecimento opcional por IA será usado naquela auditoria.

## Configurações: linguagem do usuário

Cada configuração apresenta primeiro o rótulo funcional e mantém o identificador técnico visível como referência secundária.

```text
ID        CONFIGURAÇÃO                                  VALOR EFETIVO          ORIGEM
71865000  Limite de experiência satisfatória            3 s                    [ARQUIVO]
          Variável técnica: RASAI_APDEX_THRESHOLD_SECONDS
```

Regras da apresentação:

- o ID numérico é a referência pública estável;
- o nome amigável é o rótulo principal;
- a variável/chave técnica permanece visível em segundo plano para suporte e rastreabilidade;
- `VALOR EFETIVO` representa o valor que a próxima execução utilizará;
- a origem é mostrada, por exemplo `SESSÃO`, `ARQUIVO`, `WINDOWS/USER`, `WINDOWS/MACHINE` ou `PADRÃO`;
- secrets mostram apenas `CONFIGURADO` ou `NÃO CONFIGURADO`, nunca o conteúdo;
- atributos internos Python não são tratados como identificadores públicos de configuração.

As configurações são agrupadas por contexto funcional. Quando o conjunto é extenso, `P. Pesquisar configuração` aceita rótulo humano, nome técnico, categoria, contexto, finalidade ou palavra-chave. Ao voltar de um resultado, o console preserva a pesquisa e seus resultados.

No editor, **aplicar** e **persistir** são decisões separadas. Para configuração não secreta:

```text
1. Aplicar somente nesta sessão
2. Aplicar nesta sessão e salvar no arquivo de configuração
```

Para segredo:

```text
1. Aplicar somente nesta sessão
2. Aplicar nesta sessão e persistir em Windows/User
```

Segredos nunca são gravados no `rasai-console.ini`. Windows/Machine não é alterado automaticamente.

`T. Detalhes técnicos` continua disponível para tipo, valor bruto não secreto, default, origem, categoria e fonte documental.

## Readiness

- `APTO`: requisitos mínimos conhecidos satisfeitos;
- `APTO COM LIMITAÇÕES`: execução possível com perda conhecida de fonte/enriquecimento opcional;
- `BLOQUEADO`: falta requisito obrigatório do escopo selecionado;
- `NÃO SELECIONADO`: fora do plano.

Recursos não selecionados não bloqueiam a auditoria. Toda alteração relevante recalcula imediatamente a capability e o estado do plano antes de permitir execução.

## IA e custo

O catálogo identifica operações que não usam IA, podem usar IA ou exigem IA. Provider/modelo continuam sob a configuração principal e o orquestrador canônico.

Com apenas consumidores opcionais selecionados, o plano inicia em `Executar sem IA (recomendado)`. A ação `U` permite solicitar o enriquecimento por IA; indisponibilidade do provider é exibida como limitação, sem impedir o processamento determinístico. `CAT-08` torna IA obrigatória para o fechamento integral, mas não remove a possibilidade de executar/materializar a auditoria com `ai_provider=none`. No `CAT-10`, a opção de IA reutiliza o mesmo Improvement Intelligence no domínio `SECURITY`; não existe motor/provider de segurança paralelo.

A seleção AUTO usa o `provider_registry` dinâmico; **não é uma cadeia fixa OpenAI -> DeepSeek -> MiMo**. O catálogo atual também contempla Copilot conforme o contrato do registry. Providers marcados `explicit-only` não entram silenciosamente no AUTO; continuam disponíveis quando selecionados explicitamente conforme sua política canônica.

Providers sem credencial continuam configuráveis; ausência de credencial afeta readiness/execução, não a possibilidade de abrir e editar sua configuração.

A gestão específica de credencial de provider mantém as ações operacionais existentes:

```text
S. Setar/alterar Key na sessão
P. Persistir/remover Key no Windows/User
L. Limpar Key somente da sessão
X. Excluir Key da sessão e do Windows/User
A. Habilitar/desabilitar no AUTO sem apagar a Key
U. Usar este provider nesta auditoria
```

Essas ações são do provider; na listagem geral de configurações o usuário continua vendo rótulo amigável, valor efetivo e origem, e o nome técnico somente em `T. Detalhes técnicos`.

Quando o plano efetivo gera consumo estimável, a tela financeira ocorre antes da execução e apresenta `1. Executar auditoria com IA`, `2. Executar auditoria sem IA`, `A. Ajustar configuração de IA` e `V. Voltar sem executar`. O atalho `A` abre o mesmo gerenciamento canônico de providers/credenciais; ao retornar, a estimativa é recalculada. A escolha `1` ou `2` inicia a AUD e não é seguida de uma segunda confirmação redundante. Executar sem IA vale somente para a AUD corrente e não apaga a configuração de IA da sessão/próxima auditoria. Não há cálculo financeiro duplicado na tela do catálogo.

## Salvar parâmetros

Parâmetros não sensíveis podem ficar somente na sessão ou ser salvos no arquivo de configuração. Secrets permanecem no mecanismo Windows/User e nunca entram no INI.

No Windows, persistência de segredo em escopo de usuário usa `HKEY_CURRENT_USER\Environment`; esse caminho não exige PowerShell ou `.ps1` executado como Administrador. O console não modifica Windows/Machine e Windows/Machine não é administrado automaticamente pelo RASAi.

A seleção dos catálogos pertence à próxima execução. Ela é gravada no snapshot secret-free do AUD, permitindo carregar posteriormente a mesma configuração para uma nova AUD.

## Search

`CAT-05` agrega o objetivo de Search & AI, mas SERP e GSC conservam suas regras próprias. Termos SERP, região, profundidade e device continuam configuráveis; GSC continua dependente de OAuth/property/política/cobertura da URL. A **IA competitiva** é opt-in opcional do CAT-05: exige Comparação de conteúdo ativa e IA principal apta, usa o orquestrador principal e, quando habilitada, participa explicitamente do plano de IA da próxima execução.

## Apdex

`CAT-07` depende de `CAT-06`. Cálculos de Apdex não dependem de IA e selecionar CAT-06/CAT-07 não ativa IA por si só.

`RASAI_APDEX_ACQUISITION_MODE` controla somente a estratégia de aquisição do Synthetic Apdex. Os valores técnicos aceitos são `auto` e `isolated`: `auto` é o default e compartilha somente aquisições comprovadamente compatíveis; `isolated` força aquisições independentes para comparação/troubleshooting. Essa configuração é operacional e **não altera a pontuação** nem o **Método de Pontuação de Prontidão**.

## Análise profunda e remediações

`CAT-08` consome a evidência core necessária à sua finalidade. A IA só é chamada quando esses pré-requisitos estão persistidos e válidos. Sem provider apto, a auditoria continua e CAT-08 permanece pendente para fechamento integral.

`CAT-09` produz ações rastreáveis às evidências. IA pode enriquecer explicações/exemplos, mas não altera scoring determinístico.

## Segurança passiva

`CAT-10` analisa postura de segurança somente com evidências HTTP/browser/runtime já coletadas e fontes externas governadas. Não executa pentest, exploração, fuzzing, brute force, bypass de autenticação ou submissão de formulários.

As configurações relacionadas expõem headers/CSP/CORS, cookies, scripts/recursos, third-party, runtime, OSV, CISA KEV e timeout externo. MDN HTTP Observatory e Lighthouse Best Practices são reutilizados das coletas canônicas; falha de OSV/KEV reduz a cobertura, mas não é convertida em finding do site.

A posição 15 da tela `PREPARAR AUDITORIA` passa a ser CAT-10; `Raiz das auditorias` fica na posição 16.

Contrato técnico: [PASSIVE_SECURITY_CATALOG.md](PASSIVE_SECURITY_CATALOG.md).

## Histórico e configuração de AUD

Carregar configuração de uma AUD cria uma base para **nova execução**; não modifica o AUD de origem. O snapshot preserva a lista `CAT-*` quando disponível.


Quando uma execução física termina com diagnóstico ainda parcial e existe ao menos um requisito obrigatório reprocessável, a tela final da própria sessão exibe:

```text
R. Reprocessar pendências desta auditoria [APTO]
P. Abrir pasta da auditoria
I. Abrir relatório HTML
V. Voltar ao menu
```

A ação `R` reutiliza automaticamente o `Audit ID` recém-gerado e abre o mesmo fluxo seletivo do histórico. O operador não precisa pesquisar nem digitar novamente o identificador.

No RPR, a seleção de itens é solicitada uma única vez. A tela seguinte substitui a anterior, preserva um **RESUMO DAS ESCOLHAS** no topo e apresenta as ações finais `1. Reprocessar ... com IA`, `2. Reprocessar ... sem IA` e `V. Voltar`. Não existe uma segunda confirmação da mesma intenção. Mensagens de entrada inválida aparecem em linha própria; um erro de tela anterior é limpo antes de cada prompt e nunca é reaproveitado como se fosse uma resposta do operador. Durante a execução, sucessos preservados são apresentados separadamente do trabalho executado no `RPR-*`.

## Contratos complementares

- [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [CONSOLE_VISUAL_SEMANTICS.md](CONSOLE_VISUAL_SEMANTICS.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md)
