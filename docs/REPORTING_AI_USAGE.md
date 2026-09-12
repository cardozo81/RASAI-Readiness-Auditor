# Reporting de uso e comunicação de IA

`report/ai-usage.html` é a superfície destinada a explicar consumo, falhas, roteamento e comunicação com provedores de IA durante uma auditoria.

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

## Transparência de custo em todas as páginas HTML

Toda página HTML materializada no diretório `report/`, exceto `ai-usage.html`, recebe um quadro padronizado **Consumo de IA atribuído a esta página**.

O quadro mostra, a partir da telemetria persistida:

- tentativas externas de IA;
- respostas aceitas;
- tokens de entrada;
- tokens de entrada em cache;
- tokens de saída;
- reasoning tokens, quando reportados;
- tokens totais;
- custo financeiro estimado e moeda;
- indicação explícita quando tokens ou custo não foram retornados pelo provider.

Quando nenhuma chamada pertence diretamente àquela superfície, o quadro continua presente e informa `Sem consumo IA direto`. Isso evita a falsa impressão de que uma página sem custo próprio deixou de ser contabilizada.

A atribuição é **primária e aditiva**: cada tentativa externa pertence a exatamente uma página proprietária. Se a evidência produzida por uma chamada for reutilizada em outras páginas, o mesmo custo não é repetido nessas páginas. Essa regra permite que a soma por página seja reconciliada com o total da auditoria.

A atribuição vigente é orientada pelo contrato/finalidade persistidos:

- `M18-SEMANTIC-*` → relatório Mobile ou Desktop conforme o dispositivo da tentativa; sem dispositivo, `readiness.html`;
- `M24-*`/remediação técnica de crawling → `crawling-discovery.html`;
- `SOURCE-QUALITY-*` → `context.html`;
- `IMPROVEMENT-INTELLIGENCE-*` → `improvement-intelligence.html`;
- `content_remediation_attempts` / `M20-CONTENT-REMEDIATION-*` → `content-suggestions.html`;
- contratos de Search/Competitive Intelligence, quando persistidos na telemetria canônica → `search-intelligence.html`;
- contratos futuros ainda não classificados → `index.html`, de forma explícita, para que consumo novo nunca desapareça da conciliação.

Essa atribuição é de **ownership de custo**, não uma afirmação de exclusividade de uso da evidência. `readiness.html`, `scoring.html`, `remediation.html` ou outras superfícies podem projetar resultados derivados de uma chamada cujo custo pertence à etapa que efetivamente originou o request.

## Total conciliado e drill-down em `ai-usage.html`

Além dos indicadores existentes, `ai-usage.html` contém um bloco **Total de IA e detalhamento por página**. O total usa as tentativas persistidas em:

- `ai_provider_attempts`;
- `content_remediation_attempts`.

O detalhamento é expansível por página proprietária e, dentro dela, por URL auditada/dispositivo/contrato/provider/modelo. Isso permite verificar tanto o custo de cada superfície HTML quanto o custo associado às URLs que geraram as chamadas.

A soma das páginas proprietárias deve fechar com o total da execução porque uma tentativa nunca é atribuída a duas superfícies. Páginas sem consumo direto são listadas separadamente e não entram novamente na soma.

Custo continua sendo uma estimativa operacional, não invoice. O renderer não inventa custo para tentativa sem `estimated_cost` e não inventa tokens quando o provider não os retornou. `reasoning_tokens`, quando presentes, são tratados como subconjunto de output e não são adicionados novamente a `total_tokens`.

O enriquecimento é idempotente: regerar/finalizar o mini-site substitui o bloco padronizado anterior em vez de duplicá-lo.

## Provider-neutral

O renderer não mantém uma allowlist visual de providers. Provider e modelo são projetados a partir da telemetria persistida. Assim, OpenAI, DeepSeek, MiMo, xAI, Qwen, Gemini, Anthropic, GitHub Copilot e futuros providers compatíveis com o registry usam a mesma superfície sem exigir uma variante específica do HTML.

GitHub Copilot é `explicit-only`; quando aparece no report, isso representa seleção explícita. Ele não deve aparecer como candidato/tentativa do pool `AI=auto`.

## Log de exchanges

Quando disponível, cada comunicação externa é apresentada em bloco expansível com provider/modelo, finalidade, página/snapshot, endpoint sanitizado, duração, status, request e response sanitizados, hashes e indicação de truncamento.

O conteúdo dessa tabela pertence à telemetria técnica. Ele não altera regras, findings, `SCORE-GEO-004` ou `SARI-001`.

## AUTO

Quando `AI=auto`, o relatório também apresenta o estado de saúde observado de cada provider elegível durante a execução: tentativas, sucessos, falhas temporárias, falhas terminais, elegibilidade final e motivo de exclusão quando aplicável.

O conjunto AUTO é derivado do `provider_registry`; não existe cadeia fixa documentada pelo report. Providers `explicit-only`, atualmente GitHub Copilot, permanecem fora desse pool.

A política completa está em [`AI_RUNTIME_ORCHESTRATION.md`](AI_RUNTIME_ORCHESTRATION.md) e o catálogo canônico em [`PROVIDER_REGISTRY.md`](PROVIDER_REGISTRY.md).
