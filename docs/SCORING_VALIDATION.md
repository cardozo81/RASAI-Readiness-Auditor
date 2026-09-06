# SCORING_VALIDATION.md

## Objetivo

Este documento registra a natureza da validação do `SCORE-GEO-002`, separa métricas internas de métricas externas e define caminhos possíveis para uma futura calibração empírica do SearchGEO.

## 1. Conclusão normativa

Não existe, na data desta baseline, um **score universal de GEO/AEO Readiness 0–100 externamente homologado e calibrado de ponta a ponta** por Google, OpenAI, Microsoft, NIST, W3C ou outro mantenedor equivalente.

Consequentemente, o `SCORE-GEO-002` não deve alegar equivalência a um padrão externo inexistente.

É possível, porém, aumentar substancialmente o respaldo quantitativo do produto utilizando **métricas externas oficiais ou padronizadas para fenômenos específicos** e mantendo explícito o limite de aplicabilidade de cada uma.

## 2. Hierarquia de evidência

O SearchGEO deve classificar a origem de cada sinal quantitativo em uma das categorias abaixo.

### A. Requisito oficial do mecanismo

Regra diretamente documentada por quem opera a superfície avaliada.

Exemplos:

- requisitos técnicos e de indexação do Google Search;
- elegibilidade para snippets e recursos de IA do Google;
- controles de crawler documentados por mecanismos/provedores;
- dados observados fornecidos pelo próprio Bing Webmaster Tools.

Esse nível possui forte respaldo para responder **elegibilidade/comportamento documentado**, mas normalmente não fornece um score GEO 0–100.

### B. Métrica externa calibrada ou padronizada

Métrica cuja fórmula, thresholds ou curva de scoring possuem metodologia pública e dados externos de referência.

Exemplos:

- Core Web Vitals;
- Lighthouse Performance Score;
- nDCG, MRR, Precision, Recall e métricas relacionadas usadas por NIST/TREC;
- métricas de suporte/citação empregadas em avaliações de RAG do TREC.

Essas métricas são adequadas ao fenômeno para o qual foram construídas. Elas **não devem ser promovidas automaticamente a score GEO global**.

### C. Métrica acadêmica experimental

Métrica publicada em benchmark ou estudo científico, porém sem status de padrão operacional do mercado.

Exemplo:

- métricas de visibilidade do GEO-Bench.

Podem informar desenho experimental e validação, mas exigem cautela de generalização.

### D. Heurística SearchGEO

Peso, threshold, fator ou agregação definidos internamente.

Exemplos atuais:

- `PASS = 1.00`;
- `WARNING = 0.50`;
- `FAIL = 0.00`;
- pesos iguais entre dimensões;
- Coverage 80%/90%;
- classificação visual 90/75/60/40;
- média simples das dimensões no Overall.

Esses valores devem permanecer claramente identificados como internos até calibração empírica.

## 3. Métricas externas que podem ser utilizadas

### 3.1 Google Search / AI features — elegibilidade técnica

A documentação oficial do Google estabelece que, para aparecer como link de suporte em AI Overviews ou AI Mode, a página precisa estar indexada e elegível para aparecer no Google Search com snippet. O Google também declara que não existem requisitos técnicos adicionais específicos para essas superfícies de IA.

Uso recomendado no SearchGEO:

- tratar requisitos técnicos documentados como **gates de elegibilidade**, não como pesos arbitrários;
- separar `ELIGIBLE`, `NOT_ELIGIBLE` e `UNKNOWN/UNVERIFIED`;
- nunca afirmar que elegibilidade garante inclusão/citação.

Referência:

- https://developers.google.com/search/docs/appearance/ai-features

### 3.2 Core Web Vitals — experiência de página

Os Core Web Vitals possuem thresholds documentados pelo Google e usam o percentil 75 das experiências observadas:

- LCP bom: `<= 2.5 s`;
- INP bom: `<= 200 ms`;
- CLS bom: `<= 0.1`.

Uso recomendado no SearchGEO:

- substituir thresholds próprios de performance, quando houver, pelos thresholds oficiais de CWV;
- manter Mobile e Desktop separados;
- preferir dados de campo quando disponíveis;
- não converter aprovação em CWV em “probabilidade GEO”.

Referências:

- https://web.dev/articles/vitals
- https://web.dev/articles/defining-core-web-vitals-thresholds

### 3.3 Lighthouse Performance Score — score externo calibrado de performance

O Lighthouse converte métricas de performance em score 0–100 por curvas log-normais derivadas de dados reais do HTTP Archive. A documentação explica os pontos de controle e os pesos utilizados no score.

Uso recomendado no SearchGEO:

- pode compor ou substituir uma submétrica estritamente ligada à performance técnica;
- deve ser rotulado como `Lighthouse Performance`, não como `GEO Score`;
- não deve determinar sozinho compatibilidade GEO.

Referência:

- https://developer.chrome.com/docs/lighthouse/performance/performance-scoring

### 3.4 Bing Webmaster Tools AI Performance — outcome observado

O Bing disponibiliza dados sobre participação real do conteúdo em respostas generativas, incluindo:

- Total Citations;
- Average Cited Pages;
- grounding queries;
- citation activity por URL;
- tendência temporal de citações.

Essas métricas são particularmente relevantes porque medem **resultado observado**, não apenas prontidão inferida.

O M26 (`Observed Generative Visibility`) materializa esse domínio de forma **import-first** por meio do contrato `OGV-IMPORT-001`. Na baseline atual, o SearchGEO não faz scraping do Bing Webmaster Tools nem presume endpoint público de AI Performance não documentado.

Regras do M26 para dados Bing:

- Total Citations e Average Cited Pages permanecem `source-reported`;
- grounding queries, atividade por URL e tendência são preservadas conforme o dataset normalizado;
- o artifact importado é preservado com SHA-256;
- URLs devem pertencer ao `normalized_origin` da auditoria;
- nenhum valor M26 entra em `SGRI-001`/`SCORE-GEO-002`.

Uso recomendado:

- manter `Observed Generative Visibility` separado do Readiness;
- usar citações reais como variável de validação/calibração futura;
- não interpretar contagem de citações como ranking, autoridade ou posição quando a fonte não fornece essa semântica.

Referência:

- https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview

## 4. Métricas de Information Retrieval aplicáveis a testes GEO

NIST/TREC utiliza métricas consolidadas para avaliar recuperação e ranking. Elas podem ser adaptadas a experimentos de visibilidade/citação em engines generativas, desde que o protocolo de coleta seja controlado.

### 4.1 Citation Presence Rate

Para um conjunto de query-runs controlados:

```text
Citation Presence Rate = query-runs VALID em que o origin auditado foi citado / total de query-runs VALID
```

Essa métrica é um outcome diretamente observável. O M26 já implementa essa fórmula quando o dataset contém `query_runs` controlados.

Regras:

- runs `INVALID` ficam fora do numerador e denominador;
- `cited=true` exige ao menos uma URL same-origin;
- `cited=false` não pode carregar URLs citadas do origin auditado;
- a taxa é acompanhada do tamanho amostral;
- o M26 calcula intervalo binomial de Wilson 95% para representar incerteza amostral quando `n > 0`.

A taxa histórica **não é convertida em probabilidade preditiva de citação futura** e não valida causalidade do SGRI.

### 4.2 Mean Reciprocal Rank — MRR

Quando a resposta/superfície fornece uma ordenação interpretável de fontes:

```text
RR(q) = 1 / rank_da_primeira_citação_relevante
MRR   = média de RR(q)
```

MRR é métrica tradicional de Information Retrieval e Question Answering utilizada pelo TREC.

Uso recomendado:

- medir quão cedo a fonte aparece quando existe ranking/posição observável;
- não usar quando a superfície não expõe uma ordenação semanticamente válida.

O M26 aceita `rank` apenas quando o dataset também fornece `ranking_semantics`; nesta baseline ele **não agrega automaticamente MRR**, evitando presumir equivalência de ordenação entre engines/surfaces.

### 4.3 nDCG@k

Quando existem posições e níveis graduados de relevância/prominência:

```text
DCG@k = Σ ((2^rel_i - 1) / log2(i + 1))
nDCG@k = DCG@k / IDCG@k
```

nDCG é amplamente utilizado pelo NIST/TREC para ranking com relevância graduada.

Uso recomendado:

- comparar qualidade de posicionamento de fontes em experimentos controlados;
- requer definição explícita e auditável de `rel_i`;
- não inventar níveis de relevância sem protocolo de julgamento.

### 4.4 Precision / Recall

Podem avaliar recuperação de páginas/fontes esperadas em um conjunto com ground truth.

```text
Precision = relevantes recuperados / recuperados
Recall    = relevantes recuperados / relevantes existentes no ground truth
```

São úteis principalmente em benchmark controlado, não em auditoria isolada de um site sem ground truth.

### 4.5 Weighted Citation Precision / Recall

O TREC RAG 2025 utiliza avaliação de suporte das citações com pesos:

- Full Support = `1.0`;
- Partial Support = `0.5`;
- No Support = `0.0`.

Uso recomendado no SearchGEO:

- avaliar se uma engine cita uma página e se a citação realmente sustenta a afirmação produzida;
- manter essa métrica como avaliação de qualidade/fidelidade de citação, não como peso automático do `SCORE-GEO-002`.

Referências NIST/TREC:

- https://trec.nist.gov/data/qa.html
- https://trec.nist.gov/pubs/trec34/appendices/trec2025-rag-retrieval.html
- https://trec.nist.gov/pubs/trec34/papers/Overview_rag.pdf

## 5. GEO-Bench e literatura acadêmica

O trabalho `GEO: Generative Engine Optimization` introduziu o GEO-Bench e métricas experimentais de visibilidade para estudar como alterações de conteúdo afetam sua presença em respostas generativas.

Referência:

- https://arxiv.org/abs/2311.09735

O benchmark é evidência acadêmica relevante, mas não equivale a um padrão oficial de mercado nem demonstra, sozinho, descobribilidade orgânica longitudinal e cross-platform.

Uma revisão crítica de 2026 destaca heterogeneidade de terminologia, métricas e padrões de evidência, além de variabilidade entre engines e execuções.

Referência:

- https://arxiv.org/abs/2607.14035

## 6. Arquitetura recomendada de métricas

Em vez de substituir `SCORE-GEO-002` por outro número arbitrário, a evolução recomendada separa três camadas:

### 6.1 Readiness inferido

Mantém o papel atual do SearchGEO:

- auditabilidade;
- regras evidence-backed;
- diagnósticos técnicos/semânticos;
- Coverage/Confidence/Consolidation.

Saída:

```text
SearchGEO Readiness Index (SGRI-001)
```

Natureza:

```text
interno / heurístico até calibração
```

### 6.2 External Technical Evidence

Usa métricas e gates externos quando aplicáveis:

```text
Google eligibility status
Core Web Vitals
Lighthouse Performance
outros requisitos oficiais por engine
```

Natureza:

```text
externamente documentado/calibrado para o fenômeno específico
```

### 6.3 Observed Generative Visibility

Domínio implementado pelo M26 para outcomes reais/importados:

```text
Bing AI Performance source-reported metrics
atividade/citações por URL
grounding queries
tendência importada
Citation Presence Rate em query-runs controlados
rank observado somente quando sua semântica é explícita
```

Natureza:

```text
observacional/experimental; separado do readiness
```

Métricas como MRR, nDCG e citation-support precision/recall permanecem candidatas para protocolos futuros, não outputs implícitos do M26 atual.

Essa separação evita que um único número misture prontidão inferida, experiência de página e performance real de citação.

## 7. Se um único score calibrado for exigido

Um novo score único somente terá respaldo empírico se for **calibrado contra um outcome definido**.

Exemplo de outcome binário:

```text
Y = 1 se a URL/site é citado em uma query-run elegível
Y = 0 caso contrário
```

Possível processo para uma futura versão calibrada:

1. coletar grande amostra de sites/páginas e queries;
2. executar múltiplas engines e múltiplas repetições por query;
3. extrair as features atuais do SearchGEO;
4. separar treino, calibração e teste por domínio/site para evitar leakage;
5. estimar relação entre features e outcome, por exemplo com regressão logística ou outro modelo interpretável;
6. calibrar probabilidades em conjunto separado quando necessário;
7. medir discriminação e calibração no conjunto de teste;
8. verificar estabilidade temporal e por engine;
9. publicar intervalos de confiança e limitações;
10. versionar o modelo conforme período e superfícies avaliadas.

O M26 passa a fornecer uma infraestrutura de outcomes que pode alimentar esse trabalho no futuro, mas **sua existência não valida por si só o SGRI**. Dataset, desenho experimental, separação de amostras e validação fora da amostra continuam obrigatórios.

Nesse cenário, uma saída poderia ser denominada, por exemplo:

```text
Estimated Citation Probability
```

somente se a validação demonstrar calibração adequada. Ela não deve substituir o Readiness diagnóstico: probabilidade observada e causa técnica são problemas diferentes.

## 8. Recomendação para o produto atual

Para `SGRI-001` / `SCORE-GEO-002`:

- manter a fórmula atual para continuidade e reprodutibilidade;
- explicitar que pesos/fatores/thresholds são heurísticos;
- incorporar métricas externas somente nas dimensões em que exista correspondência conceitual válida;
- não transformar Core Web Vitals, Lighthouse, métricas TREC ou outcomes M26 em “prova” do Overall Readiness;
- usar M26 como camada observacional independente e como possível fonte futura de dataset de validação;
- planejar qualquer versão calibrada como projeto empírico, não como simples troca manual de pesos;
- preferir no report a apresentação conjunta, porém não fundida, de `Readiness`, `Coverage/Confidence`, `External Evidence` e `Observed Generative Visibility` quando disponível.

## 9. Critério de linguagem

Permitido:

> O SearchGEO calcula um índice interno e reprodutível de prontidão, fundamentado em evidências técnicas e semânticas. Algumas submétricas podem utilizar padrões ou thresholds externos documentados.

Também permitido para M26:

> O SearchGEO apresenta outcomes de visibilidade generativa observados/importados separadamente do readiness, preservando fonte, período e tamanho amostral quando aplicável.

Não permitido sem validação adicional:

> Score GEO oficial.

> 85 pontos = 85% de chance de citação.

> Certificado pelo Google/OpenAI/Microsoft.

> Score cientificamente validado.

> Threshold GEO universal.

> Citation Presence Rate histórica = probabilidade futura de citação.