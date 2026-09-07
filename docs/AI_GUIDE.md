# Guia de IA

O RASAi usa IA apenas em finalidades opcionais e evidence-bound. A auditoria principal continua capaz de executar sem IA.

## Finalidades

1. **análise semântica**: avalia somente as evidências fornecidas pelo RASAi e deve devolver saída estruturada compatível com o contrato local;
2. **remediação textual opcional (Sugestões e remediação de conteúdo por IA)**: produz sugestões exatas somente para findings elegíveis e com evidência suficiente;
3. **remediação técnica opcional de crawling/discovery (Rastreamento, descoberta e acesso de crawlers)**: explica diagnósticos técnicos Rastreamento, descoberta e acesso de crawlers já determinados pelo runtime e pode sugerir correção evidence-bound, sem alterar scoring ou política editorial automaticamente.

Nenhuma dessas finalidades autoriza inventar fatos, credenciais, preços, datas, estatísticas, URLs, crawler policies ou evidências.

## Contexto editorial para evitar análise genérica

A mesma evidência textual não deve ser interpretada com a mesma régua em qualquer página. Quando configurado, o RASAi fornece aos providers um contexto editorial explícito:

```text
risk profile: standard | ymyl | auto
YMYL category
page purpose
intended audience
experience requirement
freshness sensitivity
content origin
```

Esses valores vêm das variáveis `SEARCHGEO_CONTENT_*`, `SEARCHGEO_YMYL_CATEGORY`, `SEARCHGEO_PAGE_PURPOSE`, `SEARCHGEO_INTENDED_AUDIENCE`, `SEARCHGEO_EXPERIENCE_REQUIREMENT` e `SEARCHGEO_FRESHNESS_SENSITIVITY`.

Regras:

- valor explícito é contexto fornecido pelo operador;
- `auto` é somente hipótese provisória baseada nas evidências visíveis;
- quando o conteúdo é claramente YMYL, prefira configuração explícita;
- YMYL eleva a exigência de confiança, atribuição, suporte factual e qualificadores onde material;
- Trust é tratado como elemento central de E-E-A-T; Experience, Expertise e Authoritativeness são considerados conforme o propósito/tópico, não exigidos mecanicamente em todo conteúdo;
- a IA não pode inferir como fato credenciais, compliance, revisão profissional, reputação externa, experiência pessoal ou processo editorial oculto;
- contexto editorial não cria um score E-E-A-T/YMYL e não entra diretamente na aritmética do `SARI-001`.

A base conceitual e os valores completos estão em [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md).

Fontes oficiais principais:

- <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>
- <https://services.google.com/fh/files/misc/hsw-sqrg.pdf>
- <https://static.googleusercontent.com/media/www.google.com/en//search/howsearchworks/google-about-AI-overviews.pdf>

## Providers

Providers concretos no registry:

```text
openai
deepseek
mimo
xai
qwen
gemini
anthropic
```

Aliases:

```text
grok   -> xai
claude -> anthropic
```

AUTO permanece:

```text
OpenAI -> DeepSeek -> MiMo
```

xAI, Qwen, Gemini e Anthropic permanecem explicit-only enquanto não houver promoção formal de qualificação.

## Credenciais

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
```

A presença de uma key não garante saldo, quota, plano compatível ou acesso ao modelo.

MiMo PAYG usa credencial `sk-...` no adapter atual. Token Plan `tp-...` pertence a produto/endpoint diferente.

## Defaults públicos

Quando o usuário não informa override, o produto privilegia menor custo/complexidade e o menor esforço suportado pelo adapter/modelo:

| Provider | Modelo default | Esforço default |
|---|---|---|
| OpenAI | `gpt-5.6-luna` | `NONE` |
| DeepSeek | `deepseek-v4-flash` | `NONE` |
| MiMo | `mimo-v2.5` | `NONE` |
| xAI | `grok-4.6` | `LOW` |
| Qwen | `qwen3.8-flash` | `PROVIDER_DEFAULT` |
| Gemini | `gemini-3.8-flash` | `LOW` |
| Anthropic | `claude-sonnet-5` | `LOW` |

Overrides explícitos continuam prevalecendo quando suportados.

### OpenAI

Modelos aceitos pelo adapter atual:

```text
gpt-5.6-sol
gpt-5.6-terra
gpt-5.6-luna
```

Default público: `gpt-5.6-luna` com esforço `NONE`.

### DeepSeek

Modelos:

```text
deepseek-v4-pro
deepseek-v4-flash
```

Default público: `deepseek-v4-flash` com thinking desabilitado (`NONE`) quando não há override.

### MiMo

Modelos:

```text
mimo-v2.5-pro
mimo-v2.5
```

Default público: `mimo-v2.5` com `NONE`.

### xAI

Modelo atual:

```text
grok-4.6
```

O modelo é reasoning-only no contrato atual; o menor esforço configurável usado como default é `LOW`.

### Qwen

Modelos:

```text
qwen3.8-max
qwen3.8-flash
```

Default público: `qwen3.8-flash`. O adapter atual não expõe um parâmetro de reasoning validado, portanto usa `PROVIDER_DEFAULT`.

### Gemini

Modelo atual:

```text
gemini-3.8-flash
```

Default público de thinking: `LOW` na integração atual.

### Anthropic

Modelo atual:

```text
claude-sonnet-5
```

Default público de effort: `LOW`.

## Timeout

```text
SEARCHGEO_AI_TIMEOUT_SECONDS
```

Default público:

```text
180 segundos por tentativa
```

O timeout limita cada chamada ao provider; não representa tempo máximo da auditoria completa.

O console permite alterar o timeout diretamente na opção 4.

## Remediação textual Sugestões e remediação de conteúdo por IA

Superfície:

```text
--ai-content-remediation
--no-ai-content-remediation
SEARCHGEO_AI_CONTENT_REMEDIATION
```

Default: OFF.

Sugestões e remediação de conteúdo por IA atua sobre conteúdo/findings elegíveis depois do scoring e nunca recalcula o score.

## Remediação técnica Rastreamento, descoberta e acesso de crawlers

Superfície:

```text
--ai-technical-remediation
--no-ai-technical-remediation
SEARCHGEO_AI_TECHNICAL_REMEDIATION
```

Default: OFF.

A execução determinística de crawling/discovery Rastreamento, descoberta e acesso de crawlers não depende dessa opção. O flag habilita somente a camada de IA sobre diagnósticos técnicos já persistidos.

A remediação técnica Rastreamento, descoberta e acesso de crawlers deve respeitar estas fronteiras:

- não criar nem alterar `RuleExecution`, Finding, Recommendation GEO, Score, Coverage, Confidence ou Consolidation;
- não inventar URL, canonical, sitemap, data ou crawler token;
- não decidir automaticamente se GPTBot/Google-Extended devem ser permitidos ou bloqueados;
- distinguir OAI-SearchBot de GPTBot;
- tratar Google-Extended como token de produto, não como crawler Search independente;
- tratar `llms.txt` como proposta comunitária experimental e non-scoring;
- exigir revisão humana antes de qualquer alteração em `robots.txt`, sitemap ou conteúdo publicado.

Quando não existe provider compatível/configurado, o estado técnico de IA fica indisponível/`NOT_CONFIGURED`; isso não é finding do website.

Documentação normativa: [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md).

## Console interativo

A opção 4 reúne:

```text
provider
modelo
esforço/profundidade, quando suportado
timeout por tentativa
```

A opção 5, **Remediação textual IA**, só fica disponível com provider apto. Com IA=`none` ou provider indisponível, o console informa que a opção depende da configuração da opção 4.

O grupo **IA — contexto editorial / YMYL** em `E. Variáveis de ambiente / credenciais` expõe os parâmetros contextuais com domínio aceito, default, explicação de impacto e link para a documentação específica.

A remediação técnica Rastreamento, descoberta e acesso de crawlers é uma superfície CLI/ambiente na implementação atual. Não deve ser presumida como opção persistida no INI do console até existir integração explícita correspondente.

## Persistência de configuração e secrets

`rasai-console.ini` pode persistir provider, modelo, esforço, timeout e demais parâmetros não sensíveis previstos pelo INI.

API keys e outros secrets **não são gravados no INI**. O console permite inseri-los pelo menu de variáveis, usa entrada sem eco e mostra apenas `[SET]`.

O contexto editorial avançado é lido das variáveis de ambiente e o valor efetivo usado na auditoria é persistido em `content_analysis_contexts`, permitindo reabrir o report sem depender do estado atual do ambiente.

## AUTO e fallback

AUTO considera somente:

```text
OpenAI -> DeepSeek -> MiMo
```

Cada provider mantém sua própria configuração de modelo/esforço. O primeiro resultado válido encerra a cadeia para aquele contexto. Configurações ausentes ou inválidas são excluídas; erro operacional pode colocar o provider em quarantine para a auditoria.

O termo `AUTO` do roteamento de providers é diferente de campos editoriais `auto`: o primeiro escolhe provider; o segundo permite inferência provisória do contexto editorial.

## Telemetria

Quando disponível, o RASAi persiste por tentativa:

```text
provider
modelo
reasoning profile
status
started_at / finished_at
latência/duração
tokens input/cache/output/reasoning/total
custo estimado
moeda
versão de pricing
diagnóstico sanitizado
```

O custo é estimativa técnica local, não invoice do provider. Quando não existe base de pricing confiável para aquele adapter/modelo, o HTML deve mostrar custo indisponível em vez de fabricar valor.

Para Sugestões e remediação de conteúdo por IA, `content-suggestions.html` mostra um resumo de provider/modelo/reasoning/chamadas/duração/tokens/custo e oferece atalho para o detalhamento em `ai-usage.html`.

Para Rastreamento, descoberta e acesso de crawlers, a finalidade técnica deve permanecer identificável em `crawling-discovery.html`/`ai-usage.html` e não ser misturada com o score de qualidade do website.

## Segurança

- nunca copie uma key real para documentação, issue, report ou log;
- não persista secrets no INI;
- não reutilize credencial de um provider em outro endpoint;
- não assuma que key configurada significa crédito disponível;
- falha de provider não deve ser convertida em finding do website;
- sugestão textual/técnica exige revisão humana antes de publicação;
- IA Rastreamento, descoberta e acesso de crawlers não pode escolher unilateralmente política de treinamento/crawler da organização;
- contexto YMYL não autoriza inferir responsabilidade legal/regulatória.

## Documentos relacionados

- [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [AI_PROVIDER_EXTENSIONS.md](AI_PROVIDER_EXTENSIONS.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [OPENAI_PROVIDER_DIAGNOSTICS.md](OPENAI_PROVIDER_DIAGNOSTICS.md)
- [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md)
