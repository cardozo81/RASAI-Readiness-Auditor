# Execução parcial, disponibilidade externa e fechamento diagnóstico

**Estado do produto:** pré-publicação.  
**Data de referência:** 21/09/2026.

Este documento define o contrato canônico para auditorias, reprocessamentos e consolidações quando IA, APIs ou integrações externas estão indisponíveis, não configuradas, com credencial inválida, sem crédito, com timeout, erro de rede ou outra falha operacional.

O princípio central é separar continuidade operacional de completude diagnóstica sem enfraquecer integridade, dependências ou rastreabilidade.

## 1. Estados independentes

O RASAi distingue formalmente:

- sucesso operacional da execução;
- estado individual de cada integração;
- materialização do relatório;
- integridade dos dados e arquivos;
- completude diagnóstica;
- fechamento integral da AUD;
- elegibilidade integral da AUD;
- utilização limitada de uma AUD íntegra como fonte não conclusiva de CONS.

Uma execução pode terminar e materializar HTML sem que o diagnóstico esteja integralmente fechado:

```text
Pipeline executado                 = concluído
Relatório HTML materializado       = gerado
Dados/evidências válidos           = preservados
Integridade estrutural             = preservada

Completude diagnóstica             = parcial
Fechamento integral                = pendente
consolidation_eligible             = false
Fonte de CONS com limitações       = possível, se íntegra
```

`required=True` continua significando requisito para fechamento. O RASAi não transforma requisito obrigatório em opcional para permitir continuidade.

## 2. Estados de IA

### IA não solicitada

Quando a funcionalidade é opcional e o usuário não solicitou IA, nenhuma chamada é feita e não existe pendência de IA.

### IA necessária para fechamento e sem provider

Quando um catálogo selecionado depende de IA para fechamento integral e o provider está `none`, a execução determinística continua. O work item permanece obrigatório e é projetado como `NOT_CONFIGURED`; nenhuma tentativa de provider, token ou custo é criada.

### IA bloqueada por pré-requisito

Quando a evidência necessária àquela tarefa específica ainda não está válida/persistida, a IA recebe `WAITING_FOR_DATA` com `error_class=PREREQUISITE`. O provider não é chamado.

### IA configurada e tentativa falhou

Timeout, erro de rede, falta de crédito, erro HTTP ou outra falha após uma tentativa permanecem distintos de `NOT_CONFIGURED` e de `WAITING_FOR_DATA`. A tentativa e sua provenance são preservadas.

## 3. Dependências antes da IA

A ordem causal é:

```text
coletas determinísticas
-> integrações/APIs necessárias
-> validação de suficiência da evidência
-> EVIDENCE_SEALED
-> IA
-> derivações finais
-> relatório
```

O gate é por finalidade. Não existe dependência artificial de todas as integrações do RASAi.

Exemplos:

- análise semântica depende de captura/conteúdo/evidência semântica aplicável;
- IA técnica depende das evidências técnicas que interpreta;
- CAT-08 depende do contexto core persistido da URL analisada;
- inteligência competitiva por IA depende da comparação competitiva determinística consolidada;
- GSC ou CrUX não bloqueiam uma IA que não consome esses dados.

## 4. APIs e integrações externas

Uma falha externa não invalida automaticamente toda a AUD. Quando a integração é necessária para um diagnóstico selecionado, o work item permanece pendente, os demais dados válidos são preservados, etapas independentes continuam e o relatório pode ser materializado.

`NO_DATA` continua sendo ausência de dado. Não é convertido em observação, score ou sucesso.

## 5. Relatório da auditoria

A página principal de `report-catalog/` projeta o estado atual das pendências obrigatórias a partir do fulfillment persistido. O informativo separa relatório gerado, integridade estrutural e fechamento diagnóstico.

A tabela identifica fase/CAT, integração, tipo, estado, motivo e necessidade para fechamento. Quando a pendência é resolvida, ela desaparece dessa área principal. Tentativas e falhas históricas continuam na provenance e nos registros técnicos.

A materialização HTML não chama provider nem recolhe APIs.

## 6. Matriz de encerramento estrutural

A Matriz de encerramento estrutural mede controles de configurabilidade, governança, exposição, confiabilidade, integridade e segurança da projeção. Ela não mede disponibilidade de terceiros.

Portanto é possível existir simultaneamente:

```text
Encerramento estrutural = elegível
Fechamento diagnóstico  = pendente
```

Falha externa corretamente detectada, persistida, classificada e exposta não reduz arbitrariamente os percentuais estruturais.

## 7. Reprocessamento RPR

Um `RPR-*` possui política própria e não altera a configuração original da `AUD-*`.

A política pode registrar:

- itens selecionados para o RPR;
- uso ou não de IA autorizado naquele RPR (`use_ai`);
- uso efetivo de IA observado ao final (`ai_used`);
- provider, modelo e reasoning não secretos aplicáveis ao RPR.

O usuário escolhe quais pendências deseja reprocessar. Pendências existentes na AUD e itens autorizados no RPR são conjuntos diferentes.

`use_ai=false` impede chamadas de IA naquele RPR. `use_ai=true` permite que uma AUD originalmente criada sem IA utilize IA no RPR, sem reescrever a configuração original.

Quando uma integração e uma IA dependente são selecionadas no mesmo RPR, a integração executa primeiro. A IA só é liberada se seu pré-requisito específico ficar suficiente.

## 8. Resultado do RPR

O sucesso operacional do RPR é separado do fechamento da AUD.

```text
Execução do RPR      : CONCLUÍDA
Selecionados         : 3
Resolvidos           : 2
Não resolvidos       : 1
Não selecionados     : 4
Relatório atualizado : sim
Diagnóstico integral : não
```

Uma integração continuar indisponível não transforma automaticamente todo o RPR em falha operacional. Falhas internas que impedem o runtime de terminar continuam sendo falhas operacionais reais.

## 9. SaaS

Os jobs `AUDIT`, `AUDIT_REPROCESS` e CONS seguem a mesma semântica do console.

`AUDIT_REPROCESS` admite, de forma compatível, `selected_items`, `use_ai`, `ai_provider`, `ai_model` e `ai_reasoning`. Esses campos pertencem ao RPR e não substituem a configuração da AUD de origem. O registro durável do RPR também materializa `ai_used` após a execução. Segredos continuam fora do payload durável.

## 10. Consolidado

O CONS é read-only em relação às AUDs fonte e não recolhe APIs.

A consolidação determinística pode ser materializada com IA não solicitada, IA solicitada sem provider ou provider configurado que falhou. Os estados da camada longitudinal permanecem distintos:

```text
NOT_REQUESTED  = IA não solicitada
NOT_CONFIGURED = IA solicitada sem provider configurado/apto
UNAVAILABLE    = provider configurado, mas execução não concluiu
COMPLETE       = camada longitudinal de IA concluída
```

## 11. AUD parcial como fonte de CONS

`consolidation_eligible=true` continua reservado ao fechamento integral.

Separadamente, uma AUD pode ser utilizada como fonte não conclusiva quando está fisicamente concluída, o SQLite é íntegro, o fulfillment não está em `FAILED_FATAL` e as pendências obrigatórias são reprocessáveis, como `NOT_CONFIGURED`, `REQUESTED_NOT_EXECUTED`, `WAITING_FOR_DATA` ou `FAILED_RETRYABLE`.

A leitura dessa decisão usa SQLite em `mode=ro`, `PRAGMA query_only=ON` e `PRAGMA quick_check`. O CONS não cria schema nem altera a AUD.

Uma fonte parcial mantém a série como não conclusiva e orienta reprocessamento da AUD de origem.

## 12. Integridade e provenance

Continuam obrigatórios identidade da AUD/RPR, evidências, snapshots, hashes, manifests, fingerprints, provenance, banco, assurance, artifacts e tentativas de provider.

Nunca é permitido fabricar resultado, converter `NO_DATA` em dado, apagar falha histórica, marcar provider como chamado quando não houve chamada, consumir IA com pré-requisito obrigatório incompleto ou declarar fechamento integral com requisito obrigatório pendente.

## 13. Resumo de estados

| Situação | Execução | HTML | Fulfillment | Fechamento |
| --- | --- | --- | --- | --- |
| IA opcional não solicitada | continua | gera | sem pendência de IA | conforme demais requisitos |
| IA obrigatória para fechamento + `none` | continua | gera | `NOT_CONFIGURED` | pendente |
| pré-requisito da IA incompleto | continua | gera | `WAITING_FOR_DATA` | pendente |
| provider tentou e falhou | continua | gera | falha classificada/reprocessável | pendente quando obrigatório |
| API necessária falhou | continua | gera | falha classificada/reprocessável | pendente |
| tudo obrigatório concluído | conclui | gera | `SUCCESS`/aplicável | integral |

Este contrato complementa `AI_FAILURE_FULFILLMENT_CONTRACT.md`, `GOVERNED_EVIDENCE_AI_PIPELINE.md`, `AUDIT_REPROCESSING.md`, `REPORT_CATALOG_TRUST.md` e `CONSOLIDATED_REPORTING.md`.
