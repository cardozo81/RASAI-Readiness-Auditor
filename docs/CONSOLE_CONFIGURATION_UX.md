# Contrato de UX para configuração no console

Este documento define o padrão canônico para qualquer variável, credencial ou opção avançada exposta pelo `rasai-console`.

O objetivo é impedir que o operador precise conhecer previamente o código, o nome interno de um enum ou a documentação de um fornecedor para configurar uma capacidade do RASAi.

## 1. Regra principal

Nenhuma configuração com domínio fechado deve depender de texto livre.

O console deve aplicar a seguinte ordem:

1. **booleano**: seleção explícita `true` / `false`;
2. **enum**: seleção entre os valores aceitos pelo runtime/registry;
3. **lista fechada**: seleção múltipla entre os valores aceitos;
4. **provider/model/reasoning**: lista derivada do registry canônico correspondente;
5. **valor aberto**: entrada textual somente quando o dado realmente não possuir domínio finito, por exemplo URL, caminho, token, property, locale ou número contínuo.

O runtime continua sendo a autoridade de validação. O console não deve manter uma segunda lista divergente quando um registry ou contrato já publicar os valores válidos.

## 2. Informações obrigatórias por variável

Ao abrir uma variável, a UI deve tornar visíveis, quando aplicáveis:

- nome canônico da variável;
- grupo funcional;
- **contexto/recurso** ao qual ela pertence;
- finalidade em linguagem operacional;
- tipo do dado;
- valores válidos;
- default efetivo;
- condição que torna a configuração necessária;
- indicação se o valor é sensível;
- impacto de custo, quota, carga, segurança ou comportamento;
- valor/estado atual;
- exemplo de preenchimento;
- referência interna detalhada;
- documentação oficial do recurso externo;
- URL oficial de criação/login/credencial quando existir;
- observações de quota, free tier ou limitação metodológica relevantes.

Uma variável não deve aparecer apenas como `RASAI_* = ?` sem explicar para que será usada.

## 3. Organização por contexto

A categoria continua representando a área funcional ampla. Dentro dela, o console agrupa as variáveis pelo recurso operacional sempre que for possível.

Exemplos:

```text
Métricas e padrões
  [Google Search Console]
    RASAI_GSC_ENABLED
    RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
    RASAI_GSC_SEARCH_ANALYTICS_DAYS
    RASAI_GSC_SEARCH_MAX_ROWS
    RASAI_GSC_FINAL_DATA_LAG_DAYS

Web Performance / Google APIs
  [Google PageSpeed / Lighthouse]
    RASAI_PAGESPEED_ENABLED
    RASAI_PAGESPEED_API_KEY
    RASAI_LIGHTHOUSE_CATEGORIES

  [Google Chrome UX Report (CrUX)]
    RASAI_CRUX_ENABLED
    RASAI_CRUX_API_KEY

Synthetic Apdex
  [Synthetic Navigation Apdex]
  [Synthetic User Experience Apdex]
  [Dynatrace / calibração Apdex]
```

Secrets podem permanecer em uma categoria tecnicamente apropriada para persistência/segurança, mas a UI deve deixar explícito o contexto ao qual pertencem e as dependências cruzadas.

## 4. Semântica de cores

Cor é reforço visual; o texto do estado continua obrigatório.

| Estado | Cor | Semântica |
|---|---|---|
| `APTO`, `DEFINIDO`, `ON`, credencial presente | verde | capacidade/configuração disponível |
| `CONFIGURAR`, atenção, requisito pendente | amarelo | ação necessária ou condição a revisar |
| `INDISPONÍVEL`, erro, bloqueio | vermelho | execução impedida |
| `PADRÃO`, `OPCIONAL`, `DESABILITADA`, ausente/inativo | cinza/dim | ausência deliberada, default ou hard-off |
| contexto, breadcrumb, informação explicativa | ciano | navegação/informação |

Valores booleanos seguem a mesma convenção: `true` é destacado como ativo; `false` aparece como desabilitado/dim.

## 5. Seleção guiada

### Booleano

Exemplo:

```text
RASAI_GSC_ENABLED

Valores válidos:
 1. true
 2. false
 V. Voltar
```

A documentação pode mencionar aliases aceitos pelo parser (`1/0`, `yes/no`, `on/off`), mas o console deve apresentar `true` e `false` como forma canônica.

### Enum

Exemplo:

```text
RASAI_DEVICE_CONTEXT

Valores válidos:
 1. mobile
 2. desktop
 3. both
```

### Lista fechada

Exemplo:

```text
RASAI_LIGHTHOUSE_CATEGORIES

Valores válidos (seleção múltipla):
 1. performance
 2. accessibility
 3. best-practices
 4. seo
 5. agentic-browsing
```

O usuário pode selecionar os itens sem digitar manualmente os tokens canônicos.

## 6. Valores abertos

Texto livre continua correto para dados cujo conjunto não é enumerável, por exemplo:

- URL e endpoint;
- caminho de arquivo;
- Search Console property (`sc-domain:...` ou URL-prefix);
- API key/token/secret;
- número com faixa contínua;
- locale/tag BCP-47;
- identificadores externos do cliente/IdP.

Nesses casos, a UI deve exibir tipo, formato, exemplo, dependências e documentação antes da edição.

## 7. Referências oficiais de integrações

As URLs devem preferencialmente vir dos registries canônicos usados pelo runtime.

| Recurso | Documentação | Credencial/login |
|---|---|---|
| Google Search Console API | https://developers.google.com/webmaster-tools/v1/api_reference_index | https://console.cloud.google.com/apis/credentials |
| Google PageSpeed Insights | https://developers.google.com/speed/docs/insights/v5/get-started | https://console.cloud.google.com/apis/credentials |
| Chrome UX Report API | https://developer.chrome.com/docs/crux/api/ | https://console.cloud.google.com/apis/credentials |
| W3C Nu HTML Checker | https://validator.w3.org/docs/api | não exige credencial |
| W3C CSS Validation Service | https://jigsaw.w3.org/css-validator/api.html | não exige credencial |
| MDN HTTP Observatory | https://developer.mozilla.org/en-US/observatory/docs/faq | não exige credencial |
| Web Platform Baseline / WebDX | https://github.com/web-platform-dx/web-features | dataset local/versionado |
| OpenID Connect | https://openid.net/specs/openid-connect-core-1_0.html | depende do IdP escolhido |
| PostgreSQL connection strings | https://www.postgresql.org/docs/current/libpq-connect.html | depende do deployment |
| Playwright browsers | https://playwright.dev/python/docs/browsers | não exige credencial |

Para IA e SERP, as URLs oficiais são derivadas respectivamente de `provider_registry` e `search_intelligence.provider_catalog`, evitando duplicação manual no console.

## 8. Google Search Console como exemplo completo

`RASAI_GSC_ENABLED` controla a elegibilidade da coleta observacional do Search Console.

O contexto completo inclui:

```text
RASAI_GSC_ENABLED
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
RASAI_GSC_SEARCH_ANALYTICS_DAYS
RASAI_GSC_SEARCH_MAX_ROWS
RASAI_GSC_FINAL_DATA_LAG_DAYS
```

Sem override de `RASAI_GSC_ENABLED`, o serviço pode entrar em modo automático quando token e property obrigatórios estiverem disponíveis. `false` representa hard-off explícito. `true` solicita explicitamente o serviço, mas não substitui os requisitos de autenticação/property.

A property deve corresponder a uma propriedade à qual o usuário autenticado tenha acesso:

```text
sc-domain:example.com
```

ou uma propriedade URL-prefix HTTP(S) válida.

O access token é secret e nunca entra no `rasai-console.ini`.

## 9. Fonte de verdade e extensibilidade

A UX não deve criar contratos paralelos.

A prioridade é:

```text
runtime / registry canônico
        ↓
EnvironmentSpec / metadata composta
        ↓
console guiado
        ↓
documentação
```

Quando uma extensão adicionar um novo booleano ou enum ao catálogo em runtime, a superfície guiada deve herdar automaticamente o comportamento de seleção. Quando um provider registrado informar URLs oficiais, a UI deve apresentá-las sem exigir duplicação manual.

## 10. Critério de aderência

Uma nova variável configurável só está aderente quando:

- possui finalidade compreensível;
- possui tipo e default explícitos;
- possui domínio fechado registrado quando aplicável;
- não exige digitação livre para booleano/enum conhecido;
- aparece no contexto funcional correto;
- explica dependências;
- informa impacto/custo quando material;
- apresenta documentação/credencial oficial quando o recurso externo fornecer referência;
- respeita a semântica de cores do console;
- não expõe secrets no INI, logs ou relatórios.

Documentos complementares: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md), [PROVIDER_SETUP.md](PROVIDER_SETUP.md), [STANDARDS_METRICS_AND_SERVICES.md](STANDARDS_METRICS_AND_SERVICES.md) e [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md).
