# Semântica visual do console interativo

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado; este documento descreve somente a UI atual.

## Objetivo

Cor no console é um reforço semântico. Nenhuma informação pode depender exclusivamente da cor: o texto (`APTO`, `ON`, `INDISPONÍVEL`, `CUSTO EXTERNO`, etc.) continua obrigatório.

A tela `INÍCIO > PREPARAR AUDITORIA` preserva a mesma semântica visual das superfícies detalhadas. A reorganização do menu não pode remover os badges ANSI já calculados pelo console.

## Contrato de cores

| Cor | Uso canônico |
|---|---|
| verde | habilitado, `ON`, `APTO`, `READY`, sucesso, configuração definida |
| vermelho | erro, bloqueio, indisponibilidade e exposição financeira direta de IA que exige atenção |
| amarelo | atenção, quota, limite, volume/carga relevante, condição transitória |
| ciano/azul | estrutura, contexto, informação e navegação técnica |
| cinza/dim | default, `OFF`, opcional, ausência deliberada e texto secundário |

O vermelho em custo de IA **não significa erro**. Ele sinaliza exposição financeira externa direta e deve aparecer acompanhado de texto explícito como:

```text
[CUSTO EXTERNO]
[CUSTO IA ADICIONAL]
```

Assim, erro e custo podem compartilhar cor de atenção alta, mas nunca compartilham o mesmo rótulo textual.

## Preparar auditoria

A tela canônica mantém:

```text
número = configuração
letra  = ação/navegação
título = agrupamento
```

Os títulos das seções usam ciano/azul com destaque:

```text
[ ESCOPO ]
[ INTELIGÊNCIA ARTIFICIAL ]
[ WEB PERFORMANCE ]
[ SEARCH INTELLIGENCE ]
[ ARMAZENAMENTO / EXECUÇÃO ]
[ PERFIL DA PRÓXIMA EXECUÇÃO ]
[ AÇÕES ]
```

Os valores e badges continuam vindo da superfície funcional original. A camada de layout apenas renumera/reagrupa linhas; ela não recalcula estados nem substitui cores.

Exemplos:

```text
6. IA : deepseek [APTO] [CUSTO EXTERNO]
7. Remediações IA : conteúdo=ON [CUSTO IA ADICIONAL]
9. Web Performance : ON [QUOTA EXTERNA]
```

Sem ANSI/terminal compatível, os textos permanecem legíveis e completos:

```text
[APTO]
[CUSTO EXTERNO]
[QUOTA EXTERNA]
```

## Regra técnica para recomposição de tela

Qualquer captura intermediária usada para reorganizar o dashboard deve preservar a capacidade TTY do `stdout` real. Caso contrário, `supports_color()` entende a captura como saída não interativa e remove ANSI antes da renderização final.

O contrato atual usa um buffer de captura que delega `isatty()` ao terminal real. Isso permite que os helpers existentes continuem sendo a única fonte de semântica de cor.

## Custos e consumo

Badges canônicos na preparação:

- IA ativa: vermelho, `[CUSTO EXTERNO]`;
- remediação IA ativa: vermelho, `[CUSTO IA ADICIONAL]`;
- PageSpeed/CrUX/Web Performance: amarelo, `[QUOTA EXTERNA]`;
- `both`/volume elevado: amarelo, `[VOLUME↑]`;
- limites de volume: ciano ou amarelo conforme impacto;
- IA `none`: dim, `[SEM CUSTO IA]`.

A classificação global de exposição (`NENHUM`, `BAIXO`, `MÉDIO`, `ALTO`, `EXCESSIVO`) continua usando `cost_color()` e não substitui os badges específicos de cada parâmetro.

## Erros e bloqueios

Erros exibidos no cabeçalho permanecem vermelhos e em destaque. Estados como `INDISPONÍVEL`, `BLOCKED`, `FAILED`, `ERROR` ou quarentena também usam vermelho.

Falha temporária, rate limit ou condição inconclusiva usam amarelo quando não há evidência suficiente para afirmar erro determinístico.

## Acessibilidade

A cor é redundante por projeto. A UI deve continuar compreensível em:

- terminal sem suporte ANSI;
- `NO_COLOR`;
- logs/capturas de texto;
- leitores que não distinguem cor.

Por isso os rótulos textuais e a organização por seção são obrigatórios.

## Testes

A suíte deve verificar pelo menos:

1. o buffer canônico preserva a capacidade TTY do `stdout` real;
2. sequências ANSI já presentes nos valores sobrevivem à recomposição do menu;
3. os textos dos badges continuam presentes quando cor é desabilitada;
4. a organização números/letras/seções permanece independente da cor.
