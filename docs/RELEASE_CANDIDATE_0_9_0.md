# Candidata v0.9.0 - pacote de decisão pré-release

> **REGISTRO HISTÓRICO PRÉ-PUBLICAÇÃO:** a [release `v0.9.0`](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v0.9.0) foi publicada em 29/10/2026, `immutable=true`, sobre `5da8e6247094c20dcdbe770474ac31e7f93383b2`. As declarações `DRAFT`, `NO-GO`, branch de preparação e CI pendente abaixo descrevem decisões anteriores à publicação e são preservadas para rastreabilidade, não como status atual.

**Estado:** PREPARAÇÃO / NÃO PUBLICADO. A PR #675 foi integrada e a issue #674 encerrada. A release pública vigente permanece `v0.8.0`; o pacote da branch exclusiva `release/prepare-v0.9.0` foi atualizado para `0.9.0` somente como candidata. Este documento preserva a cronologia histórica do ciclo #675 e não representa uma release publicada.

## Atualização de homologação física e decisão de aceite - 29/10/2026

**Nota posterior ao merge:** o operador autorizou a integração da PR #675, concluída em `main@810cc076052df93f1d18c6807c18e63b225d9473`; a branch anterior foi excluída e #674 encerrada. A certificação da PR foi 37/37 workflows, 46/46 jobs e 5.649 testes aprovados; a `main` recebeu 18/18 workflows `push` com sucesso. O bump `0.9.0` está isolado na nova branch e exige **nova certificação específica**, seguida de autorização para seu merge e, separadamente, publicação. Leia [RELEASE_PUBLICATION_CHECKLIST.md](RELEASE_PUBLICATION_CHECKLIST.md) e [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md).

Esta seção registra a conclusão técnica posterior ao checklist histórico abaixo; não implica merge, bump ou publicação. Evidências e ressalvas encontram-se em [RELEASE_GATE_MATRIX.md](RELEASE_GATE_MATRIX.md) e nos comentários de aceite da [issue #674](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/674).

- CI certificada no HEAD anterior `ff587677ac2b0c7a3e20372d0790886914b9b1b1`: 37/37 workflows e 46/46 checks, 5.649 testes aprovados; após o commit estritamente documental, conferir os checks aplicáveis ao novo SHA sem atribuir a ele resultados antigos.
- CONS físico: 12/12 artefatos de dois CONS e 14/14 fontes/SARI conferidos, com ressalvas de séries não controladas e ausência de hashes preexistentes independentes.
- RPR físico: `RPR-49D1B894D5DB45AFAE6E51F5D941BA81` recuperou `PASSIVE_SECURITY` (1/1) numa AUD descartável interrompida, preservando sucessos e integridade SQLite; a AUD original continua parcial. Resultado `PASS_WITH_LIMITATION` para a trajetória seletiva.
- Economia: ledger interno reconciliado exatamente em USD 0.144491916; projeção USD 0.0343468 não inclui escopos adicionais homogêneos e não há invoice externa. Aceite com ressalvas.
- Relatórios: 322/322 catálogos, 280 HTML, 14 PDFs CAT-07/114 páginas inspecionadas tecnicamente; limitação de primeira página pouco aproveitada aceita como ressalva estética, sem afirmar inspeção visual pessoal do operador.
- Proveniência temporal: relatórios de AUD/CONS históricos podem ter sido gerados por código anterior às melhorias atuais. Diferenciar data/contrato de observação, materialização HTML e geração CONS; ausência retroativa de recurso não constitui regressão. `STALE` é estado de coerência independente da antiguidade do arquivo.
- `SCORE-GEO-005` vigente para novas AUDs; `SCORE-GEO-004` preservado para replay histórico. Não converter scores, bases ou relatórios antigos retroativamente.

**Decisão:** GO técnico com ressalvas aceitas pelo operador; **NO-GO para publicação até CI aplicável no HEAD final, revisão editorial e autorização expressa posterior de integração e versão**. O aceite de ressalvas não significa teste não executado `PASS`.

## Escopo da candidata

- Regressões de integridade e reuso do pacote CONS-5, incluindo arquivos obrigatórios e artefatos opcionais de IA simulada.
- Regressões de reprocessamento RPR para idempotência, contadores por tentativa e fechamento seletivo de dependências.
- Cobertura econômica de previsão, custo atribuído, moedas incompatíveis e apresentação de operações opcionais.
- Smoke sintético de relatórios CAT/GEO, confiança numérica da IA, proveniência de métricas e revisão de impressão.
- Sincronização documental incremental da candidata.

Esses itens descrevem a estabilização em desenvolvimento na PR #675, não todas as alterações publicadas desde v0.8.0. Antes de divulgar o changelog, reconciliar o diff completo entre a tag v0.8.0 e o commit final de publicação.

## Evidências históricas e critérios

Os itens abaixo registram o estágio anterior à homologação física e não substituem a atualização de 29/10/2026 acima.

- Baseline de CI verificada: `c26b75fdbb709a87406471002754b9256603e49e`; 14/14 workflows de PR concluídos com sucesso em 28/10/2026.
- Detalhes e links dos workflows, ressalvas e matriz de aceite: [STABILIZATION_RELEASE_READINESS.md](STABILIZATION_RELEASE_READINESS.md).
- CONS-5: teste sintético aprovado; homologação com fontes físicas, comparação longitudinal e hash das AUDs ainda não comprovada nesta candidata.
- RPR: seleção e prévia econômica em AUD histórica verificadas no console Windows (sem executar chamadas pagas); smoke offline determinístico com motor/persistência reais aprovado no Windows (`tests/test_rpr_offline_acceptance.py`, `1 passed in 0.73s`, informado pelo operador em 29/10/2026). Retomada física de AUD interrompida permanece sem evidência; não equiparar o teste offline à homologação completa.
- IA/pricing: desvio histórico +320,69% reportado, ainda sem reconciliação causal do ledger físico. Não declarar fatura efetiva.
- Relatórios: smoke sintético aprovado, com ressalva de paginação inicial do PDF CAT-07 e sem paridade demonstrada com AUD física.
- Instalação limpa: execução de workflows em Windows/Linux não substitui instalação limpa em ambiente operacional.

## Compatibilidade e configuração

O bump de preparação `0.9.0` foi autorizado neste ciclo e aplicado apenas na branch `release/prepare-v0.9.0`: `pyproject.toml` e `src/rasai/__init__.py` devem permanecer coerentes; `main` continua `0.8.0` até autorização de integração da nova PR. Conservar schemas, contratos de scoring, APDEX, SARI, identidades AUD/RPR/CONS e leitura de evidências históricas. Configuração operacional de preços deve permanecer em `config/ai-pricing.toml`; não alterar dados históricos ou promover preços estimados a custos faturados. Consultar [AI_PRICING_CONFIGURATION.md](AI_PRICING_CONFIGURATION.md) e [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md).

## Checklist pré-publicação registrado antes do fechamento autônomo

| Gate | Estado atual | Aceite exigido |
| --- | --- | --- |
| CI no SHA anterior de estabilização | PASS | Reexecutar no SHA final da candidata |
| Regressões CONS-5/RPR | PASS | Preservar baseline verde |
| Homologação física CONS/RPR | PARTIAL | CONS físico e RPR offline apresentados; faltam integridade histórica das fontes e recuperação física de AUD interrompida ou ressalva formal aprovada |
| Reconciliação histórica de IA | NOT_VERIFIABLE | Ledger físico e análise causal, se mandatórios |
| Relatórios e impressão | PASS_WITH_LIMITATION | Avaliação de ressalvas e paridade conforme critério de aceite |
| Documentação #674 | PARTIAL | Links, termos, comandos e contratos revisados; CI verde |
| Instalação limpa Windows/Linux | NOT_VERIFIABLE | Execução e evidência operacional |
| Aprovação humana de merge/release | PENDING | Autorização expressa |

## Instalação, atualização e rollback

**Windows:** atualizar código somente depois da integração autorizada. Executar o procedimento de instalação do [README](../README.md), verificar a venv e o lançamento do console, revisar variáveis e a configuração local; rodar smoke sem provedores tarifados e preservar relatórios anteriores.

**Linux:** validar instalação do pacote e execução dos testes determinísticos no ambiente alvo. O sucesso do runner Linux é apenas evidência de CI, não de paridade integral de operação.

**Rollback:** guardar commit/tag `v0.8.0`, backup da configuração do operador e cópias imutáveis de evidências `AUD-*`; reverter a versão de código sem regravar o `audit.db`. Verificar incompatibilidades de artefatos produzidos por versões posteriores antes de lê-los com um runtime antigo. Não executar downgrade destrutivo.

## Decisão técnica

**NO-GO para publicação agora.** A PR #675 foi integrada e seus gates físicos foram aprovados com limitações; a issue #674 foi encerrada. A candidata `v0.9.0` está em branch exclusiva, aguardando CI de release, revisão editorial e autorização expressa para integrar essa branch. Não criar tag, GitHub Release nem publicar pacote sem aprovação posterior distinta.

## Consulta histórica da versão - limite da API

Comparação GitHub `v0.8.0...stabilization/cons-rpr-reports-release-readiness` em 28/10/2026: **1.411 commits à frente**. A API de comparação retornou uma lista de **300 arquivos**, sujeita ao limite de paginação; portanto, ela não prova o inventário integral de arquivos modificados. **Não** utilizar a enumeração parcial como changelog completo, nem atribuir as 1.411 alterações exclusivamente à PR #675.

A candidata inclui um subconjunto de estabilização detalhado neste documento. O changelog público entre `v0.8.0` e a versão futura exige classificação e deduplicação do histórico real, separação de mudanças funcionais, documentação, testes e infra, e reconciliação com a tag exata de publicação. Gate de changelog final: **PARTIAL**.

## Conferência operacional direcionada

| Frente | Fonte verificada | Resultado | Limite |
| --- | --- | --- | --- |
| Instalação Windows | `README.md`, `docs/INSTALLATION.md`, `abrir-rasai-console.cmd` | Documentação e launcher indicam inicialização pela raiz via `abrir-rasai-console.cmd`; fallback com Python 3.13, venv, editable install e Playwright Chromium | Leitura de código e instruções, não instalação limpa executada |
| Dependências opcionais | `docs/INSTALLATION.md` e launcher | Há tratamento explícito para extras definidos em `pyproject.toml` e verificação de dependências | Não atesta instalação em máquina nova |
| Rede e GeoIP | `docs/ENVIRONMENT_VARIABLES.md` e `README.md` | Sondagem ativa exige autorização e hostname exato; GeoIP local é opcional, sem inferir coordenadas quando indisponível | Não atesta conectividade, licença MaxMind ou rota física |
| Artefatos | `docs/OUTPUTS_AND_ARTIFACTS.md` | Contrato persiste em `audits/<AUD-ID>/audit.db` e `report-catalog/`, sem usar HTML como fonte de verdade | Sem mutação ou comparação com AUD física |

Os testes automatizados de documentação conferem links Markdown internos e contratos textuais cobertos pelo workflow `Public Contract Consistency`. Esta revisão **não** executou todos os links externos, nem uma instalação limpa Windows/Linux. Nenhum defeito funcional foi comprovado nesta inspeção.

## Registro histórico de subgates e trilha de execução

A [matriz consolidada de gates](RELEASE_GATE_MATRIX.md) é a fonte resumida de estados, evidências, limitações e próximos testes da candidata. A baseline inicial desta consolidação é `4b20e485eaa55b7e24348574c9f4831f8ff032c3` com 14/14 workflows de PR aprovados. Nenhuma nova execução deve ser presumida aprovada após atualização da branch.

O diff verificado da PR #675 afeta 20 caminhos: três workflows, dez documentos, uma projeção de apresentação de custos de IA e seis arquivos de testes. Esta lista descreve apenas esta PR, não a evolução integral acumulada desde `v0.8.0`. A comparação ampla de versões indicou 1.416 commits à frente no momento da consulta, com resposta de arquivos limitada; não afirmar completude do inventário com base nesse recorte.

**Lançamento condicionado:** o bump `0.9.0` foi autorizado na branch de preparo, mas sua integração/publicação ainda depende de CI, revisão de changelog e autorização expressa posterior. A ausência de uma AUD física ou ledger não transforma limitação de evidência em bug e não autoriza considerar o requisito homologado.

## Notas de mudanças do escopo da PR

As mudanças verificáveis e as limitações da PR #675 estão reunidas em [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md). Este inventário é restrito ao escopo da PR e não afirma representar todas as mudanças acumuladas desde a release pública `v0.8.0`.

## Certificação final de testes

A candidata exige a execução verde do workflow [Full RASAi Regression](../.github/workflows/full-regression.yml) no SHA final, além de todos os demais workflows aplicáveis. O workflow agora é elegível à PR de estabilização quando os arquivos cobertos forem alterados e continua podendo ser acionado manualmente. O acionamento não equivale a aprovação: conferir conclusão efetiva, testes executados e status de cada job. Consultar [RELEASE_GATE_MATRIX.md](RELEASE_GATE_MATRIX.md) para critérios de GO/NO-GO.

## Estado operacional reconciliado em 29/10/2026

A matriz vigente é [RELEASE_GATE_MATRIX.md](RELEASE_GATE_MATRIX.md). As contagens e SHAs acima são registros históricos, não certificação do HEAD atual. O inventário Git completo desde a tag pública substitui a limitação de 300 arquivos da consulta antiga; consultar [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md) e [inventário](RELEASE_CHANGE_INVENTORY.tsv). O bump `0.9.0` foi aplicado somente na branch de preparo após a integração da PR #675. Os aceites Windows A/B/C e o RPR físico seletivo permanecem válidos; não repetir sem alteração funcional que os invalide.

O [smoke isolado](../scripts/RELEASE_COMPATIBILITY_SMOKE.ps1) instala a candidata e a baseline em diretórios temporários distintos, verifica CLI, dependências, Chromium offline e contratos sintéticos. Ele não abre AUD histórica nem comprova downgrade de schema. A homologação operacional do computador do usuário e a autorização de publicação são gates distintos.
