# Continuidade de UX entre configuração e relatórios

**Estado:** contrato de arquitetura de informação para o software ainda não publicado.

## Princípio

A mesma taxonomia deve acompanhar o usuário do pedido ao resultado:

```text
CATÁLOGO
  -> CONFIGURAÇÃO EFETIVA
  -> SNAPSHOT DA AUD
  -> EXECUÇÃO / EVIDÊNCIAS
  -> RELATÓRIOS
```

A implementação atual altera o console e grava a taxonomia no snapshot reutilizável da AUD. A projeção visual completa nos HTMLs é etapa posterior.

## Antes da execução

O console usa `CAT-01..CAT-09`, readiness contextual e parâmetros efetivos. Recursos não selecionados não aparecem como bloqueios globais.

## Depois da execução

Os relatórios devem futuramente conseguir apresentar por catálogo:

- solicitado ou não solicitado;
- configuração realmente aplicada;
- capacidades/fontes esperadas;
- concluído, parcial, falha, não disponível ou não aplicável;
- evidências produzidas;
- operações que usaram IA;
- remediações ligadas às evidências.

O relatório não deve inferir o pedido apenas pela presença de uma feature no software. A referência deve ser o snapshot da AUD.

## Semântica equivalente, não layout idêntico

Console e HTML compartilham IDs, nomes, cores semânticas e subcapacidades, mas usam estados adequados à fase:

| Preparação | Pós-execução |
|---|---|
| `APTO` | `CONCLUÍDO` quando executado com sucesso |
| `APTO COM LIMITAÇÕES` | `PARCIAL` ou `CONCLUÍDO COM LIMITAÇÕES` |
| `BLOQUEADO` | não deveria iniciar execução nesse estado |
| `NÃO SELECIONADO` | `NÃO SOLICITADO` |

## IA

Relatórios devem diferenciar medição determinística de interpretação/advisory por IA. IA pode explicar, correlacionar e sugerir correções, mas não deve recalibrar scoring determinístico sem regra metodológica explícita.

## Evidências

Cada recomendação deve manter rastreabilidade para evidência/origem. A taxonomia do catálogo não substitui IDs técnicos de métricas, regras ou protocolos; ela organiza esses itens na linguagem de produto escolhida pelo operador.

## Consolidação

O consolidado deve usar a mesma taxonomia `CAT-*` para resumir o que foi pedido e o que foi concluído, sem transformar ausência deliberada em falha.

Documentos relacionados: [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md), [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md) e [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md).
