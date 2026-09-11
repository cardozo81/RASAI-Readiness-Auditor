# Análise semântica por IA, roteamento e telemetria

**Estado no baseline de desenvolvimento:** aprovado / vigente  
**Limite de scoring:** `SARI-001` / `SCORE-GEO-004`

IA é uma extensão de análise semântica. LLM não é engine de scoring, não substitui Business Rules e falha/ausência de provider não é defeito do website.

## 1. Providers

Providers reconhecidos pela superfície atual de IA:

- `OPENAI`;
- `DEEPSEEK`;
- `MIMO`;
- `XAI` / alias `grok`;
- `QWEN`;
- `GEMINI`;
- `ANTHROPIC` / alias `claude`;
- `COPILOT` / alias `github-copilot`;
- `NONE`;
- `AUTO`.

A qualificação de um provider (`QUALIFIED`, `PROVISIONAL` etc.) é informação de governança. A participação em `AUTO` é propriedade separada do `provider_registry`, expressa por `auto_eligible`, e ainda exige credencial/configuração válida na execução.

Providers de extensão podem permanecer `PROVISIONAL` e, ainda assim, participar de `AUTO` quando o registry vigente os marcar como `auto_eligible=true` e a configuração da execução estiver apta. Qualificação e elegibilidade AUTO não são sinônimos.

GitHub Copilot é a exceção deliberada: `explicit_only=true` e `auto_eligible=false`. Mesmo configurado, nunca entra em `AI=auto`; o usuário precisa selecioná-lo explicitamente.

## 2. Defaults públicos de modelo

Os defaults públicos efetivamente aplicados pelo runtime são:

| Provider | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| OpenAI | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | `gpt-5.6-luna` para custo/volume; `gpt-5.6-sol` quando a prioridade for máxima qualidade |
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | `deepseek-v4-flash` no uso normal |
| MiMo | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | `mimo-v2.5` no uso normal |
| xAI | `grok-4.6` | `grok-4.6` | default |
| Qwen | `qwen3.8-flash` | `qwen3.8-max`, `qwen3.8-flash` | `qwen3.8-flash` |
| Gemini | `gemini-3.8-flash` | `gemini-3.8-flash` | default |
| Anthropic | `claude-sonnet-5` | `claude-sonnet-5` | default |
| GitHub Copilot | `auto` | `auto` | deixar o SDK/assinatura resolver o modelo disponível; seleção explícita |

Esses são os defaults públicos de `provider_runtime_policy`. Defaults internos antigos de classes/qualificação não devem ser apresentados como defaults efetivos da CLI/console.

Referência normativa consolidada: `../ENVIRONMENT_VARIABLES.md`.

## 3. Política `AUTO`

`AUTO` **não é uma cadeia fixa**.

O runtime atual:

1. consulta o `provider_registry`;
2. considera providers com `auto_eligible=true`;
3. remove providers sem credencial, modelo ou configuração válidos para a execução;
4. remove os providers explicitamente listados em `RASAI_AI_AUTO_EXCLUDE`;
5. distribui a preferência inicial entre necessidades de IA usando round-robin compartilhado;
6. em uma mesma necessidade, tenta cada provider elegível no máximo uma vez;
7. encerra aquela necessidade na primeira resposta válida;
8. aplica circuit breaker e classificação de falhas para decidir se um provider continua elegível em necessidades posteriores.

`RASAI_AI_AUTO_EXCLUDE` tem default vazio. Os valores permitidos são lista CSV ou separada por `;` de IDs/aliases elegíveis. O recomendado é manter vazio e excluir somente providers que devam continuar configurados para seleção explícita, mas não participar do pool AUTO.

Excluir um provider de `AUTO` não apaga sua credencial e não impede seleção explícita.

Providers `explicit-only`, atualmente GitHub Copilot, não são candidatos ao pool AUTO nem à lista operacional de inclusão/exclusão desse pool.

## 4. Provider explícito

Provider selecionado explicitamente não faz failover cruzado silencioso para outro fornecedor.

Credenciais ausentes de providers não selecionados não podem invalidar um provider explícito funcional.

Selecionar explicitamente um provider sem configuração/credencial suficiente resulta em estado operacional correspondente, com zero chamada externa para aquele provider; não existe fallback automático para usar a chave de outro fornecedor.

GitHub Copilot usa `COPILOT_GITHUB_TOKEN`, o SDK oficial e `use_logged_in_user=False`, evitando fallback silencioso para sessão GitHub/Copilot já autenticada na máquina.

## 5. Falhas, retry e circuit breaker

Falhas são classificadas para separar indisponibilidade temporária de condição terminal.

Regras vigentes do coordenador AUTO incluem:

- uma falha temporária pode avançar para o próximo provider na necessidade atual e ainda permitir que o provider volte a participar de necessidades posteriores;
- condição terminal remove o provider imediatamente do restante da execução;
- o circuit breaker abre quando o provider acumula **três falhas entre as últimas cinco observações** da execução;
- uma quarentena interna legada do adapter, isoladamente, não possui autoridade para retirar definitivamente o provider do pool AUTO; a decisão final pertence ao coordenador/registry da execução;
- retries/fallbacks permanecem limitados para evitar chamadas/custo duplicados.

Falhas de rede, timeout, servidor, rate limit ou resposta vazia podem ser tratadas como temporárias conforme o classificador vigente. Auth, permission, crédito/quota, modelo, contrato ou resposta inválida podem ser terminais conforme a classificação produzida pelo runtime.

`Retry-After`, quando aplicável, é tratado de forma limitada pelo contrato de resiliência; não autoriza espera ilimitada.

## 6. Consistência URL/dispositivo

O escopo público de dispositivo é `mobile`, `desktop` ou `both`. Somente contextos materializados podem disparar chamada de IA.

Quando a política fixa provider por URL ou reutiliza preferência contextual, essa consistência deve seguir o runtime vigente. A comparação `BR-GEO-052` só existe quando ambos os dispositivos fazem parte do escopo.

## 7. Validação do contrato

Todos os adapters convergem para contrato normalizado. Uma resposta semântica só é aceita após validação local de:

- schema/estrutura esperada;
- conjunto de regras semânticas;
- ausência de duplicação/regra desconhecida;
- enums;
- `evidence_ids` existentes;
- completude contratual.

HTTP 200 ou JSON parseável isoladamente não significam resultado válido.

Uma resposta que referencia evidência inexistente ou viola o schema deve ser rejeitada como erro de integração/contrato, não convertida em finding do website.

Na integração Copilot, o contrato provider-neutral e as evidências permitidas são encapsulados no prompt do SDK; a resposta continua submetida às mesmas validações locais. A sessão é criada sem tools e não autoriza edição, shell ou browser agentic.

## 8. Reasoning

Defaults públicos:

| Provider | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| OpenAI | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` no baseline |
| DeepSeek | `NONE` | `NONE`, `LOW`, `HIGH`, `MAX` | `NONE` no baseline |
| MiMo | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` no baseline |
| xAI | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` |
| Qwen | `PROVIDER_DEFAULT` | `PROVIDER_DEFAULT` na superfície vigente | não criar variável de reasoning inexistente |
| Gemini | `LOW` | `LOW`, `MEDIUM`, `HIGH` | `LOW` |
| Anthropic | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` |
| GitHub Copilot | `PROVIDER_DEFAULT` | `PROVIDER_DEFAULT` via SDK | não criar variável de reasoning inexistente |

Aumentar reasoning pode elevar latência, tokens e custo. Esses valores não participam do scoring.

## 9. Telemetria

`ai_provider_attempts` pode registrar:

- URL/dispositivo/tentativa;
- provider/modelo/rank/reasoning;
- timestamps/duração;
- status e diagnóstico sanitizado;
- uso reportado;
- custo estimado e versão de pricing;
- hashes/resumos limitados;
- versão do contrato semântico;
- decisão de retry/fallback/sucesso quando aplicável.

`ai_exchange_log` pode preservar intercâmbios sanitizados conforme a política de segurança e limite configurado.

Segredos, headers de autorização, payload sensível integral e raciocínio privado não são persistidos.

Tokens ausentes permanecem `NULL`. Custo estimado é telemetria operacional, não invoice e não participa do score.

## 10. Relatório

Página pública de telemetria:

```text
report/ai-usage.html
```

O relatório deve distinguir configuração, tentativa, sucesso, provider previsto/efetivo, fallback, status, tokens e custo estimado sem converter falha de IA em finding do website.

O renderer não mantém allowlist visual de providers: nomes/modelos vêm da telemetria persistida. Assim, providers registrados como Copilot aparecem quando efetivamente utilizados sem exigir branch específica de HTML.

## 11. Limite de scoring

Invariantes:

1. IA permanece opcional;
2. `NONE` executa o auditor sem chamadas de LLM;
3. ausência/falha de IA não equivale a baixa qualidade do website;
4. LLM não calcula `SCORE-GEO-004`;
5. somente evidência persistida pode sustentar resultado aceito;
6. resultado válido não pode ser sobrescrito por tentativa posterior;
7. contexto de dispositivo limita chamadas ao escopo solicitado;
8. telemetria é separada de findings e score;
9. outcomes externos não entram em `SARI-001`/`SCORE-GEO-004` sem nova metodologia explícita/versionada;
10. o conjunto `AUTO` é derivado do registry vigente, não de uma lista histórica fixa escrita nesta especificação.

## 12. Onboarding e fonte de verdade

O `provider_registry` é a fonte técnica para IDs, aliases, credenciais, modelos e elegibilidade AUTO. URLs oficiais de cadastro/login e geração de credenciais ficam consolidadas em `../PROVIDER_SETUP.md`.

Documentação e superfícies de UI devem projetar o registry, não manter listas independentes que possam divergir do runtime.
