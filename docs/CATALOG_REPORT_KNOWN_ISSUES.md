# Report-catalog - estado de validação e pendências conhecidas

**Estado:** validação de desenvolvimento/pré-produção.

Data de referência: 2026-09-16.

A estrutura visual permanece preservada. Os ajustes desta rodada são de contrato de dados, materialização, linguagem, rastreabilidade e projeção; não constituem redesign e não alteram scoring determinístico.

Como o produto ainda não foi publicado, os contratos abaixo passam a ser o comportamento canônico atual. Não existe requisito de compatibilidade com estados, enums ou textos públicos obsoletos desta fase de desenvolvimento.

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
- a camada externa final do console refaz `report-catalog/` somente depois que toda a cadeia interna retorna, incluindo persistências tardias de fulfillment e de aderência de custo esperado x observado;
- portanto `freshness=FINAL` passa a representar o `audit.db` após essas persistências, e não uma fotografia produzida milissegundos antes delas;
- erro de materialização/freshness do `report-catalog` é bloqueante para a conclusão dos relatórios HTML: a execução informa `Relatórios HTML: INCOMPLETOS` e retorna o código de projeção incompleta, preservando o `audit.db`;
- erros tardios de outros enriquecimentos mantêm sua semântica própria; o gate bloqueante é específico para a projeção final que não pode ser validada como correspondente ao estado persistido.

Isso corrige também a classe de divergência em que `console_cost_forecast_outcomes` já existia no `audit.db`, mas `IA e integrações` ainda apresentava a previsão como não persistida porque o HTML havia sido gerado antes do último `COMMIT` lógico da execução.

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

As avaliações de Core Web Vitals deixaram de persistir o estado ambíguo `NEEDS_IMPROVEMENT_OR_POOR`. O contrato atual diferencia:

- `GOOD`;
- `NEEDS_IMPROVEMENT`;
- `POOR`;
- estado agregado `PASS`, `FAIL` ou `INCOMPLETE` conforme a disponibilidade das três métricas.

Para LCP, INP e CLS são aplicados os dois limites necessários para separar `Precisa melhorar` de `Ruim`. A camada pública apresenta esses rótulos em português. A requisição PageSpeed solicita `locale=pt-BR`, preservando o runtime de timeout, telemetria e política de tentativas do coletor externo.

Na camada de apresentação em português, rótulos genéricos de tabela passam a usar termos como `Desempenho web`, `Lighthouse · Desempenho`, `Lighthouse · Acessibilidade`, `Lighthouse · Boas práticas`, `Índice de velocidade (Speed Index)` e `Tempo total de bloqueio (TBT)`. Marcas, siglas e nomes técnicos oficiais permanecem preservados.

### CAT-05 - Search & AI Intelligence

O estado agregado do catálogo não é mais reutilizado como se todas as subcapacidades tivessem sido executadas. A tabela de escopo resolve separadamente:

- Inteligência de busca / SERP;
- Google Search Console;
- Visibilidade em respostas de IA;
- Observabilidade externa.

Cada linha usa sua própria evidência persistida ou work-item. Uma capacidade independente sem fonte/work-item deixa de aparecer simplesmente como `Incluída` e passa a informar, conforme o caso, `Concluída`, `Não configurado`, `Solicitado, não executado`, `Parcial`, falha ou `Não requerida nesta AUD`.

### CAT-06 - Apdex de navegação

A apresentação mantém separadas as duas dimensões:

- conclusão técnica da etapa;
- cobertura/qualidade estatística do resultado.

Um work-item `SUCCESS` com run `PARTIAL` por `SMALL_GROUP_BELOW_NORMAL_MINIMUM` não é tratado como falha. A página explica que a coleta concluiu, mas a leitura permanece parcial por população abaixo do mínimo metodológico.

### CAT-07 - Apdex de experiência

A tabela de amostras mantém:

- `captured_at` apresentado como data/hora da medição no timezone de apresentação;
- para novas execuções, o timestamp é registrado individualmente quando cada amostra conclui sua coleta, antes da persistência posterior em lote;
- quando existe aquisição compartilhada, o relatório também pode usar `synthetic_apdex_acquisitions.created_at` como proveniência do instante de coleta;
- amostras coletadas em momentos diferentes deixam de herdar o mesmo horário apenas porque foram inseridas juntas no SQLite;
- LCP e contagem de requests com falha entre as colunas principais;
- ordenação client-side aplicada sobre o dataset inteiro antes da paginação;
- paginação de 10 registros por página;
- apresentação separada de `Apdex por duração` e `Apdex efetivo`, além da contagem de amostras forçadas por erro.

A política de erro também foi corrigida. No escopo `first-party`, erros de console/JavaScript sem origem própria confiável permanecem diagnósticos e não forçam `Frustrada`. Somente falhas de requisição/HTTP atribuídas a recursos próprios, além de erro da navegação/aplicação quando aplicável, podem forçar a classificação. O escopo `all` continua disponível como política estrita explícita.

Isso elimina o caso em que todas as amostras eram classificadas como frustradas apenas por ruído de terceiros, apesar de a duração isolada produzir um Apdex alto.

### Estado lógico x auditoria-base

O topo das páginas passa a expor separadamente:

- `Resultado lógico da AUD`, derivado do fulfillment final;
- `Auditoria-base`, derivada de `audits.completion_status`/`status`.

Assim, uma execução pode estar logicamente `Concluída` e, ao mesmo tempo, preservar `Concluído com limitações` na auditoria-base. Quando `audits.limitations` contém uma limitação conhecida, ela é apresentada de forma legível, por exemplo `Lacuna na descoberta renderizada: 10`, sem achatar a informação para um único estado verde.

O aviso completo da limitação da auditoria-base fica concentrado nas páginas de visão geral/captura. Nos CATs, a limitação aparece de forma compacta com referência para os detalhes, evitando repetir o mesmo bloco extenso em todas as páginas.

### CAT-08 - Análise profunda

CAT-08 projeta os findings finais persistidos, sua distribuição por domínio, severidade, origem/CAT e vínculo com recomendações.

Quando houver menos recomendações que findings, a página mostra quantos achados não possuem remediação individual e, quando aplicável, explica o limite `max_recommendations`. Um finding sem recomendação não recebe correção inventada.

Se a etapa for solicitada mas falhar sem resultado funcional, a página mostra rastreabilidade de provider/modelo/tentativa/erro/fallback em vez de apenas `sem resultado`.

Quando CAT-08 exige IA, `IMPROVEMENT_INTELLIGENCE` passa a ser work-item obrigatório do fulfillment. Uma execução `COMPLETE_WITH_LIMITATIONS`, falha de contrato ou indisponibilidade dos providers não pode mais coexistir com CAT-08 apresentado como `CONCLUÍDO` integral. O catálogo é projetado como parcial/falho conforme o estado persistido e o fulfillment mantém a pendência reprocessável.

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
- quando nenhum dado estruturado foi observado, a sugestão é `Considerar implementar dados estruturados aplicáveis`, e não `Corrigir sintaxe`;
- quando a dimensão `STRUCTURED_DATA` está `NOT_APPLICABLE` por ausência observada e a política metodológica é `NOT_APPLICABLE_WHEN_ABSENT`, o SARI apresenta `Não aplicável — nenhum dado estruturado foi observado`, e não `Sem dados para estimar`.

### Captura e contexto

A captura visual persistida tem preview na própria página, com dispositivo, data/hora e viewport. O clique abre uma modal específica somente daquela imagem. O modal geral de contexto não vira depósito visual da captura.

### Linguagem humana

Estados e níveis usados na camada principal são humanizados. Códigos internos continuam permitidos apenas em detalhes técnicos/proveniência ou no payload bruto original. Valores em português como `CRÍTICO` também são normalizados sem perder acentuação legível.

A revisão cobre também valores vindos do banco que antes escapavam como enums/termos ingleses em tabelas portuguesas, incluindo estados de execução, componentes, dispositivo móvel e categorias genéricas de qualidade web. Nomes de produto, padrões, siglas e identificadores técnicos oficiais não são traduzidos artificialmente.

Para novas auditorias, os nomes e condições esperadas das regras semânticas `BR-GEO-028..049` passam a ser persistidos com texto humano em pt-BR. Isso evita propagar frases inglesas para CAT-03, CAT-08, CAT-09 e causas-raiz. O texto técnico bruto de uma fonte externa permanece preservado quando necessário para rastreabilidade.

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
- `freshness=FINAL` somente é válido depois da última persistência da cadeia de execução local;
- a auditoria não deve anunciar os relatórios HTML como completos quando o gate final de materialização/freshness do `report-catalog` falhar;
- CAT-08 obrigatório não pode ser omitido do fulfillment nem projetado como conclusão integral quando a análise profunda terminou com limitações.
