# Catálogo de auditoria e plano de execução do console

**Estado:** contrato vigente de desenvolvimento. O RASAi ainda não foi publicado.

Este documento define a taxonomia usada por `INÍCIO > PREPARAR AUDITORIA` e a estrutura estável que poderá ser projetada posteriormente nos relatórios HTML. A reformulação é **console-only**: não redefine scoring, collectors, fulfillment, routing de IA, retries, quarentena, metodologia, reprocessamento ou contratos do core.

## 1. Modelo mental

O operador escolhe **o resultado que deseja obter**. O console resolve as capacidades técnicas, parâmetros e dependências necessárias para esse resultado.

```text
CATÁLOGO
  -> capacidades/fontes
  -> parâmetros efetivos
  -> readiness
  -> uso de IA
  -> consumo/custo, quando aplicável
  -> execução
  -> evidências/resultados
```

Não existe Perfil da próxima auditoria na superfície pública. Se no futuro houver necessidade de conveniência para combinações recorrentes, o conceito adequado é **preset**: ele apenas preenche o catálogo e continua sujeito ao mesmo readiness/preflight.

## 2. Catálogos estáveis

Os IDs `CAT-*` são estáveis e independem da ordem visual ou do texto exibido.

| ID | Catálogo | Capacidades técnicas principais | IA |
|---|---|---|---|
| `CAT-01` | Fundamentos técnicos e descoberta | domínio/descoberta, métricas/padrões | nenhuma necessária |
| `CAT-02` | Acessibilidade | acessibilidade | não usa IA diretamente |
| `CAT-03` | Conteúdo, semântica e dados estruturados | conteúdo, JSON-LD, contexto editorial | opcional para contexto semântico/YMYL/E-E-A-T |
| `CAT-04` | Web Performance | PageSpeed/Lighthouse/CrUX conforme configuração | não usa IA diretamente |
| `CAT-05` | Search & AI Intelligence | SERP, GSC, visibilidade observada em IA, observabilidade aplicável | não usa IA principal para gerar visibilidade observada |
| `CAT-06` | Apdex de navegação | Synthetic Navigation Apdex | nenhuma para cálculo |
| `CAT-07` | Apdex de experiência | Synthetic User Experience Apdex | não usa IA no cálculo; depende de `CAT-06` |
| `CAT-08` | Análise profunda e melhorias | análise evidence-bound | **obrigatória** |
| `CAT-09` | Remediações | ações determinísticas e advisory | opcional; IA não altera scoring |

`Quality & decisão` permanece resultado sistêmico derivado, não catálogo selecionável.

A fonte canônica dessa taxonomia é `rasai.audit_catalog`.

## 3. Navegação

A tela de preparação apresenta primeiro o escopo e depois o catálogo.

```text
[ ESCOPO ]
1. Entrada
2. Projeto
3. Device
4. Idioma / mercado
5. Timezone

[ CATÁLOGO DA AUDITORIA ]
6.  [ ] CAT-01 Fundamentos técnicos e descoberta
7.  [ ] CAT-02 Acessibilidade
...
14. [ ] CAT-09 Remediações
```

Selecionar um catálogo:

1. inclui imediatamente o catálogo no plano da próxima execução;
2. abre imediatamente seu submenu;
3. mostra o readiness daquele catálogo;
4. expõe somente configurações próprias ou relacionadas ao seu contexto;
5. permite editar a variável pelo ID canônico;
6. volta para a grade mantendo a seleção.

Não existe etapa rígida `Avançar` entre escolha e configuração.

## 4. Submenu padrão

Todo catálogo segue a mesma anatomia:

```text
ESTADO
CAPACIDADES / FONTES
CONFIGURAÇÃO EFETIVA
USO DE IA
RESULTADO ESPERADO
CONFIGURAÇÕES RELACIONADAS
PERSISTÊNCIA
AÇÕES
```

A configuração relacionada continua tendo um único owner canônico. O catálogo referencia o owner; não cria uma segunda cópia da variável.

## 5. Readiness

Readiness é calculado somente para o que o operador selecionou.

| Estado | Significado |
|---|---|
| `APTO` | requisitos mínimos conhecidos do escopo selecionado estão satisfeitos |
| `APTO COM LIMITAÇÕES` | execução possível, mas enriquecimento/fonte opcional não estará disponível |
| `BLOQUEADO` | falta requisito obrigatório para o resultado selecionado |
| `NÃO SELECIONADO` | catálogo fora do plano da próxima execução |

Uma integração não selecionada não bloqueia o plano.

Exemplos:

- SERP com termos e provider apto: `CAT-05` pode ficar `APTO`;
- GSC opcional incompatível com a URL não transforma SERP apto em falha; pode gerar limitação;
- GSC explicitamente obrigatório e incompatível: `CAT-05` fica `BLOQUEADO`;
- `CAT-08` sem nenhum catálogo produtor de evidência: `BLOQUEADO`;
- `CAT-08` sem IA principal apta: `BLOQUEADO`;
- `CAT-07` inclui `CAT-06` como dependência técnica.

Readiness local não promete disponibilidade futura de um serviço externo. Timeout/rate limit/provider indisponível durante a execução continuam sendo fatos runtime.

## 6. Persistência

Parâmetros não sensíveis usam o contrato existente:

```text
1. manter somente nesta sessão
2. manter na sessão e salvar no arquivo de configuração
```

Secrets continuam fora do INI e usam a superfície Windows/User já existente.

A **seleção do catálogo** é parte do plano da execução, não um novo default persistente global. O snapshot secret-free da AUD grava:

```text
audit_catalog.version
audit_catalog.selected
audit_catalog.ai_enabled
audit_catalog.items
```

Isso permite reabrir uma configuração de AUD preservando o plano selecionado e cria a base para projeção equivalente em HTML posteriormente.

## 7. Inteligência Artificial

O catálogo registra uso de IA por operação como:

```text
NONE
OPTIONAL
REQUIRED
```

A configuração do provider/modelo continua centralizada na **IA principal** e utiliza o orquestrador já existente. Esta reformulação não cria providers especializados por catálogo nem altera AUTO, preços, quarentena, circuit breaker, fallback ou limite de tentativas.

Regras atuais:

- `CAT-03` pode usar a IA principal para análise semântica/contextual quando o operador escolher **Executar com IA**;
- `CAT-08` exige IA para entregar seu produto;
- `CAT-09` usa IA somente quando o operador escolher **Executar com IA** e o enriquecimento/remediação advisory correspondente estiver habilitado;
- `CAT-01`, `CAT-02`, `CAT-04`, `CAT-05`, `CAT-06` e `CAT-07` não ganham chamadas de IA só por serem selecionados;
- o uso de provider de IA durante a auditoria não cria, por si só, dados de visibilidade observada em IA;
- `CAT-06` e `CAT-07` não usam IA para os cálculos de Apdex;
- IA advisory nunca reescreve evidência nem scoring determinístico.

Quando apenas catálogos com IA opcional estão selecionados, o plano inicia em **Executar sem IA (recomendado)**. A opção **Executar com IA** só aparece quando a IA principal está configurada/apta. Se nenhum catálogo selecionado puder usar IA, uma configuração antiga de IA na sessão não ativa workload de IA para o plano.

Quando `CAT-08` está selecionado, IA é obrigatória e não existe opção válida de executar sem IA.

## 8. Custo e quota

A estimativa de consumo/custo continua sob os contratos canônicos já existentes.

Quando o plano selecionado usa IA ou outro recurso tarifado/limitado, a execução passa pelo preview/acknowledgement já instalado antes de iniciar o AUD. A estimativa usa a configuração efetiva naquele momento; AUTO continua sendo resolvido pelo orquestrador.

A tela do catálogo apenas informa a exposição. Ela não inventa preço nem duplica o cálculo financeiro.

## 9. Projeção de execução sem alterar o core

Algumas opções do console são session-first. Uma configuração antiga não deve voltar a participar silenciosamente depois que o operador a deixou fora do catálogo.

Imediatamente ao consultar readiness/custo/executar, a camada do console projeta temporariamente o plano selecionado sobre os campos opcionais conhecidos e restaura a sessão em seguida.

Exemplos de recursos opcionais mascarados quando o catálogo correspondente não foi selecionado:

- Web Performance;
- termos SERP, GSC e toggles de observabilidade de `CAT-05` (CrUX History, Clarity e Common Crawl);
- Synthetic Apdex;
- Experience Apdex;
- Análise profunda;
- remediação por IA;
- IA principal quando nenhum catálogo selecionado pode usá-la ou quando o operador escolheu executar sem IA;
- flags de remediação por IA quando a execução sem IA foi escolhida.

Collectors determinísticos basais não são desligados por essa camada, porque isso seria mudança de regra do core.

## 10. Search & AI Intelligence

`CAT-05` agrupa o resultado do usuário, mas preserva independência técnica:

```text
SERP
Google Search Console
Visibilidade em IA
Observabilidade externa aplicável
```

SERP e GSC não se tornam dependência um do outro. O readiness agregado considera a política efetiva de cada fonte.

## 11. Correspondência futura com HTML

A identidade visual não precisa ser uma cópia do console, mas a taxonomia deve ser a mesma:

```text
console antes da execução        HTML depois da execução
APTO                              CONCLUÍDO
APTO COM LIMITAÇÕES               PARCIAL / CONCLUÍDO COM LIMITAÇÕES
BLOQUEADO                         não executado por preflight
NÃO SELECIONADO                   NÃO SOLICITADO
```

O relatório deve conseguir informar, por `CAT-*`:

- o que foi solicitado;
- configuração efetiva;
- capacidades/fontes esperadas;
- o que executou;
- sucesso/parcial/falha/não disponível;
- IA utilizada e finalidade;
- evidências;
- remediações relacionadas.

A implementação HTML dessa projeção é escopo posterior. A taxonomia e o snapshot da AUD são mantidos agora para não exigir inferência retroativa depois.

## 12. SaaS

O catálogo implementado neste escopo é instalado apenas pelo `rasai-console`. Ele não altera endpoints, payloads, autenticação, regras ou runtime do SaaS.

A taxonomia neutra `rasai.audit_catalog` pode ser reutilizada futuramente pelo SaaS, mas isso exige uma mudança explícita de produto; não é ativado automaticamente por este escopo.

## 13. Testes Windows

A regressão do console deve rodar em `windows-latest`, incluindo:

- IDs estáveis `CAT-01..CAT-09`;
- seleção imediata e abertura do submenu;
- dependência `CAT-07 -> CAT-06`;
- bloqueio de `CAT-08` sem evidência/IA;
- projeção/restauração da sessão;
- ausência de `PERFIL DA PRÓXIMA AUDITORIA` e `ANÁLISES / RESULTADOS` na preparação pública;
- preservação do preview de custo canônico pelo fluxo de execução.
