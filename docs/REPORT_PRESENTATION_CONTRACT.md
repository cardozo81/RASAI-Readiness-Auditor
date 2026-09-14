# Contrato de apresentação dos relatórios

**Estado:** vigente.

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

## Estado universal de integrações e coletas opcionais

Ausência de dado nunca deve aparecer ao usuário como um vazio sem causa quando o RASAi possui estado suficiente para explicar a execução. Toda integração/coleta opcional deve separar, conforme aplicável:

| Estado público | Significado |
|---|---|
| Desabilitado / não solicitado | a funcionalidade não deveria executar; zero chamadas é esperado |
| Não configurado | a funcionalidade foi habilitada, mas faltou credencial, provider ou configuração necessária |
| Executado com sucesso | a operação terminou normalmente e materializou seu estado/dataset |
| Executado parcialmente | houve execução, mas parte do universo ou das fontes não produziu resultado utilizável |
| Executado sem dado utilizável | a fonte/operação respondeu, porém não entregou evidência utilizável para o indicador |
| Falhou / indisponível | houve tentativa ou bloqueio operacional e o resultado esperado não pôde ser materializado |
| Estado não determinado | não há estado persistido suficiente para classificar a execução com segurança; não deve ser convertido em sucesso ou falha |

Regras obrigatórias:

- **desabilitado não é erro**;
- **não configurado não é falha do website**;
- timeout, quota, autenticação, HTTP 4xx/5xx, rede, indisponibilidade do provider ou contrato inválido devem aparecer como limitação da integração, com motivo seguro quando persistido;
- sucesso com ausência de amostra/dado da fonte não deve virar `0` observado;
- `PARTIAL` deve continuar distinto de `SUCCESS` e de `ERROR`;
- o relatório não deve inventar `DISABLED` quando não existe evidência de configuração/execução suficiente;
- credenciais e valores secretos nunca podem aparecer no motivo, HTML, log ou ledger;
- falha de integração não cria finding do website e não altera SARI/SCORE fora de contratos explicitamente definidos;
- quando a integração ocorre pós-auditoria, seu sidecar deve persistir um ledger de tentativas suficiente para reabrir o relatório depois e distinguir `NOT_CONFIGURED`, `SUCCESS` e `ERROR`.

O `index.html` usa a seção **Configuração × resultado obtido** para as capacidades audit-owned. Superfícies especializadas pós-auditoria exibem o mesmo contrato em sua própria página.

Aplicações atuais deste contrato incluem:

- análise semântica por IA;
- remediação textual por IA;
- IA técnica de crawling/discovery;
- PageSpeed/Lighthouse/CrUX e Accessibility derivada;
- Synthetic Navigation Apdex e Synthetic User Experience Apdex;
- Search Intelligence/SERP, inclusive falhas de runtime anteriores à materialização da observação;
- Search & AI Observability, com ledger de tentativas de Search Console, CrUX History e imports suportados;
- Observed Generative Visibility, que é `import-first`: ausência de dataset significa não importado/não observado por esse fluxo e **não** falha presumida de API de IA.

## Estado contextual no topo de cada página

A existência física de um HTML canônico **não** significa que a análise correspondente foi concluída. O header de cada relatório deve informar, a partir do estado já persistido, se a leitura está:

- concluída;
- concluída com limitações;
- dependente de configuração;
- sem dados solicitados/produzidos;
- com dados insuficientes;
- não concluída por falha/bloqueio;
- ou com estado não determinado quando não existir evidência suficiente para classificar com segurança.

O header é uma projeção de apresentação e não recalcula fulfillment. Quando o contrato de execução persistido estiver disponível, ele é a referência para o estado global da auditoria; estados específicos de capabilities permanecem subordinados aos respectivos ledgers/runs.

O header também pode mostrar, de forma compacta:

- quantidade de URLs do escopo;
- dispositivos/contextos presentes;
- indicação de uso de IA quando houver evidência persistida;
- aviso de que o HTML é uma projeção dos dados persistidos e não recalcula resultados.

O estado deve ser expresso por **texto + cor semântica**, nunca apenas pela cor.

## Semântica visual comum

A apresentação final usa uma paleta semântica consistente para cards, badges, headers e estados:

| Semântica | Uso principal |
|---|---|
| verde | concluído, aprovado, melhora observada, correção verificada |
| amarelo/âmbar | parcial, configuração necessária, dado insuficiente, atenção |
| vermelho | falha, bloqueio, regressão ou condição crítica |
| azul | informação contextual/metodológica, escopo, navegação |
| cinza/neutro | não solicitado, não aplicável ou estado não determinado |

Cor reforça a interpretação, mas o rótulo textual é obrigatório. A mesma semântica deve ser reutilizada em AUD e CONS sempre que o conceito for equivalente.

## Transparência: “Entenda esta página”

Cada superfície canônica pode apresentar, próximo ao final da página, um acionador discreto **Entenda esta página**. O conteúdo detalhado fica em modal/painel sob demanda para evitar poluir a leitura principal.

A camada de transparência deve separar claramente:

1. o que a página entrega;
2. quais dados podem alimentá-la;
3. o estado das dependências nesta auditoria;
4. dependências necessárias;
5. dependências complementares;
6. orientação para obter uma análise mais completa quando houver ação possível;
7. uso ou não uso de IA;
8. rastreabilidade técnica, fonte de verdade e impacto sobre scoring.

Identificadores internos, nomes de componentes, códigos e variáveis podem aparecer no nível de rastreabilidade técnica, mas não devem substituir o vocabulário humano da leitura principal.

A interface nunca deve expor valor de segredo, token, credencial ou chave. Quando necessário, informa apenas que determinada configuração/credencial está ausente ou inválida.

## Leitura orientada ao usuário

A ordem de leitura preferencial é:

```text
resultado -> interpretação -> ação -> detalhe técnico -> evidência -> metodologia/proveniência
```

O usuário deve conseguir responder, sem conhecer a arquitetura interna do RASAi:

1. esta análise foi concluída?;
2. qual é o resultado técnico?;
3. quais dados sustentam o resultado?;
4. o que precisa ser corrigido e em qual URL/contexto?;
5. o que já melhorou ou foi resolvido quando existir base comparável?;
6. o que faltou e como habilitar/completar a medição, quando isso estiver sob controle do usuário?.

O relatório não deve sugerir uma configuração como solução quando a ausência é legítima da fonte externa, por exemplo falta de amostra CrUX para determinada URL.

## Dashboard executivo

`index.html` é a entrada executiva e deve priorizar resumo factual já existente nos relatórios especializados, sem criar novos cálculos.

Além dos indicadores persistidos, a navegação visual pode destacar três caminhos:

- **Resultado técnico** -> aprofundar Readiness e qualidade da medição;
- **Ação** -> abrir Remediações para localizar problema, página/contexto, correção e critério de aceite;
- **Evolução** -> abrir Quality/comparações disponíveis para entender melhora, regressão ou verificação.

O dashboard não combina metodologias diferentes em uma nota única e não pode apresentar valor divergente daquele usado na superfície especializada proprietária do indicador.

## Relatório consolidado

O CONS aplica a mesma semântica visual e a mesma regra de progressive disclosure do AUD.

O topo deve deixar claro que se trata de leitura histórica derivada de auditorias elegíveis/comparáveis. Quando a análise especialista por IA for solicitada, o estado dessa IA deve ser identificado separadamente e seus resultados continuam orientativos.

No consolidado:

- melhora observada não prova causalidade;
- uma correção verificada demonstra a transição persistida da regra, não prova impacto posterior em ranking, tráfego, conversão ou visibilidade em IA;
- auditorias/metodologias incompatíveis não devem ser fundidas silenciosamente;
- o HTML não reexecuta PageSpeed, CrUX, Search ou outras coletas históricas para preencher o relatório.

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

As superfícies audit-owned são projeções de `audit.db`. Integrações pós-auditoria podem usar sidecars explícitos, como `observability.db`, preservando a separação da evidência imutável do AUD. A renderização dos relatórios não dispara novas requisições ao website nem novas chamadas de IA para preencher a interface.
