# Configuração de providers de IA e SERP

Este documento é a referência operacional para descobrir **qual provider selecionar, qual variável configurar e em qual URL oficial criar ou gerenciar a credencial**.

As ofertas comerciais e franquias gratuitas pertencem aos fornecedores e podem mudar sem alteração de código do RASAi. As informações de free tier abaixo foram verificadas em **11/09/2026** e devem ser confirmadas no site do provider antes de uso em produção.

## 1. Providers de IA

| Seleção RASAi | Provider | Variável de credencial | URL para login/chave | Observação |
|---|---|---|---|---|
| `openai` | OpenAI | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> | API é faturada separadamente do ChatGPT. |
| `deepseek` | DeepSeek | `DEEPSEEK_API_KEY` | <https://platform.deepseek.com/api_keys> | Credencial da plataforma/API. |
| `mimo` | Xiaomi MiMo | `MIMO_API_KEY` | <https://mimo.mi.com/> | Adapter atual usa chave PAYG `sk-...`; Token Plan `tp-...` não é compatível. |
| `xai` / `grok` | xAI / Grok | `XAI_API_KEY` | <https://console.x.ai/> | Credencial da API xAI. |
| `qwen` | Alibaba Qwen / Model Studio | `DASHSCOPE_API_KEY` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | A região/endpoint deve permanecer coerente com a chave. |
| `gemini` | Google Gemini | `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> | Chave do Google AI Studio/Gemini API. |
| `anthropic` / `claude` | Anthropic Claude | `ANTHROPIC_API_KEY` | <https://console.anthropic.com/> | Credencial da Anthropic API. |
| `copilot` / `github-copilot` | GitHub Copilot | `COPILOT_GITHUB_TOKEN` | <https://github.com/settings/personal-access-tokens/new> | Usa a assinatura Copilot elegível do usuário via SDK oficial; não entra em `AUTO`. |

### GitHub Copilot

O RASAi usa o **GitHub Copilot SDK**, não uma API key de modelo da OpenAI/Anthropic. Para a integração local:

1. confirme que a conta GitHub possui uma assinatura Copilot elegível;
2. abra <https://github.com/settings/personal-access-tokens/new>;
3. crie um **fine-grained personal access token** da conta pessoal;
4. conceda a permissão de conta **Copilot Requests**;
5. configure o token em `COPILOT_GITHUB_TOKEN`;
6. selecione `copilot` no RASAi.

Tokens de usuário aceitos pelo contrato atual incluem prefixos `github_pat_`, `gho_` e `ghu_`. Classic PAT `ghp_` não é aceito pelo Copilot SDK para este fluxo.

Instalação do SDK opcional:

```powershell
python -m pip install -e ".[copilot]"
```

O adapter força `use_logged_in_user=False`. Isso é deliberado: uma auditoria não deve consumir silenciosamente uma sessão GitHub/Copilot diferente da credencial explicitamente configurada no RASAi.

O provider Copilot é **explicit-only** e não participa do pool `AI=auto`. Essa decisão evita consumo involuntário da franquia/créditos da assinatura.

Documentação oficial de autenticação do SDK: <https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/authenticate>.

## 2. Providers SERP com plano gratuito

`gratuito` significa que o fornecedor possuía uma franquia gratuita verificável na data acima. **Não significa ilimitado** e não elimina os limites locais do RASAi.

| `RASAI_SERP_PROVIDER` | Engine | Variável de credencial | URL para login/chave | Franquia gratuita verificada em 11/09/2026 |
|---|---|---|---|---|
| `serpapi` | Google | `RASAI_SERPAPI_API_KEY` | <https://serpapi.com/manage-api-key> | 250 pesquisas/mês. |
| `serpapi-bing` | Bing | `RASAI_SERPAPI_API_KEY` | <https://serpapi.com/manage-api-key> | Compartilha a franquia da conta SerpApi. |
| `zenserp` | Google | `RASAI_ZENSERP_API_KEY` | <https://app.zenserp.com/> | 50 pesquisas/mês. |
| `scrapingdog` | Google | `RASAI_SCRAPINGDOG_API_KEY` | <https://api.scrapingdog.com/> | 200 créditos/mês; Google Search padrão custa 5 créditos/request e mobile 10 créditos/request. |

Não existe, entre os adapters integrados, um serviço SERP externo confiável classificado como **gratuito e ilimitado**. Scraping/self-hosted pode evitar cobrança por request, mas transfere CAPTCHA, bloqueio de IP, proxies, localização, manutenção e confiabilidade metodológica para o operador; por isso não é tratado como equivalente a um provider SERP auditável.

`Serper` não foi incluído nesta classificação porque a oferta pública vigente não permitiu confirmar com segurança um free tier recorrente. O RASAi não deve documentar como gratuito aquilo que não esteja verificável no momento da integração.

## 3. Como configurar SERP

Exemplo SerpApi/Google:

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

O console interativo mostra o nome do provider selecionado, a variável de credencial correspondente, a URL de cadastro/login e a nota de franquia gratuita. O secret continua oculto e não é persistido no `rasai-console.ini`.

## 4. Limites locais versus quota do fornecedor

Estas variáveis continuam limitando o RASAi independentemente da franquia externa:

```text
RASAI_SERP_MAX_QUERIES
RASAI_SERP_MAX_REQUESTS
RASAI_SERP_MAX_DEPTH
RASAI_SERP_RETRIES
RASAI_SERP_MIN_INTERVAL_SECONDS
RASAI_SERP_TIMEOUT_SECONDS
```

`RASAI_SERP_MAX_REQUESTS` é um orçamento de **tentativas HTTP**, não um saldo de créditos comerciais. Em providers com precificação por créditos, como ScrapingDog, uma tentativa pode consumir mais de um crédito.

A quota/faturamento real do fornecedor é sempre autoritativa. O RASAi não interpreta free tier como garantia de disponibilidade nem de custo zero.

## 5. Segurança

- nunca coloque credenciais reais em documentação, issue, commit, relatório ou arquivo de URLs;
- secrets devem permanecer em variável de ambiente/secret store;
- o console mostra somente `[SET]` para credenciais;
- a presença de uma chave não comprova saldo, quota ou permissão;
- falha de provider é falha de integração, não finding do website;
- providers de IA e SERP continuam desacoplados do scoring determinístico.

## 6. Fontes técnicas no código

Metadados de IA:

```text
src/rasai/provider_registry.py
```

Metadados SERP:

```text
src/rasai/search_intelligence/provider_catalog.py
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

- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [AI_GUIDE.md](AI_GUIDE.md)
- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
