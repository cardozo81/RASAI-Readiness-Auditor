# Contrato de UX para configuração no console

**Estado:** vigente para o software ainda não publicado.

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
T. Detalhes técnicos
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
1. manter somente nesta sessão
2. manter na sessão e salvar no arquivo de configuração
```

Secrets permanecem fora do INI e usam o destino Windows/User já existente.

A seleção `CAT-*` é execution-scoped e é registrada no snapshot secret-free da AUD para reutilização e futura projeção em relatórios.

## Device e Apdex

`Device` permanece `mobile|desktop|both`.

O mix herdado de Experience Apdex continua:

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

## Inteligência Artificial

A IA principal continua global/orquestrada. O catálogo apenas declara onde IA é `NONE`, `OPTIONAL` ou `REQUIRED`.

Quando só existem consumidores opcionais (`CAT-03`/`CAT-09`), o plano usa **Executar sem IA (recomendado)** por padrão. Se a IA principal estiver configurada/apta, o operador pode alternar para **Executar com IA**. `CAT-08` exige IA e não permite o modo sem IA. Os demais catálogos não ativam IA por si só. Nenhum enriquecimento advisory pode alterar evidência/scoring determinístico.

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

O contrato de rótulo/valor/origem é de **apresentação**: nomes técnicos continuam sendo as chaves canônicas usadas internamente, portanto não há alteração das regras do core ou do formato aceito pelos runtimes.

Documentos relacionados: [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md), [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md), [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md), [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
