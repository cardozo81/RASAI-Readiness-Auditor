# Auditoria multi-URL, evidência visual/DOM e remediação acionável

## 1. Objetivo

A auditoria multi-URL com evidência visual evolui a cadeia persistida de auditoria — score, finding e remediação — para uma estrutura rastreável capaz de responder, a partir da evidência persistida: qual domínio e página foram auditados, qual snapshot Desktop/Mobile foi usado, qual elemento DOM foi observado quando determinável, qual evidência visual existe, qual ação é justificável, como a correção deve ser validada e qual autoridade técnica ou heurística interna sustenta a recomendação.

O relatório permanece uma projeção. O estado persistido da auditoria é a fonte de verdade.

## 2. Entrada `URL_SET`

Tanto um único target posicional quanto entrada explícita de múltiplos targets são suportados.

Uma sequência explícita de targets ou `--urls-file` cria `TargetType.URL_SET`, mesmo que normalização/remoção de duplicatas resulte em uma única URL. O universo explícito de páginas não pode fazer fallback silencioso para expansão por descoberta comum.

Para `URL_SET`:

- normalizar URLs pela política de URL do projeto;
- preservar a sequência ordenada e sem duplicatas de URLs normalizadas;
- preservar separadamente a quantidade bruta informada e a quantidade única normalizada;
- rejeitar URLs inválidas antes da aquisição;
- rejeitar targets fora da mesma origem normalizada antes da aquisição;
- exigir `max_pages` suficiente para todas as URLs explícitas únicas;
- criar um único `audit_id` e um único workspace;
- persistir todas as páginas nessa auditoria;
- manter Desktop e Mobile como registros `PageSnapshot` independentes.

## 3. Recursos de domínio

`robots.txt` e recursos de sitemap são evidências em escopo de domínio. São adquiridos uma vez por execução de auditoria/domínio, e não uma vez por página.

Arquitetura:

```text
Audit
├── contexto de domínio
│   ├── robots.txt
│   ├── sitemap(s)
│   └── Evidence em nível de domínio
└── Pages
    ├── Page
    │   ├── Desktop PageSnapshot
    │   └── Mobile PageSnapshot
    └── ...
```

Evidência em nível de domínio usa `page_id = null`, `snapshot_id = null`, `device = null`. Findings em nível de site não devem ser clonados em findings idênticos por página apenas porque várias URLs explícitas foram auditadas.

A evidência de sitemap registra no mínimo estado, origem da descoberta, aquisição HTTP, quantidade de URLs, URLs de páginas quando interpretáveis, referências a sitemaps filhos, redirects/evidência de rede pelo registro HTTP persistido e erro de parsing quando existente.

Ausência de `robots.txt` ou sitemap não é convertida automaticamente em `FAIL`, salvo quando uma Business Rule aprovada definir explicitamente esse resultado. `BR-GEO-003` continua proibindo falha automática de sitemap baseada apenas na ausência.

## 4. Três planos de evidência

A auditoria multi-URL com evidência visual preserva três planos distintos:

```text
RAW HTTP
→ bytes e resposta de protocolo recebidos do servidor

Rendered DOM
→ estado HTML/DOM após renderização JavaScript

Visual Snapshot
→ imagem do viewport observada pelo Chromium
```

Evidência visual nunca substitui evidência RAW nem rendered.

## 5. Snapshot visual

Para cada `PageSnapshot` renderizado válido, o Chromium tenta persistir um screenshot PNG do viewport dentro do workspace da auditoria usando caminho relativo.

Perfis de viewport, confirmados no runtime:

| Contexto | Default efetivo | Valores permitidos nesta implementação | Recomendado |
|---|---:|---|---|
| Desktop | `1440 × 900` | perfil Desktop canônico do renderer | manter o perfil canônico para comparabilidade |
| Mobile | `412 × 915` | perfil Mobile canônico do renderer | manter o perfil canônico para comparabilidade |

Os metadados permanecem vinculados ao mesmo snapshot e incluem URL solicitada, URL final, viewport, perfil de dispositivo, timestamp de captura e referência do artefato. Assets do relatório devem permanecer locais ao workspace/ZIP da auditoria; dependência remota de imagem não é permitida.

Falha na captura do screenshot deve ser representada como limitação/estado de evidência e nunca pode fabricar uma imagem.

## 6. `ElementObservation`

A capacidade adiciona o conceito persistido e aditivo `ElementObservation`, contendo no mínimo:

- `element_observation_id`;
- `audit_id`;
- `page_id`;
- `snapshot_id`;
- `device`;
- URL;
- seletor CSS quando determinável;
- tag;
- ID do elemento;
- classes relevantes;
- `outer_html` limitado e sanitizado;
- trecho de texto limitado;
- bounding box quando o elemento está visível no viewport;
- referência de artefato local quando aplicável;
- timestamp de captura.

A implementação deve validar consistência entre auditoria, página, snapshot e dispositivo antes da persistência.

Limites atuais, confirmados no runtime:

| Campo | Default/limite efetivo | Valores permitidos | Recomendado |
|---|---:|---|---|
| `outer_html` | máximo `4096` caracteres | texto sanitizado até o limite | não ampliar sem necessidade de evidência e revisão de custo/tamanho |
| trecho de texto | máximo `512` caracteres | texto sanitizado até o limite | manter o limite atual |
| classes | máximo `12` | classes observadas e individualmente limitadas pelo contrato | persistir somente classes observadas e relevantes |
| seletor | limitado pelo contrato | apenas seletor realmente gerado do DOM observado | nunca inventar seletor quando não determinável |

Seletor ausente ou ambíguo permanece `NÃO DETERMINADO`. Nenhum seletor pode ser inventado a partir de um rótulo genérico de regra.

## 7. Vínculo entre finding e elemento

Um finding só pode ser vinculado a `ElementObservation` quando a regra e o snapshot persistido identificarem deterministicamente um único nó concreto.

Se houver zero ou múltiplos candidatos, o finding permanece no nível de documento/conjunto. Exemplo: hierarquia de headings pode representar relação entre vários nós; o auditor não deve escolher arbitrariamente um heading apenas para preencher o campo de seletor.

Quando uma observação vinculada possui bounding box visível válido e screenshot, o relatório pode destacar visualmente aquela área. Findings não visuais, como headers HTTP, estado de canonical/meta, JSON-LD fora do viewport, robots e sitemap, não exigem screenshot específico do finding.

## 8. Acionabilidade

Resultado técnico bruto e acionabilidade são conceitos independentes.

Valores normativos de acionabilidade:

| Valor persistido | Rótulo no relatório | Significado |
|---|---|---|
| `REQUIRED_FIX` | AÇÃO NECESSÁRIA | Defeito sustentado por evidência cuja remediação é exigida pela semântica da regra aplicável. |
| `REVIEW_RECOMMENDED` | REVISÃO RECOMENDADA | Condição contextual ou sensível a política que exige revisão humana antes de decidir alteração no site. |
| `OPTIONAL_IMPROVEMENT` | MELHORIA OPCIONAL | Capacidade/boa prática não bloqueante; não é defeito automático. |
| `NO_ACTION` | NENHUMA AÇÃO NECESSÁRIA | Condição aprovada ou não aplicável. |
| `INSUFFICIENT_EVIDENCE` | AÇÃO NO SITE NÃO DETERMINADA | Auditor/ferramenta não possui evidência suficiente; a ação deve tratar condições de evidência/auditoria, não inventar correção no site. |

Projeção determinística:

- `PASS` / `NOT_APPLICABLE` → `NO_ACTION`;
- `UNKNOWN` / `ERROR` de análise/ferramenta → `INSUFFICIENT_EVIDENCE`;
- `FAIL` → `REQUIRED_FIX`, salvo quando a semântica aprovada da regra exigir revisão contextual;
- `WARNING` → normalmente `REVIEW_RECOMMENDED`;
- ausência de capacidade opcional permanece `OPTIONAL_IMPROVEMENT` quando a regra a define explicitamente como não bloqueante.

Acionabilidade nunca altera `RuleResult`, contribuição de scoring, peso, score, Coverage, Confidence ou Consolidation.

## 9. Invariantes de scoring

Permanecem obrigatórios:

- `UNKNOWN != FAIL`;
- `ERROR != FAIL`;
- `NOT_APPLICABLE != FAIL`;
- ausência de IA não cria penalidade artificial;
- Coverage não é Score;
- Confidence não é Score;
- Desktop e Mobile são independentes;
- Overall só existe quando os critérios metodológicos de cálculo/consolidação forem atendidos.

### Zero versus ausência

O relatório deve representar distintamente:

```text
Score: 0.0
Estado: CALCULADO
```

versus:

```text
Score: NÃO DETERMINADO
Estado: NÃO CALCULADO
```

E, de forma independente:

```text
Coverage: 0%
```

Nenhum componente de relatório pode usar zero numérico como fallback para `None`/score ausente.

## 10. Referências técnicas

A capacidade usa projeção versionada de referências de regra. Fontes técnicas primárias/autoritativas devem ser preferidas quando sustentarem diretamente uma regra, incluindo, conforme aplicabilidade:

- IETF/RFC Editor;
- WHATWG;
- Google Search Central e documentação oficial de crawling do Google;
- Schema.org;
- documentação oficial da OpenAI sobre crawlers/publicadores;
- documentação oficial da tecnologia avaliada.

Uma regra heurística sem fonte normativa externa diretamente aplicável deve exibir explicitamente:

```text
Base: HEURISTIC
Fonte externa normativa: não aplicável / não identificada
Referência interna: BR-GEO-XXX
```

O auditor nunca pode fabricar autoridade externa.

Quando um trecho externo em idioma diferente de pt-BR precisar ser reproduzido na documentação, deve seguir a convenção de `docs/README.md`: **Disclaimer — texto original da fonte** seguido de **Tradução/adaptação pt-BR**. O trecho original deve ser limitado ao necessário para a referência; o RASAi não deve copiar integralmente uma obra externa apenas para documentar uma regra.

Links oficiais do catálogo de referências desta capacidade foram verificados na data registrada pelo respectivo contrato de referência persistido. Datas fixas de verificação não devem ser tratadas como garantia permanente de disponibilidade externa.

## 11. OAI-SearchBot e GPTBot

O relatório de política de crawlers deve manter `OAI-SearchBot` e `GPTBot` separados. Suas finalidades e controles não são intercambiáveis. A matriz também pode incluir crawlers como Googlebot, Googlebot Smartphone e Bingbot.

Nenhuma recomendação de negócio pode afirmar que permitir qualquer desses crawlers garante indexação, ranking, citação ou inclusão em respostas geradas.

## 12. Contrato de relatório — `REPORT-GEO-003`

O relatório deve conter visivelmente:

1. identificação executiva de projeto, `audit_id`, domínio, modo de entrada, quantidade bruta de URLs informadas, quantidade de páginas auditadas, horário, estado provider/modelo de IA e limitações;
2. compatibilidade GEO, Coverage, Confidence e Consolidation sem confluir esses conceitos;
3. distinção explícita entre Score zero e estado não calculado;
4. inventário com links das URLs auditadas;
5. recursos de domínio, incluindo estado de robots e sitemap;
6. legenda textual de status/acionabilidade;
7. ações necessárias e itens de revisão;
8. melhorias opcionais não bloqueantes separadas de defeitos;
9. projeções Desktop e Mobile de score/readiness quando metodologicamente disponíveis;
10. seções por página com URL em destaque, estados de snapshot, screenshots do viewport, findings, seletores/observações DOM quando determinísticos e detalhes de remediação;
11. plano priorizado de correção;
12. seções de semântica/entidade/intenção e citation/evidence-trust derivadas do estado persistido de análise semântica/fallback e remediação;
13. cobertura de crawl/`URL_SET` e limitações;
14. metodologia e glossário.

URLs longas, seletores, HTML, JSON, IDs e nomes de modelos devem permanecer dentro de seus containers. CSS defensivo obrigatório inclui `min-width: 0`, wrapping seguro, overflow horizontal para blocos `code`/`pre`, grids/tipografia responsivos e `max-width: 100%` para screenshots.

## 13. Projeção de remediação do finding

Para um finding acionável, renderizar quando aplicável:

- URL;
- Device;
- Rule;
- categoria GEO;
- resultado bruto;
- Actionability;
- Priority;
- Selector;
- Element;
- HTML observado;
- problema;
- por que isso importa no contexto GEO/readiness;
- orientação exata de mudança limitada pela evidência;
- exemplo recomendado claramente identificado como exemplo;
- critérios de aceitação;
- passos de revalidação;
- referência técnica.

HTML observado deve vir de evidência/observação persistida. Exemplos recomendados nunca podem ser apresentados como HTML observado.

Se o HTML original não foi persistido, usar a mensagem semântica exata:

```text
Trecho HTML original não persistido para esta evidência.
```

## 14. Invariantes de IA

OpenAI permanece opcional. Esta capacidade não adiciona chamada livre de LLM para gerar remediação.

Saídas persistidas de análise semântica/fallback podem ser reutilizadas. IA:

- não calcula score oficial;
- não escolhe pesos;
- não converte `UNKNOWN`/`ERROR` em `FAIL`;
- não cria seletor, HTML, evidência, fonte, fato ou claim ausente do estado persistido;
- não cria autor, data, preço, cobertura de produto ou dados estruturados como fatos.

Quando OpenAI está habilitada, rastreabilidade de provider/modelo/assessment/reasoning/evidência/entidade/intenção permanece obrigatória.

## 15. Persistência

A persistência é aditiva no workspace SQLite da auditoria. Tabelas de persistência da auditoria só são estendidas por contratos explícitos de schema exigidos pelo conjunto atual de capacidades.

Tabelas adicionais podem armazenar:

- universo normalizado de URLs de entrada e resumo bruto/único;
- `ElementObservation`;
- vínculo finding → elemento.

Opções de CLI suportadas para entrada incluem:

- `--project`;
- `--language`;
- `--market`;
- `--max-pages`;
- `--audits-root`;
- `--ai-provider`;
- `--ai-model`.

Defaults e valores permitidos das configurações correspondentes devem ser consultados nas referências canônicas `../ENVIRONMENT_VARIABLES.md`, `../CONFIGURATION.md` e `../CLI_REFERENCE.md`; esta especificação não redefine esses defaults.

## 16. Validação mínima

A cobertura de regressão focada deve incluir:

- entrada de URL única;
- entrada multi-URL de mesma origem;
- normalização/remoção de duplicatas;
- rejeição de origem incompatível antes da aquisição;
- `--urls-file`;
- um único workspace de auditoria para conjunto explícito;
- uma aquisição de robots e uma aquisição por URL de sitemap/recurso de domínio;
- artefatos de screenshot Desktop/Mobile e vínculo ao snapshot;
- seletor real quando determinístico e ausência quando não determinável;
- HTML/texto observado dentro dos limites;
- invariantes de scoring `UNKNOWN`, `ERROR`, `NOT_APPLICABLE`;
- comportamento `None != 0` no relatório;
- mapeamento de acionabilidade;
- presença no relatório de domínio, audit ID, inventário de URLs, URL em destaque por página, evidência visual/DOM, referências, robots, sitemap e wrapping responsivo;
- regressão contra canonical, autor, data, dados estruturados, claim, fato comercial, seletor e HTML observado inventados.

Smoke test real pode usar domínio controlado de homologação quando ambiente/conectividade permitirem. Websites externos nunca são fixtures de unit test.
