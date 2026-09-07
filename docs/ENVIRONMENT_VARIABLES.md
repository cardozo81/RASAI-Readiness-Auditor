# Variáveis de ambiente — referência completa

Referência operacional da superfície de variáveis reconhecida pelo console do RASAi — Search & AI Readiness Auditor.

Verificação documental: **2026-09-07**. Para credenciais, endpoints externos e conceitos de qualidade de conteúdo, os procedimentos e definições abaixo foram conferidos contra documentação pública oficial dos respectivos provedores e do Google Search Central.

## Como usar esta configuração

Variáveis de ambiente são uma camada de **override avançado**, não uma lista de campos que o usuário precisa preencher antes da primeira auditoria. Quando existe um default seguro, o RASAi já o aplica internamente e o console passa a mostrar esse **default efetivo** mesmo que a variável não exista no sistema operacional.

Não materialize todos os defaults no ambiente sem necessidade. Isso criaria configuração redundante e pode mudar sem querer a semântica de parâmetros opcionais. Exemplo: `SEARCHGEO_CONFIG` não precisa existir; sem override, `searchgeo.toml` é opcional. Se `SEARCHGEO_CONFIG` for definido, o arquivo apontado precisa existir.

O menu `E. Variáveis de ambiente / credenciais` é organizado por fronteira funcional:

```text
1. Aplicação e execução
2. IA — credenciais
3. IA — modelos e reasoning
4. IA — endpoints avançados
5. IA — contexto editorial / YMYL
6. Web Performance / Google APIs
7. Synthetic Apdex
8. Browser / Playwright
A. Todas as variáveis
D. Abrir documentação detalhada
V. Voltar
```

Ao selecionar uma variável, o console mostra: finalidade, tipo, domínio aceito, default efetivo, dependências, sensibilidade, custo/impacto, valor/origem atual, exemplo e referência para obtenção do dado. Valores de enum e booleanos são escolhidos por menu, evitando digitação livre desnecessária.

## Segurança e persistência de credenciais

- API keys, OAuth bearer tokens e demais secrets aparecem apenas como `[SET]`; o valor nunca é exibido em claro.
- Secrets nunca são gravados em `rasai-console.ini`.
- `S. Setar/alterar sessão` altera o valor usado pelo processo atual.
- No Windows, `P. Persistência Windows/User` permite persistir ou remover explicitamente a credencial no ambiente **User**; a gravação exige confirmação `SIM`.
- O console informa a origem do valor efetivamente usado, por exemplo `SESSÃO`, `SO:USER`, `SO:MACHINE` ou combinação equivalente, sem revelar o segredo.
- A sessão atual prevalece durante a execução atual; valores persistidos no Windows são herdados normalmente por novos processos.
- Variável de ambiente não é um cofre de segredos. Em ambientes corporativos, use o secret manager adotado pela organização quando necessário.
- Chave/token configurado não prova saldo, quota, plano compatível, escopo OAuth ou permissão sobre o recurso externo.

## 1. Aplicação e execução

| Variável | Para que serve | Tipo / valores | Default efetivo | Quando definir | Impacto |
|---|---|---|---|---|---|
| `SEARCHGEO_CONFIG` | força um TOML geral, usado principalmente para logging | caminho de arquivo existente | `searchgeo.toml` é opcional quando não há override | somente para apontar um TOML específico | sem custo; override inválido bloqueia a configuração |
| `SEARCHGEO_LOG_LEVEL` | verbosidade do log | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG` | `INFO` | para alterar detalhamento | `DEBUG` aumenta volume de log local |
| `SEARCHGEO_DEVICE_CONTEXT` | dispositivo default | `mobile`, `desktop`, `both` | `mobile` | quando não quiser configurar pela CLI/menu principal | `both` multiplica contextos e pode aumentar tempo/chamadas externas |
| `SEARCHGEO_AI_TIMEOUT_SECONDS` | timeout por tentativa de IA | número finito `>0` em segundos | `180` | override de timeout | não cria chamadas; timeout local não garante ausência de processamento/faturamento externo |
| `SEARCHGEO_AI_CONTENT_REMEDIATION` | default da remediação textual por IA | `true`, `false` | `false` | para habilitar por ambiente | `true` pode gerar chamadas adicionais de IA |

### `SEARCHGEO_CONFIG`

Exemplo:

```powershell
$env:SEARCHGEO_CONFIG = "C:\searchgeo\searchgeo.toml"
```

Defina somente se o arquivo já existir. Para o uso normal do console, deixe a variável ausente e use `rasai-console.ini` para os parâmetros persistíveis.

## 2. IA — credenciais

As credenciais não possuem default.

| Variável | Provider | Obrigatória quando | Observação |
|---|---|---|---|
| `OPENAI_API_KEY` | OpenAI | provider `openai`; em `auto`, torna OpenAI elegível | uso da API é separado do produto ChatGPT |
| `DEEPSEEK_API_KEY` | DeepSeek | provider `deepseek`; em `auto`, torna DeepSeek elegível | erro HTTP 402 pode indicar saldo insuficiente |
| `MIMO_API_KEY` | Xiaomi MiMo | provider `mimo`; em `auto`, torna MiMo elegível | adapter atual aceita PAYG `sk-...`; Token Plan `tp-...` é produto/endpoint diferente |
| `XAI_API_KEY` | xAI / Grok | provider `xai` ou alias `grok` | explicit-only no RASAi atual |
| `DASHSCOPE_API_KEY` | Alibaba Qwen | provider `qwen` | explicit-only; região/endpoint precisam ser compatíveis com a chave |
| `GEMINI_API_KEY` | Google Gemini | provider `gemini` | use auth key atual do Gemini API |
| `ANTHROPIC_API_KEY` | Anthropic Claude | provider `anthropic` ou alias `claude` | Console/API possui billing separado do produto de chat |

### Como obter `OPENAI_API_KEY`

Fontes oficiais: <https://help.openai.com/en/articles/4936850-how-to-create-and-use-an-api-key> e <https://platform.openai.com/api-keys>.

1. Entre na OpenAI Platform.
2. Selecione o projeto que deverá concentrar acesso, limites e billing do RASAi.
3. Abra **API Keys**.
4. Selecione **Create new secret key**.
5. Configure as permissões compatíveis com a chamada ao modelo/endpoint que será usado.
6. Copie o segredo no momento da criação; a chave completa não é mostrada novamente depois.
7. Confirme créditos/billing, limites e acesso ao modelo no mesmo projeto.
8. No RASAi: `E > IA — credenciais > OPENAI_API_KEY > S`. Use `P` apenas se quiser persistir no ambiente User do Windows.

### Como obter `DEEPSEEK_API_KEY`

Fontes oficiais: <https://api-docs.deepseek.com/> e <https://platform.deepseek.com/api_keys>.

1. Entre na DeepSeek Platform.
2. Abra **API Keys**.
3. Crie uma chave e armazene-a com segurança.
4. Confirme saldo/quota antes do primeiro teste.
5. Configure `DEEPSEEK_API_KEY` no grupo **IA — credenciais**.
6. Selecione somente modelos aceitos pelo registry do RASAi; o menu rejeita nomes fora do domínio atual.

### Como obter `MIMO_API_KEY`

Fonte oficial: <https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration>.

1. Entre na Xiaomi MiMo API Open Platform.
2. Para o adapter atual do RASAi, use **Pay-as-you-go API Calls**.
3. Abra **Console > API Keys** e crie a chave PAYG.
4. Confirme que a chave começa com `sk-`.
5. Configure `MIMO_API_KEY`.
6. Não use Token Plan `tp-...` nessa integração. A documentação MiMo declara que PAYG e Token Plan são independentes, possuem formatos/base URLs próprios e não podem ser misturados.

O adapter atual usa `https://api.xiaomimimo.com/v1/responses`.

### Como obter `XAI_API_KEY`

Fonte oficial: <https://docs.x.ai/developers/quickstart>.

1. Crie/acesse sua conta em <https://console.x.ai/>.
2. Carregue créditos na conta/equipe quando necessário.
3. Abra a página **API Keys**.
4. Crie e copie a chave.
5. Configure `XAI_API_KEY` no console.

O endpoint default do adapter é `https://api.x.ai/v1/responses`.

### Como obter `DASHSCOPE_API_KEY` para Qwen

Fonte oficial: <https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen>.

1. Crie/acesse uma conta Alibaba Cloud.
2. Abra **Alibaba Cloud Model Studio** e ative o serviço/aceite os termos quando solicitado.
3. Abra a página **API Key**.
4. Selecione **Create API key**; o modelo não precisa ser escolhido durante a criação da chave.
5. Quando aplicável, restrinja o escopo de modelos conforme a política da conta.
6. Copie a chave e configure `DASHSCOPE_API_KEY`.
7. O adapter atual usa por default o endpoint US `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions`. Chaves/regiões Alibaba não são necessariamente intercambiáveis; use `SEARCHGEO_QWEN_ENDPOINT` somente se houver necessidade regional validada.

### Como obter `GEMINI_API_KEY`

Fonte oficial: <https://ai.google.dev/gemini-api/docs/api-key> e <https://aistudio.google.com/apikey>.

1. Entre no Google AI Studio.
2. Abra a área de projetos e selecione/importe o projeto que deve concentrar o Gemini API.
3. Abra **API Keys**.
4. Clique em **Create API key**.
5. Copie a nova chave e configure `GEMINI_API_KEY`.
6. Confirme quota/billing do projeto conforme o tier usado.

A documentação atual informa que novas chaves criadas no AI Studio são **auth keys** e que Standard keys deixam de ser aceitas em setembro de 2026. Para uma instalação atual, use uma auth key nova/compatível.

### Como obter `ANTHROPIC_API_KEY`

Fontes oficiais: <https://support.claude.com/en/articles/8114521-how-can-i-access-the-claude-api> e <https://console.anthropic.com/>.

1. Crie/acesse uma organização no Anthropic Console.
2. Garanta uma função com permissão para gerenciar API keys conforme a governança da organização.
3. Configure billing/créditos do Console quando necessário.
4. Abra a área de API keys e crie a chave.
5. Copie e configure `ANTHROPIC_API_KEY`.
6. Não assuma que uma assinatura paga do produto Claude de chat inclui créditos de API; o Console/API possui cobrança própria.

## 3. IA — modelos e reasoning

Estas variáveis são overrides. Se ausentes, o RASAi usa os defaults públicos abaixo.

| Variável | Valores aceitos | Default efetivo |
|---|---|---|
| `SEARCHGEO_OPENAI_MODEL` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `gpt-5.6-luna` |
| `SEARCHGEO_OPENAI_REASONING_EFFORT` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` |
| `SEARCHGEO_DEEPSEEK_MODEL` | `deepseek-v4-pro`, `deepseek-v4-flash` | `deepseek-v4-flash` |
| `SEARCHGEO_DEEPSEEK_REASONING_EFFORT` | `NONE`, `LOW`, `HIGH`, `MAX` | `NONE` |
| `SEARCHGEO_MIMO_MODEL` | `mimo-v2.5-pro`, `mimo-v2.5` | `mimo-v2.5` |
| `SEARCHGEO_MIMO_REASONING_EFFORT` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` |
| `SEARCHGEO_XAI_MODEL` | `grok-4.6` | `grok-4.6` |
| `SEARCHGEO_XAI_REASONING_EFFORT` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` |
| `SEARCHGEO_QWEN_MODEL` | `qwen3.8-max`, `qwen3.8-flash` | `qwen3.8-flash` |
| `SEARCHGEO_GEMINI_MODEL` | `gemini-3.8-flash` | `gemini-3.8-flash` |
| `SEARCHGEO_GEMINI_REASONING_EFFORT` | `LOW`, `MEDIUM`, `HIGH` | `LOW` |
| `SEARCHGEO_ANTHROPIC_MODEL` | `claude-sonnet-5` | `claude-sonnet-5` |
| `SEARCHGEO_ANTHROPIC_REASONING_EFFORT` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` |

Qwen não possui `SEARCHGEO_QWEN_REASONING_EFFORT`: o adapter atual mantém `PROVIDER_DEFAULT`. Não crie variável inexistente.

Para uso normal, prefira **4. IA** no menu principal. Use variáveis de modelo/reasoning para AUTO, automação ou override avançado. Esforço maior pode elevar latência, tokens e custo.

## 4. IA — endpoints avançados

No uso normal, deixe estas variáveis ausentes.

| Variável | Default embutido | Tipo | Quando alterar |
|---|---|---|---|
| `SEARCHGEO_XAI_ENDPOINT` | `https://api.x.ai/v1/responses` | URL HTTP(S) absoluta | somente proxy/endpoint xAI comprovadamente compatível |
| `SEARCHGEO_QWEN_ENDPOINT` | `https://dashscope-us.aliyuncs.com/compatible-mode/v1/chat/completions` | URL HTTP(S) absoluta | região/endpoint Qwen compatível |
| `SEARCHGEO_GEMINI_ENDPOINT` | `https://generativelanguage.googleapis.com/v1beta/interactions` | URL HTTP(S) absoluta | endpoint Gemini Interactions compatível |
| `SEARCHGEO_ANTHROPIC_ENDPOINT` | `https://api.anthropic.com/v1/messages` | URL HTTP(S) absoluta | endpoint Messages compatível |

O console valida que o override seja uma URL absoluta `http://` ou `https://`, mas não pode provar que um endpoint arbitrário implementa o contrato esperado. Endpoint incorreto pode causar falha, encaminhar dados a destino indevido ou gerar cobrança em serviço diferente.

## 5. IA — contexto editorial / YMYL

Estas variáveis não ligam uma integração externa por si só. Elas condicionam a análise semântica e as sugestões de conteúdo **quando uma etapa de IA já está habilitada**.

Todos os defaults são `auto`.

| Variável | Valores aceitos | Default | Finalidade / impacto |
|---|---|---|---|
| `SEARCHGEO_CONTENT_RISK_PROFILE` | `auto`, `standard`, `ymyl` | `auto` | define se a IA deve aplicar uma régua editorial comum ou uma exigência YMYL mais alta |
| `SEARCHGEO_YMYL_CATEGORY` | `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare` | `auto` | contextualiza o tipo de risco; não cria score YMYL |
| `SEARCHGEO_PAGE_PURPOSE` | `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other` | `auto` | evita aplicar a mesma expectativa editorial a finalidades distintas |
| `SEARCHGEO_INTENDED_AUDIENCE` | `auto`, `general`, `professional`, `mixed` | `auto` | calibra profundidade e explicação para o público pretendido |
| `SEARCHGEO_EXPERIENCE_REQUIREMENT` | `auto`, `required`, `beneficial`, `not-expected` | `auto` | distingue experiência em primeira mão de expertise técnica/profissional |
| `SEARCHGEO_FRESHNESS_SENSITIVITY` | `auto`, `low`, `medium`, `high` | `auto` | aumenta o rigor sobre datas e qualificadores temporais quando necessário |
| `SEARCHGEO_CONTENT_ORIGIN` | `auto`, `first-party`, `third-party`, `user-generated`, `mixed` | `auto` | diferencia criador/origem do conteúdo e publicador/host para atribuição e responsabilidade |

### Como interpretar `auto`

`auto` não significa que o RASAi conhece o contexto com certeza. Significa que a IA pode usar uma **hipótese provisória**, baseada somente nas evidências visíveis fornecidas.

Quando a classificação inferida for material, a IA deve reduzir confiança e não pode inventar:

- credenciais ou certificações;
- autoria/revisão profissional não observada;
- experiência pessoal;
- reputação externa;
- conformidade legal/regulatória;
- processo editorial oculto;
- fontes ou fatos não presentes nas evidências.

Para site claramente YMYL, prefira configuração explícita.

### Regras de consistência

- `SEARCHGEO_CONTENT_RISK_PROFILE=standard` não pode ser combinado com categoria YMYL explícita diferente de `none`/`auto`;
- `SEARCHGEO_CONTENT_RISK_PROFILE=ymyl` não pode ser combinado com `SEARCHGEO_YMYL_CATEGORY=none`;
- contexto editorial não entra diretamente em `SARI-001` nem na fórmula vigente de `SCORE-GEO-003`;
- E-E-A-T não é transformado em percentual proprietário;
- as variáveis não geram custo externo sozinhas.

### Exemplo financeiro/YMYL

```powershell
$env:SEARCHGEO_CONTENT_RISK_PROFILE = "ymyl"
$env:SEARCHGEO_YMYL_CATEGORY = "financial-security"
$env:SEARCHGEO_PAGE_PURPOSE = "product-service"
$env:SEARCHGEO_INTENDED_AUDIENCE = "general"
$env:SEARCHGEO_EXPERIENCE_REQUIREMENT = "not-expected"
$env:SEARCHGEO_FRESHNESS_SENSITIVITY = "high"
$env:SEARCHGEO_CONTENT_ORIGIN = "first-party"
```

Referência completa e base conceitual: [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md).

Fontes públicas oficiais principais:

- Google Search Central — helpful, reliable, people-first content: <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>
- Google Search Quality Rater Guidelines overview: <https://services.google.com/fh/files/misc/hsw-sqrg.pdf>
- Google — How AI Overviews in Search work: <https://static.googleusercontent.com/media/www.google.com/en//search/howsearchworks/google-about-AI-overviews.pdf>

## 6. Web Performance / Google APIs

| Variável | Finalidade | Tipo / domínio | Default | Dependência / impacto |
|---|---|---|---|---|
| `SEARCHGEO_WEB_PERFORMANCE` | habilita PageSpeed/Lighthouse/CrUX | `true`, `false` | `false` | `true` consome integração/quota externa |
| `SEARCHGEO_WEB_PERFORMANCE_MAX_PAGES` | teto de páginas enviadas | inteiro `>=0`; `0=todas` | `10` | multiplica chamadas potenciais |
| `SEARCHGEO_WEB_PERFORMANCE_TIMEOUT_SECONDS` | timeout por request | número `>0` | `120` | não cria request adicional |
| `SEARCHGEO_WEB_PERFORMANCE_FIELD_SOURCE` | política de field data | `auto`, `pagespeed`, `crux`, `none` | `auto` | `crux` exige `SEARCHGEO_CRUX_API_KEY` |
| `SEARCHGEO_LIGHTHOUSE_CATEGORIES` | categorias Lighthouse | CSV de `performance`, `accessibility`, `best-practices`, `seo` | as quatro | categoria desconhecida/duplicada é rejeitada pelo console |
| `SEARCHGEO_PAGESPEED_API_KEY` | chave PageSpeed | secret | nenhum | opcional em uso ad hoc; recomendada para uso recorrente/gestão de quota |
| `SEARCHGEO_CRUX_API_KEY` | chave CrUX direta | secret | nenhum | obrigatória para chamada direta à CrUX API |
| `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | bearer OAuth para comandos `rasai observe gsc-*` | secret/token temporário | nenhum | exige escopo Search Console compatível e permissão sobre a property; não é API key |

### Como obter as chaves Google para PageSpeed/CrUX

O procedimento completo está em [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md). Em resumo:

1. Abra <https://console.cloud.google.com/> e selecione/crie o projeto.
2. Em **APIs & Services > Library**, habilite **PageSpeed Insights API** e/ou **Chrome UX Report API**.
3. Em **APIs & Services > Credentials**, crie a API key.
4. Restrinja a chave à API necessária e, quando operacionalmente estável, aplique restrição de aplicação adequada.
5. Para a CLI, não use HTTP referrer apenas para “ter uma restrição”.
6. Prefira chaves separadas para PageSpeed e CrUX.
7. Configure `SEARCHGEO_PAGESPEED_API_KEY` e/ou `SEARCHGEO_CRUX_API_KEY` pelo menu.

### `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`

Essa variável é diferente das API keys acima. Os collectors Search Console usam **OAuth 2.0 bearer token** em runtime.

Uso:

```powershell
$env:GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN = "<oauth-access-token>"
rasai observe gsc-sites --audit AUD-...
```

Requisitos:

- token OAuth válido e não expirado;
- escopo `https://www.googleapis.com/auth/webmasters.readonly` ou outro escopo Search Console compatível com a operação;
- usuário/conta do token com acesso à property informada;
- para `gsc-search`, `gsc-appearance`, `gsc-inspect` e `gsc-sitemaps`, informe a property aceita pelo Search Console, como `sc-domain:example.com` quando aplicável.

O RASAi não implementa fluxo de login/refresh OAuth. Ele recebe um access token atual fornecido pelo operador/ambiente. Access tokens expiram e devem ser renovados pelo mecanismo OAuth adotado pela organização.

Segurança:

- não gravar o token em `rasai-console.ini`;
- não colocar o token em arquivo de URL;
- não persistir o token em artifacts, `audit.db`, `observability.db` ou HTML;
- prefira secret manager/variável efêmera em automação.

Referências oficiais: <https://developers.google.com/webmaster-tools/v1/how-tos/authorizing> e <https://developers.google.com/webmaster-tools/v1/searchanalytics/query>.

## 7. Synthetic Apdex

Synthetic Apdex é OFF por default; tuning só é necessário quando habilitado.

| Variável | Finalidade | Tipo / domínio | Default quando ativo | Impacto |
|---|---|---|---|---|
| `SEARCHGEO_SYNTHETIC_APDEX` | habilita medição | booleano | `false` | gera navegações reais contra o alvo |
| `SEARCHGEO_APDEX_THRESHOLD_SECONDS` | threshold T | número `>0` | **sem default** | obrigatório quando Apdex está ON |
| `SEARCHGEO_APDEX_SAMPLES_PER_CONTEXT` | amostras válidas por URL/device | inteiro `>=1` | `100` | maior valor aumenta carga/duração |
| `SEARCHGEO_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | teto de reposição | inteiro `>= samples` | `ceil(1.25 × samples)` | teto direto de navegações |
| `SEARCHGEO_APDEX_MAX_PAGES` | páginas medidas | inteiro `>=0`; `0=todas` | `1` | multiplica contextos |
| `SEARCHGEO_APDEX_TIMEOUT_SECONDS` | timeout por navegação | número `>0` e efetivamente `>4T` | `max(45, 4T+5)` | baixo demais trunca a faixa Frustrated |
| `SEARCHGEO_APDEX_DELAY_SECONDS` | intervalo mínimo entre inícios | número `>=0` | `1` | maior delay reduz pressão e aumenta duração |
| `SEARCHGEO_APDEX_CONCURRENCY` | workers simultâneos | `1`, `2` | `1` | `2` aumenta carga concorrente |

Para configuração normal use **11. Synthetic Apdex** no menu principal, que explica T, calcula defaults derivados e mostra a carga projetada. Use variáveis de ambiente para automação/override.

## 8. Browser / Playwright

### `PLAYWRIGHT_CHROMIUM_EXECUTABLE`

- **Finalidade:** apontar para um Chromium específico.
- **Tipo:** caminho de arquivo existente.
- **Default:** nenhum override; Playwright/RASAi usa a instalação/descoberta padrão.
- **Quando definir:** somente se houver necessidade de fixar um executável externo.
- **Validação:** o console rejeita caminho que não exista como arquivo.
- **Impacto:** execução local; sem custo externo direto.

Exemplo:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE = "C:\Program Files\Chromium\chrome.exe"
```

## Defaults para primeiro uso

Uma instalação nova não precisa preencher as variáveis. O console/INI/runtime já fornece defaults seguros:

```text
device                         = mobile
ai-provider                    = none
ai timeout                     = 180 s
ai content remediation         = false
content risk profile           = auto
ymyl category                  = auto
page purpose                   = auto
intended audience              = auto
experience requirement         = auto
freshness sensitivity          = auto
content origin                 = auto
web performance                = false
web performance max pages      = 10
web performance timeout        = 120 s
field source                   = auto
lighthouse categories          = performance,accessibility,best-practices,seo
synthetic apdex                = false
language                       = pt-BR
market                         = BR
max-pages                      = 100
audits-root                    = audits
```

Modelos e reasoning usam os defaults da tabela de IA. Credenciais, `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` e `SEARCHGEO_APDEX_THRESHOLD_SECONDS` **não recebem valor inventado**.

A configuração mínima para uma auditoria local, sem IA e sem APIs externas, é informar o alvo no item **1. Entrada**.

## Exemplos PowerShell

Sessão atual:

```powershell
$env:OPENAI_API_KEY = "<chave>"
$env:SEARCHGEO_OPENAI_MODEL = "gpt-5.6-luna"
$env:SEARCHGEO_OPENAI_REASONING_EFFORT = "NONE"
```

Remover override e voltar ao default interno:

```powershell
Remove-Item Env:SEARCHGEO_OPENAI_MODEL -ErrorAction SilentlyContinue
```

## Fontes oficiais externas verificadas

- Google Search Central — E-E-A-T/YMYL/people-first: <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>
- Google Search Quality Rater Guidelines overview: <https://services.google.com/fh/files/misc/hsw-sqrg.pdf>
- Google — How AI Overviews in Search work: <https://static.googleusercontent.com/media/www.google.com/en//search/howsearchworks/google-about-AI-overviews.pdf>
- Google Search Console API authorization: <https://developers.google.com/webmaster-tools/v1/how-tos/authorizing>
- Google Search Analytics API: <https://developers.google.com/webmaster-tools/v1/searchanalytics/query>
- OpenAI API keys: <https://help.openai.com/en/articles/4936850-how-to-create-and-use-an-api-key>
- DeepSeek quick start/API key: <https://api-docs.deepseek.com/>
- Xiaomi MiMo API key/PAYG/Token Plan: <https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration>
- xAI quickstart: <https://docs.x.ai/developers/quickstart>
- Alibaba Cloud Model Studio/Qwen: <https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen>
- Gemini API keys: <https://ai.google.dev/gemini-api/docs/api-key>
- Anthropic API access: <https://support.claude.com/en/articles/8114521-how-can-i-access-the-claude-api>
- PageSpeed/CrUX: [GOOGLE_API_KEYS.md](GOOGLE_API_KEYS.md)
