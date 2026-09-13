# Matriz de regressão - External Analytics

Esta matriz resume os contratos que devem permanecer verdes antes de integrar a feature em `main`.

| Área | Contrato |
|---|---|
| Core audit | falha externa nunca transforma website em FAIL |
| SARI | ausência Common Crawl não altera score técnico/Coverage |
| SARI | BR-GEO-060 é positive-only e não integra Critical Gates |
| SARI | impacto máximo teórico do grupo externo = 0,45 ponto Overall |
| Reprodutibilidade | evidência positiva vira Evidence + RuleExecution antes do M9 |
| Reprodutibilidade | rescoring não requer nova chamada Common Crawl |
| Segurança | URL privada/local/query/fragment/userinfo não é enviada automaticamente ao índice público |
| INI | Common Crawl credential-free fica `true` por default |
| INI | Clarity permanece opt-in |
| Segredos | tokens/keys não entram no INI/AuditJob/artifacts/HTML |
| Scope | Common Crawl = URL/global, sem device |
| Scope | CrUX History = ORIGIN + form factor |
| Scope | Clarity = URL/origin + Device quando dimensão presente |
| Relatórios | CrUX → web-performance/observability |
| Relatórios | Clarity → apdex-experience/observability |
| Relatórios | Common Crawl → crawling-discovery/observability |
| Relatórios | BR-GEO-060 → readiness/scoring |
| SaaS | AuditJob recebe somente opções não secretas |
| Perfis | perfis não ligam Clarity silenciosamente nem alteram overrides da integração |
