# Credenciais e integrações externas

## Objetivo

Este documento é a referência operacional para credenciais, tokens e API keys usados pelo RASAi. Ele descreve para que cada credencial serve, qual funcionalidade a consome, quais dependências precisam existir, onde criar ou gerenciar a credencial e quais limites de segurança devem ser observados.

O RASAi está em pré-publicação. Este documento descreve somente o contrato vigente. Não há contrato de compatibilidade com versões públicas anteriores.

Credenciais reais nunca devem ser incluídas em documentação, issue, commit, relatório, `audit.db`, `rasai-console.ini`, payload durável de job ou log.

## Regras gerais de segurança

- use secret store ou variável de ambiente para valores secretos;
- conceda somente as permissões necessárias à funcionalidade usada;
- prefira credenciais separadas por ambiente e finalidade;
- restrinja API keys por API, origem, aplicação ou rede quando o fornecedor oferecer essa opção;
- revogue credenciais que não sejam mais necessárias;
- trate `SET` ou `configured=true` apenas como presença da credencial, não como prova de validade, saldo, quota ou autorização;
- URLs de criação e documentação abaixo apontam para fontes oficiais do fornecedor;
- preços, quotas e políticas comerciais pertencem ao fornecedor e devem ser confirmados antes de uso operacional.

## Providers de IA

As credenciais desta seção são usadas apenas quando o provider correspondente é selecionado ou quando participa de uma política `AUTO` para a qual seja elegível. A API de cada provider é independente de assinaturas de produtos de chat, salvo quando explicitamente indicado.

| Provider | Variável | Uso no RASAi | Onde criar ou gerenciar | Orientação |
|---|---|---|---|---|
| OpenAI | `OPENAI_API_KEY` | análise semântica, remediação e demais finalidades de IA que selecionem `openai` | <https://platform.openai.com/api-keys> | criar uma API key da plataforma OpenAI. A cobrança da API é separada de planos do ChatGPT. |
| DeepSeek | `DEEPSEEK_API_KEY` | finalidades de IA que selecionem `deepseek` | <https://platform.deepseek.com/api_keys> | criar uma chave da plataforma/API DeepSeek e manter saldo/quota adequados. |
| Xiaomi MiMo | `MIMO_API_KEY` | finalidades de IA que selecionem `mimo` | <https://mimo.mi.com/> | usar a credencial de API aceita pelo adapter. O runtime atual valida chave PAYG com prefixo `sk-`; Token Plan `tp-` não faz parte do contrato do adapter. |
| xAI / Grok | `XAI_API_KEY` | finalidades de IA que selecionem `xai` ou alias `grok` | <https://console.x.ai/> | criar uma API key no console xAI. |
| Alibaba Qwen / Model Studio | `DASHSCOPE_API_KEY` | finalidades de IA que selecionem `qwen` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | criar a API key no Model Studio e manter região da chave e endpoint coerentes. |
| Google Gemini | `GEMINI_API_KEY` | finalidades de IA que selecionem `gemini` | <https://aistudio.google.com/apikey> | criar uma Gemini API key no Google AI Studio. |
| Anthropic Claude | `ANTHROPIC_API_KEY` | finalidades de IA que selecionem `anthropic` ou alias `claude` | <https://console.anthropic.com/> | criar e gerenciar a API key no console Anthropic. |
| GitHub Copilot | `COPILOT_GITHUB_TOKEN` | provider `copilot`, explicitamente selecionado | <https://github.com/settings/personal-access-tokens/new> | criar um fine-grained personal access token pertencente à conta pessoal, adicionar a permissão de conta `Copilot Requests` e manter assinatura Copilot elegível. |

### GitHub Copilot

O adapter vigente usa autenticação de usuário do GitHub Copilot SDK com `use_logged_in_user=False`. O token é fornecido explicitamente ao RASAi.

Tipos aceitos pelo contrato atual do adapter:

```text
github_pat_  fine-grained personal access token
gho_         OAuth user access token
ghu_         GitHub App user access token
```

Classic PAT `ghp_` não é aceito nesse fluxo. A documentação oficial do GitHub confirma esses tipos de token para autenticação de usuário no Copilot SDK: <https://docs.github.com/en/copilot/how-tos/copilot-sdk/setup/github-oauth>.

Para o caminho mais simples de uso local:

1. confirme que a conta possui Copilot elegível;
2. abra <https://github.com/settings/personal-access-tokens/new>;
3. selecione a própria conta como resource owner;
4. em permissões de conta, adicione `Copilot Requests`;
5. gere o token e armazene-o com segurança;
6. configure o valor em `COPILOT_GITHUB_TOKEN`;
7. selecione `copilot` no RASAi.

O GitHub também documenta OAuth de usuário e autenticação server-to-server para outros cenários. Esses métodos não devem ser presumidos como equivalentes ao adapter vigente sem suporte explícito do runtime. Referência geral: <https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth>.

## Providers SERP

Estas credenciais são consumidas somente quando `RASAI_SERP_MODE=live` e o provider correspondente é selecionado.

| Provider | Variável | Engine | Onde criar ou gerenciar | Dependência funcional |
|---|---|---|---|---|
| SerpApi / Google | `RASAI_SERPAPI_API_KEY` | Google | <https://serpapi.com/manage-api-key> | `RASAI_SERP_PROVIDER=serpapi` |
| SerpApi / Bing | `RASAI_SERPAPI_API_KEY` | Bing | <https://serpapi.com/manage-api-key> | `RASAI_SERP_PROVIDER=serpapi-bing` |
| Zenserp | `RASAI_ZENSERP_API_KEY` | Google | <https://app.zenserp.com/> | `RASAI_SERP_PROVIDER=zenserp` |
| ScrapingDog | `RASAI_SCRAPINGDOG_API_KEY` | Google | <https://api.scrapingdog.com/> | `RASAI_SERP_PROVIDER=scrapingdog` |

`RASAI_SERP_MAX_REQUESTS` limita tentativas HTTP feitas pelo RASAi. Não representa a quantidade de créditos comerciais do fornecedor. Um request pode consumir mais de um crédito conforme a política externa.

Consulte também [PROVIDER_SETUP.md](PROVIDER_SETUP.md) e [SERP_OBSERVATION.md](SERP_OBSERVATION.md).

## Google PageSpeed Insights

### Credencial

```text
RASAI_PAGESPEED_API_KEY
```

### Finalidade

Autoriza chamadas automatizadas à PageSpeed Insights API usadas para coletar dados Lighthouse e informações retornadas pelo serviço quando Web Performance/PageSpeed estiver elegível.

### Como obter

Referência oficial: <https://developers.google.com/speed/docs/insights/v5/get-started>.

O Google permite chamadas PageSpeed sem key em alguns cenários, mas recomenda chave para uso automatizado/frequente. O contrato do RASAi exige `RASAI_PAGESPEED_API_KEY` para tornar esse serviço elegível automaticamente.

Fluxo básico:

1. acesse o Google Cloud Console;
2. selecione ou crie um projeto;
3. habilite a PageSpeed Insights API quando necessário;
4. abra a página de credenciais: <https://console.cloud.google.com/apis/credentials>;
5. crie uma API key;
6. aplique restrições de API e de uso compatíveis com o ambiente;
7. configure a chave em `RASAI_PAGESPEED_API_KEY`.

A key não é persistida no INI.

## Chrome UX Report - CrUX e CrUX History

### Credencial

```text
RASAI_CRUX_API_KEY
```

### Finalidade

A mesma Google Cloud API key pode ser usada pela API CrUX atual e pela CrUX History API. O RASAi usa essas integrações para dados agregados de experiência real de usuários em escopo de URL ou origem, sem converter ausência de dados em falha do website.

### Como obter

Referências oficiais:

- CrUX API: <https://developer.chrome.com/docs/crux/api/>
- CrUX History API: <https://developer.chrome.com/docs/crux/history-api/>
- Google Cloud Credentials: <https://console.cloud.google.com/apis/credentials>

Fluxo básico:

1. selecione ou crie um projeto no Google Cloud;
2. habilite `Chrome UX Report API`;
3. crie uma API key em Credentials;
4. restrinja a key à API quando aplicável;
5. configure `RASAI_CRUX_API_KEY`.

A documentação oficial informa que a mesma key pode atender a API diária e a API histórica. A existência da key não garante que uma URL tenha amostra CrUX elegível.

## Google Search Console

### Credencial e contexto

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

`RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` é um OAuth 2.0 access token. Não é uma API key permanente.

`RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` identifica a propriedade à qual o usuário autenticado precisa ter acesso, por exemplo:

```text
sc-domain:example.com
https://www.example.com/
```

### Finalidade

O token autoriza as coletas Search Console habilitadas pelo RASAi, incluindo Search Analytics, Sitemaps e URL Inspection conforme o escopo e os limites configurados.

### Como obter

Referências oficiais:

- pré-requisitos: <https://developers.google.com/webmaster-tools/v1/prereqs>
- autorização OAuth 2.0: <https://developers.google.com/webmaster-tools/v1/how-tos/authorizing>
- credenciais Google Cloud: <https://console.cloud.google.com/apis/credentials>
- referência da API: <https://developers.google.com/webmaster-tools/v1/api_reference_index>

Fluxo básico:

1. confirme que a conta Google tem acesso à propriedade Search Console;
2. crie ou selecione um projeto no Google Cloud;
3. habilite a Search Console API;
4. configure a tela de consentimento quando aplicável;
5. crie credenciais OAuth 2.0 adequadas ao tipo de aplicação;
6. solicite consentimento com o menor escopo suficiente;
7. obtenha um access token válido e configure-o temporariamente em `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`;
8. configure a property exata em `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`.

Escopos oficiais relevantes:

```text
https://www.googleapis.com/auth/webmasters.readonly
https://www.googleapis.com/auth/webmasters
```

Para a natureza observacional do RASAi, prefira o escopo read-only quando ele atender aos endpoints efetivamente usados.

O runtime atual recebe o access token já emitido. O RASAi não deve documentar a API key do Google como substituta do OAuth exigido para dados privados do Search Console.

## Microsoft Clarity Data Export

### Credencial

```text
RASAI_CLARITY_API_TOKEN
```

### Finalidade

Autoriza a Data Export API para métricas comportamentais agregadas, como engagement, scroll, rage/dead clicks e erros de script. A integração é opt-in e não altera SARI.

### Como obter

Referência oficial: <https://learn.microsoft.com/clarity/setup-and-installation/clarity-data-export-api>.

Fluxo básico:

1. entre no projeto no Microsoft Clarity;
2. abra `Settings`;
3. acesse `Data Export`;
4. selecione `Generate new API token`;
5. dê um nome identificável ao token;
6. copie o token e armazene-o com segurança;
7. configure `RASAI_CLARITY_API_TOKEN`;
8. habilite explicitamente `RASAI_CLARITY_ENABLED=true` quando desejar consumir a quota.

A documentação oficial exige que o token seja gerenciado por administrador do projeto e enviado como bearer token. O RASAi mantém essa integração desligada por default porque a quota da Data Export API é limitada.

## Dynatrace

### Credencial e contexto

```text
DYNATRACE_API_TOKEN
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
```

### Finalidade

`DYNATRACE_API_TOKEN` é usado somente na importação live de configuração para Synthetic User Experience Apdex quando `RASAI_APDEX_DYNATRACE_IMPORT=true`. O RASAi também suporta `RASAI_DYNATRACE_CONFIG_JSON` para importação offline, preferível quando se deseja máxima reprodutibilidade e nenhum acesso live.

### Como obter

Referência oficial de tokens e autenticação: <https://docs.dynatrace.com/docs/dynatrace-api/basics/dynatrace-api-authentication>.

O Dynatrace usa permissões/scopes granulares. O operador deve criar um token com somente os scopes exigidos pelos endpoints efetivamente consultados pelo ambiente e pela configuração que será importada. Não deve ser concedido um conjunto amplo de permissões apenas por conveniência.

Fluxo básico:

1. identifique o ambiente Dynatrace e o application ID que será consultado;
2. no Dynatrace, abra a administração de access tokens;
3. crie um token com nome descritivo e somente os scopes necessários;
4. copie o valor no momento da criação e armazene-o com segurança;
5. configure `RASAI_DYNATRACE_BASE_URL` com a URL HTTPS do ambiente;
6. configure `RASAI_DYNATRACE_APPLICATION_ID`;
7. configure `DYNATRACE_API_TOKEN` somente no secret boundary;
8. habilite `RASAI_APDEX_DYNATRACE_IMPORT=true` apenas quando desejar importação live.

O token nunca é persistido pelo RASAi.

## OIDC para Web/SaaS

OIDC não possui uma URL universal de criação de credencial porque o Identity Provider é escolhido pela implantação.

Variáveis principais:

```text
RASAI_OIDC_ISSUER
RASAI_OIDC_CLIENT_ID
RASAI_OIDC_AUDIENCE
RASAI_OIDC_REDIRECT_URI
RASAI_OIDC_SESSION_SECRET
RASAI_OIDC_CLIENT_SECRET_ENV
```

A implantação deve registrar um client no Identity Provider escolhido e usar os valores emitidos por esse IdP. `RASAI_OIDC_CLIENT_SECRET_ENV` contém somente o nome da variável de ambiente que guarda o client secret real.

O callback configurado precisa corresponder à implantação do RASAi, normalmente:

```text
https://<host>/auth/callback
```

HTTP é aceito somente para loopback conforme o contrato vigente. O fluxo Web usa Authorization Code + PKCE S256 e `openid` é scope obrigatório.

Consulte [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md) antes de registrar o client no IdP.

## Tokens internos do RASAi

`RASAI_REMOTE_TOKEN_ENV` não aponta para uma credencial de terceiro. Ele contém o nome da variável que guarda o bearer token aceito pelo control plane remoto configurado em `RASAI_REMOTE_BASE_URL`.

A origem, emissão e rotação desse token dependem do modo de autenticação do control plane. Não invente um token manual sem contrato do endpoint remoto correspondente.

## Diagnóstico seguro

Para confirmar configuração sem exibir segredos:

```powershell
rasai providers
rasai providers --configured-only
```

O catálogo retorna apenas estado de configuração e metadados de onboarding. Valores reais de chave/token não devem aparecer em saídas de suporte.

Para variáveis não cobertas pelo catálogo de providers, use o console e os comandos de diagnóstico que exibem somente presença/estado, nunca o valor do secret.

## Referências relacionadas

- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)
- [STANDARDS_METRICS_AND_SERVICES.md](STANDARDS_METRICS_AND_SERVICES.md)
- [EXTERNAL_OBSERVABILITY_INTEGRATIONS.md](EXTERNAL_OBSERVABILITY_INTEGRATIONS.md)
- [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md)
- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md)
