# FAQ — limites de DOM, interação e representatividade (#601)

## Contrato observacional

O leitor offline diferencia `COLLAPSED_UNMOUNTED` (ID do painel ausente
do DOM), `COLLAPSED_DOM_TEXT` (texto presente mesmo com controle fechado)
e `EXPANDED_DOM_TEXT` (texto presente com estado expandido). Nenhum
estado comprova indexação, gesto humano ou ausência editorial.

O relatório read-only avalia **no máximo 12 snapshots físicos** e
identifica explicitamente capturas ilegíveis e excedentes. IDs de
snapshot duplicados tornam a agregação inconclusiva (N/D). Não encontrar
o padrão FAQ na amostra não prova que o site não possua FAQ.

## Fronteira do recibo assinado

A validação exige HMAC correto com chave confiável, consentimento por
alvo, coletor permitido, execução isolada, bloqueio de rede após carga,
dois hashes DOM e relógios físicos UTC. Complementarmente, somente
`button` nativo único, não submetível, fora de formulário, sem
`onclick`/handlers inline, `href`, `disabled` ou IDREF ambíguo
pode qualificar. Isso é **pré-condição offline**, não implementação
de clique, sandbox de browser ou prova independente de segurança.

Uma resposta vista somente após ação atestada não prova que o
Googlebot a obtenha sem interação. A projeção não altera scorer,
findings, M23/M25, auditoria ou requisições comerciais.

## Regra de execução

As regressões são fixtures locais e imutáveis. Smoke humano novo
somente se uma coleta opt-in física for necessária para esclarecer
um caso que não possa ser decidido com os artefatos já registrados.
Qualquer alteração de peso/regra BR-GEO-039/049 depende de ADR e
versão metodológica próprias; nunca regravar scores históricos.
