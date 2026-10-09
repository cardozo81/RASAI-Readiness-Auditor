# #358 - Contrato determinístico de orientação CAT-07 por arquitetura

A função `resolve_experience_architecture_guidance` em
`src/rasai/experience_architecture_guidance_358.py` é uma camada
**somente de interpretação**, sem escrita em AUD, mudança de Apdex M25,
nova configuração efetiva, XHR/Custom Action ou chamada comercial.

Ela recebe configuração efetiva fornecida explicitamente, arquitetura
informada pelo operador, arquitetura observada pelo M6 somente quando
há `snapshot_id/page_id/device`, origem por campo, modo de perfil e
objetivo do usuário (somente carregamento inicial ou experiência ampla).
Responde separando:
- `OPERATOR_DECLARED`, `M6_OBSERVED` e `UNKNOWN`;
- `CUSTOM`, `DYNATRACE_IMPORTED` e `DYNATRACE_GUIDED`;
- KPM/thresholds efetivos de valores **propostos**;
- `ADEQUADA_AO_ESCOPO`, `COBERTURA_PARCIAL`,
  `REVISAO_RECOMENDADA` e `INDETERMINADA`;
- ações `RASAI_EXECUTABLE_NOW`, `DYNATRACE_EXTERNAL` e
  `FUTURE_CAPABILITY` com suas restrições.

O perfil guiado propõe apenas 3 variáveis que já existem no CLI M25:
`RASAI_APDEX_EXPERIENCE_KPM=USER_ACTION_DURATION`,
`RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS=3.0`,
`RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS=12.0`.
São baseline **já documentado e executável pelo RASAi**, não
thresholds oficiais universais do Dynatrace por arquitetura.
O módulo não chama `os.environ`, não altera o INI nem grava esses
valores; todo valor proposto exige confirmação explícita antes de
uma futura alteração nas configurações. Custom nunca é sobrescrito;
Imported mantém os campos fornecidos e não executa parser/provider.

O seletor M6 é posterior à captura, portanto a classificação
observada não reconfigura a auditoria que a produziu. Divergência
entre arquitetura declarada e observada gera revisão e preservação
da origem, não recalcula satisfação ou duração. Para SPA, hidratação
e arquitetura mista, Load Action pode ser adequada ao objetivo
restrito de entrada inicial; se o objetivo for jornada completa, a
cobertura é parcial e requer ação externa de XHR/soft navigation,
sem insinuar que M25 execute esse tipo de coleta. Medição física
de prontidão de conteúdo aguarda #322 e jamais é inferida de Load.

Os valores efetivos fornecidos ao resolvedor precisam provir de
snapshot congelado de AUD ou de configuração de preflight real.
Não há leitura autônoma de arquivos/tenant dentro do resolvedor.
Sem evidência, `N/D`; o ID de snapshot não comprova sozinho
relação com uma navegação real ou confiabilidade do producer.

## Integração aditiva no console e CAT-07 (ciclo PR de #358)

CAT-07 Experience e CAT-06 Navigation são selecionáveis de modo independente;
desabilitar Navigation não bloqueia a edição de Experience Apdex.\n\nO console agora oferece dois eixos de prévia: arquitetura declarada
(AUTO/SSR/CSR_SPA/HYDRATED/MIXED/UNKNOWN) e calibração
(CUSTOM/DYNATRACE_GUIDED/DYNATRACE_IMPORTED). Esses dois campos são
metadados não executores no `State`, no INI e no registro de variáveis
do menu "6. Todas as configurações". O modo Guided só altera três
valores de Load já suportados após confirmação explícita. Custom
mantém KPM e thresholds do usuário; Imported preserva o parser e
a credencial/arquivo existente. A operação de cancelamento ou erro
restaura também essas opções e os campos da edição em andamento.

A seção CAT-07 recebe um *advisory read-only* que consulta
exclusivamente a `audit.db` da AUD em apresentação: configuração
M25 persistida e classificação M6 vinculada a `page_id/snapshot_id`.
Se existir múltipla arquitetura por capturas, ausência de amostra,
configuração antiga sem snapshot ou modo não congelado no momento
da auditoria, declara N/D. Os dados atuais do console ou INI da
máquina **nunca** são adotados retroativamente para relatórios
históricos. Não modifica contagens, fronteiras, fórmulas, scores,
evidências ou manifests dos motores homologados.

**Proveniência histórica do modo:** o snapshot canônico de configuração
já implementado em `audit_configuration_reuse_console._export_settings`
serializa a seção INI `settings.synthetic_apdex_experience` no handoff
filho de cada **nova** AUD, antes da finalização e do registro de
hash `audit_execution_configurations`. A projeção CAT-07 agora lê
`architecture` e `profile_mode` desse snapshot apenas quando o
hash persistido é exatamente igual ao hash recalculado pelo contrato
canônico. Se nenhum snapshot existir, for histórico ou tiver hash
inconsistente, o modo fica N/D. O relatório não lê o INI de outra
auditoria nem altera os hashes/configurações de execuções existentes.
Testes de contrato cobrem presença e abstenção do modo congelado.

Fontes do contrato RUM, diferentes do RASAi Synthetic Apdex:
https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/additional-configuration/configure-apdex-web
https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions
https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/initial-setup/configure-dynatrace-real-user-monitoring-to-capture-xhr-actions
