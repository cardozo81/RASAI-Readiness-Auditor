# Perfis de tarefa e personas de IA

## Objetivo

O RASAi separa duas responsabilidades que não devem ser confundidas:

1. **orquestração de provider/modelo**: escolhe provider, modelo, reasoning, custo, fallback, retry, quarentena e circuit breaker;
2. **especialização da tarefa**: define qual papel técnico a IA deve assumir para interpretar um conjunto específico de evidências.

A escolha do provider não altera a persona. Uma mesma tarefa recebe o mesmo perfil funcional quando executada por OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, GitHub Copilot ou outro provider integrado ao mesmo contrato.

Os perfis são versionados e configuráveis porque a redação da persona pode exigir ajuste fino ao longo do tempo. Essa flexibilidade não permite alterar contratos normativos de evidência, schema, scoring, causalidade, segurança ou revisão humana.

## Arquivos e responsabilidade

O modelo usa deliberadamente duas camadas com responsabilidades diferentes.

### Catálogo de fábrica

```text
src/rasai/config/ai-profiles-defaults.toml
```

É a baseline canônica distribuída dentro do pacote Python. Contém todos os perfis obrigatórios e é usada diretamente quando não existe override aplicável ou quando `RASAI_AI_TASK_PROFILES_SOURCE=factory`.

Esse arquivo **não é o ponto de customização do operador**. Alterá-lo significa mudar a baseline do produto e exige tratamento como alteração de código/produto, com testes e versionamento correspondentes.

### Overrides editáveis pelo operador

```text
config/ai-task-profiles.toml
```

Esse é o arquivo destinado ao ajuste humano das personas. Ele é deliberadamente **vazio de overrides por padrão** para não congelar uma cópia do catálogo de fábrica.

O operador deve adicionar somente os perfis que realmente deseja customizar. Perfis omitidos continuam herdando automaticamente a versão mais recente da baseline de fábrica.

O arquivo editável não é tecnicamente necessário para o runtime funcionar: se ele estiver ausente e a fonte for `auto`, o runtime usa a baseline de fábrica. Ele é mantido no projeto como superfície explícita e pronta para customização humana.

> Não copie o catálogo de fábrica inteiro para o arquivo editável sem necessidade. Fazer isso transforma todos os perfis em overrides locais e pode mascarar futuras atualizações da baseline do produto.

## Qual arquivo o humano deve editar

Para ajuste operacional, edite somente:

```text
config/ai-task-profiles.toml
```

Com a configuração padrão:

```text
RASAI_AI_TASK_PROFILES_SOURCE=auto
RASAI_AI_TASK_PROFILES_FILE=config/ai-task-profiles.toml
```

o runtime usa os overrides presentes nesse arquivo e completa os demais perfis com a baseline de fábrica.

No console interativo, alterações salvas entram em vigor na **próxima AUD iniciada**, sem necessidade de reiniciar o console. Imediatamente antes da execução, o RASAi resolve e valida o catálogo efetivo e cria um snapshot temporário imutável. A AUD em andamento continua usando esse snapshot mesmo que o humano altere `config/ai-task-profiles.toml` durante o processamento.

O loader de perfis continua capaz de resolver o arquivo atual quando usado fora desse limite de execução, mas o console deliberadamente não faz hot reload de persona no meio de uma AUD. Isso preserva reprodutibilidade e mantém modelos, preços e personas sob a mesma regra de consistência por execução.

Se `RASAI_AI_TASK_PROFILES_SOURCE=factory`, qualquer ajuste no arquivo editável é ignorado intencionalmente. Se `SOURCE=file`, o arquivo configurado precisa existir e ser válido.

## Seleção da fonte

O runtime reconhece:

```text
RASAI_AI_TASK_PROFILES_SOURCE=auto|factory|file
RASAI_AI_TASK_PROFILES_FILE=<caminho-do-arquivo.toml>
```

Comportamento:

| Fonte | Regra |
|---|---|
| `auto` | usa os overrides do arquivo configurado quando ele existe; se não existir, usa somente o catálogo de fábrica |
| `factory` | ignora override local e usa somente o catálogo de fábrica |
| `file` | exige que o arquivo configurado exista e seja válido; os perfis nele presentes sobrescrevem a fábrica |

O caminho padrão do override é:

```text
config/ai-task-profiles.toml
```

Overrides são parciais **no nível do perfil**. Perfis omitidos continuam herdando a fábrica. Quando um `profile_id` é sobrescrito, a seção precisa informar integralmente `version`, `role`, `objective`, `competencies` e `guidance`.

## O que pode ser alterado

Cada perfil possui somente os seguintes campos configuráveis:

| Campo | Finalidade |
|---|---|
| `version` | versão funcional do perfil |
| `role` | papel profissional assumido pela IA |
| `objective` | objetivo intelectual da tarefa |
| `competencies` | competências que devem orientar a análise |
| `guidance` | orientação adicional específica do perfil |

Campos desconhecidos são rejeitados. Isso é intencional.

O arquivo de personas **não controla**:

- schema de saída;
- lista de evidências permitidas;
- regras de scoring;
- fórmulas SARI/SCORE-GEO;
- proibições de causalidade não suportada;
- limites de segurança;
- proibição de exploração ativa;
- política de revisão humana;
- fallback/retry/quarentena;
- provider/modelo;
- política de preço.

Esses elementos permanecem em contratos técnicos protegidos pelo código.

## Grade de perfis

| Profile ID | Papel principal | Aplicação |
|---|---|---|
| `SEMANTIC_READINESS` | especialista sênior em SEO técnico, semântica web, entidades, dados estruturados e Search/AI Readiness | avaliação semântica, intenção, entidades, estrutura e interpretabilidade |
| `CONTENT_REMEDIATION` | estrategista/editor sênior de conteúdo people-first com SEO e semântica | sugestões de texto e correções editoriais baseadas em evidência |
| `TECHNICAL_HTML` | arquiteto de software/web sênior com frontend e SEO técnico | HTML, CSS, JavaScript, renderização e estrutura técnica |
| `CRAWL_DISCOVERY` | especialista sênior em Technical SEO, crawling e descoberta | robots, sitemap, controles de crawlers e descoberta de recursos |
| `SOURCE_QUALITY` | arquiteto sênior de infraestrutura/confiabilidade web | HTTP, DNS, TLS, redirects, CDN/proxy e qualidade de origem |
| `SEARCH_INTELLIGENCE` | analista sênior de Search Intelligence, SEO competitivo, SERP, AEO e GEO | oportunidades competitivas e interpretação de evidência de busca |
| `PERFORMANCE` | engenheiro sênior de performance web | Core Web Vitals, Lighthouse, rede, renderização e frontend performance |
| `ACCESSIBILITY` | especialista sênior em acessibilidade web | WCAG, semântica acessível, teclado, tecnologia assistiva e limites de automação |
| `SECURITY_PASSIVE` | arquiteto sênior de segurança web/aplicações em modo estritamente passivo | headers, TLS posture, controles de navegador e risco defensivo |
| `AI_READINESS` | especialista em descoberta, interpretabilidade e retrieval readiness para IA | clareza de entidades, answerability, citation readiness e descoberta por IA |
| `EVOLUTION` | analista multidisciplinar sênior de evolução entre auditorias | comparação temporal, regressões, melhorias e verificação de correções |

## Regra de aplicação

A persona é aplicada **depois que a funcionalidade sabe qual tarefa precisa executar e antes da serialização final da requisição ao provider**.

Fluxo lógico:

```text
necessidade de análise
        ↓
identificação do tipo de tarefa
        ↓
resolução do(s) task profile(s)
        ↓
composição da persona especializada
        ↓
instruções normativas da funcionalidade
        ↓
schema/evidências/contratos protegidos
        ↓
orquestrador seleciona provider/modelo
        ↓
adapter converte para o protocolo do provider
        ↓
requisição externa
```

O perfil é sempre complementar. Ele não substitui a instrução normativa existente.

## Aplicação por rotina

### Avaliação semântica

Usa:

```text
SEMANTIC_READINESS
```

O perfil orienta a interpretação de semântica, entidades, intenção, estrutura e dados estruturados. O contrato de evidências continua determinando exatamente o que pode ser avaliado.

### Remediação de conteúdo

Usa:

```text
CONTENT_REMEDIATION
```

O perfil é aplicado antes das regras que impedem invenção de fatos, números, credenciais, garantias e outras afirmações não sustentadas.

### HTML, CSS, JavaScript e estrutura técnica

Usa:

```text
TECHNICAL_HTML
```

O objetivo é produzir diagnóstico de engenharia web e, quando permitido pelo contrato da funcionalidade, correção técnica concreta.

### Crawling e descoberta

Usa:

```text
CRAWL_DISCOVERY
```

Abrange crawling, robots, sitemap, controles de crawlers e mecanismos de descoberta.

### Qualidade da origem e infraestrutura

Usa:

```text
SOURCE_QUALITY
```

Abrange HTTP, DNS, TLS e redirects. A classificação determinística da coleta permanece soberana.

### Search Intelligence

Usa:

```text
SEARCH_INTELLIGENCE
```

Abrange SERP, concorrência, intenção, AEO e GEO. Diferenças de ranking são tratadas como correlação, nunca como prova de causalidade.

### Segurança

Usa:

```text
SECURITY_PASSIVE
```

A persona é explicitamente defensiva e passiva. Exploração, payloads, bypasses, ataques a credenciais e active scanning permanecem fora do escopo.

### Performance

Usa:

```text
PERFORMANCE
```

Abrange métricas e evidências de performance. A IA não pode prometer ganhos numéricos sem suporte empírico.

### Acessibilidade

Usa:

```text
ACCESSIBILITY
```

A análise deve respeitar a diferença entre evidência automatizada e validação humana de acessibilidade.

### AI Readiness

Usa:

```text
AI_READINESS
```

O objetivo é melhorar clareza, interpretabilidade e recuperabilidade sem manipulação de mecanismos de IA.

### Evolução/consolidado

Usa:

```text
EVOLUTION
```

A persona é multidisciplinar porque a comparação pode conter simultaneamente SEO/GEO, performance, UX, acessibilidade, infraestrutura, segurança e conteúdo.

## Análise profunda multidomínio

Quando uma única análise contém vários domínios, o runtime compõe os perfis correspondentes.

Mapeamento:

| Domínio funcional | Perfil |
|---|---|
| HTML e problemas técnicos | `TECHNICAL_HTML` |
| Semântica e estrutura | `SEMANTIC_READINESS` |
| Conteúdo | `CONTENT_REMEDIATION` |
| Busca orgânica / SERP | `SEARCH_INTELLIGENCE` |
| Arquivos e descoberta | `CRAWL_DISCOVERY` |
| Performance | `PERFORMANCE` |
| Acessibilidade | `ACCESSIBILITY` |
| Melhores práticas web | `TECHNICAL_HTML` |
| Segurança | `SECURITY_PASSIVE` |
| Acesso e compreensão por IA | `AI_READINESS` |

Perfis repetidos são deduplicados. Por exemplo, `TECHNICAL_HTML` e `BEST_PRACTICES` não duplicam a mesma persona na requisição.

Essa composição evita uma persona genérica tentando resolver simultaneamente problemas de segurança, acessibilidade, performance e SEO com a mesma especialização.

## Persistência e auditoria

Cada tentativa de IA recebe identidade de perfil versionada. O runtime persiste metadados em:

```text
ai_task_profile_attempts
```

Campos centrais:

```text
attempt_id
source_table
request_payload_hash
task_profile_id
task_profile_version
```

Quando uma tarefa utiliza vários perfis, os IDs e versões são persistidos na mesma ordem de composição.

O `request_message_summary` também recebe um marcador funcional do tipo:

```text
profile=SOURCE_QUALITY@1.0
```

ou:

```text
profile=TECHNICAL_HTML@1.0,PERFORMANCE@1.0,SECURITY_PASSIVE@1.0
```

Isso permite rastrear qual especialização efetivamente participou de uma chamada sem depender do provider escolhido.

## Relatório de uso de IA

Quando o hash da tentativa pode ser relacionado ao envelope persistido, `ai-usage.html` acrescenta a identidade do perfil à finalidade da comunicação.

Exemplo conceitual:

```text
Análise técnica · Perfil SOURCE_QUALITY v1.0
```

Provider, modelo e reasoning continuam sendo informações separadas. Essa separação é deliberada:

```text
Tarefa/persona != provider/modelo
```

## Versionamento

Alterar semanticamente uma persona deve alterar seu campo `version`.

Exemplos:

- correção ortográfica sem mudança de significado: pode manter a versão;
- nova competência relevante: incrementar versão;
- mudança do papel profissional: incrementar versão;
- mudança material de objetivo/guidance: incrementar versão.

A versão permite comparar auditorias históricas sem assumir que duas chamadas com o mesmo `profile_id` utilizaram exatamente a mesma orientação.

## Ajuste fino recomendado

Ao ajustar um perfil:

1. edite `config/ai-task-profiles.toml`, não a baseline empacotada;
2. adicione somente o perfil diretamente relacionado ao problema observado;
3. ao sobrescrever um perfil, informe os cinco campos configuráveis completos;
4. mantenha objetivo e competências específicos, evitando personas universais;
5. não replique regras de schema/evidência no arquivo de persona;
6. evite instruções de resultado garantido;
7. altere `version` quando o comportamento esperado mudar;
8. execute testes de contrato antes de promover o ajuste.

## Falha de configuração

A configuração de personas é validada antes de uma chamada paga.

São falhas, entre outras:

- TOML inválido;
- `schema_version` incompatível;
- perfil com ID inválido;
- competências vazias;
- seção sobrescrita sem todos os campos obrigatórios;
- campos desconhecidos;
- textos acima dos limites definidos;
- `RASAI_AI_TASK_PROFILES_SOURCE=file` apontando para arquivo inexistente.

O runtime deve falhar antes da chamada externa em vez de executar silenciosamente uma persona parcialmente inválida.

## Regra arquitetural

O catálogo de personas é uma camada de especialização, não um segundo orquestrador.

Ele **não deve** decidir:

- qual IA será chamada;
- qual modelo será usado;
- preço;
- ordem AUTO;
- reasoning;
- fallback;
- retry;
- quarentena;
- circuit breaker.

Essas decisões continuam pertencendo exclusivamente ao runtime central de providers.
