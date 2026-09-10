# MODEL_ROUTING_POLICY.md

**Estado:** BASELINE OPERACIONAL VIGENTE  
**Escopo:** separar a IA usada para desenvolver o RASAi da IA consumida pelo runtime do produto.

## 1. Dois usos distintos de IA

### A. IA usada no desenvolvimento do RASAi

É a ferramenta/agente utilizada para ler especificações, criar ou revisar código, executar testes, diagnosticar problemas e avaliar arquitetura. A escolha depende do ambiente de desenvolvimento e não integra o contrato funcional do runtime.

Quando uma tarefa exigir criar ou editar arquivos em um repositório, a ferramenta utilizada precisa possuir acesso efetivo ao repositório/filesystem ou a um conector autorizado. Um chat sem esse acesso não deve afirmar que gravou arquivos localmente.

### B. IA usada pelo RASAi em runtime

É o conjunto de adapters de IA registrado no `provider_registry` canônico e consumido pela análise semântica e pelas finalidades compatíveis que reutilizam o mesmo contrato de execução.

Os dois usos não devem ser confundidos. O modelo que executa uma atividade de desenvolvimento não define o provider/modelo utilizado pela auditoria do produto.

## 2. Roteamento de esforço no desenvolvimento

A política de desenvolvimento é capability-based:

- tarefa mecânica ou textual → configuração rápida suficiente;
- implementação ou diagnóstico não trivial → modelo de raciocínio adequado;
- alteração transversal, scoring, persistência ou segurança → maior capacidade de raciocínio disponível;
- alteração de arquivos → agente/ferramenta com acesso real ao repositório;
- ausência de acesso de escrita → não declarar alteração como executada.

Nomes comerciais de modelos de desenvolvimento podem mudar e não constituem requisito normativo do RASAi.

## 3. Runtime multi-provider vigente

O runtime atual não está limitado a OpenAI. O registry canônico inclui:

| Seleção canônica | Provider | Aliases CLI relevantes | Participação possível em `AUTO` |
|---|---|---|---|
| `openai` | OpenAI | — | sim, se configurado e apto |
| `deepseek` | DeepSeek | — | sim, se configurado e apto |
| `mimo` | Xiaomi MiMo | — | sim, se configurado e apto |
| `xai` | xAI / Grok | `grok` | sim, se configurado e apto |
| `qwen` | Alibaba Qwen | — | sim, se configurado e apto |
| `gemini` | Google Gemini | — | sim, se configurado e apto |
| `anthropic` | Anthropic Claude | `claude` | sim, se configurado e apto |
| `none` | nenhum provider externo | — | não se aplica |
| `auto` | coordenador dinâmico | — | usa o pool elegível |

A propriedade `auto_eligible` pertence ao registry; participação efetiva exige também credencial e configuração válidas e ausência de exclusão explícita pelo usuário.

## 4. Defaults públicos, valores permitidos e recomendação

Os defaults públicos efetivos são definidos por `provider_runtime_policy` e são distintos de modelos históricos de qualificação interna.

| Provider | Modelo default público | Modelos permitidos pelo registry | Recomendado para operação padrão |
|---|---|---|---|
| OpenAI | `gpt-5.6-luna` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | default público, salvo necessidade técnica específica |
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro`, `deepseek-v4-flash` | default público |
| MiMo | `mimo-v2.5` | `mimo-v2.5-pro`, `mimo-v2.5` | default público |
| xAI | `grok-4.6` | conforme registry vigente | default público |
| Qwen | `qwen3.8-flash` | conforme registry vigente | default público |
| Gemini | `gemini-3.8-flash` | conforme registry vigente | default público |
| Anthropic | `claude-sonnet-5` | conforme registry vigente | default público |

A referência operacional completa de modelos e variáveis é `../ENVIRONMENT_VARIABLES.md` e deve ser usada quando o conjunto permitido mudar.

Defaults de reasoning do runtime:

| Provider | Default efetivo | Valores permitidos pelo runtime | Recomendado padrão |
|---|---|---|---|
| OpenAI | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `NONE` |
| DeepSeek | `NONE` | `NONE`, `LOW`, `HIGH`, `MAX` | `NONE` |
| MiMo | `NONE` | `NONE`, `LOW`, `MEDIUM`, `HIGH` | `NONE` |
| xAI | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH` | `LOW` |
| Qwen | `PROVIDER_DEFAULT` | `PROVIDER_DEFAULT` | `PROVIDER_DEFAULT` |
| Gemini | `LOW` | `LOW`, `MEDIUM`, `HIGH` | `LOW` |
| Anthropic | `LOW` | `LOW`, `MEDIUM`, `HIGH`, `XHIGH`, `MAX` | `LOW` |

O default de timeout de IA é `180` segundos. Alterações desse valor devem respeitar a validação do runtime e a documentação canônica de ambiente.

## 5. Seleção explícita e `AUTO`

Seleção explícita mantém o provider solicitado e suas regras específicas de retry. Não existe failover cruzado automático para outro fornecedor apenas porque um provider explícito falhou.

`AI=auto`:

1. consulta todos os providers registrados como `auto_eligible`;
2. exclui providers sem credencial/configuração válida;
3. aplica `RASAI_AI_AUTO_EXCLUDE` sem apagar credenciais ou impedir seleção explícita posterior;
4. usa round-robin compartilhado entre necessidades de IA;
5. tenta cada provider elegível no máximo uma vez por necessidade;
6. aplica estado de saúde e circuit breaker durante a execução;
7. encerra a necessidade no primeiro resultado válido.

A exclusão de um provider do `AUTO` altera apenas participação no pool daquela política; não remove sua configuração.

## 6. Fallback e estado de falha

Ausência de provider configurado ou uso de `none` não transforma limitação do auditor em defeito do website.

Princípios:

- análise determinística continua quando aplicável;
- regras semânticas sem evidência suficiente podem permanecer `UNKNOWN`;
- falha de autenticação, quota, crédito, modelo, contrato, rede ou serviço é estado operacional do provider;
- resultado válido deve satisfazer schema e fechamento de `evidence_ids`;
- HTTP 200 ou JSON parseável, isoladamente, não prova resposta semântica válida.

## 7. Saúde do provider durante a execução

Falhas terminais podem retirar imediatamente o provider do pool da execução. Falhas temporárias alimentam a janela de saúde; o circuit breaker vigente abre quando três falhas aparecem entre as últimas cinco observações daquele provider.

Esse estado é limitado à execução corrente e não altera configuração global.

## 8. Separação do domínio

Adicionar ou atualizar um adapter de provider não deve exigir redefinir Business Rules, Finding, Score, Report ou Domain Model. Todos os adapters convergem para o contrato semântico normalizado e permanecem sujeitos à validação local do RASAi.

IA não calcula `SARI-001` nem escolhe pesos do `SCORE-GEO-004`.

## 9. Segurança e telemetria

Credenciais não são persistidas no `audit.db`, HTML ou logs. Telemetria deve ser sanitizada e pode registrar provider, modelo, finalidade, duração, status, usage e custo estimado quando houver base confiável.

O custo persistido é estimativa operacional e não invoice do provider.

## 10. Regra documental

Políticas de branch, PR, merge e marcos de implementação pertencem ao processo de desenvolvimento e ao histórico Git, não a este contrato de runtime. Esta especificação deve acompanhar o registry e a `provider_runtime_policy` vigentes em `main`.