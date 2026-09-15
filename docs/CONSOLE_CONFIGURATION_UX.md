# Contrato de UX para configuração no console

Este documento define a arquitetura de informação e o sistema de interação do `rasai-console`.

O runtime e os registries canônicos são a fonte de verdade. A interface organiza e explica essas capacidades; ela não redefine execução, scoring, providers, retries, quarentena, fulfillment ou metodologia.

## 1. Modelo mental

A navegação usa dois eixos complementares:

1. **objetivo/capacidade do usuário**, para preparar a auditoria e entender o resultado esperado;
2. **owner canônico da configuração**, para editar a variável uma única vez.

Uma capacidade pode depender de configurações pertencentes a vários serviços. A tela da capacidade referencia essas dependências e abre seus owners; ela não duplica variáveis.

Regra estrutural:

> Cada configuração possui um único owner canônico. Capacidades consumidoras apenas referenciam esse owner.

## 2. Primeiro nível

```text
1. Preparar auditoria
2. Auditorias / histórico
3. Relatórios consolidados
4. Inteligência Artificial
5. Integrações e serviços
6. Todas as configurações
7. Sistema / restaurar padrões
H. Ajuda
Q. Sair
```

`Inteligência Artificial` é uma macroárea transversal. `Integrações e serviços` concentra dependências externas. `Todas as configurações` é a visão técnica completa.

## 3. Preparar auditoria

A ordem da tela é:

```text
PERFIL DA PRÓXIMA AUDITORIA
ESCOPO
ANÁLISES / RESULTADOS
RESULTADOS SISTÊMICOS
EXECUÇÃO / ARMAZENAMENTO
AÇÕES
```

O perfil aparece antes dos ajustes porque funciona como preset/base. Alterações explícitas posteriores podem personalizar a próxima execução sem alterar o contrato do preset armazenado.

### 3.1 Convenção de seleção

```text
número curto = escolha contextual da tela
ID de 6 dígitos = identidade estável da configuração
letra = ação/navegação
- = linha informativa, automática ou derivada
```

Os números curtos ajudam a operar a tela. IDs estáveis permitem localizar a mesma configuração por caminhos diferentes.

### 3.2 IDs estáveis

Variáveis do catálogo recebem um ID numérico de 6 dígitos calculado a partir do nome canônico. O ID não depende de ordem alfabética, owner, filtro ou caminho de navegação.

Quatro dígitos foram descartados porque o espaço de 10 mil combinações aumenta demais o risco de colisão conforme o catálogo cresce. Seis dígitos reduzem o ruído visual em relação ao formato anterior de 8 dígitos sem transformar a identidade da variável em um índice sequencial dependente da ordem do catálogo.

Configurações-base do console usam IDs reservados, por exemplo:

```text
000001 Perfil
000002 Entrada
000003 Projeto
000004 Device
000005 Idioma / mercado
000006 Timezone
000007 Raiz de auditorias
000008 IA principal
000009 Web Performance
000010 Inputs Search
000011 Apdex navegação
000012 Apdex experiência
000013 Análise profunda
000014 Remediações
```

## 4. Device como autoridade

`Device` aceita somente:

```text
mobile
desktop
both
```

Os relatórios Mobile e Desktop são resultados derivados:

| Device | Mobile | Desktop |
|---|---|---|
| `mobile` | `INCLUÍDO` | `NÃO APLICÁVEL` |
| `desktop` | `NÃO APLICÁVEL` | `INCLUÍDO` |
| `both` | `INCLUÍDO` | `INCLUÍDO` |

Não existe seleção independente desses dois relatórios.

## 5. Apdex de experiência

O mix normal de Experience Apdex herda `Device`:

```text
mobile  -> mobile=100,desktop=0,tablet=0
desktop -> mobile=0,desktop=100,tablet=0
both    -> mobile=60,desktop=40,tablet=0
```

Esse valor é **derivado-customizável**:

- enquanto herdado, acompanha `Device`;
- alterar outros parâmetros do Apdex não quebra a herança;
- alterar o próprio mix cria um override;
- mix herdado não é materializado no INI como override;
- `tablet` permanece apenas como opção avançada da população de Experience Apdex.

## 6. Análises e resultados

A preparação expõe capacidades com estados calculados pelos contratos existentes. Exemplos:

```text
Domínio e descoberta          INCLUÍDO
Acessibilidade                INCLUÍDO
Web Performance               APTO / DESABILITADO / CONFIGURAR
Search Intelligence / SERP    APTO / NÃO SOLICITADO / DESABILITADO / CONFIGURAR
Google Search Console         APTO / NÃO CONFIGURADO / NÃO APLICÁVEL / DESABILITADO / CONFIGURAR
Conteúdo e JSON-LD            INCLUÍDO
Apdex de navegação            APTO / DESABILITADO / CONFIGURAR
Apdex de experiência          APTO / DESABILITADO / CONFIGURAR
Quality & decisão             DERIVADO
```

Uma capacidade automática não recebe checkbox apenas para reproduzir algo que o pipeline já gera. Uma capacidade opcional mostra readiness e permite abrir os parâmetros que efetivamente controla.

`Search Intelligence / SERP` e `Google Search Console` são capacidades independentes. SERP é dirigido por termos da execução e por `RASAI_SERP_*`; GSC possui autenticação, property e política próprias. GSC não deve aparecer como dependência da capacidade SERP nem SERP como dependência da capacidade GSC.

`Conteúdo e JSON-LD` é uma capacidade agregadora, mas seu estado visual é segmentado internamente: conteúdo/estrutura e orientação JSON-LD são determinísticos e `INCLUÍDOS`; contexto editorial pode estar `AUTOMÁTICO`, `PERSONALIZADO` ou `CONFIGURAR`; remediação por IA pode estar `NÃO SOLICITADA`, `APTO` ou `CONFIGURAR`.

## 7. Tela de capacidade

A estrutura geral é:

```text
ESTADO
INFORMAÇÃO
CONFIGURAÇÃO DA ANÁLISE         # quando existe handler próprio
DEPENDÊNCIAS / CONFIGURAÇÕES RELACIONADAS
AÇÕES
```

Somente configurações consumidas por aquela capacidade devem aparecer. O usuário pode selecionar o ID relacionado e editar a variável no owner canônico.

`H. Ajuda de contexto` é ajuda operacional, não prefixo para informar um ID. A ajuda deve mostrar objetivo, estado/interpretação, forma de operar e, para as configurações relacionadas, finalidade, condição de necessidade e impacto. Dentro da própria ajuda o usuário pode informar diretamente um ID exibido para abrir o editor correspondente; `ENTER` ou `V` retorna sem erro. Um ID digitado em um prompt de retorno nunca deve ser consumido silenciosamente.

Capacidades que misturam subdomínios funcionais podem agrupar as configurações relacionadas sem criar novos owners. Em `Conteúdo e JSON-LD`, por exemplo, o console separa visualmente **Contexto editorial** de **Enriquecimento por IA**; `RASAI_AI_ANALYSIS_LANGUAGE` permanece uma configuração compartilhada/global de IA, apenas referenciada pela capacidade consumidora.

## 8. Catálogo de configurações

As visualizações disponíveis são:

```text
Por owner funcional
Ordem alfabética
Por estado
Somente modificadas
Somente pendentes
Localizar por ID/nome/finalidade
```

Os owners representam responsabilidade funcional, não fabricante como eixo obrigatório. Exemplos:

```text
Inteligência Artificial / provider
Search / Google Search Console
Search / SERP
Web / PageSpeed-Lighthouse
Web / CrUX
Synthetic Apdex / Navigation
Synthetic Apdex / User Experience
Identity / OIDC
Plataforma / Control plane
```

Fornecedor pode aparecer no nome do recurso, mas não deve fragmentar a arquitetura de informação.

## 9. Tela de variável

Todo editor canônico segue quatro blocos:

### INFORMAÇÃO

- para que serve;
- owner;
- contexto;
- quando é necessária;
- impacto de custo, quota, carga ou segurança;
- observações.

### ESTADO ATUAL

- valor ou indicação redigida;
- origem;
- estado de decisão/readiness.

### DOMÍNIO / INPUT

- tipo;
- valores aceitos;
- default;
- exemplo/referência/documentação quando disponível.

Quando o domínio é fechado, `S. Definir / alterar` não abre entrada livre. O console lista as opções técnicas aceitas, acrescenta uma explicação curta em PT-BR quando o valor pode não ser autoexplicativo e exige confirmação da seleção antes de aplicá-la.

Listas fechadas permitem selecionar um ou mais valores pelo número ou pelo identificador técnico. O texto técnico continua visível porque ele corresponde ao contrato real gravado/configurado.

Metadados de apresentação devem refletir o contrato real do runtime. Um toggle booleano, como `RASAI_GSC_ENABLED`, deve aparecer como `booleano` com domínio `true, false`; validação runtime e UI não podem divergir a ponto de a interface oferecer texto livre para um valor fechado.

### AÇÕES

- definir/alterar;
- limpar override da sessão;
- restaurar default/ausência canônica;
- gerenciar Windows/User para secrets;
- abrir documentação;
- voltar.

## 10. Configurações fechadas e abertas

Nenhuma configuração com domínio fechado deve depender de texto livre.

Ordem preferencial:

1. booleano guiado;
2. enum guiado;
3. lista fechada;
4. provider/model/reasoning derivados do registry;
5. valor dependente recalculado a partir da seleção vigente;
6. texto livre apenas quando o domínio realmente é aberto.

A UI preserva o valor técnico (`health-safety`, `financial-security`, `auto`, nomes de modelos etc.) e pode apresentar uma descrição curta em tom visual secundário. Valores triviais como `true/false` ou `mobile/desktop` podem permanecer com explicação mínima.

Valores abertos incluem URL, path, property, locale, identificador externo, secret e números de faixa contínua.

## 11. Estado, cor e símbolo

Cor é reforço, nunca informação exclusiva.

| Estado | Semântica visual |
|---|---|
| `APTO`, `INCLUÍDO`, `CONCLUÍDO`, `HABILITADO` | sucesso/disponível |
| `CONFIGURAR`, `PARCIAL`, `APTO COM LIMITAÇÕES`, `NÃO CONFIGURADO` | atenção |
| `ERRO`, `INDISPONÍVEL`, `BLOQUEADO` | impedimento |
| `AUTOMÁTICO`, `HERDADO`, `DERIVADO`, `PERSONALIZADO` | composição/origem |
| `DESABILITADO`, `NÃO APLICÁVEL`, `NÃO SOLICITADO`, `PADRÃO` | neutro/inativo |

`CONFIGURAR` significa que uma dependência conhecida exige ação; não é sinônimo de falha do website. `NÃO SOLICITADO` significa que a capacidade pode estar configurada, mas não foi pedida para a próxima execução. `NÃO CONFIGURADO` significa ausência de configuração suficiente para uma capacidade opcional/automática, sem transformá-la automaticamente em falha do AUD.

## 12. Origem

A UI pode indicar:

```text
SESSÃO
ARQUIVO
WINDOWS/USER
WINDOWS/MACHINE
DEFAULT
NÃO CONFIGURADO
```

A origem deve ser mostrada especialmente quando um valor efetivo pode surpreender o operador por precedência.

## 13. Persistência e destino da alteração

Após uma edição não sensível, o console oferece:

```text
1. Aplicar somente nesta sessão
2. Aplicar na sessão e salvar no arquivo de configuração
```

Secrets usam destino próprio e nunca entram no INI.

O comando geral `Salvar configuração` persiste o estado não sensível da próxima auditoria, incluindo inputs Search configurados na sessão.

## 14. Search Intelligence / SERP e Google Search Console

A UI separa **Search Intelligence / SERP** de **Google Search Console**.

Search Intelligence / SERP separa:

- **inputs da próxima execução**: termos, depth, região, device e análise competitiva;
- **governança/provider**: `RASAI_SERP_*` e registry SERP;
- **credencial**: variável secreta do provider;
- **IA principal**: usada somente quando alguma extensão compatível realmente exige IA.

Os inputs Search são session-first. A persistência no INI ocorre somente por ação explícita de salvar configuração.

Sem termos, uma configuração SERP válida aparece como `NÃO SOLICITADO`; `RASAI_SERP_MODE=disabled` aparece como `DESABILITADO`. Com termos, o console usa os validadores canônicos para decidir `APTO` ou `CONFIGURAR`.

Google Search Console possui superfície própria porque autenticação OAuth, property e cobertura da URL são requisitos distintos de SERP. Em modo automático/opcional sem OAuth/property suficiente, a UI usa `NÃO CONFIGURADO`; quando a property não cobre a URL em modo automático, usa `NÃO APLICÁVEL`; em modo obrigatório uma incompatibilidade previsível usa `CONFIGURAR`; hard-off usa `DESABILITADO`.

## 14.1 Conteúdo e JSON-LD

`Conteúdo e JSON-LD` permanece uma única capacidade de primeiro nível, com segmentação interna:

```text
Conteúdo / estrutura   INCLUÍDO
JSON-LD                INCLUÍDO
Contexto editorial     AUTOMÁTICO / PERSONALIZADO / CONFIGURAR
Remediação por IA      NÃO SOLICITADA / APTO / CONFIGURAR
```

A orientação JSON-LD determinística permanece disponível independentemente da remediação textual por IA. Valores editoriais `auto` são configurações válidas e não devem ser apresentados como pendência.

As configurações relacionadas são agrupadas em **Contexto editorial** (`RASAI_CONTENT_*`, `RASAI_YMYL_CATEGORY`, `RASAI_PAGE_PURPOSE`, `RASAI_INTENDED_AUDIENCE`, `RASAI_EXPERIENCE_REQUIREMENT`, `RASAI_FRESHNESS_SENSITIVITY`) e **Enriquecimento por IA** (`RASAI_AI_CONTENT_REMEDIATION` e `RASAI_AI_ANALYSIS_LANGUAGE`). O agrupamento é visual; owners canônicos e runtime não são alterados.

## 15. Inteligência Artificial

Existe uma seleção principal de IA por execução. O console não cria providers especializados por módulo.

`AUTO` reutiliza o runtime central para:

- elegibilidade;
- custo estimado;
- disponibilidade;
- quarentena;
- circuit breaker;
- fallback e limite de tentativas.

Provider, modelo e reasoning são derivados do registry. A configuração de uma capacidade consumidora referencia essa seleção principal.

## 16. Perfis

Perfis são presets da próxima auditoria, não uma fonte persistente paralela.

A precedência efetiva é:

```text
ajuste explícito posterior ao perfil
> overlay do perfil
> configuração normal de sessão / INI / SO
> default canônico
```

A camada vencedora não sobrescreve persistentemente as inferiores. Perfil `CONFIGURAR` fica visível para orientação, mas não é aplicado até resolver as dependências obrigatórias.

## 17. Secrets

Regras obrigatórias:

- nunca mostrar conteúdo real após a entrada;
- nunca gravar secret em `rasai-console.ini`;
- nunca copiar secret de snapshot de AUD;
- Windows/User exige ação explícita;
- Windows/Machine é somente observado;
- cancelamento ocorre antes de substituir o valor vigente sempre que a edição usa fluxo staged.

## 18. Restauração

Restauração por variável devolve o valor ao default/ausência canônica e aplica o mesmo mecanismo de configuração usado pelo restante do console.

A restauração integral da baseline do produto pertence a:

```text
INÍCIO > Sistema / restaurar padrões
```

Ela não é uma ação da preparação da auditoria.

## 19. Auditorias / histórico

A listagem histórica usa colunas explícitas, com `AUDITORIA`, `CONCLUSÃO LOCAL`, `SITUAÇÃO` e `REPROCESSAMENTO`. O timestamp de conclusão é apresentado no timezone configurado para apresentação e só aparece quando a auditoria atingiu conclusão efetiva.

Estados técnicos do fulfillment continuam persistidos no contrato interno, mas a UI usa textos amigáveis em PT-BR. Exemplos:

```text
COMPLETE            -> Concluída
PARTIAL_RETRYABLE   -> Parcial - pode reprocessar
PARTIAL_BLOCKED     -> Parcial - há bloqueios
FAILED_FATAL        -> Falha definitiva
EXPIRED_FOR_COMPLETION -> Expirada para conclusão
```

`report_status` não é repetido na listagem quando apenas duplica a semântica operacional de `processing_status`.

Uma auditoria `COMPLETE` não oferece reprocessamento: o objetivo já foi atingido e os itens requeridos já estão satisfeitos. O reprocessamento permanece disponível para estados em que existem pendências recuperáveis.

Ao escolher `I. Informar Audit ID`, o prompt aceita `V` para cancelar e retornar à listagem sem registrar crítica de AUD inválido. O cancelamento é navegação normal, não falha de validação.

`GERENCIAR AUDITORIAS / EXCLUSÃO SEGURA` segue a mesma linguagem tabular do histórico, acrescentando seleção, tamanho e domínio. As larguras consideram o tamanho real de `AUD-*` para evitar desalinhamento dos cabeçalhos.

## 20. Critério de aderência

Uma superfície de configuração é aderente quando:

- usa o owner canônico da variável;
- oferece ajuda e impacto antes da edição;
- guia domínios fechados;
- explica opções técnicas não autoexplicativas sem ocultar o valor canônico;
- mostra estado e origem;
- distingue automático, derivado, herdado, personalizado, não solicitado e não configurado;
- não duplica provider/configuração em módulos consumidores;
- preserva secrets;
- usa readiness real existente;
- retorna ao contexto de navegação de origem;
- não cria comportamento funcional fora do runtime.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md), [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md), [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).