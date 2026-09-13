# Reprocessamento seletivo de auditorias

O RASAi trata cada `AUD-*` como **uma única observação lógica**. Uma auditoria pode precisar de zero, uma ou várias reexecuções para satisfazer integralmente a configuração escolhida pelo usuário, sem transformar essas reexecuções em novas observações para histórico, tendência ou consolidação.

## Contrato de conclusão

A configuração original da auditoria define o universo obrigatório daquela execução. O estado final só é `FINAL` quando todos os requisitos obrigatórios e aplicáveis dessa configuração possuem um resultado efetivo de sucesso e continuam metodologicamente válidos.

Enquanto existir requisito pendente, recuperável, bloqueado ou fora da validade temporal:

- o processamento não é considerado concluído;
- o score final não é publicado como definitivo;
- o relatório é identificado como preliminar;
- o `AUD-*` não participa de relatórios consolidados, tendências, médias, percentis ou comparações históricas.

A existência física de todos os arquivos HTML não significa, por si só, que a auditoria atingiu o estado final.

## Reprocessamento

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

- aquisição HTTP ou captura browser que não concluiu na execução original pode ser repetida dentro da janela de recuperação live;
- extração determinística pode ser repetida a partir do RAW ou DOM persistido sem nova requisição ao website;
- uma chamada de IA que falhou pode ser repetida usando a evidência efetiva da mesma auditoria;
- uma coleta PageSpeed ou CrUX bem-sucedida não é repetida apenas porque outro componente de Web Performance falhou;
- Synthetic Navigation Apdex coleta somente o déficit necessário de amostras válidas por contexto;
- Synthetic User Experience Apdex coleta somente o déficit necessário da população configurada;
- remediações por IA são reavaliadas quando uma nova resposta semântica efetiva altera os achados que servem de entrada.

## Evidência core e integridade

Aquisição HTTP, captura do documento pelo browser e extração determinística são requisitos explícitos de processamento quando aplicáveis ao contexto auditado.

Há uma distinção obrigatória entre **falha de coleta** e **perda de evidência persistida**:

- se a aquisição ou a captura não concluiu na execução original, o requisito permanece recuperável e pode ser tentado novamente como `LIVE_RECOLLECTION`, dentro da janela temporal configurada;
- se uma captura foi registrada como sucesso e o artifact persistido correspondente depois não está disponível, o requisito fica `BLOCKED`; o RASAi não substitui essa evidência por uma versão posterior do site;
- se existe RAW ou DOM persistido e apenas a extração falhou, a recuperação é `REPLAY_SAFE` e reutiliza exatamente a fonte já armazenada.

Quando uma recuperação core altera a evidência efetiva, somente os cálculos determinísticos e derivados dependentes são recalculados. As versões anteriores permanecem no histórico do `RPR-*`.

## Histórico de tentativas

Falhas anteriores não são apagadas. O RASAi preserva as tentativas para rastreabilidade operacional, cálculo de custo real, confiabilidade de provider, diagnóstico de erro e tempo necessário até a conclusão.

Uma tentativa que falhou não entra no cálculo do resultado analítico quando uma tentativa posterior válida passa a ser o resultado efetivo daquele requisito.

Exemplo conceitual:

```text
AUD-ABC
  tentativa inicial -> CrUX falhou
  RPR-001           -> CrUX falhou novamente
  RPR-002           -> CrUX concluiu
```

Para o relatório consolidado existe **uma observação**, `AUD-ABC`. Para custo e confiabilidade existem três tentativas registradas.

### Duas trilhas de tentativa

O runtime mantém duas granularidades complementares e elas não devem ser confundidas:

- `audit_fulfillment_attempts` registra a avaliação operacional do work-item dentro da execução inicial ou de um `RPR-*`; é a trilha comum entre componentes e permite saber quantas vezes um requisito foi efetivamente processado;
- tabelas específicas, como tentativas de providers de IA, PageSpeed/CrUX e amostras sintéticas, registram a operação externa ou medição concreta usada para diagnóstico, custo, confiabilidade e evidência técnica.

Uma avaliação de reprocessamento pode terminar como `WAITING_FOR_DATA` ou `BLOCKED` sem produzir tentativa de provider. Nesses casos existe rastreabilidade do work-item/RPR, mas **não existe chamada de IA nem custo de provider**.

## Concorrência de reprocessamento

O estado transitório usado para compor um `RPR-*` é isolado por contexto de execução. O RASAi não troca funções globais por execução para selecionar itens pendentes, reutilizar um `RPR-*` ou filtrar snapshots já concluídos.

Isso é obrigatório no worker/SaaS: duas auditorias reprocessadas simultaneamente não podem compartilhar `reprocess_id`, lista de pendências, filtro de Content Remediation nem estado de outro `AUD-*`.

Os hooks instalados no processo permanecem estáveis; o contexto específico de cada execução é propagado isoladamente. Assim, concorrência não altera a regra de que um sucesso efetivo pertence exclusivamente ao respectivo `AUD-*` e ao seu histórico de `RPR-*`.

## Dependências de IA

Nenhuma IA é chamada antes de existirem os dados mínimos persistidos necessários para a análise solicitada. Quando conteúdo, evidência ou contexto obrigatório ainda não está disponível, o requisito permanece aguardando dados e a chamada externa não é realizada.

No fluxo semântico, a chamada do provider também exige que os pré-requisitos determinísticos da página e do snapshot confirmem que o conteúdo é tecnicamente analisável. Em particular, falha ou estado inconclusivo de `BR-GEO-009` ou `BR-GEO-020` impede a chamada externa. Esse estado é um bloqueio de pré-requisito, não uma falha do provider, portanto não gera tentativa nem custo de IA.

Se a extração falhou, mas o RAW ou DOM daquela observação está persistido, o reprocessamento executa novamente somente a extração e depois reavalia a elegibilidade da IA.

A recuperação semântica não faz uma requisição ao website por conta própria. Quando a fonte ainda não existe porque a **captura original falhou**, o work-item de captura core deve ser recuperado primeiro, dentro da janela de `LIVE_RECOLLECTION`. Somente depois de a nova captura ter sido persistida e os pré-requisitos determinísticos passarem a IA se torna elegível.

Se a captura havia sido registrada como sucesso e seu artifact persistido está ausente ou inconsistente, o RASAi não faz uma nova captura para substituir aquela evidência. Esse caso é perda de integridade, permanece bloqueado e exige uma nova auditoria para produzir uma observação válida.

Essa regra evita custo sem utilidade, respostas sem base suficiente e tentativas que não poderiam produzir resultado válido.

## Consistência temporal

Requisitos são classificados de acordo com a origem da evidência:

- `REPLAY_SAFE`: podem ser reexecutados a partir dos dados já persistidos no próprio `AUD-*`, como extração sobre RAW/DOM persistido ou nova análise de IA sobre o conteúdo efetivo da auditoria;
- `LIVE_RECOLLECTION`: exigem nova consulta ao ambiente ou serviço externo, como aquisição HTTP/captura que não concluiu, PageSpeed, CrUX e medições sintéticas.

Coletas `LIVE_RECOLLECTION` só podem promover a auditoria ao estado final dentro da janela de recuperação configurada. Quando essa janela expira, o `AUD-*` permanece fora da consolidação e uma nova auditoria deve ser executada para preservar coerência temporal entre as evidências.

A janela padrão é de 1440 minutos e pode ser ajustada por:

```text
RASAI_REPROCESS_LIVE_VALIDITY_MINUTES
```

O valor aceito é limitado pelo runtime entre 1 minuto e 10080 minutos.

A janela de `LIVE_RECOLLECTION` autoriza completar uma coleta que não obteve sucesso; ela não autoriza substituir um artifact que já havia sido persistido como evidência de uma coleta bem-sucedida.

## Recálculo de dados derivados

Quando uma nova tentativa altera a evidência efetiva, o RASAi invalida somente os dados derivados que dependem daquela evidência e os calcula novamente. Isso inclui regras determinísticas afetadas, score, contribuições, priorização e recomendações dependentes.

Os resultados anteriores substituídos são preservados no histórico de reprocessamento para auditoria. Relatórios públicos usam somente o estado efetivo atual.

## Status público

O diretório `report/` recebe `processing-status.json` com o estado de processamento, score, relatório, elegibilidade para consolidação, quantidade de requisitos, tentativas e reprocessamentos.

Os HTMLs exibem uma indicação explícita:

- **Relatório preliminar - score final ainda não definido**, enquanto algum requisito obrigatório não estiver atendido;
- **Processamento concluído - relatório final**, quando todo o contrato original estiver satisfeito e válido.

## Consolidação

Um `AUD-*` só pode participar da consolidação quando `consolidation_eligible=true`.

Reexecuções não aumentam a quantidade de observações. O consolidado usa somente o resultado efetivo de sucesso de cada requisito. Tentativas com erro continuam disponíveis apenas nas superfícies operacionais e de custo.

Essa regra impede que falhas transitórias de API, provider ou coleta distorçam SARI-001, SCORE-GEO-004, Apdex, Web Performance ou métricas temporais.
