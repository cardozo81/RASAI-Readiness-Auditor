# Relatório HTML de Search Intelligence

## Objetivo

`report/search-intelligence.html` é a superfície HTML canônica da auditoria para evidências persistidas de Search Intelligence.

O relatório é intencionalmente observacional e consultivo. Ele consolida várias camadas de evidência sem fundir suas metodologias nem alterar a propriedade de cada dado.

Quando disponível, a página pode mostrar:

- contexto observado do resultado de Search e posição do domínio do cliente;
- resultados SERP normalizados retornados pelo provider de Search configurado;
- classificação determinística de resultados pelo RASAi;
- evidência limitada de conteúdo de páginas públicas;
- diferenças determinísticas entre o cliente e líderes observados;
- análise persistida de Competitive AI vinculada a evidências;
- origem, provider, modelo, referência de artefato, hashes e limitações técnicas.

A página não cria novo score e não altera `SARI-001` nem `SCORE-GEO-004`.

## Nome canônico do arquivo e navegação

Arquivo canônico:

```text
report/search-intelligence.html
```

A página é opcional. Ela só é gerada quando o workspace da auditoria contém pelo menos uma observação SERP persistida.

Quando o arquivo existe, a navegação compartilhada dos relatórios inclui `Search Intelligence`. Se não houver evidência de Search Intelligence, a página e o item de navegação permanecem ausentes.

Isso evita mostrar uma superfície de produto vazia em auditorias que não executaram Search Intelligence.

## Modelo de proveniência

O relatório deve preservar a propriedade de cada camada.

### SERP Observation

Origem:

- provider de Search configurado para o conjunto de resultados observado;
- RASAi para normalização, persistência, metadados de integridade e apresentação contextual.

Fontes persistidas:

```text
serp_observations
serp_results
```

Campos como provider, mecanismo, query, país, região, idioma, dispositivo, profundidade solicitada, timestamp de coleta e modo de dados fazem parte do contexto da medição.

Uma posição não é propriedade permanente de um domínio. É uma observação em um contexto definido.

### Status do domínio

`FOUND` significa que o domínio de interesse configurado correspondeu a um resultado normalizado dentro da profundidade coletada.

`NOT_FOUND_WITHIN_DEPTH` significa apenas que o domínio não foi observado dentro da profundidade efetiva de resultados. Não deve ser traduzido como:

- “o site não ranqueia”;
- posição zero;
- posição infinita;
- falha do website;
- score de readiness negativo.

### Classificação competitiva de resultados

Origem:

- heurísticas determinísticas do RASAi aplicadas à observação SERP persistida.

Fonte persistida:

```text
serp_competitive_results
```

A classificação existe para selecionar candidatos razoáveis para inspeção limitada de conteúdo. Ela não estabelece que duas organizações sejam concorrentes comerciais.

Quando o domínio do cliente é encontrado, apenas resultados observados elegíveis que estejam à frente da primeira correspondência do cliente podem ser apresentados como líderes observados naquele contexto de query.

### Evidência de conteúdo público

Origem:

- resposta pública do website observada pelo coletor limitado de conteúdo do RASAi.

Fonte persistida:

```text
serp_competitive_pages
```

O relatório pode expor features determinísticas persistidas, incluindo:

- URL solicitada e URL final;
- status de fetch e status HTTP;
- tipo de conteúdo;
- quantidade de bytes recebidos, quando persistida;
- título;
- meta description;
- texto extraído de H1–H3;
- contagem aproximada de palavras do texto visível;
- termos normalizados da query;
- presença dos termos da query em título, descrição, headings e corpo;
- tipos JSON-LD;
- SHA-256 do conteúdo;
- erros de fetch e metadados de redirect, quando persistidos.

HTML bruto do cliente ou de concorrentes não é necessário para este relatório e não deve ser reconstruído nem fabricado a partir das features extraídas.

### Gaps competitivos determinísticos

Origem:

- comparação determinística do RASAi.

Identificador metodológico atual:

```text
DETERMINISTIC-CORRELATIONAL-001
```

Fonte persistida:

```text
serp_competitive_analyses
```

Esses gaps são diferenças observadas, não fatores de ranking. Cobertura lexical menor da query, volume de conteúdo diferente ou tipos diferentes de dados estruturados podem ser reportados como diferença sem afirmar que a diferença causou a ordem observada no ranking.

## Competitive AI vinculada a evidências

Competitive AI é uma camada semântica opcional e separada. O HTML não chama um provider de IA por conta própria; apenas projeta um resultado persistido produzido pelo runtime de Search Intelligence.

O relatório suporta o contrato de persistência atual:

```text
serp_competitive_ai_analyses
```

Quando disponível, a página pode expor:

- estado/status;
- motivo de execução ignorada ou indisponível;
- provider de IA;
- modelo;
- versão do contrato;
- identificador e versão do prompt;
- request ID do provider, quando disponível;
- avaliação de intenção da query;
- avaliação YMYL;
- resumo semântico;
- quantidade de oportunidades;
- payload persistido das oportunidades;
- referência do artefato de evidência;
- SHA-256 da evidência.

Uma oportunidade de IA deve permanecer vinculada a evidências. IDs de evidência citados pela saída semântica pertencem ao conjunto fechado produzido pelo contrato de evidência competitiva. O relatório não deve substituir IDs de evidência por fatos inventados.

## Limite de interpretação da IA

Competitive AI pode produzir hipóteses e recomendações. Ela não pode estabelecer causalidade privada do mecanismo de busca.

Linguagem válida inclui:

```text
Os líderes observados apresentam cobertura mais ampla do tópico X do que a página do cliente.
Considere avaliar se o tópico X é relevante para a intenção de busca e para o escopo do produto do cliente.
Evidência: CE-CUSTOMER, CE-COMP-001.
```

Linguagem inválida inclui:

```text
O Google posiciona o concorrente acima porque o tópico X está presente.
Adicionar o tópico X levará o cliente à posição 1.
```

A segunda forma afirma acesso a um mecanismo causal que a evidência não estabelece.

## Separação do scoring de readiness

Search Intelligence permanece separado dos índices proprietários de readiness.

```text
evidência do provider de Search
        |
        v
SERP Observation
        |
        +--> evidência competitiva determinística do RASAi
        |          |
        |          +--> evidência opcional e limitada de conteúdo
        |                     |
        |                     +--> Competitive AI opcional vinculada a evidências
        |
        +--> HTML de Search Intelligence

SARI-001 / SCORE-GEO-004
        |
        +--> contrato de scoring e conjunto de evidências separados
```

Nenhuma posição observada, classificação de concorrente, diferença de conteúdo ou recomendação de Competitive AI recebe peso automático no score.

Qualquer tentativa futura de introduzir Search Intelligence no scoring exige novo contrato metodológico explícito, validação documentada e política de compatibilidade. Isso não pode acontecer implicitamente durante a renderização do relatório.

## Separação de Lighthouse e CrUX

`search-intelligence.html` não deve apresentar métricas Lighthouse ou CrUX como indicadores de Search Intelligence.

Os limites de propriedade são:

- scores técnicos de Lighthouse Performance, Accessibility, Best Practices e SEO pertencem ao Google Chrome Lighthouse;
- Core Web Vitals de campo pertencem a CrUX/Web Vitals;
- observações SERP pertencem à observação do provider de Search configurado;
- classificação e comparação competitivas determinísticas pertencem ao RASAi;
- saída competitiva semântica pertence ao workflow de IA do RASAi e ao provider/modelo explicitamente identificado;
- `SARI-001` e `SCORE-GEO-004` pertencem aos respectivos contratos de scoring do RASAi.

Links cruzados são aceitáveis. Fusão metodológica sem contrato explícito não é.

## Atualização do relatório

Quando um workspace de auditoria é fornecido, a persistência de Search Intelligence é a fonte autoritativa. A geração de relatório é acessória.

O runtime de Search tenta atualizar o relatório após persistir uma observação. O runtime competitivo determinístico também tenta atualizar o relatório após persistir sua evidência aditiva.

Um problema de renderização não deve converter uma observação SERP ou comparação competitiva persistida com sucesso em falha de provider/runtime. O HTML pode ser regenerado posteriormente a partir de `audit.db`.

Competitive AI segue o mesmo contrato: depois de persistir a evidência semântica, atualiza o relatório a partir do estado persistido, em vez de passar diretamente ao renderer um objeto de IA que exista apenas em memória.

Isso mantém o HTML reproduzível a partir de suas fontes de verdade persistidas.

## Resumo executivo

Quando `report/index.html` já existe, Search Intelligence pode adicionar um painel idempotente com:

- quantidade de observações persistidas;
- quantidade de observações em que o domínio foi encontrado;
- timestamp da observação mais recente;
- link para `search-intelligence.html`.

O resumo é apenas descritivo. Não deve ser apresentado como score médio de ranking nem como score de Search para o site inteiro.

## Integridade e rastreabilidade

Quando disponíveis, devem ser expostos:

- ID da observação;
- ID da execução Search;
- request ID do provider;
- referência do artefato bruto de evidência;
- SHA-256 do artefato bruto;
- referência e SHA-256 do artefato competitivo;
- referência e SHA-256 do artefato de Competitive AI;
- identificadores de provider/modelo;
- erros e estados indisponíveis.

Uma camada indisponível permanece indisponível. O relatório nunca deve preencher um resultado de provider, feature de conteúdo ou interpretação de IA ausente com um resultado sintético de valor zero.

## Segurança e privacidade

O HTML não exibe segredos de API.

Chaves de provider permanecem fora dos dados persistidos do relatório. A inspeção de páginas públicas continua sujeita à política de segurança de rede de Search Intelligence, incluindo aquisição limitada e validação orientada a SSRF.

Competitive AI recebe o contrato limitado de evidências, e não o HTML bruto de concorrentes. Isso reduz divulgação desnecessária de conteúdo e mantém a requisição semântica vinculada a evidência extraída e reproduzível.

## Comportamento aditivo

O relatório de Search Intelligence é aditivo.

Sem observações SERP persistidas:

- `search-intelligence.html` não é produzido;
- relatórios de auditoria existentes permanecem inalterados;
- o scoring existente permanece inalterado.

Somente com SERP Observation:

- o relatório pode mostrar a SERP observada e a posição do domínio;
- seções competitivas e de IA permanecem explicitamente indisponíveis, e não são fabricadas.

Com evidência competitiva determinística:

- o relatório adiciona classificação, evidência de conteúdo e gaps determinísticos.

Com evidência de Competitive AI:

- o relatório também projeta o resultado semântico persistido, com proveniência de provider/modelo/evidência.

Essa divulgação progressiva permite que Search Intelligence evolua de forma independente, mantendo uma única superfície HTML pública estável.
