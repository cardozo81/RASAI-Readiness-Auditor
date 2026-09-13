# External Analytics - notas da entrega

A entrega adiciona integrações read-only de alto valor analítico sem introduzir novo custo obrigatório de provider.

Principais mudanças:

- CrUX History: histórico de experiência real por origem/form factor;
- Microsoft Clarity: comportamento agregado real, opt-in por quota;
- Common Crawl: histórico público bounded, sem credencial e default-on;
- SARI: Common Crawl pode gerar apenas BR-GEO-060 PASS, com peso máximo limitado;
- segurança: URLs internas/parametrizadas não são enviadas automaticamente a índice público;
- relatórios e console atualizados;
- segredos continuam fora do INI/AuditJob/artifacts/HTML.
