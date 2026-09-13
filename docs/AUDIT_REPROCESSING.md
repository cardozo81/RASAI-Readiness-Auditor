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

- uma chamada de IA que falhou pode ser repetida usando a evidência persistida da mesma auditoria;
- uma coleta PageSpeed ou CrUX bem-sucedida não é repetida apenas porque outro componente de Web Performance falhou;
- Synthetic Navigation Apdex coleta somente o déficit necessário de amostras válidas por contexto;
- Synthetic User Experience Apdex coleta somente o déficit necessário da população configurada;
- remediações por IA são reavaliadas quando uma nova resposta semântica efetiva altera os achados que servem de entrada.

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

## Dependências de IA

Nenhuma IA é chamada antes de existirem os dados mínimos persistidos necessários para a análise solicitada. Quando conteúdo, evidência ou contexto obrigatório ainda não está disponível, o requisito permanece aguardando dados e a chamada externa não é realizada.

No fluxo semântico, a chamada do provider também exige que os pré-requisitos determinísticos da página e do snapshot confirmem que o conteúdo é tecnicamente analisável. Em particular, falha ou estado inconclusivo de `BR-GEO-009` ou `BR-GEO-020` impede a chamada externa. Esse estado é um bloqueio de pré-requisito, não uma falha do provider, portanto não gera tentativa nem custo de IA.

Se a extração original falhou, mas o RAW ou DOM renderizado daquela mesma observação foi preservado, o reprocessamento pode executar novamente apenas a extração sobre esse artifact persistido e, depois, reavaliar a elegibilidade da IA. Isso é `REPLAY_SAFE`: não existe nova requisição ao website para fabricar uma fonte semântica diferente dentro do AUD antigo.

Se o RAW e o DOM originais necessários à análise semântica não foram preservados, o RASAi não faz uma captura tardia para completar artificialmente o mesmo `AUD-*`. O requisito fica bloqueado e deve ser criada uma nova auditoria. HTML/DOM que fundamenta a análise semântica é evidência de origem da observação e não pode ser substituído por uma versão posterior do site.

Essa regra evita custo sem utilidade, respostas sem base suficiente e tentativas que não poderiam produzir resultado válido.

## Consistência temporal

Requisitos são classificados de acordo com a origem da evidência:

- `REPLAY_SAFE`: podem ser reexecutados a partir dos dados já persistidos no próprio `AUD-*`, como extração sobre RAW/DOM original ou nova análise de IA sobre o conteúdo originalmente capturado;
- `LIVE_RECOLLECTION`: exigem nova consulta ao ambiente ou serviço externo, como PageSpeed, CrUX e medições sintéticas.

Coletas `LIVE_RECOLLECTION` só podem promover a auditoria ao estado final dentro da janela de recuperação configurada. Quando essa janela expira, o `AUD-*` permanece fora da consolidação e uma nova auditoria deve ser executada para preservar coerência temporal entre as evidências.

A janela padrão é de 1440 minutos e pode ser ajustada por:

```text
RASAI_REPROCESS_LIVE_VALIDITY_MINUTES
```

O valor aceito é limitado pelo runtime entre 1 minuto e 10080 minutos.

A janela de `LIVE_RECOLLECTION` não autoriza substituir evidência de origem ausente. Ela se aplica a medições externas ou sintéticas que foram contratadas como coletas live; não converte HTML/DOM sem artifact persistido em uma fonte recuperável do AUD antigo.

## Recalculo de dados derivados

Quando uma nova tentativa de IA passa a ser a evidência efetiva, o RASAi invalida somente os dados derivados que dependem daquela evidência e os calcula novamente. Isso inclui score, contribuições, priorização e recomendações afetadas.

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
