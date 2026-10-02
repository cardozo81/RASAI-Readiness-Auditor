# Configuração de providers de IA e SERP

Este documento é a referência operacional para descobrir qual provider selecionar, qual variável configurar e qual contrato o runtime aplica. Para criação de credenciais, finalidade funcional, permissões e links oficiais, consulte [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

Ofertas comerciais, quotas e franquias gratuitas pertencem aos fornecedores e podem mudar sem alteração do RASAi. Informações comerciais exibidas pelo catálogo são snapshots de onboarding e devem ser confirmadas na fonte oficial antes de uso operacional.

## 1. Consultar providers pelo RASAi

```powershell
rasai providers
```

Filtros:

```powershell
rasai providers --kind ai
rasai providers --kind serp
rasai providers --provider copilot
rasai providers --provider github-copilot
rasai providers --provider zenserp
rasai providers --configured-only
rasai providers --json
```

A saída informa:

- ID e aliases;
- nome do provider;
- variável de credencial;
- estado `SET`/`NÃO CONFIGURADA`;
- URL oficial para obter ou gerenciar credencial;
- URL de documentação;
- modelo público efetivo, quando IA;
- valores de reasoning aceitos pelo runtime;
- qualificação, elegibilidade em `AUTO` e `explicit-only`;
- engine e metadados de quota, quando SERP.

Nenhum valor de token ou API key é retornado, inclusive em `--json`. A saída estruturada contém somente o estado de configuração.

### Modelo público e modelo interno do adapter

O default público mostrado por `rasai providers` é o valor efetivamente resolvido pelo contrato de runtime quando o usuário não informa modelo. Um adapter pode manter parâmetros internos usados por sua política técnica, mas esses valores não substituem o default público documentado.

A lista de reasoning exibida pelo comando é o domínio aceito pelo runtime para o provider correspondente.

## 2. Providers de IA

| Seleção RASAi | Provider | Variável de credencial | Default público | URL para credencial | Observação |
|---|---|---|---|---|---|
| `openai` | OpenAI | `OPENAI_API_KEY` | `gpt-5.6-luna` | <https://platform.openai.com/api-keys> | API é contratada separadamente de planos do ChatGPT. |
| `deepseek` | DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` | <https://platform.deepseek.com/api_keys> | chave da plataforma/API DeepSeek |
| `mimo` | Xiaomi MiMo | `MIMO_API_KEY` | `mimo-v2.6-flash` | <https://mimo.mi.com/> | PAYG `sk-...`; v2.5/pro legados até 21/10/2026 02:00 UTC |
| `xai` / `grok` | xAI / Grok | `XAI_API_KEY` | `grok-4.6` | <https://console.x.ai/> | API key xAI |
| `qwen` | Alibaba Qwen / Model Studio | `DASHSCOPE_API_KEY` | `qwen3.8-flash` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | região da key e endpoint devem ser coerentes |
| `gemini` | Google Gemini | `GEMINI_API_KEY` | `gemini-3.8-flash` | <https://aistudio.google.com/apikey> | Gemini API key |
| `anthropic` / `claude` | Anthropic Claude | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | <https://console.anthropic.com/> | Anthropic API key |
| `mistral` | Mistral AI | `MISTRAL_API_KEY` | `mistral-small-2603` | <https://console.mistral.ai/api-keys/> | explicit-only durante a homologação inicial; endpoint global Standard fixo |
| `copilot` / `github-copilot` | GitHub Copilot | `COPILOT_GITHUB_TOKEN` | `auto` | <https://github.com/settings/personal-access-tokens/new> | usa assinatura Copilot elegível; não entra em `AI=auto` |

### Xiaomi MiMo - migração V2.6

O RASAi continua usando o mesmo serviço PAYG e o mesmo endpoint Responses. A mudança oficial é de **modelo**, não de adapter:

- default público: `mimo-v2.6-flash`;
- default do adapter: `mimo-v2.6-pro`;
- `mimo-v2.5` e `mimo-v2.5-pro`: somente legado até 21/10/2026 02:00 UTC;
- reasoning default RASAi: `NONE`;
- Token Plan, Batch, UltraSpeed, tools, web search e multimodal não são opções do contrato atual.

A migração é rastreada na [issue #183](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/183).

### Passo a passo detalhado para obtenção das credenciais

A tabela acima é a referência rápida. O procedimento canônico, com pré-requisitos, criação da credencial, permissões, configuração segura, validação sem exposição do segredo, smoke e falhas comuns, está centralizado em [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md):

- [OpenAI](EXTERNAL_CREDENTIALS.md#openai);
- [DeepSeek](EXTERNAL_CREDENTIALS.md#deepseek);
- [Xiaomi MiMo](EXTERNAL_CREDENTIALS.md#xiaomi-mimo);
- [xAI / Grok](EXTERNAL_CREDENTIALS.md#xai--grok);
- [Alibaba Qwen / Model Studio](EXTERNAL_CREDENTIALS.md#alibaba-qwen--model-studio);
- [Google Gemini](EXTERNAL_CREDENTIALS.md#google-gemini);
- [Anthropic Claude](EXTERNAL_CREDENTIALS.md#anthropic-claude);
- [Mistral AI](EXTERNAL_CREDENTIALS.md#mistral-ai);
- [GitHub Copilot](EXTERNAL_CREDENTIALS.md#github-copilot).

Regra de segurança: a documentação mostra nomes de variáveis e placeholders, nunca valores reais. `Test-Path Env:<VAR>` confirma apenas presença; validade/autorização deve ser verificada pelo diagnóstico seguro do RASAi antes de um smoke que possa consumir quota/custo.

**Escopo:** este guia descreve somente modalidades efetivamente consumidas pelo RASAi. Capacidades, planos, endpoints, tiers ou métodos de autenticação oferecidos pelos fornecedores mas ainda não implementados/homologados não são opções do produto. A análise dessas variantes está rastreada na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

### Mistral AI

Configuração mínima:

```powershell
$env:MISTRAL_API_KEY="<mistral-api-key>"
rasai audit https://example.com --ai-provider mistral --ai-model mistral-small-2603
```

Contrato inicial:

- modelo de fábrica: `mistral-small-2603`;
- endpoint fixo: `https://api.mistral.ai/v1/chat/completions`;
- autenticação Bearer com `MISTRAL_API_KEY`;
- Structured Outputs por JSON Schema, seguidos da validação local do RASAi;
- `service_tier=standard_only`;
- sem `RASAI_MISTRAL_ENDPOINT` nesta etapa;
- sem participação em `AI=auto` até homologação humana posterior.

A integração não habilita tools, web search, agents ou connectors da Mistral nesta entrega. Essas capacidades não fazem parte do contrato atual do RASAi; eventual avaliação futura está rastreada na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180). O adapter reutiliza o mesmo boundary evidence-bound, retry, telemetria e secret-safety dos providers semânticos existentes.

Documentação oficial:

- criação da API key: <https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key>
- primeira chamada: <https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request>
- modelo Mistral Small 4: <https://docs.mistral.ai/models/mistral-small-4-0-26-03>
- pricing: <https://docs.mistral.ai/inference/pricing>

### GitHub Copilot

O RASAi usa GitHub Copilot SDK com credencial de usuário explicitamente configurada.

Fluxo recomendado para o adapter atual:

1. confirme que a conta GitHub possui assinatura Copilot elegível;
2. abra <https://github.com/settings/personal-access-tokens/new>;
3. crie um fine-grained personal access token da conta pessoal;
4. conceda a permissão de conta `Copilot Requests`;
5. configure o valor em `COPILOT_GITHUB_TOKEN`;
6. selecione `copilot` no RASAi.

Tokens de usuário aceitos pelo contrato atual:

```text
github_pat_
gho_
ghu_
```

Classic PAT `ghp_` não é aceito por esse adapter.

Instalação do SDK opcional:

```powershell
python -m pip install -e ".[copilot]"
```

O adapter usa `use_logged_in_user=False`, portanto uma sessão GitHub já autenticada na máquina não é consumida silenciosamente.

O provider Copilot é `explicit-only` e não participa do pool `AI=auto`.

Documentação oficial:

- autenticação do Copilot SDK: <https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth>
- OAuth e tipos de token de usuário: <https://docs.github.com/en/copilot/how-tos/copilot-sdk/setup/github-oauth>

## 3. Providers SERP

| `RASAI_SERP_PROVIDER` | Engine | Variável de credencial | URL para credencial | Observação de onboarding |
|---|---|---|---|---|
| `serpapi` | Google | `RASAI_SERPAPI_API_KEY` | <https://serpapi.com/manage-api-key> | provider externo com quota comercial própria |
| `serpapi-bing` | Bing | `RASAI_SERPAPI_API_KEY` | <https://serpapi.com/manage-api-key> | compartilha a conta SerpApi |
| `zenserp` | Google | `RASAI_ZENSERP_API_KEY` | <https://app.zenserp.com/> | provider externo com quota comercial própria |
| `scrapingdog` | Google | `RASAI_SCRAPINGDOG_API_KEY` | <https://api.scrapingdog.com/> | cobrança/quota do fornecedor pode ser baseada em créditos |

O RASAi não classifica nenhum adapter SERP externo vigente como gratuito e ilimitado. Free tier, quando existente, não elimina os limites locais do RASAi e não garante disponibilidade.

## 4. Como configurar SERP

SerpApi/Google:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="serpapi"
$env:RASAI_SERPAPI_API_KEY="<sua-chave>"
```

Zenserp:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="zenserp"
$env:RASAI_ZENSERP_API_KEY="<sua-chave>"
```

ScrapingDog:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="scrapingdog"
$env:RASAI_SCRAPINGDOG_API_KEY="<sua-chave>"
```

O console mostra provider, variável de credencial, URL de cadastro/login e orientação de quota. O segredo permanece oculto e não é persistido no `rasai-console.ini`.

## 5. Limites locais e quota do fornecedor

Variáveis locais:

```text
RASAI_SERP_MAX_QUERIES
RASAI_SERP_MAX_REQUESTS
RASAI_SERP_MAX_DEPTH
RASAI_SERP_RETRIES
RASAI_SERP_MIN_INTERVAL_SECONDS
RASAI_SERP_TIMEOUT_SECONDS
```

`RASAI_SERP_MAX_REQUESTS` é orçamento de tentativas HTTP do RASAi, não saldo de créditos comerciais.

A quota e o faturamento do fornecedor são autoritativos. O RASAi não interpreta free tier como garantia de custo zero.

A estratégia de paginação pertence ao contrato do adapter. Providers de página fixa permitem teto determinístico de requests; paginação dirigida pelo fornecedor usa `RASAI_SERP_MAX_REQUESTS` como orçamento rígido.

## 6. Segurança

- nunca coloque credenciais reais em documentação, issue, commit, relatório ou arquivo de URLs;
- secrets devem permanecer em variável de ambiente ou secret store;
- o console mostra somente presença/estado da credencial;
- `rasai providers --json` não retorna secret;
- presença de key não comprova saldo, quota ou permissão;
- falha de provider é falha de integração, não finding do website;
- IA e SERP permanecem desacoplados do scoring determinístico, salvo contratos explicitamente versionados de evidência que não dependam da credencial SERP.

## 7. Fontes técnicas no código

Metadados de IA:

```text
src/rasai/provider_registry.py
```

Defaults públicos e reasoning:

```text
src/rasai/provider_runtime_policy.py
```

Metadados SERP:

```text
src/rasai/search_intelligence/provider_catalog.py
```

Onboarding sem exposição de segredo:

```text
src/rasai/provider_onboarding.py
```

Composição SERP:

```text
src/rasai/search_intelligence/runtime.py
```

Integrações de IA adicionais:

```text
src/rasai/provider_extensions.py   # inclui Mistral
src/rasai/copilot_provider.py      # Copilot
```

Documentos relacionados:

- [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [AI_GUIDE.md](AI_GUIDE.md)
- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
