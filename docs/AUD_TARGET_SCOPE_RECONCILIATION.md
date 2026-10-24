# Contrato transversal de alvo da AUD — Console e CAT-05

## Fonte da verdade

O campo `state.target` definido em **INÍCIO > PREPARAR AUDITORIA** é a única fonte do URL da próxima AUD. A normalização continua em `rasai.url_utils.normalize_url`; o CLI mantém a validação já homologada de uma URL. Nenhum catálogo ganha uma segunda URL executável.

Os motores técnicos, PageSpeed, Apdex e IA derivam o alvo da AUD pelo fluxo atual. SERP recebe o domínio derivado do target, mas suas consultas continuam inputs próprios. Perplexity Search API continua um pedido opcional e potencialmente faturável, com consentimento independente. GSC continua vinculada a uma propriedade de domínio ou URL-prefix autenticada, não inventada a partir do alvo.

## Proveniência das consultas independentes

`search_scope_target` e `perplexity_scope_target` são **metadados não secretos** vinculados somente quando o operador efetivamente escolhe/edita consultas no alvo corrente. Persistem nas seções `search_intelligence.source_target` e `perplexity_draft.source_target` do mesmo INI por meio do serializer existente. Não são alvo de coleta, não sobrescrevem `state.target`, não criam custo e não são carregados como autorização de pesquisa.

Um INI antigo sem esses campos continua válido. O estado exibido será `SOURCE_UNVERIFIED`, sem atribuir falsamente sua proveniência ao alvo corrente.

O contrato compartilhado `rasai.target_scope_reconciliation` calcula: `NOT_REQUESTED`, `TARGET_INVALID`, `SOURCE_UNVERIFIED`, `SAME_TARGET`, `ORIGIN_CHANGED` e `PATH_CHANGED`. Todos os catálogos continuam consumindo sua configuração de execução por interfaces existentes; o contrato é apenas uma projeção/validação da origem das configurações.

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

`tests/test_target_scope_reconciliation.py`: alteração entre domínios, caminho, INI legado, vínculo de queries, GSC incompatível, serialização das duas fontes, propagação e falha fechada quando o alvo de execução diverge. Nenhum request de provider, Docker, Browser ou smoke pago é necessário.
