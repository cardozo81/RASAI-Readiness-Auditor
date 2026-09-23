# Validação e reversibilidade - relatório consolidado longitudinal

**Estado:** vigente.

## Contrato

**Nome apresentado:** **Relatório Consolidado Longitudinal**  
**Formato público:** **001**  
**Identificador técnico do formato:** `CONS-5`

Contratos associados:

```text
TEMPORAL-APDEX-001
CONSOLIDATED-EVOLUTION-001
CONSOLIDATED-SPECIALIST-001
CONSOLIDATED-LONGITUDINAL-001
CONSOLIDATED-CATALOG-LONGITUDINAL-006
CONSOLIDATED-EXECUTION-001
CONSOLIDATED-SOURCE-GOVERNANCE-003
CONSOLIDATED-DECISION-CONTEXT-002
CONSOLIDATED-AI-CONTEXT-001
CONSOLIDATED-MATERIALIZATION-003
```

## Invariantes

A validação deve comprovar:

- exatamente uma URL por consolidado;
- exatamente um dispositivo;
- pelo menos duas auditorias elegíveis;
- BASE e ATUAL definidos pela ordem temporal;
- todas as auditorias selecionadas pertencem ao mesmo escopo longitudinal;
- `ALL`, `SUCCESS_ONLY` e `MANUAL` preservam seus contratos;
- nenhum `audit.db` é alterado;
- nenhum collector externo é reexecutado;
- Monitoring/Fix Verification continuam determinísticos;
- Mobile e Desktop não são misturados;
- o modo determinístico gera um **Relatório Consolidado Longitudinal** válido sem IA, preservando `CONS-5` como identificador técnico do formato;
- modo Determinístico e modo Determinístico + IA compartilham a mesma camada corporativa de decisão/governança; `rules-reference.html` é materializado sempre que existirem regras citadas, sem depender de `specialist-analysis.json`;
- a navegação não cria âncoras para **Análise por IA** ou **Correções técnicas** quando a seção correspondente não existe;
- `NOT_REQUESTED` é neutro e não degrada o encerramento;
- quando IA é solicitada, ela não recalcula scoring;
- cobertura integral de pricing no forecast especialista não produz `ALTA` confiança por si só; antes da execução, a incerteza de volume limita a confiança a `MÉDIA`, com `pricing_coverage` e `confidence_basis` explícitos;
- quando forecast existe, `report.html` apresenta confiança, cobertura de preços e base da confiança em linguagem humana, além dos valores monetários;
- uma AUD fonte incompleta não é ocultada e afeta governança/conclusividade conforme o contrato;
- o freshness de cada `report-catalog` fonte é verificado separadamente do `audit.db`: relatório desatualizado não altera a elegibilidade dos dados SQLite, mas deve ser sinalizado e não receber autolink;
- links para `report-catalog` stale já existentes no HTML-base também são removidos; não basta impedir somente novos autolinks;
- cada fonte materializa `source_revision_id` e digest lógico, além de `observation_at`, `revision_at` e `revision_mode`;
- RPR material posterior ao próximo marco gera governança explícita `*_AFTER_NEXT_OBSERVATION`; RPR sem item resolvido não cria revisão temporal material;
- `REPLAY_SAFE` posterior é informativo/contextual e não reduz confiança por si só; `LIVE_RECOLLECTION` posterior reduz a robustez longitudinal;
- quando o par de configuração é `UNRELATED`, o contexto da IA já recebe esse estado antes da chamada e linguagem que sugira comparação controlada deve ser rejeitada como erro de contrato;
- o validator de `UNRELATED` bloqueia afirmações **positivas** de equivalência/comparabilidade controlada, mas aceita formulações negativas corretas como “não há métrica comparável entre os marcos” ou “sem comparabilidade plena”;
- na projeção enviada à IA, a compatibilidade de escopo usa `scope_comparable` e a relação de configuração usa `configuration_pair_status`; o campo genérico `comparable` não é enviado ao provider;
- rótulos humanos de estados/domínios/controles aparecem em pt-BR, enquanto payloads técnicos brutos permanecem canônicos;
- blocos interpretativos produzidos por IA possuem marcador visual explícito de origem;
- o SARI exibido no CONS é somente o `OVERALL_READINESS` persistido, nunca um recálculo.

## Fonte de verdade

As fontes são `AUD-*/audit.db` e artifacts persistidos.

O consolidador:

- lê em modo somente leitura;
- não migra schema;
- não persiste secrets;
- pode reconstruir `.rasai/consolidated-index.db`;
- materializa apenas artefatos derivados em `consolidated/CONS-*` e `consolidated/executions/CONRUN-*`;
- preserva `CONRUN-*` mesmo quando uma falha impede a criação do relatório final.

## Intervalos

Com auditorias ordenadas:

```text
AUD-1
AUD-2
AUD-3
AUD-4
```

devem existir análises para:

```text
INTERVALO-001 = AUD-1 -> AUD-2
INTERVALO-002 = AUD-2 -> AUD-3
INTERVALO-003 = AUD-3 -> AUD-4
GLOBAL        = AUD-1 -> AUD-4
```

Nenhum intervalo consecutivo pode ser omitido pela IA.

## Catálogos

A validação longitudinal dos catálogos deve cobrir todos os CAT-* registrados no catálogo canônico.

Por intervalo, validar quando aplicável:

- estado;
- métricas;
- configuração efetiva;
- fontes persistidas;
- registros alterados;
- ausência de dado;
- estabilidade positiva;
- persistência problemática.

O HTML dos catálogos não é fonte de dados para essa comparação.

## Cobertura integral e projeção da IA

Validar:

- todos os CATs encontrados nos marcos inicial/final aparecem na cobertura do HTML;
- mudanças não estáveis aparecem integralmente nas tabelas por intervalo;
- itens estáveis permanecem disponíveis em blocos recolhidos;
- `longitudinal-evidence.json` é criado e referenciado pelo manifesto;
- SHA-256 do artifact integral é registrado;
- compactação da IA não modifica o artifact integral;
- o contexto externo usa `CONSOLIDATED-AI-CONTEXT-001`;
- um cenário sintético maior que o smoke original permanece dentro de 80 mil tokens estimados;
- se nem a projeção mínima couber, a chamada externa é bloqueada antes do provider.

## Estados

A apresentação deve distinguir:

```text
melhora observada
regressão
novo sinal
dado indisponível
não comparável
correção verificada
correção parcial
problema persistente
estável dentro do esperado
estável exigindo atenção
```

Não aceitar linguagem que transforme associação temporal em causalidade.

## IA

A IA é opcional para o **Relatório Consolidado Longitudinal** (`CONS-5` como identificador técnico).

### Modo determinístico

Validar:

- `specialist_ai.requested=false`;
- `specialist_ai.required=false`;
- `specialist_ai.status=NOT_REQUESTED`;
- `generation_mode=DETERMINISTIC`;
- `longitudinal-evidence.json`, `decision-context.json` e `execution.json` existem;
- `specialist-analysis.json` e `ai-exchanges.json` não são artifacts obrigatórios nem são criados apenas para representar ausência de IA;
- a seção longitudinal determinística continua materializada no HTML;
- a confiabilidade do consolidado é calculada independentemente da IA.

### Modo determinístico + IA

Perfil canônico:

```text
EVOLUTION
```

Validar:

- a preparação determinística antecede a chamada externa;
- profile id e versão são registrados;
- structured output é usado;
- somente `evidence_ids` fornecidos pelo RASAi podem ser citados;
- intervalos, domínios, estratégia e trade-offs permanecem rastreáveis;
- `INDETERMINADO` é usado quando não houver sustentação suficiente;
- tentativas, provider, modelo, reasoning, tokens e custo são registrados quando disponíveis;
- fallback/retry e erro técnico são registrados por tentativa;
- previsão pré-execução e uso observado permanecem distintos;
- request e response sanitizados são persistidos;
- `longitudinal-evidence.json` preserva a evidência integral local;
- `specialist-analysis.json` e `ai-exchanges.json` integram o pacote quando IA é efetivamente solicitada.

Se a IA solicitada não concluir, validar que a camada determinística já construída permanece preservada e que o manifesto diferencia claramente indisponibilidade de `NOT_REQUESTED`.

### Retry do consolidado

Validar somente no modo com IA:

1. primeira cadeia visita cada candidato elegível uma vez;
2. falha transitória pode iniciar uma segunda e última rodada;
3. somente candidatos retryable e ainda elegíveis participam;
4. erro terminal não é repetido;
5. `Retry-After` segue a política vigente;
6. tentativas permanecem registradas no `CONRUN-*`.

## Fingerprint e dedupe

O fingerprint inclui:

```text
CONS-5
TEMPORAL-APDEX-001
CONSOLIDATED-LONGITUDINAL-001
CONSOLIDATED-CATALOG-LONGITUDINAL-006
CONSOLIDATED-MATERIALIZATION-003
filtros canônicos
configuração não secreta de IA
fingerprint das fontes
```

Um artifact só é reutilizável se:

- `report_format_version=CONS-5`;
- `materialization_contract=CONSOLIDATED-MATERIALIZATION-003`;
- o fingerprint corresponder;
- `temporal_apdex.contract=TEMPORAL-APDEX-001`;
- `longitudinal_analysis.contract=CONSOLIDATED-LONGITUDINAL-001`;
- `longitudinal_analysis.ai_status=COMPLETE`;
- `decision_context.contract=CONSOLIDATED-DECISION-CONTEXT-002`;
- `source_governance.contract=CONSOLIDATED-SOURCE-GOVERNANCE-003`;
- o pacote possuir hashes dos artifacts obrigatórios, incluindo `execution.json`;
- snapshots de revisão de materialização anterior não serem reutilizados, mesmo que os dados-fonte e os filtros sejam idênticos.

## Console

Validar pontualmente:

1. a tela separa **Gerar novo** e **Histórico**;
2. a listagem permite pesquisa por Audit ID, domínio/URL ou dispositivo;
3. após o primeiro marco, somente mesma URL e mesmo dispositivo permanecem elegíveis;
4. BASE/ATUAL são definidos cronologicamente;
5. auditorias intermediárias oferecem `ALL`, `SUCCESS_ONLY` e `MANUAL`;
6. sem intermediárias, a etapa de política não cria seleção artificial;
7. o usuário escolhe entre **Determinístico** e **Determinístico + IA**;
8. prévia de custo e autorização aparecem somente quando IA é escolhida;
9. a confirmação mostra URL, dispositivo, BASE, ATUAL, período, quantidade e política;
10. a execução mostra etapas concluídas, corrente e pendentes;
11. o histórico apresenta CONS ID, URL, dispositivo, período, quantidade de AUDs, modo e confiabilidade;
12. o fluxo de consolidação não altera o launcher `abrir-rasai-console.cmd`.

## SaaS

Validar os endpoints do consolidado:

```text
GET  /api/v1/projects/{project_id}/consolidated-report-candidates
GET  /api/v1/projects/{project_id}/consolidated-reports
GET  /api/v1/projects/{project_id}/consolidated-reports/{cons_id}/result
POST /api/v1/projects/{project_id}/consolidated-reports
```

Validar:

- autorização por projeto;
- property e environment pertencem ao escopo;
- request é orientado por `baseline_audit_id`, `current_audit_id` e `selection_mode`;
- `use_ai=false` não exige provider;
- `use_ai=true` pode ser aceito sem provider apto; nesse caso o CONS determinístico é materializado e a camada de IA deve ficar `NOT_CONFIGURED`/indisponível sem chamada externa;
- payload vira `REPORT_REFRESH` com `surface=consolidated`;
- API e worker revalidam os `audit_ids` contra o tenant autorizado;
- o worker SaaS usa o mesmo `rasai.consolidation.service.generate`; não existe implementação paralela de revisão temporal, source revision, freshness, links ou validação da IA;
- o HTTP apenas enfileira/projeta o resultado; não recalcula nem reinterpreta governança do CONS;
- mesma URL e mesmo dispositivo são revalidados no servidor;
- resultado retorna referência relativa do relatório;
- histórico não depende da lista de jobs para representar CONS materializados;
- secrets não entram no payload durável.

A implementação não exige novo tipo de job nem migração de schema.

## Validação de eficiência sem mudança semântica

Para uma geração nova, validar de forma isolada:

- uma única preparação longitudinal pesada dentro da execução interativa;
- preview e geração compartilham o mesmo `LongitudinalPreparation`;
- a prévia efetivamente autorizada é a mesma registrada no `CONRUN-*`;
- mudança na cadeia de providers, modelo, reasoning, preço ou fallback após a autorização bloqueia a chamada externa e exige nova prévia;
- `Fix Verification` reutiliza o `ComparisonResult` do mesmo par;
- com N AUDs, Monitoring carrega N `AuditSnapshot` na construção longitudinal, em vez de reler os dois lados para cada comparação;
- para N AUDs, existem N comparações determinísticas nessa camada: N-1 intervalos consecutivos + marco inicial -> final;
- registros-fonte dos catálogos compartilham uma conexão SQLite read-only por AUD durante a construção do snapshot longitudinal;
- dedupe íntegro ocorre antes de `LongitudinalPreparation` e de `build_data`;
- alteração de source fingerprint, filtros canônicos ou revisão de materialização impede reuso;
- o packet integral preparado é idêntico ao packet produzido pela construção determinística sem reuso.

A otimização não autoriza cache global, cache persistente nas AUDs, alteração de `audit.db`, omissão de evidência ou estimativa de IA baseada em universo diferente do efetivamente enviado.

## Testes mínimos e isolados

Executar somente o necessário para os boundaries alterados:

1. `py_compile` dos módulos modificados;
2. seleção `ALL/SUCCESS_ONLY/MANUAL`;
3. geração determinística sem IA;
4. neutralidade de `NOT_REQUESTED`;
5. teste específico do contrato API do consolidado;
6. teste específico do worker para seleção tenant-scoped;
7. testes pontuais de apresentação do console modificada;
8. teste pontual do diagnóstico de integrações modificado.

Não executar suíte completa, crawl real, coletores externos, scoring amplo ou validação abrangente de HTML quando esses componentes não forem alterados.

## Integridade

Em teste com dois ou mais `AUD-*`:

1. calcular hash de cada `audit.db`;
2. gerar `CONS-5`;
3. recalcular os hashes;
4. exigir igualdade byte a byte.

## Reversibilidade

São derivados e removíveis:

```text
.rasai/consolidated-index.db
consolidated/CONS-*
consolidated/executions/CONRUN-*
```

A remoção não exige alteração ou migração dos `AUD-*`.

Veja também:

- [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md)
- [CONSOLIDATED_REPORTING_TEMPORAL.md](CONSOLIDATED_REPORTING_TEMPORAL.md)
- [SAAS_PILOT_WEB.md](SAAS_PILOT_WEB.md)
- [AI_TASK_PROFILES.md](AI_TASK_PROFILES.md)


## Validação de UX decisória

Validar pontualmente:

- primeira camada responde como estava, o que aconteceu, como está e onde agir primeiro;
- o índice aparece nominalmente como **Search & AI Readiness Index - Índice de Prontidão Search & IA**, com `SARI-001` apenas como identificador metodológico técnico;
- a confiança do Índice de Prontidão Search & IA nunca expõe enums ou rótulos operacionais em inglês e cobre estados conhecidos e desconhecidos com forma humana em pt-BR;
- dimensões da tabela do Índice de Prontidão Search & IA e da matriz histórica aparecem somente com rótulos pt-BR;
- categorias de ocorrências persistidas aparecem em pt-BR;
- `report.html` e `rules-reference.html` não impõem `max-width` ao `main`, e `rules-reference.html` não impõe `max-width` a `.rules-header-shell`;
- `details > summary` possui acabamento e indicação visual de expansão consistentes e mantém o texto alinhado à esquerda;
- cada `AUD-*` navegável abre `../../<AUD-ID>/report-catalog/index.html` em nova aba, sem reescrever payloads técnicos;
- resumo gerencial possui selo explícito de conteúdo gerado por IA;
- prioridades aparecem em ordem P0, P1, P2, P3;
- análise técnica de código/infraestrutura não é confundida com SEO, segurança, performance ou conteúdo;
- cada prioridade possui diagnóstico/causa provável, ação e evidências;
- `rules-reference.html` usa a mesma identidade visual e possui busca;
- ações de remediação em `rules-reference.html` usam rótulos humanos em pt-BR; enums como `REVIEW_AND_CORRECT` permanecem apenas nos artifacts técnicos;
- nomes de domínio, enums e variáveis internas não aparecem como rótulo primário em `report.html` ou `rules-reference.html` quando houver tradução inequívoca;
- Apdex temporal apresenta **Satisfeitas / Toleráveis / Frustradas**, KPM, perfil, calibração e pacing em linguagem humana, sem expor IDs internos de perfil ou pares `chave=valor` como leitura principal;
- blocos `pre`/`code`, IDs, contratos e payloads sanitizados preservam o conteúdo técnico canônico e não são reescritos pela humanização;
- governança da IA e request/response permanecem fora da leitura executiva e recolhidos por padrão;
- uma AUD não final produz alerta de série não conclusiva no topo do relatório.


## Escopo de dispositivo nas evidências de catálogo

- evidências com `device=MOBILE` entram apenas em consolidação Mobile;
- evidências com `device=DESKTOP` entram apenas em consolidação Desktop;
- evidências com `device=BOTH` entram em ambos os escopos e não podem ser omitidas do snapshot longitudinal;
- os totais e exemplos derivados devem permanecer rastreáveis ao `audit.db`.


## Fingerprint semântico das evidências

- IDs efêmeros emitidos novamente em cada AUD não devem produzir `EVIDENCIA_PERSISTIDA=ALTERADO` isoladamente;
- `diagnostic_id`, `suggestion_id`, `recommendation_id`, `remediation_group_id`, `finding_id`, `summary_id`, `sample_id`, `assessment_id`, `entity_observation_id`, `interpretation_id`, `acquisition_id`, `group_id`, `governance_id`, `remediation_id`, `resource_id`, `source_audit_id`, `source_observation_id`, `source_id`, `evidence_ids`, `evidence_ids_json`, `source_evidence_json`, `affected_findings` e `affected_pages` são ignorados somente no fingerprint comparativo;
- o conteúdo original continua preservado nos artifacts quando uma mudança semântica real é materializada;
- alteração em estado, valor observado, resultado, recomendação ou outro campo funcional continua diferenciando os registros.


## Paridade de fonte no CAT-02

- a contagem pública e o conjunto de registros longitudinais de `web_performance_attempts` devem usar apenas `service=PAGESPEED_INSIGHTS` no CAT-02;
- tentativa `CRUX_API` não pode inflar `EVIDENCIA_PERSISTIDA` do CAT-02;
- `web_performance_observations` só participa dessa fonte quando `accessibility_score` estiver presente;
- CAT-04 continua podendo consumir o conjunto completo de tentativas de desempenho conforme seu contrato próprio.

- `collected_at`, `materialized_at`, `consumed_at` e `lighthouse_fetch_time` não podem, isoladamente, produzir alteração longitudinal;
