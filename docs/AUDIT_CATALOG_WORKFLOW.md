# Catálogo de auditoria e plano de execução do console

**Estado:** contrato vigente de desenvolvimento/pré-produção. O RASAi ainda não foi publicado.

Este documento define a taxonomia usada por `INÍCIO > PREPARAR AUDITORIA`, a persistência do plano da próxima execução e sua projeção posterior nos relatórios HTML. A composição é **console-first** e não redefine scoring, collectors, fulfillment, routing de IA, retries, quarentena, metodologia, reprocessamento ou contratos do core.

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
  -> projeção HTML
```

Não existe Perfil da próxima auditoria na superfície pública. A unidade pública de composição é o catálogo `CAT-*`.

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
| `CAT-10` | Segurança passiva | HTTP/browser/runtime, cookies, recursos, third-party e vulnerability intelligence sem exploração | opcional para interpretação/remediação; fatos técnicos permanecem determinísticos |

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
15. [ ] CAT-10 Segurança passiva

[ EXECUÇÃO / ARMAZENAMENTO ]
16. Raiz das auditorias
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
- `CAT-07` inclui `CAT-06` como dependência técnica;
- `CAT-10` é executável sem IA; OSV/KEV são enriquecimentos externos fail-open e sua indisponibilidade reduz cobertura sem virar falha do alvo.

Readiness local não promete disponibilidade futura de um serviço externo. Timeout/rate limit/provider indisponível durante a execução continuam sendo fatos runtime.

## 6. Persistência do plano

Parâmetros não sensíveis usam o contrato:

```text
1. manter somente nesta sessão
2. manter na sessão e salvar no arquivo de configuração
```

Secrets continuam fora do INI e usam a superfície de credenciais suportada.

A seleção do catálogo pertence ao **plano da próxima auditoria**. Por padrão ela vive na sessão. Quando o operador usa `Salvar configuração`, o writer canônico também persiste explicitamente:

```text
[audit_catalog]
selected = CAT-01, CAT-05, ...
ai_enabled = true|false
```

Ao carregar o INI, o plano é restaurado e as dependências canônicas são reaplicadas. Exemplo: restaurar `CAT-07` mantém `CAT-06` no plano.

Essa persistência é reutilização explícita da configuração da próxima execução; não cria uma política global separada do catálogo.

No início da auditoria, o snapshot secret-free congela o plano efetivo:

```text
audit_catalog.version
audit_catalog.selected
audit_catalog.ai_enabled
audit_catalog.items
```

O snapshot da AUD é a referência da execução realizada. Alterar o INI depois não altera o plano já congelado de uma AUD existente.

## 7. Inteligência Artificial

O catálogo registra uso de IA por operação como:

```text
NONE
OPTIONAL
REQUIRED
```

A configuração do provider/modelo continua centralizada na **IA principal** e utiliza o orquestrador existente. O catálogo não cria providers especializados por CAT nem altera AUTO, preços, quarentena, circuit breaker, fallback ou limite de tentativas.

Regras atuais:

- `CAT-03` pode usar a IA principal para análise semântica/contextual quando o operador escolher **Executar com IA**;
- `CAT-08` exige IA para entregar seu produto;
- `CAT-09` usa IA somente quando o operador escolher **Executar com IA** e o enriquecimento/remediação advisory correspondente estiver habilitado;
- `CAT-10` pode usar a IA principal opcionalmente por meio do mesmo Improvement Intelligence; sem CAT-08, o domínio é limitado a `SECURITY`; com CAT-08, `SECURITY` é adicionado aos domínios já selecionados;
- `CAT-01`, `CAT-02`, `CAT-04`, `CAT-05`, `CAT-06` e `CAT-07` não ganham chamadas de IA só por serem selecionados;
- o uso de provider de IA durante a auditoria não cria, por si só, dados de visibilidade observada em IA;
- `CAT-06` e `CAT-07` não usam IA para os cálculos de Apdex;
- IA advisory nunca reescreve evidência nem scoring determinístico.

Quando apenas catálogos com IA opcional estão selecionados, o plano inicia em **Executar sem IA (recomendado)**. A opção **Executar com IA** só aparece quando a IA principal está configurada/apta. Se nenhum catálogo selecionado puder usar IA, uma configuração de IA presente na sessão não ativa workload de IA para o plano.

Quando `CAT-08` está selecionado, IA é obrigatória e não existe opção válida de executar sem IA.

## 8. Custo e quota

A estimativa de consumo/custo continua sob os contratos canônicos existentes.

Quando o plano selecionado usa IA ou outro recurso tarifado/limitado, a execução passa pelo preview/acknowledgement antes de iniciar o AUD. A estimativa usa a configuração efetiva naquele momento; AUTO continua sendo resolvido pelo orquestrador.

A tela do catálogo apenas informa a exposição. Ela não inventa preço nem duplica o cálculo financeiro.

## 9. Projeção de execução sem alterar o core

Configurações opcionais presentes na sessão não devem participar silenciosamente de uma execução quando o catálogo correspondente não foi selecionado.

Imediatamente ao consultar readiness/custo/executar, a camada do console projeta temporariamente o plano selecionado sobre os campos opcionais conhecidos e restaura a sessão em seguida.

Exemplos de recursos opcionais mascarados quando o catálogo correspondente não foi selecionado:

- Web Performance;
- termos SERP, GSC e toggles de observabilidade de `CAT-05` (CrUX History, Clarity e Common Crawl);
- Synthetic Apdex;
- Experience Apdex;
- Análise profunda;
- remediação por IA;
- IA principal quando nenhum catálogo selecionado pode usá-la ou quando o operador escolheu executar sem IA;
- flags de remediação por IA quando a execução sem IA foi escolhida;
- `RASAI_PASSIVE_SECURITY`, que só é projetada como `true` quando CAT-10 está no plano; os subcontroles persistentes do CAT-10 não são sobrescritos.

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

Os inputs de `O QUE PESQUISAR` permanecem separados da configuração reutilizável de provider/limites. Se o operador salvar o INI, os inputs não sensíveis suportados são materializados em `[search_intelligence]` e restaurados depois.

## 11. Projeção HTML atual

A taxonomia `CAT-*` já é projetada no `report-catalog/`. O HTML deriva do estado persistido da AUD e não executa nova coleta, request ou IA para preencher o relatório.

A correspondência conceitual é:

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

A seleção exibida deve vir do plano congelado da AUD. Ausência de evidência não autoriza inferir que um CAT não foi solicitado.

A materialização final do `report-catalog/` é validada contra a fonte persistida. Um relatório cuja projeção não corresponda ao estado final do `audit.db` não deve ser anunciado como relatório final completo.

## 12. SaaS

CAT-10 possui contrato secret-free explícito no control plane. O job pode transportar `passive_security`, os subcontroles de headers/cookies/resources/third-party/runtime, OSV/KEV, timeout externo e `passive_security_ai`. Credenciais continuam fora do payload.

`passive_security_ai=true` reutiliza a IA principal e o mesmo Improvement Intelligence; não existe provider/model/reasoning paralelo de segurança. O runtime SaaS projeta `SECURITY` isoladamente quando CAT-08 não está ativo e preserva/adiciona `SECURITY` quando CAT-08 também foi solicitado.

## 13. Testes Windows

A regressão do console deve rodar em `windows-latest`, incluindo:

- IDs estáveis `CAT-01..CAT-10`;
- seleção imediata e abertura do submenu;
- dependência `CAT-07 -> CAT-06`;
- bloqueio de `CAT-08` sem evidência/IA;
- projeção/restauração da sessão;
- persistência e restauração de `[audit_catalog]` no INI;
- congelamento de `audit_catalog` no snapshot da AUD;
- ausência de `PERFIL DA PRÓXIMA AUDITORIA` e `ANÁLISES / RESULTADOS` na preparação pública;
- preservação do preview de custo canônico pelo fluxo de execução.
