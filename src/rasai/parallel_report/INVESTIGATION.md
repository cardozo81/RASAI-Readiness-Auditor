# Issue #697 - investigação e decisão

Base: `13aeea0e5fc4ea3f8d5bdc7e7aec7f7f1ec4b6b7` (`origin/main`).
Branch única: `feature/issue-697-report-presentation`.
Início: 2026-11-13T00:14:23-03:00. Worktree inicial limpa.
Issue lida integralmente via GitHub em 13/11/2026. A autorização do operador
permite avançar automaticamente após os quatro gates de isolamento.

## Decisão anterior ao código de produção

O nome sugerido inicialmente recebeu NO-GO: `src/rasai/report_presentation.py`
já existe e fornece `humanize_report_html`, `public_label` e
`fractional_confidence_percentage` ao catálogo, GEO, consolidação e outros
consumidores. Um pacote homônimo tem precedência de importação sobre o módulo.
Uma prova com `PathFinder` em diretório temporário confirmou o sombreamento.
O operador autorizou explicitamente `rasai.parallel_report` nesta sessão,
preservando o diretório de saída `report-presentation/`.

Com essa correção: ISOLAMENTO, READ_ONLY, NO_EXISTING_FILE_CHANGE_REQUIRED e
NO_ENGINE_CHANGE_REQUIRED = PASS; decisão GO. Não há hook, registro de CLI,
importação de produtor, alteração de arquivo existente ou nova dependência.

O fetch genérico encontrou refspec antigo de branch remota removida. A base foi
atualizada com fetch explícito `refs/heads/main:refs/remotes/origin/main` e
`git merge --ff-only origin/main`, sem mudar configuração Git.

## Fontes inspecionadas

Contratos: REPORT_DESIGN_SYSTEM, REPORT_CATALOG_TRUST, REPORT_REMATERIALIZATION,
REPORT_GUIDE, REPORT_PRESENTATION, REPORT_PRESENTATION_CONTRACT,
REPORTING_AI_USAGE, SARI_READINESS_INDEX, LIGHTHOUSE_WEB_QUALITY,
SYNTHETIC_USER_EXPERIENCE_APDEX e SEARCH_INTELLIGENCE_REPORT.

Código: catalog_report_contract/site/presentation, persistence,
scoring_persistence, m18_persistence, m20_persistence, directed_analysis e
search_intelligence/perplexity. Também foram localizados os produtores
improvement_intelligence, m14_persistence e passive_security.

Introspecção física: uma AUD local selada com catálogo, sem WAL/SHM/journal,
contém 101 tabelas. Somente nomes de tabelas/colunas foram expostos durante a
investigação; payloads privados não entram no Git. O inventário completo de
tabelas, colunas, PKs e FKs é produzido pelo leitor; a saída registra colunas
consultadas e destino de cada família. Nenhum schema é criado/migrado.

## Matriz das dez páginas

| Nova página / seção | Fonte persistida e campos centrais | Escopo / cobertura | Páginas canônicas |
|---|---|---|---|
| Painel / identidade e resultados | audits.audit_id/status; audit_targets; scores.value/coverage/consolidation_status; fulfillment | AUD, URL, device; estado original, sem inferir execução por configuração | index; execution-evidence |
| Extração / captura e evidência física | pages.page_id; page_snapshots.snapshot_id/page_id/device/captured_at/*_artifact_ref; evidence.evidence_id/artifact_reference; element_observations.selector/outer_html | snapshot/URL/device; hash calculado não autentica a origem | capture-context; execution-evidence |
| Descoberta / padrões | m24_runs/diagnostics; standards_metric_observations.value/scope/state; standards_service_runs | URL/origin/service; ausência não é conformidade | cat-01 |
| Índices / composição | scores.score_id/dimension/value/coverage; score_contributions.score_id/rule_execution_id/weight/result_factor; rule_executions | dimensão/device; sem recálculo SARI | sari; methodology; metrics |
| Conteúdo / achados e contexto | findings.finding_id/rule_execution_id/evidence_ids; semantic_assessments; semantic_coherence_assessments; content contexts; improvement findings/recommendations | página/snapshot; inferência IA separada de literal | cat-02; cat-03; cat-08; geo-content-review |
| Performance / fontes independentes | web_performance_observations.*_score/*_lab_ms/*_p75_ms/field_scope; lighthouse_execution_profiles; synthetic_apdex_*; synthetic_ux_apdex_* | laboratório/campo/sintético, URL/origin/device/profile, amostra | cat-04; cat-06; cat-07; network |
| Busca e GEO / observações | serp_observations/results; serp_competitive_*; perplexity_search_runs/sources; geo_observation_runs.projection_json | query/mercado/idioma/device/tempo; sem comparação implícita | cat-05; geo; geo-content-review |
| Segurança / evidência passiva | passive_security_*; findings.evidence_ids_json/validation/severity | recurso/página/party, sem probes | cat-10 |
| Plano / ação e validação | directed_analysis_actions.action_id/source_id/validation_steps_json; recommendations; governance; root_cause_*; request_remediation_* | identidade canônica; aprovação não inferida | cat-09; directed-analysis; cat-08 |
| IA/custos / tentativa e proveniência | ai_provider_attempts; content_remediation_attempts; native_usage; ai_tasks/rounds/exchanges; pricing; forecast | tentativa/moeda/finalidade; realizado técnico distinto de invoice | ai-integrations; execution-evidence |

As 21 páginas canônicas estão cobertas na matriz; uma mesma página pode ser
referência de mais de uma visão. Famílias históricas/adicionais não reconhecidas
recebem destino explícito em IA/proveniência e anexo sanitizado, sem descarte
silencioso nem `LIMIT`. O mapa runtime registra todas as famílias encontradas.

## Artefatos e produtores

AUD inspecionada: HTML, JSON, PNG, respostas HTTP, texto, logs e SQLite.
page_snapshots guarda raw/rendered/main-content/structured-data references;
evidence e element_observations ligam arquivo a snapshot/elemento.
Web Performance guarda referências e hashes PageSpeed/CrUX; SERP guarda
raw_evidence_ref/hash; integrações passivas e IA podem guardar sidecars.
Todos os arquivos de origem são inventariados e hashados, incluindo os não
interpretados. Binários não são publicados como conteúdo executável.

AuditWorkspace/persistence e classes ScoringPersistence/M18/M20 inicializam
schema ou escrevem artefatos: proibidos como leitores. O materializador
catalog_report_site instala camadas, materializa governança CAT-09, cria
snapshot e publica arquivos: proibido. Helpers de humanização existentes são
consumidores de apresentação, mas não são necessários: nenhum é importado.
Biblioteca padrão somente, além de Playwright já disponível nos testes.

## Custos

Tentativas generativas e Content Remediation são ledgers distintos. Não
agregar apenas a sessão/provider final: fallback também pode ser faturável.
`observed_cost` prevalece sobre `estimated_cost` por tentativa, inclusive zero.
Moedas não se misturam. Native usage é detalhamento, não consumo adicional.
Perplexity com attempt_id correlacionado não é somado novamente. Run órfão,
identidade duplicada/ausente ou valor sem moeda deixa o total parcial; não
inventar correlação por modelo, horário ou request semelhante. Tokens Search
ausentes permanecem ausentes. Forecast e catálogo são exibidos sem entrar no
realizado. Nenhuma precificação atual é consultada ou recalculada.

## Evidência e crossrefs

Cada registro recebe ID de apresentação determinístico baseado na PK composta;
sem PK, ordinal técnico explícito, sem identidade persistente inventada.
Links bidirecionais usam IDs únicos encontrados como valores completos.
IDs ambíguos não recebem vínculo arbitrário. Não deduplicar ações por título.
Referências físicas são confinadas à AUD, sem symlink/junction/path traversal.
SHA atual identifica bytes, não prova autenticidade. Linha/coluna só são
derivadas de ocorrência literal única; seletor/XPath só são mostrados quando
persistidos. Campos ausentes são N/D ou Parcial com causa.

## Compatibilidade e limites

Tabelas/colunas são introspectadas. Estado desconhecido não vira sucesso;
0 não vira NULL. SQLite abre `mode=ro&immutable=1` com `query_only=ON`, somente
após recusar sidecars ativos, e os hashes são repetidos no fim. `immutable=1`
não é usado para ignorar WAL. Alteração concorrente reprova a geração.

O ZIP aprovado não foi encontrado no workspace. Comparação de conteúdo e
fidelidade visual do protótipo são PENDING_INPUT; não é possível afirmar quais
dados exclusivos do protótipo faltam. SARI 60/80/95 permanece proposta sem
classificar readiness. Não há ganho simulado nem nova aritmética de score.

Paridade automatizada compara registros completos das famílias principais e
custos ao snapshot SQLite dentro do catálogo. Isso não certifica que cada
valor foi renderizado corretamente no HTML histórico; essa comparação visual
e semântica permanece pendente. Sidecars sem schema conhecido permanecem no
inventário físico; não se infere conteúdo ou medição a partir de nome de arquivo.
