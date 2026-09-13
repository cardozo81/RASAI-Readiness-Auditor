# Arquitetura - External Analytics

```text
                           RASAi Audit
                              |
          +-------------------+-------------------+
          |                   |                   |
     deterministic       external field       external behavior
       evidence            observability        observability
          |                   |                   |
       audit.db          observability.db     observability.db
          |                   |                   |
          |              CrUX History             Clarity
          |                                       |
          +-------------------+-------------------+
                              |
                         HTML reports
```

Common Crawl possui um fluxo adicional estritamente bounded:

```text
safe public audited URLs
        |
Common Crawl CDX (read-only)
        |
observability.db + sanitized artifact
        |
qualifies? positive + >=50% bounded URLs + no current Discovery blocker
        |
        +-- no --> no SARI RuleExecution; no penalty
        |
        +-- yes --> Evidence + BR-GEO-060 PASS in audit.db
                            |
                            M9
                            |
                    score_contributions
```

## Fronteiras

- CrUX History e Clarity não entram no SARI.
- Common Crawl não prova Google/Bing indexation.
- BR-GEO-060 não integra Critical Gates.
- O grupo externo pesa 3% de `DISCOVERY_ACCESS`; máximo teórico = 0,45 ponto Overall.
- Quando BR-GEO-060 não existe, os sete grupos técnicos mantêm exatamente suas proporções anteriores.
- Segredos nunca são copiados para `audit.db`, INI, AuditJob, artifacts ou HTML.
- A falha de qualquer API externa é estado da integração, não falha do website.
