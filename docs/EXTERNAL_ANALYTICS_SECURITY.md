# Segurança - External Analytics

Controles aplicados:

- nenhum token/key em `rasai-defaults.ini` ou `rasai-console.ini`;
- nenhum token/key em `AuditJob`;
- nenhum token/key em artifacts e HTML;
- Clarity persiste apenas agregados, sem session replay/visitor ID/form values;
- Common Crawl não baixa WARC;
- Common Crawl automático rejeita alvo privado/local, userinfo, query e fragment;
- chamadas externas são bounded e possuem timeout;
- falhas externas são não bloqueantes para a auditoria;
- BR-GEO-060 é positive-only e não participa de Critical Gates.
