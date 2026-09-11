# Experiência e organização dos relatórios orientada a problemas

**Estado no baseline de desenvolvimento:** aprovado / vigente para a experiência e organização do site estático de relatórios.

## 1. Objetivo

O contrato de relatórios oferece, além da visão por página, uma visão orientada a problemas, causas e decisões. A UX deve privilegiar **decisão e interpretação**, não volume de informação. Dados detalhados continuam disponíveis por expansão, atalhos e páginas especializadas sem duplicar telemetria desnecessariamente.

O relatório é uma projeção de dados persistidos. Não é fonte de verdade nem reexecuta auditoria, scoring, crawling ou IA.

## 2. Contrato atual de saída

O conjunto materializado depende das capacidades efetivamente executadas e da disponibilidade de evidência, mas usa o mesmo site estático:

```text
<AUD-ID>/
├─ audit.db
├─ artifacts/
└─ report/
   ├─ index.html
   ├─ readiness.html
   ├─ scoring.html
   ├─ mobile.html                  # quando aplicável
   ├─ desktop.html                 # quando aplicável
   ├─ remediation.html
   ├─ content-suggestions.html     # quando aplicável
   ├─ crawling-discovery.html      # quando aplicável
   ├─ accessibility.html           # quando materializada
   ├─ web-performance.html         # quando materializada
   ├─ apdex.html                   # quando materializada
   ├─ apdex-experience.html        # quando materializada
   ├─ search-intelligence.html     # quando materializada
   ├─ ai-visibility.html           # quando materializada
   ├─ observability.html           # quando materializada
   ├─ quality.html                 # quando materializada
   ├─ ai-usage.html
   ├─ references.html
   └─ css/
      └─ site.css
```

Páginas opcionais devem aparecer no menu somente quando materializadas. A versão do scoring pertence a `scoring_version` e ao conteúdo de `scoring.html`, não ao nome físico da página canônica.

Arquivos HTML transitórios usados internamente durante orquestração não integram o contrato público final.

## 3. Navegação

Todas as páginas finais devem compartilhar:

- mesma arquitetura e ordem de menu;
- mesmo stylesheet externo;
- mesma área estrutural de conteúdo;
- estados visuais semanticamente consistentes;
- item ativo correspondente à página atual.

O menu deve ser produzido/normalizado pelo componente comum de navegação e conter apenas páginas materializadas. Exemplo: `desktop.html` não deve aparecer em auditoria somente Mobile.

Páginas com múltiplas seções analíticas relevantes devem oferecer **atalhos internos contextuais** próximos ao topo. Eles não substituem o menu global; servem para reduzir rolagem e localizar metodologia, contexto, telemetria, findings ou referências.

## 4. Regra transversal de contexto da tela

Cada HTML final deve permitir que um analista entenda, sem consultar o código:

1. o que a tela mede ou projeta;
2. qual é a fonte dos dados;
3. o que o estado/valor significa;
4. o que ele não significa quando houver risco material de interpretação incorreta;
5. qual ação ou página de detalhe é relevante, quando aplicável.

Aplicação esperada:

- título e introdução curtos explicam a finalidade da tela;
- rótulos usam linguagem de produto/analista, evitando identificador interno isolado;
- códigos internos (`BR-GEO-*`, reason codes, `scoring_version`) podem aparecer para rastreabilidade, mas acompanhados de contexto ou acesso rápido à metodologia;
- ausência de coleta deve ser descrita como `não coletado`, `não solicitado`, `indisponível` ou estado equivalente correto, nunca como defeito implícito do website.

O relatório não deve repetir longos blocos de documentação em todas as páginas. Quando o detalhe metodológico já existe em `references.html` ou outra tela especializada, usar explicação curta e link de atalho.

## 5. Tooltips e ajuda contextual

Tooltips/help text são indicados quando um termo compacto puder ser razoavelmente mal interpretado e a explicação completa poluiria a tela.

Exemplos:

- Confidence versus confiança de uma sugestão de IA;
- Coverage;
- Consolidation;
- contexto YMYL/E-E-A-T;
- `AUTO` inferido versus valor configurado;
- custo estimado versus cobrança real;
- dados de laboratório versus dados de campo;
- Synthetic Apdex e threshold `T`;
- reason codes `BR-GEO-*` quando exibidos de forma resumida.

Regras:

1. tooltip complementa rótulo legível; não pode ser a única forma de entender o campo;
2. usar mecanismo nativo/acessível sempre que possível (`title`, `aria-describedby`, `details/summary` ou equivalente sem dependência externa);
3. informação crítica para decisão não pode existir somente no hover;
4. o texto deve ser curto, específico e consistente com a documentação normativa;
5. tooltip não pode inventar causalidade, ranking ou interpretação que a métrica não sustenta.

## 6. Visão geral

`index.html` é a visão executiva.

Conteúdo prioritário:

- dispositivo(s) efetivamente auditado(s);
- Overall quando calculável/consolidado conforme o contrato;
- Coverage;
- Confidence;
- Consolidation;
- dimensões;
- contagens acionáveis;
- links para domínios de detalhe.

Não deve concentrar toda evidência, telemetria e remediação em uma única página extensa.

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

## 8. Remediação

`remediation.html` é a visão orientada a problema/causa.

Deve preservar:

- agrupamento global versus página quando aplicável;
- Actionability;
- Priority;
- Root Cause;
- reason code;
- elemento/seletor observado;
- alvo técnico;
- observado versus esperado;
- mudança recomendada;
- critérios de aceite;
- revalidação;
- decisão humana quando necessária.

Termos técnicos persistidos podem permanecer em inglês; a explicação ao redor deve estar em pt-BR.

Detalhes extensos podem ser recolhidos com HTML nativo (`details/summary`) para reduzir ruído sem perder rastreabilidade.

Quando existirem sugestões/remediação de conteúdo por IA para a mesma auditoria, a página deve disponibilizar link claro para `content-suggestions.html` sem misturar sugestão editorial auxiliar com finding/scoring.

## 9. Conteúdo, contexto editorial e Structured Data

`content-suggestions.html` é a superfície de sugestões/remediação de conteúdo por IA.

Deve mostrar prioritariamente:

- estado da remediação textual;
- contexto editorial/YMYL efetivamente aplicado e origem `CONFIGURADO`/`AUTO`;
- aviso quando classificação contextual depender de inferência;
- sugestões vinculadas a evidências por página/dispositivo/finding;
- orientação de Structured Data/JSON-LD;
- resumo da IA consumida nesta etapa;
- atalho para telemetria detalhada de IA;
- fontes oficiais relevantes.

Não deve virar despejo de prompt, payload bruto ou documentação completa.

## 10. IA

Telemetria operacional não pertence à mesma hierarquia visual dos findings do site.

`ai-usage.html` deve conter, quando persistido/disponível:

- provider;
- modelo;
- reasoning profile;
- finalidade/etapa;
- status/tentativas;
- timestamps e duração;
- tokens de entrada/cache/saída/reasoning/total;
- custo estimado;
- moeda e versão de pricing quando aplicáveis;
- erro sanitizado.

Falha de IA não pode receber cor/mensagem de defeito do website.

Toda página que apresente resultado gerado por IA deve permitir identificar **qual provider/modelo** gerou o conteúdo e oferecer acesso rápido à telemetria da respectiva etapa. Quando custo não puder ser calculado de modo sustentado pelo adapter/preço conhecido, usar `Indisponível`, não zero fictício.

Configuração contextual de IA que não gera request por si só não deve ser contabilizada como custo externo.

## 11. Referências

`references.html` deve reunir:

- fontes primárias/standards;
- natureza da base de cada regra;
- fórmula de Score/Coverage/Confidence/Overall;
- avisos sobre heurísticas internas;
- distinção entre recomendações RASAi e requisitos oficiais.

Páginas especializadas podem apresentar referências diretamente relevantes e encaminhar ao catálogo global quando houver material adicional.

Prioridade de fonte:

1. documentação oficial do mantenedor/provider;
2. standard/RFC/especificação normativa;
3. documentação primária de projeto reconhecido;
4. fonte secundária somente quando necessária e identificada como tal.

Links externos devem usar destino público estável e controles apropriados quando abrirem fora do relatório.

Quando for necessário reproduzir trecho externo não pt-BR, usar o padrão definido em `docs/README.md`: **Disclaimer - texto original da fonte** seguido de **Tradução/adaptação pt-BR**, reproduzindo somente o trecho necessário.

## 12. Tipografia

Requisitos:

- evitar heading excessivamente grande;
- usar negrito para hierarquia/estado/valor importante, sem excesso;
- tabelas com tipografia compacta;
- texto de leitura com `line-height` confortável;
- detalhes técnicos longos recolhidos quando adequado;
- conteúdo deve respeitar largura do container e usar wrapping seguro para URL/código/IDs.

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

- navegação fixa quando aplicável ao layout atual;
- conteúdo deve descontar a largura da navegação;
- tabelas largas usam overflow interno;
- nenhum bloco deve invadir a barra lateral;
- containers usam bordas/raios e espaçamento consistentes.

Mobile:

- navegação pode virar barra sticky/horizontal;
- conteúdo ocupa a largura disponível;
- grids colapsam para uma coluna quando necessário;
- informação dependente exclusivamente de hover é proibida.

## 15. CSS

Contrato final:

```text
report/css/site.css
```

Evitar no site final:

- `<style>` estrutural duplicado em cada página;
- CSS estrutural inline desnecessário;
- dependência obrigatória de CDN;
- criação independente de menu/paleta por página especializada.

Novas páginas devem reutilizar classes/componentes existentes sempre que suficientes. Mudança de design transversal deve ser feita no CSS compartilhado para evitar deriva visual.

## 16. Score e confiabilidade

A UI deve explicar:

- Score = qualidade observada na parcela avaliada;
- Coverage = quanto do universo aplicável foi avaliado;
- Confidence = força da conclusão;
- Consolidation = se o resultado é publicável como consolidado.

`Confidence LOW` não significa baixa qualidade textual e não autoriza ordem de reescrita sem finding específico.

Confidence devolvida por LLM para avaliação/sugestão individual não é a mesma métrica que Confidence consolidada do auditor.

## 17. Limiares

As faixas visuais de score são internas ao RASAi e não são parâmetros livres por auditoria. A UI/metodologia deve evitar linguagem que sugira certificação oficial GEO/AEO.

Threshold, target, benchmark ou classificação interna deve expor sua origem quando não for autoexplicativa:

- standard oficial;
- documentação do fornecedor;
- parâmetro configurado pelo usuário;
- heurística/versionamento interno do RASAi.

Quando um valor for configurável, a documentação correspondente deve indicar default efetivo, valores permitidos e recomendado. Quando for fixo metodológico, deve ser identificado como fixo/versionado.

## 18. Fontes externas

A fundamentação atual deve reconhecer a documentação oficial aplicável e não inventar requisitos especiais de GEO/AEO. Structured Data, chunking, `llms.txt` e escrita “para IA” não podem ser apresentados como requisitos universais quando a fonte oficial não os exige.

E-E-A-T/YMYL podem ser usados como contexto conceitual documentado, mas não como percentual oficial, garantia de ranking ou score homologado. Quando usados, a tela deve diferenciar contexto configurado de inferência automática.

## 19. Fonte de verdade

O site de relatório é projeção sobre dados persistidos. Não recalcula findings, scores, recommendations nem executa IA.

Consequências:

- valores, contexto, telemetria e custos exibidos devem vir de dados persistidos/artefatos da execução;
- HTML não pode consultar provider externo para “completar” tela;
- HTML não pode recalcular score nem transformar ausência em zero;
- informação dependente de configuração efetiva relevante para interpretação deve ser persistida antes de ser tratada como fato no relatório.

## 20. Critério de aceite transversal

Uma nova página HTML ou mudança relevante de relatório só está completa após validação de:

1. navegação compartilhada e item ativo correto;
2. stylesheet compartilhado e ausência de deriva visual material;
3. largura/wrapping/responsividade;
4. texto curto de finalidade/contexto;
5. estados semânticos corretos;
6. atalhos internos quando a página possui várias seções relevantes;
7. tooltip/help para termos compactos de interpretação ambígua;
8. referências oficiais/primárias quando a tela afirma recomendação externa;
9. telemetria completa quando a tela utiliza IA;
10. separação entre website finding e limitação de integração/auditor;
11. ausência de segredo, payload sensível ou prompt interno desnecessário;
12. smoke em HTML gerado com conteúdo suficiente para verificar menu, links e responsividade básica.

## 21. Proveniência metodológica dos indicadores

Toda página final deve informar, de forma compacta e visível, a natureza dos indicadores centrais exibidos. `references.html` deve consolidar indicador, classificação metodológica, fonte/entidade, link oficial quando existir, lógica externa aplicável e decisão/transformação específica do RASAi.

Taxonomia pública mínima:

```text
RAW_OBSERVATION
EXTERNAL_STANDARD
OFFICIAL_PLATFORM_GUIDANCE
EXTERNAL_DEFINED_METRIC
RASAI_HEURISTIC
OPERATIONAL_TELEMETRY
AI_DERIVED_ADVISORY
```

Informação metodológica essencial não pode depender somente de tooltip. Uma fonte oficial valida apenas o fenômeno no seu escopo e nunca deve ser usada para sugerir homologação externa do `SARI-001`.
