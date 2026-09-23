# Avaliação futura - Runner gerenciado, persistência SaaS e relatórios dinâmicos

**Estado:** pendência arquitetural para revisão futura.
**Rastreabilidade:** GitHub Issue #163 - https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/163
**Natureza:** levantamento de premissas, estado atual, gaps, requisitos candidatos e decisões em aberto.
**Efeito no produto atual:** nenhum. Este documento não cria endpoint, contrato público, licença, entitlement, storage remoto ou obrigação de implementação.

Antes de qualquer implementação, este documento deve ser revisado contra o estado real do produto. A revisão deve terminar em uma decisão explícita: **IMPLEMENTAR**, **SUBSTITUIR**, **MANTER PENDENTE** ou **DESCONTINUAR**.

## 1. Objetivo

Consolidar o entendimento atual sobre uma possível evolução do RASAi para um modelo em que:

- execuções locais oficiais sejam identificadas e autorizadas por um control plane SaaS;
- desenvolvimento, testes automatizados e CI continuem possíveis sem depender obrigatoriamente do SaaS;
- evidências e artefatos de execuções gerenciadas deixem de depender da permanência dos arquivos na máquina executora;
- o SaaS possa, futuramente, renderizar relatórios dinamicamente a partir dos dados e evidências persistidos, sem repetir coleta, scoring ou análise já concluída.

Este documento preserva uma decisão arquitetural em aberto. Ele não presume que todos os itens serão implementados.

## 2. Premissas que devem ser preservadas

- `AUD-*/audit.db` e os artefatos associados representam a evidência da execução.
- `report-catalog/` é projeção de leitura e não deve se tornar fonte de verdade.
- Scoring, SARI, findings, evidências, cálculos, integrações e resultados observados devem existir independentemente do HTML.
- PostgreSQL é o backend relacional alvo do control plane centralizado; não é, por definição, substituto do formato de evidência `AUD-*`.
- Estado mutável de produto, tenancy, usuários, memberships, jobs, schedules, uso e referências de auditoria pertencem ao control plane.
- Segredos não devem ser materializados em argumentos de linha de comando, logs, relatórios, INI ou payloads duráveis comuns.
- Evolução SaaS não deve alterar silenciosamente `SARI-001`, `SCORE-GEO-004`, regras de coleta ou resultados metodológicos.
- Migração deve preservar rastreabilidade, integridade criptográfica e identidade das execuções.
- HTML dinâmico, se adotado, continua sendo somente camada de apresentação sobre dados persistidos.

## 3. Estado confirmado atualmente

### 3.1 Execução local

O modo local continua sendo o comportamento padrão. Console, CLI ou agendador externo podem materializar localmente:

```text
AUD-*/
├── audit.db
├── artifacts/
├── logs/
└── report-catalog/
```

Os comandos reproduzíveis não dependem hoje de uma autorização SaaS obrigatória para iniciar o motor local.

### 3.2 Agendamento externo

O RASAi documenta execução por Agendador de Tarefas do Windows, cron/systemd e launchd. O contrato atual não exige que, antes de cada execução local, o executor consulte o SaaS para validar usuário, organização, projeto, instalação, entitlement, quota, assinatura, permissão de uso ou versão permitida.

### 3.3 Cliente remoto do control plane

Já existe cliente remoto com configuração baseada em:

```text
RASAI_CONSOLE_MODE=remote
RASAI_REMOTE_BASE_URL
RASAI_REMOTE_TOKEN_ENV
RASAI_REMOTE_USER_ID
RASAI_REMOTE_TIMEOUT_SECONDS
```

O cliente remoto pode usar bearer token e acessar o control plane HTTP. Isso deve ser distinguido de uma futura autorização de Runner: o console remoto é cliente do control plane, mas não transforma automaticamente toda chamada direta de `rasai audit` em execução licenciada/autorizada pelo SaaS.

### 3.4 Identity & Access da Web/API

A Web/API já possui contratos de identidade, autorização e escopo de tenant. Operações que passam pela API são autorizadas no servidor. Isso protege a API, mas não equivale a autorizar um processo local iniciado diretamente fora dela.

### 3.5 PostgreSQL

PostgreSQL já pode atuar como backend centralizado do control plane. É adequado para dados relacionais do produto, incluindo Organization, Workspace, Project, Property, Environment, usuários, memberships, identidades externas, catálogo de auditorias, jobs, schedules, milestones, usage, índices, referências, hashes e metadados.

PostgreSQL não é hoje uma cópia integral dos bytes de `audit.db`, `artifacts/` e `report-catalog/`.

### 3.6 Evidência física

No estado atual, a evidência detalhada permanece principalmente no workspace físico da auditoria:

```text
audits/AUD-*/audit.db
audits/AUD-*/artifacts/
audits/AUD-*/report-catalog/
```

A indexação no control plane não transfere automaticamente o bundle completo para armazenamento hospedado.

### 3.7 Reports no SaaS Pilot

A API atual de reports autoriza o usuário e serve arquivos permitidos de `report-catalog/`, mas o arquivo precisa estar acessível ao processo/servidor que atende a requisição. Uma AUD criada em máquina isolada não se torna, apenas por possuir metadados no PostgreSQL, um histórico integralmente disponível de qualquer lugar.

### 3.8 Armazenamento de objetos

A arquitetura já prevê object storage para operação hospedada, inclusive bundles AUD, artefatos, relatórios e evidência bruta. Entretanto, o armazenamento de objetos definitivo e um protocolo completo de sincronização de Runner local ainda não constituem o contrato operacional atual.

### 3.9 Relatórios

Os relatórios atuais já seguem a premissa necessária para uma evolução futura:

```text
dados/evidências persistidos
        ↓
projeção HTML
```

A renderização não deve recolher novamente o alvo nem redefinir scores. Essa separação permite considerar um renderer SaaS dinâmico futuramente.

## 4. Gaps identificados

### 4.1 Identidade própria do Runner

Não existe hoje contrato completo de entidade de Runner/instalação que permita ao SaaS saber de forma autoritativa:

- qual instalação está executando;
- a quem ela pertence;
- a quais projetos ela pode servir;
- se está ativa, revogada ou suspensa;
- qual versão do RASAi executa;
- quando se comunicou pela última vez;
- quais capacidades estão autorizadas.

### 4.2 Autorização prévia de execução local

Falta um handshake obrigatório, caso essa estratégia seja aprovada:

```text
executor local
    ↓
autenticação do Runner
    ↓
autorização do escopo
    ↓
validação de entitlement/quota/política
    ↓
autorização de execução
    ↓
motor RASAi
```

### 4.3 Entitlement/licenciamento comercial

RBAC e tenancy não equivalem a entitlement comercial. Permanecem em aberto plano habilitado, limites de uso, quota, suspensão, expiração, revogação, capacidades disponíveis e comportamento em excesso de consumo.

### 4.4 Credencial segura do Runner

Faltam contratos definitivos para enrollment, emissão, rotação, revogação, armazenamento local seguro e troca por token de curta duração. Credencial persistente não deve ser inserida como argumento literal no comando do Agendador do Windows.

### 4.5 Política offline

Não está decidido se um Runner gerenciado poderá iniciar novas execuções quando o SaaS estiver indisponível. Devem ser avaliados fail-closed, autorização assinada de curta validade ou janela de tolerância limitada.

### 4.6 Sincronização da evidência

Não existe protocolo completo para manifestar o bundle, calcular hashes, enviar, retomar upload, garantir idempotência, validar bytes recebidos, registrar persistência central e repetir somente a sincronização após falha.

### 4.7 Armazenamento central

Faltam decisões sobre fornecedor, convenção de chaves, versionamento, criptografia, retenção, exclusão, backup, replicação, lifecycle, custo, região, política de acesso e disaster recovery.

### 4.8 Histórico independente da máquina

Enquanto o bundle integral permanecer somente no executor, o SaaS não é autoridade completa sobre aquele histórico. Uma AUD marcada futuramente como persistida pelo SaaS deve continuar consultável mesmo que a máquina original esteja desligada, perdida ou desinstalada.

### 4.9 Read model central

Precisa ser definido o que permanece somente no bundle, o que é indexado/normalizado no PostgreSQL, o que é materializado em read model e o que é recuperado do object storage sob demanda. Qualquer duplicação precisa ter autoridade e regra de reconstrução explícitas.

### 4.10 Renderer SaaS dinâmico

Ainda não existe contrato definitivo para montar toda a apresentação HTML sob demanda a partir de dados centrais. Também faltam compatibilidade histórica, versionamento de template/schema, cache, materialização opcional e preservação de snapshots.

## 5. Requisitos candidatos - Runner gerenciado

1. Cada instalação gerenciada possui identidade opaca própria, por exemplo `RUN-*`.
2. Runner é vinculado a tenant e escopos autorizados.
3. Credencial de Runner é distinta da identidade humana.
4. Execução agendada não depende de login interativo.
5. Secrets não aparecem em CLI, Task Scheduler, logs ou arquivos compartilháveis.
6. Credencial persistente usa secret boundary adequado do sistema operacional.
7. Sempre que possível, o Runner troca credencial persistente por autorização/token de curta duração.
8. Revogação no SaaS impede novas execuções gerenciadas.
9. Autorização considera tenant, projeto, ambiente, capacidade e política comercial.
10. Decisão de autorização é auditável.
11. Replay deve ser prevenido quando a autorização for por execução.
12. Expiração, clock skew e indisponibilidade de rede precisam de semântica explícita.
13. Versões não suportadas do Runner podem ser bloqueadas ou limitadas por política.

## 6. Requisitos candidatos - desenvolvimento sem SaaS

- Desenvolvimento local, testes automatizados e CI devem continuar executando o core sem SaaS.
- O bypass deve ser classificado como mecanismo de desenvolvimento, não licença comercial.
- Build/distribuição oficial não deve permitir bypass trivial por simples variável de ambiente se autorização SaaS for requisito comercial.
- Testes do motor, scoring, relatórios e integrações não devem depender de disponibilidade hospedada.
- Mocks/fakes do contrato de autorização devem ser possíveis.
- Modo de desenvolvimento não altera metodologia, scoring ou formato de evidência.

A estratégia concreta de segregação entre build de desenvolvimento e distribuição oficial permanece pendente.

## 7. Requisitos candidatos - persistência central

1. Execução pode produzir temporariamente sua evidência local.
2. Runner gera manifesto e hashes.
3. Evidência é enviada para storage central.
4. Upload é autenticado, tenant-scoped e idempotente.
5. Uploads grandes suportam retry e, quando necessário, retomada.
6. SaaS valida integridade antes de declarar persistência concluída.
7. PostgreSQL registra referências, hashes, tamanho, versão de manifesto e estado do storage.
8. AUD não é tratada como arquivada centralmente enquanto evidência obrigatória estiver incompleta.
9. Perda de conectividade após auditoria permite repetir somente sincronização, sem nova coleta.
10. Retenção local após confirmação é política configurável, não condição para o histórico SaaS.

Estados conceituais a avaliar:

```text
EXECUTION_COMPLETED_LOCAL
        ↓
PENDING_UPLOAD
        ↓
UPLOADING
        ↓
VERIFYING
        ↓
PERSISTED
```

Os nomes finais e a máquina de estados precisam ser definidos antes de implementação.

## 8. PostgreSQL versus object storage

A arquitetura preferencial, se esta frente for aprovada, separa responsabilidades.

### PostgreSQL

Adequado para tenancy, autorização, Runners, jobs, estados, índices, métricas consultáveis, scores/resumos quando fizerem parte do read model, referências de storage, hashes, usage, quotas, entitlements e metadados de ciclo de vida.

### Object storage

Adequado para `audit.db` imutável, artifacts brutos, screenshots, imagens, payloads grandes, manifests, evidência de provider, bundles e snapshots de relatório materializados.

Não tratar armazenar tudo no PostgreSQL e usar object storage como alternativas equivalentes. Binários grandes no banco relacional podem ampliar WAL, replicação, backup, restore, manutenção, tráfego e contenção do banco transacional.

## 9. Requisitos candidatos - relatórios dinâmicos

Fluxo conceitual:

```text
dados persistidos
      ↓
read model
      ↓
contrato de relatório
      ↓
template versionado
      ↓
HTML
```

Requisitos mínimos:

1. Renderer é somente leitura.
2. Abrir relatório não executa crawling.
3. Abrir relatório não chama provider externo.
4. Abrir relatório não recalcula scoring já materializado como nova execução.
5. Abrir relatório não modifica evidência fonte.
6. Filtros alteram somente a projeção.
7. Todo dado necessário à apresentação existe fora do HTML.
8. Ausência de dado continua ausência; não vira zero ou sucesso artificial.
9. Regras de tenant e autorização permanecem no servidor.
10. Templates e contratos são versionados.
11. Auditorias antigas possuem política explícita de compatibilidade.
12. Exportações materializadas registram versão do renderer/contrato usado.

## 10. Snapshot materializado versus relatório dinâmico

Mesmo com visualização normal dinâmica, snapshots imutáveis podem continuar úteis para auditoria externa, exportação, anexação, preservação da apresentação e governança. A decisão futura deve distinguir fonte de verdade, visualização normal e snapshot de apresentação.

## 11. Versionamento necessário

Uma arquitetura de relatório dinâmico deve considerar, no mínimo:

- `auditor_version`;
- `ruleset_version`;
- `sari_version`;
- `scoring_version`;
- versão do schema de evidência;
- versão do manifest;
- versão do read model;
- versão do contrato de relatório;
- versão do renderer/template.

O SaaS não deve renderizar uma auditoria histórica com interpretação incompatível sem deixar explícitas as versões aplicadas.

## 12. Segurança e isolamento

Se implementado, o modelo deve prever HTTPS fora de loopback, autenticação forte do Runner, tokens curtos quando aplicável, rotação/revogação, segredo fora da linha de comando, isolamento de tenant, autorização por objeto, prevenção de traversal, limites de tamanho, validação de conteúdo, proteção contra sobrescrita da evidência, criptografia, logs de acesso, proteção contra replay e políticas de retenção/exclusão.

## 13. Confiabilidade operacional

Devem ser definidos retry, backoff, idempotência, retomada, checksum, timeout, health/heartbeat do Runner quando necessário, fila local de sincronização, falta de espaço, indisponibilidade parcial de PostgreSQL/object storage, reconciliação posterior, observabilidade, métricas e dead-letter ou mecanismo equivalente.

## 14. Decisões ainda em aberto

1. fornecedor de object storage;
2. formato de empacotamento do bundle;
3. granularidade de artifacts no storage;
4. quanto do conteúdo detalhado será normalizado no PostgreSQL;
5. desenho do read model;
6. enrollment do Runner;
7. duração/formato das credenciais;
8. política offline;
9. entitlement comercial;
10. quotas;
11. estratégia de build para separar desenvolvimento de distribuição oficial;
12. retenção e exclusão;
13. região/residência dos dados;
14. migração de AUDs locais existentes;
15. snapshot HTML/PDF imutável;
16. compatibilidade de renderer;
17. cache/CDN;
18. escopo de runners privados/remotos.

## 15. O que esta evolução não deve alterar por consequência

- fórmulas do SARI;
- `SCORE-GEO-004`;
- classificação de findings;
- coleta de evidências apenas para satisfazer o SaaS;
- integridade ou conteúdo dos artifacts;
- autoridade da evidência da AUD;
- imutabilidade da fonte pela camada Web;
- segurança de secrets;
- existência de um único motor de auditoria.

Falha de upload também não pode ser convertida em sucesso de persistência central.

## 16. Sequência sugerida se houver aprovação

```text
1. contrato de Runner e autorização
        ↓
2. protocolo de persistência/sincronização
        ↓
3. object storage + referências no control plane
        ↓
4. read model central
        ↓
5. renderer SaaS dinâmico
```

Relatório dinâmico não deve preceder a definição da autoridade dos dados que consumirá.

## 17. Critérios de revisão futura

Antes de iniciar implementação, revisar estado real do SaaS, permanência do executor local, modelo comercial, requisitos enterprise, privacidade, retenção, custo operacional, maturidade do schema, estabilidade do contrato de AUD, estabilidade dos relatórios, impacto de instalação/upgrade, operação offline e necessidade de runners privados.

A revisão deve terminar em uma das decisões abaixo:

- **IMPLEMENTAR** - converter esta avaliação em especificações e entregas versionadas.
- **SUBSTITUIR** - o problema continua válido, mas outra arquitetura passa a prevalecer.
- **MANTER PENDENTE** - ainda não há informação ou prioridade suficiente.
- **DESCONTINUAR** - a direção do produto tornou estes requisitos desnecessários.

## 18. Relação com a documentação vigente

Este documento complementa, mas não substitui:

- `PRODUCT_PLATFORM_ARCHITECTURE.md`;
- `POSTGRESQL_MIGRATION_STRATEGY.md`;
- `SAAS_PILOT_WEB.md`;
- `WEB_API_FOUNDATION.md`;
- `IDENTITY_AND_ACCESS.md`;
- `EXECUTION_SCHEDULING.md`;
- `OUTPUTS_AND_ARTIFACTS.md`.

Quando houver conflito, prevalece o contrato implementado e documentado como vigente. Este arquivo registra deliberadamente gaps e decisões futuras ainda não aprovadas.

## 19. Rastreabilidade

- Issue de acompanhamento: https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/163
- O encerramento da issue deve registrar a decisão arquitetural final e, quando aplicável, apontar para os documentos que substituírem esta avaliação.