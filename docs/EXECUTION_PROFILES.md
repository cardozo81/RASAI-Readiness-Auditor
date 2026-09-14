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
- habilita silenciosamente Improvement Intelligence;
- transforma uma property GSC de terceiro em acesso válido ao domínio auditado.

A política de GSC selecionada dentro de um perfil também é somente da sessão/próxima execução. O contrato detalhado está em [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md).

## Escopo: URL única

Perfis ficam disponíveis somente quando o item **1. Entrada** possui uma URL única explícita.

Se a entrada estiver em modo TXT/arquivo ou ainda não houver URL informada, o menu mostra o recurso como `INDISPONÍVEL`.

Se o operador trocar de URL para arquivo enquanto um perfil estiver ativo, o perfil é removido da sessão para impedir que um overlay pensado para uma URL seja aplicado a múltiplos targets.

## Estados visíveis antes da seleção

Todos os presets permanecem visíveis no catálogo para que o operador saiba quais capacidades existem e o que precisa parametrizar.

Exemplo:

```text
 1. [APTO] SEO / Search Readiness
 2. [APTO] GEO / AI Readiness
 ...
 8. [CONFIGURAR] Search Intelligence / SERP
     Falta : Search Intelligence selecionado: configure os termos transitórios no item T
 9. [CONFIGURAR] Experiência sintética
     Falta : Experiência sintética selecionada: configure Synthetic/Experience Apdex antes da execução
10. [CONFIGURAR] Análise profunda URL
     Falta : Análise profunda selecionada: habilite/configure o item 13 antes da execução
12. [CONFIGURAR] Completo máximo
     Falta : ...
```

Semântica:

- `APTO`: o preset pode ser selecionado;
- `CONFIGURAR`: o preset continua visível, mas **não pode ser aplicado** enquanto houver dependência obrigatória ausente;
- `INDISPONÍVEL`: o próprio recurso de perfis não pode ser usado no contexto atual, por exemplo entrada em arquivo/múltiplas URLs.

Ao tentar abrir um preset `CONFIGURAR`, o console mostra as pendências e orienta o item de configuração correspondente. O operador deve voltar ao menu principal, parametrizar o recurso e retornar a `F. Perfil da execução`.

Essa validação antecipada não substitui o preflight do runtime. Ela evita a situação em que uma execução aparentemente "completa" termina e só no HTML o usuário descobre que uma capacidade nunca foi solicitada.

Para GSC, a validação local também diferencia **escopo estrutural da property** de **autorização OAuth**. O console consegue saber previamente se `sc-domain:sersolucao.com.br` não cobre `https://www.portoseguro.com.br/`; ele não consegue provar sem consultar o Google se um token ainda é válido ou se a conta possui permissão na property.

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
F. Perfil da execução : APTO | <perfil> | SEM IA|IA SE DISPONÍVEL | SESSÃO
   Google Search Console  : SOMENTE SE COMPATÍVEL|OBRIGATÓRIO|DESABILITADO|HERDAR GLOBAL
```

Perfis com dependência obrigatória faltante não entram no estado ativo.

## Perfis prontos

Todos os presets usam por default **GSC somente se a property configurada cobrir a URL auditada**. Ao selecionar o perfil, o operador pode trocar essa política para `OBRIGATÓRIO`, `DESABILITADO` ou `HERDAR GLOBAL`.

### SEO / Search Readiness

Envolve core determinístico de search readiness, Lighthouse SEO e Best Practices. Serviços já configurados continuam obedecendo seus próprios contratos; GSC recebe a política de sessão escolhida no perfil.

Pode gerar chamadas PageSpeed/Lighthouse e CrUX conforme configuração/credenciais. IA é opcional e independente.

### GEO / AI Readiness

Envolve sinais para descoberta/consumo por agentes/IA, Lighthouse SEO, Best Practices, `agentic-browsing` e contexto semântico disponível.

`RASAI_CONTENT_RISK_PROFILE`, `RASAI_YMYL_CATEGORY` e demais campos editoriais continuam sob controle explícito do operador. `AUTO` permanece hipótese, não fato.

### Performance

Envolve Lighthouse Performance, Best Practices e field data conforme a configuração Web Performance vigente.

### Acessibilidade

Envolve Lighthouse Accessibility, Best Practices e as demais evidências determinísticas já existentes.

### Web Quality

Combina Best Practices, SEO e Accessibility. Validadores e observability já habilitados continuam com seus próprios contratos.

### SEO + GEO

Combina os módulos SEO e GEO na mesma execução.

### SEO + GEO + Performance

Combina search readiness, AI readiness e performance.

### Search Intelligence / SERP

O perfil **não cria termos**.

Para ficar `APTO`, exige:

- termos informados no item `T` da sessão;
- `RASAI_SERP_MODE` compatível com a execução;
- provider SERP válido;
- credencial quando `RASAI_SERP_MODE=live`;
- limites de queries/depth/requests válidos.

A validação do catálogo usa o mesmo contrato operacional do Search Intelligence; portanto termos presentes, mas provider/key/modo inválidos, continuam resultando em `CONFIGURAR`.

### Experiência sintética

O perfil **não cria threshold, amostras, tentativas, concorrência ou carga**.

Exige Synthetic Navigation Apdex e/ou Synthetic User Experience Apdex previamente configurado. A carga HTTP real contra o alvo permanece explícita.

### Análise profunda URL

Integra Improvement Intelligence somente quando o item **13. Análise profunda URL** já estiver habilitado e válido.

O perfil não inventa provider/model/reasoning. Quando o item 13 está ligado, o catálogo também valida a disponibilidade da IA exclusiva da análise profunda, incluindo credencial/provider/modelo conforme o contrato vigente.

Improvement Intelligence permanece evidence-bound, advisory/non-scoring e com segurança passiva.

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

Esses grupos têm dependências, carga ou custo adicional que justificam opt-in explícito.

GSC não é tratado como fonte pública obrigatória por este preset. O default do perfil é `SOMENTE SE COMPATÍVEL`.

### Completo máximo

Combina **todos os módulos do catálogo**:

- SEO;
- GEO;
- Performance;
- Acessibilidade;
- Web Quality;
- Search Intelligence / SERP;
- Experiência sintética;
- Análise profunda URL.

O nome "máximo" descreve cobertura funcional; não significa relaxar segurança, limites ou metodologia.

O preset fica `CONFIGURAR` e **não pode ser selecionado** até que todas as dependências dos módulos opcionais estejam válidas. Isso normalmente inclui:

- termos e provider/credencial SERP;
- configuração Synthetic/Experience Apdex;
- item 13 habilitado com provider/model/reasoning válidos.

Depois que essas dependências ficam aptas, o operador ainda escolhe se a **IA padrão do perfil** será `SEM IA` ou `IA SE DISPONÍVEL` e qual será a política GSC da execução. A IA própria de Improvement Intelligence continua independente.

## Perfil personalizado

`C. Compor perfil personalizado` abre a lista guiada de módulos.

Cada módulo mostra finalidade, custo/exposição e dependências. Uma composição personalizada com dependência obrigatória ausente também permanece `CONFIGURAR` e não é aplicada até a parametrização ser concluída.

O personalizado também recebe a escolha explícita de política GSC antes de ser aplicado.

## IA padrão do perfil

Depois que um preset está apto, o console oferece:

```text
1. Não usar IA padrão nesta execução
2. Usar IA padrão se houver provider APTO
```

### Não usar IA

Durante a execução efetiva do perfil, `ai_provider` é projetado como `none`; a configuração persistida do usuário não é alterada.

### Usar se disponível

A regra é:

1. se o provider já selecionado pelo usuário estiver `APTO`, preservá-lo;
2. caso contrário, usar `AI=auto` somente se existir provider elegível/APTO;
3. se nenhum provider estiver apto, seguir sem IA padrão.

Esse modo não bloqueia o core quando não existe IA padrão disponível.

Credenciais nunca são criadas, trocadas ou persistidas pelo perfil.

Improvement Intelligence possui IA própria e independente no item 13.

## Google Search Console no perfil

Depois da escolha de IA, o console oferece:

```text
1. Usar somente se a property GSC cobrir a URL auditada (recomendado)
2. Exigir GSC para considerar a auditoria completa/final
3. Não usar GSC nesta execução
4. Herdar exatamente a política global RASAI_GSC_ENABLED
```

### Somente se compatível

É o default dos presets. Durante a execução, o perfil remove apenas o override `RASAI_GSC_ENABLED` e deixa o contrato credential-driven decidir a elegibilidade.

Se token e property estiverem configurados, mas a property não cobrir a URL auditada, o runtime classifica GSC como `NOT_APPLICABLE` para aquele alvo e não envia chamadas incompatíveis ao Google. Isso não cria requisito de conclusão.

### Obrigatório

Projeta `RASAI_GSC_ENABLED=true` somente durante a execução do perfil.

Antes de aplicar o perfil, o console exige:

- token presente;
- property presente e sintaticamente válida;
- property cobrindo estruturalmente a URL auditada.

Se existir mismatch, o perfil fica `CONFIGURAR`. Não há motivo para iniciar uma execução que já se sabe incapaz de chegar a `COMPLETE/FINAL`.

A aprovação local não valida OAuth. Token expirado/revogado ou conta sem permissão ainda podem falhar em runtime; como GSC foi escolhido como obrigatório, essa falha deixa o AUD parcial/não final.

### Desabilitado

Projeta `RASAI_GSC_ENABLED=false` somente durante a execução do perfil.

### Herdar global

Preserva exatamente a semântica global:

- sem override → automático;
- `true` → obrigatório;
- `false` → desabilitado.

O token representa a conta Google, não um domínio. A property é que define o escopo de dados. Consulte [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md).

## Dependências e `CONFIGURAR`

Uma capacidade explicitamente solicitada não deve ser silenciosamente omitida.

| Módulo/capacidade | Dependência | Comportamento no catálogo |
|---|---|---|
| Search Intelligence | termos, modo, provider, credencial e limites | `CONFIGURAR`; preset não selecionável |
| Experiência sintética | Apdex previamente configurado | `CONFIGURAR`; preset não selecionável |
| Análise profunda | item 13 + IA deep válida | `CONFIGURAR`; preset não selecionável |
| GSC obrigatório | token + property que cubra a URL | `CONFIGURAR`; execução previsivelmente parcial não é aplicada |
| GSC somente se compatível | token/property podem estar ausentes ou ser de outro alvo | não bloqueia; GSC fica não exigido/não aplicável |
| GEO | contexto YMYL/editorial | `AUTO` é permitido e informado |
| IA padrão `se disponível` | provider apto | não bloqueia; fallback seguro para sem IA padrão |

O runtime continua executando sua validação final depois do catálogo. Se algo mudar entre a visualização e a aplicação, o preset é revalidado antes de entrar no estado ativo.

## Ajuste fino

Depois de escolher um perfil `APTO`, as opções normais continuam disponíveis. Ajustes explícitos feitos depois da seleção vencem o preset no domínio correspondente, por exemplo:

- item `4` → IA;
- item `5` → remediações;
- item `6` → Web Performance;
- item `11` → experiência sintética;
- item `13` → análise profunda;
- item `T` → Search Intelligence.

A política GSC do perfil é escolhida na própria seleção do preset. Alterações persistentes posteriores nas variáveis GSC continuam existindo na configuração normal e voltam a valer após o término do overlay da execução.

Alterações avançadas de Web Performance/Lighthouse também são respeitadas quando diferem da configuração-base capturada no momento da seleção.

## Precedência

Durante uma execução com perfil:

```text
ajuste manual posterior à seleção
> overlay do perfil
> configuração normal carregada na sessão
> default canônico do RASAi
```

Para `RASAI_GSC_ENABLED`, a política GSC do perfil é parte do overlay da sessão. Token e property não são alterados pelo preset.

Essa precedência existe somente para a execução.

## Persistência

Selecionar/remover um perfil não marca o INI como alterado porque o perfil não modifica o estado persistível.

O preset nunca é salvo. Um ajuste manual real continua podendo ser salvo somente pela ação explícita normal do usuário.

## Custos

Cada preset e módulo apresenta descrição de custo/exposição antes da aplicação. Quando aplicável, o detalhe mostra:

- nível de exposição;
- intervalo potencial de chamadas Web Performance;
- intervalo potencial de tentativas de IA;
- pricing unitário catalogado quando disponível;
- carga Synthetic Apdex já configurada;
- quantidade de termos SERP;
- aviso de chamadas adicionais da análise profunda.

GSC incompatível não deve gerar chamada ao provider apenas para descobrir um conflito de property que pode ser resolvido localmente.

O RASAi não inventa quantidade de tokens antes da execução e não converte quota em preço quando o provider não fornece base suficiente.

## Compatibilidade com os relatórios HTML

Perfis são uma superfície de **orquestração do console**, não uma nova fonte de evidência. Por isso não criam schema, score ou relatório paralelo.

Os relatórios continuam materializados a partir do estado/evidência realmente persistidos no `AUD-*`:

- `search-intelligence.html` apresenta observação SERP quando executada ou estado explícito sem observações;
- `apdex.html` apresenta Synthetic Navigation Apdex ou estado explícito de não execução;
- `apdex-experience.html` apresenta Synthetic User Experience Apdex ou estado explícito de não execução;
- `improvement-intelligence.html` apresenta a análise profunda ou estado explícito de não execução/falha conforme persistência;
- `ai-usage.html` distingue finalidade não solicitada/desabilitada de tentativa externa, resposta aceita, falha de provider/contrato, tokens e custo quando mensuráveis;
- as demais páginas recebem o quadro padronizado de consumo de IA atribuído à superfície proprietária, sem duplicar custo entre relatórios.

Quando GSC foi explicitamente exigido e existe `PROPERTY_URL_MISMATCH`, o fulfillment persiste a falha como configuração reprocessável. O banner/estado canônico do relatório deve deixar claro que a auditoria não é final enquanto o requisito continuar incompatível. Em modo `SOMENTE SE COMPATÍVEL`, o mesmo mismatch é `NOT_APPLICABLE` e não deve fabricar parcialidade.

O `Completo máximo` não exige mudança de metodologia ou renderer: ele apenas impede que o usuário aplique o preset enquanto alguma capacidade obrigatória ainda não estiver configurada. Uma vez executada, cada superfície continua obedecendo seu contrato de evidência e reporting vigente.

Falha em runtime após um preset ter ficado `APTO` continua sendo possível (rede, provider, timeout, token OAuth expirado, permissão GSC etc.). Nesse caso o relatório deve mostrar falha/parcialidade quando a capacidade era obrigatória; o console não fabrica dados para preencher uma capacidade que não concluiu.

## Segurança metodológica

Perfis selecionam **o que executar**, não alteram a metodologia.

Não modificam:

- `SARI-001`;
- `SCORE-GEO-004`;
- pesos de scoring;
- regras históricas;
- thresholds metodológicos sem ação explícita do operador.

A ausência/presença de evidência continua obedecendo ao contrato normal de cobertura/confiabilidade.
