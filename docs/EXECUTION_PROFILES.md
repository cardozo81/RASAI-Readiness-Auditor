# Perfis da próxima auditoria

Perfis são overlays temporários da próxima execução do `rasai-console`. Eles reduzem ajustes manuais sem criar uma segunda fonte de verdade, sem persistir credenciais e sem criar um pipeline alternativo.

## Acesso e precedência

Perfis nomeados ficam disponíveis somente para uma URL única explícita.

```text
ajuste explícito feito depois da seleção do perfil
> overlay temporário do perfil
> configuração normal da sessão / INI / SO
> default canônico
```

A camada vencedora vale para a execução correspondente, mas não regrava as camadas inferiores.

## Catálogo vigente

1. SEO / Search Readiness;
2. GEO / AI Readiness;
3. Performance;
4. Acessibilidade;
5. Web Quality;
6. SEO + GEO;
7. SEO + GEO + Performance;
8. Search Intelligence / SERP;
9. Experiência sintética;
10. Análise profunda URL;
11. Completo seguro;
12. Completo máximo;
13. Personalizado.

A composição continua baseada em módulos. Categorias Lighthouse repetidas entre módulos são deduplicadas antes da execução; por isso `Completo seguro` pode conter SEO, Acessibilidade e Web Quality sem gerar uma segunda execução equivalente da mesma categoria.

## Readiness e referências da preparação

A UI usa as referências canônicas da tela `INÍCIO > PREPARAR AUDITORIA`:

```text
item 6  = IA principal
item 8  = Análise profunda URL
item 12 = Synthetic Apdex
item 13 = Termos SERP
```

`Falta` deve apontar para esses itens atuais e para o nome da configuração. Não usar referências históricas como `item T`, `item 13` para Análise profunda ou números internos dos handlers.

### Search Intelligence / SERP

O perfil não inventa termos. Para ficar `APTO`:

- os Termos SERP devem existir no item 13;
- modo/provider devem formar um contrato válido;
- no modo `live`, a credencial do provider deve estar apta;
- limites e demais validadores canônicos continuam sendo autoridade.

### Experiência sintética

O perfil não inventa threshold, amostras ou carga. A pendência é apresentada como:

```text
configure Synthetic Apdex no item 12
```

Se Experience Apdex fizer parte da medição desejada, sua própria configuração também precisa permanecer válida e compatível com Navigation Apdex.

### Análise profunda URL

Análise profunda usa **a mesma IA principal/orquestrador canônico da auditoria**. Não existe provider/model/reasoning especializado para esse módulo.

Ao selecionar um perfil que contém `deep-analysis`:

- o próprio perfil solicita `improvement_enabled=true` apenas dentro do overlay da execução;
- não é necessário habilitar previamente o item 8 apenas para satisfazer o perfil;
- URL única continua obrigatória;
- uma IA principal ou `AUTO` apta é obrigatória no item 6;
- a seleção de IA não pode ser desligada dentro de um perfil que exige Análise profunda;
- custo, elegibilidade, preço, quarentena, circuit breaker e fallback continuam pertencendo ao runtime central.

Isso corrige a combinação incoerente em que um perfil de Análise profunda podia ser considerado apto e, em seguida, permitir `SEM IA`, o que tornaria o próprio módulo inexequível.

## Perfis amplos

### Completo seguro

Inclui:

- SEO;
- GEO;
- Performance;
- Acessibilidade;
- Web Quality.

Não ativa automaticamente:

- SERP;
- Synthetic Apdex/Experience;
- Análise profunda;
- Microsoft Clarity ou outra integração externa opt-in.

Integrações externas que já estiverem habilitadas continuam obedecendo ao próprio contrato. O perfil não regrava seus toggles.

### Completo máximo

Inclui todos os módulos de workload do catálogo. `Máximo` não significa ignorar guardrails.

Ele pode ficar `CONFIGURAR` quando faltar, por exemplo:

- Termos SERP no item 13;
- configuração sintética no item 12;
- IA principal/AUTO apta no item 6.

O perfil solicita Análise profunda por conta própria; portanto `item 8 desligado` isoladamente não é mais tratado como uma pendência prévia do preset.

Credenciais, termos SERP e parâmetros metodológicos sem default seguro nunca são fabricados pelo perfil.

## IA principal do perfil

Perfis sem Análise profunda podem:

- não adicionar uso opcional de IA; ou
- usar a IA principal/AUTO se houver provider apto.

Perfis com Análise profunda usam IA principal obrigatoriamente. A UI informa isso diretamente e não oferece uma escolha contraditória de `SEM IA`.

Em `AUTO`, o runtime central decide provider/modelo conforme:

- elegibilidade;
- disponibilidade;
- custo/preço vigente;
- quarentena;
- circuit breaker;
- fallback;
- limite de tentativas.

## Google Search Console

GSC continua independente de SERP e do catálogo de módulos. Depois de selecionar o perfil, a execução pode:

```text
usar somente se a property cobrir a URL
exigir GSC
não usar nesta execução
herdar a política global
```

A política do perfil é session-only e não regrava `RASAI_GSC_ENABLED`.

## O que um perfil pode fazer

Um perfil pode projetar escolhas já suportadas pelos contratos existentes:

- solicitar Web Performance;
- compor categorias Lighthouse;
- preservar/usar Search quando seus inputs existem;
- solicitar carga sintética quando sua configuração está válida;
- solicitar Análise profunda quando URL e IA principal estão aptas;
- projetar política GSC da execução.

## O que um perfil não faz

Um perfil não pode:

- criar ou persistir credenciais;
- alterar Windows/User ou Windows/Machine;
- inventar termos SERP;
- inventar contexto editorial/YMYL;
- inventar thresholds/amostras/carga de Apdex;
- ligar silenciosamente integrações opt-in de quota restrita;
- alterar SARI/SCORE-GEO;
- criar uma IA especializada paralela;
- substituir preflight/validadores.

## UI

A listagem de perfis prioriza leitura operacional:

```text
[número] [APTO|CONFIGURAR] Nome do perfil
         Escopo : módulos
         Impacto: APIs/quota/carga/IA que podem ser usados
         IA     : opcional ou obrigatória
         Falta  : somente dependências realmente pendentes
```

Detalhes extensos de custo/exposição aparecem após a seleção, evitando repetir parágrafos longos para cada perfil na tela principal.

## Persistência e execução

O perfil é consumido pelo pipeline normal:

```text
defaults
+ sessão/INI/SO
+ overlay do perfil
+ ajustes explícitos posteriores
-> configuração efetiva
-> preflight
-> pipeline normal
```

Selecionar um perfil não grava o preset no `rasai-console.ini`. Secrets permanecem fora do arquivo.

Documentos relacionados: [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [CONSOLE_READINESS_REFINEMENTS.md](CONSOLE_READINESS_REFINEMENTS.md), [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
