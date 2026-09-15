# Isolamento entre configuração e contexto de execução

## Objetivo

O RASAi trata configuração do operador e configuração efetiva de uma execução como responsabilidades distintas. Um perfil, um AUD carregado para reutilização ou qualquer outro overlay transitório não possui autorização para regravar silenciosamente a configuração canônica do usuário.

A regra vale para o console local e deve ser preservada por superfícies equivalentes do produto.

## Contextos

Existem três contextos independentes:

| Contexto | Responsabilidade | Quem pode alterar |
|---|---|---|
| configuração persistida | INI, Windows/User, Windows/Machine e secrets persistidos | ação explícita do operador ou operação administrativa explícita |
| sessão canônica do console | valores atuais apresentados/editados pelo console | ação explícita do operador, carga normal dos valores persistidos e defaults canônicos |
| overlay da execução | perfil, política específica do AUD e fallbacks recuperados para uma nova execução | composição interna do runtime; duração limitada à execução |

A precedência usada para calcular uma execução não representa permissão de escrita sobre a camada inferior.

```text
ajuste explícito do operador
> overlay da execução
> configuração canônica da sessão/persistida
> default canônico
```

Essa precedência resolve **qual valor a execução usa**. Ela não autoriza o overlay a alterar o valor que a tela de configuração apresenta nem a persistência da máquina.

## Perfis de execução

Os campos normais do perfil são projetados sobre o estado da execução e restaurados ao término do contexto. Isso inclui, entre outros:

- Web Performance;
- categorias Lighthouse;
- provider/model/reasoning principal de IA;
- remediação de conteúdo/técnica;
- Synthetic Apdex e Experience Apdex;
- termos Search Intelligence quando o perfil os suprime;
- habilitação de Análise profunda.

O perfil não deve transformar esses valores em uma segunda configuração persistida.

## Integrações dependentes de variáveis de ambiente

Quando uma integração lê `RASAI_*`, o console não deve modificar `os.environ` do processo pai apenas para satisfazer um perfil. Antes de iniciar o processo da auditoria, o RASAi cria uma cópia privada do ambiente e projeta nela os overrides da execução.

Exemplo:

```text
sessão canônica:
RASAI_GSC_ENABLED=true

perfil:
GSC=disabled

ambiente privado do AUD:
RASAI_EXECUTION_GSC_POLICY=disabled
RASAI_GSC_ENABLED=false
```

Durante e depois do AUD, a sessão canônica continua:

```text
RASAI_GSC_ENABLED=true
```

Assim, voltar à tela de variáveis, fazer preview de custo/readiness, executar, finalizar o relatório ou remover o perfil não pode restaurar um valor antigo sobre uma alteração explícita do operador.

## GSC

A política GSC do perfil é estado da execução. Ela pode ser:

- usar se compatível;
- exigir;
- desabilitar;
- herdar global.

Somente o subprocesso do AUD recebe a projeção correspondente. Com `GSC=disabled`, o critério de aceite é físico: nenhuma operação Sitemaps, URL Inspection, Search Analytics ou renovação OAuth GSC deve ocorrer naquela execução.

## Configuração recuperada de AUD anterior

Carregar um AUD para reutilizar sua configuração também não concede permissão para alterar a sessão canônica.

Valores históricos reconstruídos a partir das observações persistidas são **fallbacks da nova execução**. Em especial, provider e modo SERP reconstruídos não são promovidos silenciosamente a `RASAI_SERP_PROVIDER` ou `RASAI_SERP_MODE` no processo pai.

Se o operador configurar posteriormente provider ou modo SERP, a ação explícita do operador vence o fallback histórico.

## Variáveis revisadas

A revisão dos Perfis de Execução não encontrou o mesmo vazamento de ambiente nos demais campos normais de perfil: eles permanecem state-scoped e são restaurados após o contexto.

Foi identificado um caso da mesma família fora do mecanismo de perfil: a recuperação de Search Intelligence de um AUD antigo podia colocar `RASAI_SERP_PROVIDER` e `RASAI_SERP_MODE` diretamente no ambiente do console. Esse comportamento também foi isolado como fallback de execução.

Outros usos temporários de ambiente existentes no runtime - por exemplo, overrides de worker, supressão temporária de experiência, toggles transitórios de análise e proteções de observabilidade - continuam obrigados a salvar/restaurar o valor anterior e não constituem configuração persistente.

## Invariantes

1. Selecionar um perfil não altera configuração persistida nem canônica.
2. Executar um perfil não altera configuração persistida nem canônica.
3. Remover um perfil não restaura valores antigos sobre alterações explícitas do usuário.
4. Preview/readiness/custo não deixa efeitos colaterais em variáveis canônicas.
5. Um AUD carregado pode fornecer fallback para a nova execução, mas não pode promover dados históricos a configuração global sem ação do operador.
6. O subprocesso recebe uma cópia privada do ambiente; o processo pai permanece a fonte canônica visível ao usuário.
7. Falhas externas reais não são mascaradas pelo isolamento. HTTP 5xx, timeout, rate limit, autenticação e demais falhas técnicas continuam seguindo seus contratos próprios.

## Teste de aceitação GSC

Cenário mínimo:

```text
RASAI_GSC_ENABLED=true
Perfil 12 - Completo máximo
GSC do perfil = Não usar GSC nesta execução
```

Resultados esperados:

- a tela de variáveis continua mostrando `RASAI_GSC_ENABLED=true` antes, durante a preparação e depois do AUD;
- o processo do AUD recebe GSC efetivamente desabilitado;
- não ocorre nenhuma chamada GSC/OAuth;
- GSC não cria requisito pendente para esse AUD;
- remover o perfil mantém `RASAI_GSC_ENABLED=true`.
