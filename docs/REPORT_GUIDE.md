# Guia de leitura dos relatórios

O SearchGEO gera um mini-site HTML estático por auditoria. O report é projeção humana derivada da persistência; não recalcula scoring nem inventa dados ausentes.

## Entrada principal

```text
report/index.html
```

A página inicial é o **dashboard executivo multimetodológico**. Ela resume somente os resultados finais disponíveis de cada indicador e direciona para a página analítica correspondente.

Princípios obrigatórios do `index.html`:

- não criar um score combinado entre metodologias diferentes;
- não somar nem ponderar SGRI, Core Web Vitals, Lighthouse, Accessibility, Apdex ou outcomes M26 entre si;
- mostrar somente síntese suficiente para decisão/navegação;
- deixar tabelas, evidências, percentis, URLs e metodologia detalhada na página canônica de cada domínio;
- ausência de dado deve permanecer `NÃO DISPONÍVEL`, `INCOMPLETO` ou estado equivalente; nunca virar zero ou aprovação.

## Estrutura

```text
report/
├─ index.html                  # dashboard executivo
├─ searchgeo.html              # SGRI-001 e indicadores proprietários SearchGEO
├─ mobile.html                 # evidências/findings Mobile, condicional
├─ desktop.html                # evidências/findings Desktop, condicional
├─ remediation.html
├─ content-suggestions.html
├─ crawling-discovery.html     # M24
├─ accessibility.html          # quando materializado
├─ web-performance.html
├─ apdex.html                  # M23, quando habilitado/materializado
├─ apdex-experience.html       # M25, quando habilitado/materializado
├─ ai-visibility.html          # M26, quando importado/regenerado
├─ ai-usage.html
├─ references.html
└─ css/site.css
```

## SearchGEO Readiness Index

`searchgeo.html` é a **página canônica e exclusiva dos indicadores agregados SearchGEO**.

A identidade pública da metodologia é:

```text
SGRI-001 — SearchGEO Readiness Index
```

Enquanto a aritmética não mudar, o banco preserva:

```text
SCORE-GEO-002
```

como versão do motor de cálculo persistido. Essa compatibilidade é intencional: a mudança de nomenclatura/apresentação não recalcula auditorias históricas, não altera pesos e não simula uma nova calibração empírica.

A página apresenta, por dispositivo aplicável:

- Overall Readiness;
- dimensões SearchGEO;
- Coverage;
- Confidence;
- Consolidation;
- versão metodológica pública e versão do motor persistido;
- proveniência das BR-GEO contribuintes;
- contexto editorial/YMYL quando persistido;
- conjunto de sinais de Groundability.

### Groundability

No `SGRI-001`, Groundability **não é um novo subscore**. Para evitar uma agregação adicional ainda não calibrada externamente, a página mostra separadamente os sinais existentes:

- Answerability;
- Citation Readiness;
- Evidence & Trust.

Um subscore específico só deve ser criado em versão metodológica futura se houver fórmula documentada, validação e versionamento próprios.

### Limite de validade do SGRI-001

O SGRI-001 é metodologia proprietária, evidence-based e reprodutível. Não representa:

- nota oficial do Google, Bing, OpenAI ou outro mecanismo;
- probabilidade estatística de ranking;
- probabilidade de citação por IA;
- certificação de GEO/AEO;
- substituto de métricas externas ou outcomes observados.

Fontes oficiais sustentam os fenômenos observados; elas não homologam automaticamente a agregação SearchGEO.

## Evidências Mobile e Desktop

`mobile.html` e `desktop.html` são páginas de **evidência e findings por dispositivo**.

Elas não devem repetir:

- Overall Readiness;
- Score por dimensão;
- Coverage;
- Confidence;
- Consolidation.

Esses indicadores pertencem exclusivamente a `searchgeo.html`. Mobile/Desktop preservam URLs, snapshots, findings, RuleExecutions, evidências e avaliações semânticas necessárias ao diagnóstico.

## Regra de não duplicação de indicadores

Cada indicador tem uma página analítica canônica:

| Indicador/domínio | Página canônica | Fonte metodológica |
| --- | --- | --- |
| SearchGEO Readiness Index / dimensões | `searchgeo.html` | SearchGEO — SGRI-001 / motor SCORE-GEO-002 |
| Crawling/Discovery/AI Access | `crawling-discovery.html` | standards/guidance + diagnóstico SearchGEO M24 |
| Core Web Vitals | `web-performance.html` | Chrome / web.dev |
| Lighthouse Performance | `web-performance.html` | Chrome Lighthouse |
| Lighthouse Accessibility | `accessibility.html` | Chrome Lighthouse |
| WCAG | `accessibility.html` | W3C; não é certificada apenas por automação |
| Synthetic Navigation Apdex | `apdex.html` | Apdex Technical Specification + coleta sintética M23 |
| Synthetic User Experience Apdex | `apdex-experience.html` | Apdex + contrato/calibração sintética M25; não é RUM |
| Observed Generative Visibility | `ai-visibility.html` | fonte observada/importada + protocolo M26 |
| Uso/custo de IA | `ai-usage.html` | telemetria operacional do provider/SearchGEO |

O `index.html` pode repetir **somente a síntese final necessária ao dashboard**, sempre acompanhada de link para a página canônica. Uma página especializada pode referenciar outra métrica para contexto, mas não deve republicar seu score, percentis ou tabela como se fossem parte do próprio domínio.

## Readiness ≠ Observed Generative Visibility

`ai-visibility.html` pertence ao M26 e é deliberadamente separado de `searchgeo.html`.

A distinção é:

```text
Readiness
= condições técnicas, semânticas e evidenciais inferidas pela auditoria

Observed Generative Visibility
= outcomes efetivamente observados/importados numa fonte ou protocolo identificado
```

O M26 não altera `SGRI-001`/`SCORE-GEO-002` e não converte citações em score GEO.

A página pode apresentar, conforme o dataset:

- Total Citations reportado pela fonte;
- Average Cited Pages reportado pela fonte;
- atividade/citações por URL;
- grounding queries;
- série temporal importada;
- query-runs controlados;
- Citation Presence Rate sobre runs válidos;
- tamanho amostral `n`;
- intervalo Wilson 95%;
- source/period/market/language;
- caminho do artifact e SHA-256.

### Métricas reportadas pela fonte

Quando um valor vem de uma plataforma — por exemplo Total Citations do Bing AI Performance — o relatório o identifica como **métrica da fonte**. O SearchGEO não tenta reconstruir fórmula não publicada para afirmar equivalência.

### Citation Presence Rate

Quando existem query-runs controlados:

```text
Citation Presence Rate
= runs VALID com cited=true / total de runs VALID
```

Runs `INVALID` ficam fora do denominador. A taxa e o Wilson 95% descrevem a amostra registrada; não representam probabilidade de citação futura nem validam causalidade do SGRI.

### O que uma citação não significa

Citação observada não deve ser interpretada automaticamente como:

- ranking;
- autoridade universal;
- preferência global da engine;
- qualidade absoluta da página;
- garantia de nova citação;
- efeito causado exclusivamente por uma recomendação SearchGEO.

## Configuração × resultado obtido

A seção compara o que foi solicitado com o que realmente foi coletado/materializado.

Exemplos de estados legítimos:

```text
IA: não solicitada
IA: configurada, mas provider indisponível
Web Performance: SUCCESS
Web Performance: PARTIAL
Acessibilidade: NÃO OBTIDA — PageSpeed timeout
Synthetic Apdex: small-group
M25: não habilitado / calibrado / parcial
M26: nenhum dataset importado / dataset importado
```

A causa deve ser persistida e apresentada. Timeout, quota, HTTP, ausência de artifact ou falta de dado da fonte não são convertidos em problema do website.

## Crawling, Discovery & AI Access

`crawling-discovery.html` é a página canônica do M24. Ela concentra diagnóstico de robots/crawlers/sitemaps/discovery, `llms.txt` experimental e evidências correlatas sem recalcular o SGRI.

## Acessibilidade

`accessibility.html` apresenta somente evidência de acessibilidade automatizada realmente disponível no artifact Lighthouse.

Quando PageSpeed/Lighthouse falha, a página deve apresentar a causa concreta por URL/device, por exemplo:

```text
PageSpeed/Lighthouse falhou: TIMEOUTERROR
```

A página não representa certificação WCAG e não deve declarar conformidade com base somente no Lighthouse.

## Web Performance

`web-performance.html` reúne:

- status das tentativas PageSpeed;
- status das tentativas CrUX;
- Lighthouse lab quando disponível;
- Core Web Vitals de campo quando disponíveis;
- artifacts e limitações persistidas;
- diagnósticos técnicos de performance.

Synthetic Apdex não deve aparecer nessa página como métrica derivada de Lighthouse. Links para páginas Apdex são permitidos; conteúdo analítico de Apdex pertence aos domínios dedicados.

## Synthetic Navigation Apdex — M23

`apdex.html` apresenta:

- `T` e `4T`;
- Satisfied/Tolerating/Frustrated;
- amostras válidas/inválidas;
- tentativas;
- score Apdex;
- percentis e dispersão quando disponíveis;
- marcador `*` para small-group;
- rastreabilidade de perfil quando possível.

Apdex não é inferido de LCP, INP, CLS, FCP, TBT ou duração da chamada PageSpeed.

## Synthetic User Experience Apdex — M25

`apdex-experience.html` é o domínio sintético calibrável do M25. Ele pode usar KPM, thresholds, política de erros, session mode e mix de dispositivos explícitos/importados.

Mesmo quando calibrado contra configuração Dynatrace, continua sendo **sintético, não RUM**. O M25 não substitui o M23 e não reescreve seu resultado.

## Uso de IA

`ai-usage.html` apresenta finalidades de IA em linguagem funcional, incluindo:

- provider/modelo;
- esforço efetivo quando persistido;
- tentativas/sucessos;
- tokens;
- custo estimado;
- status/diagnóstico sanitizado.

Rótulos históricos de marcos não devem ser usados como nomes de funcionalidade na interface pública.

## Conteúdo e JSON-LD

`content-suggestions.html` reúne contexto editorial, sugestões advisory e revisão/proposta estruturada. Nenhuma sugestão deve ser tratada como alteração automática do website.

YMYL e E-E-A-T condicionam o rigor da análise quando configurados/inferidos, mas não criam um score oficial ou paralelo.

## Remediações

`remediation.html` agrupa findings por causa/ação e deve preservar selector/evidência somente quando realmente observados.

## Referências

`references.html` documenta base metodológica, proveniência e fontes públicas relevantes. A existência de uma referência não transforma uma prática em requisito universal de GEO/AEO nem homologa o SGRI-001.

O M26 também exibe em sua própria página as referências necessárias para interpretar a fonte observacional, sem transformar documentação do Bing ou de outra plataforma em homologação do SearchGEO.

## Consistência visual

Todas as páginas devem compartilhar:

- mesma navegação e ordem dos links;
- item atual selecionado;
- largura de conteúdo equilibrada;
- cards com acabamento consistente;
- tabelas legíveis e sem arredondamento excessivo;
- footer como último elemento do conteúdo principal;
- comportamento responsivo desktop/tablet/mobile.

## Falha de coleta/importação

Quando uma integração configurada falha, o report deve responder quatro perguntas:

1. foi solicitada?
2. houve tentativa?
3. qual foi o status/erro?
4. qual informação ficou indisponível por causa disso?

No M26, erro de contrato, origin divergente ou JSON inválido deve rejeitar a importação; não deve ser convertido em outcome válido.

Isso evita confundir ausência de evidence com resultado positivo, negativo ou zero.

## Fonte de verdade

Prioridade de evidência:

```text
audit.db + artifacts + audit.log
→ projeção HTML
```

Para M26, o JSON normalizado preservado em `artifacts/m26/` mais seu SHA-256 fazem parte da rastreabilidade da origem importada.

O HTML não deve criar uma segunda fonte de verdade para scores, outcomes, telemetria, tokens, custos ou estado de coleta.