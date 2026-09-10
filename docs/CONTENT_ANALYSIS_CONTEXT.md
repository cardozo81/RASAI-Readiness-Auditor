# Contexto de análise de conteúdo - YMYL, E-E-A-T e finalidade da página

## Objetivo

O RASAi pode fornecer à camada de IA um **contexto editorial explícito** para evitar análises genéricas de conteúdo. Esse contexto condiciona a interpretação semântica e as sugestões por IA, mas **não altera aritmeticamente o `SARI-001`**, não cria um score de E-E-A-T/YMYL e não representa um fator oficial isolado de ranking.

A configuração é especialmente útil em conteúdo **YMYL (Your Money or Your Life)**, no qual informações imprecisas podem afetar saúde, segurança, estabilidade financeira ou o bem-estar da sociedade.

## Base pública oficial

Fontes normativas/conceituais usadas nesta implementação:

1. **Google Search Central - Creating helpful, reliable, people-first content**
   <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>

   A documentação declara, entre outros pontos, que:
   - E-E-A-T significa Experience, Expertise, Authoritativeness e Trustworthiness;
   - **Trust é o aspecto mais importante**;
   - um conteúdo não precisa demonstrar todos os componentes da mesma forma;
   - conteúdo relacionado a tópicos YMYL recebe maior peso de sinais alinhados a E-E-A-T;
   - autoria (`Who`), processo de criação (`How`) e finalidade (`Why`) são elementos úteis de autoavaliação;
   - propósito do site, público existente/pretendido, experiência em primeira mão, completude e atualização são aspectos relevantes de conteúdo people-first;
   - E-E-A-T **não é, por si só, um fator específico de ranking**.

2. **Google - Search Quality Rater Guidelines / overview**
   <https://services.google.com/fh/files/misc/hsw-sqrg.pdf>

   As diretrizes são referência conceitual para propósito da página, Page Quality e Needs Met. Ratings humanos não são usados diretamente como ranking individual de uma página.

3. **Google - How AI Overviews in Search work**
   <https://static.googleusercontent.com/media/www.google.com/en//search/howsearchworks/google-about-AI-overviews.pdf>

   O Google informa que consultas YMYL recebem uma barra mais alta para informações de suporte provenientes de fontes confiáveis.

## Princípio de segurança

Configuração explícita tem precedência conceitual sobre interpretação automática.

Quando uma variável permanece `auto`, **a configuração oficial continua sendo `AUTO`**. Se IA estiver habilitada, o modelo pode produzir separadamente uma interpretação contextual baseada apenas no conteúdo visível e nas evidências fornecidas. Essa interpretação:

- não se torna fato persistido sobre a organização ou a página;
- não sobrescreve o valor `AUTO` em `content_analysis_contexts`;
- não autoriza inventar credenciais, certificações, revisão profissional, reputação externa, compliance, experiência pessoal ou processo editorial;
- deve usar `Não determinável` quando a evidência não sustenta uma classificação segura;
- não substitui configuração humana quando o contexto do domínio é conhecido;
- não é evidência determinística e não entra diretamente em `SARI-001`/`SCORE-GEO-004`.

A finalidade dessa leitura é comparativa: o usuário pode considerar humanamente uma página não-YMYL, por exemplo, e ainda enxergar que o conteúdo fornecido levou um modelo a interpretá-la como relacionado a finanças, saúde, segurança ou outro contexto material - acompanhado de justificativa e confiança quando disponíveis.

## Variáveis

Todas são opcionais e usam `auto` por padrão.

### `RASAI_CONTENT_RISK_PROFILE`

Valores:

```text
auto
standard
ymyl
```

Use `ymyl` quando o conteúdo analisado puder afetar materialmente saúde, segurança, estabilidade financeira ou bem-estar social.

`auto` mantém a configuração em aberto; quando IA estiver habilitada, o relatório pode mostrar separadamente a interpretação transitória feita pelo modelo. Para sites claramente YMYL, prefira `ymyl` explícito.

### `RASAI_YMYL_CATEGORY`

Valores:

```text
auto
none
health-safety
financial-security
civic-societal
other-significant-welfare
```

A categoria serve apenas para contextualizar o tipo de risco. Não é classificação oficial emitida pelo Google para a página.

Validações:

- `risk_profile=standard` não aceita categoria YMYL explícita diferente de `none`/`auto`;
- `risk_profile=ymyl` não aceita `ymyl_category=none`.

### `RASAI_PAGE_PURPOSE`

Valores:

```text
auto
informational
transactional
product-service
review-comparison
news-editorial
support-documentation
forum-ugc
other
```

Evita avaliar uma página transacional, uma review e uma documentação técnica com exatamente a mesma expectativa editorial.

### `RASAI_INTENDED_AUDIENCE`

Valores:

```text
auto
general
professional
mixed
```

Ajuda a calibrar profundidade, explicações e necessidade de contexto. Não deve ser usado para inferir requisitos legais ou regulatórios.

### `RASAI_EXPERIENCE_REQUIREMENT`

Valores:

```text
auto
required
beneficial
not-expected
```

Diferencia **experiência em primeira mão** de **expertise técnica/profissional**. O RASAi não exige ambos indiscriminadamente.

Exemplos conceituais:

- review de produto: experiência em primeira mão tende a ser relevante;
- orientação médica: experiência pessoal não substitui expertise adequada e suporte factual;
- documentação de API: experiência pessoal pode ser secundária frente à exatidão técnica.

### `RASAI_FRESHNESS_SENSITIVITY`

Valores:

```text
auto
low
medium
high
```

Quando `high`, a IA aplica maior rigor a datas, períodos, qualificadores temporais e coerência entre sinais de atualização. O sistema nunca deve propor alterar uma data apenas para aparentar conteúdo mais recente.

### `RASAI_CONTENT_ORIGIN`

Valores:

```text
auto
first-party
third-party
user-generated
mixed
```

Ajuda a distinguir autor/criador do conteúdo e entidade publicadora/host. É relevante para atribuição, responsabilidade editorial e avaliação de conteúdo de terceiros ou UGC.

## Exemplo - site financeiro/YMYL

PowerShell:

```powershell
$env:RASAI_CONTENT_RISK_PROFILE = "ymyl"
$env:RASAI_YMYL_CATEGORY = "financial-security"
$env:RASAI_PAGE_PURPOSE = "product-service"
$env:RASAI_INTENDED_AUDIENCE = "general"
$env:RASAI_EXPERIENCE_REQUIREMENT = "not-expected"
$env:RASAI_FRESHNESS_SENSITIVITY = "high"
$env:RASAI_CONTENT_ORIGIN = "first-party"
```

Efeito esperado: a IA deve elevar a exigência de confiança, atribuição e suporte factual, prestar atenção especial a claims financeiros, datas, condições e qualificadores e evitar recomendações que criem promessas, garantias ou fatos não sustentados.

## Exemplo - conteúdo comum com interpretação parcial

```powershell
$env:RASAI_CONTENT_RISK_PROFILE = "standard"
$env:RASAI_CONTENT_ORIGIN = "first-party"
```

Os demais campos permanecem `auto`. A configuração persistida continua distinguindo os valores explícitos daqueles mantidos em `AUTO`. Quando IA for usada, `readiness.html` pode apresentar separadamente a leitura transitória dos campos `AUTO`, sem resolver esses campos no banco.

## Persistência e rastreabilidade

`content_analysis_contexts` persiste **a configuração efetiva usada como input** da auditoria. Valores explícitos permanecem explícitos; valores `auto` permanecem `AUTO`.

A interpretação transitória de IA **não é persistida nessa tabela nem em outra classificação canônica**. Ela é capturada em memória durante a chamada e inserida na projeção HTML final depois que os renderizadores persistidos terminam.

O report `content-suggestions.html` continua mostrando a configuração editorial usada. O report `readiness.html`, quando aplicável, mostra separadamente:

- configuração `AUTO`;
- interpretação feita pela IA naquela execução;
- confiança/qualificador;
- justificativa curta;
- IDs de evidência usados;
- `Não determinável` quando não houver suporte suficiente.

O HTML materializa a leitura daquela execução para inspeção humana, mas não transforma a classificação em verdade reutilizável em uma nova auditoria.

Detalhamento: [CONTENT_CONTEXT_AI_INTERPRETATION.md](CONTENT_CONTEXT_AI_INTERPRETATION.md).

## IA, custo e telemetria

Configurar contexto editorial **não gera chamada por si só**.

Quando uma etapa com IA é executada, continuam valendo os contratos de telemetria:

- provider;
- modelo;
- reasoning profile;
- status/tentativas;
- horário de início/fim e duração;
- tokens de entrada, cache, saída, reasoning e total quando disponibilizados pelo provider;
- custo estimado e moeda quando existe tabela de pricing suportada;
- versão da tabela de pricing;
- falhas técnicas/contratuais sem exposição de credenciais;
- exchange sanitizado de request/response quando a chamada externa efetivamente ocorre.

A interpretação editorial transitória é redigida do exchange log persistido e aparece legível somente na seção interpretativa do HTML, preservando a regra de não persistência canônica.

O HTML não deve fabricar custo quando o adapter não possui base confiável para estimá-lo.

## Relação com SARI-001

O contexto editorial é **advisory/contextual**.

Ele pode mudar a interpretação da IA sobre suficiência de evidência, trust, answerability, claims, atribuição, freshness e gaps de intenção, mas não adiciona diretamente uma nova parcela matemática ao score.

Isso evita afirmar que existe uma fórmula oficial de E-E-A-T/YMYL ou uma probabilidade oficial de ranking/citação, o que não é suportado pela documentação pública atual.
