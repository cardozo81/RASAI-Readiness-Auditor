# Perfis de Execução do console

## Objetivo

Os **Perfis de Execução** simplificam a configuração de uma auditoria sem criar uma segunda fonte de verdade para o RASAi.

O perfil é uma camada temporária sobre a configuração normal:

```text
defaults canônicos do RASAi
        +
configuração normal da sessão/INI/SO
        +
perfil selecionado para a próxima execução
        +
ajustes finos feitos depois da seleção
        =
configuração efetiva da execução
```

O perfil existe somente em memória. Ele **não**:

- grava valores no `rasai-console.ini`;
- altera defaults do runtime;
- cria ou apaga variáveis em Windows/User;
- modifica Windows/Machine;
- grava credenciais;
- inventa termos SERP;
- inventa contexto YMYL/editorial;
- inventa parâmetros Synthetic Apdex;
- habilita silenciosamente Improvement Intelligence.

## Escopo inicial deliberado: URL única

Perfis ficam disponíveis somente quando o item **1. Entrada** possui uma URL única explícita.

Se a entrada estiver em modo TXT/arquivo ou ainda não houver URL informada, o menu mostra o perfil como `INDISPONÍVEL`.

Se o operador trocar de URL para arquivo enquanto um perfil estiver ativo, o perfil é removido da sessão para impedir que um overlay pensado para uma URL seja aplicado a múltiplos targets.

Essa restrição simplifica e torna determinísticas dependências de Search Intelligence, contexto editorial e Improvement Intelligence.

## Acesso

No menu principal:

```text
F. Perfil da execução
```

Sem perfil:

```text
F. Perfil da execução : NENHUM | disponível para URL única | sessão apenas
```

Com perfil ativo:

```text
F. Perfil da execução : APTO|CONFIGURAR | <perfil> | SEM IA|IA SE DISPONÍVEL | SESSÃO
```

O bloco mostra ainda módulos, exposição estimada, dependências faltantes e ajustes finos feitos depois da seleção.

## Perfis prontos

### SEO / Search Readiness

Envolve:

- core determinístico de search readiness;
- Lighthouse SEO;
- Lighthouse Best Practices;
- serviços/integradores já configurados, como GSC, continuam obedecendo seus próprios contratos.

Custo/exposição:

- pode gerar chamadas PageSpeed/Lighthouse e CrUX conforme configuração/credenciais;
- IA é opcional e independente;
- GSC exige OAuth/property quando estiver configurado e apto.

### GEO / AI Readiness

Envolve:

- sinais de consumo por agentes/IA;
- Lighthouse SEO;
- Lighthouse Best Practices;
- categoria `agentic-browsing`;
- contexto semântico já disponível no audit.

Custo/exposição:

- pode gerar chamadas PageSpeed/Lighthouse;
- IA padrão é opcional e pode gerar tokens/custo de provider.

Dependência editorial:

- `RASAI_CONTENT_RISK_PROFILE`, `RASAI_YMYL_CATEGORY` e demais campos de contexto continuam sob controle explícito do operador;
- quando permanecem `AUTO`, o preset não transforma a inferência em fato;
- um contexto YMYL explícito já existente é preservado.

### Performance

Envolve:

- Lighthouse Performance;
- Lighthouse Best Practices;
- field data segundo a configuração Web Performance vigente.

Custo/exposição:

- pode consumir quota PageSpeed/CrUX;
- o RASAi não inventa cobrança monetária quando o provider só expõe quota.

### Acessibilidade

Envolve:

- Lighthouse Accessibility;
- Lighthouse Best Practices;
- demais evidências determinísticas do audit continuam disponíveis.

Custo/exposição:

- pode gerar chamadas PageSpeed/Lighthouse;
- IA não é obrigatória.

### Web Quality

Envolve:

- Lighthouse Best Practices;
- Lighthouse SEO;
- Lighthouse Accessibility;
- integrações de standards/observability já habilitadas continuam com seus contratos próprios.

Custo/exposição:

- pode gerar chamadas PageSpeed/Lighthouse;
- W3C/MDN ou outros serviços já habilitados podem continuar realizando chamadas externas conforme configuração normal.

### SEO + GEO

Combina os módulos SEO e GEO na mesma execução.

### SEO + GEO + Performance

Combina search readiness, AI readiness e performance.

### Search Intelligence / SERP

O perfil **não cria termos**.

Para ficar `APTO`, exige:

- termos informados no item `T` da sessão;
- provider SERP válido;
- credencial quando `RASAI_SERP_MODE=live`;
- limites de queries/depth/requests válidos.

Custo/exposição:

- requests/quota do provider SERP dependem dos termos, profundidade e paginação;
- a tela informa quantos termos existem no momento da seleção.

Se o perfil foi escolhido sem termos, ele pode permanecer selecionado, mas `R. Executar` fica bloqueado como `CONFIGURAR` até o operador preencher a dependência.

### Experiência sintética

O perfil **não cria threshold, amostras, tentativas, concorrência ou carga**.

Exige Synthetic Navigation Apdex e/ou Synthetic User Experience Apdex previamente configurado.

Custo/exposição:

- sem API paga própria;
- usa Chromium/CPU/tempo local;
- gera tráfego HTTP real contra a URL;
- a carga projetada usa a configuração existente e é mostrada antes da execução.

### Análise profunda URL

O perfil integra a capacidade Improvement Intelligence somente quando o item **13. Análise profunda URL** já estiver habilitado e válido.

O perfil não define provider/model/reasoning dessa capacidade.

Custo/exposição:

- gera chamadas adicionais de IA;
- o provider/model/reasoning são independentes da IA padrão do perfil;
- permanece evidence-bound, advisory/non-scoring e com segurança passiva.

### Completo seguro

Combina:

- SEO;
- GEO;
- Performance;
- Acessibilidade;
- Web Quality.

Deliberadamente **não ativa automaticamente**:

- Search Intelligence/SERP;
- Synthetic Apdex;
- Improvement Intelligence.

Esses três grupos têm dependências, carga ou custo adicional que justificam opt-in explícito.

## Perfil personalizado

`C. Compor perfil personalizado` abre uma lista guiada de módulos.

Cada módulo mostra:

- finalidade;
- custo/exposição;
- dependências obrigatórias.

O operador marca/desmarca módulos e aplica a combinação desejada. Não há necessidade de criar presets permanentes para todas as combinações possíveis.

## IA padrão do perfil

Depois de selecionar um perfil, o console oferece:

```text
1. Não usar IA padrão nesta execução
2. Usar IA padrão se houver provider APTO
```

### Não usar IA

Durante a execução efetiva do perfil, `ai_provider` é projetado como `none` e remediações IA não são executadas, sem alterar a configuração persistida do usuário.

### Usar se disponível

A regra é:

1. se o provider já selecionado pelo usuário estiver `APTO`, preservá-lo;
2. caso contrário, usar `AI=auto` somente se existir provider elegível/APTO;
3. se nenhum provider estiver apto, seguir sem IA padrão.

Esse modo **não bloqueia** o core quando não existe IA disponível.

Credenciais nunca são criadas, trocadas ou persistidas pelo perfil.

Improvement Intelligence possui IA própria e continua independente.

## Dependências e estado `CONFIGURAR`

Uma capacidade explicitamente selecionada pelo perfil não deve ser silenciosamente omitida quando depende de dado operacional obrigatório.

Casos atuais:

| Módulo | Dependência | Comportamento |
|---|---|---|
| Search Intelligence | termos SERP/provider/credencial | bloqueia execução até preencher |
| Experiência sintética | Apdex configurado | bloqueia execução até preencher |
| Análise profunda | item 13 configurado | bloqueia execução até preencher |
| GEO | contexto YMYL/editorial | `AUTO` é permitido e informado; não inventa valores |
| IA padrão `se disponível` | provider apto | fallback seguro para sem IA |

A validação específica do runtime continua sendo executada depois dessas dependências do perfil. O perfil não substitui preflight existente.

## Ajuste fino

Depois de escolher um perfil, as opções normais continuam disponíveis.

Ajustes explícitos feitos depois da seleção vencem o preset nos domínios correspondentes, por exemplo:

- item `4` → IA;
- item `5` → remediações;
- item `6` → Web Performance;
- item `11` → experiência sintética;
- item `13` → análise profunda;
- item `T` → Search Intelligence.

Alterações avançadas de Web Performance/Lighthouse feitas pelo catálogo de variáveis também são respeitadas quando diferem da configuração-base capturada no momento da seleção.

O resumo do perfil indica quando existem ajustes finos.

## Precedência

Durante uma execução com perfil:

```text
ajuste manual posterior à seleção
> overlay do perfil
> configuração normal carregada na sessão
> default canônico do RASAi
```

Essa precedência existe **somente para a execução**.

## Persistência e botão Salvar

Selecionar/remover um perfil não marca o INI como alterado porque o perfil não modifica o estado persistível.

Se o usuário fizer um ajuste manual real em opções normais do console, esse ajuste continua obedecendo a semântica já existente do botão `S. Salvar configuração INI`.

Portanto:

- o preset nunca é salvo;
- um ajuste manual pode ser salvo somente porque o usuário alterou a configuração normal e escolheu explicitamente `S`.

## Custos

Cada perfil pronto e cada módulo do compositor apresenta uma descrição de custo antes da aplicação.

Depois da seleção, o detalhe do perfil usa a projeção canônica de consumo do console para mostrar, quando aplicável:

- nível de exposição;
- intervalo potencial de chamadas Web Performance;
- intervalo potencial de tentativas de IA;
- pricing unitário catalogado quando disponível;
- carga Synthetic Apdex já configurada;
- quantidade de termos SERP já presente;
- aviso de chamadas adicionais da análise profunda.

O RASAi não inventa quantidade de tokens antes da execução e não converte quota em preço quando o provider não fornece base suficiente.

## Segurança metodológica

Perfis selecionam **o que executar**, não alteram a metodologia.

Não modificam:

- `SARI-001`;
- `SCORE-GEO-004`;
- pesos de scoring;
- regras históricas;
- thresholds metodológicos sem ação explícita do operador.

A ausência/presença de evidência continua obedecendo ao contrato normal de cobertura/confiabilidade.
