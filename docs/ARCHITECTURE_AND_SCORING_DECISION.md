# Decisão arquitetural - consumidores e metodologia consultiva

Status: **contrato conservador aprovado para evolução incremental**, 17/10/2026.
Escopo: arquitetura F3, evidências GEO/SARI, SEO opcional e roadmaps
longitudinal/concorrentes. A autorização do roadmap e da metodologia
não define valores de pesos, thresholds, comparabilidade entre fornecedores
ou autorização de coleta externa irrestrita.

## Fronteiras executáveis

1. F1/F2 continuam como observação e descrição, com identidade
   `audit_id/page_id/snapshot_id/requested_url/final_url/device`. Somente
   `descriptive_report` e `m6_read_only_diagnostic` podem receber contexto
   efetivo sob a política `APPROVED_ADVISORY_CONSUMERS`.
2. F3 é elegível para desenho de contratos e fixtures, **não** para ativação
   automática em coleta, avaliação de prontidão, SARI, SCORE-GEO, Apdex ou IA. O conjunto
   de consumidores operacionais é vazio nesta versão da política.
3. Para sinais opcionais robots/canonical/sitemap, conservar o motor SCORE-GEO
   vigente até existir tabela versionada de deltas/pesos, critérios de amostra
   e golden diferencial do mesmo AUD. Não inferir alteração de pesos do
   aceite genérico de metodologia.
4. FAQ sem clique tem estado `NOT_OBSERVED_WITHOUT_INTERACTION`, não
   `ABSENT_EDITORIALLY`. A observação pós-clique exige mesmo navegador
   e snapshot, isolados e autorizados.
5. Claims reguladas exigem documento primário, edição/vigência e produto
   correlacionados. Sem fonte, a saída permanece `UNVERIFIED`, sem
   afirmação de conformidade.
6. GEO só agrega coortes com query, intent, mercado, janela e proveniência
   comparáveis; dados incompletos conservam abstenção. Snippet não
   equivale ao conteúdo integral.
7. Os roadmaps GEO longitudinal/concorrentes passam a ter autorização de
   planejamento e implementação local isolada. Coleta live e integração
   operacional exigem budgets, consentimento do alvo, segurança e teste
   de não regressão - independentemente da aprovação de roadmap.

## Gates de adoção operacional

- Versão de contrato, migração explícita e plano de rollback.
- Fixture adversarial, erro, ausências, dados legados e golden antes/depois.
- Prova de integridade AUD e invariância dos motores canônicos.
- Coorte física pareável quando metodologia usa dados reais.
- Aprovação de tabela normativa concreta antes de mudar pontuação.

Esta decisão **não modifica** índices nem executa integrações comerciais.


## Entrega F3 descritiva por snapshot

O projetor de relatório arquitetural e sua CLI foram integrados somente para consumidores aprovados. A descrição não é ativação de processamento automático por catálogo: `AUTO` observa módulo arquitetural quando aplicável e `DECLARED` conserva a escolha congelada separada da descoberta medida. Falta de prova física/decisão metodológica não é contornada por esse painel. Consulte [`ARCHITECTURE_AUDIT_ADVISORY.md`](ARCHITECTURE_AUDIT_ADVISORY.md).
