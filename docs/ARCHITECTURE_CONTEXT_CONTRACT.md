# Contexto arquitetural consultivo - contrato inicial

Este contrato é **F1 / resolução isolada e read-only**, vinculado à issue #646.
Nenhuma integração no planejamento da auditoria, catálogo, score, modelo de IA,
report ou SQLite foi ativada por esta mudança. Não há propagação F2/F3.

A API pura `rasai.architecture_context.resolve_architecture` separa
observação física, escolha declarada, modo e aplicação por consumidor. O conjunto
de consumidores autorizados é fornecido explicitamente pelo chamador; o default
é vazio, portanto nenhum consumidor herda arquitetura automaticamente.
Isso **não é** aprovação de novos consumidores. O contrato recusa evidência
ausente, contraditória, sem identificador ou de outra AUD/página/URL solicitada/URL final/device/snapshot. Identidades
opcionais ausentes em dados legados não satisfazem uma solicitação com
AUD/página/URL final explícitas; não existe inferência por domínio.

## Matriz de elegibilidade provisória (não constitui aprovação)

| Consumidor | Classificação inicial | Estado |
| --- | --- | --- |
| Diagnósticos descritivos do relatório | ADVISORY_SAFE | Candidato, não integrado |
| Recomendações IA descritivas | ADVISORY_SAFE | Candidato, requer evidência/limites |
| CAT-01..CAT-08: parâmetros de coleta | PRE_COLLECTION_ONLY | Sem herança |
| SARI e SCORE-GEO | METHOD_CHANGE_REQUIRES_ADR | Sem herança |
| Apdex e thresholds | METHOD_CHANGE_REQUIRES_ADR | Sem herança |
| índice sintético de navegação e índice sintético de experiência | METHOD_CHANGE_REQUIRES_ADR | Sem herança |
| Relatórios: fatos históricos | INAPPLICABLE | Somente fatos originais |

Antes de habilitar um consumidor: identificar seu owner, fase, fonte física,
versão de contrato, dados necessários, risco, testes e aprovação metodológica.
A versão inicial não fornece confiança numérica, pois nenhum método de
calibração da confiança foi aprovado. Não presume SSR distinguível de estático.

## Próximos gates

- Inventariar classes e chaves reais em módulo de descoberta/relatório de rastreamento e mapear os consumidores exatos.
- Definir o contrato de precedência INI/sessão/snapshot sem tocar o INI do operador.
- Testar round-trip de configuração isolada e perfis antigos.
- Integrar apenas consumidores consultivos explicitamente autorizados, com
  provenance e indicação de divergência; manter scores históricos imutáveis.
- Executar testes focais e CI no HEAD da branch antes do merge.

## Escolha versionada isolada (F2 parcial)

O módulo `architecture_choice.py` implementa serialização pura e validação
estrita de `AUTO`, `DECLARED` e `UNFORCED`. Ausência em registros antigos
resulta em `UNFORCED`, sem alterar o comportamento histórico. O método
`write_choice` cria uma cópia do mapeamento recebido; não acessa o INI,
Registry, segredos, banco de evidências ou configuração de execução.

`DECLARED` exige classe concreta, enquanto `AUTO` e `UNFORCED` recusam
valor declarado residual. Registros explícitos malformados são recusados;
sem downgrade silencioso. A passagem deste contrato para INI/sessão/snapshot
exige outra fase de integração e teste de precedência por campo.

## Precedência isolada de seleção

A API pura `resolve_choice_precedence` avalia, nesta ordem, snapshot,
sessão e configuração-base. Uma opção explícita `UNFORCED` na camada
superior desativa a herança das camadas inferiores. Registros ausentes em
todas as camadas mantêm `UNFORCED`; registros inválidos recusam a resolução
sem fallback silencioso. O resolvedor não lê ou grava INI, SQLite ou sessão
real. A aprovação de integração operacional permanece um gate separado.

## Congelamento e restauração isolados

O codec `architecture_choice_snapshot.py` produz um registro JSON versionado,
identificado por AUD, usando a precedência previamente validada. A restauração
exige o mesmo identificador de auditoria, recusa campos e chaves JSON duplicadas,
versões incompatíveis e seleção inválida. Não executa I/O ou persistência real.
O contrato não presume consentimento para serviços faturáveis e não altera
índices, configuração do operador ou evidências físicas.
