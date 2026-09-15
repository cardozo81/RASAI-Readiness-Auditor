# Evidências da execução e integridade da configuração

## Objetivo

Cada auditoria deve permitir responder, sem depender do estado atual da máquina:

1. qual configuração efetiva foi usada;
2. qual perfil foi selecionado;
3. quais ajustes explícitos do usuário prevaleceram sobre o perfil;
4. quais capacidades estavam solicitadas;
5. quais capacidades não estavam solicitadas;
6. quais capacidades concluíram;
7. quais falharam ou ficaram pendentes;
8. onde consultar tecnicamente o erro;
9. quais nomes de variáveis/configurações faltaram quando o erro foi de configuração.

A superfície canônica para essa leitura é:

```text
<AUD-ID>/report/execution-evidence.html
```

Ela faz parte do `REPORT-CONTRACT-002` vigente. Como o produto permanece em desenvolvimento pré-publicação, o contrato corrente foi atualizado diretamente; não existe migração de versão pública anterior a preservar.

## Princípio central

O relatório deve representar o **contrato efetivo da execução**, e não a capacidade máxima do RASAi.

Exemplos:

- IA desabilitada pelo usuário/perfil = `NÃO SOLICITADO`, não falha;
- categoria Lighthouse Accessibility fora do perfil = `NÃO SOLICITADO`, não `NÃO DISPONÍVEL`;
- Synthetic Apdex desabilitado = estado neutro;
- Google Search Console não solicitado = estado neutro;
- Google Search Console solicitado sem configuração obrigatória = `CONFIGURAÇÃO NECESSÁRIA`;
- serviço solicitado que tentou executar e recebeu erro operacional = `FALHA` ou estado parcial correspondente.

Capacidade não solicitada não deve reduzir o fulfillment, transformar o AUD em preliminar nem bloquear consolidação.

## Escopos de configuração

O console possui três escopos distintos e eles não devem ser confundidos.

### Configuração persistida do operador

Inclui INI, defaults e configuração persistida no sistema operacional. É propriedade do operador e não pode ser reescrita por um perfil apenas para executar um AUD.

### Sessão atual do console

Contém alterações explícitas feitas pelo usuário durante a sessão. A sessão permanece propriedade do operador.

### Overlay da execução

É a projeção temporária de um perfil ou de um contexto de execução restaurado. Existe somente para determinar a próxima execução e o ambiente privado entregue ao subprocesso.

O overlay:

- não altera `rasai-defaults.ini`;
- não altera `rasai-console.ini`;
- não grava Windows/User;
- não grava Windows/Machine;
- não grava credenciais;
- não deve permanecer no `os.environ` do processo pai após a preparação da execução.

## Precedência do perfil e do usuário

Um perfil é um preset de execução, não uma fonte de configuração permanente.

A regra operacional é:

```text
ajuste explícito do usuário após selecionar o perfil
> overlay do perfil
> configuração da sessão / configuração persistida
```

O perfil somente projeta os domínios que ele controla e que não receberam override manual. Ao terminar a preparação/execução, o estado da sessão é restaurado.

A configuração reutilizável persistida no AUD é serializada **com o mesmo overlay efetivo usado pelo subprocesso**. Isso evita o erro de persistir a configuração-base da sessão enquanto a execução real usou valores diferentes definidos pelo perfil.

## Snapshot efetivo e integridade

A tabela `audit_execution_configurations` persiste uma representação **secret-free** da configuração efetiva.

O snapshot inclui, conforme aplicável:

- alvo(s) normalizado(s);
- parâmetros do core;
- configuração de IA sem credenciais;
- Web Performance e categorias Lighthouse;
- Synthetic Apdex e Experience Apdex;
- Search Intelligence;
- variáveis não secretas persistíveis;
- metadados do perfil efetivo: identificador, rótulo, módulos, modo de IA e overrides manuais.

O snapshot possui `configuration_hash` SHA-256 calculado a partir da serialização canônica. A página `execution-evidence.html` recalcula esse hash e apresenta:

- `ÍNTEGRO`: hash persistido = hash recalculado;
- `HASH DIVERGENTE`: o conteúdo persistido não corresponde ao hash;
- `SNAPSHOT AUSENTE`: não há snapshot reutilizável para o AUD;
- `SNAPSHOT CORROMPIDO`: o JSON persistido não é materializável.

O hash valida a integridade do snapshot persistido. Ele não substitui a integridade das evidências, artifacts ou do banco completo.

## Segurança de credenciais

Credenciais não entram no snapshot nem no HTML.

São excluídos valores associados a:

- API keys;
- access tokens;
- refresh tokens;
- client secrets;
- senhas;
- authorization headers;
- outras credenciais equivalentes.

Quando uma integração registra configuração ausente, o relatório pode mostrar apenas o **nome** esperado, por exemplo:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL
```

O valor da credencial/configuração sensível nunca deve ser materializado na página.

## Matriz de execução

`execution-evidence.html` possui uma linha por capacidade relevante. O inventário inclui o core, IA, Web Performance, categorias Lighthouse, medições sintéticas, Search Intelligence e serviços registrados de métricas/padrões/observabilidade.

As colunas são:

| Coluna | Significado |
|---|---|
| Opção / capacidade | funcionalidade que o RASAi pode executar |
| Ativada? | se integrou o contrato efetivo deste AUD |
| Origem da decisão | perfil, override explícito, configuração persistida ou padrão operacional |
| Estado | concluído, parcial, falha, configuração necessária ou não solicitado |
| Onde verificar tecnicamente | tabela/artefato persistido que contém o detalhe operacional |
| Configuração faltante | nomes de variáveis/parâmetros ausentes quando essa informação foi persistida |

## Fontes técnicas

A página usa somente dados já persistidos. As principais fontes são:

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

Outras tabelas específicas podem ser citadas na coluna de referência técnica.

## Relação com fulfillment

O denominador do fulfillment é formado pelos requisitos obrigatórios **aplicáveis**.

Estados `DISABLED` e `NOT_APPLICABLE` permanecem excluídos do conjunto de requisitos relevantes. A camada HTML usa a mesma semântica e não deve transformar esses estados neutros em ausência/falha.

Uma capacidade solicitada pode impedir conclusão quando estiver em estado como:

- `NOT_CONFIGURED`;
- `WAITING_FOR_DATA`;
- `REQUESTED_NOT_EXECUTED`;
- `FAILED_RETRYABLE`;
- `FAILED_PERMANENT`;
- `BLOCKED`.

O motivo deve permanecer operacional. Falha de API, quota, autenticação, provider ou timeout não cria finding do website por si só.

## Consistência entre páginas HTML

A regra solicitado/não solicitado é comum a todas as páginas.

O passe final de apresentação deve preservar equivalência semântica entre:

- `index.html`;
- páginas especializadas;
- `execution-evidence.html`;
- banners de fulfillment;
- modal de transparência;
- navegação canônica.

Em particular, o dashboard não deve apresentar uma categoria Lighthouse como indisponível quando ela não fazia parte de `web_performance_runs.categories`. Nesse caso o estado público é `NÃO SOLICITADO` ou `DESABILITADO`, conforme o contrato efetivo.

A existência de uma página canônica não prova que sua capacidade foi executada.

## Reprocessamento

Reprocessamento não altera o contrato original de forma silenciosa.

O RASAi deve reutilizar o snapshot da execução e tentar somente requisitos pendentes elegíveis conforme os contratos de reprocessamento. A página de evidências deve ser regenerada depois da reconciliação final para refletir o estado efetivo mais recente do mesmo AUD.

## Limites

A página é read-only:

- não executa rede;
- não chama IA;
- não altera scoring;
- não altera fulfillment;
- não altera findings/evidences;
- não grava configuração do operador;
- não substitui `audit.db` como fonte de verdade.

O HTML é uma projeção para leitura e diagnóstico. A fonte autoritativa continua sendo a persistência da auditoria.
