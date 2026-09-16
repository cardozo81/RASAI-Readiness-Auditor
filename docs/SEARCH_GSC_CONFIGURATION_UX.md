# Agrupamento de configuração: SERP e Google Search Console

## Objetivo

`CAT-05 Search & AI Intelligence` reúne a intenção funcional de Search, mas **SERP e Google Search Console continuam sendo fontes independentes**. A UI não deve apresentar suas propriedades como uma lista única de variáveis.

A estrutura pública deve permitir ao operador entender três dimensões sem conhecer nomes `RASAI_*`:

1. o que pertence ao **escopo da próxima execução**;
2. o que configura o **serviço/integrador** de forma reutilizável;
3. quais dados são **credenciais** e onde podem ser persistidos.

Os IDs numéricos canônicos continuam sendo a identidade pública de cada configuração. O nome técnico da variável permanece disponível somente em `T. Detalhes técnicos`.

## Escopo da próxima execução

Antes das propriedades persistentes dos serviços, CAT-05 mostra separadamente os inputs do pedido atual.

A apresentação pública segue esta estrutura:

```text
ESCOPO DESTA EXECUÇÃO
  URL / entrada
  Idioma / mercado
  Device da auditoria

O QUE PESQUISAR
  Termos de busca
  Quantidade de termos
  Localidade
  Profundidade desejada (Top N)
  Dispositivo da busca
  Análise de concorrentes

GOOGLE SEARCH CONSOLE
  Estado para a URL atual
```

Os valores internos `search_queries`, `search_region`, `search_depth`, `search_device` e `search_competitive` não são nomes apresentados ao operador. A UI usa rótulos funcionais.

`Profundidade desejada` significa o Top N que será consultado para cada termo. Ela não deve ser confundida com a configuração persistente `profundidade máxima permitida`, que é um limite de governança do serviço.

Esses dados não devem ser confundidos com credencial, provider ou limites operacionais persistentes.

## SERP

As configurações SERP são apresentadas nesta ordem:

### Ativação e modo de coleta

- modo `disabled`, `live` ou `fixture`.

### Provider e credencial

- provider SERP selecionado;
- chave correspondente ao provider live.

A credencial exibida depende do registry canônico do provider. Secrets nunca são exibidos e nunca entram no `rasai-console.ini`.

### Escopo e limites de coleta

- máximo de termos;
- máximo de requests;
- profundidade máxima;
- máximo de concorrentes observados.

Esses limites são governança técnica do RASAi e não representam necessariamente a unidade comercial cobrada pelo fornecedor.

### Rede, retries e ritmo

- timeout;
- retries;
- intervalo mínimo entre requests.

### Fixture / teste offline

- caminho da fixture, aplicável somente ao modo de teste offline.

## Google Search Console

GSC é apresentado em grupos independentes da SERP.

### Ativação

- política de uso do Google Search Console.

### OAuth temporário - teste/uso pontual

- Access Token.

O Access Token é uma alternativa temporária. Ele **não é obrigatório em paralelo** quando o fluxo OAuth durável está configurado.

### OAuth durável - recomendado

- Client ID;
- Client Secret;
- Refresh Token.

Client Secret e Refresh Token são secrets. Client ID não é segredo e pode seguir a política normal de persistência não sensível.

### Property e cobertura da URL auditada

- property do Google Search Console.

A property é validada contra o alvo da auditoria. Uma property incompatível não deve ser descrita como falha da SERP.

### Search Analytics - janela e volume

- quantidade de dias consultados;
- máximo de linhas;
- defasagem usada para considerar dados finalizados.

Sitemaps e URL Inspection reutilizam a mesma autenticação/property; não exigem um segundo conjunto de credenciais.

## Regra de independência

A UI deve deixar explícito:

```text
SERP configurada != GSC configurado
GSC configurado  != SERP configurada
```

Uma dependência GSC ausente ou inválida só bloqueia o plano quando GSC pertence ao escopo efetivamente selecionado/requerido. O mesmo princípio vale para SERP.

## Visibilidade de configurações

`INÍCIO > Todas as configurações` é a superfície de escape completa do operador. Toda configuração registrada no catálogo público deve ser alcançável nessa tela, independentemente de também aparecer em um catálogo funcional.

A suíte de regressão mantém dois contratos:

- toda variável de runtime classificada como configuração pública deve estar registrada no catálogo do console;
- todo `EnvironmentSpec` registrado deve ser alcançável em `Todas as configurações`.

Marcadores internos de subprocesso e seletores de IA locais já aposentados não fazem parte da superfície pública.

## Persistência

Ao usar `Salvar configuração`, o INI passa a ser também um inventário completo da configuração pública não sensível:

- toda configuração pública não sensível é materializada na seção `[environment]`;
- a precedência para o valor salvo é: valor explícito da sessão/ambiente, projeção do estado do console, default público do runtime;
- configurações públicas sem valor efetivo nem default permanecem listadas com valor vazio;
- os inputs não sensíveis de Search ficam na seção `[search_intelligence]` (`queries`, `depth`, `region`, `device`, `competitive`);
- secrets permanecem somente em sessão ou Windows/User, conforme suporte existente;
- API keys, tokens, client secrets, passwords e outros valores classificados como sensíveis nunca entram no INI;
- o snapshot do AUD continua preservando o plano efetivo da execução conforme seu contrato próprio.

Isso significa que parâmetros SERP como modo, provider, limites, timeout, retries e intervalo passam a ser persistidos mesmo quando o operador estiver usando o default efetivo e nunca tiver criado um override manual.

Documentos relacionados: [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
