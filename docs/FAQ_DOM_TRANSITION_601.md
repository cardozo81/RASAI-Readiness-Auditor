# FAQ: evidência sem clique versus dois DOMs (issue #601)

O diagnóstico da captura inicial `faq_observation_601` mede somente o DOM persistido e seus controles de acordeão, rejeitando ambiguidades de `aria-expanded` e IDs duplicados.

`faq_transition_policy_601.compare_faq_dom_views` compara duas representações HTML já disponíveis, desde que identifiquem o mesmo URL e o mesmo alvo FAQ. Quando a primeira captura contém controle recolhido e a segunda expõe o controle expandido, a função sinaliza:

- `TEXT_PRESENT_IN_LATER_DOM_NOT_CLICK_PROOF`: texto encontrado no DOM posterior, não na prova de interação.
- `LATER_DOM_WITHOUT_RECOVERABLE_TEXT`: mesmo com controle expandido, texto recuperável não foi demonstrado.

Não se faz qualquer chamada a navegador, site, API, formulário, serviço de IA ou mecanismo de busca. A função **não autentica** que uma pessoa ou um agente clicou no controle, não prova descoberta pelo Googlebot e não comprova ausência de resposta editorial. Os campos `action_or_click_verified`, `crawler_discovery_verified`, `editorial_answer_absence_proven` e `score_change_authorized` permanecem **false**. Capturas com URLs diferentes ou DOM ambíguo levam à abstenção.

## Gate não atendido

Uma futura coleta pós-interação só será aceita com intenção/opt-in específica, alvo de FAQ autorizado e verificado, orçamento de ações e tempo, isolamento da captura canônica, proibição de formulários/credenciais/compra, hashes das duas observações, horários e fonte de replay auditável. A existência de um segundo HTML por si só não é atestado dessa cadeia. Não se alteram BR-GEO-039/049, SCORE-GEO ou SARI até contrato versionado e testes físicos, incluindo casos SPA de lazy mount.

A implementação presente é um contrato interpretativo read-only com testes de cross-URL, ID duplicado, resposta DOM e ausência de resposta. Ela não fecha a issue #601.
