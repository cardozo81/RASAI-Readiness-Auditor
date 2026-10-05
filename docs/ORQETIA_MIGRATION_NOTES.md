# Orqetia migration notes

Este documento registra somente correções do RASAi que representam contrato canônico de orquestração ou fronteira compartilhada com um futuro orquestrador externo. Regras de HTML, CATs, auditoria e apresentação específicas do RASAi não devem ser copiadas para o Orqetia.

## ORQETIA-CARRYOVER-001 — identidade estável de tentativa e exchange

- **Origem RASAi:** issue #200; branch `fix/ai-audit-boundary-correlation`; PR a vincular nesta entrega.
- **Data:** 2026-10-05.
- **Classificação:** `ORCHESTRATION_CANONICAL`.
- **Problema:** `ai_provider_attempts` possuía `attempt_id`, mas `ai_exchange_log` não carregava identidade estável da tentativa. A correlação podia depender de provider/modelo/finalidade e produzir falso “request/response não persistido”.
- **Arquivos/símbolos RASAi de referência:**
  - `src/rasai/m18_ai.py::ProviderAttempt`;
  - `src/rasai/ai_exchange_log.py::AiExchange`;
  - `src/rasai/ai_exchange_log.py::AiExchangeRecorder.bind_latest_attempt`;
  - `src/rasai/ai_exchange_log.py::persist_ai_exchange_log`;
  - `src/rasai/ai_orchestration_unification.py::_attempt`.
- **Contrato corrigido:** uma tentativa de provider possui identidade estável criada uma única vez. O exchange externo pertencente à tentativa recebe a mesma identidade. A identidade explícita prevalece sobre qualquer inferência.
- **Invariantes esperados:**
  1. `attempt_id` não muda entre execução, persistência da tentativa, usage/pricing e exchange telemetry;
  2. sucesso, erro técnico, erro de contrato e fallback continuam gerando tentativa identificável;
  3. nenhum join novo depende exclusivamente de timestamp, proximidade temporal ou texto de `purpose`;
  4. hashes de request são fingerprints auxiliares, não identidade primária;
  5. retries de payload idêntico continuam distintos por `attempt_id`.
- **Comportamento de erro:** se um exchange histórico não possuir identidade explícita, a leitura não falha. Correlação auxiliar por fingerprint só é aceitável quando existir um único candidato exato; ambiguidade deve permanecer não correlacionada, nunca resolvida por adivinhação temporal.
- **Modelo de dados:** `attempt_id` passa a existir de forma intrínseca em `ProviderAttempt` e opcionalmente em `AiExchange`; a tabela `ai_exchange_log` recebe coluna aditiva `attempt_id`.
- **Compatibilidade retroativa:** bancos antigos sem a coluna continuam legíveis. A inicialização adiciona a coluna sem recriar/destruir a tabela; linhas históricas podem permanecer `NULL`.
- **Teste de referência:** `tests/test_ai_audit_boundary_regressions.py` — correlação Directed Analysis, Competitive Intelligence e upgrade de schema legado.
- **Ação no Orqetia:** modelar `attempt_id` como identidade de primeira classe desde o início e propagá-la em request lifecycle, retry/fallback, usage, pricing, diagnostics e exchange log.
- **Não copiar do RASAi:** nomes de CAT, HTML, `report-catalog`, tabelas `directed_analysis_*`, regras de Search Intelligence e qualquer lógica de apresentação.

## ORQETIA-CARRYOVER-002 — governança explícita para execução sem task/round

- **Origem RASAi:** issue #200; branch `fix/ai-audit-boundary-correlation`.
- **Data:** 2026-10-05.
- **Classificação:** `SHARED_CONTRACT_BOUNDARY`.
- **Problema:** uma tentativa da Análise Direcionada era válida, mas persistia `operation=NULL`, `ai_task_id=NULL` e `ai_round_id=NULL`, tornando impossível distinguir “execução taskless por contrato” de “governança perdida”.
- **Arquivos/símbolos RASAi de referência:**
  - `src/rasai/directed_analysis.py` — persistência da tentativa com `operation=DIRECTED_ANALYSIS`;
  - `src/rasai/improvement_intelligence.py::_persist_attempt`.
- **Contrato corrigido:** task/round não devem ser fabricados apenas para satisfazer telemetria. Uma execução sem task/round deve declarar uma `operation` estável e documentar que `ai_task_id`/`ai_round_id` são opcionais naquele contrato.
- **Invariantes esperados:**
  1. `operation` é obrigatória para uma tentativa que não possui task/round;
  2. nulidade de task/round é semântica e documentada, não ambígua;
  3. `attempt_id` continua obrigatório para a correlação da chamada externa;
  4. a ausência de task/round não altera retry, fallback, pricing ou status operacional.
- **Compatibilidade retroativa:** linhas antigas com todos os campos nulos continuam legíveis; não devem ser reinterpretadas automaticamente como uma operação específica.
- **Teste de referência:** `test_directed_analysis_taskless_attempt_correlates_with_exchange`.
- **Ação no Orqetia:** definir no contrato da API a diferença entre `attempt`, `operation` e eventuais conceitos de `task/round`. Não exigir task/round universalmente se o consumidor não possuir esse conceito.
- **Não copiar do RASAi:** a semântica de negócio `DIRECTED_ANALYSIS`, Recommendation Governance, CATs e ações estratégicas.

## ORQETIA-CARRYOVER-003 — integridade de payload persistido na fronteira de apresentação

- **Origem RASAi:** issues #199 e #200; branch `fix/ai-audit-boundary-correlation`.
- **Data:** 2026-10-05.
- **Classificação:** `SHARED_CONTRACT_BOUNDARY`.
- **Problema:** conteúdo persistido de request/response podia ser semanticamente humanizado ao ser apresentado, alterando tokens técnicos que fazem parte da evidência.
- **Arquivos/símbolos RASAi de referência:**
  - `src/rasai/catalog_report_integrations.py::_persisted_payload_text`;
  - `src/rasai/catalog_report_integrations.py::_raw_payload_block`;
  - `src/rasai/ai_exchange_log.py` — sanitização e persistência do exchange.
- **Contrato corrigido:** sanitização de segredo ocorre antes da persistência; depois de persistido, request/response/prompt/schema expostos como evidência técnica devem ser retornados sem reescrita semântica. Camadas consumidoras podem humanizar apenas metadados, labels e estados.
- **Invariantes esperados:**
  1. segredo não é reintroduzido;
  2. payload sanitizado persistido é source of truth da evidência exposta;
  3. token técnico dentro do payload não é traduzido nem substituído;
  4. escaping/serialização de transporte pode ocorrer sem mudar o conteúdo semântico.
- **Teste de referência:** `test_persisted_raw_payload_is_not_semantically_humanized`.
- **Ação no Orqetia:** separar DTO/campos de metadata humanizável dos campos de evidência bruta sanitizada. O Orqetia não deve aplicar localizações, labels ou enum fallback ao corpo bruto.
- **Não copiar do RASAi:** `safe_visible_fallback`, CSS, HTML, labels pt-BR e regras visuais de provider.

## Itens explicitamente RASAI_ONLY

As alterações de provider visual em `catalog_report_integrations.py` e `catalog_report_final_refinements.py` são `RASAI_ONLY`. O Orqetia deve preservar a identidade canônica do provider como dado, mas não deve copiar marcação HTML, classes CSS ou política de humanização do relatório RASAi.
