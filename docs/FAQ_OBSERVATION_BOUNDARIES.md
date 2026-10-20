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

## Identidade física consultiva por captura (próximo macrolote #601)

A projeção CAT-03 registra, quando **presentes no SQLite selado**, os
atributos `snapshot_id / page_id / requested_url / final_url / device`
da mesma AUD na tabela de proveniência FAQ. Campos não existentes em
capturas legadas ou URLs/dispositivos inválidos continuam `N/D`.
IDs de snapshot duplicados em qualquer página da base são recusados,
inclusive se uma ocorrência não aparecer entre os 12 exibidos.
Os valores são texto escapado, não hiperlinks executáveis.

Isso permite selecionar **qual snapshot concreto** exigiria um recibo
assinado de interação, mas **não** o produz, não atesta clique nem liga
automaticamente os hashes de um navegador posterior à coleta captura canônica. Não
altera BR-GEO-039/049, nem permite recalcular scores já selados.
A decisão de método e a autorização para obter recibo físico continuam
gates separados. Essa projeção apenas lê SQLite e HTML locais.

## Vínculo offline de recibo assinado × DOM da AUD (#601)

A função `faq_aud_receipt_binding.inspect_faq_receipt_aud_binding` recebe
**uma AUD local existente e um recibo externo já assinado**; não cria o recibo
nem coleta páginas. A validação (i) autentica HMAC por chave/permissão de
coletor fornecidas por fora da AUD; (ii) exige identidade única do snapshot
`audit_id/page_id/snapshot_id/URL solicitada/URL final/device` em SQLite
imutável e estável; (iii) compara **os mesmos bytes UTF-8** do DOM anterior
assinado com o arquivo `rendered_artifact_ref` persistido; (iv) recusa
identidade duplicada, URL/dispositivo divergentes, snapshot legado sem
campos, arquivo ausente, symlink e SQLite com WAL/SHM/journal.

Resultado de sucesso: `SIGNED_RECEIPT_MATCHES_PERSISTED_AUD_DOM_BYTES`.
Significa **somente identidade dos bytes anteriores e da URL da captura
assinada**, não que o coletor executou no mesmo browser/contexto/tempo da
AUD. O recibo v1 não assina ID da AUD/snapshot/device nem traz âncora
externa da cadeia histórica de artefatos; esses escopos continuam
`same_aud_sample_verified=false`,
`same_browser_session_verified=false` e
`persisted_aud_artifact_independently_attested=false`.

Sem consentimento para coleta nova, não há interação real a executar.
A integração é estritamente consultiva: nenhum score, BR-GEO-039/049,
motor, AUD ou reporte anterior é modificado. Mudança normativa continua
dependendo de ADR e aprovação explícita; resultado N/D permanece correto
quando o vínculo físico for impossível.

## Referência para decisão normativa segregada - #651

A observação do DOM continua somente consultiva. A política de
status, fatores e pesos de BR-GEO-039/049 depende da decisão formal
na proposta [ADR_FAQ_NORMATIVE_SEMANTICS.md](ADR_FAQ_NORMATIVE_SEMANTICS.md).
A referência não autoriza mudar SCORE-GEO-005 nem reprocessar
AUDs anteriores e não elimina a prova física independente de #652.
