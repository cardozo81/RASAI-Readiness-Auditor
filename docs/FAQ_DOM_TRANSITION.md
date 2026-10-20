# FAQ: evidência sem clique versus dois DOMs (issue #601)

O diagnóstico da captura inicial `faq_observation` mede somente o DOM persistido e seus controles de acordeão, rejeitando ambiguidades de `aria-expanded` e IDs duplicados.

`faq_transition_policy.compare_faq_dom_views` compara duas representações HTML já disponíveis, desde que identifiquem o mesmo URL e o mesmo alvo FAQ. Quando a primeira captura contém controle recolhido e a segunda expõe o controle expandido, a função sinaliza:

- `TEXT_PRESENT_IN_LATER_DOM_NOT_CLICK_PROOF`: texto encontrado no DOM posterior, não na prova de interação.
- `LATER_DOM_WITHOUT_RECOVERABLE_TEXT`: mesmo com controle expandido, texto recuperável não foi demonstrado.

Não se faz qualquer chamada a navegador, site, API, formulário, serviço de IA ou mecanismo de busca. A função **não autentica** que uma pessoa ou um agente clicou no controle, não prova descoberta pelo Googlebot e não comprova ausência de resposta editorial. Os campos `action_or_click_verified`, `crawler_discovery_verified`, `editorial_answer_absence_proven` e `score_change_authorized` permanecem **false**. Capturas com URLs diferentes ou DOM ambíguo levam à abstenção.

## Gate não atendido

Uma futura coleta pós-interação só será aceita com intenção/opt-in específica, alvo de FAQ autorizado e verificado, orçamento de ações e tempo, isolamento da captura canônica, proibição de formulários/credenciais/compra, hashes das duas observações, horários e fonte de replay auditável. A existência de um segundo HTML por si só não é atestado dessa cadeia. Não se alteram BR-GEO-039/049, SCORE-GEO ou SARI até contrato versionado e testes físicos, incluindo casos SPA de lazy mount.

A implementação presente é um contrato interpretativo read-only com testes de cross-URL, ID duplicado, resposta DOM e ausência de resposta. Ela não fecha a issue #601.


## Recibo independente de ação FAQ (sem execução de navegador)

`faq_interaction_receipt.verify_faq_interaction_receipt` valida um recibo HMAC-SHA256 gerado por coletor isolado confiável e previamente autorizado. A chave de verificação (mínimo 32 bytes), IDs permitidos de coletores e o MAC chegam **fora da página auditada**. O recibo assinado deve ligar alvo `aria-controls`, URL única, hashes SHA-256 dos dois DOMs, instantes UTC antes/depois (janela máxima de 30 segundos), opt-in específico, interação em contexto isolado sem autenticação e bloqueio de rede após carregamento. Alteração de qualquer campo, fonte não reconhecida, ausência de opt-in, atraso, URL divergente ou DOM adulterado invalida o atestado.

Após a verificação, o classificador read-only compara os estados visíveis no DOM e informa `text_recoverable_after_action` ou ausência **no DOM posterior**. O resultado `ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION` é **atestado pelo coletor**, não validação humana, certificação de acessibilidade, disponibilidade a crawlers ou autorização para alterar SCORE-GEO. Se o painel se expande mas não materializa resposta, isso **não prova ausência editorial**. O módulo não clica, não navega, não lê cookies e não realiza requests: uma futura integração Playwright só poderá assinar recibos após cumprir isolamento e bloqueios prometidos.

#601 continua aberta para a implementação/homologação do coletor Playwright opt-in, replay de gesto físico, matriz SPA/lazy mount e decisão de scoring versionada.


## Piloto Playwright de pagina existente (isolado e sem atestado)

`faq_existing_page_pilot.inspect_existing_page_faq` recebe uma pagina
Playwright **ja carregada** pelo chamador. Exige opt-in afirmativo e
reconhecimento do isolamento, um unico tab no contexto e nenhum service
worker em execucao. So seleciona um `button[aria-controls]` com
identidade unica, fechado antes do gesto; aborta novas requisicoes HTTP
durante o clique e reavalia DOM e URL no **mesmo objeto page**. Mudanca
de URL, popup, controles ambiguos ou DOM excessivo produzem abstencao.

O piloto nao abre navegador, nao navega, nao usa provedor de IA, nao
escreve AUD e nao altera scores. O output devolve hashes dos DOMs,
estados de antes/depois e limitacoes, **nunca o HTML bruto**. A rota de
bloqueio e removida ao sair. Este isolamento local nao comprova ausencia
de trafego WebSocket, uma sessao produtiva de mesma amostra nem coleta
por crawler. O piloto nao assina recibos e nao promove sua observacao
a atestado de coletor independente.

`tests/test_faq_existing_page_pilot.py` executa um navegador Chrome
real de runner contra um documento de fixture interceptado localmente:
opt-out preserva DOM, opt-in revela resposta apos clique, URL nao muda
e nenhum destino externo e acessado. A suite integra o workflow de
piloto fisico isolado. Essa prova offline nao equivale a teste do
website-alvo ou homologacao de acessibilidade.


## Ampliação funcional do relatório CAT-03 - estados de DOM (#601, 19/10)

A leitura da captura canônica distingue agora controles recolhidos com texto
montado, recolhidos sem painel, expandidos com texto, expandidos sem texto e
expandidos sem painel montado, preservando ambiguidades. O painel consultivo
exibe **dois resultados de natureza distinta**: texto recuperável no DOM
sem interação e disponibilidade depois de um clique. Sem recibo independente
de interação na amostra física, a segunda coluna permanece N/D.

A indicação de "expandido" descreve atributo aria-expanded da captura,
sem inferir que ocorreu clique, que o humano viu a resposta, ou que um
crawler consegue indexá-la. HTML escondido mas montado demonstra apenas
texto no DOM daquele snapshot. Ausência de um target aria-controls não
prova inexistência editorial. Nenhuma regra BR-GEO-039/049, score SARI,
SCORE-GEO, auditoria histórica ou motor de captura é alterado.

Fixtures de leitura de DOM e SQLite real cobrem a matriz dos quatro estados,
escopo por AUD e bytes inalterados de banco e HTML.

## Handoff experimental para a MESMA página física (#652)

O adaptador `faq_existing_page_pilot.inspect_existing_page_faq` aceita
`expected_before_sha256` para exigir que o HTML imediatamente antes
do clique seja **byte a byte** o mesmo DOM já capturado pela captura canônica.
Quando a origem não coincide, recusa o clique com
`CAPTURED_AUD_DOM_DOES_NOT_MATCH_LIVE_PAGE`. Isto impede reabrir uma
URL em outro navegador e declarar a mesma amostra por similaridade.

O capturador `device_context_capture` mantém um seam de callback
`_rasai_optin_faq_observer` na **página captura canônica viva, depois da captura
canônica e antes do fechamento**; por padrão nenhum callback existe,
nenhum clique ocorre e os relatórios históricos permanecem idênticos.
A única projeção no metadata, quando injetada por um coletor confiável,
contém status e hashes, não HTML nem segredo. Um callback sem prova
independente ainda informa `same_aud_sample_verified=false`.

`rasai.same_sample_observation.observe_same_browser_sample` faz a
operação real opt-in no mesmo objeto Playwright `page`: medição
seletiva de prontidão antes do clique, controle de página única,
verificação do SHA-256 congelado, ação FAQ restrita sem navegação,
recibo HMAC do coletor autorizado e associação explícita de
`audit_id/page_id/snapshot_id/sample_id/context_id/device`. O recibo
não declara prova de crawler. A verificação cruzada de uma AUD selada
continua no contrato `faq_aud_receipt_binding`; o recibo local **não
atesta independentemente** que a captura foi a amostra captura canônica histórica.

O coletor principal não ativa esse fluxo automaticamente. Para a prova
real será necessário um chamador controlado que mantenha a página captura canônica
aberta, instale o opt-in com consentimento por URL/alvo, utilize uma
AUD temporária e comprove a ancoragem da captura no audit.db. Não
habilitar navegação pública de Chromium sem isolamento de rede físico
comprovado; o route abort da ação não contém WebRTC/egress nativo.
