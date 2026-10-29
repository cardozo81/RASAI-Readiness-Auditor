# Candidata v0.9.0 - pacote de decisão pré-release

**Estado:** DRAFT / NÃO PUBLICADO. Documento restrito à PR #675 e ao ciclo da issue #674. A versão pública vigente permanece `v0.8.0`; não utilizar este documento como changelog de uma release publicada.

## Escopo da candidata

- Regressões de integridade e reuso do pacote CONS-5, incluindo arquivos obrigatórios e artefatos opcionais de IA simulada.
- Regressões de reprocessamento RPR para idempotência, contadores por tentativa e fechamento seletivo de dependências.
- Cobertura econômica de previsão, custo atribuído, moedas incompatíveis e apresentação de operações opcionais.
- Smoke sintético de relatórios CAT/GEO, confiança numérica da IA, proveniência de métricas e revisão de impressão.
- Sincronização documental incremental da candidata.

Esses itens descrevem a estabilização em desenvolvimento na PR #675, não todas as alterações publicadas desde v0.8.0. Antes de divulgar o changelog, reconciliar o diff completo entre a tag v0.8.0 e o commit final de publicação.

## Evidências históricas e critérios

- Baseline de CI verificada: `c26b75fdbb709a87406471002754b9256603e49e`; 14/14 workflows de PR concluídos com sucesso em 28/10/2026.
- Detalhes e links dos workflows, ressalvas e matriz de aceite: [STABILIZATION_RELEASE_READINESS.md](STABILIZATION_RELEASE_READINESS.md).
- CONS-5: teste sintético aprovado; homologação com fontes físicas, comparação longitudinal e hash das AUDs ainda não comprovada nesta candidata.
- RPR: seleção e prévia econômica em AUD histórica verificadas no console Windows (sem executar chamadas pagas); smoke offline determinístico com motor/persistência reais aprovado no Windows (`tests/test_rpr_offline_acceptance.py`, `1 passed in 0.73s`, informado pelo operador em 29/10/2026). Retomada física de AUD interrompida permanece sem evidência; não equiparar o teste offline à homologação completa.
- IA/pricing: desvio histórico +320,69% reportado, ainda sem reconciliação causal do ledger físico. Não declarar fatura efetiva.
- Relatórios: smoke sintético aprovado, com ressalva de paginação inicial do PDF CAT-07 e sem paridade demonstrada com AUD física.
- Instalação limpa: execução de workflows em Windows/Linux não substitui instalação limpa em ambiente operacional.

## Compatibilidade e configuração

Nenhum bump de versão está autorizado neste estágio; `pyproject.toml` e `src/rasai/__init__.py` permanecem em `0.8.0`. Conservar schemas, contratos de scoring, APDEX, SARI, identidades AUD/RPR/CONS e leitura de evidências históricas. Configuração operacional de preços deve permanecer em `config/ai-pricing.toml`; não alterar dados históricos ou promover preços estimados a custos faturados. Consultar [AI_PRICING_CONFIGURATION.md](AI_PRICING_CONFIGURATION.md) e [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md).

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

**NO-GO para publicação agora.** A baseline de testes é verde, mas a issue #674, os gates físicos e a aprovação humana não estão encerrados. A candidata `v0.9.0` é uma proposta SemVer plausível para incremento pré-1.0, não uma decisão de publicação. PR #675 aberta e pronta para revisão humana; esse estado não autoriza publicação; não criar tag, release, merge ou excluir branch.

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

**Lançamento condicionado:** manter `0.8.0` como versão no código durante o preparo documental. Qualquer bump da candidata exige decisão explícita, reconciliação de changelog e CI no SHA resultante. A ausência de uma AUD física ou ledger não transforma limitação de evidência em bug e não autoriza considerar o requisito homologado.

## Notas de mudanças do escopo da PR

As mudanças verificáveis e as limitações da PR #675 estão reunidas em [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md). Este inventário é restrito ao escopo da PR e não afirma representar todas as mudanças acumuladas desde a release pública `v0.8.0`.

## Certificação final de testes

A candidata exige a execução verde do workflow [Full RASAi Regression](../.github/workflows/full-regression.yml) no SHA final, além de todos os demais workflows aplicáveis. O workflow agora é elegível à PR de estabilização quando os arquivos cobertos forem alterados e continua podendo ser acionado manualmente. O acionamento não equivale a aprovação: conferir conclusão efetiva, testes executados e status de cada job. Consultar [RELEASE_GATE_MATRIX.md](RELEASE_GATE_MATRIX.md) para critérios de GO/NO-GO.

## Estado operacional reconciliado em 29/10/2026

A matriz vigente é [RELEASE_GATE_MATRIX.md](RELEASE_GATE_MATRIX.md). As contagens e SHAs acima são registros históricos, não certificação do HEAD atual. O inventário Git completo desde a tag pública substitui a limitação de 300 arquivos da consulta antiga; consultar [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md) e [inventário](RELEASE_CHANGE_INVENTORY.tsv). Nenhum bump foi aplicado. Os aceites Windows A/B/C e RPR offline permanecem válidos; não repetir sem alteração funcional que os invalide.

O [smoke isolado](../scripts/RELEASE_COMPATIBILITY_SMOKE.ps1) instala a candidata e a baseline em diretórios temporários distintos, verifica CLI, dependências, Chromium offline e contratos sintéticos. Ele não abre AUD histórica nem comprova downgrade de schema. A homologação operacional do computador do usuário e a autorização de publicação são gates distintos.
