# TECHNICAL_ARCHITECTURE.md

**Estado no baseline de desenvolvimento:** aprovado / vigente  
**Readiness:** `SARI-001`  
**Scoring em runtime:** `SCORE-GEO-004`

## 1. Estilo arquitetural

O RASAi mantém Windows como plataforma principal da operação local, com arquitetura modular e execução por CLI/console. A auditoria principal não exige servidor Web, servidor de banco externo, Docker, IA externa nem APIs externas de Search/Performance.

O produto também possui control plane separado para operação multiusuário, multiprojeto e multipropriedade/multidomínio, além de fluxos orientados a deployment. SQLite é o backend local padrão; PostgreSQL 18 é um backend explícito já implementado para centralização do control plane. Essa arquitetura prepara e sustenta a evolução SaaS sem alterar o contrato de evidência imutável dos `AUD-*`.

A camada Web/API e o SaaS Pilot Web existem sobre esse mesmo domínio de produto; não criam segunda interpretação de scoring nem de evidência.

## 2. Runtime

Baseline local:

- CPython 3.13.x;
- Playwright + Chromium;
- SQLite embarcado;
- filesystem local;
- HTTP/HTTPS para alvos auditados;
- integrações HTTPS opcionais somente quando explicitamente habilitadas/configuradas.

Docker não é requisito do runtime local SQLite. É utilizado, quando desejado, como alvo de desenvolvimento/integração PostgreSQL 18.

## 3. Pipeline principal da auditoria

```text
CLI / console interativo
→ configuração + contexto de dispositivo
→ descoberta/aquisição
→ renderização
→ extração/evidência
→ regras determinísticas
→ provider semântico opcional
→ comparação de dispositivos quando aplicável
→ findings
→ scoring por dimensão
→ Overall SCORE-GEO-004
→ priorização/remediação
→ site estático de relatório
→ enriquecimentos opcionais
```

A evidência autoritativa da auditoria permanece `AUD-*/audit.db` + artefatos.

## 4. Scoring

Método atual:

```text
SCORE-GEO-004
HIERARCHICAL_WEIGHTED_READINESS_V1
```

Os cálculos por dimensão permanecem determinísticos e vinculados a evidências. Overall é a média ponderada dos scores medidos das dimensões aplicáveis, usando pesos versionados e renormalização do denominador sobre as dimensões participantes. Dimensões aplicáveis sem valor não são imputadas como zero; reduzem Coverage/Confidence e podem restringir Consolidation. Dimensões críticas de readiness preservam os gates mais rígidos definidos em `05_SCORING_MODEL.md`.

Nenhum enriquecimento downstream pode criar silenciosamente ScoreContribution nem entrar em SARI/SCORE-GEO-004.

## 5. Contexto de dispositivo

O escopo público de dispositivo é `mobile`, `desktop` ou `both`. Somente contextos selecionados/materializados podem disparar análise downstream ou chamadas opcionais. Comparação Desktop × Mobile só é aplicável quando ambos existem.

Synthetic User Experience Apdex pode modelar `TABLET` como perfil sintético, mas `TABLET` não é um `DeviceContext` canônico do core; uma auditoria apenas mobile não pode executar silenciosamente contextos desktop ou tablet do pipeline principal.

## 6. Limites de persistência

### Evidência imutável da auditoria

```text
AUD-*/audit.db
AUD-*/artifacts/
AUD-*/report/
```

### Sidecar de Observability

```text
AUD-*/observability.db
AUD-*/artifacts/observability/
```

Armazena observações externas pós-auditoria sem migrar nem reescrever `audit.db`.

### Cache analítico consolidado

```text
audits/.rasai/consolidated-index.db
```

É derivado e reconstruível; bancos `AUD-*` de origem são lidos somente leitura pelos fluxos derivados.

### Control plane do produto

Backend local padrão:

```text
audits/.rasai/platform.db
```

Backend centralizado explícito:

```text
PostgreSQL 18 via RASAI_PLATFORM_DB_BACKEND=postgresql
                + RASAI_PLATFORM_DATABASE_URL
```

É a autoridade separada para organization/workspace/project/property/environment, users/memberships, milestones/deployments, baselines, schedules, integrações, uso, Search Monitoring, execution jobs e vínculos de identidade. Não substitui evidência de `audit.db`.

## 7. IA opcional

`SemanticAnalysisProvider` é abstraído de fornecedor e `NONE` é um estado válido conforme o contrato correspondente.

Invariantes:

- falha de provider não é finding do website;
- resultado aceito encerra a cadeia daquele contexto;
- providers indisponíveis não sobrescrevem evidência válida;
- provider/modelo/uso/custo são telemetria operacional, não scoring;
- segredos e raciocínio privado não são persistidos;
- remediação por IA é consultiva e vinculada a evidências;
- `AI=AUTO` separa capacidade configurada de participação no pool: excluir um provider do AUTO não remove sua credencial nem impede seleção explícita posterior.

Defaults e valores permitidos de providers/modelos/reasoning são definidos em `../ENVIRONMENT_VARIABLES.md` e no contrato de runtime correspondente.

## 8. Domínios externos/adjacentes

Os itens abaixo permanecem independentes de SARI, salvo futura metodologia explícita e versionada que altere o contrato:

- métricas lab de PageSpeed/Lighthouse, incluindo Agentic Browsing experimental quando solicitado/suportado;
- métricas de campo CrUX;
- automação de Accessibility;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- enriquecimentos de crawling/discovery;
- Search Intelligence / Competitive Search;
- Observed Generative Visibility;
- Search & AI Observability;
- Monitoring/Change Impact;
- Quality/Verification.

Integrações opcionais indisponíveis produzem limitações/estado operacional, não falhas artificiais do website.

## 9. Arquitetura de relatórios

O resultado por `AUD-*` é um site HTML estático. Abri-lo nunca dispara crawling, IA nem coleta de API.

Rotas canônicas de método:

```text
index.html
readiness.html
scoring.html
```

A versão do método é armazenada em `scoring_version` e renderizada na página, não codificada no filename canônico.

Totais de consumo de IA do relatório derivam da telemetria persistida de tentativas, não de scraping de labels de apresentação. Chamadas cujo provider não retornou uso permanecem sem custo monetário inventado.

## 10. Monitoring / Observability / Quality

Monitoring abre `AUD-*` persistidos somente leitura e respeita comparabilidade de dispositivo, universo de URLs e `scoring_version`.

Observability usa sidecar derivado e proveniência explícita. Quality/Verification usa evidência somente leitura para apoiar decisões sem criar outro score de readiness.

Associação temporal não é inferência causal.

## 11. Product Platform e alvo SaaS

A Product Platform suporta duas autoridades de control plane:

| Backend | Default/ativação | Uso recomendado |
|---|---|---|
| SQLite | default local | máquina única, operação offline/local, piloto portátil |
| PostgreSQL 18 | opt-in explícito | control plane centralizado/hospedado e validação de paridade |

A arquitetura SaaS alvo complementa PostgreSQL com scheduler/fila durável, workers Linux/container, object storage, secret management e autenticação/tenant context hospedados.

Windows local permanece modo de execução de primeira classe. O limite de migração é produto/control plane, não reescrita da evidência histórica `audit.db`.

## 12. Web/API e execution plane

A Web API é uma superfície tenant-aware sobre os contratos do control plane. Requests de execução criam jobs duráveis; crawling/auditoria e Search Monitoring são executados por workers desacoplados quando usados por essa superfície.

O SaaS Pilot Web consome a mesma API/store e não cria regras de negócio paralelas no frontend.

Persistir fila/schedules em banco é necessário, mas não suficiente para execução distribuída segura: múltiplos workers/schedulers exigem claims atômicos, idempotência, leases/locks, retries limitados e controles de concorrência.

## 13. Segurança e isolamento de falhas

- aplicar regras de escopo/mesma origem quando cabível;
- nenhuma expansão cross-origin implícita;
- nenhum segredo em relatórios/artefatos/bancos destinados a evidência;
- respostas externas são entrada não confiável;
- workflows derivados não modificam `AUD-*` de origem;
- falhas opcionais são isoladas da auditoria principal bem-sucedida;
- `scoring_version` histórico é preservado, não normalizado silenciosamente;
- autenticação Web default é fail-closed até configuração válida;
- autorização de tenant é revalidada no servidor, não delegada ao frontend.
