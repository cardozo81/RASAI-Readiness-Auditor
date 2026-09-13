# Reutilização de configuração de AUD concluído

## Objetivo

O RASAi permite iniciar **uma nova auditoria** usando como ponto de partida a configuração efetiva de um `AUD-*` anterior. O recurso existe para repetir medições em momentos diferentes com menor deriva de configuração e para tornar a interpretação longitudinal do relatório consolidado mais confiável.

Este fluxo **não é reprocessamento**.

- **Reprocessar** mantém o mesmo `AUD-*` e tenta completar requisitos pendentes da observação original.
- **Reutilizar configuração** sempre cria um novo `AUD-*`, em outro momento, usando um AUD concluído apenas como fonte de configuração.

## Elegibilidade da origem

A única regra de elegibilidade é a regra canônica de consolidação já existente no fulfillment.

Um AUD de origem só é aceito quando `consolidation_eligible=true`, o que implica que todos os requisitos obrigatórios e aplicáveis definidos pela configuração daquela execução foram atendidos e o relatório/score chegaram ao estado final correspondente.

Não existe uma segunda definição de sucesso específica para este recurso.

São rejeitados:

- AUD parcial, preliminar, bloqueado ou ainda recuperável;
- AUD expirado para conclusão;
- AUD sem `audit.db` disponível;
- AUD concluído em versão anterior que não possua o snapshot canônico reutilizável de configuração;
- snapshot com schema ou hash inválido.

A rejeição de AUD antigo sem snapshot é deliberadamente **fail-closed**. O RASAi não tenta inferir uma configuração histórica incompleta a partir de relatórios ou efeitos observados, pois isso produziria falsa reprodutibilidade.

## Snapshot canônico

Execuções iniciadas pelas superfícies de configuração suportadas nesta entrega - console local e durable job SaaS `AUDIT` - persistem no próprio `audit.db` um snapshot não secreto da configuração efetivamente usada.

A tabela derivada `audit_execution_configurations` registra:

- versão do schema do snapshot;
- tipo da superfície (`CONSOLE` ou `AUDIT_PAYLOAD`);
- configuração canônica em JSON;
- SHA-256 da configuração;
- `source_audit_id`, quando a execução veio de outro AUD;
- hash da configuração de origem;
- campos efetivamente alterados;
- `execution_series_id`;
- escopo operacional necessário para validação de tenancy/SaaS;
- timestamp de criação.

O hash descreve **a configuração efetiva**, não a proveniência. Metadados de linhagem não entram no hash.

### Janela de persistência e imutabilidade

A configuração é vinculada ao contexto da execução **antes** do audit começar. A persistência ocorre dentro da finalização canônica do AUD, enquanto `audit.db` ainda está na janela legítima de escrita e **antes do primeiro SHA-256 usado pela indexação do control plane**.

Console e worker não escrevem o snapshot depois que `entrypoint.main()` retorna. Isso impediria a imutabilidade porque o control plane já poderia ter indexado o hash do `audit.db`.

Portanto, o snapshot faz parte do mesmo estado imutável que será inicialmente indexado. Não existe atualização posterior do digest apenas para registrar a configuração.

## Secrets

Credenciais nunca são copiadas do AUD de origem.

API keys, bearer tokens, senhas, tokens OAuth e demais secrets continuam sendo resolvidos no momento da nova execução a partir do mecanismo vigente da sessão, sistema operacional ou ambiente SaaS.

O snapshot contém apenas parâmetros não secretos que já são elegíveis ao contrato de configuração persistente do RASAi.

Consequência operacional: uma configuração histórica pode solicitar um provider que hoje não possui credencial válida. Nesse caso o preflight atual deve bloquear a execução até o usuário configurar a credencial necessária; nenhuma credencial histórica é recuperada do AUD.

## Console local

A tela principal de configuração recebe o atalho:

```text
L. Carregar configuração de AUD concluído [NOVA EXECUÇÃO]
```

O fluxo é:

1. usuário informa `AUD-*`;
2. RASAi valida a elegibilidade canônica para consolidação;
3. RASAi valida snapshot/schema/hash;
4. parâmetros não secretos e targets efetivos são carregados;
5. usuário retorna ao fluxo normal de configuração;
6. usuário pode revisar e alterar qualquer parâmetro permitido;
7. preflight normal é executado;
8. a execução cria um **novo `AUD-*`**;
9. o novo snapshot registra origem, série e diferenças.

Para uma única URL, o target volta ao modo URL. Para múltiplos targets, o console materializa um TXT operacional em `audits/.reused-inputs/` e mantém no snapshot a lista canônica de URLs, não o caminho desse arquivo.

O target reutilizado vem da lista canônica registrada no snapshot da execução de origem. O RASAi não depende do caminho de um TXT histórico mutável para reconstruir a configuração.

### UX

O recurso foi colocado no nível principal para **não criar mais um submenu**.

A convenção vigente de navegação `V. Voltar` permanece preservada nesta entrega. A introdução de um atalho global `M. Menu principal` exigiria alteração transversal de vários submenus e do teste de regressão que hoje protege a convenção vigente; por isso deve ser tratada como evolução de UX independente, e não misturada à lógica de reprodutibilidade.

## SaaS / Web API

O backend SaaS suporta o mesmo contrato de domínio. Não há implementação paralela da regra no front-end.

Ao criar um durable job `AUDIT`, a API aceita opcionalmente:

```json
{
  "source_audit_id": "AUD-...",
  "payload": {
    "max_pages": 25
  }
}
```

Sem `source_audit_id`, `payload` continua representando uma execução normal.

Com `source_audit_id`:

1. o backend carrega o payload efetivo do AUD concluído;
2. aplica somente os overrides enviados pelo usuário;
3. revalida tudo pelo contrato canônico atual de `AUDIT`;
4. adiciona proveniência gerenciada pelo servidor;
5. enfileira um novo job `AUDIT`.

`source_audit_id` é inválido para `SEARCH_MONITOR` e `REPORT_REFRESH`.

No SaaS, o AUD de origem deve pertencer ao mesmo `project_id`, `property_id` e `environment_id`. Isso impede que configuração histórica atravesse scopes de tenancy/propriedade por engano.

A UI web pode consumir essa capacidade posteriormente sem criar nova regra de negócio.

## Linhagem e séries

A primeira execução que possui snapshot recebe um `execution_series_id`.

Quando outro AUD é criado a partir dela, o novo AUD herda esse mesmo identificador. Assim uma sequência pode ser representada como uma série longitudinal, independentemente de qual membro foi usado como origem direta.

Exemplo:

```text
SER-ABC
  AUD-001  baseline
  AUD-014  reutilizou AUD-001 sem alterações
  AUD-031  reutilizou AUD-014 com max_pages alterado
```

O relatório continua tratando cada `AUD-*` como uma observação independente. O `SER-*` apenas descreve a relação metodológica entre as observações.

## Comparabilidade no consolidado

O consolidado não recalcula score nem muda o valor persistido por causa da configuração. A linhagem é uma camada de interpretação adicional.

A classificação usa o mesmo par temporal escolhido pelo relatório:

- `FIRST_LAST`: primeiro e último AUD elegíveis do filtro;
- `LATEST_PREVIOUS`: penúltimo e último;
- `MANUAL`: os dois Audit IDs explicitamente escolhidos pelo usuário.

Classificações principais:

- `EXACT`: baseline e atual pertencem à mesma série e possuem o mesmo hash de configuração;
- `PARTIAL`: pertencem à mesma série, mas o hash mudou;
- `EQUIVALENT_WITHOUT_LINEAGE`: hashes equivalentes, porém sem uma mesma série explícita;
- `UNRELATED`: série/configuração não estabelecem uma repetição controlada;
- `INSUFFICIENT_DATA`: não há snapshot suficiente no par escolhido para classificá-lo.

Quando a comparação é parcial ou não relacionada, o relatório consolidado registra uma limitação metodológica explícita. Campos alterados dentro de uma mesma série são listados quando disponíveis.

Isso complementa, e não substitui, as proteções já existentes de comparabilidade por:

- versão de scoring;
- versão do ruleset/auditor;
- universo de URLs;
- perfil e threshold de Apdex;
- fonte/escopo de métricas externas.

## Relação com reprocessamento

Um AUD que falhou inicialmente e posteriormente foi reprocessado até se tornar completamente elegível para consolidação pode servir de origem, desde que possua snapshot canônico.

O número de `RPR-*` anteriores não altera a regra. O snapshot descreve a configuração da observação `AUD-*`; reprocessamentos apenas completam essa mesma observação.

## Testes por sistema operacional

A validação segue a matriz operacional vigente do projeto:

- **Windows**: autoridade para console local, navegação, carregamento de configuração, materialização de targets e runtime local;
- **Linux**: autoridade para SaaS/Web API, durable jobs, control plane e integrações de servidor;
- testes puros de domínio, hash, schema, elegibilidade e comparabilidade são multiplataforma quando isso agrega cobertura real.

Não se duplica uma regressão em diferentes sistemas operacionais quando não existe dependência de SO.

## Segurança e integridade

O recurso não altera:

- SARI-001;
- SCORE-GEO-004;
- pesos ou gates de readiness;
- política de quarentena/circuit breaker de providers;
- semântica do reprocessamento seletivo;
- `audit.db` como fonte de evidência da observação;
- regra de que somente AUD elegível participa da consolidação geral.

A falha ao persistir um snapshot de configuração não deve transformar um resultado analítico válido em falha de auditoria. Nesse caso o AUD pode continuar válido para relatório/consolidação, mas fica indisponível como origem de configuração porque o carregamento é fail-closed na ausência do snapshot.
