# Contrato de UX para configuração no console

Este documento define o padrão canônico para variáveis, credenciais, opções avançadas e Perfis de Execução expostos pelo `rasai-console`.

O objetivo é permitir que o operador configure capacidades do RASAi sem precisar conhecer previamente nomes internos, enums, registries ou documentação de fornecedores.

## 1. Regra principal

Nenhuma configuração com domínio fechado deve depender de texto livre.

Ordem preferencial:

1. **booleano**: seleção explícita `true` / `false`;
2. **enum**: seleção entre valores aceitos pelo runtime/registry;
3. **lista fechada**: seleção múltipla;
4. **provider/model/reasoning**: lista derivada do registry canônico;
5. **valor dependente**: recalculado a partir da dependência vigente;
6. **valor aberto**: texto apenas quando o dado realmente não possui domínio finito, como URL, caminho, token, property, locale ou número contínuo.

O runtime continua sendo a autoridade de validação. O console não deve manter uma lista paralela divergente quando um registry ou contrato já publica os valores válidos.

### 1.1 Convenção do dashboard Preparar auditoria

A tela `INÍCIO > PREPARAR AUDITORIA` usa uma convenção única:

```text
número = parâmetro editável da próxima auditoria
letra  = ação, comando ou navegação
título = agrupamento visual; nunca é uma opção
```

A sequência canônica é contínua e sem atalhos de configuração por letra:

```text
[ ESCOPO ]
 1. Entrada
 2. Projeto
 3. Dispositivo
 4. Idioma / mercado
 5. Timezone apresentação

[ INTELIGÊNCIA ARTIFICIAL ]
 6. IA
 7. Remediações IA
 8. Análise profunda URL

[ WEB PERFORMANCE ]
 9. Web Performance
10. Máx. páginas da auditoria
11. Máx. páginas em Web Performance
12. Synthetic Apdex

[ SEARCH INTELLIGENCE ]
13. Termos SERP

[ ARMAZENAMENTO / EXECUÇÃO ]
14. Raiz auditorias

[ PERFIL DA PRÓXIMA EXECUÇÃO ]
15. Perfil da execução
```

As ações permanecem identificadas por letras:

```text
R. Executar
S. Salvar configuração INI
L. Carregar configuração de AUD
E. Integrações / credenciais
C. Histórico / relatórios consolidados
H. Ajuda / custos
V. Voltar ao início
Q. Sair
```

`Restaurar padrões do RASAi` não pertence à preparação de uma auditoria. A restauração global existe somente em `INÍCIO > Sistema / restaurar padrões`.

## 2. Informações obrigatórias por variável

A UI deve tornar visíveis, quando aplicáveis:

- nome canônico e grupo funcional;
- contexto/recurso;
- finalidade operacional;
- tipo, valores válidos e default efetivo;
- condição que torna a configuração necessária;
- indicação de dado sensível;
- impacto de custo, quota, carga, segurança ou comportamento;
- estado atual;
- exemplo;
- referência interna;
- documentação oficial;
- URL oficial de criação/login/credencial;
- observações de free tier ou limitações metodológicas.

Uma variável não deve aparecer apenas como `RASAI_* = ?` sem contexto.

## 3. Organização por contexto

A categoria representa a área funcional ampla e, dentro dela, a UI agrupa por recurso operacional.

Exemplo:

```text
Métricas e padrões
  [Google Search Console]
    RASAI_GSC_ENABLED
    RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
    ...

Web Performance / Google APIs
  [Google PageSpeed / Lighthouse]
    RASAI_PAGESPEED_ENABLED
    RASAI_PAGESPEED_API_KEY
    RASAI_LIGHTHOUSE_CATEGORIES

  [Google Chrome UX Report]
    RASAI_CRUX_ENABLED
    RASAI_CRUX_API_KEY

Synthetic Apdex
  [Synthetic Navigation Apdex]
  [Synthetic User Experience Apdex]
  [Dynatrace / calibração Apdex]
```

Secrets podem permanecer em uma categoria tecnicamente apropriada, mas a UI deve deixar claro a qual integração pertencem.

## 4. Semântica de estados e cores

Cor é reforço visual; o texto do estado é obrigatório.

| Estado | Cor | Semântica |
|---|---|---|
| `APTO`, `DEFINIDO`, `ON` | verde | capacidade disponível |
| `CONFIGURAR`, atenção | amarelo | ação obrigatória ou condição a revisar |
| `INDISPONÍVEL`, erro, bloqueio | vermelho | recurso não utilizável no contexto atual |
| `PADRÃO`, `OPCIONAL`, `DESABILITADA` | cinza/dim | ausência deliberada/default |
| contexto/informação | ciano | orientação |

`CONFIGURAR` não deve ser usado como sinônimo de falha do runtime: ele representa uma pendência conhecida antes da execução.

## 5. Seleção guiada

### Booleano

```text
RASAI_GSC_ENABLED

Valores válidos:
 1. true
 2. false
 V. Voltar
```

### Enum

```text
RASAI_DEVICE_CONTEXT

Valores válidos:
 1. mobile
 2. desktop
 3. both
```

### Lista fechada

```text
RASAI_LIGHTHOUSE_CATEGORIES

Valores válidos:
 1. performance
 2. accessibility
 3. best-practices
 4. seo
 5. agentic-browsing
```

### Domínio dependente

Quando modelo/reasoning dependem do provider, a lista deve ser recalculada depois da escolha do provider. O usuário não deve precisar conhecer o catálogo interno.

## 6. Valores abertos

Texto livre permanece correto para:

- URL e endpoint;
- caminho de arquivo;
- Search Console property;
- API key/token/secret;
- número com faixa contínua;
- locale/tag BCP-47;
- identificadores externos.

A UI deve exibir formato, exemplo, dependências e documentação antes da edição.

`RASAI_WEB_FEATURES_DATASET`, por exemplo, é caminho para arquivo local do dataset WebDX/web-features, não enum como `latest`/`stable`.

## 7. Secrets mascarados e canceláveis

Secrets não aparecem em claro. Quando o terminal permite leitura segura caractere a caractere, o feedback visual é mascarado:

```text
OPENAI_API_KEY: ************************
```

A edição é staged:

```text
C. Confirmar alteração
V. Cancelar e manter o valor atual
```

Regras:

- valor real nunca é ecoado;
- secret não entra no `rasai-console.ini`;
- cancelamento ocorre antes de mutação de sessão/persistência;
- fallback de terminal usa `getpass`, nunca texto em claro;
- falha de mascaramento não pode reduzir o nível de proteção.

## 8. Reset de variáveis

O console disponibiliza reset seguro pelo catálogo canônico, distinguindo:

1. sessão atual;
2. sessão + `rasai-console.ini`;
3. Windows: sessão + INI + Windows/User.

Remoção de Windows/User exige confirmação destrutiva. Windows/Machine nunca é removido pelo RASAi.

Reset significa retornar ao default/auto/ausência do runtime, não inventar valores.

A restauração global da baseline do produto é uma função de sistema e fica exclusivamente em:

```text
INÍCIO > Sistema / restaurar padrões
```

Ela não é exibida como ação de `Preparar auditoria`.

Contrato detalhado: [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md).

## 9. Perfis de Execução de sessão

Perfis reduzem a necessidade de alternar várias configurações antes de uma auditoria. São overlays temporários e não criam nova fonte de verdade.

Disponíveis apenas com **uma URL única explícita**:

```text
15. Perfil da execução
```

Regras obrigatórias:

- existem apenas na sessão/execução atual;
- não são gravados no INI;
- não alteram Windows/User ou Windows/Machine;
- não criam/trocam/persistem credenciais;
- apresentam módulos, dependências e custo/quota/carga antes da aplicação;
- ajustes finos posteriores vencem o preset no domínio alterado;
- a configuração-base é restaurada depois da projeção temporária.

### 9.1 Catálogo sempre visível

Todos os presets devem permanecer visíveis mesmo quando ainda não podem ser usados.

```text
 1. [APTO] SEO / Search Readiness
 ...
 8. [CONFIGURAR] Search Intelligence / SERP
     Falta: termos SERP no item 13
 9. [CONFIGURAR] Experiência sintética
     Falta: Synthetic/Experience Apdex no item 12
10. [CONFIGURAR] Análise profunda URL
     Falta: item 8 / IA principal no item 6
12. [CONFIGURAR] Completo máximo
     Falta: ...
```

A finalidade é transformar o catálogo também em guia de parametrização.

### 9.2 Perfil `CONFIGURAR` não é selecionável

Quando um preset possui dependência obrigatória ausente:

- continua visível;
- mostra cada pendência em linguagem operacional;
- informa o item/menu onde o usuário deve configurar;
- **não entra no estado ativo da sessão**;
- não chega ao passo de aplicação até ficar `APTO`.

Depois da parametrização, o operador retorna ao catálogo e o estado é recalculado dinamicamente.

Isso evita a falsa expectativa de uma execução "completa" quando SERP, Apdex ou Improvement Intelligence ainda não podem rodar.

### 9.3 Dependências que nunca são inventadas

- Search Intelligence exige termos no item 13 e contrato SERP válido, incluindo provider/credencial quando aplicável;
- GEO preserva contexto editorial/YMYL explícito ou `AUTO`;
- Experiência sintética exige parâmetros Apdex já configurados no item 12;
- Análise profunda exige item 8 habilitado e IA principal apta no item 6;
- IA padrão pode ser `SEM IA` ou `IA SE DISPONÍVEL`; ausência de provider apto no segundo modo não bloqueia o core.

### 9.4 Completo seguro e Completo máximo

`Completo seguro` cobre SEO, GEO, Performance, Acessibilidade e Web Quality sem ativar automaticamente SERP, carga sintética ou análise profunda.

`Completo máximo` cobre todos os módulos do catálogo, mas só fica `APTO` depois que Search Intelligence, Experiência sintética e Análise profunda estiverem devidamente parametrizados.

"Máximo" significa cobertura funcional, não redução de segurança ou limites.

Contrato detalhado: [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md).

## 10. Referências oficiais de integrações

As URLs devem vir preferencialmente dos registries canônicos.

| Recurso | Documentação | Credencial/login |
|---|---|---|
| Google Search Console API | https://developers.google.com/webmaster-tools/v1/api_reference_index | https://console.cloud.google.com/apis/credentials |
| Google PageSpeed Insights | https://developers.google.com/speed/docs/insights/v5/get-started | https://console.cloud.google.com/apis/credentials |
| Chrome UX Report API | https://developer.chrome.com/docs/crux/api/ | https://console.cloud.google.com/apis/credentials |
| W3C Nu HTML Checker | https://validator.w3.org/docs/api | não exige credencial |
| W3C CSS Validation Service | https://jigsaw.w3.org/css-validator/api.html | não exige credencial |
| MDN HTTP Observatory | https://developer.mozilla.org/en-US/observatory/docs/faq | não exige credencial |
| Web Platform Baseline / WebDX | https://github.com/web-platform-dx/web-features | dataset local/versionado |
| OpenID Connect | https://openid.net/specs/openid-connect-core-1_0.html | depende do IdP |
| PostgreSQL | https://www.postgresql.org/docs/current/libpq-connect.html | depende do deployment |
| Playwright browsers | https://playwright.dev/python/docs/browsers | não exige credencial |

Para IA e SERP, URLs oficiais devem ser derivadas de `provider_registry` e `search_intelligence.provider_catalog`.

## 11. Fonte de verdade

Prioridade:

```text
runtime / registry canônico
        ↓
EnvironmentSpec / metadata composta
        ↓
console guiado
        ↓
documentação
```

Perfis apenas projetam escolhas sobre contratos existentes. Não mantêm metodologia, credenciais ou defaults paralelos.

## 12. Reporting e expectativa do usuário

O console deve impedir dependências conhecidas antes da seleção, mas não pode prometer que uma integração externa concluirá com sucesso.

Depois da execução, os HTMLs continuam representando o que foi realmente persistido:

- solicitado e concluído;
- solicitado e parcial/falho;
- não solicitado/desabilitado;
- indisponível por provider/rede/contrato.

Perfis não fabricam evidência nem score. `ai-usage.html` e os quadros de consumo por página permanecem a fonte de transparência para chamadas/tokens/custo de IA.

## 13. Critério de aderência

Uma nova configuração/superfície só está aderente quando:

- finalidade, tipo e default são compreensíveis;
- domínio fechado é guiado;
- dependências são explicadas;
- custo/impacto é informado quando material;
- referências oficiais são apresentadas quando disponíveis;
- semântica de estados/cores é respeitada;
- secrets são mascarados, canceláveis e não vazam em INI/log/report;
- reset destrutivo exige confirmação;
- Perfis de Execução permanecem session-only;
- presets `CONFIGURAR` ficam visíveis para orientação, mas não são aplicados;
- relatórios continuam evidence-bound e distinguem ausência, falha e execução real.

Documentos complementares: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md), [PROVIDER_SETUP.md](PROVIDER_SETUP.md), [STANDARDS_METRICS_AND_SERVICES.md](STANDARDS_METRICS_AND_SERVICES.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md) e [WEB_PLATFORM_BASELINE.md](WEB_PLATFORM_BASELINE.md).