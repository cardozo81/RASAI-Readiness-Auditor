# Gestão e exclusão segura de auditorias

## Objetivo

O console local do RASAi permite administrar evidências `AUD-*` antigas sem transformar o produto em um sistema de backup, cold storage ou lifecycle de objetos.

O escopo é deliberadamente limitado a:

- inventariar AUDs persistidos;
- filtrar por data, domínio, projeto e status;
- selecionar um, vários, todos do filtro ou todos os AUDs existentes;
- estimar espaço ocupado;
- identificar `CONS-*` derivados que dependem dos AUDs selecionados;
- excluir o lote de forma coordenada;
- preservar rastreabilidade local da exclusão;
- atualizar o índice consolidado derivado;
- repetir posteriormente uma limpeza física que tenha sido bloqueada pelo sistema operacional.

Não fazem parte desse contrato:

- ZIP automático;
- archive/restore transparente;
- hot/warm/cold tiering;
- política automática de retenção;
- leitura de SQLite dentro de archive;
- identificação do processo externo que mantém um handle Windows aberto.

## Acesso pelo console

Em:

```text
Início > Auditorias / histórico
```

a lista normal de AUDs passa a oferecer:

```text
G. Gerenciar / excluir auditorias
```

A gestão não substitui o fluxo normal de selecionar um AUD para reprocessar, reutilizar configuração ou consultar seus artefatos.

## Inventário e filtros

A tela administrativa lê `audit.db` somente em modo read-only e apresenta, quando disponíveis:

```text
AUD-ID
Data semântica da observação
Status
Tamanho aproximado em disco
Domínio/domínios
Projeto
Série de execução
Elegibilidade para consolidação
Existência de configuração reutilizável
```

Filtros disponíveis:

```text
Data inicial
Data final
Domínio
Projeto
Status
```

A data usa os timestamps persistidos da auditoria; timestamps arbitrários do filesystem não são autoridade temporal.

A interface diferencia:

```text
seleção individual
seleção de todos os AUDs do filtro atual
exclusão de todos os AUDs existentes
```

`Excluir todos` exige a frase reforçada:

```text
EXCLUIR TODOS OS AUDS
```

Para um lote normal a confirmação é:

```text
EXCLUIR
```

## Análise de impacto

Antes de qualquer mutação física o RASAi calcula e exibe:

```text
quantidade de AUDs
espaço estimado
CONS derivados afetados
séries de execução afetadas
configurações reutilizáveis que serão perdidas
```

Um AUD com metadados que não possam ser lidos/validados é rejeitado pela operação segura. Um AUD em estado de processamento ativo também não pode ser excluído.

## Regra para CONS

`audits/consolidated/CONS-*/manifest.json` registra os `source_audits` usados na geração.

Se qualquer AUD selecionado participar de um `CONS-*`, o CONS inteiro entra automaticamente no mesmo lote de exclusão.

O RASAi não edita um consolidado existente para retirar somente um AUD porque médias, tendências, percentis, interpretações e demais conclusões foram calculados sobre o universo original.

Exemplo:

```text
CONS-001 = AUD-001 + AUD-002 + AUD-003
CONS-002 = AUD-004 + AUD-005

Excluir AUD-002
=> remove CONS-001
=> preserva CONS-002
```

A exclusão não gera automaticamente outro consolidado. Uma geração posterior usa apenas os AUDs ainda existentes e elegíveis.

## Exclusão em duas fases

A exclusão não executa `rmtree` diretamente sobre cada AUD do lote.

### Fase 1 - preparação/staging

Todos os AUDs e CONS derivados são movidos, por rename dentro do mesmo `audits-root`, para:

```text
audits/.trash/DEL-*/
```

Somente quando todos os elementos entram na área de descarte o lote pode ser considerado logicamente removido do namespace operacional.

Se qualquer movimento falhar antes do commit lógico, os itens já movimentados são restaurados em ordem reversa.

Estados possíveis incluem:

```text
PREPARATION_FAILED
ROLLBACK_COMPLETED
ROLLBACK_FAILED
LOGICALLY_DELETED
PHYSICAL_CLEANUP_PENDING
COMPLETED
```

`ROLLBACK_FAILED` é uma condição excepcional e explícita: o filesystem não oferece transação ACID para múltiplas árvores e um processo externo pode interferir também durante o rollback.

### Fase 2 - limpeza física

Depois do commit lógico o diretório `DEL-*` é removido fisicamente.

Se um antivírus, indexador, editor, SQLite externo ou outro processo impedir a remoção de algum arquivo, a auditoria não volta a aparecer como ativa no RASAi. O estado passa a:

```text
PHYSICAL_CLEANUP_PENDING
```

O console oferece uma ação para tentar novamente a limpeza de lotes pendentes.

Essa separação evita que um lote fique com parte dos AUDs ainda operacionais e parte definitivamente removida apenas porque um arquivo estava bloqueado no meio da sequência.

## Windows e arquivos em uso

Não existe uma checagem prévia de `arquivo em uso` capaz de garantir que o arquivo continuará livre até a exclusão. Há uma condição de corrida inevitável entre testar um handle e executar a mutação.

Por isso a autoridade prática é a tentativa de rename/movimentação do próprio lote. Se o sistema operacional recusar, a preparação falha e o rollback é executado.

O módulo fecha apenas as conexões SQLite que ele próprio abre. Ele não tenta enumerar handles de processos externos nem assumir responsabilidade de um diagnosticador do Windows.

Também devem ser considerados, quando existirem, arquivos auxiliares SQLite como:

```text
audit.db-wal
audit.db-shm
```

Como o workspace inteiro é movimentado, esses sidecars acompanham o AUD.

## Índice consolidado

`audits/.rasai/consolidated-index.db` permanece cache derivado e reconstruível.

Após o staging lógico, o RASAi solicita `ConsolidationIndex.refresh()`. Os AUDs que deixaram de existir na raiz operacional são removidos do índice conforme o contrato normal do consolidado.

Falha temporária de refresh é registrada como aviso no ledger de exclusão; não transforma o índice derivado em fonte de verdade.

## Control plane

A exclusão local de evidência não apaga registros históricos já persistidos no control plane SQLite/PostgreSQL.

Isso é intencional: execução histórica e evidência física são conceitos diferentes.

Neste escopo não foi introduzido `evidence_status` no schema central porque isso exigiria migração coordenada de SQLite e PostgreSQL e ampliaria o risco da feature. O histórico central existente permanece intacto, enquanto o workspace apontado pode deixar de existir fisicamente.

Uma futura evolução SaaS pode modelar explicitamente `evidence_status/deleted_at` no control plane, mas isso é uma mudança de contrato de persistência independente desta administração local.

## Ledger local

Cada lote registra eventos append-only em:

```text
audits/.rasai/audit-deletions.jsonl
```

O ledger preserva, sem secrets:

```text
batch_id
AUDs removidos
metadados operacionais disponíveis
domínios
status
série de execução
CONS derivados removidos
timestamp
estado da limpeza física
avisos do índice consolidado
```

O ledger não substitui `audit.db`, não permite reprocessamento e não recria evidência apagada. Ele existe apenas para rastreabilidade administrativa.

## Efeito funcional da exclusão

Depois que um AUD sai do namespace operacional deixam de estar disponíveis, para aquela observação:

- `audit.db`;
- artifacts;
- relatórios HTML do AUD;
- logs locais;
- reprocessamento `RPR-*`;
- reutilização da configuração daquele AUD;
- evidência bruta;
- participação em novos consolidados.

O RASAi continua apto a executar novas auditorias e a trabalhar com os demais AUDs.

## Princípio de produto

A feature administra com segurança evidências produzidas pelo próprio RASAi. Ela não tenta resolver backup corporativo ou armazenamento de longo prazo.

Se retenção avançada, object storage ou tiering se tornarem necessários no SaaS, devem ser tratados como capacidades do control plane/storage, não adicionados implicitamente ao runtime local de auditoria.
