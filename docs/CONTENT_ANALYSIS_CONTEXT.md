# Contexto de análise de conteúdo — YMYL, E-E-A-T e finalidade da página

## Objetivo

O SearchGEO pode fornecer à camada de IA um **contexto editorial explícito** para evitar análises genéricas de conteúdo. Esse contexto condiciona a interpretação semântica e as sugestões Sugestões e remediação de conteúdo por IA, mas **não altera aritmeticamente o `SCORE-GEO-002`**, não cria um score de E-E-A-T/YMYL e não representa um fator oficial isolado de ranking.

A configuração é especialmente útil em conteúdo **YMYL (Your Money or Your Life)**, no qual informações imprecisas podem afetar saúde, segurança, estabilidade financeira ou o bem-estar da sociedade.

## Base pública oficial

Fontes normativas/conceituais usadas nesta implementação:

1. **Google Search Central — Creating helpful, reliable, people-first content**
   <https://developers.google.com/search/docs/fundamentals/creating-helpful-content>

   A documentação declara, entre outros pontos, que:
   - E-E-A-T significa Experience, Expertise, Authoritativeness e Trustworthiness;
   - **Trust é o aspecto mais importante**;
   - um conteúdo não precisa demonstrar todos os componentes da mesma forma;
   - conteúdo relacionado a tópicos YMYL recebe maior peso de sinais alinhados a E-E-A-T;
   - autoria (`Who`), processo de criação (`How`) e finalidade (`Why`) são elementos úteis de autoavaliação;
   - propósito do site, público existente/pretendido, experiência em primeira mão, completude e atualização são aspectos relevantes de conteúdo people-first;
   - E-E-A-T **não é, por si só, um fator específico de ranking**.

2. **Google — Search Quality Rater Guidelines / overview**
   <https://services.google.com/fh/files/misc/hsw-sqrg.pdf>

   As diretrizes são referência conceitual para propósito da página, Page Quality e Needs Met. Ratings humanos não são usados diretamente como ranking individual de uma página.

3. **Google — How AI Overviews in Search work**
   <https://static.googleusercontent.com/media/www.google.com/en//search/howsearchworks/google-about-AI-overviews.pdf>

   O Google informa que consultas YMYL recebem uma barra mais alta para informações de suporte provenientes de fontes confiáveis.

## Princípio de segurança

Configuração explícita tem precedência conceitual sobre inferência automática.

Quando uma variável permanece `auto`, a IA pode usar apenas uma **hipótese de trabalho** baseada no conteúdo visível e nas evidências fornecidas. Essa inferência:

- não se torna fato persistido sobre a organização;
- não autoriza inventar credenciais, certificações, revisão profissional, reputação externa, compliance, experiência pessoal ou processo editorial;
- deve reduzir confiança quando a classificação inferida for material para a conclusão;
- não substitui configuração humana quando o contexto do domínio é conhecido.

## Variáveis

Todas são opcionais e usam `auto` por padrão.

### `SEARCHGEO_CONTENT_RISK_PROFILE`

Valores:

```text
auto
standard
ymyl
```

Use `ymyl` quando o conteúdo analisado puder afetar materialmente saúde, segurança, estabilidade financeira ou bem-estar social.

`auto` permite classificação provisória pela IA. Para sites claramente YMYL, prefira `ymyl` explícito.

### `SEARCHGEO_YMYL_CATEGORY`

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

### `SEARCHGEO_PAGE_PURPOSE`

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

### `SEARCHGEO_INTENDED_AUDIENCE`

Valores:

```text
auto
general
professional
mixed
```

Ajuda a calibrar profundidade, explicações e necessidade de contexto. Não deve ser usado para inferir requisitos legais ou regulatórios.

### `SEARCHGEO_EXPERIENCE_REQUIREMENT`

Valores:

```text
auto
required
beneficial
not-expected
```

Diferencia **experiência em primeira mão** de **expertise técnica/profissional**. O SearchGEO não exige ambos indiscriminadamente.

Exemplos conceituais:

- review de produto: experiência em primeira mão tende a ser relevante;
- orientação médica: experiência pessoal não substitui expertise adequada e suporte factual;
- documentação de API: experiência pessoal pode ser secundária frente à exatidão técnica.

### `SEARCHGEO_FRESHNESS_SENSITIVITY`

Valores:

```text
auto
low
medium
high
```

Quando `high`, a IA aplica maior rigor a datas, períodos, qualificadores temporais e coerência entre sinais de atualização. O sistema nunca deve propor alterar uma data apenas para aparentar conteúdo mais recente.

### `SEARCHGEO_CONTENT_ORIGIN`

Valores:

```text
auto
first-party
third-party
user-generated
mixed
```

Ajuda a distinguir autor/criador do conteúdo e entidade publicadora/host. É relevante para atribuição, responsabilidade editorial e avaliação de conteúdo de terceiros ou UGC.

## Exemplo — site financeiro/YMYL

PowerShell:

```powershell
$env:SEARCHGEO_CONTENT_RISK_PROFILE = "ymyl"
$env:SEARCHGEO_YMYL_CATEGORY = "financial-security"
$env:SEARCHGEO_PAGE_PURPOSE = "product-service"
$env:SEARCHGEO_INTENDED_AUDIENCE = "general"
$env:SEARCHGEO_EXPERIENCE_REQUIREMENT = "not-expected"
$env:SEARCHGEO_FRESHNESS_SENSITIVITY = "high"
$env:SEARCHGEO_CONTENT_ORIGIN = "first-party"
```

Efeito esperado: a IA deve elevar a exigência de confiança, atribuição e suporte factual, prestar atenção especial a claims financeiros, datas, condições e qualificadores e evitar recomendações que criem promessas, garantias ou fatos não sustentados.

## Exemplo — conteúdo comum com inferência parcial

```powershell
$env:SEARCHGEO_CONTENT_RISK_PROFILE = "standard"
$env:SEARCHGEO_CONTENT_ORIGIN = "first-party"
```

Os demais campos permanecem `auto`. O report classificará a origem do contexto como **MIXED**: parte configurada e parte inferível.

## Persistência e rastreabilidade

O contexto efetivo é persistido no workspace da auditoria em `content_analysis_contexts`.

O report `content-suggestions.html` mostra:

- valor de cada contexto;
- se foi `CONFIGURADO` ou `AUTO`;
- origem global `MANUAL`, `MIXED` ou `AUTO`;
- explicações contextuais em tooltip;
- referências oficiais;
- telemetria das chamadas Sugestões e remediação de conteúdo por IA quando IA é usada.

O objetivo é que a interpretação continue reproduzível mesmo que as variáveis de ambiente sejam alteradas depois da execução.

## IA, custo e telemetria

Configurar contexto editorial **não gera chamada por si só**.

Quando uma etapa com IA é executada, continuam valendo os contratos já existentes de telemetria:

- provider;
- modelo;
- reasoning profile;
- status/tentativas;
- horário de início/fim e duração;
- tokens de entrada, cache, saída, reasoning e total quando disponibilizados pelo provider;
- custo estimado e moeda quando existe tabela de pricing suportada;
- versão da tabela de pricing;
- falhas técnicas/contratuais sem exposição de credenciais.

O HTML não deve fabricar custo quando o adapter não possui base confiável para estimá-lo.

## Relação com SCORE-GEO-002

O contexto editorial é **advisory/contextual**.

Ele pode mudar a interpretação da IA sobre suficiência de evidência, trust, answerability, claims, atribuição, freshness e gaps de intenção, mas não adiciona diretamente uma nova parcela matemática ao score.

Isso evita afirmar que existe uma fórmula oficial de E-E-A-T/YMYL ou uma probabilidade oficial de ranking/citação, o que não é suportado pela documentação pública atual.
