# Reprocessamento seletivo de auditorias

O RASAi está em desenvolvimento e ainda não foi publicado. Este documento descreve somente o contrato atual do produto.

O RASAi trata cada `AUD-*` como **uma única observação lógica**. Uma auditoria pode precisar de zero, uma ou várias reexecuções para satisfazer integralmente a configuração escolhida pelo usuário, sem transformar essas reexecuções em novas observações para histórico, tendência ou consolidação.

## Contrato de conclusão

A configuração original da auditoria define o universo obrigatório daquela execução. O estado final só é `FINAL` quando todos os requisitos obrigatórios e aplicáveis dessa configuração possuem um resultado efetivo de sucesso e continuam metodologicamente válidos.

Enquanto existir requisito pendente, recuperável, bloqueado ou fora da validade temporal:

- o processamento não é considerado concluído;
- o score final não é publicado como definitivo;
- o relatório é identificado como preliminar;
- o `AUD-*` não pode ser tratado como fonte conclusiva nem contribuir silenciosamente como observação final; quando um CONS o inclui para transparência histórica, a série deve ser marcada como **não conclusiva**, expor a pendência e recomendar reprocessamento quando aplicável.

A existência física dos arquivos HTML não significa, por si só, que a auditoria atingiu o estado final.

## Retomada após interrupção operacional

Interrupção de processo não cria uma nova observação. Quando a execução original termina por `Ctrl+C`, fechamento do terminal, encerramento abrupto do processo, reboot, falha transitória de rede/provider ou situação equivalente, o RASAi retoma a partir do **último checkpoint durável e validado**.

A semântica é:

```text
AUD-ABC
  execução inicial interrompida
  RPR-001 -> retomada seletiva da mesma observação
```

O runtime não tenta restaurar a pilha Python nem continuar uma instrução de memória. Antes da primeira coleta significativa, a execução grava no contrato de fulfillment um plano `AUDIT-RESUME-001` sem secrets, contendo o universo mínimo necessário para reconstruir a intenção original, como targets, tipo do alvo, idioma, mercado, limite de páginas, contexto de dispositivo e flags de remediação. A configuração reutilizável canônica também é persistida antecipadamente quando estiver disponível.

Cada execução local de uma AUD mantém uma sessão durável em `audit_execution_sessions` com identidade de execução, PID, host, início e heartbeat. Uma retomada é recusada enquanto existir sessão comprovadamente ativa. Sessões cujo processo local não existe mais, ou cujo heartbeat remoto expirou, são registradas como `INTERRUPTED` antes do novo RPR. O lifecycle de negócio pode ter permanecido em `DISCOVERING`, `ANALYZING`, `SCORING` etc.; por isso esses rótulos, isoladamente, não provam que existe processo vivo.

### Reconciliação de tentativa abandonada

Um work-item que ficou `RUNNING` não é repetido automaticamente. Na abertura do RPR, a tentativa órfã é fechada como `INTERRUPTED` e o item volta a estado recuperável. Em seguida, os sincronizadores de cada componente confrontam o ledger com a evidência efetiva:

- se o resultado completo já foi persistido antes da queda, o item é reconciliado para `SUCCESS` sem nova chamada;
- se não existe resultado efetivo suficiente, somente o déficit é executado;
- se havia sucesso declarado mas o artifact correspondente desapareceu, o item fica `BLOCKED`; uma coleta atual não substitui silenciosamente evidência histórica perdida.

A descoberta/aquisição inicial possui checkpoint próprio `DISCOVERY_ACQUISITION`. Se a interrupção ocorrer antes de esse checkpoint concluir, o RPR trata essa etapa como live e respeita a mesma janela temporal das demais coletas. Persistência parcial da descoberta/aquisição inicial é arquivada na trilha do RPR antes de qualquer replay; se já existir evidência downstream incompatível com essa limpeza isolada, a recuperação é bloqueada em vez de apagar dados relacionados.

Para renderização, o plano antecipado permite detectar um contexto configurado que nunca chegou a materializar um `PageSnapshot`. O RPR cria somente o contexto ausente e, depois, a extração/derivados correspondentes. Contextos já concluídos permanecem intactos.

O plano também preserva a intenção efetiva de componentes opcionais que podem executar depois do core. No CLI direto isso inclui, quando aplicável, Web Performance, Synthetic Navigation Apdex, Synthetic User Experience Apdex e Search Intelligence, além de um snapshot whitelist de parâmetros não secretos usados por Improvement Intelligence, Google Search Console e Segurança Passiva. API keys, tokens OAuth, senhas e demais secrets não entram nesse contrato. Se a queda ocorrer antes de o componente criar sua própria tabela/run/work-item, o backfill materializa o requisito como `REQUESTED_NOT_EXECUTED` e o RPR continua a fila a partir dessa intenção persistida.

A retomada conserva as regras já existentes para Web Performance, Synthetic Navigation Apdex, Synthetic User Experience Apdex e IA: amostras e chamadas válidas são preservadas, Apdex coleta apenas déficit e IA só volta à fila quando está pendente ou quando uma mudança material de evidência invalida especificamente sua dependência. Quando Apdex/experiência estavam configurados mas ainda não possuíam run persistido, o primeiro RPR materializa a execução inicial desse requisito a partir do plano original; tentativas posteriores continuam usando apenas o déficit.

### Finalização da mesma AUD

`CORE_AUDIT` não é mais classificado como bloqueio permanente apenas porque `audits.status` não é `COMPLETED`. Uma AUD interrompida torna-se `FAILED_RETRYABLE` somente quando existe base durável suficiente para uma recuperação segura. Auditorias antigas sem plano explícito usam backfill conservador baseado em evidência persistida; quando o contrato original não pode ser provado, permanecem bloqueadas e o RASAi não inventa configuração ausente.

Depois que todos os requisitos obrigatórios aplicáveis estão resolvidos, o RPR recompõe somente derivados faltantes/afetados, promove `CORE_AUDIT` e conclui **o mesmo `AUD-*`**. Se a execução caiu durante scoring ou recomendações antes do checkpoint `CORE_AUDIT`, a existência de um score parcial não é aceita como prova de finalização: os derivados finais replay-safe são reconstruídos a partir do conjunto efetivo persistido antes da promoção para `COMPLETE`. O fato histórico da interrupção e as tentativas anteriores continuam auditáveis. A projeção HTML é rematerializada depois do fechamento lógico do RPR e depois do encerramento da sessão mutável da execução. Isso evita que o próprio update final do lease altere o `audit.db` após o fingerprint do `report-catalog/` ter sido calculado.

## Reprocessamento pelo console interativo

O caminho normal para um operador local é:

```text
rasai-console
> Auditorias / histórico
> selecionar AUD-*
> Reprocessar pendências desta auditoria
```

Antes de iniciar, o console apresenta o contexto e as escolhas já realizadas. Cada etapa substitui a tela anterior e mantém um resumo compacto no topo:

- situação atual do `AUD-*`;
- requisitos atendidos;
- itens ainda recuperáveis ou bloqueados;
- uma única seleção de escopo da tentativa: `T` para todos, números separados por vírgula ou `V` para voltar;
- uma única decisão final de modo: `1` para reprocessar com IA quando aplicável, `2` para reprocessar sem IA ou `V` para voltar;
- sucessos que serão preservados;
- itens `DISABLED` ou `NOT_APPLICABLE` fora da fila de reprocessamento;
- motivo persistido das pendências quando disponível;
- prévia de custo de IA direta quando houver requisito de IA pendente;
- aviso de IA condicional quando uma pendência sem IA puder alterar evidência consumida por análises dependentes.

### Prévia financeira e ação final

A prévia de custo do reprocessamento usa o mesmo histórico e o mesmo catálogo canônico de pricing da execução normal. Quando já existem requisitos de IA diretamente pendentes, a estimativa monetária considera somente essa parcela; sucessos preservados, itens desabilitados e itens não aplicáveis não entram como nova carga.

Uma pendência atual **sem IA** pode, porém, alterar evidência persistida. Nessa situação, o grafo de dependências só pode determinar depois da recuperação quais resultados de IA ficaram obsoletos. O console não deve prometer custo zero: apresenta `IA CONDICIONAL` e identifica as superfícies que podem exigir nova análise. Exemplos vigentes incluem CAT-08 e Análise Direcionada quando a evidência consumida por elas muda; CAT-09 só volta à fila quando a mudança atinge a dependência semântica/técnica de suas remediações assistidas por IA.

Quando existe histórico monetário comparável para trabalho de IA já conhecido, o console mostra custo esperado, faixa provável, cenário potencial e confiança. Quando a necessidade de IA ainda depende do resultado da recuperação, o valor monetário é declarado não determinável antecipadamente. O RASAi não inventa quantidade futura de chamadas, tokens ou preço ausente.

Depois da seleção do escopo, a própria escolha do modo é a autorização final da tentativa não destrutiva:

```text
1. Reprocessar itens selecionados com IA quando aplicável
2. Reprocessar itens selecionados sem IA
V. Voltar
```

A prévia de custo é recalculada para o escopo selecionado antes dessa escolha. Não existe uma segunda tela `Confirmar e iniciar reprocessamento`, porque ela apenas repetiria a intenção já expressa. `V` retorna sem executar e preserva as escolhas anteriores válidas.

A autorização de IA vale **somente para os itens selecionados nesta tentativa**. Escolher “com IA” não inclui automaticamente outra pendência que o operador deixou fora do escopo. Quando nenhum item selecionado usa IA, o console informa que a opção com IA não produz efeito naquele escopo. No resultado final, pendências não selecionadas são marcadas como `NÃO SELECIONADO` e o motivo exibido é identificado como estado persistido anterior, evitando confundir uma pendência não tentada com falha da tentativa corrente.

### Acompanhamento durante a execução

Depois da escolha final do modo, **processar e reprocessar usam a mesma superfície operacional do console**. O reprocessamento não possui uma segunda tela de execução com outra disposição de informações.

Enquanto o `RPR-*` está ativo, processamento e reprocessamento chamam o mesmo renderer canônico de execução ao vivo. A estrutura exibida é:

```text
Status / URL / Dispositivo / Operação / tempo
Etapa        : X de Y
Anterior     : etapa anterior
Atual        : etapa corrente
Próxima      : etapa seguinte ou condicional
Andamento    : percentual da etapa quando medido
Pipeline     : projeção/medição do total
Executando   : atividade corrente

Audit ID / RPR / Log técnico
```

O reprocessamento acrescenta apenas o título `REPROCESSAMENTO EM EXECUÇÃO`; não mantém uma implementação paralela dessa tela.

A diferença está somente no conteúdo da etapa. No reprocessamento, a superfície separa **sucessos preservados**, **selecionados nesta tentativa**, **resolvidos neste RPR**, **em execução** e **restantes**. O requisito/scope atual e a quantidade avaliada aparecem nos detalhes da etapa. Dados preservados nunca são apresentados como se tivessem sido reprocessados.

A superfície é atualizada periodicamente durante o `RPR-*`; chamadas externas longas não devem deixar o operador sem indicação visível de que o trabalho continua em andamento.

A previsão seletiva aparece antes da escolha final do modo. Durante etapas de IA podem ser mostrados provider/modelo e telemetria já observável sem inventar custo futuro; o resumo final separa custo desta tentativa e custo acumulado do AUD. Valores derivados de tokens e pricing conhecido são estimativas técnicas, não invoice do provider.

A apresentação é atualizada por leitura do estado persistido dos work-items. Essa projeção não cria outro motor de reprocessamento e não altera as regras de seleção, retry, quarentena, provider ou custo.

A sequência operacional do RPR é apresentada como `Preparando reprocessamento -> Executando requisitos selecionados -> Gerando relatório -> Validação e conclusão`. A etapa **Gerando relatório** consolida resultados/evidências já persistidos e materializa HTML/artefatos; ela não repete sucessos preservados nem abre uma coleta apenas para alimentar a apresentação.

### Resumo, custos e ações ao terminar

Ao terminar, o console fecha a execução com a mesma estrutura operacional do processamento normal e mantém o resultado do reprocessamento na própria superfície final, sem depender de um `ENTER` intermediário para revelar as ações disponíveis.

São mostrados os dados específicos do `RPR-*`:

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

Em seguida aparecem os custos no mesmo contexto de pós-execução:

1. **Consumo desta tentativa de reprocessamento**: diferença entre a telemetria persistida antes e depois do `RPR-*`, incluindo novas tentativas de IA, tokens, custo estimado e novas chamadas Web Performance.
2. **Consumo e cobertura real persistidos do AUD**: reutiliza exatamente o renderer padrão já usado após uma execução normal, preservando todas as tentativas anteriores para custo, cobertura e confiabilidade.
3. **Ações do reprocessamento**: `R` para tentar novamente somente pendências ainda recuperáveis, `P` para abrir a pasta, `I` para abrir o relatório HTML e `V` para voltar à auditoria selecionada. A saída global permanece no menu `INÍCIO`.

A ação `R` só fica operacional quando permanece ao menos um work-item obrigatório, aplicável e `retryable`. Ao escolhê-la, o console volta para `PREPARAR REPROCESSAMENTO`, recalcula escopo e prévia de custo sobre o estado atual e exige nova escolha explícita de modo com IA/sem IA. Quando restam apenas bloqueios definitivos, itens não aplicáveis ou itens sem retry automático, um novo reprocessamento direto não é oferecido como ação válida.

A mesma ação `R. Reprocessar pendências desta auditoria` também aparece imediatamente na tela pós-execução de uma AUD parcial. Nesse caso o console reutiliza automaticamente o `Audit ID` recém-gerado; o operador não precisa pesquisar ou informar novamente o identificador.

Se um requisito for bloqueado por pré-requisito antes de qualquer chamada externa, a tentativa de reprocessamento pode ter custo de IA igual a zero. Os valores exibidos são estimativas técnicas persistidas pelos adapters, não invoice do provider.

O console usa o mesmo motor seletivo da CLI. Não existe uma segunda regra de reprocessamento para a interface interativa.

O roteiro operacional de validação manual no Windows está em [REPROCESSING_HUMAN_SMOKE.md](REPROCESSING_HUMAN_SMOKE.md).

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

Para reproduzir exatamente a seleção feita no console, a CLI também aceita `--item` repetido com a chave canônica `COMPONENTE::ESCOPO`, além de `--use-ai|--no-use-ai` e dos overrides `--ai-provider`, `--ai-model` e `--ai-reasoning` quando IA é autorizada.

No console, depois de selecionar os itens, a ação final escolhe reprocessar com IA ou sem IA e inicia a tentativa sem confirmação duplicada. O comando efetivamente executado é registrado e `M. Ver linha de comando` permanece disponível após a tentativa. O log humano correspondente é secret-free e fica fora do workspace da AUD.

Uso em Agendador de Tarefas, cron, systemd timer ou launchd, incluindo a regra de `**********` para secrets e override apenas do processo, está em [EXECUTION_SCHEDULING.md](EXECUTION_SCHEDULING.md).

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

### Mudança material e invalidação de dependências

Uma tentativa de reprocessamento, por si só, não cria uma nova versão analítica da evidência. Antes e depois das recuperações elegíveis, o runtime compara um fingerprint material dos resultados persistidos que alimentam análise e relatório.

Não constituem mudança material isoladamente:

- timestamp de tentativa;
- atualização do ledger operacional;
- nova mensagem transitória de erro sem mudança do resultado efetivo;
- abertura de um `RPR-*` que não produziu novo dado.

Constituem mudança material, quando aplicável:

- nova observação/medição efetiva;
- alteração do estado analítico de uma coleta;
- novo dataset observacional ou artifact com conteúdo diferente;
- recuperação de HTTP, render ou extração que substitui a evidência efetiva;
- alteração de inventário ou resultado derivado persistido.

Sem mudança material e sem mudança nos IDs de evidência, o RASAi reutiliza o snapshot de evidência anterior. Tarefas de IA e derivados já concluídos permanecem válidos e não entram novamente na fila.

Quando a mudança material afeta uma dependência, somente o work-item ou tarefa dependente é invalidado. A decisão usa a fatia de evidência realmente consumida por aquela finalidade, e não apenas o fato de existir uma nova versão global de evidência. Assim, por exemplo, recuperar PageSpeed/Lighthouse não deve invalidar uma análise semântica de conteúdo se a medição recuperada não fazia parte da entrada consumida por essa tarefa.

Uma tarefa de IA marcada como `STALE` não volta a sucesso apenas porque ainda existem tentativas ou assessments antigos persistidos. Esses registros continuam válidos como histórico, mas a tarefa precisa ser revalidada ou reprocessada para a dependência vigente.

O resultado anterior conserva `last_success_at`, `effective_result_ref` e tentativas. Resultados derivados substituídos de Improvement Intelligence e Análise Direcionada são copiados para `audit_reprocess_derived_archive` antes da nova materialização, vinculados ao `RPR-*`; a nova execução passa a ser a versão efetiva apenas depois de concluída.

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

A análise profunda não possui um segundo motor/provider especializado. Na execução inicial, usa a seleção principal de IA da AUD. Em um `RPR-*`, usa a política de IA autorizada especificamente para aquele reprocessamento (`use_ai`, `ai_provider`, `ai_model`, `ai_reasoning`) quando fornecida, sem reescrever a configuração histórica da AUD.

Se o RPR não fornecer política própria, permanece compatível com a seleção efetiva persistida da AUD. Se o RPR selecionar `AUTO`, a política canônica resolve novamente os providers elegíveis/configurados no ambiente atual, preservando custo, quarentena, circuit breaker, fallback e limite de tentativas do runtime principal. Credenciais nunca são persistidas no `RPR-*`.

Quando uma execução anterior da análise profunda já concluiu com sucesso e sua evidência persistida continua íntegra, o reprocessamento reutiliza o resultado com `reused=true`; não faz uma segunda chamada paga apenas para regenerar o relatório.

Quando o work-item está pendente, a análise pode ser repetida sobre a evidência persistida da mesma observação. A tentativa de IA continua registrada pelo mecanismo normal de provider, incluindo tokens, custo estimado e versão de pricing. O reprocessamento não possui uma segunda camada de cobrança ou precificação.

### Custo, pricing e tentativas opcionais

O reprocessamento não recalcula o custo observado de tentativas históricas. Cada chamada já realizada conserva os tokens, custo estimado e versão de pricing que foram persistidos na execução correspondente.

Uma nova tentativa feita por um `RPR-*` usa o mesmo motor vigente de pricing e telemetria usado por uma execução normal. O custo adicional aparece como nova tentativa; ele não sobrescreve nem reprecifica a tentativa anterior.

Antes de um `RPR-*`, o console separa IA diretamente pendente de IA potencialmente invalidável por mudança de evidência. Para trabalho de IA já conhecido, pode projetar estimativa monetária seletiva a partir do histórico comparável e do catálogo vigente. Para pendências sem IA que possam modificar evidência, informa IA condicional e não garante custo zero antes da recuperação. Essa projeção é independente do custo observado e pode ser declarada não estimável quando a base histórica ou o próprio conjunto futuro de chamadas ainda não estiver determinado.

## Evidência core e integridade

Aquisição HTTP, captura do documento pelo browser e extração determinística são requisitos explícitos de processamento quando aplicáveis ao contexto auditado.

Há uma distinção obrigatória entre **falha de coleta** e **perda de evidência persistida**:

- se a aquisição ou captura não concluiu, o requisito permanece recuperável e pode ser tentado novamente como `LIVE_RECOLLECTION`, dentro da janela temporal configurada;
- se uma captura foi registrada como sucesso e o artifact persistido correspondente não está disponível, o requisito fica `BLOCKED`; o RASAi não substitui essa evidência por uma versão posterior do site;
- se existe RAW ou DOM persistido e apenas a extração falhou, a recuperação é `REPLAY_SAFE` e reutiliza exatamente a fonte armazenada.

O mesmo princípio vale para componentes opcionais: um work-item marcado como sucesso não é considerado íntegro se a evidência persistida que comprova esse resultado desapareceu. Nesse caso o status de sucesso é invalidado e a inconsistência aparece como falha de integridade, em vez de o RASAi assumir que o resultado ainda existe.

Quando uma recuperação core altera a evidência efetiva, somente os cálculos determinísticos e derivados dependentes são recalculados. As versões anteriores permanecem na trilha do `RPR-*`.

A validação de integridade pré-RPR também confronta o estado `SUCCESS` com o resultado persistido de Search Intelligence, Google Search Console, Improvement Intelligence, Web Performance, Synthetic Navigation Apdex, Synthetic User Experience Apdex e Segurança passiva. Se o resultado que comprovava um sucesso não existe mais ou está estruturalmente inconsistente, o item fica `BLOCKED` e não é recolhido automaticamente para simular a evidência histórica perdida.

### Segurança passiva no reprocessamento

CAT-10 consome HTTP, headers, HTML bruto/renderizado, runtime e inventário de recursos já persistidos. Por isso, um CAT-10 concluído **não** é reexecutado quando o RPR trata somente PageSpeed, Search, GSC, Apdex ou outro requisito independente.

Se HTTP, render ou extração core forem recuperados e alterarem a entrada efetiva do CAT-10:

1. somente o work-item `PASSIVE_SECURITY` é reaberto por dependência;
2. o estado CAT-10 anterior é arquivado na trilha do `RPR-*`;
3. recursos, componentes, findings e remediações são recalculados a partir da evidência efetiva;
4. advisories OSV/KEV continuam reutilizados quando os mesmos componentes/versionamentos permanecem válidos;
5. OSV/KEV só são consultados novamente quando o inventário de componentes/versionamento realmente mudou e a configuração congelada da AUD mantém essas fontes habilitadas.

A configuração usada nesse recálculo vem do contrato não secreto persistido da própria auditoria. O RPR não adota silenciosamente toggles CAT-10 diferentes apenas porque o ambiente atual mudou.

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

O estado de processamento, score, elegibilidade para consolidação, quantidade de requisitos, tentativas e reprocessamentos permanece persistido no contrato de fulfillment. `report/processing-status.json` não integra o contrato de saída de `rasai audit`.

`report-catalog/` continua projetando o estado efetivo persistido, inclusive condição preliminar/final quando aplicável.

Quando um `RPR-*` efetivamente executa trabalho, a projeção final de `report-catalog/` ocorre somente depois de o ledger `audit_reprocess_runs` estar encerrado com seu status, contadores e `completed_at` definitivos. O snapshot e o fingerprint do relatório devem representar o estado final do `audit.db`; não é válido selar o pacote enquanto o próprio RPR ainda está `RUNNING`.

## Consolidação

Uma AUD com `consolidation_eligible=true` e fulfillment final participa como fonte conclusiva. Uma AUD fisicamente encerrada com `status=COMPLETED`, mas ainda sem fulfillment final, pode ser incluída pelo consolidador somente para transparência histórica; nesse caso `CONSOLIDATED-SOURCE-GOVERNANCE-003` marca a série como `NON_CONCLUSIVE`, a pendência permanece visível e a fonte não é promovida a observação final equivalente às AUDs elegíveis.

Reexecuções não aumentam a quantidade de observações. O consolidado usa somente o resultado efetivo de sucesso de cada requisito. Tentativas com erro continuam disponíveis nas superfícies operacionais e de custo.

Para preservar cronologia, o CONS distingue a data semântica da observação da data de revisão por RPR. Um RPR material posterior pode alterar a revisão lógica da mesma AUD sem criar uma nova observação. A governança longitudinal registra `source_revision_id`, `revision_at` e `revision_mode`: `REPLAY_SAFE` reutiliza a evidência persistida do marco original; `LIVE_RECOLLECTION` indica que houve nova coleta e exige qualificação quando a revisão ocorreu depois do próximo marco temporal. RPR sem item materialmente resolvido não é tratado como nova revisão temporal.

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

## Política própria do RPR

Cada `RPR-*` possui uma autorização própria de execução. O conjunto de pendências existentes na AUD não é automaticamente o conjunto executado pelo RPR.

O operador pode selecionar itens específicos e decidir separadamente se IA será usada naquele reprocessamento. A política durável, sem segredos, registra `selected_items`, `use_ai`, `ai_provider`, `ai_model` e `ai_reasoning`; ao final, o mesmo registro recebe `ai_used`, distinguindo autorização de uma tentativa efetiva de provider.

Essa política não sobrescreve o snapshot original da AUD. Assim, uma AUD originalmente sem IA pode usar IA em um RPR, e uma AUD originalmente com IA pode executar um RPR apenas de integração com `use_ai=false`.

Na preparação do RPR, o console separa explicitamente:

- **Configuração original da AUD**: snapshot histórico preservado como provenance;
- **IA atual da sessão**: provider/modelo atualmente configurados no console e usados para prever esta nova tentativa;
- **Política deste RPR**: `S` usa a configuração atual da sessão quando aplicável; `N`/ENTER executa sem IA.

Consequentemente, uma AUD criada com `provider=none` pode ser reprocessada com a sessão atual em `AUTO` sem reescrever a configuração original.

Quando integração e IA dependente são selecionadas juntas, a integração é executada e validada primeiro. Se o pré-requisito continuar incompleto, a IA permanece `WAITING_FOR_DATA`, sem chamada de provider, tokens ou custo.

O status operacional do RPR também é separado do fechamento lógico da AUD: um RPR pode concluir sua execução, resolver parte dos itens e deixar a AUD em `PARTIAL_RETRYABLE`. Itens não selecionados continuam pendentes sem serem classificados como falha daquela execução.

Consulte [PARTIAL_DIAGNOSTIC_EXECUTION.md](PARTIAL_DIAGNOSTIC_EXECUTION.md).
