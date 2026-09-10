# RASAi - Monitoramento, observabilidade e qualidade - estado atual das capacidades

**Estado:** implementado e integrado à `main`.

Este documento resume as capacidades presentes no contrato atual do RASAi. Ele não é um histórico de entrega por branch ou pull request (PR).

## Áreas de produto entregues

### Monitoramento longitudinal

- comparação somente leitura de workspaces `AUD-*` persistidos;
- semântica explícita para os estados técnicos `REGRESSED`, `IMPROVED`, `CHANGED`, `NEW`, `RESOLVED`, `DATA_UNAVAILABLE` e `NOT_COMPARABLE`;
- nenhuma conversão silenciosa entre contratos de scoring;
- limiares de materialidade por família de sinal;
- Release Gate determinístico;
- comportamento padrão *fail-closed* quando o par de auditorias não é comparável;
- novas falhas materiais (`NEW`) bloqueiam por padrão;
- sobrescritas operacionais explícitas `--allow-noncomparable` e `--allow-new-failures`;
- famílias opcionais - regras semânticas, performance, métricas sintéticas, agregados de findings e dimensões de score - somente entram mediante opção explícita;
- Change Impact com validação da comparabilidade das janelas e uso de `TEMPORAL_ASSOCIATION_ONLY`, sem atribuição causal.

### Observabilidade de Search & AI

- sidecar `RASAI-OBS-002` com identidade composta de observação `(dataset_id, record_id)`;
- persistência dos artefatos de origem e de seu SHA-256;
- descoberta de propriedades do Search Console;
- leitura somente leitura de Sitemaps do Search Console;
- Search Analytics;
- Search Appearance com proveniência distinta;
- URL Inspection restrita a URLs persistidas no `AUD-*`;
- falhas sistêmicas de URL Inspection interrompem o lote, em vez de repetir falhas de autenticação, quota ou rede para cada URL;
- coleta direta de CrUX History;
- Search Analytics/CrUX, em coleta direta ou importada, limitados à origem auditada;
- linhas de Search Analytics fora de escopo não são persistidas nas linhas normalizadas nem nos artefatos;
- Bing Search Performance em modelo *import-first*, com identidade do dataset sensível à superfície;
- Google Generative AI Performance em modelo *import-first* para Search/Discover;
- observação do controle Google GenAI `INCLUDE`/`EXCLUDE`/`INHERIT`;
- importador genérico `RASAI-OBS-IMPORT-001` com validação de URL, origem e período.

### Endurecimento da interpretação de resultados

- métricas ausentes permanecem ausentes; `NULL` nunca é sintetizado como zero;
- exportações de Google Generative AI Performance permanecem não direcionais no Change Impact quando os valores de origem não permitem concluir uma direção;
- a seleção do dataset compatível mais recente evita somar duas vezes coletas sobrepostas;
- associação temporal exige períodos alinhados ou parcialmente sobrepostos.

### Diagnósticos

- Indexability Reality Matrix;
- Query × Intent Alignment;
- candidatos conservadores a Potential Search Cannibalization;
- verificações de documentação de dados estruturados;
- verificações de `hreflang` e busca internacional;
- consistência de entidades;
- diagnósticos de atualização com base em datas persistidas;
- diagnósticos de recuperação e *chunkability*;
- agrupamento por template/causa raiz.

Os nomes acima permanecem em inglês quando correspondem ao nome técnico da capacidade ou ao rótulo persistido/exibido pelo produto.

### Qualidade e verificação da auditoria

- `report/quality.html`;
- Audit Health / Data Quality;
- Evidence Confidence;
- Coverage Map;
- Recommendation Validation;
- controles do publicador (`nosnippet`, `max-snippet`, `data-nosnippet`, `X-Robots-Tag`);
- Operational Priority acionável em P0-P3, excluindo `RESOLVED`/`CLOSED`/`DISMISSED` da fila executiva de trabalho e preservando as evidências necessárias à linha do tempo e às comparações;
- Fix Verification;
- Evidence Timeline;
- leituras de artefatos confinadas ao workspace `AUD-*`;
- gerenciador de dataset de calibração;
- fingerprint/manifest determinísticos do dataset;
- gates de suficiência anteriores ao ajuste de modelo;
- acesso somente leitura aos `AUD-*` de origem;
- correção da granularidade de feature/target para resultados sem especificidade por dispositivo;
- distinção explícita `READY_FOR_MODEL_FIT != VALIDATED`.

### Relatórios e navegação

- `report/observability.html`;
- `report/quality.html`;
- `MON-*/report.html`, `manifest.json` e, opcionalmente, `impact.html`;
- `VER-*/report.html`;
- `TIMELINE-*/report.html`;
- registro canônico de navegação de páginas opcionais, preservando ordenação e estado da página ativa.

## Gates de segurança

A cobertura automatizada dedicada inclui:

- identidade composta da observação `(dataset_id, record_id)`;
- limites rígidos e escopo de origem para Search Analytics;
- escopo de origem para CrUX direto/importado;
- isolamento de falhas sistêmicas de URL Inspection;
- identidade de superfície do Bing;
- tratamento de métricas ausentes/ambíguas do Google GenAI;
- comparabilidade do Release Gate e política de falhas `NEW`;
- prioridades acionáveis de Quality;
- confinamento de filesystem de Quality;
- suítes de regressão de crawling/discovery, Synthetic User Experience Apdex, Observed Generative Visibility, qualidade de origem e relatório consolidado.

## Limite metodológico

- `SARI-001` é o índice público de readiness;
- resultados observados não passam automaticamente a compor o SARI/scoring;
- Quality oferece suporte à decisão e não constitui outro score de readiness;
- Monitoring detecta mudança/associação e não infere causalidade.

## Validação operacional

Regressão automatizada é obrigatória para alterações nesses domínios. Smoke test humano sobre `AUD-*` persistidos representativos e integrações externas reais é usado quando há credenciais/acesso de rede e a mudança exige validação ambiental.

Comandos operacionais e procedimento de smoke test: [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md).
Contratos normativos: [`specification/27_MONITORING_OBSERVABILITY.md`](specification/27_MONITORING_OBSERVABILITY.md) e [`specification/28_AUDIT_QUALITY_VERIFICATION.md`](specification/28_AUDIT_QUALITY_VERIFICATION.md).
