# Guia de IA

O RASAi usa IA apenas em finalidades opcionais e evidence-bound. A auditoria principal continua capaz de executar sem IA.

## Finalidades

1. **análise semântica**: avalia somente as evidências fornecidas pelo RASAi e deve devolver saída estruturada compatível com o contrato local;
2. **remediação textual opcional (Sugestões e remediação de conteúdo por IA)**: produz sugestões exatas somente para findings elegíveis e com evidência suficiente;
3. **remediação técnica opcional de crawling/discovery (Rastreamento, descoberta e acesso de crawlers)**: explica diagnósticos técnicos já determinados pelo runtime e pode sugerir correção evidence-bound, sem alterar scoring ou política editorial automaticamente.

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

Esses valores vêm das variáveis `RASAI_CONTENT_*`, `RASAI_YMYL_CATEGORY`, `RASAI_PAGE_PURPOSE`, `RASAI_INTENDED_AUDIENCE`, `RASAI_EXPERIENCE_REQUIREMENT` e `RASAI_FRESHNESS_SENSITIVITY`.

Regras:

- valor explícito é contexto fornecido pelo operador e permanece como configuração oficial;
- quando um campo está em `auto` e IA está ligada, o provider pode produzir uma **interpretação transitória** baseada somente nas evidências/conteúdo enviados;
- essa interpretação é mostrada separadamente em `readiness.html`, sem substituir o valor `AUTO`;
- a interpretação transitória não sobrescreve `content_analysis_contexts`, não vira evidência determinística e não altera diretamente `SARI-001`/`SCORE-GEO-004`;
- quando a evidência não sustenta uma classificação, o relatório deve mostrar `Não determinável`;
- quando o conteúdo é claramente YMYL e a organização já conhece sua classificação, configuração explícita continua preferível;
- YMYL eleva a exigência de confiança, atribuição, suporte factual e qualificadores onde material;
- Trust é tratado como elemento central de E-E-A-T; Experience, Expertise e Authoritativeness são considerados conforme o propósito/tópico, não exigidos mecanicamente em todo conteúdo;
- a IA não pode inferir como fato credenciais, compliance, revisão profissional, reputação externa, experiência pessoal ou processo editorial oculto;
- contexto editorial não cria um score E-E-A-T/YMYL e não entra diretamente na aritmética do `SARI-001`.

A base conceitual e os valores completos estão em [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md) e o comportamento transitório está em [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md).

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
copilot
```

Aliases:

```text
grok           -> xai
claude         -> anthropic
github-copilot -> copilot
```

Em `AI=auto`, participam apenas os providers registrados como `auto_eligible`, com credencial e configuração válidas. O registry é a fonte de verdade; não existe uma cadeia fixa limitada aos providers históricos.

`copilot` é deliberadamente **explicit-only**: mesmo com credencial válida, não entra em `AI=auto`. Isso impede que a presença de um token de usuário faça o RASAi consumir silenciosamente créditos/franquia da assinatura GitHub Copilot. O usuário precisa selecionar Copilot de forma explícita.

## Credenciais

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
MIMO_API_KEY
XAI_API_KEY
DASHSCOPE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
COPILOT_GITHUB_TOKEN
```

A presença de uma key/token não garante saldo, quota, plano compatível ou acesso ao modelo.

MiMo PAYG usa credencial `sk-...` no adapter atual. Token Plan `tp-...` pertence a produto/endpoint diferente.

GitHub Copilot usa um token de usuário compatível com o Copilot SDK. Para operação local do RASAi, o recomendado é fine-grained PAT com a permissão de conta `Copilot Requests`; classic PAT `ghp_` não é suportado nesse fluxo. A integração desativa fallback para credenciais locais do Copilot CLI/GitHub CLI.

As URLs oficiais para criar/gerenciar as credenciais de todos os providers estão em [PROVIDER_SETUP.md](PROVIDER_SETUP.md) e também são expostas pelo console de variáveis.

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
| GitHub Copilot | `auto` | `PROVIDER_DEFAULT` |

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

### GitHub Copilot

O adapter usa o SDK oficial `github-copilot-sdk` e o modelo público `auto`:

```text
RASAI_COPILOT_MODEL=auto
COPILOT_GITHUB_TOKEN=<token de usuário>
```

O pacote é opcional:

```powershell
python -m pip install -e ".[copilot]"
```

A autenticação é explicitamente vinculada ao token configurado e `use_logged_in_user=false`; isso evita fallback silencioso para uma sessão Copilot/GitHub existente na máquina. O SDK é usado sem tools disponíveis e com a política deny-by-default de permissões, pois o RASAi precisa apenas de inferência evidence-bound, não de capacidades agentic de edição/shell/browser.

Copilot permanece fora de `AI=auto`; selecione `copilot` ou `github-copilot` explicitamente.

## Timeout

```text
RASAI_AI_TIMEOUT_SECONDS
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
RASAI_AI_CONTENT_REMEDIATION
```

Default: OFF.

Sugestões e remediação de conteúdo por IA atua sobre conteúdo/findings elegíveis depois do scoring e nunca recalcula o score.

## Remediação técnica Rastreamento, descoberta e acesso de crawlers

Superfície:

```text
--ai-technical-remediation
--no-ai-technical-remediation
RASAI_AI_TECHNICAL_REMEDIATION
```

Default: OFF.

A execução determinística de crawling/discovery não depende dessa opção. O flag habilita somente a camada de IA sobre diagnósticos técnicos já persistidos.

A remediação técnica deve respeitar estas fronteiras:

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

A opção 5, **Remediação textual IA**, só fica disponível com provider apto. Com IA=`none` ou nenhum provider AUTO elegível, o console informa a indisponibilidade sem transformar isso em finding do site.

O grupo **IA - contexto editorial / YMYL** em `E. Variáveis de ambiente / credenciais` expõe os parâmetros contextuais com domínio aceito, default, explicação de impacto e link para a documentação específica. As credenciais de IA exibem também a URL oficial de cadastro/login onde o usuário cria ou gerencia a key/token.

A remediação técnica é uma superfície CLI/ambiente na implementação atual. Não deve ser presumida como opção persistida no INI do console até existir integração explícita correspondente.

## Persistência de configuração e secrets

`rasai-console.ini` pode persistir provider, modelo, esforço, timeout e demais parâmetros não sensíveis previstos pelo INI.

API keys e outros secrets **não são gravados no INI**. O console permite inseri-los pelo menu de variáveis, usa entrada sem eco e mostra apenas `[SET]`.

O contexto editorial configurado é persistido em `content_analysis_contexts` para que o relatório conheça a configuração efetiva usada na auditoria. Quando o valor configurado é `auto`, continua persistido como `AUTO`; a interpretação produzida pela IA não sobrescreve esse valor nem cria uma classificação canônica paralela no banco.

## AUTO, rotação e fallback

AUTO constrói dinamicamente o pool de providers registrados como elegíveis e configurados corretamente na execução. Providers marcados como explicit-only, como GitHub Copilot, não entram nesse pool.

A seleção usa round-robin compartilhado entre necessidades de IA. Em uma mesma necessidade, cada provider pode ser tentado no máximo uma vez. Se um provider falhar temporariamente, o fallback segue para o próximo; esse provider pode voltar ao pool em uma necessidade futura enquanto não atingir o circuit breaker.

Condições terminais como autenticação, crédito, quota terminal, permissão, modelo inválido/inexistente e HTTP 401/403/404/410 retiram o provider do restante da execução. Falhas temporárias abrem o circuit breaker quando três falhas aparecem entre as últimas cinco observações daquele provider.

A exclusão é somente da auditoria atual e não altera a configuração global.

O termo `AUTO` do roteamento de providers é diferente de campos editoriais `auto`: o primeiro escolhe dinamicamente um provider; o segundo mantém a configuração editorial indefinida e permite apenas uma interpretação transitória para apresentação.

Contrato detalhado: [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md).

## Structured output e validação local

O schema local do RASAi permanece normativo. Quando o wire format do provider aceita apenas um subconjunto do JSON Schema, o runtime projeta o schema imediatamente antes do transporte e mantém as validações locais mais estritas depois da resposta.

Na integração OpenAI isso evita enviar constraints incompatíveis em contratos estruturados de análise/remediação sem relaxar os invariantes que o RASAi valida localmente. Na integração Copilot, o contrato provider-neutral completo, incluindo o schema esperado e as evidências permitidas, é encapsulado no prompt do SDK e continua sendo validado localmente depois da resposta.

Erro de schema/request é erro técnico de integração, não defeito do website auditado.

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

Além da telemetria agregada, `ai_exchange_log` registra os envelopes externos sanitizados de request e response, com finalidade, página/snapshot, endpoint sanitizado, duração, resultado, hashes e truncamento. A projeção principal desse log está em `ai-usage.html`.

Headers de autenticação, API keys, tokens, passwords/client secrets e campos reconhecidos como raciocínio privado não são persistidos. O log pode conter conteúdo/evidência da página enviados ao provider e deve receber a mesma proteção de acesso/retenção do workspace da auditoria.

Uma resposta recebida e posteriormente rejeitada pelo contrato local continua sendo uma chamada externa e pode ter consumo/custo. O relatório deve distingui-la de falha de transporte e de resposta aceita.

O custo é estimativa técnica local, não invoice do provider. Quando não existe base de pricing confiável para aquele adapter/modelo, o HTML deve mostrar custo indisponível em vez de fabricar valor.

Para Sugestões e remediação de conteúdo por IA, `content-suggestions.html` mostra um resumo e oferece atalho para o detalhamento em `ai-usage.html`.

Para Rastreamento, descoberta e acesso de crawlers, a finalidade técnica deve permanecer identificável em `crawling-discovery.html`/`ai-usage.html` e não ser misturada com o score de qualidade do website.

## Segurança

- nunca copie uma key real para documentação, issue, report ou log;
- não persista secrets no INI;
- não reutilize credencial de um provider em outro endpoint;
- não assuma que key configurada significa crédito disponível;
- falha de provider não deve ser convertida em finding do website;
- `evidence_ids` retornados por provider são limitados ao conjunto exato fornecido naquele contexto; referência a ID externo ao input invalida a resposta, não a evidência local;
- provider configurado/chamado com resposta indisponível ou rejeitada por contrato deve aparecer como execução degradada, e não como `NO_AI`;
- sugestão textual/técnica exige revisão humana antes de publicação;
- IA de crawling/discovery não pode escolher unilateralmente política de treinamento/crawler da organização;
- contexto YMYL não autoriza inferir responsabilidade legal/regulatória.

Detalhamento de retenção/sanitização: [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md).

## Documentos relacionados

- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [AI_RUNTIME_SECURITY.md](AI_RUNTIME_SECURITY.md)
- [REPORTING_AI_USAGE.md](REPORTING_AI_USAGE.md)
- [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md)
- [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [AI_PROVIDER_EXTENSIONS.md](AI_PROVIDER_EXTENSIONS.md)
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)
- [OPENAI_PROVIDER_DIAGNOSTICS.md](OPENAI_PROVIDER_DIAGNOSTICS.md)
- [specification/18_AI_RUNTIME_ORCHESTRATION.md](specification/18_AI_RUNTIME_ORCHESTRATION.md)
- [specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md](specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md)

<!-- rasai-ai-purpose-separation-20260908 -->
## Separação das remediações por IA

As finalidades são independentes:

- `RASAI_AI_CONTENT_REMEDIATION`: sugestões textuais evidence-bound para findings de conteúdo elegíveis;
- `RASAI_AI_TECHNICAL_REMEDIATION`: explicação/remediação advisory de crawling, discovery, `robots.txt`, sitemap e controles de crawlers.

Execução degradada ou `CONTRACT_ERROR` significa que a finalidade foi habilitada e houve tentativa de provider, mas a resposta não foi aceita pelo contrato; isso não deve ser apresentado como "IA desabilitada". A remediação de conteúdo restringe `finding_id` e `evidence_ids` ao universo enviado e persiste reason codes seguros para falhas contratuais.

A IA técnica de crawling/discovery não possui autoridade para elevar Confidence ou SARI por julgamento. Ela permanece advisory; somente evidência válida incorporada por uma regra de scoring pode alterar Coverage/Confidence.