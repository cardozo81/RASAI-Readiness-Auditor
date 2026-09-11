# Sugestões e remediação de conteúdo por IA + orientação JSON-LD

**Estado no baseline de desenvolvimento:** implementado como capacidade opcional downstream e separado do scoring.

## 1. Objetivo

Sugestões e remediação de conteúdo por IA adiciona uma camada opcional de remediação downstream que pode propor texto exato para findings de conteúdo/semântica sustentados por evidência e pode fornecer orientação determinística de JSON-LD por página/dispositivo auditado.

Essa capacidade **não** é uma etapa de scoring. Ela nunca pode alterar retroativamente:

- `RuleExecution`;
- `Finding`;
- `Recommendation` gerada pela priorização;
- Score;
- Coverage;
- Confidence;
- Consolidation.

Toda saída de remediação de conteúdo por IA é consultiva e exige revisão humana antes de publicação.

## 2. Default, valores permitidos e ativação

Remediação textual por IA externa permanece desabilitada por default.

Controles públicos:

```text
--ai-content-remediation
--no-ai-content-remediation
RASAI_AI_CONTENT_REMEDIATION
```

Precedência:

1. flag booleana explícita da CLI;
2. variável de ambiente;
3. `false`.

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_AI_CONTENT_REMEDIATION` | `false` | `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off`, sem distinção de caixa | `false` no baseline; habilitar apenas com provider apto e intenção explícita de gerar propostas textuais |
| `--ai-content-remediation` | não aplicado por default | flag de ativação | usar somente na execução em que a remediação for desejada |
| `--no-ai-content-remediation` | não aplicado por default | flag de desativação | usar para override explícito quando necessário |

A orientação JSON-LD é determinística e permanece disponível mesmo quando remediação textual por IA está desabilitada ou nenhum provider de IA está configurado.

## 3. Contexto editorial de análise - YMYL / E-E-A-T

A camada de IA pode receber contexto explícito da auditoria para que avaliação semântica e remediação de conteúdo não sejam forçadas a um único perfil editorial genérico.

Todos os campos abaixo têm default efetivo `auto`:

| Variável | Default | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_CONTENT_RISK_PROFILE` | `auto` | `auto`, `standard`, `ymyl` | `auto`, salvo classificação humana conhecida |
| `RASAI_YMYL_CATEGORY` | `auto` | `auto`, `none`, `health-safety`, `financial-security`, `civic-societal`, `other-significant-welfare` | `auto`; configurar manualmente somente com base editorial explícita |
| `RASAI_PAGE_PURPOSE` | `auto` | `auto`, `informational`, `transactional`, `product-service`, `review-comparison`, `news-editorial`, `support-documentation`, `forum-ugc`, `other` | `auto` |
| `RASAI_INTENDED_AUDIENCE` | `auto` | `auto`, `general`, `professional`, `mixed` | `auto` |
| `RASAI_EXPERIENCE_REQUIREMENT` | `auto` | `auto`, `required`, `beneficial`, `not-expected` | `auto` |
| `RASAI_FRESHNESS_SENSITIVITY` | `auto` | `auto`, `low`, `medium`, `high` | `auto` |
| `RASAI_CONTENT_ORIGIN` | `auto` | `auto`, `first-party`, `third-party`, `user-generated`, `mixed` | `auto` |

### 3.1 Regras de segurança do contexto

O contexto é entrada interpretativa, não novo score nem vetor oficial de fatores de ranking.

Comportamento obrigatório:

1. valores explícitos são contexto da auditoria fornecido pelo operador;
2. `auto` permite somente hipótese de trabalho provisória baseada na evidência visível/persistida fornecida;
3. inferência AUTO não pode se tornar fato persistido sobre credenciais, revisão profissional, experiência pessoal, reputação, conformidade legal/regulatória, processo editorial ou outros fatos ocultos;
4. quando uma inferência AUTO alterar materialmente uma conclusão, a confiança do provider deve ser menor do que em contexto explícito equivalente;
5. com `risk_profile=ymyl`, o provider deve aplicar padrão materialmente mais alto de confiança/evidência a claims que possam afetar saúde, segurança, estabilidade/segurança financeira, bem-estar cívico/social ou outro bem-estar significativo comparável;
6. Trust é tratado como consideração central de E-E-A-T; Experience, Expertise e Authoritativeness são relevantes conforme finalidade/tema da página e não devem ser exigidos mecanicamente de toda página;
7. `experience_requirement` distingue experiência em primeira mão de expertise temática, sem tratá-las como equivalentes;
8. `freshness_sensitivity=high` eleva a verificação de datas, períodos e qualificadores temporais, mas nunca autoriza fabricar data mais recente;
9. `content_origin` distingue criador/origem do conteúdo do publicador hospedeiro quando houver conteúdo third-party, UGC ou misto;
10. idioma e mercado são somente contexto e não comprovam jurisdição nem conformidade regulatória.

Validação de consistência:

- `risk_profile=standard` não pode ser combinado com categoria YMYL explícita diferente de `auto`/`none`;
- `risk_profile=ymyl` não pode ser combinado com `ymyl_category=none`.

O contexto efetivo da auditoria deve ser persistido para que o relatório reaberto demonstre quais campos foram explícitos e quais permaneceram `AUTO`.

Referências conceituais primárias:

- Google Search Central - Creating helpful, reliable, people-first content: `https://developers.google.com/search/docs/fundamentals/creating-helpful-content`
- Google Search Quality Rater Guidelines: `https://services.google.com/fh/files/misc/hsw-sqrg.pdf`
- Google - How AI Overviews in Search work: `https://static.googleusercontent.com/media/www.google.com/en//search/howsearchworks/google-about-AI-overviews.pdf`

Essas referências sustentam o uso conceitual de E-E-A-T/YMYL e análise de finalidade/necessidade do usuário. O RASAi não deve descrever E-E-A-T isoladamente como fator oficial único de ranking nem publicar probabilidade E-E-A-T/YMYL fabricada.

Os links acima são referências, não reprodução de texto externo. Se futuramente um trecho não pt-BR precisar ser citado literalmente em Markdown, deve seguir a convenção de `docs/README.md`: **Disclaimer - texto original da fonte** seguido de **Tradução/adaptação pt-BR**, limitado ao trecho necessário.

## 4. Contrato de gatilho

Remediação textual por IA só pode ser acionada por findings persistidos de conteúdo/semântica que sejam elegíveis.

`Confidence LOW`, isoladamente, **nunca** é gatilho e não deve ser interpretada como conteúdo ruim.

Universo de regras elegíveis para propostas de texto exato nesta versão:

```text
BR-GEO-028..033
BR-GEO-038..049
```

Regras de Structured Data não são enviadas ao prompt livre de remediação de conteúdo. Orientação JSON-LD é tratada separadamente pelo contrato determinístico desta especificação.

## 5. Limite de evidência

Cada request externo de remediação de conteúdo por IA tem escopo de um único snapshot/dispositivo persistido e pode conter somente:

- URL normalizada da página;
- dispositivo selecionado;
- título observado;
- artefato persistido e limitado do conteúdo principal;
- contexto editorial efetivo;
- findings elegíveis daquela página/dispositivo;
- condição esperada e valor observado desses findings;
- evidências persistidas vinculadas aos findings.

A saída do provider deve referenciar um `finding_id` fornecido e existente, e IDs de evidência que sejam subconjunto dos IDs persistidos daquele finding.

Sugestão com referência estrangeira ou inventada de finding/evidência é inválida pelo contrato e não pode ser publicada.

## 6. Saída de texto exato

Cada sugestão aceita contém:

- `finding_id`;
- objetivo da alteração;
- local/posicionamento alvo;
- texto exato proposto;
- IDs de evidência;
- confiança da sugestão;
- observação obrigatória de revisão humana;
- provider/modelo persistidos separadamente.

O sistema nunca deve gravar a sugestão diretamente no website auditado.

## 7. Contrato people-first e antifabricação

As instruções ao provider devem exigir conteúdo que melhore utilidade, clareza, completude ou confiança para usuários reais.

A remediação por IA não deve solicitar ao provider:

- escrever apenas para mecanismos de busca ou sistemas generativos;
- fazer keyword stuffing;
- atingir contagem arbitrária de palavras;
- aplicar chunking artificial apenas para recuperação por IA;
- fabricar atualização/data;
- inventar preços, claims, garantias, estatísticas, credenciais, expertise, experiência ou fontes;
- gerar conteúdo em massa sem sustentação.

Como endurecimento local, tokens que representem números, datas ou preços introduzidos no texto proposto devem já existir no corpus persistido de conteúdo/evidência fornecido. Caso contrário, a resposta é rejeitada como erro de contrato.

Essa proteção numérica é contenção adicional de risco; não prova que toda afirmação não numérica seja factual. Revisão humana continua obrigatória.

## 8. Roteamento de providers

A remediação reutiliza o universo de providers, roteamento e telemetria já configurado para análise semântica. Não introduz credenciais nem configuração de modelo separadas.

Regras:

1. providers em quarentena pela análise semântica na auditoria atual não são reativados para remediação;
2. provider explicitamente selecionado mantém comportamento de provider único;
3. `AUTO` pode usar a cadeia saudável/configurada remanescente;
4. chamadas são sequenciais;
5. a primeira resposta válida encerra a cadeia daquele request;
6. sucesso do provider estabelece pinning de provider por URL para contextos subsequentes de remediação da mesma URL;
7. provider que falhar fica em quarentena na sessão de roteamento da remediação;
8. não há retry automático por timeout;
9. `RASAI_DEVICE_CONTEXT` limita o universo de requests porque somente snapshots selecionados existem downstream.

Falha de provider da remediação é estado operacional do auditor e nunca finding do website.

Defaults de providers/modelos/reasoning pertencem ao contrato central `../ENVIRONMENT_VARIABLES.md`; esta especificação não redefine esses valores.

## 9. Telemetria

A remediação persiste telemetria separadamente das tentativas de análise semântica, permitindo auditoria de custo por finalidade.

Telemetria mínima:

- URL;
- página/snapshot/dispositivo;
- provider/modelo;
- perfil de reasoning;
- índice da tentativa;
- status;
- timestamps/duração;
- classe/status/código/request ID de diagnóstico sanitizado;
- tokens input/cached/output/reasoning/total quando reportados;
- custo/moeda/pricing version estimados localmente quando houver base de preço suportada;
- resumo/hash do request;
- versão do contrato de remediação.

API keys brutas, headers `Authorization` e corpos ilimitados de erro do provider nunca devem ser persistidos.

Se provider/modelo não possuir base local de preço confiável, o relatório deve exibir estimativa monetária como indisponível, em vez de fabricar custo.

As variáveis de contexto da seção 3 não criam chamadas externas por si só e, portanto, não geram custo independente de IA.

## 10. Estados de execução da remediação

Estados persistidos permitidos incluem:

```text
DISABLED
NOT_CONFIGURED
NO_ELIGIBLE_FINDINGS
SUCCESS
PARTIAL
NO_SAFE_SUGGESTIONS
DEGRADED
```

`NOT_CONFIGURED`, `PARTIAL` e `DEGRADED` não alteram scoring do website.

## 11. Orientação JSON-LD quando ausente

Para cada snapshot/dispositivo efetivamente auditado sem artefato JSON-LD persistido, o RASAi pode materializar baseline conservador Schema.org `WebPage` usando somente dados persistidos/observados.

Campos genéricos permitidos incluem:

```json
{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "url": "<canonical-or-normalized-url>",
  "inLanguage": "<audit-language>",
  "name": "<observed-title-if-present>",
  "description": "<observed-meta-description-if-present>"
}
```

Um `mainEntity` opcional só pode ser incluído quando uma única entidade persistida de alta confiança for suficientemente inequívoca e sustentada pela evidência visível/persistida da página. O auditor deve preferir omissão a tipagem especulativa.

O baseline não deve inventar FAQ, reviews, ratings, preços, autores, datas, offers, endereços, credenciais, identificadores de produto nem outra propriedade sem suporte no conteúdo observado.

Uma proposta genérica `WebPage` não é promessa de elegibilidade a rich result do Google.

## 12. Orientação JSON-LD quando existente

Quando há JSON-LD persistido, a capacidade não o substitui integralmente. Executa revisão genérica não destrutiva e pode identificar:

- erros de parsing JSON;
- blocos duplicados idênticos;
- ausência de `@context` de documento/grafo;
- nós sem `@type`;
- nó `WebPage` sem `url`, `name`, `description` ou `inLanguage` quando o valor correspondente já estiver persistido;
- oportunidade de representar semântica `WebPage` no nível da página sem substituir tipo principal mais específico e válido.

Quando nenhum problema genérico for detectado, o relatório deve informar que propriedades obrigatórias/recomendadas específicas do tipo ainda exigem validação contra a documentação da feature aplicável.

## 13. Orientação externa sobre Structured Data

A capacidade deve comunicar corretamente que:

- Google suporta JSON-LD, Microdata e RDFa e, em geral, recomenda JSON-LD pela facilidade de implementação;
- Structured Data deve representar conteúdo visível/relevante da página e não pode ser enganoso;
- tipos Schema.org mais específicos e aplicáveis são preferíveis quando descrevem fielmente o conteúdo;
- propriedades obrigatórias/recomendadas variam por feature/tipo de Search;
- markup válido não garante exibição de rich result;
- Structured Data/JSON-LD não é requisito universal de Search & AI generativa;
- RASAi não deve inventar markup especial GEO/AEO.

Referências primárias:

- Google Search Central - General Structured Data Guidelines: `https://developers.google.com/search/docs/appearance/structured-data/sd-policies`
- Google Search Central - Intro to Structured Data: `https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data`
- documentação Schema.org: `https://schema.org/docs/documents.html`
- Google Search Central - Optimizing for generative AI features: `https://developers.google.com/search/docs/fundamentals/ai-optimization-guide`

## 14. Contrato de relatório

`REPORT-SITE-GEO-001` é estendido com:

```text
<AUD-ID>/report/content-suggestions.html
```

A página deve usar a mesma navegação compartilhada e stylesheet externo das demais páginas do relatório, preservando consistência com o design system do report.

Deve mostrar somente informação analiticamente útil, incluindo:

- habilitação/status/contagens da remediação;
- contexto editorial efetivo e indicação de quais campos foram configurados explicitamente ou permaneceram `AUTO`;
- alerta explícito quando o contexto for parcial ou totalmente inferido;
- sugestões textuais exatas agrupadas por página/dispositivo/finding;
- objetivo, posicionamento, evidência, provider/modelo e requisito de revisão;
- telemetria compacta desta etapa: provider/modelo/reasoning, quantidade de chamadas, duração acumulada, tokens e custo estimado quando disponível;
- atalho para a página completa de telemetria de IA;
- proposta JSON-LD quando ausente;
- notas de melhoria JSON-LD quando existente;
- linguagem explícita de caráter consultivo e fora do scoring;
- links concisos para referências oficiais relevantes.

Requisitos de usabilidade:

1. usar atalhos contextuais quando uma página contém múltiplas seções analíticas;
2. métricas ambíguas ou conceitos específicos do projeto devem possuir tooltip/help conciso quando isso reduzir risco de interpretação;
3. tooltip/help complementa, não substitui, rótulo visível compreensível;
4. telemetria detalhada pertence a `ai-usage.html`; a página de conteúdo mostra apenas o resumo necessário e atalho direto;
5. referências devem apontar preferencialmente para fontes públicas oficiais/primárias;
6. nenhuma página pode sugerir garantia de ranking, citação, rich result ou conformidade regulatória.

A telemetria da remediação também deve aparecer em `report/ai-usage.html`, claramente separada da telemetria de análise semântica, com provider/modelo/reasoning/status/tokens/custo/duração/erro em nível de tentativa.

## 15. Invariantes de persistência

Tabelas de remediação são aditivas a `audit.db` e devem preservar capacidade de reabertura/reprodução do relatório.

Entidades lógicas mínimas:

```text
ContentAnalysisContext
ContentRemediationRun
ContentRemediationSuggestion
ContentRemediationAttempt
JsonLdRemediationSuggestion
```

`ContentAnalysisContext` deve preservar valores efetivos da auditoria, campos explicitamente configurados, campos que permaneceram `AUTO` e se o modo de origem foi `MANUAL`, `MIXED` ou `AUTO`.

Foreign keys devem ligar sugestões ao universo já persistido de audit/page/snapshot/finding, conforme aplicabilidade.

## 16. Critérios de aceitação vigentes

A capacidade deve preservar os seguintes contratos:

1. auditoria default não faz chamada externa adicional de remediação de conteúdo;
2. auditoria default ainda produz revisão determinística de JSON-LD;
3. remediação habilitada usa somente findings/evidências persistidos elegíveis;
4. referências estrangeiras/inválidas de evidência são rejeitadas;
5. claims numéricos não suportados são rejeitados;
6. falhas de provider permanecem operacionais, não findings do website;
7. remediação não altera score/findings preexistentes;
8. `mobile`, `desktop` e `both` preservam escopo correto de dispositivo;
9. site de relatório expõe a página com CSS/navegação compartilhados e hierarquia visual consistente;
10. contexto editorial é validado, persistido e exposto como configurado versus `AUTO`;
11. combinações inválidas YMYL/contexto falham antes de produzir saída enganosa;
12. prompts de análise semântica/remediação recebem o contexto sem alterar o contrato estruturado de saída semântica;
13. telemetria distingue finalidades de análise semântica e remediação e não fabrica custo monetário quando a base de preço está indisponível;
14. relatório expõe atalhos, tooltips e referências contextuais sem virar despejo de documentação;
15. regressões unitárias/de integração cobrem os contratos críticos;
16. smoke real com Chromium pode validar a capacidade desabilitada e habilitada sem provider, sem transformar ausência de provider em falha do website;
17. documentação, CLI e glossário de configuração devem permanecer aderentes ao runtime vigente.
