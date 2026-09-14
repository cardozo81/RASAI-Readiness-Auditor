# Reprocessamento seletivo de auditorias

O RASAi está em desenvolvimento e ainda não foi publicado. Este documento descreve somente o contrato atual do produto.

O RASAi trata cada `AUD-*` como **uma única observação lógica**. Uma auditoria pode precisar de zero, uma ou várias reexecuções para satisfazer integralmente a configuração escolhida pelo usuário, sem transformar essas reexecuções em novas observações para histórico, tendência ou consolidação.

## Contrato de conclusão

A configuração original da auditoria define o universo obrigatório daquela execução. O estado final só é `FINAL` quando todos os requisitos obrigatórios e aplicáveis dessa configuração possuem um resultado efetivo de sucesso e continuam metodologicamente válidos.

Enquanto existir requisito pendente, recuperável, bloqueado ou fora da validade temporal:

- o processamento não é considerado concluído;
- o score final não é publicado como definitivo;
- o relatório é identificado como preliminar;
- o `AUD-*` não participa de relatórios consolidados, tendências, médias, percentis ou comparações históricas.

A existência física dos arquivos HTML não significa, por si só, que a auditoria atingiu o estado final.

## Reprocessamento pelo console interativo

O caminho normal para um operador local é:

```text
rasai-console
> Auditorias / histórico
> selecionar AUD-*
> Reprocessar pendências desta auditoria
```

Antes de confirmar, o console apresenta os itens ainda não resolvidos e a quantidade de sucessos preservados quando o fulfillment já está projetado.

A confirmação exige:

```text
REPROCESSAR
```

### Acompanhamento durante a execução

Depois da confirmação, **processar e reprocessar usam a mesma superfície operacional do console**. O reprocessamento não possui uma segunda tela de execução com outra disposição de informações.

Enquanto o `RPR-*` está ativo, a tela mantém a mesma estrutura usada por uma execução normal:

```text
Status
URL
Dispositivo
Operação
Ambiente
Início
Fim
Duração
Etapa
Andamento
Progresso
Executando

Audit ID
Log técnico
```

A diferença está somente no conteúdo da etapa. No reprocessamento, `Etapa` identifica `Reprocessamento seletivo` e `Executando` informa o requisito que está sendo avaliado, sua scope, quantidade já avaliada e sucessos anteriores preservados.

O custo não é inserido em uma posição paralela no meio da tela de andamento. Assim como no processamento normal, a telemetria monetária e de consumo fica na área de pós-execução. Isso evita misturar andamento do pipeline com valores acumulados do AUD.

A apresentação é atualizada por leitura do estado persistido dos work-items. Essa projeção não cria outro motor de reprocessamento e não altera as regras de seleção, retry, quarentena, provider ou custo.

### Resumo e custos ao terminar

Ao terminar, o console primeiro fecha a execução com a mesma estrutura do processamento normal:

```text
Status / tempo / progresso concluído
Audit ID
Log técnico
Relatórios
```

Na área de pós-execução são mostrados os dados específicos do `RPR-*`:

```text
RPR
Processamento
Score
Relatório
Elegibilidade para consolidação
Itens tentados
Itens resolvidos
Sucessos preservados
Itens restantes
Itens temporalmente expirados, quando existirem
```

Se algum requisito continuar pendente, o console não apresenta apenas `Itens restantes: N`. Para cada item não resolvido mostra:

- componente e scope;
- status efetivo (`WAITING_FOR_DATA`, `FAILED_RETRYABLE`, `BLOCKED` ou equivalente);
- código e mensagem do último motivo persistido;
- quantidade de tentativas;
- orientação operacional para a próxima ação;
- limite temporal quando o requisito depende de `LIVE_RECOLLECTION`.

Em seguida aparecem os custos no mesmo contexto de pós-execução usado pelo processamento:

1. **Consumo desta tentativa de reprocessamento**: diferença entre a telemetria persistida antes e depois do `RPR-*`, incluindo novas tentativas de IA, tokens, custo estimado e novas chamadas Web Performance.
2. **Consumo e cobertura real persistidos do AUD**: reutiliza exatamente o renderer padrão já usado após uma execução normal, preservando todas as tentativas anteriores para custo, cobertura e confiabilidade.
3. **Ações da auditoria desta sessão**: abrir pasta, abrir relatório, voltar ou sair, usando a mesma superfície do processamento normal.

Se um requisito for bloqueado por pré-requisito antes de qualquer chamada externa, a tentativa de reprocessamento pode ter custo de IA igual a zero. Os valores exibidos são estimativas técnicas persistidas pelos adapters, não invoice do provider.

O console usa o mesmo motor seletivo da CLI. Não existe uma segunda regra de reprocessamento para a interface interativa.

## Reprocessamento pela CLI

Comando principal:

```powershell
rasai audit reprocess AUD-XXXXXXXX --audits-root audits
```

Também é aceito:

```powershell
rasai reprocess AUD-XXXXXXXX --audits-root audits
```

Para consultar somente o estado atual:

```powershell
rasai audit reprocess AUD-XXXXXXXX --audits-root audits --status-only
```

Cada execução de recuperação recebe um identificador `RPR-*`. O `AUD-*` original permanece o identificador da observação.

## Regra de seleção

O reprocessamento não executa novamente um requisito que já possui resultado efetivo de sucesso. São elegíveis somente requisitos ainda não satisfeitos e que possam ser recuperados com segurança.

Exemplos:

- aquisição HTTP ou captura browser que não concluiu pode ser repetida dentro da janela de recuperação live;
- extração determinística pode ser repetida a partir do RAW ou DOM persistido sem nova requisição ao website;
- uma chamada de IA que falhou pode ser repetida usando a evidência efetiva da mesma auditoria;
- uma coleta PageSpeed ou CrUX bem-sucedida não é repetida apenas porque outro componente de Web Performance falhou;
- Synthetic Navigation Apdex coleta somente o déficit necessário de amostras válidas por contexto;
- Synthetic User Experience Apdex coleta somente o déficit necessário da população configurada;
- remediações por IA são reavaliadas quando uma nova resposta semântica efetiva altera os achados que servem de entrada.

Uma chamada sobre um `AUD-*` já completo é um no-op analítico: o estado atual é devolvido sem repetir serviços bem-sucedidos.

## Componentes opcionais solicitados na auditoria

Um recurso opcional deixa de ser opcional para o fulfillment quando o usuário o seleciona explicitamente na configuração daquela auditoria. Nesse caso ele passa a integrar o denominador obrigatório do `AUD-*` e precisa ter resultado efetivo antes de o relatório ser final e o AUD ser elegível para consolidação.

O contrato atual cobre explicitamente:

- `SEARCH_INTELLIGENCE`, quando termos SERP foram configurados no console da auditoria;
- `GOOGLE_SEARCH_CONSOLE`, quando o serviço foi explicitamente habilitado;
- `IMPROVEMENT_INTELLIGENCE`, quando a análise profunda por IA foi explicitamente habilitada;
- Synthetic Navigation Apdex e Synthetic User Experience Apdex, quando selecionados na configuração da execução.

Se um desses recursos foi solicitado, mas nenhuma execução correspondente foi materializada, o work-item permanece visível como `REQUESTED_NOT_EXECUTED`. Ausência de configuração obrigatória é diferenciada de falha de execução. Por exemplo, Google Search Console explicitamente solicitado sem `RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` permanece `NOT_CONFIGURED` com código `SITE_URL_REQUIRED`. Se a property existe, mas nenhuma forma OAuth está completa, o item também permanece `NOT_CONFIGURED` com diagnóstico de autenticação/configuração correspondente.

### Search Intelligence da auditoria

Search Intelligence solicitado no console pertence ao contrato daquele `AUD-*`. O RASAi persiste no work-item apenas parâmetros não secretos necessários para reproduzir a observação, como termos, profundidade, região, dispositivo, mercado, idioma, provider, engine, limites, timeout e política de retry.

Credenciais SERP não são copiadas para o work-item. No reprocessamento, a configuração não secreta original é reutilizada e a credencial é resolvida novamente a partir do ambiente atual.

Uma observação Search já concluída com sucesso não é executada outra vez porque outro componente falhou. Uma observação Search pendente pode ser repetida dentro da janela `LIVE_RECOLLECTION`. Se essa janela expirar, o AUD antigo não é atualizado com uma nova observação temporalmente incompatível; uma nova auditoria deve ser executada.

`SEARCH_MONITOR` do control plane SaaS permanece um job separado. A existência de monitoramento contínuo não transforma suas execuções em work-items da observação local `AUD-*`.

### Google Search Console

Google Search Console é tratado como `LIVE_RECOLLECTION`. O RASAi preserva a configuração não secreta original da property, limites da coleta e, quando aplicável, o OAuth Client ID. Segredos OAuth não são copiados para o work-item.

No momento da recuperação, a autenticação é resolvida novamente a partir do ambiente atual. O contrato aceita:

```text
CLIENT_ID + CLIENT_SECRET + REFRESH_TOKEN
```

ou, como alternativa temporária:

```text
ACCESS_TOKEN manual
```

No fluxo com Refresh Token, o access token é obtido imediatamente antes da chamada e permanece apenas em memória. Client Secret, Refresh Token e Access Token não são persistidos no `AUD-*`.

Se o work-item já possui sucesso efetivo e sua evidência persistida continua íntegra, o finalizador reutiliza os datasets existentes e não faz nova chamada à API. Se o item está pendente e ainda está dentro da janela temporal, somente esse requisito pode ser coletado novamente. Depois do vencimento da janela, nova coleta não promove o AUD antigo a resultado final.

### Análise profunda por IA

A análise profunda reutiliza a **seleção principal de IA** da configuração original da auditoria, junto dos domínios, limite de recomendações, timeout e idioma aplicáveis. Ela não possui provider, modelo ou reasoning especializados próprios.

Quando a seleção principal era explícita, o reprocessamento reaplica esse contrato sem persistir a credencial do provider. Quando a seleção era `AI=auto`, o reprocessamento reutiliza a política canônica de AUTO e resolve novamente os providers elegíveis/configurados no ambiente atual, preservando custo, quarentena, circuit breaker, fallback e limite de tentativas do runtime principal.

Quando uma execução anterior da análise profunda já concluiu com sucesso e sua evidência persistida continua íntegra, o reprocessamento reutiliza o resultado com `reused=true`; não faz uma segunda chamada paga apenas para regenerar o relatório.

Quando o work-item está pendente, a análise pode ser repetida sobre a evidência persistida da mesma observação. A tentativa de IA continua registrada pelo mecanismo normal de provider, incluindo tokens, custo estimado e versão de pricing. O reprocessamento não possui uma segunda camada de cobrança ou precificação.

### Custo, pricing e tentativas opcionais

O reprocessamento não recalcula o custo observado de tentativas históricas. Cada chamada já realizada conserva os tokens, custo estimado e versão de pricing que foram persistidos na execução correspondente.

Uma nova tentativa feita por um `RPR-*` usa o mesmo motor vigente de pricing e telemetria usado por uma execução normal. O custo adicional aparece como nova tentativa; ele não sobrescreve nem reprecifica a tentativa anterior.

A previsão de uma futura execução pode reutilizar consumo histórico e o catálogo de preços vigente para estimativa, mas isso é uma projeção separada e não altera o custo observado do AUD.

## Evidência core e integridade

Aquisição HTTP, captura do documento pelo browser e extração determinística são requisitos explícitos de processamento quando aplicáveis ao contexto auditado.

Há uma distinção obrigatória entre **falha de coleta** e **perda de evidência persistida**:

- se a aquisição ou captura não concluiu, o requisito permanece recuperável e pode ser tentado novamente como `LIVE_RECOLLECTION`, dentro da janela temporal configurada;
- se uma captura foi registrada como sucesso e o artifact persistido correspondente não está disponível, o requisito fica `BLOCKED`; o RASAi não substitui essa evidência por uma versão posterior do site;
- se existe RAW ou DOM persistido e apenas a extração falhou, a recuperação é `REPLAY_SAFE` e reutiliza exatamente a fonte armazenada.

O mesmo princípio vale para componentes opcionais: um work-item marcado como sucesso não é considerado íntegro se a evidência persistida que comprova esse resultado desapareceu. Nesse caso o status de sucesso é invalidado e a inconsistência aparece como falha de integridade, em vez de o RASAi assumir que o resultado ainda existe.

Quando uma recuperação core altera a evidência efetiva, somente os cálculos determinísticos e derivados dependentes são recalculados. As versões anteriores permanecem na trilha do `RPR-*`.

## Histórico de tentativas e motivo de falha

Falhas anteriores não são apagadas. O RASAi preserva tentativas para rastreabilidade operacional, cálculo de custo real, confiabilidade de provider, diagnóstico de erro e análise do caminho até a conclusão.

Uma tentativa que falhou não entra no resultado analítico quando uma tentativa posterior válida passa a ser o resultado efetivo daquele requisito.

Exemplo:

```text
AUD-ABC
  execução inicial -> CrUX falhou
  RPR-001          -> CrUX falhou novamente
  RPR-002          -> CrUX concluiu
```

Para o consolidado existe **uma observação**, `AUD-ABC`. Para custo e confiabilidade existem as tentativas efetivamente registradas.

### Preservação do diagnóstico específico

Um adapter de recuperação pode detectar um motivo mais preciso antes do fallback genérico do orquestrador. Exemplos:

- `WAITING_FOR_DATA` porque conteúdo/evidência mínima não existe;
- `BLOCKED` por perda de integridade de artifact persistido;
- `FAILED_RETRYABLE` com erro específico de provider ou serviço externo.

Esses estados e seus códigos/mensagens são autoritativos. O fallback genérico do reprocessamento não deve sobrescrevê-los por uma mensagem `*_RETRY_INCOMPLETE` quando já existe um diagnóstico mais específico desta avaliação.

Isso é especialmente importante para IA: ausência de pré-requisito não é falha de provider e não deve parecer uma tentativa de IA com erro. O console exibe o motivo efetivamente persistido para explicar por que o `RPR-*` não promoveu o AUD para `COMPLETE`.

Quando uma resposta de IA técnica chega ao RASAi, mas é rejeitada pelo contrato de evidência, a falha é classificada como erro de contrato da análise e permanece elegível para reprocessamento seletivo. O runtime não dispara uma segunda chamada paga imediata apenas para tentar corrigir automaticamente a resposta. Essa nova chamada só ocorre em um `RPR-*` explícito, depois que o operador decide reprocessar o requisito pendente.

### Duas trilhas de tentativa

O runtime mantém granularidades complementares:

- `audit_fulfillment_attempts` registra a avaliação operacional do work-item na execução inicial ou em um `RPR-*`;
- tabelas específicas de providers, PageSpeed/CrUX e medições sintéticas registram a operação externa ou medição concreta usada para diagnóstico, custo, confiabilidade e evidência técnica.

Uma avaliação de reprocessamento pode terminar como `WAITING_FOR_DATA` ou `BLOCKED` sem produzir tentativa de provider. Nesse caso existe rastreabilidade do work-item/RPR, mas não existe chamada de IA nem custo de provider.

## Concorrência de reprocessamento

O estado transitório usado para compor um `RPR-*` é isolado por contexto de execução. Duas auditorias reprocessadas simultaneamente não podem compartilhar `reprocess_id`, lista de pendências, filtros ou estado de outro `AUD-*`.

Os hooks instalados no processo permanecem estáveis; o contexto de cada execução é propagado isoladamente. Configurações não secretas restauradas para GSC e análise profunda usam overrides locais ao contexto e não alteram `os.environ` do processo. Isso evita que workers concorrentes compartilhem temporariamente parâmetros de outra auditoria.

O console preserva o contexto corrente ao executar o motor seletivo em sua projeção de progresso. Um sucesso efetivo pertence exclusivamente ao respectivo `AUD-*` e ao seu histórico de `RPR-*`.

## Dependências de IA

Nenhuma IA é chamada antes de existirem os dados mínimos persistidos necessários para a análise solicitada. Quando conteúdo, evidência ou contexto obrigatório ainda não está disponível, o requisito permanece aguardando dados e a chamada externa não é realizada.

No fluxo semântico, a chamada do provider também exige que os pré-requisitos determinísticos da página e do snapshot confirmem que o conteúdo é tecnicamente analisável. Falha ou estado inconclusivo dos pré-requisitos correspondentes impede a chamada externa. Esse estado é um bloqueio de pré-requisito, não uma falha do provider, portanto não gera tentativa nem custo de IA.

Se a extração falhou, mas o RAW ou DOM da observação está persistido, o reprocessamento executa novamente somente a extração e depois reavalia a elegibilidade da IA.

A recuperação semântica não faz uma requisição ao website por conta própria. Quando a fonte ainda não existe porque a captura falhou, o work-item de captura deve ser recuperado primeiro dentro da janela de `LIVE_RECOLLECTION`.

Se a captura havia sido registrada como sucesso e seu artifact persistido está ausente ou inconsistente, o RASAi não faz nova captura para substituir aquela evidência. Esse caso é perda de integridade, permanece bloqueado e exige uma nova auditoria para produzir outra observação válida.

## Consistência temporal

Requisitos são classificados conforme a origem da evidência:

- `REPLAY_SAFE`: podem ser reexecutados a partir dos dados já persistidos no próprio `AUD-*`;
- `LIVE_RECOLLECTION`: exigem nova consulta ao ambiente ou serviço externo.

Coletas `LIVE_RECOLLECTION` só podem promover a auditoria ao estado final dentro da janela configurada. Quando a janela expira, o `AUD-*` permanece fora da consolidação e uma nova auditoria deve ser executada para preservar coerência temporal.

A janela padrão é de 1440 minutos e pode ser ajustada por:

```text
RASAI_REPROCESS_LIVE_VALIDITY_MINUTES
```

O runtime aceita valores entre 1 e 10080 minutos.

A janela autoriza completar uma coleta que não obteve sucesso. Ela não autoriza substituir um artifact já persistido como evidência de uma coleta bem-sucedida.

## Recálculo de dados derivados

Quando uma nova tentativa altera a evidência efetiva, o RASAi invalida somente os dados derivados que dependem daquela evidência e os calcula novamente. Isso inclui regras determinísticas afetadas, score, contribuições, priorização e recomendações dependentes.

Os resultados substituídos permanecem disponíveis na trilha de reprocessamento. Relatórios públicos usam somente o estado efetivo atual.

## Status público

O diretório `report/` recebe `processing-status.json` com estado de processamento, score, relatório, elegibilidade para consolidação, quantidade de requisitos, tentativas e reprocessamentos.

Os HTMLs apresentam indicação explícita de estado preliminar ou final conforme o fulfillment efetivo.

## Consolidação

Um `AUD-*` só participa da consolidação quando `consolidation_eligible=true`.

Reexecuções não aumentam a quantidade de observações. O consolidado usa somente o resultado efetivo de sucesso de cada requisito. Tentativas com erro continuam disponíveis nas superfícies operacionais e de custo.

Essa regra impede que falhas transitórias de API, provider ou coleta distorçam SARI-001, SCORE-GEO-004, Apdex, Web Performance ou métricas temporais.

## Relação com reutilização de configuração

Reprocessar e reutilizar configuração são capacidades independentes:

```text
Reprocessar
AUD-123 -> RPR-001 -> continua AUD-123

Reutilizar configuração
AUD-123 -> carregar configuração -> executar -> novo AUD
```

Um AUD incompleto pode ser reprocessável e, simultaneamente, servir como fonte de configuração quando seu snapshot canônico está íntegro. Consulte [AUDIT_CONFIGURATION_REUSE.md](AUDIT_CONFIGURATION_REUSE.md).
