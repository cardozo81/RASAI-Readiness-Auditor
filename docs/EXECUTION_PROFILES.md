# Perfis da próxima auditoria

Perfis são **presets temporários de capacidades** da próxima execução do `rasai-console`.
Existe **um único catálogo de perfis** e ele usa as mesmas capacidades canônicas apresentadas em
`INÍCIO > PREPARAR AUDITORIA`.

Não existe segundo grupo funcional, taxonomia paralela, compatibilidade de perfil legado ou
camada de migração. O programa ainda não foi publicado em produção; este documento descreve
somente o contrato atual.

## Princípio central

A composição é:

```text
perfil nomeado ou personalizado
-> conjunto de capacidades canônicas
-> política explícita de IA e GSC da execução
-> readiness das capacidades solicitadas
-> projeção temporária do escopo
-> preflight/runtime normal
-> evidências/fulfillment do que foi efetivamente solicitado
```

A fonte canônica do catálogo técnico é `rasai.execution_capabilities`.

## Regra de escopo

O perfil selecionado é **autoritativo para a próxima execução**.

Variáveis já existentes na sessão continuam armazenadas e podem fornecer parâmetros para uma
capacidade incluída pelo perfil, mas **não podem reativar silenciosamente uma capacidade que o
perfil excluiu**.

Exemplos:

- perfil com `SEM IA` executa com `ai_provider=none`, mesmo que a sessão tenha OpenAI/Gemini/etc.;
- perfil sem Search Intelligence não executa SERP apenas porque existem termos na sessão;
- perfil sem Apdex não executa navegações sintéticas apenas porque Synthetic/Experience Apdex
  estavam habilitados;
- perfil sem Análise profunda não executa Improvement Intelligence apenas porque a variável da
  sessão estava ativa;
- perfil sem remediação por IA não executa esse enriquecimento somente porque os flags da sessão
  estavam ativos;
- perfil com Web Performance pode usar os parâmetros vigentes da sessão para essa capacidade.

A projeção é temporária. Ao terminar preflight/execução, o estado original da sessão é restaurado.

## Precedência

A precedência efetiva é:

```text
ajuste explícito feito depois da seleção do perfil
> escopo e política definidos pelo perfil
> parâmetros já existentes da sessão para capacidades incluídas
> INI / SO / defaults canônicos
```

Assim, o usuário pode escolher um perfil e depois alterar deliberadamente uma opção no menu
normal. Esse ajuste posterior passa a ser um override explícito da sessão e vence o preset.

## Capacidades canônicas

O catálogo compartilhado inclui:

- Domínio e descoberta;
- Acessibilidade;
- Web Performance;
- Métricas e padrões;
- Search Intelligence / SERP;
- Apdex de navegação;
- Apdex de experiência;
- Visibilidade em IA;
- Search & AI observados;
- Análise profunda e melhorias;
- Conteúdo e JSON-LD;
- Remediações;
- Quality & decisão.

Capacidades automáticas ou derivadas continuam sem checkbox independente quando representam
resultados que o pipeline já produz. O perfil personalizado expõe somente workloads que o
operador pode solicitar ou excluir diretamente.

## Catálogo único de perfis

### SEO / Search Readiness

Diagnostica descoberta, indexabilidade e sinais técnicos de busca orgânica. O resultado esperado
é Search Readiness técnico com descoberta/conteúdo e Lighthouse SEO/boas práticas.

### GEO / AI Readiness

Diagnostica preparo técnico para descoberta e consumo por agentes/IA. O resultado esperado inclui
estrutura de conteúdo, sinais agentic e evidências disponíveis de visibilidade.

### Performance

Mede PageSpeed/Lighthouse/CrUX disponíveis com foco em Performance e boas práticas, sem ampliar
por si só para SERP, Apdex ou Análise profunda.

### Acessibilidade

Aprofunda acessibilidade com evidências do core e enriquecimento Lighthouse quando disponível.

### Web Quality

Entrega visão ampla de qualidade técnica Web sem acionar SERP, carga sintética ou IA obrigatória.

### SEO + GEO

Combina Search Readiness e AI Readiness na mesma execução.

### SEO + GEO + Performance

Combina Search/AI Readiness com performance de laboratório/campo.

### Search Intelligence / SERP

Observa resultados de busca para termos explicitamente fornecidos. O perfil nunca cria termos,
região, device ou depth.

### Apdex de navegação

Executa navegações reais repetidas conforme thresholds, amostras e perfil sintético configurados.

### Apdex de experiência

Executa Navigation + Experience Apdex. Experience mantém Navigation como dependência técnica.

### Análise profunda URL

Executa análise evidence-bound adicional com priorização corretiva usando a mesma IA
principal/orquestrador canônico da auditoria.

### Completo seguro

Executa cobertura técnica ampla sem workloads que exigem termos SERP, carga sintética ou IA
obrigatória.

### Completo máximo

Solicita todas as capacidades do catálogo. Inputs não inventáveis, credenciais e guardrails
continuam obrigatórios.

## Perfil personalizado

O perfil personalizado usa o mesmo catálogo de capacidades selecionáveis; não existe uma segunda
família de perfis.

`Apdex de experiência` adiciona `Apdex de navegação` como dependência e a UI impede remover
Navigation enquanto Experience permanecer selecionado.

Depois da composição, o usuário escolhe a política de IA da execução:

```text
1. Não usar IA nesta execução do perfil
2. Usar IA principal/AUTO se houver provider APTO
```

A opção 1 significa efetivamente **SEM IA** durante essa execução. A configuração de IA da sessão
não é apagada; ela apenas não é projetada para o runtime desse perfil.

## IA

Existe uma única IA principal por execução.

Quando o perfil está em `SEM IA`, provider/model/reasoning são temporariamente neutralizados e
remediações dependentes de IA não são executadas. Quando a IA é permitida, a seleção atual da
sessão é usada se estiver apta; caso contrário, o orquestrador `AUTO` segue o contrato central de
elegibilidade, preço, quarentena, circuit breaker, fallback e limite de tentativas.

Análise profunda exige IA principal e, por isso, não pode ser combinada com `SEM IA`.

## Google Search Console

GSC continua independente de SERP. Após selecionar o perfil, a execução pode:

- usar somente se a property cobrir a URL;
- exigir GSC;
- não usar GSC nesta execução;
- herdar a política global.

Essa política é temporária e não regrava credenciais nem a configuração persistente do operador.

## Readiness

O perfil não possui validador técnico paralelo. O estado é agregado a partir da aptidão das
capacidades canônicas solicitadas.

```text
APTO
  todas as capacidades obrigatórias do perfil estão executáveis

CONFIGURAR
  ao menos uma capacidade solicitada possui dependência conhecida não atendida
```

Capacidades automáticas/derivadas não se tornam falha apenas por não produzirem dado opcional.
SERP, Apdex e Análise profunda precisam satisfazer seus próprios contratos quando solicitados.

## Persistência e evidências

O perfil não grava INI, Windows/User, Windows/Machine nem credenciais.

O snapshot secret-free do AUD registra o contrato atual em termos de:

- `profile_id`;
- `label`;
- `capabilities`;
- `ai_mode`;
- `manual_overrides`.

Não é mantido campo paralelo de `modules` para compatibilidade histórica de perfil.

A evidência de execução deve refletir o **estado efetivo projetado pelo perfil**, e não o estado
bruto das variáveis da sessão antes da projeção. Portanto, uma execução `SEM IA` deve aparecer
como IA não solicitada mesmo que a sessão tenha um provider configurado fora do perfil.

## Desenvolvimento

O programa permanece em desenvolvimento e não possui versão pública/legado a preservar. A
arquitetura descrita aqui é o contrato vigente.
