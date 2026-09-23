# Relatório consolidado - remediação técnica acionável

**Estado:** vigente.  
**Escopo:** somente `CONS-*`; não altera auditorias `AUD-*`, SARI/SCORE-GEO, regras, provider adapters, quarentena ou política de preços de IA.

## Objetivo

O relatório consolidado deve transformar uma mudança observada em informação operacional suficiente para investigação e correção. A camada especialista não pode ficar limitada a frases como "investigar BR-GEO-xxx" quando a auditoria atual já possui root cause, elemento afetado, valor observado e receita de remediação persistidos.

A implementação é instalada exclusivamente no pacote `rasai.consolidation`, antes da importação do serviço de consolidação. Dessa forma, o enriquecimento não modifica o pipeline de auditoria nem a seleção/custo dos providers de IA.

## Linguagem

A regra pública continua sendo a definida em `specification/11_REPORTING_LANGUAGE_GLOSSARY.md`:

- mensagens, estados, unidades operacionais, ações, categorias e explicações destinadas ao usuário: pt-BR;
- nomes de métricas e padrões técnicos consolidados, como `Core Web Vitals`, `Lighthouse` e `Apdex`, permanecem canônicos quando a tradução reduziria precisão;
- dimensões e categorias com rótulo público inequívoco, como `Evidence & Trust`, `Intent Coverage` e `Structured Data`, são apresentadas em pt-BR;
- IDs, contratos e valores técnicos permanecem canônicos nos artifacts e blocos explicitamente técnicos.

O CONS normaliza vazamentos de inglês operacional na superfície humana sem modificar os valores persistidos.

Nos dois HTMLs do pacote, o rótulo humano prevalece sobre enums, nomes de domínio e variáveis internas quando houver tradução inequívoca. Títulos de regras são apresentados em pt-BR, `details > summary` mantém leitura alinhada à esquerda e tokens técnicos continuam canônicos somente quando necessários à rastreabilidade ou quando aparecem em blocos explicitamente técnicos como `pre`/`code`.

## Referências BR-GEO

Toda regra `BR-GEO-*` citada no consolidado pode ser apresentada como link descritivo para `rules-reference.html` dentro do próprio diretório `CONS-*`.

A página é gerada somente com regras realmente citadas pelo relatório e combina:

- descrição contextual/tooltip do RASAi;
- receita determinística de `rasai.remediation`;
- alvo, elemento e local de correção quando definidos;
- exemplo de implementação quando existir;
- critérios de aceite;
- passos de revalidação;
- decisão humana requerida;
- referências primárias cadastradas em `rasai.rule_references`.

O relatório permanece utilizável offline. Links externos são apenas referências complementares e não são necessários para abrir a definição local da regra.

O campo canônico `RemediationRecipe.action` continua inalterado no artifact estruturado. Em `rules-reference.html`, todas as ações conhecidas são projetadas com rótulo humano em pt-BR, por exemplo `REVIEW_AND_CORRECT` -> **Revisar e corrigir** e `ADD_OR_CORRECT` -> **Adicionar ou corrigir**. Uma ação futura sem mapeamento recebe rótulo humano conservador e não expõe o enum bruto ao usuário. A base das referências também usa rótulos como **Padrão técnico**, **Heurística** e **Referência interna do RASAi**.

## Contexto técnico enviado à IA

O pacote `CONSOLIDATED_SPECIALIST` continua evidence-bound. Além de `changes` e `fix_verification`, a consolidação anexa, quando disponível, o contexto técnico persistido da auditoria atual a partir de `root_cause_analyses` em modo SQLite read-only.

Campos aproveitados incluem:

- `finding_id` e `rule_id`;
- URL e dispositivo;
- severidade e título do finding;
- causa e escopo afetado;
- valor observado e condição esperada;
- elementos afetados, selector, `outer_html` e trecho textual quando persistidos;
- alteração técnica exata;
- exemplo pós-correção;
- critérios de aceite;
- revalidação;
- decisão humana;
- confiança diagnóstica;
- receita determinística da regra.

O CONS compara a assinatura `regra + URL + dispositivo` entre baseline e auditoria atual e marca o contexto como `NEW`, `CHANGED` ou `PERSISTING`. Isso permite que mudanças agregadas de findings sejam acompanhadas de achados técnicos atuais, em vez de uma recomendação genérica para "investigar" a contagem.

A quantidade enviada é limitada e ordenada por aderência à mudança material, novidade/alteração e severidade para controlar tamanho de contexto e custo.

## Política de trechos e exemplos

Existe uma separação obrigatória entre evidência observada e exemplo de remediação:

- `outer_html`/`text_excerpt` só podem ser apresentados como **trecho observado** quando estiverem persistidos no AUD;
- se o trecho não estiver persistido, o relatório declara explicitamente que não está disponível;
- o CONS nunca fabrica um trecho supostamente extraído da URL;
- `example_after` ou `RemediationRecipe.example` são rotulados como **exemplo de implementação**, não como conteúdo observado.

Essa distinção também é incluída nas instruções enviadas ao modelo de IA.

## Apresentação de correções técnicas

O HTML consolidado recebe uma seção determinística `technical-remediation` com, por finding elegível:

1. regra, título, severidade e estado de evolução;
2. URL e dispositivo;
3. problema encontrado;
4. valor observado;
5. trecho observado, quando persistido;
6. correção técnica recomendada;
7. exemplo de implementação, quando disponível;
8. critérios de aceite;
9. como revalidar;
10. decisão humana, quando requerida.

Esse bloco é a base técnica utilizada pela análise especialista quando IA está habilitada. O conteúdo determinístico não é rotulado como "gerado por IA".

## Instruções adicionais ao especialista

Sem mudar provider, modelo, política de preço ou schema público da resposta, o especialista recebe instruções para:

- usar `current_technical_findings` e `rule_reference`;
- citar regra e URL/dispositivo quando fornecidos;
- reutilizar alteração exata, exemplo, aceite e revalidação existentes;
- priorizar achados `NEW`/`CHANGED` quando um delta agregado de findings for discutido;
- nunca inventar selector, HTML, URL ou trecho observado;
- declarar quando o trecho observado não foi persistido;
- produzir texto e ações em pt-BR, preservando apenas nomes conceituais oficiais em inglês.

## Reabertura de CONS materializado

Ao reabrir um `CONS-*` que tenha `specialist-analysis.json`, a camada resolve o contexto técnico usando os IDs de baseline/current persistidos, desde que os respectivos `AUD-*/audit.db` continuem disponíveis. O acesso é read-only e o enriquecimento modifica apenas arquivos derivados do `CONS-*`.

## Falha segura

A funcionalidade é fail-open:

- ausência da tabela `root_cause_analyses` não invalida o consolidado;
- erro ao ler contexto técnico não altera o resultado determinístico;
- ausência de recipe específica usa fallback conservador;
- ausência de referência externa não cria fonte artificial;
- erro ao gerar a página auxiliar não afeta `report.html`.

## Testes mínimos

A suíte específica cobre:

- leitura read-only do root cause e classificação `CHANGED`;
- propagação de URL, trecho observado e recipe;
- criação de links/tooltip para `BR-GEO-*`;
- distinção visual entre trecho observado e exemplo de implementação;
- tradução de inglês operacional, dimensões/categorias públicas e ações de remediação sem alterar seus valores canônicos persistidos;
- ausência de enums de ação brutos, como `REVIEW_AND_CORRECT`, em `rules-reference.html`.
