# Matriz consolidada de gates da candidata

**Decisão: NO-GO para publicação.** PR #675 aberta e pronta para revisão humana, branch exclusiva `stabilization/cons-rpr-reports-release-readiness`. Versão no código: `0.8.0`. Candidata `v0.9.0` não publicada. Esta matriz reconcilia a operação iniciada em `02d2a7fb1a00abe907a5595602dbbab6bcae0603`, em 29/10/2026. Resultados finais de CI, com SHA e run IDs, devem ser conferidos na PR e na issue #674 após o último commit; não é possível um documento conter o hash do próprio commit.

## Estados

Usar somente `PASS`, `PASS_WITH_LIMITATION`, `PARTIAL`, `FAIL`, `BLOCKED` ou `NOT_VERIFIABLE`. O método e a limitação acompanham cada resultado. `PASS` automatizado não significa homologação física. Resultados históricos estão em [STABILIZATION_RELEASE_READINESS.md](STABILIZATION_RELEASE_READINESS.md).

## Gates e evidências

| Gate | Estado na reconciliação | Evidência e método | Limitação e próxima ação | Dependência humana |
| --- | --- | --- | --- | --- |
| CI-BASELINE | FAIL | HEAD inicial: 36 workflows, 34 success e 2 failure; full run 40860226266: 5.647 passed, 2 failed, 29 skipped, 134 subtests | Duas falhas documentais; correção de dois travessões em um título, sem relaxar contrato | Não |
| DOC-CONTRACT | PASS | Correção 96d7dc00775fb4a55551f383148208d08d28fefc: 24 testes focais e gate público local aprovados | Revalidar no último SHA com Public Contract Consistency | Não |
| CI-FINAL | PARTIAL | Matriz de gatilhos e runs deve ser fechada no último SHA | Full RASAi Regression e todos os workflows aplicáveis precisam de success; ausências não são PASS | Não |
| CHANGELOG | PASS_WITH_LIMITATION | [Notas por capacidades](RELEASE_NOTES_DRAFT.md) e inventário integral de 822 entradas, tag pública até baseline inicial | Reconciliação da candidata, não publicação; incluir commits desta operação e revisar qualquer alteração posterior | Revisão editorial final |
| CONS-AUTOMATED | PASS | Regressão local conjunta: 47 passed, 12 subtests, incluindo pacote CONS, RPR, economia e compatibilidade | Fixtures temporárias; confirmar também workflow CONS no SHA final | Não |
| CONS-PHYSICAL | PARTIAL | Operador: CONS-20261029-071709-322 com 2 fontes e hashes 5/5; CONS-20261029-071944-660 com 12 fontes e hashes 7/7; ambos COMPLETE | Pacotes e bancos fonte não disponíveis no Worker; não há comparação controlada com/sem IA nem prova independente antes/depois | Entrega de arquivos e aceite |
| RPR-OFFLINE | PASS | Operador Windows: 1 passed in 0.73s; regressão local novamente aprovada | Workspace temporário real, sem provider; não equivale a retomada histórica | Aceite já obtido |
| WINDOWS-NAVIGATION | PASS | Operador aprovou A: CONS e Voltar; B: histórico e dois retornos; C: cancelar confirmação | Não repetir sem alteração funcional invalidante | Aceite já obtido |
| RPR-PHYSICAL | PARTIAL | Prévia da AUD-741C986F3FDD413DAD0E168934CA0BA4: duas pendências IA, 13 sucessos preservados, seleção e dependências verificadas | Reprocessamento não executado; não usar essa AUD para chamadas pagas | Aceite ou dispensa formal da retomada física |
| ECONOMY-ARITHMETIC | PASS_WITH_LIMITATION | Valores informados: forecast US$ 0,0343468; atribuído US$ 0,144491916; diferença US$ 0,110145116; desvio +320,6852341% | Aritmética dos totais informados; não prova causalidade, ledger ou faturamento | Não |
| ECONOMY-CAUSAL | NOT_VERIFIABLE | AUD-01D61DBA30DD45D19F99401AB927580D não disponível | Necessários audit.db, forecast persistido, tentativas, tokens, pricing efetivo e eventos opcionais | Entrega de evidência; nenhuma nova chamada |
| REPORT-PHYSICAL | NOT_VERIFIABLE | HTML e SQLite das AUDs físicas não disponíveis | Comparar achados, recomendações, catálogos, confiança, denominadores e duplicidades com fontes; não inferir pela fixture | Entrega de arquivos e aceite visual |
| REPORT-SYNTHETIC | PASS_WITH_LIMITATION | Smoke histórico e inspeção documentada de desktop/tablet/mobile/PDF | Ressalva CAT-07: primeira página pouco preenchida; não há defeito sistêmico comprovado; CI final regenera fixtures | Aceite de impressão |
| INSTALL-ISOLATED | PASS_WITH_LIMITATION | [Script autocontido](../scripts/RELEASE_COMPATIBILITY_SMOKE.ps1), [workflow](../.github/workflows/release-compatibility-smoke.yml), Python 3.13 | Workflow 40864404198 aprovado em Windows/Linux no SHA 6bfaf520e0c54dc97074afe628e527fccd00e2a4; instalação base com attestation/GeoIP, sem integrações externas | Não no CI; máquina operacional é separada |
| ROLLBACK-RUNTIME | PASS_WITH_LIMITATION | Dois runtimes isolados, candidata e tag pública fixa; hashes de arquivo sentinela sintético | Não é rollback de bancos nem prova de leitura histórica; workflow 40864404198 aprovado nos dois sistemas; revalidar no SHA final | Não |
| HISTORICAL-COMPATIBILITY | NOT_VERIFIABLE | Ausência de bancos físicos e respectivos hashes anteriores | Cópias consistentes, manifestos e versão de origem exigidos; nunca abrir original para migração | Entrega de arquivos |
| SECURITY-NETWORK | PARTIAL | Workflows de segredos, rede/GeoIP e contratos aplicáveis ao SHA final | Não comprova rota física, licença GeoIP ou segurança universal; não habilitar chamadas tarifadas | Aceite operacional quando aplicável |
| DOC-ISSUE | PARTIAL | Documentação reconciliada, inventário completo e comandos de smoke | #674 permanece aberta até evidência final de CI e validação da PR; links externos indisponíveis não ganham aceite implícito | Revisão da PR |
| RELEASE-AUTHORIZATION | BLOCKED | Sem autorização de merge, versão, tag ou release | Só operador pode autorizar após gates obrigatórios ou dispensas explícitas | Sim |

## Arquivos físicos faltantes e preservação

- Pastas completas dos dois CONS acima, incluindo manifest, `report.html`, `decision-context.json`, `longitudinal-evidence.json`, `execution.json` e arquivos opcionais de IA referenciados.
- Cada `AUD-*/audit.db` fonte identificado nesses manifests, seus sidecars e `report-catalog/`; incluir inventário de hashes anterior à consolidação quando existente. Um hash calculado agora não recupera uma evidência histórica ausente.
- Pasta da AUD econômica, incluindo banco, forecast persistido, registros de tentativas de provider/remediação e snapshots de modelo/preços. Logs devem ser compartilhados com segredos removidos, preservando uma cópia original sob controle do operador.
- Cópia consistente de AUD realmente interrompida e evidências antes/depois, caso esse gate não seja formalmente dispensado. A AUD de prévia com pendências IA não autoriza gasto.

A inspeção deve usar cópias e leituras somente leitura. Nunca executar checkpoints, migrações ou reprocessamento nos originais. Não assumir que hashes dos arquivos derivados provam imutabilidade dos bancos fonte.

## Roteiro humano mínimo

1. Preservar os aceites A/B/C e RPR offline já obtidos. Não repetir por alteração puramente documental.
2. Disponibilizar os pacotes físicos acima; comparar SQLite, manifests e HTML sem executar providers. Aceite: todo indicador e recomendação rastreável, fontes íntegras e divergências classificadas.
3. Para instalação operacional Windows, executar `powershell -ExecutionPolicy Bypass -File scripts/RELEASE_COMPATIBILITY_SMOKE.ps1 -Candidate <SHA-final>` com Python 3.13 no PATH. O script preserva seu diretório temporário e imprime o caminho da evidência. Exit 0 significa apenas os gates executados; verificar NOT_VERIFIABLE no JSON. Exit 1 indica falha. Não instala no checkout do usuário, não apaga dados e não chama o launcher interativo.
4. Reconciliação econômica: somar tentativas únicas por provider/modelo/moeda, separar retries/fallback e remediações opcionais, conferir tokens e preços efetivos, comparar apenas escopo equivalente ao forecast. Aceite: total atribuído explicável; incertezas e ausência de pricing explícitas; não afirmar fatura externa sem documento próprio.
5. Registrar aceite visual e eventual dispensa de gates físicos, com responsável, justificativa e risco. Ausência de resposta não é dispensa. Mesmo com CI verde, merge/tag/release exigem autorização expressa posterior.

## Gate da suíte completa no SHA final

[Full RASAi Regression](../.github/workflows/full-regression.yml) deve executar o contrato público e `pytest -q` com Python 3.13 e Chromium. Seu run e os demais workflows aplicáveis precisam concluir com `success` no SHA exato. `skipped`, `cancelled`, `failure`, `in_progress` ou ausência de execução não são GO. Um commit posterior exige nova certificação. Não confundir todas as definições do repositório com os workflows cujos gatilhos se aplicam a esta PR.

## Cobertura documental e matriz de workflows

O [inventário de workflows](RELEASE_WORKFLOW_MATRIX.tsv) cobre **98 definições** presentes nesta revisão: **37 elegíveis** ao evento `pull_request/synchronize` para `main`, comparando os caminhos alterados da PR; **61 não elegíveis** nesse evento, com motivo individual. Não são 98 workflows executados. Workflows condicionais de infraestrutura externa e opções manuais não são promovidos a PASS pela suíte local. O smoke de arquitetura OCI, por exemplo, requer marcador explícito no commit e não é habilitado neste lote documental.

Verificações locais adicionais: **61 testes** de documentação, branding e versão, linguagem, referências e nomes de arquivos; **51 testes** de economia e GeoIP. Os grupos se sobrepõem à suíte integral e não devem ser somados como testes únicos. Inspeção operacional: launcher, requisitos de Python, extras, CLI, configuração de preços, consentimento de rede e fronteiras SQLite/HTML. Os comandos de versão e ajuda foram executados nos runtimes isolados; exemplos de auditoria externa não foram executados.

Consulta focal de 15 URLs documentais oficiais de preços/modelos em 29/10/2026: 14 páginas acessíveis pelo leitor público; a URL legada de preços Perplexity com `?calc=search` não foi acessível pelo leitor. Isso não comprova indisponibilidade universal e não altera o catálogo de preços nem autoriza nova chamada ao provider. Disponibilidade de página não certifica equivalência de cada tarifa com faturamento. O gate de links externos é PASS_WITH_LIMITATION, limitado a esse recorte.

Os índices README apresentavam SCORE-GEO-004 como vigente. Foram alinhados ao runtime SCORE-GEO-005 e ao documento canônico, sem alteração de scoring, dados ou exemplos históricos.
