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

Uma integração não selecionada não pode bloquear a auditoria. `CONFIGURAR` continua válido em superfícies técnicas de variável/capacidade, mas o catálogo converte requisito obrigatório pendente em `BLOQUEADO`.

## IDs de configuração

Números curtos são escolhas da tela. IDs numéricos canônicos identificam a mesma variável independentemente do caminho usado para chegar a ela.

A tela de catálogo referencia o owner canônico da configuração; não duplica variáveis.

## Persistência

Após alteração não sensível:

```text
1. manter somente nesta sessão
2. manter na sessão e salvar no arquivo de configuração
```

Secrets permanecem fora do INI e usam o destino Windows/User já existente.

A seleção `CAT-*` é execução-scoped e é registrada no snapshot secret-free da AUD para reutilização e futura projeção em relatórios.

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

## Tela de variável

O editor canônico continua exibindo:

- finalidade/owner/contexto;
- valor efetivo e origem;
- tipo/domínio/default;
- impacto/custo/quota quando relevante;
- ações de definir, limpar override, restaurar e persistir.

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

Documentos relacionados: [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md), [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md), [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md), [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
