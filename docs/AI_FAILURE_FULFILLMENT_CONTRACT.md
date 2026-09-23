# Contrato de falhas de IA, fulfillment e conclusão do AUD

**Estado do produto:** pré-publicação.  
**Data de referência desta documentação:** 14/09/2026.  
**Contrato de pricing de referência:** `RASAI-PRICING-2026-09-13`.

Este documento define a relação entre configuração efetiva, trabalho esperado, tentativas externas, consumo, fulfillment, resultado lógico do `AUD-*`, reprocessamento e apresentação no console/SaaS.

O objetivo é impedir que o encerramento físico de um processo, a disponibilidade de um provider ou a existência de um HTML sejam confundidos com conclusão analítica da auditoria.

## 1. Dois estados diferentes

O RASAi mantém duas noções que não são equivalentes:

1. **progresso físico da execução**: indica quanto do processo/orquestração terminou;
2. **fulfillment lógico do AUD**: indica se todos os requisitos obrigatórios e aplicáveis da configuração original foram atendidos.

Uma execução pode chegar a:

```text
Execução física : 100% ENCERRADA
```

sem que o AUD esteja completo.

Exemplo válido:

```text
Execução física : 100% ENCERRADA
Status do AUD   : PARCIAL - REPROCESSÁVEL
Relatório       : PRELIMINARY
Score           : PENDING
Consolidação    : NÃO ELEGÍVEL
Requisitos      : 7/8 atendidos
```

`100%` descreve o término físico do processo. Não significa sucesso de todos os requisitos.

## 2. Universo obrigatório da auditoria

A configuração efetiva original define os work items que precisam ser satisfeitos.

Um componente opcional só entra como requisito quando foi efetivamente solicitado ou habilitado pela configuração aplicável à execução.

Exemplos de componentes que podem participar do fulfillment:

- `CORE_AUDIT`;
- `SEMANTIC_AI`;
- `TECHNICAL_AI`;
- `CONTENT_REMEDIATION_AI`;
- `IMPROVEMENT_INTELLIGENCE`;
- `WEB_PERFORMANCE`;
- `SYNTHETIC_APDEX`;
- `EXPERIENCE_APDEX`;
- `GOOGLE_SEARCH_CONSOLE`;
- demais serviços opcionais quando possuírem contrato canônico próprio de fulfillment.

Serviços default que não constituem uma escolha explícita do usuário não são promovidos indiscriminadamente a requisito obrigatório apenas por existirem no registry.

PageSpeed/Lighthouse e CrUX continuam representados pelo work item canônico de Web Performance enquanto essa for a unidade metodológica vigente. Não se cria obrigação paralela apenas para aumentar o denominador.

## 3. Estados de work item

O contrato base continua usando os estados canônicos existentes e admite estados operacionais adicionais que continuam sendo pendências até resolução.

| Estado | Significado |
| --- | --- |
| `SUCCESS` | requisito atendido |
| `NOT_APPLICABLE` | requisito não se aplica ao universo observado |
| `DISABLED` | recurso não solicitado/desabilitado |
| `WAITING_FOR_DATA` | falta evidência/pré-requisito recuperável |
| `NOT_CONFIGURED` | recurso solicitado, mas configuração obrigatória está ausente |
| `REQUESTED_NOT_EXECUTED` | recurso solicitado e elegível, porém sem execução materializada |
| `FAILED_RETRYABLE` | houve tentativa/falha recuperável |
| `FAILED_PERMANENT` | falha não recuperável no mesmo AUD |
| `BLOCKED` | requisito bloqueado por integridade, dependência ou condição não recuperável no mesmo fluxo |

`NOT_CONFIGURED` e `REQUESTED_NOT_EXECUTED` são pendências. Não são sucesso e não podem desaparecer do denominador quando o componente era obrigatório.

## 4. REQUESTED_NOT_EXECUTED

O estado `REQUESTED_NOT_EXECUTED` representa explicitamente:

```text
solicitado = sim
pré-requisitos = suficientes para a etapa existir
execução materializada = não
```

Exemplos:

- `RASAI_IMPROVEMENT_INTELLIGENCE=true`, mas nenhuma execução da análise profunda foi materializada;
- `RASAI_SYNTHETIC_APDEX=true`, mas nenhuma execução Synthetic Apdex foi registrada;
- `RASAI_APDEX_EXPERIENCE=true`, mas nenhuma execução Experience Apdex foi registrada;
- integração com contrato de fulfillment solicitada e sem registro operacional após a finalização.

A classificação é de orquestração/runtime e permanece reprocessável.

## 5. CONTRACT_ERROR não é provider indisponível

Um provider pode responder corretamente no transporte/API e ainda assim devolver conteúdo recusado pelo contrato evidence-bound do RASAi.

Fluxo:

```text
RASAi
  -> provider
  -> resposta HTTP/API recebida
  -> tokens observados
  -> validação local do contrato técnico
  -> resposta viola o contrato evidence-bound
  -> CONTRACT_ERROR
```

Nesse caso é incorreto classificar a tentativa como indisponibilidade do provider.

O provider esteve disponível para transporte e execução. A falha está na validade contratual do conteúdo recebido.

### 5.1 Diagnóstico do contrato técnico

Para uma rejeição local do contrato técnico, a tentativa mantém:

```text
status       = CONTRACT_ERROR
error_class  = CONTRACT_ERROR
error_type   = tipo da exceção local, por exemplo ValueError
error_code   = TECHNICAL_AI_CONTRACT_VALIDATION_ERROR
error_detail = mensagem sanitizada da validação
```

O fulfillment projeta isso como:

```text
component    = TECHNICAL_AI
status       = FAILED_RETRYABLE
error_class  = AI_CONTRACT
error_code   = TECHNICAL_AI_CONTRACT_VALIDATION_ERROR
```

A mensagem sanitizada preserva o motivo concreto, por exemplo uma referência de evidência fora do universo permitido para o recurso avaliado.

### 5.2 Proteções que permanecem obrigatórias

A classificação correta do erro não reduz as validações do contrato técnico.

Continuam inválidos, entre outros:

- diagnostic code desconhecido;
- `evidence_id` inexistente;
- evidência fora do universo fornecido;
- evidência de um recurso usada para justificar outro;
- recurso duplicado;
- campos obrigatórios ausentes;
- classificação inválida;
- confidence fora do intervalo permitido;
- schema inconsistente.

Nenhuma resposta rejeitada é promovida artificialmente a sucesso.

## 6. Retry corretivo de CONTRACT_ERROR

No contrato vigente, `CONTRACT_ERROR` do contrato técnico é marcado como:

```text
retry_eligible = true
decision       = REPROCESS_ELIGIBLE
```

O retry corretivo é executado por **reprocessamento seletivo**, e não como uma segunda chamada automática imediata no mesmo passo.

Motivo: erros evidence-bound podem indicar violação estrutural ou metodológica. Reenviar automaticamente uma mensagem de reparo sem uma política especializada por classe de erro poderia:

- gerar chamada paga adicional sem ganho provável;
- induzir a IA a mascarar uma referência inválida;
- alterar a estrutura sem corrigir a relação real entre recurso e evidência;
- criar comportamento diferente entre providers.

Se retry corretivo automático vier a ser habilitado, deverá ser bounded, provider-neutral, contabilizado como nova tentativa e restrito às classes consideradas estruturalmente reparáveis.

## 7. Fallback e cadeia de providers

Cada chamada continua sendo uma tentativa independente.

Quando uma tentativa falha e outra IA é chamada na sequência:

- a nova tentativa registra `fallback_from_provider` e `fallback_reason` quando aplicável;
- a tentativa anterior permanece append-only;
- o fallback não apaga tokens/custo da tentativa anterior;
- AUTO e seleção explícita continuam obedecendo as regras canônicas de roteamento;
- quarentena não é contornada por este contrato.

`CONTRACT_ERROR` não é convertido automaticamente em `PROVIDER_UNAVAILABLE` para justificar quarentena.

## 8. Pricing e custo por tentativa

Não existe um pricing resolver específico para fulfillment ou retry.

Toda chamada real usa o motor canônico introduzido pela arquitetura parametrizável:

```text
catálogo de pricing selecionado
             ->
regra vigente para provider/modelo/contexto/horário
             ->
ai_provider_attempts
```

Uma tentativa que termina em `CONTRACT_ERROR` pode ter custo real estimável porque o provider respondeu e devolveu usage.

Esse custo não desaparece por a resposta analítica ter sido rejeitada.

Persistem, quando informados pelo provider/adapters:

- input tokens;
- cached input tokens;
- output tokens;
- reasoning tokens;
- total tokens;
- custo estimado observado;
- moeda;
- `pricing_version`;
- horário e duração.

### 8.1 Tentativas posteriores

Uma nova tentativa causada por reprocessamento, retry ou fallback usa a política de preço vigente no instante da nova chamada.

Exemplo:

```text
tentativa 1 - 00:55 UTC - pricing rule A
tentativa 2 - 01:05 UTC - pricing rule B
```

Cada tentativa conserva seu próprio `pricing_version` e custo.

### 8.2 Histórico não é reprecificado

Se o catálogo de preços mudar amanhã, uma tentativa persistida hoje não é recalculada retroativamente.

O catálogo atual serve novas chamadas. A telemetria histórica conserva os valores e a versão de pricing aplicada no momento da tentativa.

## 9. Google Search Console: configuração não é falha da IA técnica

Google Search Console exige sua configuração própria: uma property e uma forma OAuth válida.

As formas aceitas são:

```text
# recomendada para uso repetido
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN

# alternativa temporária/manual
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

Se o serviço foi explicitamente solicitado e falta a property:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

o work item é:

```text
component    = GOOGLE_SEARCH_CONSOLE
status       = NOT_CONFIGURED
error_class  = CONFIGURATION
error_code   = SITE_URL_REQUIRED
```

Se a property existe, mas nenhuma forma OAuth está completa, o estado também permanece `NOT_CONFIGURED`, com diagnóstico de configuração/autenticação correspondente. Uma Google API Key, normalmente iniciada por `AIza`, não substitui OAuth.

No modo durável, o RASAi obtém o access token a partir do Refresh Token imediatamente antes da chamada e não o persiste.

Nenhum desses estados altera `TECHNICAL_AI` nem deve aparecer como indisponibilidade de DeepSeek, OpenAI ou outro provider.

Depois de corrigir autenticação/property, o item pode voltar a ser elegível para reprocessamento dentro das regras temporais aplicáveis.

## 10. Análise profunda por IA

Quando `RASAI_IMPROVEMENT_INTELLIGENCE=true`, a análise profunda passa a participar do fulfillment da execução.

Ela usa a **mesma seleção principal de IA** da auditoria. Não possui provider, modelo ou reasoning próprios. Com `AI=auto`, reutiliza a mesma política canônica de elegibilidade, custo, quarentena, circuit breaker e fallback.

Estados relevantes:

- configuração principal de IA inválida/indisponível para o requisito: `NOT_CONFIGURED`;
- configuração válida sem execução persistida: `REQUESTED_NOT_EXECUTED`;
- execução `COMPLETE`: `SUCCESS`;
- execução `COMPLETE_WITH_LIMITATIONS`: `FAILED_RETRYABLE` até que o requisito solicitado possa ser satisfeito conforme o contrato de recuperação.

As tentativas continuam usando `ai_provider_attempts` e o mesmo pricing canônico.

## 11. Synthetic Apdex e Experience Apdex

Quando explicitamente solicitados, ambos devem estar representados no fulfillment.

Se as tabelas de execução existem, o estado é reconciliado pelos contratos específicos já existentes.

Se o toggle está ativo, mas nenhuma execução foi materializada, o estado é `REQUESTED_NOT_EXECUTED` em vez de a etapa desaparecer do denominador.

As coletas continuam classificadas como `LIVE_RECOLLECTION` e respeitam a validade temporal do AUD.

## 12. Resultado final do console

A tela final deve separar o encerramento físico do resultado lógico.

Exemplo parcial:

```text
====================================================================
RESULTADO DA AUDITORIA
====================================================================
Execução física : 100% ENCERRADA
Audit ID        : AUD-...
Status do AUD   : PARCIAL - REPROCESSÁVEL
Relatório       : PRELIMINARY
Score           : PENDING
Consolidação    : NÃO ELEGÍVEL
Requisitos      : 7/8 atendidos

PENDÊNCIAS

[REPROCESSAR] TECHNICAL_AI
Estado     : FAILED_RETRYABLE
Classe     : AI_CONTRACT
Provider   : DEEPSEEK
Modelo     : deepseek-v4-pro
Código     : TECHNICAL_AI_CONTRACT_VALIDATION_ERROR
Detalhe    : provider respondeu; resposta rejeitada pelo contrato evidence-bound do RASAi

[CONFIGURAR] GOOGLE_SEARCH_CONSOLE
Estado     : NOT_CONFIGURED
Código     : SITE_URL_REQUIRED
====================================================================
```

Exemplo final:

```text
Execução física : 100% ENCERRADA
Status do AUD   : COMPLETO
Relatório       : FINAL
Score           : FINAL
Consolidação    : ELEGÍVEL
```

## 13. Reprocessamento seletivo

O `AUD-*` continua sendo uma observação lógica única.

O reprocessamento:

- não repete work item efetivamente `SUCCESS`;
- executa pendências elegíveis;
- mantém tentativas anteriores;
- mantém custos anteriores;
- adiciona novos custos apenas para novas chamadas reais;
- usa pricing vigente para a nova tentativa;
- reconstrói o estado público com o resultado efetivo mais recente;
- só promove o AUD a `COMPLETE` quando todos os requisitos obrigatórios e aplicáveis estão satisfeitos.

Um `CONTRACT_ERROR` técnico é reprocessável sem apagar a primeira tentativa que consumiu tokens.

## 14. Consolidação

`consolidation_eligible=true` continua significando que a AUD está integralmente apta/conclusiva para consolidação.

Separadamente, uma AUD fisicamente concluída, íntegra e com pendências obrigatórias apenas reprocessáveis pode ser lida pelo CONS como fonte **não conclusiva**, com as limitações e a recomendação de reprocessamento explicitadas. Essa utilização limitada não altera `consolidation_eligible` da AUD e não promove score/diagnóstico pendente a final.

Término de subprocesso, geração física dos HTMLs ou sucesso do core isoladamente não tornam uma auditoria conclusiva.

## 15. SaaS e control plane

O contrato não é exclusivo do console.

O mesmo `audit_fulfillment_*`, `ai_provider_attempts` e pricing canônico são consumidos pelo worker/control plane.

O SaaS deve poder distinguir:

- execução física do job;
- fulfillment do AUD;
- falha de provider;
- falha de contrato local;
- ausência de configuração;
- solicitado mas não executado;
- retryabilidade;
- fallback;
- custo e `pricing_version` de cada tentativa.

Payloads duráveis continuam secret-free.

A camada SaaS não mantém uma tabela paralela de preço nem uma lógica alternativa de fulfillment.

## 16. Segurança e diagnóstico

Mensagens de exceção persistidas são sanitizadas.

Não devem ser persistidos no `error_detail`:

- API keys;
- bearer tokens;
- refresh tokens;
- client secrets;
- senhas;
- secrets;
- payload integral sensível;
- conteúdo proibido pelos contratos existentes de segurança.

O objetivo do diagnóstico é responder com precisão:

- o provider respondeu?;
- houve erro HTTP/timeout/auth/quota?;
- houve resposta inválida?;
- houve `CONTRACT_ERROR` local?;
- qual validação recusou a resposta?;
- houve fallback?;
- quanto cada tentativa consumiu/custou?;
- qual pricing version e contrato semântico estavam ativos?.

## 17. Relação com outros documentos

- `AI_PRICING_CONFIGURATION.md`: catálogo e schema de preços.
- `AUTO_COST_AWARE_AI_ROUTING.md`: seleção econômica no modo AUTO.
- `AUDIT_REPROCESSING.md`: recuperação seletiva do mesmo `AUD-*`.
- `IMPROVEMENT_INTELLIGENCE.md`: contrato da análise profunda.
- `GSC_OAUTH.md`: autenticação atual do Google Search Console.
- `EXTERNAL_OBSERVABILITY_INTEGRATIONS.md`: integrações externas e Google Search Console.

Este documento descreve o contrato atual do produto em desenvolvimento.

## 18. Execução parcial e disponibilidade externa

A indisponibilidade de IA/API não é, por si só, falha fatal da execução. O pipeline e o `report-catalog/` podem ser materializados com fulfillment parcial, desde que dados válidos, provenance e integridade sejam preservados.

As causas permanecem distintas:

- IA opcional não solicitada: sem pendência;
- IA necessária para fechamento com provider `none`: `NOT_CONFIGURED`, sem tentativa/custo;
- IA bloqueada por evidência insuficiente: `WAITING_FOR_DATA` / `PREREQUISITE`, sem tentativa/custo;
- provider configurado que foi chamado e falhou: tentativa persistida e estado de falha correspondente;
- API solicitada sem configuração ou indisponível: pendência própria da integração.

`report_status=PRELIMINARY` descreve completude lógica, não ausência física do HTML. A Matriz de encerramento estrutural permanece independente do fechamento diagnóstico.

O contrato completo está em [PARTIAL_DIAGNOSTIC_EXECUTION.md](PARTIAL_DIAGNOSTIC_EXECUTION.md).
