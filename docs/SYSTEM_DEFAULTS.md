# Padrões canônicos do sistema

O `rasai-console` possui uma baseline versionada em `src/rasai/config/rasai-defaults.ini`.

Esse arquivo representa a configuração padrão do produto para uma instalação nova e para a ação **Sistema / restaurar padrões**. Ele não substitui o `rasai-console.ini` do usuário e nunca contém secrets.

## Precedência

A configuração efetiva do console local segue:

1. argumento/ação explícita da sessão, quando aplicável;
2. variável de ambiente/processo ou valor persistido no SO;
3. `rasai-console.ini` do usuário;
4. `rasai-defaults.ini` versionado do produto;
5. fallback defensivo interno do código.

O `rasai-console.ini` é salvo pelo writer canônico. API keys, bearer tokens, passwords, DSNs com credencial e demais secrets não são escritos nele.

Uma configuração explícita de maior precedência também governa dependências do baseline. Como Synthetic User Experience Apdex depende de Synthetic Navigation Apdex, `RASAI_SYNTHETIC_APDEX=false` torna Experience efetivamente `false`, inclusive quando um valor `true` de camada inferior foi materializado pelo baseline/INI. Para executar Experience, Navigation precisa estar habilitado.

## Política da baseline

A baseline procura habilitar o máximo de capacidade de auditoria sem exigir credencial:

- capacidade interna/local sem credencial: habilitada;
- serviço externo gratuito sem credencial: habilitado quando metodologicamente seguro;
- integração que exige credencial: dirigida por requisitos/AUTO ou desabilitada até a configuração obrigatória existir;
- superfície administrativa/de segurança: fail-closed;
- valores específicos do cliente que não podem ser inventados permanecem vazios/AUTO.

Por isso W3C Nu HTML Checker, W3C CSS Validator, MDN HTTP Observatory, métricas derivadas, métricas de Information Retrieval, Open Web Metrics e Web Platform Baseline podem permanecer habilitados por padrão. Indisponibilidade, rate limit, egress bloqueado ou ausência de dataset é tratada como limitação/NO_DATA/UNAVAILABLE, nunca como finding artificial do website.

PageSpeed, CrUX e Google Search Console não recebem hard-on/hard-off obrigatório na baseline apenas para forçar disponibilidade. Eles permanecem condicionados a requisitos, política e configuração efetiva.

## Synthetic Apdex

Synthetic Navigation Apdex e Synthetic User Experience Apdex possuem defaults técnicos do runtime. A interface do console pode projetar valores derivados da próxima auditoria sem alterar esses defaults canônicos.

### Navigation Apdex

Baseline técnica:

- habilitado: `true`;
- threshold `T`: `3 s`;
- amostras válidas por URL/dispositivo: `1`;
- máximo de tentativas: `2`;
- máximo de páginas: `1`;
- concorrência: `1`;
- delay: `1 s`.

`T=3 s` é uma baseline RASAi compatível com a referência temporal adotada pelo produto; não é apresentado como SLO universal. Quando a organização conhece seu SLO/Task target real, esse valor deve prevalecer.

Com `T=3 s`, Navigation Apdex classifica `Satisfied <= 3 s`, `Tolerating > 3 s e <= 12 s` e `Frustrated > 12 s`.

### Experience Apdex - baseline do runtime

Na ausência de configuração projetada pela interface, override explícito ou importação aplicável, o runtime preserva sua baseline técnica:

- habilitado: `true`;
- amostras válidas por página: `20` na baseline de sistema;
- máximo de tentativas: `25`;
- máximo de páginas: `1`;
- device mix técnico: `mobile=60,desktop=35,tablet=5`;
- sessão: `cold`;
- KPM executável: `USER_ACTION_DURATION`;
- Satisfied: `3 s`;
- Frustrated: `12 s`;
- erros qualificáveis afetam Apdex: `true`;
- escopo de erro: `first-party`;
- concorrência: `1`.

O mix `60/35/5` pertence ao contrato técnico do runtime/CLI e continua disponível quando nenhuma camada de maior precedência o substitui.

### Experience Apdex - herança normal do console

Na preparação interativa, quando o mix ainda está marcado como **HERDADO**, o console projeta a população a partir de `Device`:

```text
Device=mobile   -> mobile=100,desktop=0,tablet=0
Device=desktop  -> mobile=0,desktop=100,tablet=0
Device=both     -> mobile=60,desktop=40,tablet=0
```

Essa projeção é configuração de maior precedência da próxima auditoria; não modifica `rasai-defaults.ini` e não redefine o contrato técnico da CLI.

Enquanto herdado:

- mudar `Device` recalcula o mix;
- editar amostras, thresholds ou outros parâmetros não cria override de mix;
- o mix não é materializado no INI apenas para repetir a herança;
- alterar explicitamente o próprio mix transforma-o em configuração personalizada;
- Tablet permanece disponível somente como override avançado da população Experience, não como `Device` do core.

As 20 amostras da baseline de sistema continuam sendo uma configuração de baixa carga. O runtime pode classificar grupos pequenos conforme sua metodologia vigente. Para comparações mais representativas, use volume coerente com o objetivo de medição e com a política de carga autorizada.

A referência Dynatrace permanece metodológica e não significa equivalência de fornecedor. Consulte [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md).

## Restaurar padrões do RASAi

O acesso atual é:

```text
INÍCIO > Sistema / restaurar padrões
```

Há duas modalidades apresentadas pela superfície de sistema:

1. restaurar configurações e preservar credenciais;
2. restaurar configurações e remover credenciais gerenciadas da sessão e, no Windows, de `Windows/User`.

Em ambas as modalidades, overrides não secretos conhecidos do RASAi podem ser removidos/recompostos para que a baseline volte a ser efetiva. Apenas regravar o INI não seria suficiente quando uma camada de maior precedência permanece ativa.

`Windows/Machine` nunca é removido automaticamente. Se houver override nesse escopo, o console informa a origem e o valor pode voltar a prevalecer em novo processo conforme a precedência do sistema operacional.

`RASAI_CONSOLE_INI` e `RASAI_CONFIG` são localizadores/bootstrap e seguem as regras específicas do contrato de restauração.

Depois da confirmação destrutiva exigida pela tela, o console:

1. limpa os overrides aplicáveis nos escopos permitidos;
2. carrega a baseline da versão instalada;
3. aplica os valores ao estado da sessão;
4. salva a configuração restaurada com o writer canônico quando aplicável;
5. mantém secrets fora do INI.

A restauração não apaga auditorias, `AUD-*/audit.db`, relatórios HTML, bancos do control plane ou arquivos do projeto.

## Distribuição e validação

`src/rasai/config/rasai-defaults.ini` faz parte do pacote distribuído e não depende do diretório do repositório existir ao lado do executável.

A versão/configuração da baseline é validada antes do uso. Testes de contrato verificam os valores esperados, precedência do `rasai-console.ini`, precedência de overrides explícitos e preservação/remoção opcional de credenciais.

Documentos relacionados:

- [CONFIGURATION.md](CONFIGURATION.md)
- [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md)
- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
- [SYNTHETIC_APDEX.md](SYNTHETIC_APDEX.md)
- [SYNTHETIC_USER_EXPERIENCE_APDEX.md](SYNTHETIC_USER_EXPERIENCE_APDEX.md)
