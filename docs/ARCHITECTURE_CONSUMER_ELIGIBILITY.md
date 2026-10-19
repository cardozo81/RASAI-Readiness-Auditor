# Elegibilidade de consumidores do contexto arquitetural

## Contrato de implementação (issue #646)

A arquitetura é uma **observação**, não um índice e não uma autorização
para trocar coletores, coortes, perfis ou cálculos. A preferência local de
aquisição (`STATIC`, `DYNAMIC`, `SKIP`) é independente da escolha
selada da AUD (`AUTO`, `DECLARED`, `UNFORCED`).

O leitor `architecture_m6_evidence.read_audit_architecture_observations`
consulta as observações já persistidas por módulo arquitetural, em SQLite somente leitura.
Um registro só é exposto como candidato se contiver identidade completa
de AUD/página/snapshot/URL solicitada/URL final/dispositivo, classe válida
e referências RAW e renderizada não vazias. Isso não equivale a verificar
integridade criptográfica de cada artefato: a garantia final requer
verificação do manifesto selado e a própria proveniência módulo arquitetural.

`resolve_historical_architecture_for_consumer` faz a correlação consultiva
de módulo arquitetural e escolha selada, usando o resolvedor `architecture_context`.
Não executa navegador, DNS, coleta, cálculo ou escrita. Escopo incompatível,
dados duplicados, ausência de evidência ou escolha histórica indisponível
devem resultar em abstenção.

| Consumidor | Estado | Efeito permitido |
| --- | --- | --- |
| `descriptive_report` | ADVISORY_SAFE (somente com opt-in do chamador) | Descrever evidência com limitações |
| `m6_read_only_diagnostic` | ADVISORY_SAFE (somente com opt-in do chamador) | Diagnóstico read-only |
| CAT-01 a CAT-08 e CAT-10 | METHOD_CHANGE_REQUIRES_ADR | Nenhuma propagação funcional automática |
| SARI / SCORE-GEO | METHOD_CHANGE_REQUIRES_ADR | Fórmulas e thresholds intactos |
| Apdex / métricas de performance | PRE_COLLECTION_ONLY / METHOD_CHANGE_REQUIRES_ADR | Nunca modificar coleta retroativamente |
| IA e recomendações | INTERPRETATION_REVIEW_REQUIRED | Nenhuma nova execução/custo implícito |
| Demais consumidores | INAPPLICABLE | Abster |

F3 **não está liberada** pela existência deste inventário. Requer
aprovação explícita por consumidor, ADR, golden/paridade histórica e
versionamento do método. Nenhum consumidor de scoring é autorizado pelo
allowlist atual.

## Operações

- **Nova AUD:** AUTO explícito pode consultar o serviço canônico; falha
  opcional não impede os catálogos independentes. Resultados da prévia
  não são persistidos como verdade módulo arquitetural ou injetados na configuração selada.
- **RPR:** mostra escolha histórica e contagem de observações módulo arquitetural elegíveis,
  sem novas consultas.
- **Complemento:** só pode consultar o leitor read-only por padrão; uma nova
  coleta exige operação e autorização explícitas, ainda pendentes de
  integração no fluxo de complemento.
- **Reclassificação:** resolver somente observações persistidas
  inequivocamente vinculadas ao mesmo escopo de URL, dispositivo e snapshot.

## Gates pendentes

1. Validação end-to-end de nova AUD/RPR/complemento no Windows.
2. Comprovação de artefatos módulo arquitetural por hash/manifesto antes de elevá-los a
   evidência reutilizável em relatórios.
3. Matriz de consumidores aprovada por responsáveis e ADRs para F3.
4. Persistência versionada do diagnóstico preliminar opcional, sem afetar
   AUD selada e sem armazenar HTML/segredos indevidamente.
5. Smoke dinâmico focal por URLs de controle, após gate CI.


## Diagnóstico físico sem atestado de manifesto

A função `inspect_architecture_artifact_pair` lê exclusivamente arquivos de
`artifacts/` dentro da AUD, recusa referências com travessia, symlinks,
conteúdo ausente e caminhos externos, e calcula SHA-256 RAW/renderizado para
diagnóstico. A saída `PRESENT_UNATTESTED` **não comprova** que esses bytes
sejam os capturados originalmente: hashes calculados na hora não possuem
âncora histórica independente. O atributo `manifest_attested` permanece
sempre `false`. Esse diagnóstico não é prova para alterar scoring, promover
um `UNKNOWN` ou desbloquear novos consumidores. Para autenticar o conteúdo
será preciso vínculo verificável com um manifesto ou recibo canônico gerado
durante a captura e preservado de modo compatível com AUDs históricas.


## Inspeção física por identidade persistida

`inspect_historical_snapshot_artifacts` recebe AUD, página, snapshot, URL
solicitada/final e dispositivo. A consulta SQLite é somente leitura, exige
correspondência exata e snapshot sem duplicidade dentro da AUD. Só depois
inspeciona os dois caminhos sob `artifacts/`. Divergências retornam
`MISSING_OR_AMBIGUOUS_IDENTITY`; existência de bytes retorna
`PRESENT_UNATTESTED`, **nunca** integridade histórica autenticada.
Não habilita classificação, pontuação, reprocessamento ou recoleta adicionais.

## Configuração histórica - campos numéricos

Ao restaurar uma configuração de AUD, campos inteiros de Search Intelligence
rejeitam booleanos e valores não finitos (`NaN`, `Infinity`). Cada campo
inválido preserva o valor vigente e gera aviso; o restante da restauração
segue a precedência aprovada. Isso não autoriza consultas Perplexity nem
muda o modo arquitetural selado.

## Integridade dos inteiros de Search Intelligence na reutilização de AUD

A restauração de uma AUD exige valores inteiros exatos em profundidade,
limites de páginas, bytes e redirecionamentos. Frações como `2.9` e texto
como `1e6` não são truncados silenciosamente; o campo da sessão atual
é preservado com aviso. Inteiros decimais em texto continuam aceitos.
Isso não altera escolhas de serviços externos nem concede opt-in.

## Reutilização segura dos termos de Search Intelligence

O snapshot de uma AUD pode restaurar consultas textuais não secretas, mas
não pode converter objetos, números ou cargas de controle em novas queries.
Uma lista inválida ou excessiva é recusada com aviso e preserva as consultas
da sessão; listas válidas são normalizadas, deduplicadas e obedecem ao
`enabled` explícito. Targets históricos não textuais impedem a restauração.
Isso não modifica o opt-in de Perplexity, que permanece exclusivo da sessão.


## Implementação F3 consultiva autorizada (19/10/2026)

A fase F3 exclusivamente descritiva agora possui integração read-only em `index.html#architecture` e consulta por AUD via `python -m rasai.architecture_audit_cli /caminho/AUD-ID`. A matriz executável `architecture_consumer_eligibility.architecture_consumer_eligibility()` documenta consumidores e exige que somente `descriptive_report` e `m6_read_only_diagnostic` sejam ADVISORY_SAFE, tal como `architecture_context.APPROVED_ADVISORY_CONSUMERS`.

As classificações `INTERPRETATION_SAFE`, `PRE_COLLECTION_ONLY`, `METHOD_CHANGE_REQUIRES_ADR` e `INAPPLICABLE` são classificações de elegibilidade *não executável*. A entrada do índice não ativa ajuste de métrica, autorização de IA, injeção em coletores ou mudança dos thresholds navegação sintética/experiência sintética. Os IDs externos da própria AUD são preservados; histórico `UNFORCED` não herda perfil do INI atual. Critérios operacionais pendentes continuam declarados nesta documentação. Especificação do mecanismo em [`ARCHITECTURE_AUDIT_ADVISORY.md`](ARCHITECTURE_AUDIT_ADVISORY.md).
