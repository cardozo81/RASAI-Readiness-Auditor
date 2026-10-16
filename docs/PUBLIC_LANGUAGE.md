# #377 - Vocabulário público e rastreabilidade técnica

## Inventário focalizado - ciclo pré-smoke

| Origem | Texto anterior no usuário | Rótulo público | Decisão |
| --- | --- | --- | --- |
| Console / cronologia de IA | Cronologia IA M18/M20 | Tempo e consumo das análises por IA | Remover IDs; preservar soma e união independentes |
| Console / configuração Apdex | Classificação M6 será descoberta | Arquitetura será identificada durante a coleta | Separar declarado de observado |
| metrics.html / linha temporal IA | Durações em bases M18/M20 | Durações das solicitações de análise por IA | Preservar ressalva sobre overlap/wall-clock |
| metrics.html / requisição web | Tempos M21, Serviço M21 | Tempos observados de requisições web, Serviço web | Não confundir soma HTTP com tempo de fase |
| cat-07.html / arquitetura | Rastreabilidade da arquitetura M6 | Rastreabilidade da arquitetura identificada | Preservar snapshot/page/device e N/D |
| CAT-07 / motivos | configuração efetiva M25 | configuração do Apdex de experiência | Apenas rótulo; códigos estruturados imutáveis |
| CLI Dynatrace / orientação | mesma amostra M6; M23/M25 | mesma amostra de arquitetura; Apdex de navegação e experiência | Não confundir RUM com Synthetic |

## Ampliação de inventário operacional (ciclo seguinte)

| Origem | Texto anterior no usuário | Rótulo público | Decisão |
| --- | --- | --- | --- |
| CLI `audit-attempts --help` | attempts M18/M20, M21 HTTP | tentativas de IA e requisições HTTP | Preservar nomes físicos apenas no JSON |
| Descrições do CLI e ledger de tempos | relógios de tentativas M18/M20, Valores M21 | relógios de análises por IA, tempos informados por requisição | Sem alterar valores e fórmulas |
| Manual operacional de custos | tempos M18/M20 e chamadas HTTP M21 | tempos de análises por IA e requisições web | Preservar os campos JSON documentados |

## Exceções deliberadas

**Documentação técnica:** `docs/AUDIT_STAGE_SCOPE.md`,
`docs/CONS_DOMAIN_COMPARATIVE.md`,
`docs/CAT07_EXPERIENCE_ARCH_GUIDANCE.md` e
`docs/AI_RUNTIME_ORCHESTRATION.md` continuam com IDs M* porque
descrevem interfaces internas, contratos, datas, tabelas e módulos.

**Dados e rastreabilidade:** códigos como `M25_RUNTIME_FAILURE`,
identificadores de regra/SQL, `snapshot_id`, código-fonte, telemetria
e caminhos de arquivo são deliberadamente preservados. Substituí-los
globalmente poderia romper contratos e esconder evidência.

**Mensagens públicas novas:** utilizar nomes funcionais curtos. Referências
internas somente em seções explicitamente técnicas sob demanda.
Validação focalizada inclui console, metrics, CAT-07 e a orientação
Dynatrace offline; não executa AUD nem provider.

Nenhum motor, score, cálculo, schema ou hash de auditoria é alterado.
