# Improvement Intelligence - análise profunda e melhorias

## Objetivo

`IMPROVEMENT-INTELLIGENCE-001` transforma evidências já coletadas pelo RASAi em um backlog de melhoria por **uma única URL explicitamente configurada**.

A feature é deliberadamente separada do `SARI-001`/`SCORE-GEO-004`:

- **SARI-001/SCORE-GEO-004 mede** readiness de forma determinística;
- **Improvement Intelligence interpreta e recomenda**;
- **Opportunity Priority** ordena correções pelo impacto potencial, severidade, confiança e esforço;
- **nova auditoria / before-after comprova** o ganho efetivamente observado.

Nenhuma sugestão de IA altera automaticamente score, Coverage, Confidence, gates ou posição SERP.

## Restrição de URL única

A análise profunda só é habilitada quando a execução possui exatamente uma URL de entrada.

O crawler normal pode descobrir páginas auxiliares segundo o limite da auditoria, mas o estudo profundo permanece vinculado à URL explicitamente informada. Arquivo TXT ou payload SaaS com múltiplas URLs bloqueia a feature antes da chamada de IA.

Essa restrição preserva contexto específico, evita generalizações entre páginas, limita custo/token e mantém o relatório acionável por elemento/URL.

## Evidências correlacionadas

Quando disponíveis no mesmo `AUD-*/audit.db` e nos artifacts associados, a feature reutiliza:

- Findings, RuleExecutions e Evidences do core;
- HTML bruto/renderizado e snapshots;
- `title`, meta description, canonical, headings e landmarks;
- imagens, links e botões observados;
- PageSpeed/Lighthouse, categorias, savings e referências DOM quando fornecidas;
- Core Web Vitals/CrUX persistidos;
- `robots.txt`, sitemap/feed, `llms.txt` e diagnósticos de discovery;
- SERP Observation e Competitive Search & Content Intelligence, quando executados;
- headers HTTP persistidos para postura de segurança passiva.

A feature não amplia silenciosamente o escopo de rede e não cria um segundo crawler competitivo.

## Domínios de análise

O usuário pode selecionar um subconjunto de:

- `TECHNICAL_HTML` - problemas técnicos/HTML;
- `SEMANTICS_STRUCTURE` - headings, landmarks e coerência semântica;
- `CONTENT` - clareza, completude e texto da página;
- `SEARCH_RANKING` - gaps observados em Search/SERP;
- `FILES_DISCOVERY` - robots/sitemap/llms e descoberta;
- `PERFORMANCE` - oportunidades Lighthouse/performance;
- `ACCESSIBILITY` - problemas automatizáveis de acessibilidade;
- `BEST_PRACTICES` - melhores práticas observadas;
- `SECURITY` - postura de segurança passiva;
- `AI_ACCESS` - crawlability, semântica e compreensão por agentes/IA.

## Segurança

O domínio `SECURITY` é **passivo**.

O RASAi pode apontar, quando a evidência foi capturada, ausência ou configuração de HTTPS, CSP, HSTS, framing, `X-Content-Type-Options`, `Referrer-Policy`, atributos de cookies, exposição aparente de versão e achados Lighthouse relacionados.

Ausência de header é reportada como postura/configuração observada, não como prova de vulnerabilidade explorável. A feature não executa payloads, fuzzing, bypass de autenticação, exploração XSS/SQLi/SSRF ou pentest ativo.

## Search / SERP

Quando Search Intelligence existe na auditoria, o relatório pode usar query, posição observada, resultados à frente, gaps determinísticos e features das páginas competitivas que foram explicitamente adquiridas.

A IA pode sugerir conteúdo/estrutura que reduza gaps observados, mas é proibido concluir que uma alteração **causará** determinada posição. Ranking é tratado como observação correlacional.

## HTML original x HTML sugerido

Para findings técnicos com fragmento/selector observável, `improvement-intelligence.html` pode mostrar selector, HTML original, HTML sugerido, diferenças, justificativa e forma de validação pós-deploy.

A sugestão continua exigindo revisão humana.

## Degradação atual e benefício esperado

Toda recomendação de IA deve permanecer vinculada às evidências disponíveis e explicar o problema/limitação observada e o benefício qualitativo razoável da correção. O benefício é hipótese evidence-bound, não promessa.

A IA não pode garantir ganho de ranking, tráfego, conversão, receita, segurança ou performance nem inventar percentuais. O ganho efetivo depende de nova medição/before-after.

## Priorização

Cada recomendação recebe prioridade derivada de severidade do finding, dimensões potencialmente afetadas, confiança e esforço (`LOW`, `MEDIUM`, `HIGH`).

As dimensões de impacto são Performance, SEO, Best Practices, Accessibility, AI Access e Security.

Essa prioridade **não é SARI** e não deve ser usada como score metodológico de readiness.

## Seleção e orquestração de IA

Improvement Intelligence **não possui provider, modelo ou reasoning próprios**. Quando habilitada, usa a configuração principal de IA da mesma execução.

Configuração principal explícita:

```text
ai_provider = <provider-do-registry>
ai_model = <modelo-opcional>
ai_reasoning = <reasoning-opcional>
```

Nesse modo, a análise profunda usa o mesmo provider configurado para a execução, desde que ele suporte o contrato estruturado necessário.

Configuração principal automática:

```text
ai_provider = auto
```

Nesse modo, a necessidade `IMPROVEMENT_INTELLIGENCE` reutiliza a política canônica existente:

1. providers configurados e elegíveis ao `AUTO`;
2. exclusões e estado de saúde da execução;
3. estimativa de custo por provider/modelo/reasoning;
4. prioridade pelo menor custo estimado conforme a política vigente;
5. mesma classificação de falhas;
6. mesma quarentena/circuit breaker;
7. fallback para o próximo candidato elegível;
8. término no primeiro sucesso ou no esgotamento da cadeia.

A feature não possui política própria de ordenação, quarentena, circuit breaker ou número de tentativas. O contrato especializado continua responsável apenas pelo prompt, schema, evidências e validação da resposta.

Configurações exclusivas da feature permanecem limitadas a ativação, domínios, teto de recomendações, timeout da necessidade e idioma preferencial.

### Idioma de análise

`RASAI_AI_ANALYSIS_LANGUAGE` define o idioma preferencial das explicações/textos sugeridos.

- `auto` - usa o idioma principal da auditoria;
- ou tag BCP-47 como `pt-BR`, `en-US`, `es-ES`.

Esse parâmetro não força o idioma da página nem substitui evidência real do conteúdo.

## Console interativo

O item **13. Análise profunda URL** controla somente a habilitação e os parâmetros próprios da análise profunda.

A configuração persistida em `[improvement_intelligence]` contém:

- `enabled`;
- `domains`;
- `max_recommendations`;
- `timeout_seconds`.

Provider, modelo e reasoning vêm exclusivamente da configuração principal `[ai]`. Credenciais nunca são gravadas no INI.

O item 13 deve indicar qual seleção principal será usada (`provider` explícito ou `AUTO`) e bloquear a habilitação quando a IA principal estiver `none`.

## SaaS / Control Plane

O contrato SaaS usa `ExecutionJob.payload` e permanece secret-free.

Campos específicos da feature:

- `improvement_intelligence`;
- `improvement_domains`;
- `improvement_max_recommendations`;
- `improvement_ai_timeout_seconds`;
- `ai_analysis_language`.

A seleção de IA é feita somente pelos campos canônicos do job de auditoria:

- `ai_provider`;
- `ai_model`;
- `ai_reasoning`.

Quando `improvement_intelligence=true`, `urls` deve conter exatamente uma URL e `ai_provider` deve estar habilitado. `auto` é válido e aciona a mesma orquestração do core.

Credenciais continuam no boundary seguro do worker/integration/environment e não entram no payload durável.

## Variáveis de ambiente próprias

A feature reconhece apenas controles próprios de escopo/comportamento:

```text
RASAI_IMPROVEMENT_INTELLIGENCE
RASAI_IMPROVEMENT_DOMAINS
RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS
RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS
RASAI_AI_ANALYSIS_LANGUAGE
```

A seleção de provider/modelo/reasoning não é duplicada em variáveis de Improvement Intelligence.

## Persistência e idempotência

Tabelas:

- `improvement_intelligence_runs`;
- `improvement_intelligence_findings`;
- `improvement_intelligence_recommendations`.

A configuração efetiva e a evidência recebem fingerprints. Se ambas são idênticas e já existe execução completa, o runtime pode reutilizar o resultado para evitar nova chamada paga.

Os campos de provider/modelo/reasoning persistidos no resultado representam a seleção/execução efetiva para rastreabilidade, não uma configuração paralela da feature.

## Telemetria de IA

Cada tentativa usa a tabela canônica `ai_provider_attempts` com provider/modelo/reasoning, horário, duração, status, tokens, custo estimado quando calculável e diagnóstico.

O contrato é identificado por:

```text
semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001
```

O relatório próprio contém o recorte de consumo dessa análise e a superfície canônica de Uso de IA pode atribuir o mesmo consumo ao contrato correspondente.

## Relatórios

A superfície canônica é `report/improvement-intelligence.html`, no grupo **Ações e referência**.

O HTML separa backlog priorizado derivado pela IA, findings/evidências determinísticos, HTML original/sugerido quando aplicável, consumo de IA e fronteiras metodológicas.

O relatório é gerado mesmo quando a feature não foi executada, deixando o estado explícito.

## Relatório consolidado

O consolidado usa o vocabulário canônico de dimensões do `SCORE-GEO-004`. Improvement Intelligence, Lighthouse/Core Web Vitals, Apdex, SERP e postura de segurança são complementares e não são artificialmente promediados dentro da série temporal do SARI.

A análise especialista do próprio consolidado possui telemetria de IA separada e também utiliza a orquestração canônica.

## Validação pós-deploy

Uma recomendação é hipótese de melhoria até que a URL seja auditada novamente.

```text
evidência -> finding -> recomendação -> prioridade -> deploy -> nova auditoria -> before/after
```

Somente a nova medição pode afirmar o ganho efetivamente observado.
