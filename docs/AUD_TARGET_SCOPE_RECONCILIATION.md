# Contrato transversal de alvo da AUD - Console e CAT-05

## Fonte da verdade

O campo `state.target` definido em **INÍCIO > PREPARAR AUDITORIA** é a única fonte do URL da próxima AUD. A normalização continua em `rasai.url_utils.normalize_url`; o CLI mantém a validação já homologada de uma URL. Nenhum catálogo ganha uma segunda URL executável.

Os motores técnicos, PageSpeed, Apdex e IA derivam o alvo da AUD pelo fluxo atual. SERP recebe o domínio derivado do target, mas suas consultas continuam inputs próprios. Perplexity Search API continua um pedido opcional e potencialmente faturável, com consentimento independente. GSC continua vinculada a uma propriedade de domínio ou URL-prefix autenticada, não inventada a partir do alvo.

## Proveniência das consultas independentes

`search_scope_target` e `perplexity_scope_target` são **metadados não secretos** vinculados somente quando o operador efetivamente escolhe/edita consultas no alvo corrente. Persistem nas seções `search_intelligence.source_target` e `perplexity_draft.source_target` do mesmo INI por meio do serializer existente. Não são alvo de coleta, não sobrescrevem `state.target`, não criam custo e não são carregados como autorização de pesquisa.

Um INI antigo sem esses campos continua válido. O estado exibido será `SOURCE_UNVERIFIED`, sem atribuir falsamente sua proveniência ao alvo corrente.

O contrato compartilhado `rasai.target_scope_reconciliation` calcula: `NOT_REQUESTED`, `TARGET_INVALID`, `SOURCE_UNVERIFIED`, `SAME_TARGET`, `ORIGIN_CHANGED` e `PATH_CHANGED`. Todos os catálogos continuam consumindo sua configuração de execução por interfaces existentes; o contrato é apenas uma projeção/validação da origem das configurações.

## Propagação e ajuste autossuficiente

Ao editar a opção `00000002`, `propagate_target` normaliza e aplica a URL uma vez a `state.target` e `state.current_url`. O preflight existente passa a mesma identidade aos motores técnicos, Apdex e IA; o domínio SERP continua calculado dinamicamente da URL efetiva. Não se cria variável adicional de coleta nem se duplica um motor. Ao salvar (opção `2`), o INI recebe a URL normalizada pela serialização já existente; com opção `1`, apenas a sessão a mantém. Alterações de barra final não significam mudança de alvo.

Se não houver consultas em determinada fonte, o marcador inerte de proveniência pode acompanhar o novo alvo. Quando há termos SERP ou rascunhos Perplexity, o marcador original é **preservado** até edição/confirmação explícita, evitando esconder parâmetros de outro domínio. Localidade, termos, filtros de domínio, propriedade Google Search Console e consentimento comercial são configurações independentes; a URL, isoladamente, não permite inferir seus valores.

O console apresenta um **resumo do que foi herdado e o que precisa de revisão**, com o destino de ajuste em cada mensagem de conflito. A opção `A` no próprio menu **Preparar auditoria** abre um assistente com os editores já existentes:

- `1`: CAT-05, termos e localidade SERP
- `2`: CAT-05, consultas/rascunhos Perplexity
- `3`: editor canônico da propriedade GSC (ID `23579716`)
- `V`: voltar sem disparar auditoria nem consulta externa

Quando a URL realmente mudou, `A` também aparece em **Destino da alteração**, antes da escolha entre sessão `1` e salvar no INI `2`. O assistente não cria requests faturáveis, não concede consentimento e não converte uma propriedade GSC em outra sem escolha do operador. Se a URL só foi reformatada, os conflitos preexistentes continuam disponíveis pelo atalho `A` da preparação, sem apresentar prompt de save desnecessário.

## Revisão antes da execução

Quando há **alteração de origem comprovada** entre consultas configuradas e o novo alvo, o console pergunta se o operador deseja:

- **C:** confirmar que as consultas existentes servem ao novo alvo (isto somente atualiza os metadados de contexto; não autoriza nenhuma API)
- **N:** executar a AUD sem as pesquisas SERP/Perplexity desta vez (restaurar o plano após o uso)
- **V:** voltar ao plano para revisão, sem execução

Uma alteração de path gera aviso não bloqueante; uma configuração legada sem proveniência gera aviso, não reescrita. A confirmação financeira independente de cada integração permanece obrigatória.

O CAT-05 e a preparação exibem uma matriz de herança dos motores, termos independentes, Perplexity e compatibilidade da propriedade GSC. Divergências no escopo de GSC seguem a política canônica do `gsc_scope` (fonte obrigatória vs opcional).

## Fronteira de execução

`build_search_argv` usa a URL fornecida pelo preflight, compara com o alvo normalizado e deriva o domínio apenas daquele valor. A mudança nunca modifica regras de scoring ou evidências históricas; futuras AUDs registram target e consultas efetivas pelo sistema de persistência existente. Reprocessamento de AUD anterior permanece vinculado à identidade física do banco e não adota `state.target` do console atual.

## Testes

`tests/test_target_scope_reconciliation.py`: alteração entre domínios, caminho, INI anterior, vínculo de queries, GSC incompatível, serialização das duas fontes, propagação e falha fechada quando o alvo de execução diverge. Nenhum request de provider, Docker, Browser ou smoke pago é necessário.
