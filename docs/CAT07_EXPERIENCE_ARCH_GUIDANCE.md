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

### Evidência e rastreabilidade no HTML (#358)

A projeção CAT-07 mostra os identificadores `snapshot_id`, `page_id` e
`device` **apenas** quando a AUD contém uma única classificação M6
inequívoca vinculada à mesma AUD. Em capturas múltiplas, dados antigos ou
evidência incompleta, o relatório usa `N/D`, sem atribuir a arquitetura
de uma página a outras rotas ou dispositivos. Os valores são escapados no
HTML e a origem é sempre a base `audit.db` aberta em modo somente leitura.

A mesma seção informa a versão do contrato determinístico, a Task Load
efetivamente medida e a explicação em português dos motivos estruturados
do diagnóstico. A explicação **não** transforma recomendações em
configuração executada, não interpreta KPMs RUM/Synthetic Browser como
medições M25 e não modifica o hash, o score ou as evidências originais.
A regressão focalizada cobre rastreabilidade, HTML escaping,
abstenção multicontexto e rematerialização determinística sem escrita.

Fontes do contrato RUM, diferentes do RASAi Synthetic Apdex:
https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/additional-configuration/configure-apdex-web
https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions
https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/initial-setup/configure-dynatrace-real-user-monitoring-to-capture-xhr-actions

## Política efetiva de erros e execução (incremento de evidência #358)

A seção CAT-07 passou a exibir os flags persistidos de captura e impacto
de erros (JavaScript, requisição, console, XHR/Fetch), escopo de erro,
modo de sessão, volume de amostras, limite de tentativas, concorrência,
intervalo e settle. Todos são projetados **somente** do
`synthetic_ux_apdex_runs.configuration` da AUD corrente, em allowlist
explícita. Ausência e campos inválidos em AUDs de versões anteriores produzem `N/D`; o relatório
não reconsulta INI/env nem infere defaults Dynatrace ou RASAi.

A interpretação preserva a fronteira temporal: `settle_seconds` é
observação e não tempo adicionado ao índice; ter XHR/Fetch capture não
significa executar XHR Action como tarefa separada. URL/token/configuração
Dynatrace e parâmetros fora da allowlist nunca são serializados nesse
advisory. Testes de replay, sigilo e imutabilidade do audit.db por bytes
acompanham os contratos unitários sem chamada ao provider.


## CAT-07: proveniência física antes da interpretação (12/10/2026)

O consumidor HTML da arquitetura **não abre** um `audit.db`
symlinkado ou acompanhado de `-wal`, `-shm`, `-journal`.
Em vez de invalidar toda a materialização de relatório, emite um
bloco CAT-07 N/D explicando que a fonte não é estável. A leitura
usa `mode=ro&immutable=1` e verifica novamente os sidecars após
a consulta física. A duplicação de `page_snapshots.snapshot_id`
entre páginas/AUDs invalida a proveniência da arquitetura individual:
mesmo que um JOIN por `audit_id` encontre uma captura, o identificador
não é rastreável unicamente.

São regras somente da apresentação, sem modificar tabelas, os sensores
M23/M25, thresholds, Dynatrace externo, ou snapshots já persistidos.
Não se cria prova de mesma sessão de RUM, hidratação SPA ou conteúdo
pronto. As fixtures SQLite simulam três journals, aparição concorrente
de WAL e reutilização de ID, preservando bytes da AUD.


## Abstencao em alteracao fisica observavel do SQLite CAT-07 (#358)

O consumer consultivo `cat07_architecture_advice_html` passou a verificar
que `audit.db` pertence a um arquivo regular em diretorio fisico,
sem links simbolicos no arquivo ou em seu ancestral imediato.
Antes de abrir o banco somente leitura, registra os identificadores
`st_dev`, `st_ino`, `st_size` e `st_mtime_ns`; apos finalizar
a leitura por `ro&immutable=1`, exige o mesmo conjunto de metadados
e ausencia de WAL/SHM/journal. Mudanca observavel, origem inexistente
ou substituicao de caminho devolve o bloco CAT-07 explicitamente N/D,
sem conservar arquitetura ou configuracao positiva extraida de uma
possivel fonte mista.

O controle nao altera M23/M25, snapshot, CLI, banco, score ou
coleta. Trata-se de verificacao economica de metadados, **nao**
assinatura criptografica da AUD nem prova de ausencia de escrita
maliciosa com estatisticas preservadas. Testes isolados simulam
drift durante a leitura, fonte inexistente e ancestral com symlink,
sem gravar na fonte historica ou acessar Dynatrace.
