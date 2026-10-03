# Compatibilidade

## Ambiente suportado

| Componente | Contrato |
|---|---|
| Python | CPython `>=3.13,<3.14` |
| Windows/PowerShell | alvo operacional principal para console e runtime local |
| Linux | alvo operacional principal para SaaS, API, workers e containers |
| Playwright | `>=1.57,<2` |
| Chromium | necessário para rendering e Synthetic Apdex |
| SQLite | local/embarcado |
| PostgreSQL | control plane centralizado/hospedado |

## Política de validação por sistema operacional

A escolha do sistema operacional de teste deve seguir a superfície realmente alterada. O projeto não exige duplicação automática Windows + Linux para toda mudança.

### Windows obrigatório

Executar validação em Windows quando a mudança envolver o produto local ou comportamento dependente do ambiente Windows, incluindo:

- console interativo e CLI usada localmente;
- launcher/bootstrap e PowerShell;
- `rasai-console.ini` e persistência Windows/User;
- SQLite local;
- filesystem, paths, locks e ciclo de vida de arquivos;
- multiprocessing/process spawning, subprocessos e sinais específicos do runtime local;
- Chromium/Playwright quando utilizado pelo fluxo local;
- abertura/localização de relatórios e artifacts no desktop.

Uma validação somente Linux não substitui o gate Windows nesses casos.

### Linux obrigatório

Executar validação em Linux quando a mudança envolver a arquitetura hospedada/SaaS, incluindo:

- Web/API;
- control plane PostgreSQL hospedado;
- workers desacoplados;
- scheduler, queue, leases e retries do ambiente hospedado;
- containers e deploy de serviços;
- integrações e observabilidade específicas do runtime SaaS.

Uma validação somente Windows não substitui o gate Linux nesses casos.

### Testes agnósticos de sistema operacional

Regras determinísticas, scoring, schemas, contratos de dados, transformações puras e outras rotinas sem dependência conhecida de sistema operacional devem rodar em um único ambiente canônico de CI. Não há ganho em duplicá-las em Windows e Linux apenas por precaução.

### Quando testar nos dois

Windows + Linux são obrigatórios somente quando:

1. o mesmo componente é suportado e executado nos dois ambientes; ou
2. a alteração cruza uma fronteira compartilhada suscetível a diferenças de SO, como filesystem, multiprocessing, subprocessos, browser runtime ou networking de baixo nível; ou
3. um incidente/regressão anterior demonstrou comportamento diferente entre os ambientes.

A regra é testar onde existe risco real, não maximizar a quantidade de jobs. macOS não integra o gate obrigatório enquanto não for formalmente promovido a plataforma suportada.

## Dispositivos

```text
mobile
desktop
both
```

Default: `mobile`. Somente contextos materializados participam das análises dependentes de snapshot e das integrações opcionais.

## IA

A auditoria funciona com IA desligada. Providers concretos suportados pelo registry:

```text
OpenAI
DeepSeek
MiMo
xAI/Grok
Qwen
Gemini
Anthropic/Claude
Mistral AI
Cohere
GitHub Copilot
```

`AI=auto` não usa uma cadeia fixa. O pool é derivado do `provider_registry`: entram somente providers com `auto_eligible=true`, credencial/configuração válidas e não excluídos por `RASAI_AI_AUTO_EXCLUDE`.

Mistral é `explicit-only` nesta entrega e não participa de `AI=auto` antes da homologação humana; o adapter usa `mistral-small-2603`, Chat Completions no endpoint global e `service_tier=standard_only`. Cohere também é `explicit-only`: o contrato atual usa Chat V2, `command-a-03-2025`, Structured Outputs com projeção de schema no wire e validação local, sem tools/documents/RAG/Rerank. GitHub Copilot também é deliberadamente `explicit-only` e não participa de `AI=auto`, mesmo quando `COPILOT_GITHUB_TOKEN` está configurado. A integração Copilot usa o SDK oficial e exige uma assinatura Copilot elegível; o extra Python é declarado em `pyproject.toml` e pode ser instalado com `python -m pip install -e ".[copilot]"` quando o bootstrap automático não for usado.

O RASAi documenta somente as combinações de credencial, modelo, endpoint, structured output e reasoning que pertencem ao contrato atual de cada adapter. A existência de outros planos ou modalidades no fornecedor não implica compatibilidade; variantes não implementadas/homologadas são rastreadas na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

Referências: [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md), [PROVIDER_SETUP.md](PROVIDER_SETUP.md) e [AI_GUIDE.md](AI_GUIDE.md).

## MiMo

O adapter atual continua compatível com o endpoint OpenAI Responses da Xiaomi e com a credencial PAYG `sk-...`. A família vigente no RASAi é `mimo-v2.6-pro` / `mimo-v2.6-flash`; `mimo-v2.5` e `mimo-v2.5-pro` permanecem selecionáveis somente até 21/10/2026 02:00 UTC.

A migração V2.6 não exige novo adapter nem nova credencial. Token Plan `tp-...`, Batch, UltraSpeed, web search, tools e multimodal não são configurações suportadas pelo contrato atual. A migração é rastreada na [issue #183](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/183); modalidades adicionais permanecem na [issue #180](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/180).

## Web Performance

PageSpeed/Lighthouse e CrUX são opcionais e independentes de IA. O default público de timeout externo é 120 s e pode ser alterado.

Acessibilidade automatizada depende do artifact Lighthouse; se PageSpeed falhar, a página de Acessibilidade deve registrar a limitação em vez de inferir resultado.

## Synthetic Apdex

Synthetic Apdex usa Chromium local e tráfego HTTP real contra o alvo. Não depende de IA, PageSpeed ou CrUX. O timeout por navegação é independente do timeout das APIs externas.

## Persistência do console

`rasai-console.ini` armazena somente parâmetros não sensíveis. Credenciais nunca entram no INI. Na sessão atual, o usuário pode definir/remover credenciais; no Windows, pode opcionalmente persistir/remover o valor no escopo `User` mediante ação explícita. O escopo `Machine` é somente observado pelo RASAi.
