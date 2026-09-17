# Contexto de análise de conteúdo — propósito, YMYL, confiança e coerência

## Objetivo

O RASAi mantém um **contexto editorial explícito** para evitar análise genérica de conteúdo. Esse contexto condiciona a interpretação semântica, mas não altera aritmeticamente `SARI-001`/`SCORE-GEO-004`, não cria score proprietário de E-E-A-T/YMYL e não representa fator oficial isolado de ranking.

A auditoria de conteúdo distingue dois escopos:

1. **perfil semântico da propriedade** — quem é o negócio/propriedade, sua oferta, público e objetivo;
2. **contexto editorial, risco e confiança da página** — propósito, público categórico, origem, YMYL, experiência e freshness.

O contrato completo está em [SEMANTIC_COHERENCE_AUDIT.md](SEMANTIC_COHERENCE_AUDIT.md).

## Contexto da propriedade

O perfil reutilizável usa:

- `RASAI_PROPERTY_BUSINESS_SECTOR`
- `RASAI_PROPERTY_BUSINESS_DESCRIPTION`
- `RASAI_PROPERTY_PRIMARY_OFFERING`
- `RASAI_PROPERTY_TARGET_AUDIENCE_PROFILE`
- `RASAI_PROPERTY_PRIMARY_GOAL`
- `RASAI_PROPERTY_POSITIONING`

Todos usam `auto` por padrão. Texto explícito é **contexto declarado pelo operador**, não evidência observada. Os valores são tratados como dados não confiáveis e nunca podem virar instruções executáveis para o provider.

## Contexto editorial da página

### `RASAI_PAGE_PURPOSE`

Valores: `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other`.

### `RASAI_INTENDED_AUDIENCE`

Valores: `auto`, `general`, `professional`, `mixed`.

`RASAI_INTENDED_AUDIENCE` é uma classificação estruturada da página. O perfil detalhado do público da propriedade fica em `RASAI_PROPERTY_TARGET_AUDIENCE_PROFILE`.

### `RASAI_CONTENT_ORIGIN`

Valores: `auto`, `first-party`, `third-party`, `user-generated`, `mixed`.

## Risco e requisitos de confiança

### `RASAI_CONTENT_RISK_PROFILE`

Valores: `auto`, `standard`, `ymyl`.

### `RASAI_YMYL_CATEGORY`

Valores: `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare`.

Validações:

- `risk_profile=standard` não aceita categoria YMYL explícita diferente de `none`/`auto`;
- `risk_profile=ymyl` não aceita `ymyl_category=none`.

YMYL aumenta o rigor da análise de confiança/suporte quando aplicável. Não produz uma nota YMYL/E-E-A-T.

### `RASAI_EXPERIENCE_REQUIREMENT`

Valores: `auto`, `required`, `beneficial`, `not-expected`.

Esse campo diferencia necessidade de experiência em primeira mão de expertise técnica/profissional. O RASAi não presume que ambos sejam exigidos em qualquer página.

### `RASAI_FRESHNESS_SENSITIVITY`

Valores: `auto`, `low`, `medium`, `high`.

Quando `high`, a interpretação aplica maior rigor a datas, períodos, qualificadores temporais e coerência entre sinais de atualização. O sistema não deve recomendar atualização artificial de data.

## E-E-A-T

E-E-A-T é usado como referência conceitual para interpretar sinais observáveis de confiança, experiência, expertise/atribuição e responsabilidade. O usuário não configura `E-E-A-T=alto`, `Trust=92%` ou equivalentes.

Sinais como autoria, responsável, credenciais apresentadas, suporte de claims, fontes e datas são **observados pelo CAT-03** e avaliados no contexto da página. Ausência de evidência deve resultar em `NOT_DETERMINABLE` quando não houver base suficiente para uma conclusão.

## AUTO

Configuração explícita tem precedência sobre inferência.

Quando um campo permanece `auto`, a configuração canônica continua sendo `AUTO`. Se IA estiver habilitada, o modelo pode produzir uma hipótese evidence-bound para aquela execução. Essa interpretação:

- não sobrescreve configuração;
- não vira fato canônico sobre a organização/página;
- não autoriza inventar credenciais, certificações, reputação, compliance, experiência pessoal ou processo editorial;
- deve usar `NOT_DETERMINABLE` quando a evidência não sustenta classificação segura;
- não entra diretamente em scoring.

Uma sugestão derivada de AUTO pode ser apresentada ao operador para futura confirmação, mas **IA recomenda contexto; humano confirma contexto**.

## Gate antes da IA

Configurar contexto não gera chamada externa por si só.

Antes da primeira chamada semântica, o runtime deve materializar o corpus completo necessário ao CAT-03 e congelar:

- páginas/snapshots da AUD;
- evidência de extração disponível;
- `ContentAnalysisContext` efetivo;
- `PropertySemanticProfile` efetivo.

Somente depois de `semantic_corpus_manifests.status=READY` o provider pode receber um `SemanticInput` daquela AUD. A ordem detalhada está em [SEMANTIC_COHERENCE_AUDIT.md](SEMANTIC_COHERENCE_AUDIT.md).

## Console

Na preparação do CAT-03 a UI usa grupos funcionais, não a antiga categoria genérica “IA - contexto editorial / YMYL”:

```text
Contexto da propriedade
Contexto editorial
Risco e confiança
Análise semântica por IA
```

Estado funcional esperado:

```text
Conteúdo / estrutura          INCLUÍDO
JSON-LD                       INCLUÍDO
Contexto da propriedade       AUTOMÁTICO / PERSONALIZADO / CONFIGURAR
Contexto editorial            AUTOMÁTICO / PERSONALIZADO / CONFIGURAR
Coerência semântica por IA    NÃO SOLICITADA / APTO / CONFIGURAR
```

`AUTO` é configuração válida e não representa pendência.

**Remediação por IA não é componente funcional do CAT-03.** CAT-03 diagnostica/evidencia; CAT-09 centraliza possíveis correções derivadas dos catálogos produtores.

As treze variáveis de contexto são não secretas e pertencem ao catálogo canônico do console. Quando o operador escolhe persistir, usam o fluxo normal do `rasai-console.ini`; não existe shadow config do CAT-03.

## Persistência por AUD

- `content_analysis_contexts` congela os sete campos editoriais/risco usados na execução;
- `property_semantic_contexts` congela os seis campos da propriedade usados na execução;
- `semantic_corpus_manifests` registra o gate/hash anterior à IA;
- avaliações de coerência e sinais observados são persistidos separadamente e nunca sobrescrevem os contextos declarados.

Alterar o `.ini`, Property Profile ou schedule depois do início não muda o contexto da AUD já materializada.

## SaaS

O perfil semântico reutilizável pertence à Property e é persistido em entidade própria. Ao criar um job `AUDIT`:

1. o perfil da Property fornece valores para campos não explicitados;
2. override explícito do job, inclusive `auto`, vence;
3. o payload durável do job recebe os seis valores efetivos;
4. o worker converte o mesmo contrato para os envs canônicos do core.

## Relatórios

O CAT-03 é a projeção canônica do diagnóstico de conteúdo/semântica:

- contexto efetivamente usado;
- estado do gate;
- coerência page-level;
- coerência cross-page/property-level;
- entidades;
- dados estruturados;
- evidências/drill-down.

Detalhes de provider, request/response sanitizados, tokens, retries, fallback e custo permanecem em **IA e integrações**.

Soluções detalhadas ficam no CAT-09.

## IA, custo e rastreabilidade

Toda chamada usa o contrato global de IA do RASAi. Permanecem rastreáveis, quando disponibilizados pelo provider/adapter:

- provider/model/reasoning;
- tentativas e decisões de retry/fallback;
- horários/duração;
- tokens de entrada/cache/saída/reasoning/total;
- custo estimado e pricing version;
- falhas técnicas/contratuais sanitizadas;
- `ai_provider_attempts`;
- `ai_exchange_log` com request/response sanitizados.

A auditoria de coerência não cria roteador, pricing ou exchange log paralelos.

## Base pública conceitual

Referências principais:

- Google Search Central — Creating helpful, reliable, people-first content: <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>
- Google Search Quality Rater Guidelines: <https://services.google.com/fh/files/misc/hsw-sqrg.pdf>

Essas referências ajudam a contextualizar propósito, utilidade, confiança e YMYL. O RASAi não afirma uma fórmula oficial de E-E-A-T nem converte as diretrizes em fator matemático proprietário de ranking.
