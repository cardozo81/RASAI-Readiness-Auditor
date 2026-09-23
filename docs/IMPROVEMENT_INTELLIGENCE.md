# Improvement Intelligence - análise profunda e melhorias

## Objetivo

`IMPROVEMENT-INTELLIGENCE-001` transforma evidências já coletadas pelo RASAi em um backlog de melhoria para **uma única URL explicitamente configurada**.

A capacidade é separada de `SARI-001` e `SCORE-GEO-004`:

- SARI/SCORE-GEO medem readiness segundo seus contratos;
- Improvement Intelligence interpreta evidências e recomenda ações;
- Opportunity Priority ordena correções por impacto potencial, severidade, confiança e esforço;
- uma nova auditoria comprova o ganho efetivamente observado.

Nenhuma sugestão de IA altera automaticamente score, Coverage, Confidence, gates ou posição SERP.

## Restrição de URL única

A análise profunda só é elegível quando a execução possui exatamente uma URL de entrada.

O crawler pode descobrir páginas auxiliares segundo o limite da auditoria, mas o estudo profundo permanece vinculado à URL explicitamente informada. Arquivo TXT ou payload com múltiplas URLs bloqueia a capacidade antes da chamada de IA.

Essa restrição preserva contexto específico, limita custo/token e mantém o resultado acionável por elemento/URL.

## Evidências correlacionadas

Quando disponíveis no mesmo `AUD-*/audit.db` e artifacts associados, a capacidade pode reutilizar:

- Findings, RuleExecutions e Evidences do core;
- HTML bruto/renderizado e snapshots;
- title, meta description, canonical, headings e landmarks;
- imagens, links e botões observados;
- PageSpeed/Lighthouse, categorias, savings e referências DOM;
- Core Web Vitals/CrUX persistidos;
- `robots.txt`, sitemap/feed, `llms.txt` e diagnósticos de discovery;
- Search Intelligence/SERP e Competitive Search & Content Intelligence, quando executados;
- headers HTTP persistidos para postura de segurança passiva.

A capacidade não amplia silenciosamente o escopo de rede e não cria um segundo crawler competitivo.

## Domínios de análise

O usuário pode selecionar um subconjunto de:

- `TECHNICAL_HTML`;
- `SEMANTICS_STRUCTURE`;
- `CONTENT`;
- `SEARCH_RANKING`;
- `FILES_DISCOVERY`;
- `PERFORMANCE`;
- `ACCESSIBILITY`;
- `BEST_PRACTICES`;
- `SECURITY`;
- `AI_ACCESS`.

## Segurança

O domínio `SECURITY` é passivo.

O RASAi pode interpretar evidências já capturadas, como HTTPS, CSP, HSTS, framing, `X-Content-Type-Options`, `Referrer-Policy`, atributos de cookies, exposição aparente de versão e achados Lighthouse relacionados.

Ausência de header é reportada como postura/configuração observada, não como prova de vulnerabilidade explorável. A capacidade não executa payloads, fuzzing, bypass de autenticação, exploração XSS/SQLi/SSRF ou pentest ativo.

## Search / SERP

Quando Search Intelligence existe na auditoria, o relatório pode usar query, posição observada, resultados à frente, gaps determinísticos e evidências competitivas que tenham sido explicitamente adquiridas.

A IA pode sugerir conteúdo/estrutura que reduza gaps observados, mas não pode concluir que uma alteração causará determinada posição. Ranking é tratado como observação correlacional.

## HTML original x HTML sugerido

Para findings técnicos com fragmento/selector observável, `cat-08.html` pode mostrar selector, HTML original, HTML sugerido, diferenças, justificativa e forma de validação pós-deploy.

A sugestão exige revisão humana.

## Benefício esperado

Toda recomendação permanece vinculada às evidências disponíveis e explica o problema/limitação observada e o benefício qualitativo razoável da correção.

O benefício é hipótese evidence-bound, não promessa. A IA não garante ganho de ranking, tráfego, conversão, receita, segurança ou performance nem inventa percentuais. O ganho efetivo depende de nova medição.

## Priorização

Cada recomendação recebe prioridade derivada de severidade, dimensões potencialmente afetadas, confiança e esforço (`LOW`, `MEDIUM`, `HIGH`).

As dimensões de impacto incluem Performance, SEO, Best Practices, Accessibility, AI Access e Security.

Essa prioridade não é SARI e não é usada como score metodológico de readiness.

## Seleção e orquestração de IA

Improvement Intelligence **não possui provider, modelo ou reasoning próprios**. Quando habilitada, usa a seleção principal de IA da mesma execução.

Configuração principal explícita:

```text
ai_provider = <provider-do-registry>
ai_model = <modelo-opcional>
ai_reasoning = <reasoning-opcional>
```

Nesse modo, a análise profunda usa o provider principal, desde que ele suporte o contrato estruturado necessário.

Configuração principal automática:

```text
ai_provider = auto
```

Nesse modo, a necessidade `IMPROVEMENT_INTELLIGENCE` reutiliza a política canônica existente:

1. providers configurados e elegíveis ao AUTO;
2. exclusões e estado de saúde da execução;
3. estimativa de custo por provider/modelo/reasoning;
4. prioridade vigente de custo/roteamento;
5. classificação de falhas;
6. quarentena/circuit breaker;
7. fallback para o próximo candidato elegível;
8. término no primeiro sucesso ou no esgotamento da cadeia.

A capacidade não possui política própria de ordenação, quarentena, circuit breaker ou número de tentativas. Seu contrato especializado fica restrito a prompt, schema, evidências e validação da resposta.

Configurações próprias permanecem limitadas a ativação, domínios, teto de recomendações, timeout da necessidade e idioma preferencial.

### Idioma de análise

`RASAI_AI_ANALYSIS_LANGUAGE` define o idioma preferencial das explicações/textos sugeridos:

- `auto`: usa o idioma principal da auditoria;
- ou tag BCP-47 como `pt-BR`, `en-US`, `es-ES`.

Esse parâmetro não força o idioma da página nem substitui evidência real do conteúdo.

## Console interativo

No console, abra:

```text
INÍCIO > PREPARAR AUDITORIA > Análise profunda e melhorias
```

A tela da capacidade controla somente sua habilitação e parâmetros próprios. Dependências relacionadas são apresentadas com os IDs canônicos das configurações correspondentes.

A configuração persistível específica contém:

- `enabled`;
- `domains`;
- `max_recommendations`;
- `timeout_seconds`;
- idioma de análise quando aplicável ao contrato de configuração.

Provider, modelo e reasoning vêm exclusivamente da **IA principal** da execução, acessível pela macro `INÍCIO > Inteligência Artificial` e pelo catálogo completo de configurações.

Credenciais nunca são gravadas no INI.

A capacidade deve indicar a seleção principal que será usada (`provider` explícito, `AUTO` ou `NONE`). Quando CAT-08 está selecionado e a IA principal não está apta, a auditoria permanece executável com limitação explícita: a análise profunda não chama provider e continua pendente para fechamento integral.

## SaaS / Control Plane

O contrato SaaS usa `ExecutionJob.payload` e permanece secret-free.

Campos específicos da capacidade incluem:

- `improvement_intelligence`;
- `improvement_domains`;
- `improvement_max_recommendations`;
- `improvement_ai_timeout_seconds`;
- `ai_analysis_language`.

A seleção de IA é feita somente pelos campos canônicos do job de auditoria:

- `ai_provider`;
- `ai_model`;
- `ai_reasoning`.

Quando `improvement_intelligence=true`, `urls` deve conter exatamente uma URL e a política de IA precisa ser compatível. `auto` é válido e aciona a mesma orquestração do core.

Credenciais ficam no boundary seguro do worker/integration/environment e não entram no payload durável.

## Variáveis de ambiente próprias

A capacidade reconhece somente controles próprios de escopo/comportamento:

```text
RASAI_IMPROVEMENT_INTELLIGENCE
RASAI_IMPROVEMENT_DOMAINS
RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS
RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS
RASAI_AI_ANALYSIS_LANGUAGE
```

Provider/modelo/reasoning não são duplicados em variáveis de Improvement Intelligence.

## Persistência e idempotência

Tabelas:

- `improvement_intelligence_runs`;
- `improvement_intelligence_findings`;
- `improvement_intelligence_recommendations`.

A configuração efetiva e a evidência recebem fingerprints. Se ambas forem idênticas e já existir execução completa reutilizável, o runtime pode reaproveitar o resultado para evitar nova chamada paga conforme o contrato vigente.

Os campos de provider/modelo/reasoning persistidos no resultado representam a execução efetiva para rastreabilidade, não configuração paralela.

## Telemetria de IA

Cada tentativa usa a telemetria canônica de providers com provider/modelo/reasoning, horário, duração, status, tokens, custo estimado quando calculável e diagnóstico.

O contrato é identificado por:

```text
semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001
```

O relatório próprio contém o recorte de consumo da análise e a superfície canônica de Uso de IA pode atribuir o mesmo consumo ao contrato correspondente.

## Relatórios

A superfície canônica é:

```text
report-catalog/cat-08.html
```

O HTML separa backlog priorizado derivado pela IA, findings/evidências determinísticos, HTML original/sugerido quando aplicável, consumo de IA e fronteiras metodológicas.

A página existe no contrato de relatório mesmo quando a capacidade não foi executada, deixando o estado explícito.

## Relatório consolidado

O consolidado usa o vocabulário canônico de dimensões do `SCORE-GEO-004`. Improvement Intelligence, Lighthouse/Core Web Vitals, Apdex, SERP e postura de segurança são complementares e não são artificialmente promediados dentro da série temporal do SARI.

A análise especialista do próprio consolidado possui telemetria separada e também utiliza a orquestração canônica quando IA é solicitada.

## Validação pós-deploy

Uma recomendação é hipótese de melhoria até que a URL seja auditada novamente:

```text
evidência -> finding -> recomendação -> prioridade -> deploy -> nova auditoria -> comparação
```

Somente a nova medição pode afirmar o ganho efetivamente observado.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md) e [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md).
