# Reporting de uso e comunicação de IA

`report-catalog/ai-integrations.html` é a superfície destinada a explicar consumo, falhas, roteamento e comunicação com provedores de IA durante uma auditoria.

O relatório deve distinguir:

- finalidade desabilitada/não solicitada;
- provider não configurado;
- tentativa externa realizada;
- resposta aceita pelo contrato RASAi;
- resposta recebida e posteriormente rejeitada por validação/contrato local;
- erro técnico de request/provider;
- provider removido da execução por condição terminal;
- provider removido pelo circuit breaker;
- tokens medidos e custo estimado quando o provider fornece dados suficientes.

Uma resposta rejeitada localmente ainda representa comunicação externa e pode ter consumido tokens/custo. Portanto, não deve ser escondida nem descrita como se nenhuma chamada tivesse ocorrido.

Ausência de dado de IA não deve ser convertida em finding do website. O estado deve indicar, conforme a evidência persistida, se a finalidade estava desabilitada, não configurada, foi executada sem saída utilizável, ficou parcial ou falhou/ficou indisponível.

## Transparência de custo e atribuição funcional

`report-catalog/ai-integrations.html` centraliza a telemetria financeira e operacional das tentativas de IA. As páginas CAT apresentam o resultado funcional produzido e não repetem tokens, request/response ou custo individual.

A página de IA e integrações apresenta, a partir da telemetria persistida:

- finalidade da chamada;
- aplicação funcional no relatório;
- provider e modelo;
- data/hora da tentativa no contrato canônico de timezone da apresentação;
- origem da execução, distinguindo **Processamento** de **Reprocessamento** quando a telemetria persistida permite vincular o evento a um `RPR-*`;
- estado da tentativa;
- tokens de entrada, cache, saída e raciocínio quando fornecidos;
- custo individual e moeda quando houver preço persistido;
- roteamento, fallback e motivo técnico;
- request e response sanitizados quando disponíveis;
- custo observado total;
- previsão pré-execução, quando persistida;
- desvio entre custo esperado e observado, quando calculável de forma confiável.

A atribuição é funcional e aditiva: cada tentativa externa é contada uma única vez no total da auditoria. Uma mesma evidência pode ser reutilizada por várias páginas sem duplicar custo.

Mapeamentos públicos vigentes incluem:

- análise semântica por dispositivo -> contexto SARI e CATs que consomem o resultado persistido;
- crawling e remediação técnica de descoberta -> CAT-01;
- Search/Competitive Intelligence -> CAT-05;
- Improvement Intelligence -> CAT-08;
- remediação assistida de conteúdo -> CAT-09;
- Análise Direcionada -> página `directed-analysis.html`;
- demais finalidades -> contexto funcional explicitado na própria linha da tentativa.

Quando uma tentativa não possui telemetria suficiente para custo, o relatório mantém a tentativa e exibe **Não precificado**; ausência de preço não é convertida em custo zero. Quando o custo persistido é explicitamente `0`, moeda e valor são exibidos em cinza claro e, na mesma tentativa, tokens de entrada/saída recebem o mesmo tratamento visual secundário. `reasoning_tokens`, quando presentes, são subconjunto dos tokens de saída e não são somados novamente ao total.

A regeneração do `report-catalog/` apenas reprojeta os dados persistidos. Ela não cria chamadas de IA adicionais para preencher a página.

## `AI=auto`, fallback e múltiplos providers no mesmo relatório

`AI=auto` não implica um único provider por relatório. Uma mesma finalidade pode ter mais de uma tentativa externa, por exemplo:

1. provider A responde, mas a resposta é rejeitada pelo contrato local;
2. o runtime executa fallback para provider B;
3. provider B produz a resposta aceita.

Se ambas as chamadas retornaram usage/custo, **ambas entram no custo do relatório proprietário**. Se a primeira chamada não retornou dados suficientes para estimativa, ela continua aparecendo como tentativa sem custo mensurável; o RASAi não assume custo zero nem inventa um valor.

Também é possível que URLs ou dispositivos diferentes do mesmo relatório sejam atendidos por providers distintos ao longo da execução. Por isso o relatório local e o totalizador sempre agregam por tentativa persistida, não por `effective_provider` da sessão.

## Total conciliado e drill-down em `ai-integrations.html`

Além dos indicadores existentes, `ai-integrations.html` contém o bloco **Total de IA e onde cada custo foi alocado**. O total usa as tentativas persistidas em:

- `ai_provider_attempts`;
- `content_remediation_attempts`.

A listagem de **Outras integrações** segue o mesmo contrato temporal: cada linha apresenta data/hora e origem da execução quando esses dados podem ser determinados a partir dos ledgers persistidos. A projeção converte timestamps UTC para o timezone de apresentação sem alterar a evidência original.

A página apresenta três níveis complementares:

1. **Mapa de alocação: relatório × provider/modelo** - mostra financeiramente em qual HTML cada provider/modelo ficou alocado;
2. **Consumo global por provider/modelo** - consolida o custo de cada provider/modelo independentemente da superfície;
3. **Detalhamento por relatório proprietário** - expande URL, dispositivo, contrato/finalidade, motivo da alocação, provider/modelo, status, tokens e custo.

A soma das páginas proprietárias deve fechar com o total da execução porque uma tentativa nunca é atribuída a duas superfícies. Páginas sem consumo direto são listadas separadamente e não entram novamente na soma.

Custo continua sendo uma estimativa operacional, não invoice. O renderer não inventa custo para tentativa sem `estimated_cost` e não inventa tokens quando o provider não os retornou. `reasoning_tokens`, quando presentes, são tratados como subconjunto de output e não são adicionados novamente a `total_tokens`.

O enriquecimento é idempotente: regerar/finalizar o mini-site substitui o bloco padronizado anterior em vez de duplicá-lo.

## Provider-neutral

O renderer não mantém uma allowlist visual de providers. Provider e modelo são projetados a partir da telemetria persistida. Assim, OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, GitHub Copilot e futuros providers compatíveis com o registry usam a mesma superfície sem exigir uma variante específica do HTML.

GitHub Copilot é `explicit-only`; quando aparece no report, isso representa seleção explícita. Ele não deve aparecer como candidato/tentativa do pool `AI=auto`.

## Log de exchanges

Quando disponível, cada comunicação externa é apresentada em bloco expansível com provider/modelo, finalidade, página/snapshot, endpoint sanitizado, duração, status, request e response sanitizados, hashes e indicação de truncamento.

A projeção HTML usa nomes públicos e funcionais para etapas e contratos. Identificadores internos de entrega não fazem parte do contrato público do relatório. Quando a cópia visual de um payload precisa normalizar um identificador interno, o hash continua referindo-se ao conteúdo original persistido/enviado; `audit.db` e a evidência bruta não são reescritos. O próprio HTML informa essa distinção para evitar que a versão sanitizada seja confundida com o payload bruto usado no cálculo do hash.

O conteúdo dessa tabela pertence à telemetria técnica. Ele não altera regras, findings, `SCORE-GEO-004` ou `SARI-001`.

## AUTO

Quando `AI=auto`, o relatório também apresenta o estado de saúde observado de cada provider elegível durante a execução: tentativas, sucessos, falhas temporárias, falhas terminais, elegibilidade final e motivo de exclusão quando aplicável.

O conjunto AUTO é derivado do `provider_registry`; não existe cadeia fixa documentada pelo report. Providers `explicit-only`, atualmente GitHub Copilot, permanecem fora desse pool.

A política completa está em [`AI_RUNTIME_ORCHESTRATION.md`](AI_RUNTIME_ORCHESTRATION.md) e o catálogo canônico em [`PROVIDER_REGISTRY.md`](PROVIDER_REGISTRY.md).
