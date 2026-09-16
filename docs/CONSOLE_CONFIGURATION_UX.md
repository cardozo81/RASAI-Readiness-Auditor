# Contrato de UX para configuração no console

**Estado:** vigente para o software em desenvolvimento/pré-produção.

O `rasai-console` organiza configuração por **catálogo de auditoria**. Runtime, registries e validadores existentes continuam como fonte de verdade; a UI não redefine scoring, collectors, providers, retries, quarentena, fulfillment ou metodologia.

## Navegação principal

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

O menu `INÍCIO` é o owner dos acessos globais. Subtelas operacionais não duplicam atalhos para Inteligência Artificial, Integrações e serviços, Todas as configurações, Histórico, Consolidados, Ajuda ou Sair.

## Padronização dos submenus

Toda subtela deve apresentar somente ações que atuem sobre o contexto corrente e uma ação explícita de retorno. Acesso global não é repetido em níveis inferiores.

Regras:

- `Q. Sair` existe somente em `INÍCIO`; telas de execução, resultado e reprocessamento usam `V. Voltar`;
- `Todas as configurações`, `Integrações e serviços`, `Inteligência Artificial`, `Ajuda`, `Histórico` e `Relatórios consolidados` são destinos globais e pertencem somente ao menu `INÍCIO`;
- uma subtela de integração pode validar/retestar a integração e ajustar somente suas dependências relacionadas, mas não abrir o catálogo global de configurações;
- uma subtela de catálogo pode editar diretamente uma configuração relacionada pelo ID canônico, mas não oferece acesso paralelo ao menu global;
- uma tela de resultado pode abrir artefatos, reprocessar pendências quando aplicável e voltar ao contexto anterior; sair do programa não é ação local;
- ações indisponíveis não devem ser substituídas por atalhos globais. Quando necessário, a interface informa o caminho `INÍCIO > ...`.

Como referência visual, o teto recomendado é de até quatro ações operacionais visíveis por tela comum. Telas de gestão em lote, como gerenciamento/exclusão de AUDs, podem ter mais comandos porque todos continuam pertencendo ao mesmo contexto operacional.

## Mensagens semânticas, cores e disposição

A camada pública do console usa o mesmo vocabulário em todas as superfícies:

```text
OK         : operação concluída ou alteração aplicada com sucesso
INFO       : contexto útil; nenhuma correção obrigatória foi detectada
ALERTA     : condição que merece atenção, limitação, quota/custo ou consequência de continuar
ERRO       : entrada inválida, falha, bloqueio ou operação que não pôde ser concluída
```

Contrato visual:

- **verde**: sucesso, concluído, apto ou valor explicitamente válido;
- **ciano**: navegação, títulos, informação e contexto operacional;
- **amarelo**: alerta, limitação, configuração pendente, quota/custo ou validação ainda não feita;
- **vermelho**: erro, bloqueio, falha ou condição destrutiva que exige correção/confirmação;
- **dim/neutro**: texto secundário, explicação, default/herança ou condição não aplicável.

Uma mensagem operacional deve responder, quando a informação existir, a três perguntas: **o que aconteceu**, **qual o efeito** e **qual a próxima ação**. Mensagens genéricas como `ação inválida`, `ID/ação inválido` ou `variável inválida` são projetadas para texto amigável que indique o que o operador pode informar naquela tela. Detalhe técnico continua disponível quando necessário, mas não substitui a orientação operacional.

Ações também descrevem seu efeito. Quando uma ação altera armazenamento/persistência, a própria legenda ou a etapa imediatamente seguinte deve deixar claro se afeta **somente a sessão**, o **arquivo de configuração**, **Windows/User**, ou se cria uma **nova AUD** sem alterar a origem. Ações potencialmente destrutivas, como reset e exclusão, continuam exigindo confirmação explícita.

## Preparar auditoria

A tela é organizada em:

```text
ESCOPO
CATÁLOGO DA AUDITORIA
PLANO DA PRÓXIMA AUDITORIA
EXECUÇÃO / ARMAZENAMENTO
AÇÕES
```

Não há Perfil da próxima auditoria nem uma lista paralela `ANÁLISES / RESULTADOS`.

A seção `AÇÕES` desta tela é contextual ao plano corrente:

```text
R. Executar auditoria
U. Usar/não usar IA opcional nesta próxima auditoria   # somente quando aplicável
S. Salvar configurações não sensíveis no arquivo       # secrets não são gravados
L. Carregar configuração de AUD como base              # cria nova execução; não altera a origem
V. Voltar ao início
```

Ação global não deve ser reproduzida aqui. Quando um catálogo depende de configuração global de IA/provider, a tela apenas informa o caminho `INÍCIO > Inteligência Artificial`.

Isso não impede edição contextual de uma configuração diretamente necessária ao catálogo selecionado. Uma variável relacionada ao item pode continuar sendo aberta pelo seu ID canônico sem expor menus globais paralelos.

### Catálogos

A preparação usa os IDs estáveis `CAT-01..CAT-09` definidos em [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md).

Selecionar um catálogo o inclui no plano e abre imediatamente seu submenu. O submenu segue:

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

## Aptidão

Aptidão é contextual ao plano selecionado:

```text
APTO
APTO COM LIMITAÇÕES
BLOQUEADO
NÃO SELECIONADO
```

Uma integração não selecionada não pode bloquear a auditoria. `CONFIGURAR` continua válido em superfícies técnicas de configuração/capacidade, mas o catálogo converte requisito obrigatório pendente em `BLOQUEADO`.

## Identidade pública das configurações

Números curtos são escolhas da tela. IDs numéricos canônicos identificam a mesma configuração independentemente do caminho usado para chegar a ela.

O **nome da variável de ambiente não é identidade pública**. A visualização normal deve privilegiar propósito e efeito:

```text
ID        CONFIGURAÇÃO                                  VALOR EFETIVO          ORIGEM
71865000  Limite de experiência satisfatória            3 s                    [ARQUIVO]
63673900  Amostras por contexto                          1                      [SESSÃO]
```

Contrato global para todas as variáveis:

- cada variável possui um rótulo amigável e funcional;
- o ID numérico permanece estável e é a referência indicada para suporte/documentação;
- o nome técnico (`RASAI_*`, credencial de provider etc.) fica suprimido na navegação normal;
- `VALOR EFETIVO` representa o valor que o runtime receberá após resolver sessão, arquivo, Windows/User e default;
- valores booleanos/enums/unidades devem ser apresentados em linguagem humana quando houver representação inequívoca;
- secrets nunca revelam conteúdo: aparecem somente como `CONFIGURADO` ou `NÃO CONFIGURADO`;
- cor do valor pode comunicar estado: explicitamente configurado, default/herdado, atenção obrigatória ou não aplicável.

A tela de catálogo referencia o owner canônico da configuração; não duplica variáveis.

## Detalhes técnicos

O editor oferece uma ação explícita:

```text
T. Exibir detalhes técnicos desta configuração
```

Somente essa visão avançada apresenta o nome real da variável, além de informações úteis para diagnóstico:

```text
ID público
Variável
Valor bruto (nunca para secrets)
Tipo
Default
Origem efetiva
Categoria
Fonte documental
```

O objetivo é manter detalhes de implementação disponíveis para troubleshooting sem obrigar o operador a compreender nomes de ambiente durante a operação normal.

## Persistência

Após alteração não sensível:

```text
1. aplicar somente nesta sessão
2. aplicar na sessão e salvar no arquivo de configuração
```

Para secrets, o destino persistente é Windows/User e o INI nunca recebe o conteúdo secreto. Limpar o override da sessão não apaga automaticamente arquivo/Windows; restauração ou gerenciamento de persistência possuem ações próprias e explícitas.

O `rasai-console.ini` pode persistir explicitamente:

- configuração pública não sensível materializada em `[environment]`;
- inputs reproduzíveis de Search em `[search_intelligence]`;
- seleção do plano da próxima auditoria em `[audit_catalog].selected`;
- decisão de IA opcional do plano em `[audit_catalog].ai_enabled`;
- demais seções não sensíveis suportadas pelo writer canônico.

A seleção `CAT-*` continua pertencendo ao plano da próxima auditoria. Salvar o INI apenas permite reutilizar explicitamente esse plano em outra sessão; não cria uma política global independente do catálogo.

No início da execução, o plano efetivo é congelado no snapshot secret-free da AUD, incluindo `audit_catalog.version`, `selected`, `ai_enabled` e `items`.

### Atomicidade das edições

O editor canônico aplica alterações de configuração como uma unidade coerente entre ambiente e estado do console:

- o valor é validado antes de ser considerado aplicado;
- contratos entre campos são reconciliados antes da validação final quando o runtime possui regra derivada;
- se a alteração produzir estado inválido, o ambiente e o estado do console retornam ao valor anterior;
- uma edição rejeitada não deve aparecer como sucesso nem ser gravada no INI.

Para Synthetic Navigation Apdex, aumentar `samples_per_context` pode exigir aumento conjunto de `max_attempts_per_context`. O editor usa o mesmo contrato derivado do configurador dedicado: quando o orçamento atual é insuficiente, reconcilia para pelo menos `ceil(1.25 × samples)`. Reduzir manualmente o orçamento de tentativas para uma combinação inválida é rejeitado e revertido.

## Device e Apdex

`Device` permanece `mobile|desktop|both`.

O mix efetivo de Experience Apdex segue:

```text
mobile  -> mobile=100,desktop=0,tablet=0
desktop -> mobile=0,desktop=100,tablet=0
both    -> mobile=60,desktop=40,tablet=0
```

`CAT-07` depende de `CAT-06`; selecionar Experience Apdex inclui Navigation Apdex no plano.

## Search & AI Intelligence

`CAT-05` agrega a intenção do usuário, sem fundir contratos técnicos:

- SERP;
- Google Search Console;
- Visibilidade em IA;
- Observabilidade externa aplicável.

SERP e GSC continuam independentes. GSC obrigatório incompatível pode bloquear o catálogo; GSC opcional não aplicável não deve invalidar SERP apto.

Os inputs de `O QUE PESQUISAR` são execução-scoped durante a edição normal, mas podem ser persistidos explicitamente no INI por `Salvar configuração` e também são congelados no snapshot da AUD quando participam da execução.

## Inteligência Artificial

A IA principal continua global/orquestrada. O catálogo apenas declara onde IA é `NONE`, `OPTIONAL` ou `REQUIRED`.

Quando só existem consumidores opcionais (`CAT-03`/`CAT-09`), o plano usa **Executar sem IA (recomendado)** por padrão. Se a IA principal estiver configurada/apta, o operador pode alternar para **Executar com IA**. `CAT-08` exige IA e não permite o modo sem IA. Os demais catálogos não ativam IA por si só. Nenhum enriquecimento advisory pode alterar evidência/scoring determinístico.

A escolha local `U` altera apenas o plano da próxima auditoria. Configurar provider, modelo, credencial, AUTO ou política global continua pertencendo exclusivamente ao menu `INÍCIO > Inteligência Artificial`.

Quando houver consumo, o fluxo canônico de estimativa/aceite continua executando antes do AUD.

## Tela de configuração

O editor canônico exibe prioritariamente:

- ID público e rótulo amigável;
- finalidade/contexto;
- valor efetivo e origem;
- domínio/formato e exemplo de preenchimento;
- impacto/custo/quota quando relevante;
- ações de definir, limpar override, restaurar, persistir e abrir detalhes técnicos.

Enums, booleanos e listas fechadas devem usar escolha guiada; texto livre somente quando o domínio for realmente aberto.

## Origem de valor

A UI pode indicar:

```text
SESSÃO
ARQUIVO
WINDOWS/USER
WINDOWS/MACHINE
DEFAULT
NÃO CONFIGURADO
```

## Regra de implementação

A última tela não é o local para descobrir dependências básicas. Cada catálogo recalcula readiness enquanto o operador configura. `R. Executar auditoria` permanece bloqueado quando existe pendência obrigatória conhecida.

A padronização final de mensagens e rótulos é exclusivamente de **apresentação**. Ela pode reescrever copy pública como `ERRO/ALERTA/INFO/OK` e tornar a descrição de uma ação mais explícita, mas nunca modifica a tecla aceita, o retorno da ação, a persistência executada, a validação, o core da auditoria ou o contrato dos runtimes.

O contrato de rótulo/valor/origem é de **apresentação**: nomes técnicos continuam sendo as chaves canônicas usadas internamente, portanto não há alteração das regras do core ou do formato aceito pelos runtimes.

Documentos relacionados: [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md), [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md), [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md), [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
