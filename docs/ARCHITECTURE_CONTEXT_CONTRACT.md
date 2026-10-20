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

## Integração com o registro canônico da auditoria (adaptador)

O adaptador `architecture_choice_audit_adapter.py` inclui a escolha de forma
opcional no mesmo objeto de configuração que recebe a assinatura SHA-256
já utilizada pelo RASAi. Não cria tabela paralela nem modifica o registro de
uma auditoria existente. Ausência da escolha mantém o JSON e o hash originais;
leitura com hash divergente é recusada. A ativação na execução real ainda
exige conexão explícita com o ponto de captura do estado e testes ponta a ponta.

## Caminho de execução opcional

`configuration_context` aceita agora `architecture_choice` opcional e somente
validado. Uma escolha explícita percorre o transporte seguro de configuração
para o subprocesso e o registro canônico da auditoria, protegido pela mesma
assinatura da configuração. Sem este argumento, o conteúdo anterior é mantido
sem campos adicionais. A interface de configuração do operador ainda não
oferece essa escolha: nenhuma ativação implícita foi realizada. A observação
da arquitetura segue independente da preferência e das pontuações.

## Diagnóstico independente de arquitetura no console

A opção 8 do menu principal é separada da seleção de arquitetura para a AUD.
O controlador `console_architecture_discovery.py` utiliza URL e dispositivo da
sessão e chama `architecture_probe.probe_architecture`, que delega toda a
classificação a `architecture_discovery.assess_architecture`, a mesma função
consumida pelo módulo de diagnóstico JavaScript da auditoria e pelo caminho de reprocessamento. O diagnóstico
não gera AUD, não processa CAT, não altera índices e não propaga AUTO/DECLARED.

A aquisição leve usa somente HTTP público com limites de requisição e
tamanho, e navegador Chromium com bloqueios para origens diferentes e
destinos não públicos. **Limitação de segurança:** validar DNS antes da
requisição não equivale a uma política de egress com IP fixado, portanto
cenários com DNS rebinding exigem restrição adicional na rede/proxy antes da
homologação de segurança para ambientes hostis. A evidência de testes offline
não substitui smoke com navegador e destino reais; ausência de prova física
resulta em `UNKNOWN`, não em arquitetura inferida.

### Segurança da captura prévia

A sondagem física externa fica **desabilitada por padrão** quando o ambiente não
indica a existência de controle de saída de rede. A variável de implantação
`RASAI_ARCH_PROBE_EGRESS_GUARDED=1` libera a tentativa somente para ambientes
com bloqueio de destinos internos/privados também **na camada de rede**; declarar
a variável sem realmente configurar esse bloqueio não é uma garantia de segurança.
Sem essa condição, o diagnóstico retorna inconclusivo sem abrir conexão. O
operador não deve precisar configurar essa variável para usar o restante do
RASAi. É uma medida de proteção até existir transporte com destino fixado e
verificação de rede comprovada. Nenhum serviço pago é habilitado por esse sinal.

### Separação de garantias entre HTTP e Chromium

O transporte HTTP bruto da descoberta independente utiliza o mesmo componente
de saída pública com **endereço IP de conexão fixado após validação**, sem
redirecionamentos, e mantém a validação de certificado/SNI do hostname original.
Essa garantia aplica-se à captura HTTP, **não** a toda a navegação Chromium.

O navegador agora instala roteamento HTTP no contexto **antes de criar páginas**, alcançando também a primeira requisição de popups; operações HTTP diferentes de GET são negadas. WebSockets são fechados via `route_web_socket` antes de abrir conexão. Isso melhora o bloqueio na aplicação, **mas não prova isolamento de DNS, redirects internos ou WebRTC**, e a guarda de rede externa permanece obrigatória.

O navegador usa limite de requisições, bloqueio de destinos não públicos e de
origens diferentes, impede service workers e aguarda a estabilização da
renderização por um intervalo limitado. Essas medidas não comprovam, sozinhas,
proteção contra troca de DNS após a verificação. Portanto a navegação física
continua condicionada a uma política efetiva e externa de saída de rede, além
da indicação de sua existência. Sem esse ambiente, o diagnóstico retorna
inconclusivo e não realiza consulta externa. Testes de contrato não substituem
captura real em ambiente protegido.

### Proveniência de bytes na prévia renderizada

Para evitar reconsulta direta por DNS/HTTP do Chromium, a opção 8 usa
`BrowserContext.route` e entrega os corpos de respostas HTTP do transporte
público fixado por IP via `route.fulfill`. O HTML de navegação é a própria
captura RAW inicial (mesmo snapshot); recursos adicionais têm limite agregado.
Respostas com redirects, identidade final divergente, MIME ausente ou erro
abstêm, sem fallback para tráfego nativo. A prevenção de DNS rebinding via
replay HTTP **não** certifica ausência de WebRTC/outro egress Chromium.

### Transparência da escolha no console

O menu de preparação exibe a opção arquitetural **atual da sessão**, sem
confundi-la com a observação física. O estado sem escolha explícita aparece como
"NÃO SELECIONADA", `UNFORCED` como "SEM FORÇAR", `AUTO` depende de evidência
e consumidor autorizado, e `DECLARED` mostra a classe acompanhada de
"informada, não descoberta". A apresentação não altera INI, scores, coleta,
snapshot nem dá autorização a consumidores adicionais.

## Matriz de política consultiva e identidade - gate complementar

`tests/test_architecture_context_policy_matrix.py` percorre a matriz
`AUTO / DECLARED / UNFORCED` × cinco arquiteturas observáveis
× fases `PRE_COLLECTION / POST_COLLECTION` × consumidor
descritivo autorizado ou índice não autorizado × dispositivos
`mobile / desktop`. Em todos os casos, a proveniência
`audit_id / page_id / requested_url / final_url / device / snapshot_id`
é mantida, e consumidores fora da allowlist **nunca** recebem
`effective_architecture`. Observações `UNKNOWN`, conflitantes,
duplicadas ou referentes a outro escopo não são promovidas à
descoberta automática. A escolha declarada é identificada como
`USER_DECLARED`, não como evidência observada.

Em `tests/test_m6_javascript_spa.py`, o caso existente de AUD sintética
agora inclui um *spy* que comprova chamada real de
`m6.execute_m6 -> assess_architecture` com os próprios bytes RAW/DOM
da captura. O pipeline de reprocessamento já compartilha
`m6.execute_m6_snapshot_scope`. A opção 8 conserva o
`architecture_probe.probe_architecture -> assess_architecture`
canônico, sem gravar AUD.

**Limite metodológico do F3:** estas provas **não** aprovam alterar
SARI, SCORE-GEO, Apdex, execução sintética, thresholds nem novos consumidores
de IA. A matriz é contratual e read-only; apenas a apresentação
descritiva das observações arquiteturais existentes nos relatórios é autorizada no
contrato atual. A promoção a consumidor operacional exige ADR e
aprovação metodológica específicos antes de alterar execução/score.

## Transparência aditiva da escolha selada na página de rastreamento

A projeção descritiva da arquitetura pode exibir, além da classificação observacional
já existente, a **seleção da própria AUD** quando ela foi congelada em
`audit_execution_configurations` com hash canônico verificável. O adaptador
`m24_reporting._read_report_architecture_choice` lê a escolha com
`read_sealed_audit_choice`; não lê a opção atual de outra sessão, não grava
no banco, não altera HTML preexistente e não habilita nenhum consumidor de
pontuação. `DECLARED` é identificada como informação do operador; o
relatório indica divergência quando for diferente da observação física conhecida.
`AUTO` e `UNFORCED` aparecem como seleção, **não como arquitetura medida**.

AUD legada, sem escolha explícita, mantém a indicação anterior N/D. Config
com hash inválido não fornece uma escolha inferida e recebe aviso
"não verificável". Os testes verificam as duas condições, o conteúdo
HTML original, tratamento de discrepância e bytes de SQLite imutáveis.

Isso é **transparência consultiva de F2 no consumidor descritivo já existente**,
não propagação operacional F3 a índices, coletores, APDEX ou IA. A aprovação
metodológica desses demais consumidores continua separada.

## Bloqueio canônico de ampliação da allowlist por consumidor

A resolução de contexto exige **duas condições** para liberar um uso
estritamente descritivo: o identificador está no conjunto fixo
`APPROVED_ADVISORY_CONSUMERS` do módulo `architecture_context` **e**
o chamador o incluiu na sua lista local (que apenas restringe permissões).
O conjunto fixo contém somente `descriptive_report` e
`m6_read_only_diagnostic`. Identificadores de índices, escore, Apdex,
coleta, navegação sintética e recomendações de IA continuam `INAPPLICABLE`,
mesmo que o chamador tente incluí-los em `advisory_consumers`.

Esta proteção reduz o risco de uma integração F3 ser ativada por
parametrização local sem revisão. O teste simula a autoautorização
de dez consumidores não aprovados em AUTO/DECLARED/UNFORCED e
comprova a abstenção antes de qualquer efeito de execução. Mudança
futura nesse conjunto exige ADR, contrato versionado, teste de
paridade histórica e autorização metodológica explícita.

**Estado atual de F3:** os únicos consumidores liberados são de
apresentação/diagnóstico; nenhum índice, collector, Apdex ou IA é
liberado. Isto constitui uma política executável de **não propagação**,
não uma alegação de aprovação metodológica de propagação operacional.


## Leitura unificada da proveniência M6 — gate #646

A ponte `architecture_observation_reader.observed_architecture_for_snapshot`
usa o leitor canônico `architecture_m6_evidence.read_audit_architecture_observations`,
não mais SQL classificatório independente. Exige `AUD-*/audit.db` e identidade
exata de URL pedida/final, dispositivo, página e snapshot. O leitor histórico
rejeita SQLite ativo com WAL/SHM/journal, usa leitura `immutable=1` e
confere a identidade física/mtime do banco antes e depois da inspeção.
Vínculos SHA-256 e Ed25519 continuam sujeitos ao mesmo gate; com âncora
pública configurada, remover metadados/assinatura não promove arquitetura.
Ausência de evidência produz `UNKNOWN` consultivo, nunca herança
operacional de perfil ou mudança de índice. Não existe novo coletor nem
mudança em score, M23/M25 ou AUD persistida.
