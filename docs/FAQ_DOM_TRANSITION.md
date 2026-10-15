# FAQ: evidência sem clique versus dois DOMs (issue #601)

O diagnóstico da captura inicial `faq_observation_601` mede somente o DOM persistido e seus controles de acordeão, rejeitando ambiguidades de `aria-expanded` e IDs duplicados.

`faq_transition_policy_601.compare_faq_dom_views` compara duas representações HTML já disponíveis, desde que identifiquem o mesmo URL e o mesmo alvo FAQ. Quando a primeira captura contém controle recolhido e a segunda expõe o controle expandido, a função sinaliza:

- `TEXT_PRESENT_IN_LATER_DOM_NOT_CLICK_PROOF`: texto encontrado no DOM posterior, não na prova de interação.
- `LATER_DOM_WITHOUT_RECOVERABLE_TEXT`: mesmo com controle expandido, texto recuperável não foi demonstrado.

Não se faz qualquer chamada a navegador, site, API, formulário, serviço de IA ou mecanismo de busca. A função **não autentica** que uma pessoa ou um agente clicou no controle, não prova descoberta pelo Googlebot e não comprova ausência de resposta editorial. Os campos `action_or_click_verified`, `crawler_discovery_verified`, `editorial_answer_absence_proven` e `score_change_authorized` permanecem **false**. Capturas com URLs diferentes ou DOM ambíguo levam à abstenção.

## Gate não atendido

Uma futura coleta pós-interação só será aceita com intenção/opt-in específica, alvo de FAQ autorizado e verificado, orçamento de ações e tempo, isolamento da captura canônica, proibição de formulários/credenciais/compra, hashes das duas observações, horários e fonte de replay auditável. A existência de um segundo HTML por si só não é atestado dessa cadeia. Não se alteram BR-GEO-039/049, SCORE-GEO ou SARI até contrato versionado e testes físicos, incluindo casos SPA de lazy mount.

A implementação presente é um contrato interpretativo read-only com testes de cross-URL, ID duplicado, resposta DOM e ausência de resposta. Ela não fecha a issue #601.


## Recibo independente de ação FAQ (sem execução de navegador)

`faq_interaction_receipt_601.verify_faq_interaction_receipt` valida um recibo HMAC-SHA256 gerado por coletor isolado confiável e previamente autorizado. A chave de verificação (mínimo 32 bytes), IDs permitidos de coletores e o MAC chegam **fora da página auditada**. O recibo assinado deve ligar alvo `aria-controls`, URL única, hashes SHA-256 dos dois DOMs, instantes UTC antes/depois (janela máxima de 30 segundos), opt-in específico, interação em contexto isolado sem autenticação e bloqueio de rede após carregamento. Alteração de qualquer campo, fonte não reconhecida, ausência de opt-in, atraso, URL divergente ou DOM adulterado invalida o atestado.

Após a verificação, o classificador read-only compara os estados visíveis no DOM e informa `text_recoverable_after_action` ou ausência **no DOM posterior**. O resultado `ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION` é **atestado pelo coletor**, não validação humana, certificação de acessibilidade, disponibilidade a crawlers ou autorização para alterar SCORE-GEO. Se o painel se expande mas não materializa resposta, isso **não prova ausência editorial**. O módulo não clica, não navega, não lê cookies e não realiza requests: uma futura integração Playwright só poderá assinar recibos após cumprir isolamento e bloqueios prometidos.

#601 continua aberta para a implementação/homologação do coletor Playwright opt-in, replay de gesto físico, matriz SPA/lazy mount e decisão de scoring versionada.
