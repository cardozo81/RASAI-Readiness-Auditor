# Guia de IA

O RASAi usa IA em finalidades opcionais e evidence-bound. A auditoria determinística continua capaz de executar sem IA. Os consumidores que usam o **registry canônico de IA** reutilizam a mesma seleção principal e o mesmo motor local de ciclos, provider/modelo, custo, health, quarentena e fallback. Integrações externas de domínio específico podem ter boundary próprio quando isso evita misturar pesquisa externa com evidência determinística.

## Finalidades

A composição atual usa IA para finalidades como:

- análise semântica baseada somente nas evidências fornecidas;
- sugestões e remediação de conteúdo por IA;
- orientação técnica opcional sobre diagnósticos já determinados pelo runtime;
- análise profunda de uma URL quando habilitada;
- análises especializadas que fazem parte do relatório consolidado ou de outras superfícies opcionais.

Nenhuma finalidade autoriza inventar fatos, credenciais, preços, datas, estatísticas, URLs, políticas de crawler ou evidências.

## Escopo das integrações documentadas

O guia descreve somente capacidades efetivamente expostas pelo RASAi. A existência, no fornecedor, de outro plano, tipo de credencial, autenticação, endpoint, tier, tool, search, agent ou connector não amplia automaticamente o contrato do produto. Variantes não implementadas/homologadas identificadas durante a revisão estão rastreadas na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

## Providers integrados

Providers concretos no registry:

```text
openai
deepseek
mimo
xai
qwen
gemini
anthropic
mistral
cohere
kimi
copilot
```

Aliases:

```text
grok           -> xai
claude         -> anthropic
moonshot       -> kimi
github-copilot -> copilot
```

`none` desabilita IA. `auto` aciona a orquestração econômica entre providers elegíveis.

Mistral, Cohere, Kimi e GitHub Copilot podem participar do `AUTO` quando suas credenciais/modelos estiverem configurados e aptos. Use `RASAI_AI_AUTO_EXCLUDE` para manter um provider configurado fora do pool.

## Search Intelligence externa

A Perplexity Search API é a primeira integração externa deste tipo. Ela não é adicionada à lista de providers concretos acima, não participa do `AI=auto` e não substitui SERP observada. A finalidade é descoberta de fontes externas com provenance explícita e persistência separada.

A regra geral de providers canônicos permanece mais forte: qualquer novo provider que entrar no registry após homologação deve ser AUTO-eligible no mesmo merge quando configurado/apto. Perplexity Search API fica fora somente porque nesta entrega não pertence a esse registry.

Contrato: [PERPLEXITY_SEARCH_INTELLIGENCE.md](PERPLEXITY_SEARCH_INTELLIGENCE.md).

## Arquivos administráveis pelo operador

A convenção do RASAi é:

```text
config/                         <- humano / operador
├─ ai-models.toml
├─ ai-pricing.toml
└─ ai-task-profiles.toml

src/rasai/config/               <- baseline interna do produto
├─ ai-models-defaults.toml
├─ ai-pricing-defaults.toml
└─ ai-profiles-defaults.toml
```

Para ajustes operacionais, o humano edita somente os arquivos em `config/`. Os arquivos `*-defaults.toml` sob `src/rasai/config/` são referências de fábrica distribuídas com o produto e não são a superfície normal de customização.

No console interativo, os três catálogos são resolvidos e validados imediatamente antes de cada AUD. Arquivos file-backed são snapshotados para a execução. Portanto, uma alteração salva em `config/` entra na **próxima AUD** sem reiniciar o console, enquanto uma AUD já iniciada permanece com a configuração que recebeu no início.

## Catálogo de modelos

Os adapters técnicos continuam em código. A superfície humana padrão é:

```ini
RASAI_AI_MODELS_SOURCE = auto
RASAI_AI_MODELS_FILE = config/ai-models.toml
```

`auto` usa o arquivo do operador quando ele existe e recorre à baseline empacotada quando ele não existe. `factory` ignora o arquivo do operador; `file` exige que o caminho configurado exista e seja válido.

Isso permite adicionar ou desativar modelos de providers já integrados, alterar default, reasoning permitido e elegibilidade ao `AUTO`, sem alterar código quando o novo modelo continuar compatível com o protocolo do adapter existente.

Detalhamento e exemplos: [AI_MODEL_CONFIGURATION.md](AI_MODEL_CONFIGURATION.md).

### Catálogo de fábrica em 03/10/2026

| Provider | Default público | Reasoning default |
|---|---|---|
| OpenAI | `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.6-flash` | `NONE` |
| xAI | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `NONE` |
| Gemini | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `LOW` |
| Mistral | `mistral-small-2603` | `PROVIDER_DEFAULT` |
| Cohere | `command-a-03-2025` | `PROVIDER_DEFAULT` |
| Kimi / Moonshot | `kimi-k3` | `LOW` |
| GitHub Copilot | `auto` | `PROVIDER_DEFAULT` |

Essa tabela é somente a fotografia de fábrica. O catálogo efetivamente snapshotado para a execução é a autoridade da AUD.

MiMo V2.6 é a família vigente para o contrato PAYG do RASAi. `mimo-v2.5` e `mimo-v2.5-pro` permanecem selecionáveis somente até 21/10/2026 02:00 UTC e não são mais defaults. A troca preserva o mesmo adapter Responses e a mesma variável `MIMO_API_KEY`; detalhes e rastreabilidade estão na issue #183.

## Seleção do modelo e reasoning

As variáveis por provider continuam selecionando o modelo efetivo, por exemplo:

```ini
RASAI_OPENAI_MODEL = gpt-5.6-luna
RASAI_OPENAI_REASONING_EFFORT = NONE
```

O modelo precisa existir, estar habilitado/selecionável e vigente no catálogo. O reasoning precisa pertencer a `reasoning_values` **daquele modelo**. Configuração inválida é rejeitada; não existe troca silenciosa para outro modelo.

O default RASAi de reasoning é sempre o **menor nível válido suportado pelo modelo e pelo wire contract implementado**. Por isso OpenAI, DeepSeek, MiMo e Qwen usam `NONE`; xAI, Gemini e Anthropic usam `LOW`; Mistral Small 4 e Copilot `auto` permanecem em `PROVIDER_DEFAULT` enquanto não houver controle determinístico implementado.

## Credenciais

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
MISTRAL_API_KEY
COHERE_API_KEY
COPILOT_GITHUB_TOKEN
```

A presença de uma credencial não garante saldo, quota, assinatura ou acesso ao modelo.

MiMo PAYG usa credencial compatível com o adapter atual. GitHub Copilot usa token de usuário compatível com o SDK; o fluxo local recomendado usa fine-grained PAT com `Copilot Requests`, e o adapter desativa fallback para outra sessão GitHub local.

Referência: [PROVIDER_SETUP.md](PROVIDER_SETUP.md).

## Contexto editorial

Quando configurado, o RASAi fornece contexto editorial explícito à IA:

```text
risk profile
YMYL category
page purpose
intended audience
experience requirement
freshness sensitivity
content origin
```

Campos em `auto` podem gerar apenas uma interpretação transitória baseada nas evidências disponíveis. Essa interpretação não substitui a configuração oficial, não vira evidência determinística e não altera diretamente scoring.

O RASAi não deve inferir como fato credenciais, compliance, revisão profissional, reputação externa, experiência pessoal ou processo editorial oculto.

Referências: [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md) e [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md).

## AUTO, preço e fallback

Modelos e preços são catálogos separados:

```text
config/ai-models.toml   -> capacidade e elegibilidade
config/ai-pricing.toml  -> política comercial
```

Para cada provider, o `AUTO` resolve um modelo efetivo a partir do override do provider ou do `public_default` do catálogo. O candidato entra no pool quando:

1. provider e modelo são tecnicamente válidos;
2. há credencial/configuração válida;
3. o modelo está habilitado, vigente e `auto_eligible=true`;
4. o provider não está inelegível pela saúde/quarentena;
5. o pricing é resolvido quando houver regra/contexto compatível, exclusivamente para ordenar e telemetrar custo.

O runtime estima o custo da necessidade atual quando isso é reproduzível e ordena primeiro os candidatos precificados do menor para o maior custo. A ordem pode mudar por horário, tokens, contexto, cache e reasoning.

**Modelo elegível sem pricing vigente permanece `UNPRICED` no `AUTO`.** Ele é tentado depois dos candidatos precificados; ausência de preço nunca é tratada como custo zero nem como inelegibilidade. Na seleção explícita, pricing também não é gate: a falta de preço não bloqueia a chamada de um provider que esteja configurado e apto.

Cada provider pode ser chamado no máximo uma vez **por ciclo** da mesma necessidade. O default é 3 ciclos com espera de 60 s somente entre ciclos. Falhas transitórias permanecem recuperáveis; falhas terminais normalizadas retiram o provider do restante da AUD/RPR. Provider explícito usa exatamente o mesmo contrato com pool unitário.

Detalhes: [AUTO_COST_AWARE_AI_ROUTING.md](AUTO_COST_AWARE_AI_ROUTING.md) e [AI_PRICING_CONFIGURATION.md](AI_PRICING_CONFIGURATION.md).

## Política de execução

```text
RASAI_AI_TIMEOUT_SECONDS=180
RASAI_AI_MAX_CYCLES=3
RASAI_AI_CYCLE_DELAY_SECONDS=60
```

- **timeout**: limite de uma tentativa externa de provider;
- **max cycles**: orçamento de ciclos por necessidade lógica de IA, reiniciado a cada nova necessidade;
- **cycle delay**: espera apenas entre ciclos, nunca entre providers do mesmo ciclo.

`Retry-After` transitório pode elevar a espera efetiva até o cap canônico de 300 s. O adapter não executa retry nem `sleep` próprio. O timeout/cadência não representam duração máxima da auditoria completa.

## Structured output e validação local

O schema local do RASAi permanece normativo. Quando o wire format do provider aceita apenas um subconjunto do contrato, o runtime adapta o transporte e mantém as validações locais depois da resposta.

Erro de schema/request é erro técnico de integração, não defeito do website auditado.

## Remediações e análises especializadas

As superfícies opcionais não possuem provider/modelo paralelo. Quando usam IA, recebem a mesma seleção principal:

```text
provider explícito
ou
AUTO central
```

Em `AUTO` ou provider explícito, isso reutiliza o mesmo motor de ciclos, custo, qualification, pricing, health, quarentena e fallback. A finalidade pode alterar requisitos e tamanho estimado de input/output, mas não cria outro mecanismo de retry/roteamento.

## Mistral AI

A integração usa `mistral-small-2603`, `MISTRAL_API_KEY` e Chat Completions no endpoint global com `service_tier=standard_only`. Structured Outputs continuam sujeitos à validação local evidence-bound. O provider está elegível ao AUTO quando configurado e apto.

## Cohere

A integração inicial usa `COHERE_API_KEY`, `command-a-03-2025` e `POST https://api.cohere.com/v2/chat`. Structured Outputs são projetados para o subconjunto JSON Schema aceito pelo wire da Cohere, mas o schema local do RASAi continua normativo e é validado integralmente após a resposta.

O adapter não envia `tools` nem `documents`, e não habilita RAG/Rerank. Reasoning permanece `PROVIDER_DEFAULT`. Para pricing, `RASAI_COHERE_COMMERCIAL_MODE` aceita `UNKNOWN`, `TRIAL` ou `PRODUCTION`; `UNKNOWN` mantém o custo UNPRICED, `TRIAL` aplica custo monetário zero conforme a política oficial de trial e `PRODUCTION` aplica a tarifa pública token-based. Cohere está elegível ao AUTO quando configurado e apto.

## GitHub Copilot

O adapter usa o SDK oficial `github-copilot-sdk` e o modelo de fábrica `auto`:

```text
RASAI_COPILOT_MODEL=auto
COPILOT_GITHUB_TOKEN=<token de usuário>
```

Instalação opcional:

```powershell
python -m pip install -e ".[copilot]"
```

A autenticação usa o token configurado e `use_logged_in_user=false`. O RASAi disponibiliza apenas a inferência necessária ao contrato evidence-bound e não habilita tools de edição/shell/browser. Copilot pode participar do AUTO quando configurado; use `RASAI_AI_AUTO_EXCLUDE=copilot` para evitar consumo automático.

## Telemetria

Quando disponível, cada tentativa registra de forma sanitizada:

```text
provider
modelo
reasoning profile
status
horários e duração
tokens input/cache/output/reasoning/total
custo estimado
moeda
versão de pricing
diagnóstico técnico
```

A execução também preserva a versão do catálogo de pricing. No console local, os arquivos de configuração de IA usados pela AUD são snapshotados no início da execução. No SaaS, modelo e pricing são fixados por snapshot de job, com versão e hash, para que uma publicação administrativa durante a auditoria não altere uma execução em andamento.

Secrets, headers de autenticação, passwords/client secrets e conteúdo reconhecido como raciocínio privado não são persistidos como telemetria pública.

## Console e persistência

O console permite selecionar provider/modelo/reasoning apenas entre valores válidos do catálogo efetivo. `rasai-console.ini` pode persistir configuração não sensível; API keys e tokens não são gravados nesse arquivo.

Os catálogos em `config/` também não são secret stores. Suas origens e caminhos são configuração administrativa persistível. Salvar uma alteração neles não modifica uma AUD que já começou; a próxima AUD resolve e snapshotará novamente os arquivos.

## Referências

- [AI_MODEL_CONFIGURATION.md](AI_MODEL_CONFIGURATION.md)
- [AI_PRICING_CONFIGURATION.md](AI_PRICING_CONFIGURATION.md)
- [AI_TASK_PROFILES.md](AI_TASK_PROFILES.md)
- [AUTO_COST_AWARE_AI_ROUTING.md](AUTO_COST_AWARE_AI_ROUTING.md)
- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
