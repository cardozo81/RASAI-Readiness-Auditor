# Escopo implementado — coerência semântica e confiança do report

Este documento registra o fechamento do escopo desenvolvido na branch `feature/semantic-property-coherence`.

## Console e configuração

- seis campos de perfil semântico da propriedade adicionados ao catálogo canônico;
- sete campos editoriais/YMYL/E-E-A-T contextual preservados;
- grupos separados em contexto da propriedade, contexto editorial e risco/confiança;
- remediação deixa de ser responsabilidade funcional do CAT-03;
- valores não secretos seguem o writer canônico do `rasai-console.ini`;
- `auto` é válido e não representa pendência;
- testes pontuais cobrem persistência/reload e agrupamento do console.

## Core semântico

- `PropertySemanticProfile` separado de `ContentAnalysisContext`;
- snapshot por AUD;
- corpus semântico precisa estar `READY` antes da primeira chamada de IA;
- coerência page-level `SC-P*`;
- sinais normalizados da propriedade;
- agregação cross-page determinística;
- interpretação AUTO persistida como inferência não canônica/non-scoring;
- uso do roteamento, tentativas, exchange log, pricing e telemetria globais existentes.

## SaaS/control plane

- perfil semântico persistente por Property em entidade própria;
- API de leitura/atualização;
- revisão/isolamento de tenant conforme store/control plane;
- campos participam do contrato durável `AUDIT`;
- perfil da Property fornece defaults e override explícito do job tem precedência;
- job materializa os valores efetivos antes do worker.

## CAT-03

- mantém diagnóstico/evidência, não plano de correção;
- contexto declarado, inferência AUTO, assessments BR-GEO, coerência por página e cross-page ficam separados;
- detalhes técnicos de provider/tokens/custo permanecem em IA e integrações.

## CAT-05

- contrato `SOURCE-STATE-001`;
- SERP, AI Overview, Competitive Intelligence, GSC, Clarity e Common Crawl projetados separadamente;
- configured/requested/enabled/executed/data_available/freshness não são fundidos;
- SERP live anterior à AUD sem proveniência de reuso bloqueia publicação;
- reuso exige AUD/origem/motivo persistidos.

## CAT-08 e dependências de IA

- fulfillment existente preservado;
- análise profunda solicitada continua obrigatória no fulfillment;
- `COMPLETE_WITH_LIMITATIONS` não é promovido a completude integral;
- `AI-DEPENDENCY-001` registra prontidão antes do limite do provider;
- IA técnica exige evidência técnica persistida;
- deep analysis exige work items anteriores e contexto evidence-bound prontos.

## CAT-09

- contrato `RECOMMENDATION-GOVERNANCE-001`;
- classificação `TARGET_SITE`, `AUDITOR_INTERNAL`, `EXTERNAL_PROVIDER`, `ENVIRONMENTAL`, `INFORMATIONAL`;
- decisões `ACCEPTED/REJECTED` persistidas;
- problemas internos do auditor não entram no plano do cliente;
- third-party é tratado como fornecedor/dependência externa;
- conflito `JSON-LD ausente × corrigir JSON-LD existente` é rejeitado deterministicamente;
- inventário técnico bruto continua disponível apenas para rastreabilidade.

## Integridade do `report-catalog`

- snapshot SQLite standalone em `integrity/audit-snapshot.db`;
- estado committed do WAL incorporado via SQLite backup;
- hashes SHA-256 dos arquivos entregues;
- verificação offline sem dependência do WAL original;
- fonte não pode mudar durante materialização;
- CAT-09 governance é materializada antes do fingerprint final;
- geração do relatório não cria nova chamada de IA.

## Hardening de estados

- CAT-02 não usa métricas Lighthouse não relacionadas como prova de acessibilidade;
- CAT-04 não é concluído sem medição de performance materializada;
- CAT-06 não é concluído sem amostra/resumo Apdex;
- CAT-07 não é concluído sem amostra/resumo de experiência;
- ausência de dado não equivale a sucesso de execução.

## Testes pontuais adicionados

Principais suites novas/alteradas:

- `test_property_semantic_profile.py`
- `test_property_semantic_profile_persistence.py`
- `test_property_semantic_profile_api.py`
- `test_property_semantic_profile_saas.py`
- `test_semantic_console_persistence.py`
- `test_semantic_corpus.py`
- `test_semantic_coherence.py`
- `test_semantic_audit_execution_contract.py`
- `test_context_interpretation_persistence.py`
- `test_serp_freshness_provenance.py`
- `test_catalog_report_search_trust.py`
- `test_catalog_report_package_integrity.py`
- `test_ai_dependency_reporting.py`
- `test_recommendation_governance.py`
- `test_catalog_state_trust.py`

Providers reais não são requisito desses testes; contratos de IA usam fakes/estado persistido sempre que aplicável.

## Documentação normativa relacionada

- `CONTENT_ANALYSIS_CONTEXT.md`
- `SEMANTIC_COHERENCE_AUDIT.md`
- `AI_DEPENDENCY_TRACEABILITY.md`
- `RECOMMENDATION_GOVERNANCE.md`
- `REPORT_CATALOG_TRUST.md`
