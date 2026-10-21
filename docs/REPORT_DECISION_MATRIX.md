# Matriz decisória de evidências da AUD

**Contrato consultivo:** RASAI-DECISION-EVIDENCE-604-001.
**Issues:** #604, #600, #319, #304, #601, #602, #603.

## Superfícies e indicadores

A visão geral index.html recebe a seção Matriz decisória de evidências; sari.html recebe a seção Universo medido e limites de comparação, com link para a visão geral. O leitor não recalcula o índice e não agrega métricas de universos diferentes.

| Indicador | Fonte | Limitação |
| --- | --- | --- |
| SARI por dispositivo | scores.OVERALL_READINESS | Nota do método, cobertura e readiness; não certifica ranking ou experiência. |
| Cobertura por dimensão | scores.coverage | Confiança agregada não apaga cobertura não integral. |
| Lighthouse Performance | web_performance_observations.performance_score | Laboratório em escala 0-100; não CrUX. |
| CrUX LCP/INP/CLS | web_performance_observations | ORIGIN agrega uma origem; URL significa página específica. |
| CAT-06/CAT-07 | Status do catálogo persistido | Conclusão operacional não comprova representatividade das amostras Apdex. |
| SERP | Uma observação identificável da AUD | Retorno versus requested_depth não é participação de mercado. |
| Sinais SEO opcionais | score_contributions + rule_executions | Descontos do SCORE-GEO-004 já persistidos; não são aplicados novamente. |
| Alegações comerciais | Fronteira do CAT-03 | Esta matriz não autentica condições gerais ou registro regulatório. |
| Presença generativa | Limitação de escopo | SERP e Search API não comprovam citação gerativa ou share. |

## CLI somente leitura para o smoke consolidado

```bash
python -m rasai.report_decision_matrix_cli /caminho/AUD-ID
```

A CLI emite apenas JSON no stdout: saída 0 quando a matriz é montada e 2 quando a origem não é verificável. Exige pasta AUD-*, audit.db físico regular, sem symlink ou WAL/SHM/journal pendente. SQLite é aberto em mode=ro&immutable=1 e query_only=ON, sem escrita. Os sensores físicos de SERP e SEO são projetados pelos leitores existentes de relatório, preservando abstenção individual quando não há identidade completa.

Nenhum browser, IA, Search API, PageSpeed, reprocessamento, custo adicional ou escrita no histórico é acionado. A matriz não constitui nova pontuação, não substitui inspeção visual dos HTMLs nem autentica recibos jurídicos de fonte externa.

## Aceite contextual

Na AUD de referência do dia 14/10/2026, conferir o score SARI e sua cobertura, Lighthouse separado de CrUX ORIGIN, estado de catálogos parciais, profundidade SERP realmente observada, descontos SEO opcionais e limitações explícitas de prova documental/generativa.

Essa verificação não fecha automaticamente #601 (clique físico same-sample), #602 (decisão normativa sobre scoring), #603 (fonte primária vigente), nem o épico #604.


## Gate offline de paridade dos relatórios HTML (#600/#604, 19/10/2026)

Para uma AUD selada com pacote `report-catalog` já materializado, execute
**somente quando o HTML já existir**:

```powershell
.\.venv\Scripts\python.exe -m rasai.report_decision_matrix_cli "audits\AUD-ID" --verify-html
```

Este modo é **opt-in**, não altera o CLI original nem materializa relatórios.
O leitor reconstitui a matriz de decisão a partir de `audit.db` em
`mode=ro&immutable=1` e exige a integridade integral do pacote pelo
verificador canônico `verify_catalog_report_package`, manifesto com
`audit_id` igual ao diretório e publicação `freshness=FINAL`. As páginas
`index.html` e `sari.html` devem ser arquivos regulares, sem symlink,
de no máximo 4 MiB cada, com digest físico igual ao SHA-256 registrado
no manifesto. A análise interpreta o DOM HTML, não busca strings em
scripts ou comentários: exige exatamente um bloco
`data-contract=DECISION-EVIDENCE-604-001` nas seções
`decision-matrix` (index) e `scope` (SARI), e compara **cada célula** da
tabela visível com a projeção independente do SQLite. Em `sari.html`
o subconjunto exigido é exclusivamente SARI e cobertura dimensional,
sem transplantar dados CrUX/Apdex de outras populações.

O resultado recebe `html_semantic_gate.status=HTML_MATRIX_PARITY_VERIFIED`
quando ambos os conjuntos conferem ou códigos de abstenção quando o
pacote, a fonte, o escopo ou as células divergem. O comando retorna exit 2
quando a opção foi solicitada e a paridade não foi comprovada.
A saída não imprime conteúdo do relatório, query, URL ou caminhos.
Este gate prova apenas **integridade local e paridade tabular**;
`browser_inspection_verified=false` e `normative_acceptance=false`
continuam explícitos. Não autentica interpretação visual, leitura de
outras seções, execução de coletores, representatividade estatística,
documento regulatório real, SEO externo ou índice revisado.

Quando o relatório físico não existir, não é necessário gerar nova AUD
para executar o teste. A paridade pode ser validada por fixture local,
sem simular falsamente uma evidência física do operador.


### Abstenção obrigatória sem linha de prontidão SARI persistida (#600)

O gate `--verify-html` distingue paridade tabular de evidência positiva:
um par de páginas `index.html` e `sari.html` que renderiza
corretamente uma matriz **sem nenhuma linha física SARI**
não pode retornar `HTML_MATRIX_PARITY_VERIFIED`. Nesse cenário retorna
`SARI_PHYSICAL_EVIDENCE_ABSENT` com aceitação normativa e inspeção
visual ainda falsas. Isso evita elevar a integridade de um relatório
vazio à condição de prontidão ou cobertura medida. Não impõe que a
AUD tenha pontuação positiva e não altera scoring, geração do relatório
ou seu uso exploratório: apenas o diagnóstico independente
de aceite se abstém até existir população SARI verificável.


### Paridade contra a AUD física atual, não apenas pacote autocoerente (#600/#604)

O manifesto de `report-catalog` contém
`audit_snapshot.source_logical_sha256` apurado quando o HTML foi
materializado. O gate `--verify-html` agora confere esse digest com
o estado **lógico efetivo** do `audit.db` da mesma AUD, por meio da
função existente `catalog_report_site._sqlite_logical_digest`.
A fonte deve estar fechada (sem `-wal/-shm/-journal`), não ser
symlink, ser SQLite físico limitado e manter identidade/tamanho/mtime
durante o cálculo. Estados de abstenção:
`AUD_SOURCE_UNAVAILABLE`, `AUD_SOURCE_NOT_SEALED`,
`AUD_REPORT_SOURCE_BINDING_ABSENT`,
`AUD_REPORT_SOURCE_STALE` e
`AUD_SOURCE_CHANGED_DURING_READ`.

Uma cópia de relatório intacta, cujo SQLite original recebeu alterações
**após** a geração do pacote, não pode reivindicar paridade de evidências
de uma AUD atualizada: exige rematerialização autorizada do relatório
ou inspeção histórica do snapshot pertinente. O diagnóstico não executa
geração, rematerialização, score ou coleta; apenas lê. A comparação
continua não significando OAuth/CrUX/browser ou aceite metodológico
normativo. Fixtures físicas SQLite incluem source original, mutação
pós-publicação, manifesto sem vínculo e WAL ativo. O custo do digest
lógico só ocorre quando `--verify-html` é solicitado explicitamente.


## Resumo opt-in de revisao documental vinculada a AUD (#603/#604)

Quando existir **pacote documental externo ja obtido e atestado por revisor
autorizado**, a CLI consultiva aceita:

```bash
python -m rasai.report_decision_matrix_cli /caminho/AUD-ID --claim-review-manifest /caminho/packet/manifest.json
```

A chave e os revisores confiaveis precisam ter origem no ambiente privado
`RASAI_CLAIM_REVIEW_HMAC_KEY_HEX` e
`RASAI_CLAIM_REVIEWER_ALLOWLIST`; nunca informar segredo no comando, AUD,
manifesto, site auditado ou JSON de saida. Esta opcao exige automaticamente
a data de coleta **assinada** no recibo, vinculo literal por
`snapshot_id/page_id` na mesma AUD, HMAC de revisor autorizado, vigencia
e versao da fonte. Sem prova, o suplemento
`documentary_claim_advisory.status=NOT_VERIFIABLE`, retorno de processo
**2**: nao se omite a falha quando o operador solicitou o gate.

Com evidencias admissiveis, a chave aditiva
`documentary_claim_advisory` traz contagens apenas das **alegacoes
submetidas**: total, observadas no snapshot, nao comprovadas na AUD,
corroboradas documentalmente, contraditas em revisao e sem verificacao
documental. Nunca interpreta esse recorte como todas as alegacoes do site
ou como certificacao de fonte oficial, autenticidade de seguradora,
conformidade regulatoria ou falha juridica. NAO mostra claim literal,
URL de fonte, identidade do revisor nem segredo.

A matriz `rows` **nao muda**: `--verify-html` continua comparando apenas
o relatorio canonico materializado com a AUD selada e o novo resultado
fica fora desse bloco. Assim, pode-se usar as duas opcoes juntas sem
reprojetar ou alterar `index.html`, `sari.html`, `audit.db`, hashes,
score, SARI, M23/M25 ou consulta a provedores. Por default, o
suplemento sequer e acessado; continua a ressalva de validacao externa
na matriz original. Esta implementacao nao substitui a fonte primaria
real e o aceite externo ainda pendentes da #603.
