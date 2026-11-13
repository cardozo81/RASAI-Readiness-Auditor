# Aceitação da análise editorial contextual

Matriz versionada `contextual-editorial-acceptance-v1`, vinculada à #690.
Baseline reconciliada: `main@1b020ef162222eb87a33f273d9453c8efb02bb18`
(PRs #691, #693, #694 e #695 integradas). As provas novas usam fixtures
sintéticas; não representam leitura ou novo aceite de uma AUD real.

## Matriz requisito → evidência → comportamento → teste → estado

COMPROVADO significa contrato demonstrável offline, sem significar verdade
comercial ou autorização paga. IMPLEMENTED e TESTED_OFFLINE descrevem código
e ensaio; NOT_AUTHORIZED, N/D e REQUIRES_HUMAN_GO conservam gates externos.
Os casos novos abaixo ficam no único `tests/test_contextual_ai_contract.py`.

| Requisito #690 | Evidência / reuso | Baseline AI=none e resultado permitido | Caso de teste | Estado / limite |
|---|---|---|---|---|
| A/C0: title/H1, navegação, CTA, social e repetição | Hash/ID/posição v1; overlays v2/v3; fila reversa existente | Segmento title/H1 equivalente não cria tarefa; divergência condicional; menu não vira FAQ | `test_c0_measures_conditional_contracts_without_inflating_opportunities`; `test_contextual_content.py` | COMPROVADO offline; inspeção editorial real PARCIAL |
| A/C0: FAQ presente ou tardia | Mesmo snapshot, controle e painel; fallback raw explícito | Alvo não observado = N/D; não prova ausência no site, indexação ou visita de crawler | `test_contextual_faq_aria.py`; `test_c0_hash_mismatch_and_raw_fallback_are_nd` | COMPROVADO offline; interação real N/D |
| A/C0: documento e alegação comercial/YMYL | Referência candidata/heading observado, nunca corpo autenticado | Revisão de suporte/aplicabilidade exige fonte autorizada e humano | `test_contextual_reverse_review.py`; parametrizações C0 | COMPROVADO contrato; verdade/vigência N/D |
| C0: metodologia reproduzível | Inventário SHA-256 + fila reversa + disposições v2 | Conta candidatos, não acionáveis, N/D e verificações condicionais qualificadas; fixture limpa termina com 0 | `test_c0_rejects_historical_false_positives_without_erasing_them`; oito cenários C0 | IMPLEMENTED / TESTED_OFFLINE; sem percentual arbitrário |
| C0.2: ganho real da IA | Nenhum par real autorizado e comparável fornecido neste ciclo | AI_INCREMENTAL_QUALITY=N/D; mocks avaliam contrato/abstenção | Retornos de `evaluate_editorial` / `validate_response` | N/D / REQUIRES_HUMAN_GO futuro |
| C1: finalidade e consentimento | contextual-editorial-ai-v1; fingerprint imutável; inspeção AUD/página/device/snapshot | none DISABLED; requested NOT_AUTHORIZED, mesmo com chave/persona/registro coincidente | `test_c1_no_scope_inspection_can_authorize_live_execution` | IMPLEMENTED / TESTED_OFFLINE; concessão/persistência de consentimento NÃO implementada |
| C2: uma invocação | AiExecutionPolicy.max_provider_calls no orquestrador existente | Default None preservado; limite inclui candidatos/ciclos, partial/transient/terminal | `test_c2_one_invocation_across_two_candidates_and_all_cycles`; `test_ai_canonical_orchestration.py` | COMPROVADO no callback; não prova retries internos ou tokens no wire |
| C2: preço/moeda/tokens/saldo | ai_cost_policy.resolve_price sob instante/condições | Recusa desconhecido, AUTO, excesso, moeda incompatível e saldo inválido; nunca libera transporte | `test_c2_diagnostics_never_turn_a_forecast_into_permission`; `test_c2_unknown_canonical_price_is_not_zero`; testes canônicos de pricing/telemetria | TESTED_OFFLINE negativo; hard stop monetário real NÃO implementado |
| C3: reserva/concorrência/replay | SQLite isolado de fixtures, PK por tarefa; PENDING_UNCERTAIN pré-tentativa simulada | Um vencedor; falha de persistência impede reserva; timeout/replay não liberam slot | `test_c3_atomic_offline_reservation_precedes_simulated_invocation_and_blocks_replay`; `test_c3_concurrent_first_reservation_has_one_winner` | COMPROVADO no ensaio; não é reserva financeira |
| C3: allowlist/injeção/privacidade | Fatia mínima; IDs da própria tarefa, fonte/hash/posição | Dados hostis em campo separado; saída aceita enums/referências, sem prosa livre/parecer | `test_c3_provider_invented_contradictory_or_extra_fields_are_rejected`; `test_c3_truncation_and_injection_remain_untrusted_data_not_instructions` | COMPROVADO validação local; comportamento de LLM real N/D |
| C3: AUD fechada | _inventory, mode=ro&immutable=1 e publicação externa existentes | Nenhuma escrita em AUD/db/score/reports/manifesto; WAL/SHM/journal recusados pelo leitor canônico | `test_c4_opt_in_companion_keeps_original_scores_files_and_default_html`; `test_contextual_advisory.py`; `test_contextual_report_integration.py` | COMPROVADO em fixture; AUD real não acessada |
| D/C4: pt-BR | Painel optativo na rota existente geo-content-review.html, só contagens | Default preserva bytes/contrato; demais páginas idênticas; sem CAT/página/score novo | `test_c4_opt_in_companion_keeps_original_scores_files_and_default_html`; `test_c4_cli_evaluation_is_opt_in_and_console_has_no_literals` | IMPLEMENTED / TESTED_OFFLINE; aceite visual humano REQUIRES_HUMAN_GO |
| B: Search | Ledger/query/proveniência da PR #695 | Filtros coincidentes = REQUEST_FILTERS_MATCH_ONLY; contexto NOT_COMPARABLE | `test_contextual_search.py`; `test_perplexity_search_intelligence.py` | COMPROVADO negativo; B positivo N/D |

## C0: método e reprodução

`contextual-editorial-evaluation-v1` avalia seis dimensões: evidência física
permitida com hash íntegro; afirmação observada ou explicitamente N/D;
materialidade revisável; ação e validação humana; ausência de promoção a
score/verdade/ranking/autenticidade; privacidade da projeção.
O input confiável é a projeção dos leitores canônicos junto com inventário
físico, nunca JSON arbitrário do provider. O hash não autentica a origem nem
o conteúdo comercial da fonte.

Contagens: historical_candidates, historical_non_actionable, historical_nd,
verification_candidates, qualified_conditional_verifications, verification_nd,
capture_coverage_nd, physical_scope_nd e qualified_opportunities. A última
permanece zero: o método qualifica verificações, não demonstra melhorias.
Cobertura e suficiência são dimensões distintas, sem denominador de confiança.
Mocks não demonstram ganho incremental de modelo; C0.2 requer piloto real
autorizado e comparável.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_contextual_ai_contract.py tests/test_ai_canonical_orchestration.py
```

No companheiro externo já autorizado, `--evaluate-editorial` de
`python -m rasai.contextual_advisory` acrescenta contadores em evidence.json
e um painel na página de análise reversa. Não é default, não altera o
verificador anterior nem habilita provider. Exige fonte terminal e nova saída
privada segundo o contrato existente. Nenhuma AUD real é necessária para os
testes; não publicar texto capturado.

## C1/C3: contrato offline implementado

`contextual_ai_contract.prepare_input` liga audit_id/page_id/device/snapshot_id,
source_ref/source_sha256, ocorrência/heading, instante e escopo.
evidence_snapshot_id fica null sem vínculo canônico comprovado; não cria versão
na AUD histórica. task_id, allowed_evidence_ids e input_fingerprint delimitam
JSON imutável de uma captura. `offline_prompt` reutiliza CONTENT_REMEDIATION
de fábrica, com versão e instrução para tratar evidência como dados hostis.
Persona, modelo, feature flag e chave global não são consentimento.
Importar o contrato e executar C0 não carrega configuração comercial; o catálogo
canônico só é resolvido dentro do preflight econômico, ainda bloqueado.

Limites locais: 256 capturas, 512 tarefas, 16 referências por tarefa herdadas
da projeção, 32 evidências por input, excertos de 240 caracteres, input até
24.000 bytes, resposta até 16.000 bytes e oito sugestões. Omissões,
truncamento e redação são registrados. URLs/emails/segredos reconhecidos
são omitidos/redigidos no input; outros dados de negócio podem ser privados.
Redação não substitui consentimento/controle de acesso. Sem leitura de PDF,
envio de corpus, retrieval ou novo processamento de HTML.

`output_schema()` normaliza saída estrita. `validate_response` recusa campos
extras, JSON duplicado, IDs inventados, troca de tarefa, fingerprint divergente,
score, HTML e parecer regulatório. Só aceita verificações preexistentes com
ação enum, LOCAL_REVIEW, REQUIRES_HUMAN_VALIDATION e limitações fixas.
Não publica prosa do provider nem prova qualidade factual de LLM.

`inspect_consent` verifica estruturalmente propósito/escopo/identidade,
ator, instante/expiração, provider/modelo, consentimento de texto e limites.
Não verifica autenticidade/RBAC nem grava concessão. Mesmo
EXPLICIT_SCOPE_MATCH_ONLY termina NOT_AUTHORIZED no execution_gate.
Não existe CLI/feature flag/callback ligando esse contrato a transporte.
`ai_availability` conserva exatamente seu comportamento público anterior.

## C2: limite real deste ciclo

max_provider_calls=1 impede segunda **invocação canônica**, inclusive após
partial/transient. Não é isoladamente barreira monetária. O adapter inspecionado
`search_intelligence/competitive_ai.py::_request_payload` não contém teto
contextual de saída de 1.200 tokens nem contagem exata prévia de input.
8.000/1.200 é parâmetro de ensaio, nunca aprovação comercial. Estimativa de
caracteres, max_cycles, preço e forecast não bastam.

Runtime pago contextual: **NO-GO / NOT_AUTHORIZED**, por faltar:

- Concessão específica autenticada/persistida com limites/RBAC.
- Adapter canônico com teto no wire, tokenização do envelope completo e
  interpretação comprovada de reasoning/cache/billability.
- Preço vigente exato e reserva monetária durável, atômica/idempotente antes
  do transporte; reconciliação conservadora de PENDING_UNCERTAIN.
- Telemetria canônica por tentativa no derivado autorizado, sem escrever na
  AUD selada, separando tokens estimados/observados, regra/versão, moeda,
  custo conhecido/UNPRICED e erro sanitizado.

`offline_cost_preflight` reutiliza pricing só para recusas. Preço encontrado
nunca libera execução; não calcula máximo de fatura, não reserva dinheiro,
não consulta tarifa online nem declara tarifa vigente homologada.
`OfflineReplayLedger` aceita só SQLite isolado de fixtures: reserva **simulada
de slot**, não saldo. Pendente/ambíguo bloqueia repetição; schema AUD é recusado
antes de inicialização. Nenhum ledger novo na AUD ou motor de transporte.

Zero chamadas reais implica custo externo incremental real zero neste ciclo.
Preço/consumo de chamada futura ficam N/D/UNPRICED, sem conversão para USD 0.
Callbacks contam invocações simuladas, nunca chamadas comerciais.
Git/GitHub administrativo utiliza rede separadamente.

## B: matriz por atributo após PR #695

Inspeção de código/persistência com fixtures, sem AUD real ou consulta ativa.
Não foi necessário alterar algoritmo nem buscar documentação externa para
inventar suporte positivo.

| Atributo | Prova SERP | Prova Perplexity Search | Decisão |
|---|---|---|---|
| AUD/run/observação | audit_id/run_id/observation_id | audit_id/run_id | Mesma AUD obrigatória; valores em AUD real N/D neste ciclo |
| Query/atribuição | query/query_origin | query_json; query explícita em source_metadata_json quando presente | Multiquery sem atribuição = N/D; não replicar fontes |
| País/idioma solicitados | country/language da observação | Scope JSON tipado ligado ao corpo/hash em novas execuções | REQUEST_FILTERS_MATCH_ONLY quando iguais; jamais COMPARABLE |
| País/idioma efetivos equivalentes | Não atestam o outro serviço | Sem atestado efetivo no contrato inspecionado | N/D |
| Região | region | Sem equivalência efetiva comprovada | N/D |
| Device | device | Não atestado por Search | N/D; bloqueia B positivo |
| Período | collected_at UTC | started_at/finished_at UTC | Janela 24h só descritiva, sem prova de atualidade/equivalência |
| Intenção | Query/URL não provam intenção editorial | Sem vínculo físico à intenção local | N/D |
| Observação SERP | OBSERVED_API/OBSERVED e raw | Resultados de pesquisa próprios | Fontes distintas; sem causalidade |
| Proveniência de link | serp_results por observação; URL exata | sources por run; atribuição explícita quando disponível | Host, URL e citação são distintos |
| Integridade | Prova própria da observação | Filtros + query reconstruíveis e conferidos com digest | Hash quebrado = SCOPE_UNVERIFIABLE |
| Execução anterior sem scope | Fonte preservada | Sem tabela/linha do contrato novo | LEGACY_SCOPE_NOT_PERSISTED; sem backfill |
| Citação generativa | Não inferida de SERP | results[] não é resposta generativa observada | N/D |

Proposta formal de produto: manter B positivo e C0.2/IA ativa pendentes na #690;
alternativamente, responsável pode aprovar redução de escopo para correlação
descritiva/contratos offline. Nenhuma opção transforma N/D em PASS ou autoriza
fechamento automático.

## Gate humano consolidado

Revisar diff, testes/CI do HEAD exato e painel sintético; aprovar ou recusar
merge da única PR DRAFT. #690 continua OPEN/PARCIAL. Aceite editorial/visual
e eventual piloto real exigem decisão humana; merge não consente despesa.
Não há GO comercial solicitado neste ciclo.
