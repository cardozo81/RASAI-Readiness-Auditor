#322 - Piloto A/B fisico Synthetic User Experience Apdex em Chromium (ambiente local)

Este gate executa cinco pares reais controle/sonda sobre uma SPA servida por
`ThreadingHTTPServer` exclusivamente em `127.0.0.1`, sob Chromium do runner.
Amostras usam o gateway Playwright Synthetic User Experience Apdex efetivo, perfil/device iguais,
mesmo contexto metodologico e callback opt-in na mesma page da medicao;
a selecao de ordem alterna A/B e B/A. O resultado mede delta de LOAD, custo
ativo adicional do probe e readout do avaliador ja existente.

**Limites:** sem acesso a sites publicos, consultas comerciais ou providers;
sem AUD real, integridade de SQLite selado, sidecar de producao, amostra de
trafego real ou identidade fisica comprovada contra persistencia Synthetic User Experience Apdex.
`_persisted_sample` testa o caminho real de conversao, sem gravar SQLite.
Logo o piloto local e verdadeiro para navegador/observador, mas nao constitui
homologacao final de producao. O contrato continuara sinalizando
`gateway_identity_attested=false` e
`m25_production_activation_approved=false` mesmo com cinco pares.

O exemplo `--budget-ms 30` e mantido exclusivamente como comparacao
diagnostica, **nao** como orcamento aprovado pelo operador. O teste nao
reprova por diferenca natural de desempenho contra esse valor. Nao modificar
Apdex, Synthetic Navigation Apdex/Synthetic User Experience Apdex, scores, AUD, URL externa ou consentimento comercial com
base nesta medicao. Prova fisica do runner e JSON resumido ficam no log do
workflow focal `Primary content readiness physical browser pilot 322`;
os jobs deterministas ja validados nao precisam ser invocados a parte.

Para aceite integral #322 ainda e necessario estabelecer, com autorizacao
operacional propria, ambiente/URL/perfil representativos, budget e prova de
persistencia/sidecar na AUD fisica com as mesmas amostras de gateway.
