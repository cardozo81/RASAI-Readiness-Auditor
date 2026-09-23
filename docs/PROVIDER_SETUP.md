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
| `mimo` | Xiaomi MiMo | `MIMO_API_KEY` | `mimo-v2.5` | <https://mimo.mi.com/> | adapter exige chave PAYG `sk-...`; `tp-...` não é aceita |
| `xai` / `grok` | xAI / Grok | `XAI_API_KEY` | `grok-4.6` | <https://console.x.ai/> | API key xAI |
| `qwen` | Alibaba Qwen / Model Studio | `DASHSCOPE_API_KEY` | `qwen3.8-flash` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | região da key e endpoint devem ser coerentes |
| `gemini` | Google Gemini | `GEMINI_API_KEY` | `gemini-3.8-flash` | <https://aistudio.google.com/apikey> | Gemini API key |
| `anthropic` / `claude` | Anthropic Claude | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | <https://console.anthropic.com/> | Anthropic API key |
| `copilot` / `github-copilot` | GitHub Copilot | `COPILOT_GITHUB_TOKEN` | `auto` | <https://github.com/settings/personal-access-tokens/new> | usa assinatura Copilot elegível; não entra em `AI=auto` |

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

Integração Copilot:

```text
src/rasai/copilot_provider.py
```

Documentos relacionados:

- [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [AI_GUIDE.md](AI_GUIDE.md)
- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
