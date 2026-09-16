# Report-catalog - estado de validação e pendências conhecidas

**Estado:** validação de desenvolvimento/pré-produção.

Data de referência: 2026-09-16.

A estrutura visual permanece preservada. Os ajustes desta rodada são de contrato de dados, materialização, linguagem, rastreabilidade e projeção; não constituem redesign e não alteram scoring determinístico.

## Correções incorporadas

### Freshness, materialização e gate final

`report-catalog/` é tratado como projeção final derivada do estado persistido da AUD:

- a Improvement Intelligence é executada antes da última finalização do relatório no fluxo de console;
- a materialização do `report-catalog` calcula fingerprint SHA-256 da fonte persistida (`audit.db` e WAL ativo, quando existir) antes e depois da renderização;
- o relatório só é promovido se a fonte permanecer estável durante a projeção;
- a árvore anterior é retirada do caminho público antes da nova materialização;
- se o renderer falhar, a árvore anterior não volta a ficar disponível como se fosse final;
- o `manifest.json` registra `generated_at`, `source_audit`, `source_fingerprint`, algoritmo do fingerprint, `projection_version` e `freshness=FINAL`;
- existe verificação explícita de freshness após a promoção;
- erro de materialização/freshness do `report-catalog` é bloqueante para a conclusão dos relatórios HTML: a execução informa `Relatórios HTML: INCOMPLETOS` e retorna o código de projeção incompleta, preservando o `audit.db`;
- erros tardios de outros enriquecimentos mantêm sua semântica própria; o gate bloqueante é específico para a projeção final que não pode ser validada como correspondente ao estado persistido.

Isso corrige a classe de erro observada em validação na AUD `AUD-1851DA1A3CBE466AA649D34CAC2D48E0`, em que CAT-08/CAT-09/IA e integrações haviam sido materializados antes dos dados finais da análise profunda.

### Tabelas interativas

As tabelas marcadas como interativas ordenam o dataset inteiro antes da paginação. A chave de ordenação normaliza valores formatados que, se comparados apenas como texto, produziriam ordem incorreta:

- timestamps apresentados como `dd/mm/aaaa hh:mm:ss` são comparados cronologicamente;
- valores em `ms` são comparados numericamente;
- percentuais são comparados numericamente;
- a apresentação visível permanece localizada/formatada; somente a chave de ordenação é normalizada.

### IA e integrações

A página usa uma única agregação canônica das tentativas persistidas e apresenta:

- tentativas e sucessos;
- tokens de entrada, cache, saída, reasoning e total canônico;
- reasoning como detalhamento informativo, sem double-count no total;
- custo monetário observado como soma única dos custos persistidos por tentativa;
- chamada que falhou após consumir provider incluída no custo observado;
- previsão x consumo observado com custo esperado, observado, desvio absoluto/percentual, faixa provável, P90, confiança, classificação e relação com a faixa;
- aviso explícito de que o custo é estimativa técnica do RASAi e não invoice/fatura do provider;
- camada humana por tentativa: finalidade, CAT/aplicação, entrada utilizada, dados envolvidos, resultado funcional esperado, fallback, erro e telemetria;
- request/response bruto somente quando realmente persistido e sanitizado; quando ausente, a página informa `Solicitação/resposta bruta não persistida` e não reconstrói payload.

### Lighthouse / Web Performance

Foi corrigido o caso de fronteira em que `performance_score=1.0`, já persistido na escala `0..100`, era interpretado novamente como `0..1` e virava `100/100`.

Pontuações de categoria provenientes de `web_performance_observations` são projetadas diretamente na escala persistida. Portanto `1.0` é exibido como `1 / 100`, enquanto `78.0` é `78 / 100`.

### CAT-06 - Apdex de navegação

A apresentação mantém separadas as duas dimensões:

- conclusão técnica da etapa;
- cobertura/qualidade estatística do resultado.

Um work-item `SUCCESS` com run `PARTIAL` por `SMALL_GROUP_BELOW_NORMAL_MINIMUM` não é tratado como falha. A página explica que a coleta concluiu, mas a leitura permanece parcial por população abaixo do mínimo metodológico.

### CAT-07 - Apdex de experiência

A tabela de amostras mantém:

- `captured_at` apresentado como data/hora da captura no timezone de apresentação;
- explicação de que esse timestamp é o momento persistido da captura, não necessariamente o início individual da navegação;
- LCP e contagem de requests com falha entre as colunas principais;
- ordenação client-side aplicada sobre o dataset inteiro antes da paginação;
- paginação de 10 registros por página;
- explicação explícita quando a política `errors_affect_apdex` força amostras para `Frustrada`, evitando atribuir a classificação somente à duração.

### CAT-08 - Análise profunda

CAT-08 projeta os findings finais persistidos, sua distribuição por domínio, severidade, origem/CAT e vínculo com recomendações.

Quando houver menos recomendações que findings, a página mostra quantos achados não possuem remediação individual e, quando aplicável, explica o limite `max_recommendations`. Um finding sem recomendação não recebe correção inventada.

Se a etapa for solicitada mas falhar sem resultado funcional, a página mostra rastreabilidade de provider/modelo/tentativa/erro/fallback em vez de apenas `sem resultado`.

### CAT-09 - Remediações

As recomendações finais da análise profunda são projetadas individualmente. Quando os campos existirem, cada item apresenta:

- problema observado;
- CAT/domínio de origem;
- severidade/prioridade;
- risco de manter como está;
- benefício esperado;
- seletor/path;
- situação atual/HTML original;
- proposta corrigida/HTML ou texto sugerido;
- critério de validação e revalidação;
- evidências, esforço e confiança.

Remediações determinísticas/editoriais que representem o mesmo finding já coberto pela análise profunda são suprimidas na listagem principal para reduzir duplicação conflitante.

### Robots, sitemap, llms.txt e dados estruturados

A apresentação diferencia correção necessária de oportunidade:

- `robots.txt` ausente não é rotulado como arquivo `não interpretável` nem como erro de crawling; pode aparecer como oportunidade de explicitar política;
- sitemap ausente no caminho convencional é lacuna de descoberta/readiness, não falha fatal; URLs não descobertas não são inventadas;
- `llms.txt` permanece opcional/não padronizado e sua ausência não é tratada como requisito obrigatório;
- quando nenhum dado estruturado foi observado, a sugestão é `Considerar implementar dados estruturados aplicáveis`, e não `Corrigir sintaxe`.

### Captura e contexto

A captura visual persistida tem preview na própria página, com dispositivo, data/hora e viewport. O clique abre uma modal específica somente daquela imagem. O modal geral de contexto não vira depósito visual da captura.

### Linguagem humana

Estados e níveis usados na camada principal são humanizados. Códigos internos continuam permitidos apenas em detalhes técnicos/proveniência ou no payload bruto original. Valores em português como `CRÍTICO` também são normalizados sem perder acentuação legível.

## Limitações de dados ainda reais

### Requests individuais do Apdex de experiência

O contrato atual de `synthetic_ux_apdex_samples` preserva contagens de XHR/fetch, recursos dinâmicos, erros de console/JavaScript, request failures e erros HTTP por amostra, mas não necessariamente a lista completa de URLs de cada request. O relatório mostra o que foi persistido e declara a ausência da lista individual; nunca a reconstrói por inferência.

### Comunicação bruta da análise profunda

Algumas tentativas de IA possuem telemetria em `ai_provider_attempts` sem entrada correspondente em `ai_exchange_log`. Nesses casos o relatório exibe provider/modelo, status, tokens, duração, custo, contrato, fallback e erro persistidos, e informa que request/response bruto não foi armazenado.

### Cobertura 1:1 de remediações de IA

A Improvement Intelligence pode analisar mais findings do que o limite configurado de recomendações (`max_recommendations`). Nessas execuções não existe garantia de uma recomendação de IA individual para cada finding. O CAT-08 mantém todos os findings visíveis e o CAT-09 projeta somente as remediações realmente persistidas; nenhuma correção adicional é inventada pelo renderer.

### Fontes compartilhadas

Alguns collectors servem a mais de um domínio, por exemplo PageSpeed/Lighthouse. O dado funcional pode aparecer no CAT proprietário, mas a chamada externa e sua telemetria são exibidas uma única vez em `IA e integrações`.

## Invariantes

- seleção vem do plano congelado; ausência de snapshot não significa `NÃO SOLICITADO`;
- CAT desmarcado não pode iniciar chamada paga nem work-item funcional próprio;
- coleta, análise e remediação são responsabilidades distintas;
- CATs referenciam evidências de outros domínios em vez de duplicá-las;
- IA não altera scoring determinístico;
- `report-catalog/` permanece read-only e não executa nova coleta/request/IA;
- modais são contextuais, nunca um depósito de detalhes da página;
- componentes visuais e ordem estrutural das seções permanecem compartilhados e estáveis;
- um `report-catalog` cujo fingerprint não corresponda à fonte persistida não é considerado final;
- a auditoria não deve anunciar os relatórios HTML como completos quando o gate final de materialização/freshness do `report-catalog` falhar.
