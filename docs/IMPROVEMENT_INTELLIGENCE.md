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

Essa restrição existe para:

1. preservar contexto semântico específico;
2. impedir generalizações entre páginas distintas;
3. tornar custo/token previsível;
4. manter o relatório acionável por elemento/URL.

## Evidências correlacionadas

Quando disponíveis no mesmo `AUD-*/audit.db` e nos artifacts associados, a feature reutiliza:

- Findings, RuleExecutions e Evidences do core;
- HTML bruto/renderizado e snapshots;
- `title`, meta description, canonical, headings e estrutura de landmarks;
- elementos como imagens, links e botões;
- PageSpeed/Lighthouse, incluindo auditorias, categorias, savings e referências DOM (`selector`, `path`, `snippet`) quando fornecidas pelo artifact;
- Core Web Vitals/CrUX já persistidos;
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

O RASAi pode apontar, quando a evidência foi capturada, por exemplo:

- ausência de HTTPS;
- ausência de CSP;
- ausência de HSTS em HTTPS;
- falta de proteção explícita contra framing;
- ausência de `X-Content-Type-Options`;
- ausência de `Referrer-Policy`;
- cookies sem `Secure`/`SameSite` observáveis;
- exposição aparente de versão no header `Server`;
- achados Lighthouse de segurança/best practices já coletados.

Ausência de header é reportada como **postura/configuração observada**, não como prova de vulnerabilidade explorável. A feature não executa payloads, fuzzing, bypass de autenticação, exploração XSS/SQLi/SSRF ou pentest ativo.

## Search / SERP

Quando Search Intelligence existe na auditoria, o relatório pode usar:

- query;
- posição observada do domínio;
- resultados à frente;
- gaps determinísticos;
- título/description/headings/termos/JSON-LD das páginas competitivas que foram explicitamente adquiridas pelo subsistema Search.

A IA pode sugerir conteúdo/estrutura que reduza gaps observados, mas é proibido concluir que uma alteração **causará** determinada posição. Ranking é tratado como observação correlacional.

## HTML original x HTML sugerido

Para findings técnicos que possuem fragmento/selector observável, o relatório `improvement-intelligence.html` mostra:

- selector do elemento;
- HTML original observado;
- HTML sugerido pela IA, quando a correção pode ser proposta com segurança;
- destaque visual das diferenças;
- justificativa;
- como validar depois do deploy.

A sugestão continua exigindo revisão humana.

## Priorização

Cada recomendação recebe prioridade derivada de:

- severidade do finding determinístico;
- quantidade/intensidade de dimensões potencialmente afetadas;
- confiança da recomendação evidence-bound;
- esforço estimado (`LOW`, `MEDIUM`, `HIGH`).

As dimensões de impacto são:

- Performance;
- SEO;
- Best Practices;
- Accessibility;
- AI Access;
- Security.

Essa prioridade **não é SARI** e não deve ser usada como score metodológico de readiness.

## IA independente da análise normal

A feature exige provider explícito. `AUTO` e `NONE` não são permitidos para a chamada profunda.

O usuário escolhe, independentemente da IA padrão da auditoria:

- provider;
- modelo;
- esforço/reasoning;
- timeout;
- domínios;
- teto de recomendações.

A key/token não é duplicada: a feature reutiliza a credencial já configurada para o provider selecionado.

### Idioma de análise

`RASAI_AI_ANALYSIS_LANGUAGE` define o idioma preferencial das explicações/textos sugeridos.

- `auto` - default; usa o idioma principal da auditoria;
- ou uma tag como `pt-BR`, `en-US`, `es-ES`.

Esse parâmetro **não força o idioma da página** e não substitui evidência real de `<html lang>`, conteúdo ou detecção semântica.

## Console interativo

O item **13. Análise profunda URL** segue o mesmo fluxo do console atual.

A configuração não sensível é persistida em `rasai-console.ini` na seção `[improvement_intelligence]`:

- `enabled`;
- `provider`;
- `model`;
- `reasoning_effort`;
- `domains`;
- `max_recommendations`;
- `timeout_seconds`.

Credenciais nunca são gravadas no INI.

A execução ocorre depois da auditoria normal e, quando Search Intelligence foi habilitado na mesma sessão, depois da coleta SERP. O progresso mostra fase, URL, provider/modelo e andamento da análise profunda antes de concluir a execução.

Dentro de `rasai-console`, o item 13 é a autoridade de ativação da etapa. O toggle de ambiente é neutralizado durante a auditoria base e restaurado depois para impedir execução oculta ou duplicada. O contrato por variável continua disponível para CLI, worker/SaaS e automação.

## SaaS / Control Plane

O contrato SaaS usa o `ExecutionJob.payload`, que permanece secret-free.

Campos adicionados ao job de auditoria:

- `improvement_intelligence`;
- `improvement_ai_provider`;
- `improvement_ai_model`;
- `improvement_ai_reasoning`;
- `improvement_domains`;
- `improvement_max_recommendations`;
- `improvement_ai_timeout_seconds`;
- `ai_analysis_language`.

Quando `improvement_intelligence=true`, `urls` deve conter exatamente uma URL.

Credenciais continuam no boundary seguro do worker/integration/environment e não entram no payload durável.

## Persistência e idempotência

Tabelas aditivas:

- `improvement_intelligence_runs`;
- `improvement_intelligence_findings`;
- `improvement_intelligence_recommendations`.

A configuração e a evidência recebem fingerprints. Se ambos são idênticos e já existe execução completa, o runtime pode reutilizar o resultado para evitar nova chamada paga.

## Telemetria de IA

Cada tentativa usa a tabela canônica `ai_provider_attempts` com:

- provider/modelo/reasoning;
- horário/duração/status;
- tokens input/cache/output/reasoning/total quando fornecidos;
- custo estimado quando calculável;
- diagnóstico/retry;
- `semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001`.

O custo é apresentado separadamente como **Improvement Intelligence por IA**. O relatório próprio também contém o recorte de consumo dessa análise.

## Relatórios

A superfície canônica é:

`report/improvement-intelligence.html`

Ela fica no grupo **Ações e referência**, antes das superfícies de conteúdo/remediação.

O HTML separa explicitamente:

1. backlog priorizado derivado pela IA;
2. findings/evidências determinísticos;
3. HTML original e sugerido;
4. consumo da IA;
5. fronteiras metodológicas.

O relatório é gerado mesmo quando a feature não foi executada, deixando o estado explícito e evitando links inconsistentes no mini-site.

## Relatório consolidado

O consolidado atual usa o vocabulário vigente de dimensões, incluindo `DISCOVERY_ACCESS` e `CONTENT_VALUE`. `TECHNICAL_ACCESSIBILITY` permanece apenas como leitura histórica legada.

Improvement Intelligence, Lighthouse/Core Web Vitals, Apdex, SERP e postura de segurança são complementares e não são artificialmente promediados dentro da série histórica do SARI.

## Validação pós-deploy

Uma recomendação é uma hipótese de melhoria até que a URL seja auditada novamente.

A sequência recomendada é:

`evidência -> finding -> recomendação -> prioridade -> deploy -> nova auditoria -> before/after`

Somente a nova medição pode afirmar o ganho efetivamente observado.
