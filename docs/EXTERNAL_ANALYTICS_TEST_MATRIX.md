# Matriz de regressão - External Analytics

Esta matriz reúne casos de regressão para os serviços externos. Consulte o [guia dos relatórios](REPORT_GUIDE.md) para distinguir as páginas do catálogo técnico das sínteses executivas.

| Área | Contrato |
|---|---|
| Core audit | falha externa nunca transforma website em FAIL |
| SARI | ausência Common Crawl não altera score técnico/Coverage |
| SARI | BR-GEO-060 é positive-only e não integra Critical Gates |
| SARI | contribuição nominal de 0,45 ponto no resultado geral quando os pesos são integralmente medidos |
| Reprodutibilidade | evidência positiva vira Evidence + RuleExecution antes do cálculo do método vigente em novas auditorias (`SCORE-GEO-005`) |
| Reprodutibilidade | rescoring não requer nova chamada Common Crawl |
| Segurança | URL privada/local/query/fragment/userinfo não é enviada automaticamente ao índice público |
| INI | Common Crawl credential-free fica `true` por default |
| INI | Clarity permanece opt-in |
| Segredos | tokens/keys não entram no INI/AuditJob/artifacts/HTML |
| Scope | Common Crawl = URL/global, sem device |
| Scope | CrUX History = ORIGIN + form factor |
| Scope | Clarity = URL/origin + Device quando dimensão presente |
| Catálogo técnico | CrUX em `report-catalog/cat-04.html`. Observações de Clarity e Common Crawl em `report-catalog/cat-05.html`, quando disponíveis. |
| Índice técnico | Corroboração `BR-GEO-060` rastreável em `report-catalog/sari.html` e `report-catalog/methodology.html`. |
| Apresentação executiva | `report-presentation/performance.html` para leitura de desempenho e `report-presentation/indices.html` para leitura dos índices, com cobertura condicionada aos dados persistidos. |
| SaaS | AuditJob recebe somente opções não secretas |
| Perfis | perfis não ligam Clarity silenciosamente nem alteram overrides da integração |
