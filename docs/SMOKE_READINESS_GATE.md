# Gate técnico de liberação para smoke humano

## Estado e semântica

**NÃO LIBERADO** no HEAD da PR #645 verificado em 16/10/2026. O GitHub Actions retornou apenas workflows `queued` / `pending`, sem check `success` neste HEAD. Uma inspeção estática focal em 16 arquivos alterados confirmou ausência de marcadores de conflito e nomes duplicados de testes, mas **não** compilou os módulos Python nem executou `pytest`. O runner necessário não estava disponível neste ambiente para uso local (sem resolução externa do GitHub); não é permitido apresentar essa inspeção como teste verde.

O gate aplica-se à **mesma branch** `chore/acceptance-evidence-reconciliation` e à PR #645; commits posteriores invalidam os resultados de um HEAD anterior.

## Comandos reprodutíveis no checkout da PR

```bash
python -m compileall -q src/rasai tests
git diff --check origin/main...HEAD
python -m pytest -q tests/test_sari_readiness_presentation.py tests/test_faq_transition_policy.py tests/test_optional_seo_policy_errors.py tests/test_claim_collection_provenance.py
python -m pytest -q tests/test_audit_attempt_timeline.py tests/test_audit_cost_explain.py tests/test_console_config_provenance.py
python -m pytest -q tests/test_geo_query_ledger.py tests/test_geo_competitor_content_provenance.py tests/test_geo_cons_companion.py
python -m pytest -q tests/test_apdex_content_readiness.py tests/test_apdex_readiness_sidecar.py
python -m pytest -q tests/test_dynatrace_apdex_arch_advisory.py tests/test_dynatrace_rum_population.py tests/test_m21_field_scope_presentation.py
python -m pytest -q tests/test_repository_filename_policy.py
python tests/test_repository_filename_policy.py --base origin/main --head HEAD
```

Após corrigir qualquer falha focal, exigir execução verde dos checks **obrigatórios** Linux/Windows e segurança do HEAD final no GitHub, não apenas de commits anteriores. Avaliar separadamente requisitos de prova física Windows/INI, interação FAQ autorizada, autenticidade de documentos externos, Dynatrace RUM realmente representativo e comparabilidade GEO. Fixtures/fake network não substituem essas fontes.

## Regras de liberação

1. Nenhum `SyntaxError`, `ImportError`, erro de contrato, regressão focal ou check obrigatório vermelho.
2. Nenhum score/catálogo SARI/SCORE-GEO/Apdex/CONS histórico alterado indevidamente. Provar integridade e paridade do pacote em AUD de teste selada, mantendo dados originais intactos.
3. Reconciliar individualmente todas as issues elegíveis >= #301; se um aceite depende de fonte externa, registrar como não demonstrado e não simular aprovação.
4. Somente após o gate técnico comprovadamente verde anunciar pacote **apto para smoke humano**. Isso não é homologação final nem autorização automática de merge se houver condições adicionais.

**Status atual:** PENDENTE de execução técnica real, de CI verde e dos critérios externos aplicáveis; não utilizar este documento como certificado de aceite.
