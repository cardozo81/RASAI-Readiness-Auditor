# Escopos de dados - External Analytics

| Fonte | Granularidade canônica | Device/form factor | Uso |
|---|---|---|---|
| CrUX History | `ORIGIN` | ALL/PHONE/DESKTOP/TABLET conforme contexto auditado | histórico de campo; não SARI |
| Microsoft Clarity | `URL`/origem | `Device` somente quando solicitado/retornado | Behavioral UX; não SARI |
| Common Crawl | `URL` | nenhum | histórico público; BR-GEO-060 global positive-only |

O RASAi não replica Common Crawl por device e não transforma dados de origem em dado de página sem proveniência explícita.
