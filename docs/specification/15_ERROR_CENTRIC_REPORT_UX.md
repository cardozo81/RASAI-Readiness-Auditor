# ERROR_CENTRIC_REPORT_UX.md

**Status:** APPROVED — M15 historical contract evolved by REPORT-SITE-GEO-001 + M20/M21/M22/M23

## 1. Objetivo

M15 introduziu uma visão orientada a problemas além da visão orientada a página. A evolução REPORT-SITE-GEO-001 preserva o princípio de separação por domínio, mas substitui o contrato público de dois HTMLs soltos por um mini-site estático.

A UX do report deve privilegiar **decisão e interpretação**, não volume de informação. Dados detalhados continuam disponíveis por expansão, atalhos e páginas especializadas sem duplicar telemetria desnecessariamente.

## 2. Contrato final de saída

O conjunto efetivamente materializado depende das capacidades executadas, mas segue o mesmo mini-site:

```text
<AUD-ID>/
├─ audit.db
├─ artifacts/
└─ report/
   ├─ index.html
   ├─ mobile.html                 # quando aplicável
   ├─ desktop.html                # quando aplicável
   ├─ remediation.html
   ├─ content-suggestions.html    # M20
   ├─ ai-usage.html
   ├─ references.html
   ├─ accessibility.html          # quando materializada
   ├─ web-performance.html        # quando materializada
   └─ css/
      └─ site.css
```

Outras páginas aditivas aprovadas devem obedecer ao mesmo contrato visual/navegacional e aparecer no menu somente quando materializadas.

`report.html` e `remediation.html` na raiz não são mais contrato público final. Podem existir apenas transitoriamente durante a orquestração interna e devem ser removidos após finalização bem-sucedida do report site.

## 3. Navegação

Todas as páginas finais devem compartilhar:

- mesma arquitetura e ordem de menu;
- mesmo stylesheet externo;
- mesma área estrutural de conteúdo;
- estados visuais semanticamente consistentes;
- item ativo correspondente à página atual.

O menu deve ser produzido/normalizado pelo componente comum de navegação e conter apenas páginas materializadas. Ex.: `desktop.html` não deve aparecer em auditoria Mobile-only.

Páginas com múltiplas seções analíticas relevantes devem oferecer **atalhos internos contextuais** próximos ao topo. Esses atalhos não substituem o menu global; servem para reduzir rolagem e localizar blocos como metodologia, contexto, telemetria, findings ou referências.

## 4. Regra transversal de contexto da tela

Cada HTML final deve permitir que um analista entenda, sem consultar o código:

1. **o que a tela mede ou projeta**;
2. **qual é a fonte dos dados**;
3. **o que o estado/valor significa**;
4. **o que ele não significa**, quando houver risco material de interpretação incorreta;
5. **qual ação ou página de detalhe é relevante**, quando aplicável.

Aplicação esperada:

- título e lead curtos explicam a finalidade da tela;
- labels devem usar linguagem de produto/analista, evitando identificador interno isolado;
- códigos internos (`BR-GEO-*`, reason codes, score versions) podem aparecer para rastreabilidade, mas com explicação contextual ou acesso rápido à metodologia;
- ausência de coleta deve ser descrita como `não coletado`, `não solicitado`, `indisponível` ou estado equivalente correto, nunca como defeito implícito do website.

O report não deve repetir longos blocos de documentação em todas as páginas. Quando o detalhe metodológico já existe em `references.html` ou outra tela especializada, use uma explicação curta e um link de atalho.

## 5. Tooltips e ajuda contextual

Tooltips/help text são obrigatórios quando um termo compacto puder ser razoavelmente mal interpretado e a explicação completa poluiria a tela.

Exemplos:

- Confidence vs confiança de uma sugestão de IA;
- Coverage;
- Consolidation;
- YMYL/E-E-A-T context;
- `AUTO` inferido vs valor configurado;
- custo estimado vs invoice;
- lab data vs field data;
- Synthetic Apdex e threshold T;
- reason codes `BR-GEO-*` quando exibidos de forma resumida.

Regras:

1. tooltip complementa um label legível; não pode ser a única forma de entender o campo;
2. usar mecanismo nativo/acessível sempre que possível (`title`, `aria-describedby`, `details/summary` ou componente equivalente sem dependência externa);
3. informação crítica para decisão não pode existir somente no hover, pois touch/teclado/impressão podem não expor hover;
4. texto deve ser curto, específico e consistente com a documentação normativa;
5. tooltip não pode inventar causalidade, ranking ou interpretação que a métrica não sustenta.

## 6. Visão geral

`index.html` é dashboard executivo.

Conteúdo prioritário:

- dispositivo(s) efetivamente auditado(s);
- Overall quando consolidado;
- Coverage;
- Confidence;
- Consolidation;
- dimensões;
- contagens acionáveis;
- ligação para domínios de detalhe.

Não deve concentrar toda evidência, telemetria e remediação em uma página longa.

## 7. Mobile e Desktop

Resultados por dispositivo ficam separados:

```text
mobile.html
desktop.html
```

Cada página pode conter:

- scorecard do dispositivo;
- dimensões;
- páginas auditadas;
- screenshots;
- findings aplicáveis;
- avaliações semânticas relevantes.

Resultados do outro dispositivo não devem ser misturados.

## 8. Remediation

`remediation.html` é a visão orientada a problema/causa.

Deve preservar:

- agrupamento global versus página quando aplicável;
- actionability;
- prioridade;
- causa raiz;
- reason code;
- elemento/selector observado;
- alvo técnico;
- observado vs esperado;
- mudança recomendada;
- critérios de aceite;
- revalidação;
- decisão humana quando necessária.

Detalhes extensos podem ser colapsados com HTML nativo (`details/summary`) para reduzir ruído sem perder rastreabilidade.

Quando existir M20 para o mesmo audit, a página deve disponibilizar link claro para `content-suggestions.html` sem misturar sugestão editorial auxiliar com finding/scoring.

## 9. Conteúdo, contexto editorial e Structured Data

`content-suggestions.html` é a superfície de M20.

Deve manter a mesma identidade visual do report e mostrar prioritariamente:

- estado da remediação textual;
- contexto editorial/YMYL efetivamente aplicado e origem `CONFIGURADO`/`AUTO`;
- aviso quando classificação contextual depende de inferência;
- sugestões evidence-bound por página/device/finding;
- Structured Data/JSON-LD advisory;
- resumo da IA consumida nesta etapa;
- atalho para telemetria detalhada de IA;
- fontes oficiais relevantes.

Não deve virar um dumping de prompt, payload bruto ou documentação completa.

## 10. IA

Telemetria operacional não pertence à mesma hierarquia visual dos findings do site.

`ai-usage.html` deve conter, quando persistido/disponível:

- provider;
- modelo;
- reasoning profile;
- finalidade/etapa;
- status/tentativas;
- timestamps e duração;
- tokens input/cache/output/reasoning/total;
- custo estimado;
- moeda e versão de pricing quando aplicáveis;
- erro sanitizado.

Falha de IA não pode receber cor/mensagem de defeito do website.

Toda página que apresente resultado gerado por IA deve, no mínimo, permitir identificar **qual IA/modelo** gerou o conteúdo e oferecer acesso rápido à telemetria da respectiva etapa. Quando custo não puder ser calculado de modo sustentado pelo adapter/pricing conhecido, usar `Indisponível`, não zero fictício.

Configuração contextual de IA que não gera request por si só não deve ser contabilizada como custo externo.

## 11. Referências

`references.html` deve reunir:

- fontes primárias/standards;
- natureza da base de cada regra;
- fórmula de Score/Coverage/Confidence/Overall;
- avisos sobre heurísticas internas;
- distinção entre recomendações SearchGEO e requisitos oficiais.

Páginas especializadas podem apresentar 2–5 referências diretamente relevantes com links claros e encaminhar ao catálogo global quando houver material adicional.

Prioridade de fonte:

1. documentação oficial do mantenedor/provedor;
2. standard/RFC/especificação normativa;
3. documentação primária de projeto reconhecido;
4. fonte secundária somente quando necessária e identificada como tal.

Links externos devem usar destino público estável, `target='_blank'` quando abrir fora do report e `rel='noopener'`.

## 12. Tipografia

Requisitos:

- evitar heading excessivamente grande;
- negrito reservado a hierarquia/estado/valor importante;
- tabelas com tipografia compacta;
- texto de leitura com line-height confortável;
- detalhes técnicos longos recolhidos quando adequado;
- texto interno deve respeitar largura do container e usar wrapping seguro para URL/código/IDs.

## 13. Cores

Estados determinantes devem usar semântica estável:

- positivo: verde;
- atenção/parcial: âmbar;
- problema: vermelho;
- informação: azul;
- não determinado/indisponível: cinza.

Cor nunca substitui texto.

Métricas de integração/telemetria não devem herdar vermelho de finding apenas por falha externa. O domínio visual precisa distinguir **qualidade do site** de **limitação do auditor/provider**.

## 14. Layout

Desktop:

- navegação fixa;
- conteúdo deve descontar explicitamente a largura da navegação;
- tabelas largas usam overflow interno;
- nenhum bloco deve invadir a sidebar;
- containers usam bordas/raios sutis e espaçamento consistente.

Mobile:

- navegação pode virar barra sticky/horizontal;
- conteúdo ocupa 100%;
- grids colapsam para uma coluna quando necessário;
- informação dependente exclusivamente de hover é proibida.

## 15. CSS

Contrato final:

```text
report/css/site.css
```

Proibido no report site final:

- `<style>` duplicado em cada página;
- CSS estrutural inline;
- dependência de CDN obrigatória;
- criação independente de menu/paleta por página especializada.

Novas páginas devem reutilizar classes/componentes existentes sempre que suficientes. Mudança de design transversal deve ser feita no core/shared CSS para evitar deriva visual.

## 16. Score e reliability

A UI deve explicar:

- Score = qualidade observada na parcela avaliada;
- Coverage = quanto do universo aplicável foi avaliado;
- Confidence = força da conclusão;
- Consolidation = se o resultado é publicável como consolidado.

`Confidence LOW` não significa baixa qualidade textual e não autoriza ordem de reescrita sem finding específico.

Confidence devolvida por um LLM para uma avaliação/sugestão individual não é a mesma métrica que Confidence consolidada do auditor.

## 17. Thresholds

As faixas visuais de score são internas ao SearchGEO. A UI/metodologia deve evitar linguagem que sugira certificação oficial GEO/AEO.

Threshold, target, benchmark ou classificação interna deve expor sua origem quando não for autoexplicativa:

- standard oficial;
- documentação do fornecedor;
- parâmetro configurado pelo usuário;
- heurística/versionamento interno do SearchGEO.

## 18. Fontes externas

A fundamentação atual deve reconhecer o guia do Google para recursos generativos de Search e não inventar requisitos especiais de GEO/AEO. Structured Data, chunking, `llms.txt` e escrita “para IA” não podem ser apresentados como requisitos universais quando a fonte oficial não os exige.

E-E-A-T/YMYL podem ser usados como contexto conceitual documentado, mas não como percentual oficial, garantia de ranking ou score homologado. Quando usados, a tela deve diferenciar contexto configurado de inferência automática.

## 19. Fonte de verdade

O report site é projeção sobre dados persistidos. Não recalcula findings, scores, recommendations nem executa IA.

Consequências:

- valores, contexto, telemetria e custos exibidos devem vir de dados persistidos/artifacts da execução;
- HTML não pode consultar provider externo para “completar” uma tela;
- HTML não pode recalcular score ou transformar ausência em zero;
- uma informação que dependa de configuração efetiva relevante para interpretação deve ser persistida antes de ser tratada como fato no report.

## 20. Critério de aceite transversal

Uma nova página HTML ou mudança relevante de report não está concluída enquanto não houver validação de:

1. navegação compartilhada e item ativo correto;
2. stylesheet compartilhado e ausência de deriva visual material;
3. largura/wrapping/responsividade;
4. texto curto de finalidade/contexto;
5. estados semânticos corretos;
6. atalhos internos quando a página possui várias seções relevantes;
7. tooltip/help para termos compactos de interpretação ambígua;
8. referências oficiais/primárias quando a tela afirma uma recomendação externa;
9. telemetria completa quando a tela utiliza IA;
10. separação entre website finding e limitação de integração/auditor;
11. ausência de segredo, payload sensível ou prompt interno desnecessário;
12. smoke em HTML gerado com conteúdo suficiente para verificar menu, links e responsividade básica.

## 17. Proveniência metodológica dos indicadores

Toda página final deve informar, de forma compacta e visível, a natureza dos indicadores centrais exibidos. `references.html` deve consolidar indicador, classificação metodológica, fonte/entidade, link oficial quando existir, lógica externa aplicável e decisão/transformação específica do SearchGEO.

Taxonomia pública mínima: `RAW_OBSERVATION`, `EXTERNAL_STANDARD`, `OFFICIAL_PLATFORM_GUIDANCE`, `EXTERNAL_DEFINED_METRIC`, `SEARCHGEO_HEURISTIC`, `OPERATIONAL_TELEMETRY` e `AI_DERIVED_ADVISORY`.

Informação metodológica essencial não pode depender somente de tooltip. Uma fonte oficial valida apenas o fenômeno no seu escopo e nunca deve ser usada para sugerir homologação externa do `SCORE-GEO-002`.

