# Apresentação de estados nos relatórios HTML

Os relatórios HTML do RASAi são projeções humanas dos dados persistidos. A camada de apresentação pode substituir valores internos por rótulos legíveis sem alterar o valor armazenado, o scoring, a comparabilidade ou a evidência.

## Regra

Valores internos usados como mensagem principal devem ser apresentados de forma legível ao analista.

Exemplos:

| Valor persistido | Apresentação HTML |
|---|---|
| `UNAVAILABLE` | Indisponível |
| `NOT_CONFIGURED` | Não configurado |
| `CONSOLIDATED` | Consolidado |
| `NOT_CONSOLIDATED` | Não consolidado |
| `HIGH` | Alta |
| `REGRESSED` | Regrediu |
| `PARTIAL_OVERLAP` | Sobreposição parcial |
| `NOT_OBSERVED` | Não observado |
| `P1` | Alta (P1) |
| `SEMANTIC_STRUCTURE` | Estrutura semântica |
| `EVIDENCE_TRUST` | Confiança da evidência |

A tradução ocorre apenas quando o valor aparece isolado como conteúdo principal de tabela, badge ou métrica. O valor persistido no banco permanece inalterado.

## O que permanece técnico

Identificadores necessários para diagnóstico e rastreabilidade não são substituídos. A camada humana apresenta primeiro o conceito de negócio e mantém o ID técnico como detalhe secundário. Exemplos:

- `BR-GEO-*` como ID técnico de **Regra de Avaliação de Prontidão**;
- `SCORE-GEO-004` como contrato técnico do **Método de Pontuação de Prontidão**, versão pública **001**;
- `SARI-001` como ID técnico do **Search & AI Readiness Index - Índice de Prontidão Search & IA**, versão pública **001**;
- códigos HTTP;
- IDs oficiais do Lighthouse;
- `error_code` e `reason_code` em detalhes técnicos;
- SHA, Audit ID e outros identificadores;
- JSON e conteúdo dentro de blocos `code` ou `pre`.

Quando um código técnico também precisar de explicação humana, a explicação deve ser exibida como texto principal e o código deve permanecer como detalhe de rastreabilidade. O segmento `GEO` de IDs como `BR-GEO-*` e `SCORE-GEO-004` não é expandido na camada humana; **GEO - Generative Engine Optimization - Otimização para Mecanismos Generativos** é usado somente quando essa disciplina for explicitamente o assunto.

## Escopo

A normalização canônica é aplicada ao mini-site de cada auditoria. Relatórios standalone de Monitoring, Change Impact, Quality e Fix Verification também aplicam a mesma política na geração.

A camada é exclusivamente de apresentação. Ela não altera:

- `audit.db` ou `observability.db`;
- enums e estados persistidos;
- SARI-001;
- SCORE-GEO-004;
- Coverage, Confidence ou Consolidation;
- regras de release gate;
- comparabilidade entre auditorias.
