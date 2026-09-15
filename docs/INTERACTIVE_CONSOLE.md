# Console interativo

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado.

## Inicialização

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

IDs canônicos de variáveis podem ser usados diretamente para abrir o editor correspondente.

## Readiness

- `APTO`: requisitos mínimos conhecidos satisfeitos;
- `APTO COM LIMITAÇÕES`: execução possível com perda conhecida de fonte/enriquecimento opcional;
- `BLOQUEADO`: falta requisito obrigatório do escopo selecionado;
- `NÃO SELECIONADO`: fora do plano.

Recursos não selecionados não bloqueiam a auditoria.

## IA e custo

O catálogo identifica operações que não usam IA, podem usar IA ou exigem IA. Provider/modelo continuam sob a configuração principal e o orquestrador canônico.

Com apenas consumidores opcionais selecionados, o plano inicia em `Executar sem IA (recomendado)`. A ação `U` permite alternar para `Executar com IA` somente quando a IA principal está configurada/apta. `CAT-08` torna IA obrigatória e remove a possibilidade de execução sem IA.

Quando o plano efetivo gera consumo estimável, o preview/aceite canônico ocorre antes da execução. Não há cálculo financeiro duplicado na tela do catálogo.

## Salvar parâmetros

Parâmetros não sensíveis podem ficar somente na sessão ou ser salvos no arquivo de configuração. Secrets permanecem no mecanismo Windows/User e nunca entram no INI.

A seleção dos catálogos pertence à próxima execução. Ela é gravada no snapshot secret-free do AUD, permitindo carregar posteriormente a mesma configuração para uma nova AUD.

## Search

`CAT-05` agrega o objetivo de Search & AI, mas SERP e GSC conservam suas regras próprias. Termos SERP, região, profundidade e device continuam configuráveis; GSC continua dependente de OAuth/property/política/cobertura da URL.

## Apdex

`CAT-07` depende de `CAT-06`. Cálculos de Apdex não dependem de IA e selecionar CAT-06/CAT-07 não ativa IA por si só.

## Análise profunda e remediações

`CAT-08` consome evidências de catálogos produtores e exige IA principal apta.

`CAT-09` produz ações rastreáveis às evidências. IA pode enriquecer explicações/exemplos, mas não altera scoring determinístico.

## Histórico e configuração de AUD

Carregar configuração de uma AUD cria uma base para **nova execução**; não modifica o AUD de origem. O snapshot preserva a lista `CAT-*` quando disponível.

## Contratos complementares

- [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [CONSOLE_VISUAL_SEMANTICS.md](CONSOLE_VISUAL_SEMANTICS.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md)
