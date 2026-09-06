# Guia de leitura dos relatórios

O SearchGEO gera um mini-site HTML estático por auditoria. O report é projeção humana derivada da persistência; não recalcula scoring nem inventa dados ausentes.

## Entrada principal

```text
report/index.html
```

A página inicial é o **dashboard executivo multimetodológico**. Ela resume somente os resultados finais disponíveis de cada indicador e direciona para a página analítica correspondente.

Princípios obrigatórios do `index.html`:

- não criar um score combinado entre metodologias diferentes;
- não somar nem ponderar SGRI, Core Web Vitals, Lighthouse, Accessibility ou Apdex entre si;
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
├─ accessibility.html          # quando materializado
├─ web-performance.html
├─ apdex.html                  # quando habilitado/materializado
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
- substituto de métricas externas.

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
| Core Web Vitals | `web-performance.html` | Chrome / web.dev |
| Lighthouse Performance | `web-performance.html` | Chrome Lighthouse |
| Lighthouse Accessibility | `accessibility.html` | Chrome Lighthouse |
| WCAG | `accessibility.html` | W3C; não é certificada apenas por automação |
| Synthetic Navigation Apdex | `apdex.html` | Apdex Technical Specification |
| Uso/custo de IA | `ai-usage.html` | telemetria operacional do provider/SearchGEO |

O `index.html` pode repetir **somente a síntese final necessária ao dashboard**, sempre acompanhada de link para a página canônica. Uma página especializada pode referenciar outra métrica para contexto, mas não deve republicar seu score, percentis ou tabela como se fossem parte do próprio domínio.

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
```

A causa deve ser persistida e apresentada. Timeout, quota, HTTP, ausência de artifact ou falta de dado da fonte não são convertidos em problema do website.

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

Synthetic Apdex não deve aparecer nessa página como métrica derivada de Lighthouse. Um link para `apdex.html` é permitido; conteúdo analítico de Apdex pertence à página dedicada.

## Synthetic Apdex

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

## Consistência visual

Todas as páginas devem compartilhar:

- mesma navegação e ordem dos links;
- item atual selecionado;
- largura de conteúdo equilibrada;
- cards com acabamento consistente;
- tabelas legíveis e sem arredondamento excessivo;
- footer como último elemento do conteúdo principal;
- comportamento responsivo desktop/tablet/mobile.

## Falha de coleta

Quando uma integração configurada falha, o report deve responder quatro perguntas:

1. foi solicitada?
2. houve tentativa?
3. qual foi o status/erro?
4. qual informação ficou indisponível por causa disso?

Isso evita confundir ausência de evidence com resultado positivo, negativo ou zero.

## Fonte de verdade

Prioridade de evidência:

```text
audit.db + artifacts + audit.log
→ projeção HTML
```

O HTML não deve criar uma segunda fonte de verdade para scores, telemetria, tokens, custos ou estado de coleta.
