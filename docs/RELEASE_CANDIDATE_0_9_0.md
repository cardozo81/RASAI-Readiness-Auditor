# Candidata v0.9.0 - pacote de decisão pré-release

**Estado:** DRAFT / NÃO PUBLICADO. Documento restrito à PR #675 e ao ciclo da issue #674. A versão pública vigente permanece `v0.8.0`; não utilizar este documento como changelog de uma release publicada.

## Escopo da candidata

- Regressões de integridade e reuso do pacote CONS-5, incluindo arquivos obrigatórios e artefatos opcionais de IA simulada.
- Regressões de reprocessamento RPR para idempotência, contadores por tentativa e fechamento seletivo de dependências.
- Cobertura econômica de previsão, custo atribuído, moedas incompatíveis e apresentação de operações opcionais.
- Smoke sintético de relatórios CAT/GEO, confiança numérica da IA, proveniência de métricas e revisão de impressão.
- Sincronização documental incremental da candidata.

Esses itens descrevem a estabilização em desenvolvimento na PR #675, não todas as alterações publicadas desde v0.8.0. Antes de divulgar o changelog, reconciliar o diff completo entre a tag v0.8.0 e o commit final de publicação.

## Evidências e critérios

- Baseline de CI verificada: `887ae218e71cfead81583c66652978d2f302aa67`; 12/12 workflows de PR concluídos com sucesso em 28/10/2026.
- Detalhes e links dos workflows, ressalvas e matriz de aceite: [STABILIZATION_RELEASE_READINESS.md](STABILIZATION_RELEASE_READINESS.md).
- CONS-5: teste sintético aprovado; homologação com fontes físicas, comparação longitudinal e hash das AUDs ainda não comprovada nesta candidata.
- RPR: regressões aprovadas; smoke físico de retomada seletiva permanece pendente de evidência.
- IA/pricing: desvio histórico +320,69% reportado, ainda sem reconciliação causal do ledger físico. Não declarar fatura efetiva.
- Relatórios: smoke sintético aprovado, com ressalva de paginação inicial do PDF CAT-07 e sem paridade demonstrada com AUD física.
- Instalação limpa: execução de workflows em Windows/Linux não substitui instalação limpa em ambiente operacional.

## Compatibilidade e configuração

Nenhum bump de versão está autorizado neste estágio; `pyproject.toml` e `src/rasai/__init__.py` permanecem em `0.8.0`. Conservar schemas, contratos de scoring, APDEX, SARI, identidades AUD/RPR/CONS e leitura de evidências históricas. Configuração operacional de preços deve permanecer em `config/ai-pricing.toml`; não alterar dados históricos ou promover preços estimados a custos faturados. Consultar [AI_PRICING_CONFIGURATION.md](AI_PRICING_CONFIGURATION.md) e [AUDIT_REPROCESSING.md](AUDIT_REPROCESSING.md).

## Checklist pré-publicação

| Gate | Estado atual | Aceite exigido |
| --- | --- | --- |
| CI no SHA anterior de estabilização | PASS | Reexecutar no SHA final da candidata |
| Regressões CONS-5/RPR | PASS | Preservar baseline verde |
| Homologação física CONS/RPR | NOT_VERIFIABLE | Evidências ou ressalva formal aprovada |
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

**NO-GO para publicação agora.** A baseline de testes é verde, mas a issue #674, os gates físicos e a aprovação humana não estão encerrados. A candidata `v0.9.0` é uma proposta SemVer plausível para incremento pré-1.0, não uma decisão de publicação. Manter PR #675 em Draft; não criar tag, release, merge ou excluir branch.
