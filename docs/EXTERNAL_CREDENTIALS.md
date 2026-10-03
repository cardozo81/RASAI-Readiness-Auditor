# Credenciais e integrações externas

**Estado:** vigente.

## Objetivo

Este documento é a referência operacional para credenciais, tokens e API keys usados pelo RASAi. Ele descreve para que cada credencial serve, qual funcionalidade a consome, quais dependências precisam existir, onde criar ou gerenciar a credencial e quais limites de segurança devem ser observados.

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

Para execução externa/agendada, `M. Ver linha de comando` materializa nomes de secrets apenas como linhas comentadas com `**********`. Manter ou remover a linha comentada faz a execução usar a credencial disponível no ambiente do processo/SO. Ativar a linha e substituir o placeholder cria um override somente para aquele processo e seus filhos; não altera a credencial persistida no sistema operacional. O clipboard padrão não inclui placeholders. Consulte [EXECUTION_SCHEDULING.md](EXECUTION_SCHEDULING.md).

## Providers de IA

As credenciais desta seção são usadas apenas quando o provider correspondente é selecionado ou quando participa de uma política `AUTO` para a qual seja elegível. A API de cada provider é independente de assinaturas de produtos de chat, salvo quando explicitamente indicado.

### Escopo desta referência

Esta seção documenta **somente o contrato consumido pelo RASAi hoje**. Ela não é um catálogo das capacidades comerciais ou técnicas completas de cada fornecedor.

Uma modalidade externa só pode aparecer como opção operacional quando houver, no RASAi, adapter/contrato verificável, configuração correspondente e teste que a sustente. Formatos de credencial, planos, endpoints, tiers, métodos de autenticação, tools, search, agents ou connectors que existam no fornecedor mas não estejam implementados/homologados no RASAi **não devem ser interpretados como suportados**.

Quando for necessário citar uma modalidade externa apenas para impedir configuração incorreta, a documentação deve marcá-la expressamente como **não suportada/não homologada**. A avaliação dessas extensões está centralizada na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180), sem autorização automática de implementação.

### Visão rápida

| Provider | Variável | Uso no RASAi | Onde criar ou gerenciar | Observação essencial |
|---|---|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `openai` | <https://platform.openai.com/api-keys> | API Platform e ChatGPT têm faturamentos separados. |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek` | <https://platform.deepseek.com/api_keys> | autenticação Bearer; saldo/quota pertencem à plataforma DeepSeek. |
| Xiaomi MiMo | `MIMO_API_KEY` | `mimo` | <https://mimo.mi.com/> | o contrato atual do RASAi aceita somente PAYG `sk-...`; Token Plan `tp-...`/`ttp-...` é uma modalidade válida do fornecedor, mas exige credencial/Base URL próprias e não é suportada pelo adapter atual. |
| xAI / Grok | `XAI_API_KEY` | `xai` ou `grok` | <https://console.x.ai/> | usar a API key consumida pelo adapter de inferência; operações administrativas xAI estão fora do escopo atual. |
| Alibaba Qwen / Model Studio | `DASHSCOPE_API_KEY` | `qwen` | <https://www.alibabacloud.com/help/en/model-studio/get-api-key> | key, endpoint e modelo devem ser coerentes com a região; planos/credenciais alternativos não estão homologados. |
| Google Gemini | `GEMINI_API_KEY` | `gemini` | <https://aistudio.google.com/apikey> | o adapter atual usa API key em `x-goog-api-key`; métodos alternativos de autenticação não fazem parte do contrato atual. |
| Anthropic Claude | `ANTHROPIC_API_KEY` | `anthropic` ou `claude` | <https://console.anthropic.com/> | o adapter atual usa API key do Console/Workspace em `x-api-key`; outros métodos de autenticação não fazem parte do contrato atual. |
| Mistral AI | `MISTRAL_API_KEY` | `mistral` | <https://console.mistral.ai/api-keys/> | explicit-only; endpoint global e Standard tier fixos; sem endpoint alternativo, tools/search/agents/connectors. |
| Cohere | `COHERE_API_KEY` | `cohere` | <https://dashboard.cohere.com/api-keys> | explicit-only; Chat V2 generativo com `command-a-03-2025`; sem tools, documents, RAG ou Rerank no contrato atual. |
| GitHub Copilot | `COPILOT_GITHUB_TOKEN` | `copilot` ou `github-copilot` | <https://github.com/settings/personal-access-tokens/new> | fine-grained PAT de conta pessoal com `Copilot Requests`; explicit-only. |

### Procedimento padrão depois de criar qualquer credencial

Use este fluxo para todos os providers. As subseções seguintes informam os passos específicos de criação.

1. Crie a credencial somente no console oficial do fornecedor.
2. Copie o segredo no momento em que o fornecedor o exibir. Alguns consoles não mostram novamente o valor completo.
3. Armazene-o em secret store ou variável de ambiente. Não grave o valor em `rasai-console.ini`, `rasai.toml`, issue, commit, relatório ou script versionado.
4. Configure a variável exigida pelo provider na sessão do PowerShell.
5. Valide apenas a **presença** da variável com `Test-Path`; não imprima seu conteúdo.
6. Consulte `rasai providers --provider <id>` para confirmar que o RASAi reconhece a configuração sem expor o segredo.
7. Execute o diagnóstico seguro do console antes de uma auditoria real: `INÍCIO > 5. Integrações e serviços > T. Validar integrações e IAs configuradas`.
8. Faça um smoke funcional mínimo somente quando aceitar eventual consumo de quota/custo do provider.
9. Se houver suspeita de exposição, revogue/rotacione a credencial no fornecedor e atualize o secret boundary antes de nova execução.

Exemplo genérico de presença segura:

```powershell
Test-Path Env:NOME_DA_VARIAVEL
```

Retorno `True` comprova somente que a variável existe na sessão. Não comprova que a chave é válida, que há saldo/quota, que o modelo está liberado ou que o endpoint está acessível.

Nunca faça:

```powershell
# NÃO FAZER: imprime o segredo no terminal/histórico/captura de tela.
Write-Host $env:OPENAI_API_KEY
```

O diagnóstico seguro é consultivo e não altera scoring, `AI=auto`, SARI, SCORE-GEO, Apdex, retry funcional, evidência do website ou consolidação. Consulte [INTEGRATION_DIAGNOSTICS.md](INTEGRATION_DIAGNOSTICS.md).

### OpenAI

**Variável usada pelo RASAi:** `OPENAI_API_KEY`  
**Seleção:** `openai`  
**Página de chaves:** <https://platform.openai.com/api-keys>  
**Quickstart oficial:** <https://platform.openai.com/docs/quickstart/make-your-first-api-request>  
**Ajuda sobre chaves:** <https://help.openai.com/articles/4936850-where-do-i-find-my-openai-api-key>

#### Pré-requisitos

- conta com acesso à OpenAI API Platform;
- projeto/organização da API em que a chave será criada;
- billing/créditos da API quando o uso pretendido exigir. Uma assinatura ChatGPT não fornece automaticamente créditos da API; os sistemas de faturamento são separados.

#### Criar a chave

1. Entre na OpenAI API Platform com a conta que deve possuir a credencial.
2. Abra <https://platform.openai.com/api-keys>.
3. Confirme que está no projeto/organização de API correto antes de criar a credencial.
4. Escolha a opção de criar uma nova secret key.
5. Dê um nome que identifique finalidade e ambiente, por exemplo `rasai-local-dev` ou `rasai-prod`.
6. Se o console oferecer controles de projeto/permissão, aplique o menor escopo compatível com as chamadas de inferência necessárias.
7. Crie a chave e copie o valor imediatamente para um secret store. A chave completa não deve ser tratada como informação recuperável posteriormente.
8. Confirme na área de billing da API que a organização/projeto tem a forma de cobrança, créditos ou limites adequados ao uso pretendido.

#### Configurar no PowerShell

```powershell
$env:OPENAI_API_KEY="<openai-api-key>"
Test-Path Env:OPENAI_API_KEY
rasai providers --provider openai
```

Para persistência suportada pelo RASAi no Windows, use a superfície própria de secrets descrita em [WINDOWS_SECRET_PERSISTENCE.md](WINDOWS_SECRET_PERSISTENCE.md); não coloque a chave no INI.

#### Validar

Primeiro execute o diagnóstico seguro pelo console. Para smoke funcional real, somente se houver autorização para consumo de API:

```powershell
rasai audit https://example.com --ai-provider openai
```

#### Falhas típicas

- `401`: chave inválida, revogada, associada ao contexto incorreto ou não disponível para o processo;
- erro de quota/billing: presença da chave não implica créditos ou autorização de consumo;
- `429`: rate limit/quota do fornecedor;
- assinatura ChatGPT existente sem billing de API: esperado, pois ChatGPT e API Platform são produtos cobrados separadamente.

### DeepSeek

**Variável usada pelo RASAi:** `DEEPSEEK_API_KEY`  
**Seleção:** `deepseek`  
**Página de chaves:** <https://platform.deepseek.com/api_keys>  
**Documentação da API:** <https://api-docs.deepseek.com/api/deepseek-api/>  
**Erros oficiais:** <https://api-docs.deepseek.com/quick_start/error_codes/>

#### Pré-requisitos

- conta na DeepSeek Platform;
- API key criada na plataforma;
- saldo suficiente quando o modelo/uso não estiver coberto por crédito disponível.

#### Criar a chave

1. Entre em <https://platform.deepseek.com/>.
2. Abra a área de API Keys: <https://platform.deepseek.com/api_keys>.
3. Crie uma nova API key para a finalidade do RASAi.
4. Use um nome que permita identificar ambiente/finalidade quando o console oferecer esse campo.
5. Copie a chave e armazene-a fora do repositório.
6. Verifique saldo/quota da conta antes do smoke. A documentação oficial diferencia erro `401` de autenticação, `402` de saldo insuficiente e `429` de limite de requisições.

#### Configurar no PowerShell

```powershell
$env:DEEPSEEK_API_KEY="<deepseek-api-key>"
Test-Path Env:DEEPSEEK_API_KEY
rasai providers --provider deepseek
```

#### Validar

```powershell
rasai audit https://example.com --ai-provider deepseek
```

Use primeiro o diagnóstico seguro do console. O smoke acima pode consumir saldo.

#### Falhas típicas

- `401 Authentication Fails`: conferir/recriar a API key;
- `402 Insufficient Balance`: adicionar saldo ou corrigir a conta usada;
- `429 Rate Limit Reached`: reduzir cadência e respeitar a política de concorrência;
- `5xx`: indisponibilidade do serviço, não evidência de problema no website auditado.

### Xiaomi MiMo

**Variável usada pelo RASAi:** `MIMO_API_KEY`  
**Seleção:** `mimo`  
**Portal:** <https://mimo.mi.com/>  
**Documentação oficial de API Key:** <https://mimo.mi.com/docs/en-US/quick-start/faq/api-integration>

#### Credencial aceita pelo contrato atual

O RASAi aceita, neste adapter, a credencial Pay-as-you-go `sk-...` em `MIMO_API_KEY`.

Credenciais Token Plan `tp-...`/`ttp-...` são modalidades válidas do Xiaomi MiMo, mas usam contrato comercial e Base URL próprios. Elas **não são uma configuração suportada pelo RASAi hoje**. Não tente compensar isso alterando manualmente endpoint ou variável do adapter PAYG. A eventual adoção dessa modalidade deve ser decidida e qualificada separadamente na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

#### Modelos vigentes no contrato RASAi

A credencial PAYG não muda com a migração de modelo. O RASAi usa o mesmo endpoint Responses e a mesma `MIMO_API_KEY`:

- default público: `mimo-v2.6-flash`;
- default do adapter: `mimo-v2.6-pro`;
- `mimo-v2.5` e `mimo-v2.5-pro`: somente para compatibilidade até **21/10/2026 02:00 UTC**;
- reasoning default: `NONE`.

A retirada da família v2.5 e a migração para v2.6 estão rastreadas na [issue #183](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/183). Esta mudança não habilita Token Plan, Batch, UltraSpeed, web search, tools ou multimodal.

#### Criar a chave Pay-as-you-go

1. Entre no Xiaomi MiMo API Open Platform em <https://mimo.mi.com/>.
2. Abra `Console` > `API Keys`.
3. Solicite/crie a API Key Pay-as-you-go usada pelo contrato atual do RASAi.
4. Confirme que a credencial resultante usa o formato esperado `sk-...`.
5. Copie a chave quando for criada e armazene-a em secret store.
6. Confira saldo, créditos ou limites da conta antes do smoke.

#### Configurar no PowerShell

```powershell
$env:MIMO_API_KEY="<mimo-payg-sk-key>"
Test-Path Env:MIMO_API_KEY
rasai providers --provider mimo
```

#### Validar

```powershell
rasai audit https://example.com --ai-provider mimo
```

#### Falhas típicas

- `tp-...`/`ttp-...`: credenciais Token Plan válidas no fornecedor, porém fora do contrato atual do adapter RASAi; não misturar com o endpoint PAYG; evolução registrada na issue #180;
- chave incompatível com o endpoint efetivo: autenticação pode falhar mesmo com valor sintaticamente válido;
- saldo insuficiente ou limite comercial: tratar como condição do provider, não finding do alvo auditado.

### xAI / Grok

**Variável usada pelo RASAi:** `XAI_API_KEY`  
**Seleção:** `xai` ou alias `grok`  
**Console:** <https://console.x.ai/>  
**Quickstart oficial:** <https://docs.x.ai/developers/quickstart>  
**Referência de autenticação:** <https://docs.x.ai/developers/rest-api-reference/inference>

#### Pré-requisitos

- conta no xAI Console;
- créditos/billing suficientes para o uso pretendido;
- API key válida para o endpoint de inferência consumido pelo adapter RASAi. Operações administrativas da conta xAI não fazem parte do produto atual.

#### Criar a chave

1. Entre em <https://console.x.ai/>.
2. Confirme a equipe/conta correta.
3. Configure créditos ou billing conforme necessário para a API.
4. Abra a página `API Keys` do console.
5. Crie a API key destinada ao uso da API de inferência.
6. Copie-a e armazene-a como segredo.
7. Não configure em `XAI_API_KEY` uma credencial destinada exclusivamente a APIs administrativas. Esse tipo de integração está fora do contrato atual e só pode ser avaliado futuramente pela issue #180.

#### Configurar no PowerShell

```powershell
$env:XAI_API_KEY="<xai-api-key>"
Test-Path Env:XAI_API_KEY
rasai providers --provider xai
```

#### Validar

```powershell
rasai audit https://example.com --ai-provider xai
```

Também é possível selecionar o alias `grok`; o provider canônico permanece xAI.

#### Falhas típicas

- credencial não compatível com o endpoint de inferência do adapter;
- conta/equipe sem créditos suficientes;
- `401` por chave inválida/revogada;
- `429` por limites de uso.

### Alibaba Qwen / Model Studio

**Variável usada pelo RASAi:** `DASHSCOPE_API_KEY`  
**Seleção:** `qwen`  
**Como obter a API key:** <https://www.alibabacloud.com/help/en/model-studio/get-api-key>  
**Regiões e endpoints:** <https://www.alibabacloud.com/help/en/model-studio/regions>  
**Base URLs:** <https://www.alibabacloud.com/help/en/model-studio/base-url>

#### Regra obrigatória: região coerente

O Model Studio trata região como parte do contrato. API key, endpoint e lista de modelos são regionais e não devem ser combinados entre regiões. Antes de criar a credencial, determine a região que será usada pelo RASAi.

#### Criar a chave

1. Entre na Alibaba Cloud com uma conta ou RAM user que tenha permissão para a página de API Keys.
2. Abra a documentação/atalho de criação em <https://www.alibabacloud.com/help/en/model-studio/get-api-key>.
3. Na página de API Keys do Model Studio, selecione a **região** no canto superior direito.
4. Crie a API key nessa região.
5. Copie a chave e registre, fora do segredo, qual região ela utiliza.
6. Confirme que o modelo pretendido existe na mesma região.
7. Confirme que o endpoint efetivo do RASAi pertence à mesma região.

O contrato atual do RASAi não declara suporte genérico a modalidades de credencial específicas de planos comerciais. Use uma API key compatível com a região, endpoint e modelo efetivamente configurados. Modalidades adicionais de plano/credencial são objeto da [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

#### Configurar no PowerShell

```powershell
$env:DASHSCOPE_API_KEY="<qwen-api-key>"
Test-Path Env:DASHSCOPE_API_KEY
rasai providers --provider qwen
```

Se houver override de `RASAI_QWEN_ENDPOINT`, revise-o junto com a região da chave e do modelo antes do smoke.

#### Validar

```powershell
rasai audit https://example.com --ai-provider qwen
```

#### Falhas típicas

- API key de uma região usada contra endpoint de outra região;
- modelo não disponível na região escolhida;
- credencial incompatível com a região/endpoint configurados;
- `401` decorrente de key/endpoint incompatíveis.

### Google Gemini

**Variável usada pelo RASAi:** `GEMINI_API_KEY`  
**Seleção:** `gemini`  
**Gerenciar chaves:** <https://aistudio.google.com/apikey>  
**Documentação oficial:** <https://ai.google.dev/gemini-api/docs/api-key>

#### Método de autenticação do adapter atual

O adapter RASAi envia `GEMINI_API_KEY` no header `x-goog-api-key`. O onboarding recomendado é criar a chave no Google AI Studio e usar somente esse método para este provider.

OAuth, service account e outros métodos que possam existir no ecossistema Google **não são métodos alternativos implementados por este adapter**; eventual necessidade deve ser analisada separadamente na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

#### Criar a Auth key

1. Entre no Google AI Studio: <https://aistudio.google.com/apikey>.
2. Selecione o projeto Google Cloud que deve suportar o consumo ou importe/crie o projeto quando necessário.
3. Clique para criar uma nova API key.
4. Confirme que a chave criada é válida para a Gemini API e para o projeto escolhido.
5. Copie a chave e armazene-a como segredo.
6. Confirme billing/quota e acesso ao modelo efetivo conforme o projeto.
7. Não compartilhe a chave com outras APIs/serviços apenas por conveniência; mantenha credenciais segregadas quando possível.

#### Configurar no PowerShell

```powershell
$env:GEMINI_API_KEY="<gemini-auth-key>"
Test-Path Env:GEMINI_API_KEY
rasai providers --provider gemini
```

#### Validar

```powershell
rasai audit https://example.com --ai-provider gemini
```

#### Falhas típicas

- chave não válida para o endpoint Gemini usado pelo adapter;
- projeto correto não importado/selecionado no AI Studio;
- chave válida, mas projeto sem quota/billing ou sem acesso ao modelo;
- chave bloqueada/revogada pelo Google.

### Anthropic Claude

**Variável usada pelo RASAi:** `ANTHROPIC_API_KEY`  
**Seleção:** `anthropic` ou alias `claude`  
**Console:** <https://console.anthropic.com/>  
**Acesso à API:** <https://support.anthropic.com/en/articles/8114521-how-can-i-access-the-anthropic-api>  
**Workspaces/API keys:** <https://support.anthropic.com/en/articles/9796807-creating-and-managing-workspaces>  
**Segurança de API keys:** <https://support.anthropic.com/en/articles/9767949-api-key-best-practices-keeping-your-keys-safe-and-secure>

O adapter RASAi autentica esta integração exclusivamente com `ANTHROPIC_API_KEY` enviado em `x-api-key`. Workspaces são relevantes porque determinam onde a chave é criada/gerenciada no Console; isso não implica suporte a métodos alternativos de autenticação. Outros métodos permanecem fora do contrato atual e são rastreados na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

#### Pré-requisitos

- conta no Anthropic API Console;
- acesso à organização/workspace apropriado;
- função com permissão para gerenciar API keys. A documentação do Console indica que papel `Developer` pode gerenciar keys; administradores também possuem capacidades ampliadas;
- créditos/billing da API Console. Planos pagos do Claude.ai não incluem uso da API Console.

#### Criar a chave

1. Entre no Anthropic Console: <https://console.anthropic.com/>.
2. Confirme a organização correta.
3. Se a organização utilizar Workspaces, abra `Settings` > `Workspaces` e selecione o Workspace que deverá possuir a credencial.
4. Confirme que seu papel permite gerenciar API keys.
5. No Workspace, abra a aba `API Keys`.
6. Clique em `Create Key`.
7. Dê um nome descritivo à credencial.
8. Crie e copie a chave para um secret store.
9. Confirme créditos/limites do Workspace e da organização. A chave permanece vinculada ao Workspace em que foi criada.

#### Configurar no PowerShell

```powershell
$env:ANTHROPIC_API_KEY="<anthropic-api-key>"
Test-Path Env:ANTHROPIC_API_KEY
rasai providers --provider anthropic
```

#### Validar

```powershell
rasai audit https://example.com --ai-provider anthropic
```

O alias `claude` resolve para o mesmo provider canônico.

#### Falhas típicas

- usuário sem papel que permita criar/gerenciar API keys;
- chave de Workspace diferente do contexto operacional esperado;
- assinatura Claude.ai existente, porém API Console sem créditos;
- chave exposta: revogue imediatamente no Console, crie outra e atualize o secret boundary.

### Mistral AI

**Variável usada pelo RASAi:** `MISTRAL_API_KEY`  
**Seleção:** `mistral`  
**API Keys:** <https://console.mistral.ai/api-keys/>  
**Quickstart de criação:** <https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key>  
**Gestão de API keys:** <https://docs.mistral.ai/admin/identity-access/api-keys>  
**Primeira chamada:** <https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request>

#### Estado comercial e escopo

O Studio permite criar API keys no modo Free, sujeito a limites de uso/rate limit; cartão não é requisito para a criação no modo Free. A key pertence ao Workspace em que foi criada e usa quota/limites desse Workspace. Pay-as-you-go pode ampliar consumo, mas não transforma a key em um tipo diferente.

#### Criar a chave

1. Entre no Mistral Studio.
2. Abra `API Keys` na barra lateral ou <https://console.mistral.ai/api-keys/>.
3. Clique em `Create new key`.
4. Informe um nome descritivo, por exemplo `rasai-local`.
5. Defina data de expiração quando apropriado; rotação periódica é recomendada.
6. Crie a chave para o Workspace que executará as chamadas de inferência do RASAi.
7. **Copie imediatamente.** A documentação Mistral informa que o valor completo aparece apenas uma vez.
8. Armazene a chave em secret store.

O RASAi não solicita nem utiliza tools, web search, agents ou connectors da Mistral neste contrato. Essas capacidades não devem ser habilitadas ou descritas como requisito do produto; eventual avaliação futura está registrada na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

#### Configurar no PowerShell

```powershell
$env:MISTRAL_API_KEY="<mistral-api-key>"
Test-Path Env:MISTRAL_API_KEY
rasai providers --provider mistral
```

#### Contrato específico do RASAi

- modelo piloto de fábrica: `mistral-small-2603`;
- endpoint fixo: `https://api.mistral.ai/v1/chat/completions`;
- autenticação Bearer;
- `service_tier=standard_only`;
- Structured Output por JSON Schema seguido de validação local;
- sem override `RASAI_MISTRAL_ENDPOINT` nesta etapa;
- sem tools/search/connectors;
- `explicit-only=true` e `auto_eligible=false` até homologação humana posterior.

#### Validar

Depois do diagnóstico seguro, o smoke funcional exigido para homologação é:

```powershell
rasai audit https://example.com --ai-provider mistral --ai-model mistral-small-2603
```

Confirme provider/modelo efetivos, Structured Output validado localmente, usage/custo materializados e ausência de tools/search externos.

#### Falhas típicas

- `401`: key incorreta, ausente, revogada ou de contexto inadequado;
- `402`: o fornecedor pode exigir habilitação de consumo/billing para o volume/recurso solicitado;
- `429`: limite do plano/Workspace;
- key configurada, mas expectativa de participação em `AI=auto`: não ocorre nesta etapa por decisão de homologação.

### Cohere

**Variável usada pelo RASAi:** `COHERE_API_KEY`  
**Seleção:** `cohere`  
**Criar/gerenciar API key:** <https://dashboard.cohere.com/api-keys>  
**Chat V2:** <https://docs.cohere.com/v2/reference/chat>  
**Structured Outputs:** <https://docs.cohere.com/v2/docs/structured-outputs>

#### Configurar no PowerShell

```powershell
$env:COHERE_API_KEY="<cohere-api-key>"
$env:RASAI_COHERE_COMMERCIAL_MODE="<TRIAL-ou-PRODUCTION>"
Test-Path Env:COHERE_API_KEY
rasai providers --provider cohere
```

#### Contrato específico do RASAi

- modelo de fábrica: `command-a-03-2025`;
- endpoint fixo: `https://api.cohere.com/v2/chat`;
- autenticação Bearer;
- `RASAI_COHERE_COMMERCIAL_MODE=UNKNOWN|TRIAL|PRODUCTION`; `UNKNOWN` é o default e mantém pricing UNPRICED;
- o endpoint `check-api-key` valida atividade da key, mas não informa ao RASAi se ela é trial ou production; essa modalidade é configuração humana não secreta;
- Structured Outputs por JSON Schema projetado para o subconjunto aceito no wire, seguido da validação local integral;
- `PROVIDER_DEFAULT` para reasoning; não existe variável de effort Cohere no contrato atual;
- sem override de endpoint;
- sem `tools`, `documents`, RAG ou Rerank nesta primeira entrega;
- `explicit-only=true` e `auto_eligible=false` até smoke humano positivo e qualificação deliberada posterior.

#### Validar

```powershell
rasai audit https://example.com --ai-provider cohere --ai-model command-a-03-2025
```

Confirme resposta estruturada aceita, usage em `billed_units`, pricing/telemetria e ausência de capacidades externas não autorizadas. A existência de Rerank/RAG na plataforma Cohere não os torna funcionalidades do RASAi.

### GitHub Copilot

**Variável usada pelo RASAi:** `COPILOT_GITHUB_TOKEN`  
**Seleção:** `copilot` ou alias `github-copilot`  
**Criar fine-grained PAT:** <https://github.com/settings/personal-access-tokens/new>  
**Autenticação do Copilot SDK:** <https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/authenticate>  
**Autenticação da Copilot CLI com PAT:** <https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli>

#### Contrato de autenticação do RASAi

O adapter atual usa o GitHub Copilot SDK com `use_logged_in_user=False`. Isso impede fallback silencioso para a sessão da Copilot CLI ou para credenciais do `gh`. O RASAi recebe explicitamente `COPILOT_GITHUB_TOKEN`.

Tipos de token aceitos pelo contrato atual:

```text
github_pat_  fine-grained personal access token
gho_         OAuth user access token
ghu_         GitHub App user access token
```

Classic PAT `ghp_` não é aceito nesse fluxo.

#### Criar o fine-grained PAT recomendado para uso local

1. Confirme que a conta pessoal possui uma assinatura Copilot elegível para autenticação como usuário.
2. Abra <https://github.com/settings/personal-access-tokens/new>.
3. Em `Resource owner`, selecione **sua conta pessoal**. Não selecione uma organização; a documentação do GitHub informa que `Copilot Requests` para esse fluxo está disponível em PAT fine-grained de propriedade do usuário.
4. Defina nome e expiração apropriados para a credencial.
5. Em `Repository access`, selecione somente o nível necessário ao seu caso: repositórios públicos, todos ou apenas repositórios escolhidos.
6. Em `Permissions`, abra a guia `Account`.
7. Clique em `Add permissions`.
8. Adicione `Copilot Requests`.
9. Gere o token.
10. Copie e armazene o token como segredo.
11. Confirme que o token começa com `github_pat_` quando usar o fluxo fine-grained PAT recomendado.

#### Configurar no PowerShell

```powershell
$env:COPILOT_GITHUB_TOKEN="<github-fine-grained-pat>"
Test-Path Env:COPILOT_GITHUB_TOKEN
rasai providers --provider copilot
```

Instalação manual do SDK opcional, quando o bootstrap não tiver instalado o extra:

```powershell
python -m pip install -e ".[copilot]"
```

#### Validar

Use primeiro o diagnóstico seguro. Para smoke funcional:

```powershell
rasai audit https://example.com --ai-provider copilot
```

#### Falhas típicas

- classic PAT `ghp_`: não suportado pelo adapter;
- token fine-grained criado com organização como `Resource owner`: `Copilot Requests` pode não estar disponível para o fluxo documentado;
- ausência da permissão de conta `Copilot Requests`;
- conta sem assinatura Copilot elegível para autenticação de usuário;
- extra Python `copilot` ausente;
- expectativa de fallback para sessão já logada: o adapter deliberadamente usa `use_logged_in_user=False`;
- expectativa de participação em `AI=auto`: Copilot permanece `explicit-only`.

### Rotação, revogação e incidente de credencial

Para qualquer provider:

1. crie uma nova credencial no console oficial;
2. atualize o secret boundary do ambiente;
3. valide presença sem imprimir o valor;
4. execute o diagnóstico seguro;
5. faça smoke mínimo quando aplicável;
6. somente depois revogue a credencial antiga, salvo incidente de segurança;
7. em caso de vazamento suspeito, **revogue primeiro** e trate qualquer indisponibilidade temporária como contenção necessária;
8. revise logs, histórico de commits, issues e artefatos para confirmar que o valor não ficou persistido.

Uma credencial real nunca deve ser enviada em comentários de issue/PR nem colada em logs de validação compartilhados. Ao solicitar suporte, forneça somente nome da variável, provider, status HTTP/classificação, timestamp, modelo e identificadores não secretos.

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

A mesma key pode atender a API diária e a API histórica. A existência da key não garante que uma URL tenha amostra CrUX elegível.

## Google Search Console

### Credencial e contexto

O contrato atual aceita duas formas OAuth.

**Recomendada para uso repetido:**

```text
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

Nesse modo, o RASAi troca o Refresh Token por um access token imediatamente antes da chamada ao Google. O access token obtido fica apenas em memória.

**Alternativa para teste pontual:**

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

`RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` é um OAuth 2.0 bearer token temporário. Uma Google API Key, normalmente iniciada por `AIza`, não é um access token OAuth e não serve para dados privados do Search Console.

`RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` identifica a propriedade à qual o usuário autenticado precisa ter acesso, por exemplo:

```text
sc-domain:example.com
https://www.example.com/
```

### Finalidade

A autenticação autoriza as coletas Search Console habilitadas pelo RASAi, incluindo Search Analytics, Sitemaps e URL Inspection conforme o escopo e os limites configurados.

### Como obter

Referências oficiais:

- pré-requisitos: <https://developers.google.com/webmaster-tools/v1/prereqs>
- autorização OAuth 2.0: <https://developers.google.com/webmaster-tools/v1/how-tos/authorizing>
- credenciais Google Cloud: <https://console.cloud.google.com/apis/credentials>
- referência da API: <https://developers.google.com/webmaster-tools/v1/api_reference_index>

Fluxo recomendado:

1. confirme que a conta Google tem acesso à propriedade Search Console;
2. crie ou selecione um projeto no Google Cloud;
3. habilite a Search Console API;
4. configure a tela de consentimento quando aplicável;
5. crie um OAuth Client ID e obtenha o respectivo Client Secret;
6. solicite consentimento com o menor escopo suficiente;
7. obtenha um Refresh Token para essa autorização;
8. configure `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID`;
9. configure `RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET` somente no boundary de secrets;
10. configure `RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN` somente no boundary de secrets;
11. configure a property exata em `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL`;
12. valide a integração no console do RASAi.

Para um teste temporário, é possível usar um access token já emitido em `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`, sabendo que ele expira e precisa ser substituído manualmente.

Escopos oficiais relevantes:

```text
https://www.googleapis.com/auth/webmasters.readonly
https://www.googleapis.com/auth/webmasters
```

Para a natureza observacional do RASAi, prefira o escopo read-only quando ele atender aos endpoints efetivamente usados.

`CLIENT_SECRET`, `REFRESH_TOKEN` e `ACCESS_TOKEN` nunca entram no INI. `CLIENT_ID` e a property são configurações não secretas. Consulte [GSC_OAUTH.md](GSC_OAUTH.md) para o contrato completo.

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
- [GSC_OAUTH.md](GSC_OAUTH.md)
- [PROVIDER_SETUP.md](PROVIDER_SETUP.md)
- [STANDARDS_METRICS_AND_SERVICES.md](STANDARDS_METRICS_AND_SERVICES.md)
- [EXTERNAL_OBSERVABILITY_INTEGRATIONS.md](EXTERNAL_OBSERVABILITY_INTEGRATIONS.md)
- [IDENTITY_AND_ACCESS.md](IDENTITY_AND_ACCESS.md)
- [SERP_OBSERVATION.md](SERP_OBSERVATION.md)
- [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md)
