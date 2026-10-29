# Matriz consolidada de gates da candidata

> **REGISTRO HISTÓRICO PRÉ-PUBLICAÇÃO (29/10/2026):** a linha `NO-GO` e os estados da tabela abaixo descrevem o momento anterior à integração da PR #676 e ao lançamento. Não representam o status da release pública atual.

## Encerramento pós-publicação verificado - 29/10/2026

- [Release estável `v0.9.0`](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v0.9.0): publicada, `draft=false`, `prerelease=false`, `immutable=true` (ID `428194689`).
- Tag anotada `v0.9.0` -> commit `5da8e6247094c20dcdbe770474ac31e7f93383b2`. Verificação `gh release verify v0.9.0` aprovada no ambiente do operador.
- PR #676: 16/16 workflows e 18/18 jobs aprovados no HEAD de preparo, com 5.649 testes aprovados, 29 ignorados e 134 subtestes aprovados; instalação isolada Windows/Linux aprovada.
- `main@5da8e6247094c20dcdbe770474ac31e7f93383b2`: 10/10 workflows de `push` aprovados. As ressalvas `PASS_WITH_LIMITATION` da homologação física da PR #675 permanecem nos limites documentados.
- Decisão de publicação: **GO efetivado** mediante autorização expressa do operador. A `v0.8.0` é release histórica; a `v0.9.0` deixou de ser candidata não publicada.

**Decisão: NO-GO para publicação da candidata.** A PR #675 foi integrada em `main@810cc076052df93f1d18c6807c18e63b225d9473`, sua branch excluída e a issue #674 encerrada. A release pública ainda é `v0.8.0`; o pacote na branch `release/prepare-v0.9.0` identifica `0.9.0` sem tag/publicação. Esta matriz reconcilia a operação iniciada em `02d2a7fb1a00abe907a5595602dbbab6bcae0603`, com atualização em 29/10/2026. Resultados de CI só valem para o SHA efetivamente executado; o HEAD desta candidata exige nova certificação.

## Estados

O histórico técnico da PR #675 foi aceito com limitações. Os estados `PASS_WITH_LIMITATION` documentam o universo realmente validado; não tornam automaticamente íntegra qualquer auditoria ou release futuro. O checklist canônico para o novo pacote está em [RELEASE_PUBLICATION_CHECKLIST.md](RELEASE_PUBLICATION_CHECKLIST.md).

Usar somente `PASS`, `PASS_WITH_LIMITATION`, `PARTIAL`, `FAIL`, `BLOCKED` ou `NOT_VERIFIABLE`. O método e a limitação acompanham cada resultado. `PASS` automatizado não significa homologação física. Resultados históricos estão em [STABILIZATION_RELEASE_READINESS.md](STABILIZATION_RELEASE_READINESS.md).

## Gates e evidências

| Gate | Estado na reconciliação | Evidência e método | Limitação e próxima ação | Dependência humana |
| --- | --- | --- | --- | --- |
| CI-BASELINE | FAIL | HEAD inicial: 36 workflows, 34 success e 2 failure; full run 40860226266: 5.647 passed, 2 failed, 29 skipped, 134 subtests | Duas falhas documentais; correção de dois travessões em um título, sem relaxar contrato | Não |
| DOC-CONTRACT | PASS | Correção 96d7dc00775fb4a55551f383148208d08d28fefc: 24 testes focais e gate público local aprovados | Revalidar no último SHA com Public Contract Consistency | Não |
| CI-FINAL | PARTIAL | No HEAD `b72ca79253327ea1d7a58f95be9a9d72591cb2f4` da PR #675: 37/37 workflows e 46/46 jobs success, 5.649 passed, 29 skipped, 134 subtests. Pós-merge `main@810cc076052df93f1d18c6807c18e63b225d9473`: 18/18 workflows de push success | A candidata `0.9.0` possui novo SHA; verificar todos os workflows de PR e regressão integral antes de promover a PASS no próprio HEAD | Não |
| CHANGELOG | PARTIAL | [Notas](RELEASE_NOTES_DRAFT.md), [inventário de 822 caminhos](RELEASE_CHANGE_INVENTORY.tsv) na baseline 02d2a7 e [delta de 22 caminhos](RELEASE_CHANGE_DELTA_V0_9_0.tsv) até a main integrada | Os 22 caminhos do delta podem sobrepor-se aos 822; conferir a candidata final e revisar notas antes de publicar | Revisão editorial final |
| CONS-AUTOMATED | PASS | Regressão local conjunta: 47 passed, 12 subtests, incluindo pacote CONS, RPR, economia e compatibilidade | Fixtures temporárias; confirmar também workflow CONS no SHA final | Não |
| CONS-PHYSICAL | PASS_WITH_LIMITATION | Dois CONS: 12/12 artefatos íntegros; 14/14 hashes de bancos fonte e 14/14 SARI conferidos; 437/437 cópias estáveis no suplemento | Fontes são históricas e sem hash independente pré-consolidação; conjuntos 2 vs 12 AUDs não são experimento controlado de IA | Ressalvas aceitas pelo operador |
| RPR-OFFLINE | PASS | Operador Windows: 1 passed in 0.73s; regressão local novamente aprovada | Workspace temporário real, sem provider; não equivale a retomada histórica | Aceite já obtido |
| WINDOWS-NAVIGATION | PASS | Operador aprovou A: CONS e Voltar; B: histórico e dois retornos; C: cancelar confirmação | Não repetir sem alteração funcional invalidante | Aceite já obtido |
| RPR-PHYSICAL | PASS_WITH_LIMITATION | AUD-E970C05B3B274CA8A6CED4BB80E693B5 interrompida: RPR-49D1B894D5DB45AFAE6E51F5D941BA81 SUCCESS; PASSIVE_SECURITY recuperado 1/1; SQLite íntegro; 0 sucessos preexistentes alterados | Recuperação seletiva apenas, AUD continua PARTIAL_RETRYABLE com 9 pendências; sem ledger externo ou prova independente de custo IA zero | Aceite técnico com ressalvas comunicado pelo operador |
| ECONOMY-ARITHMETIC | PASS_WITH_LIMITATION | Valores informados: forecast US$ 0,0343468; atribuído US$ 0,144491916; diferença US$ 0,110145116; desvio +320,6852341% | Aritmética dos totais informados; não prova causalidade, ledger ou faturamento | Não |
| ECONOMY-CAUSAL | PASS_WITH_LIMITATION | Ledger da AUD-01D61DBA30DD45D19F99401AB927580D reconciliado: 8 tentativas IA + 1 remediação = USD 0.144491916; previsão USD 0.0343468; diferença de USD 0.110145116 | Operações independentes respondem por 88,52% do custo atribuído; comparação de escopos não homogêneos, sem fatura/observed_cost externo; risco metodológico aceito | Ressalva aceita pelo operador |
| REPORT-PHYSICAL | PASS_WITH_LIMITATION | 14/14 SQLite íntegros, 322/322 arquivos dos catálogos e 73/73 dependências presentes conferidas; 280 HTML e 15.329 links relativos examinados sem destino interno inexistente | Não equivale a auditoria semântica exaustiva; arquivos antigos podem não conter melhorias posteriores. Aceite de risco residual da inspeção histórica | Ressalvas aceitas pelo operador |
| REPORT-SYNTHETIC | PASS_WITH_LIMITATION | Smoke sintético preservado; impressão física de 14 CAT-07 históricos em Chromium: 14 PDFs, 114 páginas, 0 páginas sem texto e 0 overflow A4 identificado | Primeira página ocupou 28,8%-35,9% da altura; estética aceita com ressalva, sem alegar comprovação pessoal de inspeção visual pelo operador nem atribuir o HTML antigo ao HEAD novo | Recomendação de aceite acatada pelo operador |
| INSTALL-ISOLATED | PASS_WITH_LIMITATION | [Script autocontido](../scripts/RELEASE_COMPATIBILITY_SMOKE.ps1), [workflow](../.github/workflows/release-compatibility-smoke.yml), Python 3.13 | Workflow 40864404198 aprovado em Windows/Linux no SHA 6bfaf520e0c54dc97074afe628e527fccd00e2a4; instalação base com attestation/GeoIP, sem integrações externas | Não no CI; máquina operacional é separada |
| ROLLBACK-RUNTIME | PASS_WITH_LIMITATION | Dois runtimes isolados, candidata e tag pública fixa; hashes de arquivo sentinela sintético | Não é rollback de bancos nem prova de leitura histórica; workflow 40864404198 aprovado nos dois sistemas; revalidar no SHA final | Não |
| HISTORICAL-COMPATIBILITY | PASS_WITH_LIMITATION | 14/14 bancos e snapshots com integrity_check OK e 0 violações FK; schemas iguais; 11/14 paridades de linhas completas; 3 diferenças de fulfillment/timestamps classificadas | Hashes independentes anteriores não existem neste pacote; preservação histórica não é certificada retroativamente; risco residual aceito | Ressalva aceita pelo operador |
| SECURITY-NETWORK | PARTIAL | Workflows de segredos, rede/GeoIP e contratos aplicáveis ao SHA final | Não comprova rota física, licença GeoIP ou segurança universal; não habilitar chamadas tarifadas | Aceite operacional quando aplicável |
| DOC-ISSUE | PASS | Documentação e matriz da PR #675 reconciliadas; issue #674 encerrada depois do merge; contratos SCORE-GEO-005 vigente e 004 histórico distinguidos | Este novo ciclo de preparação conserva documentação de release separada e exige revisão do changelog final | Revisão editorial da candidata |
| RELEASE-AUTHORIZATION | BLOCKED | Autorização humana da PR #675 limitou-se ao merge; branch nova de preparação não integrada; sem tag `v0.9.0` ou GitHub Release | Primeiro revisão de CI/nota e autorização específica do merge da nova PR; em outro ato autorizar tag, release imutável e eventual distribuição | Sim |

## Arquivos físicos recebidos e preservação

- CONS: 12 artefatos dos manifestos, inclusive HTML de relatório, mais fontes SQLite das 14 referências, inspecionadas em cópia somente leitura.
- Catálogos históricos: 322 arquivos e 73 dependências presentes, com controle de SHA, SQLite e HTML; 14 PDFs CAT-07 gerados em cópias para avaliação de impressão.
- Economia: banco e ledger da AUD econômica recebidos, custos por tentativa e preços reconstruídos; não foram recebidas faturas externas.
- RPR: `before.json`, `after.json` e `comparison.json` da AUD descartável, com tentativa `RPR-*` material; não se reprocessaram AUDs históricas.
- Não há inventário independente de hash dos bancos anterior à primeira consolidação. O aceite com limitação não substitui essa prova temporal inexistente.

A inspeção deve usar cópias e leituras somente leitura. Nunca executar checkpoints, migrações ou reprocessamento nos originais. Não assumir que hashes dos arquivos derivados provam imutabilidade dos bancos fonte.

## Roteiro humano mínimo

1. Preservar os aceites A/B/C e RPR offline já obtidos. Não repetir por alteração puramente documental.
2. Pacotes físicos conferidos em cópias; não repetir a coleta nem regenerar AUDs/CONS históricos sem evidência de mudança invalidante. Manter a classificação de diferenças por versão de geração, contrato persistido e status `STALE` independente.
3. Para instalação operacional Windows, executar `powershell -ExecutionPolicy Bypass -File scripts/RELEASE_COMPATIBILITY_SMOKE.ps1 -Candidate <SHA-final>` com Python 3.13 no PATH. O script preserva seu diretório temporário e imprime o caminho da evidência. Exit 0 significa apenas os gates executados; verificar NOT_VERIFIABLE no JSON. Exit 1 indica falha. Não instala no checkout do usuário, não apaga dados e não chama o launcher interativo.
4. Ledger econômico interno conciliado; preservar limitação da comparação com forecast por divergência de escopos e ausência de invoice externa. Não solicitar execução paga para comprovar uma estimativa.
5. Aceite com ressalvas do operador registrado em 29/10/2026; preservar a limitação estética CAT-07 histórico e o resultado seletivo RPR sem presumir inspeção visual individual nem invoice. A revisão da PR e a autorização de merge, bump, tag ou release são atos posteriores e expressos.

## Gate da suíte completa no SHA final

[Full RASAi Regression](../.github/workflows/full-regression.yml) deve executar o contrato público e `pytest -q` com Python 3.13 e Chromium. Seu run e os demais workflows aplicáveis precisam concluir com `success` no SHA exato. `skipped`, `cancelled`, `failure`, `in_progress` ou ausência de execução não são GO. Um commit posterior exige nova certificação. Não confundir todas as definições do repositório com os workflows cujos gatilhos se aplicam a esta PR.

## Cobertura documental e matriz de workflows

O [inventário de workflows](RELEASE_WORKFLOW_MATRIX.tsv) cobre **98 definições** presentes nesta revisão: **37 elegíveis** ao evento `pull_request/synchronize` para `main`, comparando os caminhos alterados da PR; **61 não elegíveis** nesse evento, com motivo individual. Não são 98 workflows executados. Workflows condicionais de infraestrutura externa e opções manuais não são promovidos a PASS pela suíte local. O smoke de arquitetura OCI, por exemplo, requer marcador explícito no commit e não é habilitado neste lote documental.

Verificações locais adicionais: **61 testes** de documentação, branding e versão, linguagem, referências e nomes de arquivos; **51 testes** de economia e GeoIP. Os grupos se sobrepõem à suíte integral e não devem ser somados como testes únicos. Inspeção operacional: launcher, requisitos de Python, extras, CLI, configuração de preços, consentimento de rede e fronteiras SQLite/HTML. Os comandos de versão e ajuda foram executados nos runtimes isolados; exemplos de auditoria externa não foram executados.

Consulta focal de 15 URLs documentais oficiais de preços/modelos em 29/10/2026: 14 páginas acessíveis pelo leitor público; a URL legada de preços Perplexity com `?calc=search` não foi acessível pelo leitor. Isso não comprova indisponibilidade universal e não altera o catálogo de preços nem autoriza nova chamada ao provider. Disponibilidade de página não certifica equivalência de cada tarifa com faturamento. O gate de links externos é PASS_WITH_LIMITATION, limitado a esse recorte.

Os índices README haviam sido alinhados ao runtime SCORE-GEO-005, mas o corpo de guias e apresentações ainda continha referências prospectivas a SCORE-GEO-004. Esta reconciliação consolida 005 para novas AUDs e 004 para replay histórico, sem alteração de scoring, dados ou exemplos históricos.
