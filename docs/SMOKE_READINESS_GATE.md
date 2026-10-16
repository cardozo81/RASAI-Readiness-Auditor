# Gates independentes de smoke e aceite da PR de reconciliação

## Escopo, origem e regra de prova

Branch única: `chore/acceptance-evidence-reconciliation` · PR #645.

Toda liberação precisa indicar **SHA testado, executor/ambiente, comandos e resultados efetivamente observados**. Resultados de outro SHA não aprovam o HEAD atual. `queued`/`pending` não significam sucesso nem falha de código; inspeção estática não equivale a `compileall`, importação efetiva, `pytest` ou execução de GitHub Actions.

Este documento separa dois gates **independentes**. O Gate A é suficiente para iniciar **smoke humano exploratório isolado**, mesmo enquanto a CI integral ou questões externas de outras issues permanecem pendentes. O Gate B é obrigatório para homologação final e integração. Não usar pendências de Gate B para impedir indevidamente Gate A, nem promover Gate A a aprovação final.

## Gate A — smoke exploratório isolado

**Pré-requisitos obrigatórios, comprovados no mesmo HEAD:**

1. `python -m compileall -q src/rasai tests` sem erro, com Python/venv compatível com o projeto.
2. Importação **executada** dos entrypoints envolvidos (console, relatório, SARI e serviços usados no roteiro); nenhuma inicialização faturável ou mutação de AUD como efeito colateral.
3. `pytest` focal efetivamente verde para SARI/critério de readiness, governança de relatório, FAQ, persistência de configuração e política de paths. Ajustar a seleção à árvore do SHA e ao roteiro; completar com GEO/SQLite/Dynatrace quando diretamente exercitados.
4. `git diff --check origin/main...HEAD`, integridade dos paths de workflow/nomes versionados e ausência de conflitos de merge.
5. Nenhuma falha crítica conhecida que torne inseguros os fluxos exatos do smoke.

**Sequência reprodutível em checkout isolado** (exemplos, não resultados):

```bash
python -m compileall -q src/rasai tests
python -c "import rasai.sari_readiness_presentation; import rasai.catalog_report_governance"
python -m pytest -q tests/test_sari_readiness_presentation.py tests/test_catalog_report_final_refinements.py
python -m pytest -q tests/test_catalog_report_site.py tests/test_faq_transition_policy.py
python -m pytest -q tests/test_console_config_provenance.py tests/test_console_complete_persistence.py
python -m pytest -q tests/test_repository_filename_policy.py
python tests/test_repository_filename_policy.py --full-tree --head HEAD
git diff --check origin/main...HEAD
```

Se um teste focal falhar, corrigir sua causa e reexecutar o conjunto afetado; **não liberar** um pacote comprovadamente inexecutável. Se não houver executor, marcar `NÃO EXECUTADO` e manter Gate A **NÃO COMPROVADO**; não substituir runtime por inspeção de fonte.

**Após aprovação objetiva do Gate A:** declarar “APTO A SMOKE EXPLORATÓRIO”, citar SHA + testes + ambiente + limitações e fornecer roteiro Windows em **cópia da branch**, nunca na `main`/INI/AUD originais. Usar INI temporário e AUD sintética ou cópia read-only selada; abrir console, navegar/preparar auditoria sem execução paga, renderizar relatórios, verificar SARI/FAQ/GEO/arquitetura quando houver evidências. Capturar erros e artefatos redigidos sem credenciais. Nenhum provider pago, rede externa faturável, nova AUD comercial, reprocessamento destrutivo ou gravação no INI original sem aprovação específica.

A aprovação exploratória **não** é aceite executivo, não fecha épicos metodológicos, não autoriza merge e não declara SARI/Apdex/GEO recalibrados.

## Gate B — homologação final e merge

**Todos** os requisitos seguintes precisam de evidência própria (se aplicáveis), sem “herdar PASS” de outro SHA:

- Suites relevantes Linux/Windows, segurança e **todos os required checks do HEAD final** efetivamente verdes; inspecionar job/log de falhas e proteções.
- Paridade e integridade de banco, manifestos, hashes e relatórios (inclusive dados ocultos/escapados), score canônico e dados históricos preservados.
- Reconciliação **por requisito** de cada issue elegível `>= #301`; fechar apenas tickets 100% aceitos e comprovados. Pendência metodológica/externa mantém seu ticket OPEN e não é mascarada como PASS.
- ADR, versionamento e aprovação explícita para alterações de SCORE-GEO/SARI/M23/M25 ou propagação arquitetural que mudem método. Política arquitetural transversal #646 é evolução rastreada e **não bloqueia o Gate A** sem defeito específico comprovado.
- Gates físicos/externos que de fato integrem o aceite: round-trip isolado Windows/INI (#523), FAQ SPA sem interação indevida (#601), conteúdo legal oficial versionado quando exigível (#603), comparação SERP × Perplexity realmente equivalente (#304), Dynatrace RUM representativo (#355/#357), amostra same-sample browser (#322).
- Smoke humano homologatório quando previsto, PR retirada de Draft somente ao completar aceite e merge controlado; validar `main` **depois** da integração.

Questões não pertencentes ao escopo da PR podem continuar em roadmap, mas nenhum aceite da PR ou de issue pode ser declarado completo se seus próprios critérios ainda dependerem delas. Toda exceção exige justificativa explícita, não desativação de gates críticos.

## Estado factual da última inspeção registrada

Em 16/10/2026, no `d99aa9245220dd7e7c6f658d77d6442475c749ab`, a CI do SHA apresentava **77 workflow runs queued e 2 pending**, sem resultado conclusivo. Uma validação **estática** leu 1.474 paths versionados (0 basenames proibidas) e 86 workflows (0 referências Python literais positivas inexistentes); preservado 1 guard negativo intencional. **Não houve `compileall`, imports, `pytest` nem execução do smoke demonstrados por essa inspeção.** Consequentemente, naquele checkpoint, Gate A = **NÃO COMPROVADO** e Gate B = **PENDENTE**. Nova leitura do HEAD e dos checks é obrigatória antes de qualquer decisão.

Nenhuma afirmação deste documento converte leitura estática ou CI pendente em teste de runtime.

## Gate A físico — Windows e smoke focal de restauração (16/10/2026)

- `21cacbe40e911b4957cf637004ecd88a25d4ca28`: 8 checks focais em Windows com exit 0; o primeiro smoke detectou defeito real: após **V** em “Restaurar padrões”, o console exigia indevidamente uma segunda decisão de gravação.
- `98d89a5659c64f7d05371449a41bbc037d45f9c0`: correção do cancelamento implementada na PR #645. O operador executou o Gate A revisado no Windows: **9 checks reportados PASS**, incluindo `console_restore_navigation`; o smoke protegido confirmou `NETWORK_GUARD_ACTIVE`, `REGISTRY_WRITE_GUARD_ACTIVE` e **APROVADO** somente para o cenário **Sistema → Restaurar padrões → V** sem exibição do diálogo de persistência.
- Este resultado aprova o fluxo humano **focal**, não a experiência completa, a preservação do Windows/User sob restauração real, o save/reopen de INI físico, os relatórios ou o Gate B. Arquivos físicos de registro e logs do novo smoke ainda não foram inspecionados. Não atribuir aceite transversal à issue #523.
- Há risco independente: restauração confirmada pode alterar valores **Windows/User** mesmo quando o INI aponta para arquivo temporário; manter ações de restauração efetiva fora do roteiro exploratório. Guards no processo Python não substituem sandbox de sistema operacional.
- Qualquer commit **posterior** a esse SHA exige prova de execução focal no novo HEAD antes de promover novo aceite. A PR permanece **DRAFT / NO MERGE** enquanto a CI requerida e os aceites por issue não estiverem concluídos.
