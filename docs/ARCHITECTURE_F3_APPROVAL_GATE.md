# Aprovação metodológica: contexto arquitetural consultivo

**Decisão aprovada pelo responsável do projeto:** o contexto arquitetural
pode alimentar exclusivamente diagnósticos e relatórios descritivos, sem
alterar índices, coleta, pontuação, coortes ou fórmulas.

## Consumidores liberados
- `descriptive_report`: descrição consultiva baseada em evidência elegível.
- `m6_read_only_diagnostic`: inspeção de evidências e limitações.

A identidade física deve corresponder à URL solicitada e final,
dispositivo, página e snapshot. Declaração do usuário não é uma observação
física. Seleção não implica permissão de execução de qualquer integração.

## Superfícies não autorizadas
SARI, SCORE-GEO, Apdex, métricas, coletores, parâmetros de auditoria,
coortes e outros motores protegidos permanecem invariáveis. Qualquer
mudança de método exigirá nova ADR individual, owner, golden/parity,
versão de contrato, rollback e autorização explícita.

## Assinatura de evidência
A estratégia Ed25519 foi aprovada. Uma chave privada gerenciada pelo
operador, fora de INI e repositório, assina o par de hashes RAW/rendered
e a identidade física do snapshot. A verificação exige uma chave pública
fornecida de forma independente pelo operador. Alteração no artefato,
identidade ou chave de confiança faz a evidência assinada falhar fechada.
Sem chave configurada, o processamento dos demais catálogos continua.

Configurações optativas: `RASAI_ARCHITECTURE_SIGNING_KEY_FILE`
e `RASAI_ARCHITECTURE_VERIFY_KEY_FILE`. Não incluir os arquivos PEM no
repositório, INI ou workspace AUD. Chaves de confiança antigas devem
continuar disponíveis quando políticas de rotação determinarem validação
de capturas assinadas anteriormente.

## Limite
A autenticação é relativa à chave pública que o operador confia.
Capturas anteriores à habilitação permanecem sem assinatura, sem
elevação retroativa. Nenhum ajuste de score decorre dessa decisão.

## ADR-F3-OPER-001 v1 - Veto a novos consumidores operacionais nesta versão (20/10/2026)

**Estado: APROVADA - VETO FORMAL DE AMPLIAÇÃO.**
**Responsável pela decisão:** operador/proprietário do projeto RASAi.
**Registro da aprovação:** autorização humana expressa `prossiga. tudo autorizado`,
respondendo à proposta de veto formal da issue #654 na conversa do projeto
de 20/10/2026. A matriz deliberativa foi registrada na própria issue
antes da aprovação. Este registro documenta o aceite do operador; **não
é assinatura criptográfica nem homologação física**.
**Questão deliberada:** permitir, nesta versão, que o diagnóstico de
arquitetura diagnóstico arquitetural passe a comandar novos consumidores operacionais?
**Decisão:** **NÃO**. Permanecem autorizados somente
`descriptive_report` e `m6_read_only_diagnostic`, já aprovados na #646.
Esta ADR encerra a avaliação de expansão F3 **por veto**, não por
implementação de novos caminhos de execução. Versão da decisão: v1;
contrato de runtime permanece `architecture-context-v1` e inventário
`architecture-consumer-eligibility-v1`.

### Matriz deliberada por consumidor

Os valores de "classe" reproduzem a classificação consultiva do inventário,
sem converter elegibilidade hipotética em autorização para executar. Todos os
consumidores abaixo do segundo permanecem vetados nesta versão.

| Consumidor | Owner funcional | Classe consultiva | Decisão e fundamento |
| --- | --- | --- | --- |
| `descriptive_report` | relatórios técnicos / Relatório | ADVISORY_SAFE | MANTER: fatos descritivos com identidade da evidência. |
| `m6_read_only_diagnostic` | diagnóstico arquitetural / Prévia | ADVISORY_SAFE | MANTER: inspeção local somente leitura. |
| CAT-01 | Dados e recursos | INTERPRETATION_SAFE | VETAR: contrato por catálogo não aprovado. |
| CAT-02 | Aquisição e rastreamento | PRE_COLLECTION_ONLY | VETAR: diagnóstico arquitetural pós-coleta não reabre aquisição. |
| CAT-03 | Conteúdo e FAQ | INTERPRETATION_SAFE | VETAR: interação e método em #652/#651 não homologados. |
| CAT-04 | Lighthouse / CrUX | INAPPLICABLE | VETAR: coortes URL/ORIGIN e campo/lab independentes. |
| CAT-05 | SERP / GEO | INAPPLICABLE | VETAR: proveniência e comparabilidade externa #653 não demonstradas. |
| CAT-06 | Apdex navegação | METHOD_CHANGE_REQUIRES_ADR | VETAR: T/4T, amostras e score protegidos. |
| CAT-07 | Apdex experiência | METHOD_CHANGE_REQUIRES_ADR | VETAR: método de ações/amostragem protegido. |
| CAT-08 | Improvement Intelligence | INTERPRETATION_SAFE | VETAR: nenhum novo contrato de interpretação aprovado. |
| CAT-09 | Remediações | INTERPRETATION_SAFE | VETAR: não converter diagnóstico arquitetural em instrução operacional. |
| CAT-10 | Segurança passiva | INAPPLICABLE | VETAR: evidência HTTP/DOM é independente de diagnóstico arquitetural. |
| SARI | Índice de prontidão | METHOD_CHANGE_REQUIRES_ADR | VETAR: preservação da fórmula/contrato vigentes. |
| SCORE-GEO | Pesos e regras GEO | METHOD_CHANGE_REQUIRES_ADR | VETAR: sem recálculo/versão de método. |
| Synthetic Navigation Apdex | Synthetic Navigation | PRE_COLLECTION_ONLY | VETAR: sem mutar coleta ou thresholds. |
| Synthetic User Experience Apdex | Synthetic User Experience | PRE_COLLECTION_ONLY | VETAR: sem mutar tarefas, perfis ou histórico. |
| IA | Motores atuais de IA | INAPPLICABLE | VETAR: sem chamadas, custos ou roteamento implícito. |
| Dynatrace RUM | Tenant externo | INAPPLICABLE | VETAR: tenant e amostra externa independentes. |
| CONS e demais relatórios operacionais | Consolidação / Reporting | SEM AUTORIZAÇÃO | VETAR: não alterar CONS, comparabilidade, score ou fonte. |

### Efeito vinculante, fase e alternativas rejeitadas

A decisão **não** amplifica `APPROVED_ADVISORY_CONSUMERS`, não habilita
feature gates, não modifica coleta, `page.goto`, thresholds, coortes,
orquestração de IA, parâmetros pré-coleta, SARI, SCORE-GEO, Synthetic Navigation Apdex/Synthetic User Experience Apdex,
Apdex, CONS, hashes, configuração, AUD/RPR ou dados históricos. O
diagnóstico `POST_COLLECTION` pode alimentar apenas os dois consumidores
descritivos; `PRE_COLLECTION` não pode herdar resultados diagnóstico arquitetural ainda não
produzidos. Uma escolha `DECLARED` nunca equivale a prova observacional.

**Alternativa rejeitada A:** liberar diretamente `INTERPRETATION_SAFE`,
pois a classificação no inventário não é contrato validado para novos
consumidores. **Alternativa rejeitada B:** expandir F3 para execução/coleta,
pois diagnóstico arquitetural posterior não tem legitimidade temporal para parametrizar o passado.
**Alternativa rejeitada C:** alterar pesos e indicadores, pois exigiria
decisão normativa individual, calibração, golden/parity, versão e aceites.

### Rastreabilidade e condição de reabertura de proposta

Evidência técnica de compatibilidade: `src/rasai/architecture_context.py`
contém **somente** os dois IDs da allowlist; a função
`architecture_consumer_eligibility()` verifica a correspondência entre
classificação advisory e allowlist. A inspeção é estática, sem teste novo
ou homologação física atribuída a esta ADR. O veto não exige implementar,
migrar nem executar consumidores vetados; por isso não há golden/parity
de caminho operacional novo a executar para concluir **esta decisão**.
Os gates físicos já segregados na #655 permanecem independentes.

Uma proposta futura para cada consumidor exigirá nova autorização explícita,
owner, contrato e versão independentes, origem URL/device/snapshot,
negativas para UNKNOWN/divergência/histórico, opt-in, custo, golden/parity
e migração não destrutiva antes de qualquer mudança funcional. Nenhuma
aprovação retroativa resulta desta decisão.

**Rastreabilidade:** issue #654 (aprovação e matriz por consumidor),
#646 (F1/F2/F3 consultivas), #655 (homologação física independente).
