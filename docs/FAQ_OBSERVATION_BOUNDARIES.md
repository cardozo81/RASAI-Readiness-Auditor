# FAQ  -  limites de DOM, interação e representatividade (#601)

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
pode qualificar. A validação assinada é **pré-condição offline** e não substitui o
piloto opcional de clique em uma página já carregada. O piloto
`faq_existing_page_pilot.inspect_existing_page_faq` exige consentimento
explícito, contexto de navegador isolado e bloqueio de novas requisições
após o carregamento. Antes do clique, aplica a mesma elegibilidade do
verificador de recibo: botão único, fora de formulário, sem
`onclick`/handlers inline, submissão implícita ou atributos ambíguos.
Seu resultado continua **não atestado**, sem vinculação comprovada
à mesma amostra da AUD, sem prova para crawler e sem mudar o score.

Uma resposta vista somente após ação atestada não prova que o
Googlebot a obtenha sem interação. A projeção não altera scorer,
findings, motor de Apdex de navegacao/motor de Apdex de experiencia, auditoria ou requisições comerciais.

## Regra de execução

As regressões são fixtures locais e imutáveis. Smoke humano novo
somente se uma coleta opt-in física for necessária para esclarecer
um caso que não possa ser decidido com os artefatos já registrados.
Qualquer alteração de peso/regra BR-GEO-039/049 depende de ADR e
versão metodológica próprias; nunca regravar scores históricos.

## Observação tardia de FAQ SPA (contrato do piloto)

Depois do único clique elegível, `faq_existing_page_pilot` admite no máximo
900 ms adicionais de estabilização **somente do DOM da página já carregada**.
A espera exige que o botão observado esteja expandido e que o painel de mesmo
ID possua texto materializado. Ela não dispara nova navegação nem permite
tráfego HTTP após o clique; a rota temporária bloqueia novas requisições.
Um timeout não equivale a resposta editorial inexistente: o DOM final ainda
é inspecionado pelo comparador e pode permanecer inconclusivo.

No caminho de sucesso, o piloto devolve os hashes SHA-256 do HTML anterior e
posterior e os instantes UTC observados; não se trata de recibo assinado.
Falha de inspeção *após* o clique declara `action_performed=true`, evitando
afirmar que nenhuma ação ocorreu. A saída **não** atesta mesma amostra da AUD,
visibilidade por crawler, conformidade ou permissão de alterar score.
