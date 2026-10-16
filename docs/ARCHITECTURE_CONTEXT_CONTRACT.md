# Contexto arquitetural consultivo — contrato inicial

Este contrato é **F1 / resolução isolada e read-only**, vinculado à issue #646.
Nenhuma integração no planejamento da auditoria, catálogo, score, modelo de IA,
report ou SQLite foi ativada por esta mudança. Não há propagação F2/F3.

A API pura `rasai.architecture_context.resolve_architecture` separa
observação física, escolha declarada, modo e aplicação por consumidor. O conjunto
de consumidores autorizados é fornecido explicitamente pelo chamador; o default
é vazio, portanto nenhum consumidor herda arquitetura automaticamente.
Isso **não é** aprovação de novos consumidores. O contrato recusa evidência
ausente, contraditória, sem identificador ou de outra URL/device/snapshot.

## Matriz de elegibilidade provisória (não constitui aprovação)

| Consumidor | Classificação inicial | Estado |
| --- | --- | --- |
| Diagnósticos descritivos do relatório | ADVISORY_SAFE | Candidato, não integrado |
| Recomendações IA descritivas | ADVISORY_SAFE | Candidato, requer evidência/limites |
| CAT-01..CAT-08: parâmetros de coleta | PRE_COLLECTION_ONLY | Sem herança |
| SARI e SCORE-GEO | METHOD_CHANGE_REQUIRES_ADR | Sem herança |
| Apdex e thresholds | METHOD_CHANGE_REQUIRES_ADR | Sem herança |
| M23 e M25 | METHOD_CHANGE_REQUIRES_ADR | Sem herança |
| Relatórios: fatos históricos | INAPPLICABLE | Somente fatos originais |

Antes de habilitar um consumidor: identificar seu owner, fase, fonte física,
versão de contrato, dados necessários, risco, testes e aprovação metodológica.
A versão inicial não fornece confiança numérica, pois nenhum método de
calibração da confiança foi aprovado. Não presume SSR distinguível de estático.

## Próximos gates

- Inventariar classes e chaves reais em M6/M24 e mapear os consumidores exatos.
- Definir o contrato de precedência INI/sessão/snapshot sem tocar o INI do operador.
- Testar round-trip de configuração isolada e perfis antigos.
- Integrar apenas consumidores consultivos explicitamente autorizados, com
  provenance e indicação de divergência; manter scores históricos imutáveis.
- Executar testes focais e CI no HEAD da branch antes do merge.
