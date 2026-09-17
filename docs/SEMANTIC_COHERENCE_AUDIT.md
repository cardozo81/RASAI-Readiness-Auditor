# Auditoria de Coerência Semântica da Propriedade Digital

## Objetivo

A Auditoria de Coerência Semântica compara **contexto/intenção declarados** com **evidência observável** da propriedade digital e usa IA somente para a interpretação semântica que não pode ser obtida com segurança por regras determinísticas.

Ela pertence ao `CAT-03 · Conteúdo, semântica e dados estruturados` como diagnóstico. Implementações/correções derivadas pertencem ao `CAT-09 · Remediações`.

A capacidade não cria score proprietário de E-E-A-T, não altera implicitamente `SARI-001`/`SCORE-GEO-004` e não transforma inferência de IA em fato canônico.

## Três fontes de verdade

O runtime mantém separadas:

1. **contexto declarado** pelo operador/control plane;
2. **evidência observada** pelo crawler/browser/regras determinísticas;
3. **interpretação da IA**, sempre evidence-bound e com confiança/IDs de evidência.

Uma conclusão de coerência deve poder ser lida como:

> Foi declarado X; foram observados A/B/C; a interpretação evidence-bound indica Y; o resultado da comparação é Z.

## Contexto da propriedade

Os campos são não secretos, opcionais e usam `auto` por padrão:

- `RASAI_PROPERTY_BUSINESS_SECTOR`
- `RASAI_PROPERTY_BUSINESS_DESCRIPTION`
- `RASAI_PROPERTY_PRIMARY_OFFERING`
- `RASAI_PROPERTY_TARGET_AUDIENCE_PROFILE`
- `RASAI_PROPERTY_PRIMARY_GOAL`
- `RASAI_PROPERTY_POSITIONING`

Texto livre é tratado como **dado não confiável**. Texto inserido nesses campos nunca pode ser executado ou promovido a instrução de sistema/provider.

`market` não é duplicado nesse perfil: continua sendo configuração global da AUD.

## Contexto editorial, risco e confiança

Permanecem os campos canônicos:

- `RASAI_PAGE_PURPOSE`
- `RASAI_INTENDED_AUDIENCE`
- `RASAI_CONTENT_ORIGIN`
- `RASAI_CONTENT_RISK_PROFILE`
- `RASAI_YMYL_CATEGORY`
- `RASAI_EXPERIENCE_REQUIREMENT`
- `RASAI_FRESHNESS_SENSITIVITY`

YMYL aumenta o rigor interpretativo quando aplicável, mas não produz nota YMYL/E-E-A-T. Sinais como autoria, responsável, suporte de claims e atualidade são observados pelo CAT-03; não são qualidades autodeclaradas.

## AUTO

`auto` significa ausência de declaração explícita. Quando IA estiver habilitada, o modelo pode produzir uma hipótese baseada apenas nas evidências fornecidas.

Uma hipótese AUTO:

- não sobrescreve a configuração;
- não vira fato da Property;
- não entra no score por si só;
- deve usar `NOT_DETERMINABLE` quando não houver suporte suficiente;
- pode ser apresentada como sugestão para uma auditoria futura, mas requer confirmação humana para virar contexto declarado.

## Gate de coleta antes da IA

A primeira chamada semântica de IA só é elegível depois de o corpus inteiro necessário ao CAT-03 estar materializado.

Ordem normativa:

```text
descoberta e coleta
  -> renderização e snapshots
  -> extração e evidências
  -> contexto técnico aplicável
  -> extração de conteúdo
  -> congelamento do contexto editorial + perfil da propriedade
  -> semantic_corpus_manifests = READY
  -> primeira chamada semântica de IA
```

O gate valida que todas as páginas/snapshots pertencem à AUD, persiste o contexto efetivo e grava um hash do corpus. Uma chamada para snapshot fora do manifesto READY é recusada antes de chegar ao provider.

Essa regra não cria um roteador CAT-03. A chamada continua usando o mesmo provider/routing session global do RASAi, preservando AUTO routing, retries, circuit breaker, pricing, `ai_provider_attempts` e `ai_exchange_log`.

## Coerência por página

A mesma chamada estruturada que já executa a análise semântica BR-GEO retorna também os critérios `SC-P*`:

| ID | Comparação |
|---|---|
| `SC-P01` | título × conteúdo |
| `SC-P02` | headings/hierarquia × conteúdo |
| `SC-P03` | propósito da página × conteúdo/intenção |
| `SC-P04` | público × linguagem/profundidade |
| `SC-P05` | oferta principal × conteúdo |
| `SC-P06` | posicionamento × conteúdo |
| `SC-P07` | entidades × conteúdo |
| `SC-P08` | dados estruturados × conteúdo |
| `SC-P09` | entidades estruturadas × entidades observadas |
| `SC-P10` | CTA × propósito/objetivo |
| `SC-P11` | claims × suporte observável |
| `SC-P12` | autoria/responsabilidade × risco/confiança |
| `SC-P13` | freshness × sensibilidade temporal |

Estados permitidos:

- `COHERENT`
- `PARTIAL`
- `INCOHERENT`
- `NOT_DETERMINABLE`
- `NOT_APPLICABLE`

`COHERENT`, `PARTIAL` e `INCOHERENT` exigem IDs de evidência fornecidos pelo RASAi.

## Sinais normalizados da propriedade

Cada chamada page-level pode retornar observações evidence-bound para:

- `organization_identity`
- `business_sector`
- `primary_offering`
- `target_audience_profile`
- `primary_goal`
- `positioning`

Esses sinais continuam sendo **observações/inferências da página**, não fatos declarados.

## Coerência entre páginas

Não existe segunda chamada obrigatória de IA para o cross-page. Depois de todas as páginas terem seus resultados persistidos, o RASAi agrega deterministicamente os resultados page-level em:

- `SC-X01` identidade organizacional;
- `SC-X02` oferta principal;
- `SC-X03` público-alvo;
- `SC-X04` posicionamento;
- `SC-X05` objetivo/CTA;
- `SC-X06` propósito das páginas × contexto da propriedade.

O agregador evita tratar diferenças lexicais automaticamente como contradição factual. Em sinais livres sem contexto explícito suficiente, divergência nominal tende a `PARTIAL`, não `INCOHERENT`.

## Persistência no audit.db

A execução pode materializar:

- `property_semantic_contexts` - snapshot do contexto declarado usado;
- `semantic_corpus_manifests` - gate/hash do corpus antes da IA;
- `semantic_coherence_assessments` - avaliações page-level;
- `semantic_property_signals` - sinais observados por página;
- `property_semantic_summaries` - agregação cross-page.

Essas tabelas são diagnósticas. Elas não participam automaticamente da fórmula de score.

## Console local

A preparação do CAT-03 é segmentada em:

```text
Contexto da propriedade
Contexto editorial
Risco e confiança
Análise semântica por IA
```

As seis novas variáveis pertencem ao catálogo canônico de configurações do console. Por serem não secretas, podem ser mantidas somente na sessão ou persistidas em `rasai-console.ini` pelo fluxo padrão do console.

Remediação por IA não é apresentada como componente funcional do CAT-03; pertence ao CAT-09.

## SaaS

O control plane mantém um perfil semântico reutilizável por Property em entidade própria, sem misturar os campos com a identidade técnica da tabela `properties`.

Endpoints:

- `GET /api/v1/properties/{property_id}/semantic-profile`
- `PUT /api/v1/properties/{property_id}/semantic-profile`

Leitura respeita escopo de tenant/projeto. Atualização requer papel com permissão de gerenciamento de execução e usa revisão otimista.

Ao enfileirar uma AUD:

1. o perfil atual da Property preenche somente campos não explicitados no payload;
2. override explícito do job, inclusive `auto`, tem precedência;
3. os seis valores efetivos são gravados no payload durável do job;
4. alteração posterior do perfil da Property não muda uma AUD já enfileirada.

## Relatórios

`CAT-03` mostra:

- contexto efetivamente usado;
- estado do gate/corpus;
- matriz resumida de coerência da propriedade;
- matriz resumida por página;
- drill-down de diagnóstico/evidência;
- entidades e dados estruturados já existentes.

Provider, request/response sanitizados, tokens, custos, retries e fallback permanecem em **IA e integrações**.

`CAT-09` é o local para ações/remediações derivadas das divergências. O CAT-03 pode apenas apontar que existe remediação relacionada.

## Falhas e degradação

A indisponibilidade de IA não invalida o CAT-03 inteiro. Conteúdo/estrutura, JSON-LD e baseline determinística permanecem válidos quando coletados.

Exemplo:

```text
CAT-03                         CONCLUÍDO COM LIMITAÇÕES
Conteúdo / estrutura           CONCLUÍDO
JSON-LD                        CONCLUÍDO
Contexto                       CONCLUÍDO
Coerência semântica por IA     NÃO DISPONÍVEL
Coerência entre páginas        NÃO DISPONÍVEL
```

## Multimodalidade

Análise real do conteúdo visual de imagens é evolução posterior. Alt text, metadados e artefatos existentes podem continuar sendo evidência determinística, mas o RASAi não deve declarar que interpretou visualmente uma imagem sem uma chamada multimodal explícita e rastreável.
