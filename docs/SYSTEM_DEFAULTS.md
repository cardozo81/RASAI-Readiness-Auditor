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

Uma configuração explícita de maior precedência governa cada domínio do baseline de forma independente. `RASAI_SYNTHETIC_APDEX=false` desabilita somente Navigation Apdex; `RASAI_APDEX_EXPERIENCE=true` pode manter Experience habilitado na mesma execução. A seleção CAT-* continua sendo a autoridade para projetar os dois flags no processo filho.

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

Synthetic Navigation Apdex e Synthetic User Experience Apdex possuem **targets independentes** e herdam o mesmo device único da AUD.

### Navigation Apdex

Baseline canônica para novas populações:

- habilitado: `true` na baseline empacotada do console;
- threshold `T`: `3 s`;
- amostras válidas por URL/device: **`150`**;
- máximo de tentativas por contexto: **`188`** (`ceil(1.25 × 150)`);
- máximo de páginas: `1`;
- concorrência: `1`;
- delay: `1 s`.

`T=3 s` é uma baseline operacional RASAi, não um SLO universal. Quando a organização conhece seu SLO/Task target real, o valor configurado deve prevalecer.

### Experience Apdex

Baseline canônica para novas populações:

- habilitado: `true` na baseline empacotada do console;
- amostras válidas por página: **`100`**;
- máximo de tentativas por página: **`125`** (`ceil(1.25 × 100)`);
- máximo de páginas: `1`;
- device: **herdado integralmente da AUD**;
- sessão: `cold`;
- KPM executável: `USER_ACTION_DURATION`;
- Satisfied: `3 s`;
- Frustrated: `12 s`;
- erros qualificáveis afetam Apdex: `true`;
- erros JavaScript afetam Apdex: `true`;
- erros de requisição/HTTP/CSP afetam Apdex: `true`;
- `console.error` afeta Apdex: `false`;
- captura de erros JavaScript/XMLHttpRequest/Fetch: habilitada conforme o contrato vigente;
- captura de `console.error`: `false`;
- máximo de erros detalhados: `10`;
- escopo de erros de requisição: `all`;
- concorrência: `1`.

Para novas AUDs, `Device=mobile` implica 100% MOBILE e `Device=desktop` implica 100% DESKTOP. **Não existe device mix público e Tablet não é uma opção operacional.** O campo técnico legado de mix permanece somente para compatibilidade interna com dados históricos.

### Ciclo de vida canônico

A configuração efetiva é congelada na população que a criou:

- processamento inicial persiste target, budget, device e perfis efetivos;
- RPR/reprocessamento recupera exatamente esse contrato persistido e não adota silenciosamente defaults de uma versão posterior;
- ao acrescentar CAT-06 ou CAT-07 a uma AUD, o novo catálogo parte dos defaults atuais/configuração explícita do complemento e congela sua própria população;
- uma AUD histórica multi-device pode continuar sendo lida/reprocessada, mas não autoriza inventar um device para uma nova população CAT-06/CAT-07.

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


## Registry canônico de configuração

A superfície configurável do console é inventariada em tempo de execução a partir dos
`EnvironmentSpec` efetivamente instalados e do mesmo mapa de capacidades usado pelos
catálogos. O registry classifica, para cada chave, sensibilidade, persistência, default e
ownership por `CAT-*`; não existe uma segunda lista manual por catálogo.

Os nove perfis físicos sintéticos `RASAI_APDEX_*_{CLIENT|HARDWARE|NETWORK}_PROFILE`
fazem parte da baseline empacotada e do contrato Save -> Reload -> Restore. Eles são
configuração compartilhada entre CAT-06 e CAT-07, portanto não pertencem exclusivamente
a nenhum dos dois catálogos.


## Restaurar padrões de um único catálogo

A tela de cada CAT-* oferece restauração local somente quando existem configurações
exclusivas não secretas. O escopo é calculado pelo registry canônico, não por uma lista
manual. Overrides exclusivos são removidos da sessão e de Windows/User quando aplicável,
a baseline empacotada volta a prevalecer e o resultado é persistido pelo writer normal.

Configurações compartilhadas são preservadas. Em especial, os nove perfis físicos
sintéticos continuam intactos ao restaurar CAT-06 ou CAT-07; uma restauração exclusiva de
um desses catálogos não pode alterar silenciosamente a medição futura do outro.
`Windows/Machine`, secrets e snapshots já congelados em AUD/RPR nunca são modificados.
