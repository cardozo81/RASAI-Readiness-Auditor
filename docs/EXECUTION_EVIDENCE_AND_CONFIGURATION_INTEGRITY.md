# Evidências da execução e integridade da configuração

## Objetivo

Cada auditoria deve permitir responder, sem depender do estado atual da máquina:

1. qual configuração efetiva foi usada;
2. qual perfil foi selecionado;
3. quais capacidades canônicas o perfil solicitou;
4. quais ajustes explícitos do usuário prevaleceram sobre o perfil;
5. quais capacidades estavam ou não solicitadas;
6. quais concluíram, falharam ou ficaram pendentes;
7. onde consultar tecnicamente o erro;
8. quais configurações faltaram quando a falha foi de parametrização.

A superfície canônica é:

```text
<AUD-ID>/report/execution-evidence.html
```

## Princípio central

O relatório representa o **contrato efetivo da execução**, não a capacidade máxima do RASAi.

Capacidade não solicitada não reduz fulfillment, não transforma o AUD em preliminar e não
bloqueia consolidação.

Exemplos:

- IA não solicitada pelo perfil e ausente na sessão = `NÃO SOLICITADO`;
- IA já selecionada na sessão permanece parte da execução mesmo quando o perfil não adiciona IA;
- categoria Lighthouse fora do contrato efetivo = `NÃO SOLICITADO`;
- Synthetic Apdex desabilitado e não solicitado = estado neutro;
- GSC não solicitado = estado neutro;
- GSC obrigatório sem configuração suficiente = `CONFIGURAÇÃO NECESSÁRIA`;
- serviço solicitado que tentou executar e recebeu erro = `FALHA` ou estado parcial correspondente.

## Escopos de configuração

### Configuração persistida do operador

Inclui INI, defaults e configuração persistida no sistema operacional. É propriedade do operador
e não pode ser reescrita por um perfil.

### Sessão atual

Contém as escolhas explícitas do operador. A sessão é autoridade superior ao preset quando o
operador altera algo depois da seleção do perfil.

### Overlay da execução

É a projeção temporária do perfil/contexto restaurado usada para preparar a execução.

O overlay:

- é **aditivo**;
- não desliga silenciosamente capacidades já habilitadas na sessão;
- não altera `rasai-defaults.ini`;
- não altera `rasai-console.ini`;
- não grava Windows/User ou Windows/Machine;
- não grava credenciais;
- não permanece no `os.environ` do processo pai após a projeção.

A precedência é:

```text
ajuste explícito posterior do usuário
> intenção adicionada pelo perfil
> estado/configuração já existente na sessão
> configuração persistida/defaults
```

## Perfis e capacidades canônicas

Perfis não possuem mais uma taxonomia independente de módulos. Eles são combinações das mesmas
capacidades canônicas mostradas em `Preparar auditoria`.

O snapshot secret-free persiste, quando houver perfil:

- `profile_id`;
- `label`;
- `capabilities`;
- `ai_mode`;
- `manual_overrides`.

O objetivo é permitir que perfil, preparação, execução, fulfillment, reprocessamento e relatório
usem a mesma linguagem funcional.

## Snapshot efetivo e integridade

A tabela `audit_execution_configurations` persiste a configuração efetiva secret-free usada pelo
subprocesso.

O snapshot inclui, conforme aplicável:

- alvo(s) normalizado(s);
- parâmetros do core;
- configuração de IA sem credenciais;
- Web Performance e categorias Lighthouse;
- Synthetic Navigation/Experience Apdex;
- Search Intelligence;
- variáveis não secretas persistíveis;
- metadados do perfil/capacidades;
- overrides explícitos do operador.

`configuration_hash` é SHA-256 da serialização canônica. A página apresenta:

- `ÍNTEGRO`;
- `HASH DIVERGENTE`;
- `SNAPSHOT AUSENTE`;
- `SNAPSHOT CORROMPIDO`.

O hash valida o snapshot, não substitui integridade de artifacts/evidências/banco.

## Segurança de credenciais

Credenciais nunca entram no snapshot ou HTML. Isso inclui API keys, access/refresh tokens,
client secrets, senhas, authorization headers e equivalentes.

Quando uma integração registra configuração ausente, o relatório pode mostrar somente o nome da
configuração esperada, por exemplo:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

## Matriz de execução

`execution-evidence.html` possui uma linha por capacidade relevante. O inventário cobre core,
IA, Web Performance/Lighthouse, medições sintéticas, Search Intelligence e serviços registrados
de métricas/padrões/observabilidade.

| Coluna | Significado |
|---|---|
| Opção / capacidade | funcionalidade canônica do RASAi |
| Ativada? | se integrou o contrato efetivo do AUD |
| Origem da decisão | perfil, sessão/override, configuração persistida ou padrão |
| Estado | concluído, parcial, falha, configuração necessária ou não solicitado |
| Onde verificar tecnicamente | tabela/artefato persistido com o detalhe operacional |
| Configuração faltante | nomes de variáveis/parâmetros ausentes quando persistidos |

## Fontes técnicas

A página é read-only e usa dados já persistidos, incluindo:

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

Estados `DISABLED` e `NOT_APPLICABLE` ficam fora do conjunto relevante. Capacidade solicitada
pode impedir conclusão quando estiver, por exemplo, em:

- `NOT_CONFIGURED`;
- `WAITING_FOR_DATA`;
- `REQUESTED_NOT_EXECUTED`;
- `FAILED_RETRYABLE`;
- `FAILED_PERMANENT`;
- `BLOCKED`.

Erro de API, quota, autenticação, provider ou timeout não cria finding do website por si só.

## Consistência entre páginas

A semântica solicitado/não solicitado deve ser equivalente entre `index.html`, páginas
especializadas, `execution-evidence.html`, banners de fulfillment e modal de transparência.

A existência de uma página canônica não prova que sua capacidade foi executada.

## Reprocessamento

Reprocessamento reutiliza o snapshot efetivo do AUD e tenta somente requisitos pendentes
elegíveis. Não altera silenciosamente o contrato original.

Depois da reconciliação, `execution-evidence.html` deve refletir o estado mais recente do mesmo
AUD.

## Limites

A página:

- não executa rede;
- não chama IA;
- não altera scoring/fulfillment/findings/evidências;
- não grava configuração do operador;
- não substitui `audit.db` como fonte de verdade.

## Desenvolvimento

O produto permanece em desenvolvimento e não há versão pública/legado a preservar. O contrato
vigente usa **capacidades** como unidade canônica de composição dos perfis.
