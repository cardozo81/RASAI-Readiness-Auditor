# Contrato de apresentação dos relatórios

Este documento define regras de apresentação que são comuns ao mini-site HTML do RASAi. Ele não altera cálculo, pesos, gates, persistência ou evidência do `SARI-001` / `SCORE-GEO-004` e não altera a fórmula Apdex.

## Faixas visuais do SARI

Um score numérico SARI válido usa a classificação interna vigente:

| Score | Classificação | Cor semântica |
|---:|---|---|
| 90-100 | Excelente | verde |
| 75-89 | Alta | verde |
| 60-74 | Moderada | amarelo/âmbar |
| 40-59 | Baixa | laranja |
| 0-39 | Crítica | vermelho |
| sem score válido | Não determinado | cinza/neutro |

`Coverage`, `Confidence` e `Consolidation` qualificam a força/completude da medição e permanecem apresentados separadamente. Eles **não mudam a faixa nem a cor de um score numérico válido**. Exemplo: um score 82 continua na faixa **Alta**; `Confidence=LOW` deve ser exibido como limitação da medição, não recolorir 82 como score crítico.

A cor nunca substitui o texto da faixa.

## Dashboard executivo e Apdex de experiência

Quando houver estado persistido de Synthetic User Experience Apdex, `index.html` deve incluir um card complementar próprio, separado de Synthetic Navigation Apdex.

O card:

- aponta para `apdex-experience.html`;
- usa os resumos `POPULATION` persistidos;
- mostra valor único quando todas as populações materializadas possuem o mesmo Apdex ou uma faixa mínima-máxima quando existem várias páginas;
- mostra amostras válidas/target e o estado da execução;
- permanece independente do SARI e não participa de `SCORE-GEO-004`.

## Tentativas e retornos em `apdex-experience.html`

Uma **tentativa** corresponde a uma user action sintética com uma navegação principal sob um perfil efetivo de dispositivo/cliente/hardware/rede.

O relatório deve permitir auditar, por `URL x device x profile_id`:

- target de amostras válidas;
- número de tentativas executadas;
- quantidade de respostas HTTP da navegação principal;
- distribuição dos HTTP status da navegação principal;
- status da navegação, por exemplo `SUCCESS`, `TIMEOUT` ou `APPLICATION_ERROR`;
- válidas e inválidas;
- classificação `SATISFIED`, `TOLERATING` e `FRUSTRATED`;
- contadores persistidos de XHR/fetch, requests falhos e respostas HTTP `>=400`.

Uma página pode disparar vários subrequests durante uma tentativa. Esses subrequests **não são novas amostras da população**. O RASAi não deve apresentar a soma de contadores parciais como se fosse o total exato de requests de rede quando a lista completa de requests não foi persistida.

## Estado vazio em `ai-usage.html`

A tabela **Remediação opcional de conteúdo por IA** representa somente a finalidade controlada por `RASAI_AI_CONTENT_REMEDIATION` / `--ai-content-remediation`. Ela é independente da análise semântica e da IA técnica de crawling/discovery.

Uma tabela sem tentativas não é automaticamente erro. O relatório deve distinguir pelo estado persistido:

| Condição | Interpretação |
|---|---|
| recurso desabilitado | esperado; a finalidade é default OFF |
| habilitado e zero findings elegíveis | esperado; não havia motivo para chamada |
| `NOT_CONFIGURED` | habilitado, mas sem provider saudável/configurado para a finalidade |
| findings elegíveis e zero tentativas com estado degradado/erro | requer investigação; exibir `status` e `reason` persistidos |
| tentativas existentes | listar provider/modelo/status/tokens/custo/duração/erro de cada tentativa |

Além da tabela, `ai-usage.html` deve mostrar `Findings elegíveis`, `Contextos registrados`, `Sugestões publicadas` e o motivo persistido da etapa quando disponível.

## Fonte de verdade

Todas essas superfícies são projeções de `audit.db`. A renderização dos relatórios não dispara novas requisições ao website nem novas chamadas de IA para preencher a interface.
