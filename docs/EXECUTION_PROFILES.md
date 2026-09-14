# Perfis de Execução do console

## Objetivo

Os **Perfis de Execução** simplificam a preparação de uma auditoria sem criar uma segunda fonte de verdade para o RASAi.

No dashboard `INÍCIO > PREPARAR AUDITORIA`, o acesso canônico é:

```text
15. Perfil da execução
```

Um perfil é apenas um overlay temporário da sessão:

```text
defaults canônicos
+ configuração normal da sessão/INI/SO
+ perfil selecionado para a próxima execução
+ ajustes explícitos feitos depois da seleção
= configuração efetiva da execução
```

O perfil não:

- grava credenciais;
- altera Windows/Machine;
- cria provider de IA paralelo;
- cria termos SERP;
- inventa contexto YMYL/editorial;
- inventa parâmetros Synthetic Apdex;
- altera SARI-001 ou SCORE-GEO-004;
- persiste o preset como configuração estrutural do produto.

Perfis ficam disponíveis somente para **uma URL explícita**. Entrada por arquivo/TXT ou múltiplas URLs torna essa superfície indisponível.

## Estados do catálogo

Cada perfil é apresentado com um dos estados:

- `APTO`: todas as dependências obrigatórias conhecidas estão satisfeitas;
- `CONFIGURAR`: o perfil permanece visível, mas não pode ser aplicado enquanto houver dependência obrigatória ausente;
- `INDISPONÍVEL`: a própria superfície de perfis não pode ser usada no contexto atual.

A validação do catálogo é preventiva e não substitui o preflight final do runtime.

## Regra canônica de IA

Existe **uma única seleção principal de IA por execução**.

Ela pode ser:

- `none`;
- um provider explícito registrado;
- `auto`.

Não existem providers de produção exclusivos para Search Intelligence, Improvement Intelligence ou qualquer outra feature.

Uma feature que usa IA mantém apenas seu contrato funcional: prompt, schema, evidências, validação, finalidade e limites. A seleção de provider pertence ao runtime central.

### Provider explícito

Quando um provider explícito está selecionado, os módulos compatíveis usam esse mesmo provider e suas configurações canônicas de modelo/reasoning.

### AUTO

Quando `AI=auto`, os módulos compatíveis reutilizam a política central de:

- elegibilidade;
- custo estimado da necessidade atual;
- catálogo de preços vigente;
- quarentena por falha terminal;
- circuit breaker para falhas temporárias;
- fallback;
- telemetria de tentativas;
- limites de retry existentes.

O perfil não possui algoritmo AUTO próprio.

## IA no seletor de perfil

O console oferece duas decisões gerais:

```text
1. Não usar IA opcional nos módulos que não a exigem
2. Usar a IA principal se houver provider APTO
```

A opção 1 não pode invalidar um módulo cuja própria finalidade exige IA.

### Regra especial para Análise profunda

`Análise profunda URL` usa **a mesma IA principal da execução**.

Se um perfil contém `deep-analysis`:

- o item 8 precisa estar habilitado;
- a entrada precisa ser uma URL única;
- a IA principal do item 6 precisa estar apta;
- `none` não é válido para a etapa;
- provider/model/reasoning próprios da análise profunda não existem;
- se a seleção principal for `AUTO`, a análise profunda reutiliza o mesmo coordenador central;
- o overlay do perfil não pode desligar a IA necessária a essa etapa.

Mesmo que o operador escolha “não usar IA opcional”, um perfil que inclui `deep-analysis` mantém a IA principal necessária à análise profunda. Após aplicação, o estado efetivo do perfil reflete essa exigência.

## Perfis prontos

### SEO / Search Readiness

Prioriza sinais técnicos de descoberta/indexabilidade e Lighthouse SEO/Best Practices.

IA permanece opcional.

### GEO / AI Readiness

Prioriza sinais de descoberta e compreensão por agentes/IA, incluindo semântica e `agentic-browsing` quando disponível.

Contexto editorial/YMYL permanece explícito ou `AUTO`; o perfil não transforma hipótese de IA em fato persistido.

### Performance

Prioriza Lighthouse Performance, Best Practices e field data conforme as integrações disponíveis.

### Acessibilidade

Prioriza Lighthouse Accessibility e evidências automatizáveis já suportadas.

### Web Quality

Combina Best Practices, SEO e Accessibility como visão operacional de qualidade Web.

### SEO + GEO

Combina Search Readiness e AI Readiness.

### SEO + GEO + Performance

Combina Search/AI readiness com performance.

### Search Intelligence / SERP

O perfil não cria termos.

Para ficar `APTO`, exige:

- termos configurados no item 13 para a sessão;
- `RASAI_SERP_MODE` compatível;
- provider SERP válido;
- credencial quando o modo for `live`;
- limites de requests/depth válidos.

Competitive AI, quando utilizada por fluxos Search compatíveis, usa a seleção principal de IA. Não existe `RASAI_SEARCH_AI_PROVIDER` no contrato vigente.

### Experiência sintética

Exige Synthetic Navigation Apdex e/ou Synthetic User Experience Apdex previamente configurado.

O perfil não inventa threshold, amostras, tentativas, concorrência ou carga.

### Análise profunda URL

Inclui Improvement Intelligence evidence-bound, advisory/non-scoring e com segurança passiva.

Para ficar `APTO`, exige:

- item 8 habilitado;
- uma única URL explícita;
- IA principal apta no item 6, por provider explícito ou `AUTO`;
- domínios/limites/timeout válidos.

A análise profunda não possui seleção própria de provider/model/reasoning.

### Completo seguro

Combina:

- SEO;
- GEO;
- Performance;
- Acessibilidade;
- Web Quality.

Não ativa automaticamente:

- Search Intelligence;
- Synthetic Apdex;
- Análise profunda.

Esses recursos têm dependências, carga ou custo adicional e permanecem opt-in.

### Completo máximo

Combina todos os módulos disponíveis, incluindo:

- SEO;
- GEO;
- Performance;
- Acessibilidade;
- Web Quality;
- Search Intelligence;
- Experiência sintética;
- Análise profunda.

O perfil permanece `CONFIGURAR` enquanto alguma dependência obrigatória estiver ausente.

Para Análise profunda, a dependência de IA é satisfeita pela seleção principal da execução; não existe uma segunda parametrização de IA.

## Perfil personalizado

`C. Compor perfil personalizado` permite selecionar qualquer combinação de módulos.

As mesmas regras de dependência dos perfis prontos são aplicadas.

Se `deep-analysis` fizer parte da composição, a IA principal passa a ser requisito da execução e não pode ser desligada pelo overlay.

## Google Search Console

Cada perfil recebe uma política GSC específica da sessão:

```text
1. Usar somente se a property cobrir a URL auditada
2. Exigir GSC para considerar a auditoria completa/final
3. Não usar GSC nesta execução
4. Herdar a política global RASAI_GSC_ENABLED
```

### Somente se compatível

É a opção recomendada.

Uma property de outro domínio não é transformada em requisito de conclusão. Se a configuração não cobrir a URL auditada, GSC fica não aplicável para aquele alvo.

### Obrigatório

Exige:

- OAuth token presente;
- property sintaticamente válida;
- property cobrindo estruturalmente a URL auditada.

A validação local não comprova se o token está expirado nem se a conta possui permissão real. Essa confirmação depende da resposta do Google.

### Desabilitado

Projeta GSC como desabilitado somente durante a execução do perfil.

Essa decisão é estado da execução, não alteração permanente da configuração global. Ela acompanha o processo de auditoria iniciado pelo console e é reaplicada no coletor antes de qualquer operação GSC. Assim, uma configuração global `RASAI_GSC_ENABLED=true` não pode reativar Search Console dentro de uma execução cujo perfil escolheu “Não usar GSC nesta execução”. Ao terminar/remover o perfil, a configuração global original volta a valer normalmente.

O critério de aceite desse modo é físico: a execução não deve tentar Sitemaps, URL Inspection, Search Analytics nem renovação OAuth para GSC.

### Herdar global

Preserva a política configurada no ambiente normal.

## Dependências principais

| Módulo/capacidade | Dependência obrigatória | Resultado quando ausente |
|---|---|---|
| Search Intelligence | item 13 + modo/provider SERP + credencial quando live + limites válidos | `CONFIGURAR` |
| Experiência sintética | configuração Apdex válida no item 12 | `CONFIGURAR` |
| Análise profunda | item 8 + URL única + IA principal apta no item 6 | `CONFIGURAR` |
| GSC obrigatório | token + property compatível | `CONFIGURAR` |
| GSC somente se compatível | nenhuma dependência bloqueante | não bloqueia |
| GEO | contexto editorial válido | `AUTO` permitido |
| IA opcional | provider apto quando solicitada | pode degradar para sem IA, exceto em módulos que exigem IA |

## Ajustes depois da seleção

Ajustes explícitos feitos após selecionar o perfil têm precedência no domínio correspondente.

Principais entradas do dashboard:

- item `6`: IA principal;
- item `7`: remediações por IA;
- item `9`: Web Performance;
- item `12`: experiência sintética;
- item `8`: Análise profunda;
- item `13`: Search Intelligence.

Uma alteração manual que torne uma dependência obrigatória inválida faz o perfil voltar a `CONFIGURAR` e bloqueia a execução até correção.

Exemplo: selecionar `none` na IA principal enquanto `deep-analysis` estiver ativo torna a Análise profunda não apta.

## Precedência

Durante a execução:

```text
ajuste manual posterior à seleção
> overlay do perfil
> configuração normal da sessão/INI/SO
> default canônico
```

Essa precedência não autoriza um overlay a violar requisito estrutural do módulo. Por isso, Análise profunda preserva a IA principal necessária à própria execução.

## Persistência

O perfil é somente de sessão.

Selecionar, remover ou trocar perfil não grava o preset no INI e não altera credenciais.

A configuração real feita pelo usuário fora do perfil continua seguindo as regras normais de persistência do console.

## Custos

Antes de executar, o console pode apresentar:

- chamadas Web Performance estimadas;
- tentativas de IA estimadas;
- pricing catalogado quando disponível;
- carga Synthetic Apdex;
- quantidade de termos SERP;
- chamadas adicionais da análise profunda.

Para `AUTO`, o custo efetivo depende do provider/modelo selecionado pelo runtime para cada necessidade, respeitando a política central vigente.

## Relatórios

Perfis não criam relatórios paralelos nem alteram contratos de scoring.

Eles apenas determinam quais capacidades são solicitadas para aquela execução.

Os relatórios continuam projetando dados persistidos, status de fulfillment, tentativas e limitações conforme seus contratos próprios.

## Referências

- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [AI_RUNTIME_ORCHESTRATION.md](AI_RUNTIME_ORCHESTRATION.md)
- [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md)
- [COMPETITIVE_AI_INTELLIGENCE.md](COMPETITIVE_AI_INTELLIGENCE.md)
- [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
