# Semântica visual do console interativo

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado.

Cor é reforço semântico; texto continua obrigatório.

## Cores

| Cor | Uso canônico |
|---|---|
| verde | `APTO`, sucesso, habilitado/configurado |
| vermelho | `BLOQUEADO`, erro determinístico, indisponibilidade crítica |
| amarelo | `APTO COM LIMITAÇÕES`, quota, condição transitória ou atenção |
| ciano/azul | estrutura, contexto, navegação |
| cinza/dim | `NÃO SELECIONADO`, `OFF`, default, opcional e texto secundário |

Exposição financeira deve ser rotulada explicitamente (`CUSTO EXTERNO`, estimativa, quota) e nunca depender apenas da cor.

## Preparar auditoria

A organização visual vigente é:

```text
[ ESCOPO ]
[ CATÁLOGO DA AUDITORIA ]
[ PLANO DA PRÓXIMA AUDITORIA ]
[ EXECUÇÃO / ARMAZENAMENTO ]
[ AÇÕES ]
```

Cada linha de catálogo mantém simultaneamente seleção e readiness:

```text
[X] CAT-04 Web Performance          [APTO]
[ ] CAT-05 Search & AI Intelligence [NÃO SELECIONADO]
[X] CAT-08 Análise profunda         [BLOQUEADO]
```

No submenu, a mesma identidade `CAT-*` aparece no breadcrumb e no bloco `ESTADO`.

## Estados

- `APTO`: verde;
- `APTO COM LIMITAÇÕES`: amarelo;
- `BLOQUEADO`: vermelho;
- `NÃO SELECIONADO`: neutro/dim.

Integrações não selecionadas não devem produzir destaque vermelho no plano global.

## IA e custo

A UI separa:

- readiness técnico;
- uso de IA (`NONE|OPTIONAL|REQUIRED`);
- modo efetivo da próxima execução (`SEM IA`, `COM IA`, `OBRIGATÓRIA`);
- exposição de custo/quota.

Quando IA é apenas opcional, `SEM IA (RECOMENDADO)` é o estado inicial. Custo não é erro. A confirmação financeira/operacional continua no preview canônico antes da execução quando IA estiver efetivamente ativa.

## Acessibilidade

A interface deve permanecer compreensível em terminal sem ANSI, `NO_COLOR`, logs e capturas de texto. Todo significado de cor precisa ter rótulo textual equivalente.

## Correspondência futura com HTML

Relatórios podem usar componentes visuais diferentes, mas devem preservar identidade `CAT-*`, terminologia e semântica de status adequadas à fase de execução.
