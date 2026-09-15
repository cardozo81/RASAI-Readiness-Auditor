# Perfis da próxima auditoria

Perfis são **presets temporários de capacidades** da próxima execução do `rasai-console`.
Eles não possuem uma taxonomia técnica paralela: usam as mesmas capacidades canônicas
apresentadas em `INÍCIO > PREPARAR AUDITORIA`.

O objetivo do perfil é reduzir escolhas repetitivas e deixar explícito **qual resultado o
operador pretende obter**, sem criar outra fonte de verdade para configuração, readiness,
fulfillment ou relatórios.

## Princípio central

A composição é:

```text
perfil nomeado
-> conjunto de capacidades canônicas
-> readiness das mesmas capacidades exibidas em Preparar auditoria
-> overlay temporário e aditivo
-> preflight/runtime normal
-> evidências/fulfillment das capacidades efetivamente solicitadas
```

A fonte canônica do catálogo técnico é `rasai.execution_capabilities`.

## Preservação da sessão

Selecionar um perfil **não pode desligar silenciosamente uma escolha que já exista na sessão**.

Exemplos:

- IA já selecionada continua selecionada;
- termos SERP já informados permanecem na sessão;
- Synthetic/Experience Apdex já habilitados permanecem habilitados;
- Análise profunda já habilitada permanece habilitada;
- categorias Lighthouse existentes são preservadas;
- integrações opt-in já habilitadas continuam sob seus próprios contratos.

O perfil é aditivo: pode solicitar Web Performance, acrescentar categorias Lighthouse ou
solicitar Análise profunda, mas a ausência de uma capacidade no preset não significa `OFF`.

A precedência efetiva é:

```text
ajuste explícito feito depois da seleção do perfil
> intenção adicionada pelo perfil
> estado/configuração que já existia na sessão
> INI / SO / defaults canônicos
```

Ao terminar a projeção da execução, o estado do processo pai é restaurado.

## Capacidades canônicas

O catálogo compartilhado inclui, entre outras:

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

Capacidades automáticas ou derivadas continuam sem checkbox apenas para reproduzir algo que
o pipeline já gera. O perfil personalizado expõe somente workloads que realmente podem ser
solicitados/desmarcados pelo operador.

## Catálogo de perfis

### SEO / Search Readiness

**Uso:** diagnosticar descoberta, indexabilidade e sinais técnicos que afetam busca orgânica.

**Resultado esperado:** leitura técnica de Search Readiness com descoberta/conteúdo e
Lighthouse SEO/boas práticas.

### GEO / AI Readiness

**Uso:** diagnosticar se a URL está tecnicamente preparada para descoberta e consumo por
agentes/IA.

**Resultado esperado:** leitura de AI Readiness com estrutura de conteúdo, sinais agentic e
evidências disponíveis de visibilidade.

### Performance

**Uso:** medir desempenho técnico sem ampliar o escopo para SERP, Apdex ou Análise profunda.

**Resultado esperado:** métricas PageSpeed/Lighthouse/CrUX disponíveis, com foco em
Performance e boas práticas.

### Acessibilidade

**Uso:** aprofundar a leitura de acessibilidade com enriquecimento Lighthouse.

**Resultado esperado:** evidências do core mais Lighthouse Accessibility/boas práticas quando
disponível.

### Web Quality

**Uso:** obter leitura ampla de qualidade técnica Web sem acionar SERP, carga sintética ou IA
obrigatória.

**Resultado esperado:** descoberta, acessibilidade, padrões, conteúdo e categorias Lighthouse
de qualidade Web.

### SEO + GEO

Combina os objetivos de Search Readiness e AI Readiness na mesma execução.

### SEO + GEO + Performance

Combina Search/AI Readiness com performance de laboratório/campo.

### Search Intelligence / SERP

**Uso:** observar resultados de busca para termos explicitamente fornecidos.

**Resultado esperado:** observação SERP/concorrencial restrita aos termos, região, device e
depth configurados. O perfil nunca cria termos.

### Apdex de navegação

**Uso:** medir repetidamente navegação real sob perfil sintético controlado.

**Resultado esperado:** amostras e Apdex de navegação conforme thresholds, amostras e perfil
operacional configurados.

### Apdex de experiência

**Uso:** medir experiência sintética considerando a distribuição de dispositivos configurada.

**Resultado esperado:** Navigation + Experience Apdex. Experience mantém Navigation como
dependência técnica explícita.

### Análise profunda URL

**Uso:** obter análise evidence-bound adicional com priorização e ações corretivas.

**Resultado esperado:** recomendações adicionais vinculadas às evidências da URL, usando a
mesma IA principal/orquestrador canônico da auditoria.

### Completo seguro

**Uso:** cobertura técnica ampla sem acionar workloads que exigem termos SERP, carga sintética
ou IA obrigatória.

**Resultado esperado:** descoberta, acessibilidade, performance, padrões, conteúdo e resultados
sistêmicos/observacionais disponíveis. Integrações externas opt-in não são ligadas pelo preset.

### Completo máximo

**Uso:** executar todas as capacidades selecionáveis que estiverem corretamente parametrizadas.

**Resultado esperado:** cobertura máxima, incluindo SERP, Apdex e Análise profunda.

`Máximo` não ignora guardrails. Inputs não inventáveis e credenciais continuam obrigatórios.

## Readiness do perfil

O perfil não mantém um validador paralelo. O estado é agregado a partir da aptidão das
capacidades canônicas que ele solicita.

```text
APTO
  todas as capacidades obrigatórias do preset estão executáveis

CONFIGURAR
  ao menos uma capacidade solicitada possui dependência conhecida não atendida

APTO com observações
  capacidades obrigatórias estão aptas, mas fontes automáticas/opcionais podem não produzir dados
```

Capacidade automática/derivada ausente não transforma o perfil em falha. Capacidade realmente
solicitada pelo preset, como SERP, Apdex ou Análise profunda, precisa satisfazer seu próprio
contrato.

## IA

Existe uma única IA principal por execução.

Para perfis que não exigem IA, a UI oferece:

```text
não adicionar IA pelo perfil e preservar a seleção atual da sessão
usar IA principal/AUTO somente se a sessão estiver sem IA e houver provider APTO
```

O primeiro caso **não equivale a `SEM IA`** se o operador já havia selecionado uma IA antes do
perfil.

Análise profunda exige IA principal. Não existe provider/model/reasoning especializado paralelo.
`AUTO` continua governado pelo runtime central de elegibilidade, preço, quarentena, circuit
breaker, fallback e limite de tentativas.

## Google Search Console

GSC continua independente de SERP e do preset técnico. Após selecionar um perfil, a execução
pode:

- usar somente se a property cobrir a URL;
- exigir GSC;
- não usar GSC nesta execução;
- herdar a política global.

A política é session-only e não regrava credenciais nem `RASAI_GSC_ENABLED`.

## Perfil personalizado

A composição personalizada mostra somente capacidades que representam workloads
selecionáveis. Capacidades automáticas/derivadas permanecem incluídas pelo contrato normal.

`Apdex de experiência` adiciona `Apdex de navegação` como dependência. A UI não permite remover
Navigation enquanto Experience continuar selecionado.

## Persistência e evidências

O preset não grava INI, Windows/User, Windows/Machine nem credenciais.

O snapshot secret-free do AUD registra o perfil em termos de **capacidades**, além de:

- identificador/rótulo do perfil;
- política de IA;
- overrides explícitos feitos depois da seleção.

A página `report/execution-evidence.html` deve continuar representando o contrato efetivo da
execução: solicitado, não solicitado, concluído, parcial, falha ou configuração necessária.

## Desenvolvimento

O programa permanece em desenvolvimento e não possui versão pública/legado a preservar. Esta
arquitetura é o contrato vigente; não existe camada de migração para o modelo anterior de módulos
de perfil.

Documentos relacionados: `CONSOLE_CONFIGURATION_UX.md`,
`EXECUTION_EVIDENCE_AND_CONFIGURATION_INTEGRITY.md`, `INTERACTIVE_CONSOLE.md` e
`PROVIDER_SETUP.md`.
