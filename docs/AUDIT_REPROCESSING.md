# Reprocessamento seletivo de auditorias

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

Ao terminar, o console apresenta:

```text
AUD
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

## Evidência core e integridade

Aquisição HTTP, captura do documento pelo browser e extração determinística são requisitos explícitos de processamento quando aplicáveis ao contexto auditado.

Há uma distinção obrigatória entre **falha de coleta** e **perda de evidência persistida**:

- se a aquisição ou captura não concluiu, o requisito permanece recuperável e pode ser tentado novamente como `LIVE_RECOLLECTION`, dentro da janela temporal configurada;
- se uma captura foi registrada como sucesso e o artifact persistido correspondente não está disponível, o requisito fica `BLOCKED`; o RASAi não substitui essa evidência por uma versão posterior do site;
- se existe RAW ou DOM persistido e apenas a extração falhou, a recuperação é `REPLAY_SAFE` e reutiliza exatamente a fonte armazenada.

Quando uma recuperação core altera a evidência efetiva, somente os cálculos determinísticos e derivados dependentes são recalculados. As versões anteriores permanecem na trilha do `RPR-*`.

## Histórico de tentativas

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

### Duas trilhas de tentativa

O runtime mantém granularidades complementares:

- `audit_fulfillment_attempts` registra a avaliação operacional do work-item na execução inicial ou em um `RPR-*`;
- tabelas específicas de providers, PageSpeed/CrUX e medições sintéticas registram a operação externa ou medição concreta usada para diagnóstico, custo, confiabilidade e evidência técnica.

Uma avaliação de reprocessamento pode terminar como `WAITING_FOR_DATA` ou `BLOCKED` sem produzir tentativa de provider. Nesse caso existe rastreabilidade do work-item/RPR, mas não existe chamada de IA nem custo de provider.

## Concorrência de reprocessamento

O estado transitório usado para compor um `RPR-*` é isolado por contexto de execução. Duas auditorias reprocessadas simultaneamente não podem compartilhar `reprocess_id`, lista de pendências, filtros ou estado de outro `AUD-*`.

Os hooks instalados no processo permanecem estáveis; o contexto de cada execução é propagado isoladamente. Um sucesso efetivo pertence exclusivamente ao respectivo `AUD-*` e ao seu histórico de `RPR-*`.

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
