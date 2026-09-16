# Evidências da execução e integridade da configuração

**Estado:** contrato vigente de desenvolvimento/pré-produção.

## Objetivo

Cada auditoria deve permitir responder, sem depender do estado atual da máquina:

1. qual configuração efetiva foi usada;
2. quais catálogos `CAT-*` foram selecionados;
3. quais capacidades/fontes cada catálogo solicitou;
4. se IA opcional foi autorizada no plano;
5. quais capacidades estavam ou não solicitadas;
6. quais concluíram, falharam ou ficaram pendentes;
7. onde consultar tecnicamente o erro;
8. quais configurações faltaram quando a falha foi de parametrização.

A superfície canônica é:

```text
<AUD-ID>/report/execution-evidence.html
```

## Princípio central

O relatório representa o **contrato efetivo da execução**, não a capacidade máxima do RASAi e não o estado bruto das variáveis da sessão antes da projeção do plano.

Capacidade não solicitada não reduz fulfillment, não transforma o AUD em preliminar e não bloqueia consolidação.

Exemplos:

- `CAT-05` não selecionado = SERP/GSC/observabilidade própria do catálogo `NÃO SOLICITADOS`, mesmo que existam configurações presentes na sessão;
- `CAT-06`/`CAT-07` não selecionados = medições sintéticas `NÃO SOLICITADAS`;
- categoria Lighthouse fora do contrato efetivo = `NÃO SOLICITADO`;
- GSC não solicitado = estado neutro;
- GSC obrigatório sem configuração suficiente = `CONFIGURAÇÃO NECESSÁRIA`;
- serviço solicitado que tentou executar e recebeu erro = `FALHA` ou estado parcial correspondente;
- IA configurada globalmente não implica uso de IA quando o plano selecionado não a autoriza ou não a requer.

## Escopos de configuração

### Configuração persistida do operador

Inclui INI, defaults e configuração persistida no sistema operacional. É propriedade do operador e não é reescrita permanentemente pelo plano de uma AUD.

### Sessão atual e plano da próxima auditoria

A sessão contém valores e parâmetros explícitos do operador. O plano `CAT-*` define quais resultados opcionais pertencem à próxima execução.

Quando o operador usa `Salvar configuração`, valores não sensíveis suportados podem ser persistidos no `rasai-console.ini`, inclusive:

```text
[search_intelligence]
...

[audit_catalog]
selected = CAT-...
ai_enabled = true|false
```

Persistir o plano permite restaurá-lo em outra sessão; não altera AUDs já executadas.

### Projeção da execução

Imediatamente antes de readiness final, custo/preflight e execução, o console projeta temporariamente o plano selecionado sobre as capacidades opcionais conhecidas.

A projeção:

- define o escopo efetivo das capacidades selecionáveis;
- neutraliza temporariamente workloads fora do plano;
- preserva parâmetros da sessão apenas para capacidades incluídas;
- não altera `rasai-defaults.ini`;
- não grava credenciais;
- não deve permanecer como mutação indevida no processo pai depois da execução/projeção.

Collectors determinísticos basais não são desligados por essa camada quando pertencem ao core da auditoria.

## Catálogo efetivo da AUD

A unidade pública de composição é o catálogo `CAT-*`.

O snapshot secret-free persiste:

```text
audit_catalog.version
audit_catalog.selected
audit_catalog.ai_enabled
audit_catalog.items
```

`selected` contém a seleção efetiva da execução, já com dependências canônicas resolvidas. `items` preserva a projeção dos catálogos selecionados necessária para rastreabilidade.

O contrato vigente do console não usa `execution_profile` como unidade pública de composição da próxima auditoria.

## Snapshot efetivo e integridade

A tabela `audit_execution_configurations` persiste a configuração efetiva secret-free usada pelo subprocesso.

O snapshot inclui, conforme aplicável:

- alvo(s) normalizado(s);
- parâmetros do core;
- configuração efetiva de IA sem credenciais;
- Web Performance e categorias Lighthouse;
- Synthetic Navigation/Experience Apdex;
- Search Intelligence;
- variáveis não secretas persistíveis;
- plano `audit_catalog`;
- overrides explícitos do operador e proveniência necessária à reutilização.

`configuration_hash` é SHA-256 da serialização canônica. A página apresenta estados de integridade como:

- `ÍNTEGRO`;
- `HASH DIVERGENTE`;
- `SNAPSHOT AUSENTE`;
- `SNAPSHOT CORROMPIDO`.

O hash valida o snapshot, não substitui integridade de artifacts/evidências/banco.

## Segurança de credenciais

Credenciais nunca entram no snapshot ou HTML. Isso inclui API keys, access/refresh tokens, client secrets, senhas, authorization headers e equivalentes.

Quando uma integração registra configuração ausente, o relatório pode mostrar somente o nome da configuração esperada, por exemplo:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

## Matriz de execução

`execution-evidence.html` possui uma linha por capacidade relevante. O inventário cobre core, IA, Web Performance/Lighthouse, medições sintéticas, Search Intelligence e serviços registrados de métricas/padrões/observabilidade.

| Coluna | Significado |
|---|---|
| Opção / capacidade | funcionalidade canônica do RASAi |
| Ativada? | se integrou o contrato efetivo do AUD |
| Origem da decisão | plano `CAT-*`, sessão/override, configuração persistida ou padrão |
| Estado | concluído, parcial, falha, configuração necessária ou não solicitado |
| Onde verificar tecnicamente | tabela/artefato persistido com o detalhe operacional |
| Configuração faltante | nomes de variáveis/parâmetros ausentes quando persistidos |

A presença de configuração de provider não equivale a capacidade solicitada. A seleção deve ser derivada do plano congelado sempre que esse dado existir.

## Fontes técnicas

A página é read-only e usa dados já persistidos, incluindo conforme aplicável:

```text
audit_execution_configurations
audit_fulfillment_contracts
audit_fulfillment_work_items
audit_fulfillment_attempts
web_performance_runs
web_performance_attempts
web_performance_observations
standards_service_runs
ai_audit_sessions
ai_provider_attempts
synthetic_apdex_runs
synthetic_ux_apdex_runs
```

## Relação com fulfillment

O denominador do fulfillment contém somente requisitos obrigatórios aplicáveis.

Estados `DISABLED` e `NOT_APPLICABLE` ficam fora do conjunto relevante. Capacidade solicitada pode impedir conclusão quando estiver, por exemplo, em:

- `NOT_CONFIGURED`;
- `WAITING_FOR_DATA`;
- `REQUESTED_NOT_EXECUTED`;
- `FAILED_RETRYABLE`;
- `FAILED_PERMANENT`;
- `BLOCKED`.

Erro de API, quota, autenticação, provider ou timeout não cria finding do website por si só.

## Consistência entre páginas

A semântica solicitado/não solicitado deve ser equivalente entre `index.html`, páginas especializadas, `execution-evidence.html`, `report-catalog/`, banners de fulfillment e modal de transparência.

A existência de uma página canônica não prova que sua capacidade foi executada.

No `report-catalog/`, ausência de resultado não deve ser convertida em `NÃO SOLICITADO` quando o snapshot mostra que o CAT foi selecionado. Da mesma forma, um CAT fora do plano não pode ser apresentado como executado apenas porque existe configuração técnica disponível.

## Reprocessamento

Reprocessamento reutiliza o snapshot efetivo do AUD e tenta somente requisitos pendentes elegíveis. Não altera silenciosamente o contrato original.

Depois da reconciliação, `execution-evidence.html` deve refletir o estado mais recente do mesmo AUD.

## Limites

A página:

- não executa rede;
- não chama IA;
- não altera scoring/fulfillment/findings/evidências;
- não grava configuração do operador;
- não substitui `audit.db` como fonte de verdade.

## Desenvolvimento

O produto permanece em desenvolvimento/pré-produção. A documentação descreve somente o contrato vigente: catálogo `CAT-*`, configuração efetiva, snapshot da execução e evidências persistidas.
