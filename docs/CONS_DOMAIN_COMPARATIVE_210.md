# #210 - Prévia metodológica de comparação de URLs do mesmo domínio

## Estado

Esta implementação é um **contrato advisory puro**, não uma extensão do
motor CONS produtivo. `selection.resolve_selection` continua exigindo
exatamente a mesma URL e o mesmo dispositivo para uma série longitudinal.
O objetivo desta fase é estabelecer um gate verificável de elegibilidade
para um eventual modo **SAME_DOMAIN_COMPARATIVE** sem confundi-lo com
**SAME_URL_LONGITUDINAL**.

## Entrada e saída

A função
`rasai.consolidation.domain_comparative_preview_210.preview_same_domain_candidates`
recebe de dois a cem `AuditCandidate` produzidos pelo índice analítico
existente e não faz descoberta, indexação, coleta, consulta externa ou
materialização. Sua saída é JSON-compatível, versão
`RASAI-CONS-DOMAIN-COMPARATIVE-ADVISORY-001`.

As condições mínimas são: AUDs distintas com estado lógico COMPLETE,
URL individual verificável, mesmo hostname exato e dispositivo, pelo
menos duas URLs diferentes e instantes offset-aware únicos e válidos.
A implementação usa deliberadamente **hostname exato**, não eTLD+1
estimado, evitando confundir subdomínios, `www.` com apex, ou
domínios de registradores públicos. Se esse critério for ampliado,
exigirá uma Public Suffix List versionada e regra explícita de
equivalência organizacional.

A prévia devolve URL normalizada de cada AUD, a hora observada em UTC,
fingerprint SHA-256 do universo de uma URL e motivos determinísticos de
rejeição. O campo `domain` declarado no candidato não substitui
a verificação a partir da URL.

## Matriz de admissibilidade de métricas

| Dimensão | SAME_URL_LONGITUDINAL homologado | SAME_DOMAIN_COMPARATIVE advisory |
| --- | --- | --- |
| Identidade da URL | Mesma URL e device | Host e device iguais; URLs distintas |
| Apdex M23/M25 | Contrato histórico do CONS atual | N/D: universos e contexto de navegador distintos |
| PageSpeed/CrUX | Contrato histórico do CONS atual | N/D: métricas de URLs distintas não formam tendência da mesma página |
| HTML, descoberta e conteúdo | Evidências da URL original | Somente evidência segmentada por URL; sem delta causal |
| SARI/SCORE-GEO | Política canônica do CONS atual | Delta N/D até prova de equivalência de universo/ruleset/configuração |
| GEO | Observar método e escopo existentes | Não inferir tendências nem citações por IA |
| Intervalo temporal | Série da mesma página | Apenas ordem das AUDs, nunca delta de desempenho da página |

Nenhum valor Apdex, CWV, score ou tendência de página é calculado
pela prévia. O mesmo hostname por si só não estabelece que as ofertas,
rotas, renderizações, intenções ou amostras sejam comparáveis.

## Próximo gate de engenharia

Antes de integrar um eventual modo no CONS, validar a composição de
universos, versões de ruleset, fontes de score audit-level, contexto de
dispositivo, cache, amostragem, arquitetura SPA/SSR e permissões.
Definir artefato CONS próprio com método e hashes sem modificar
séries CONS antigas, e preparar aceite humano da semântica dos relatórios.
A integração é uma demanda distinta de implementação produtiva;
**não é tratada como homologada por estes testes**.

Esta fase modifica apenas o módulo advisory, seus testes isolados
e a documentação. Nem o índice SQL, nem o seletor CONS homologado,
nem seus manifests, coleta, IA, SCORE-GEO ou Apdex são alterados.

## Validação adicional de identidade (#210)

A prévia rejeita URLs com espaços nas extremidades, controles ASCII e
barras invertidas, em vez de remover caracteres malformados e promover
um recurso para a mesma origem/hostname. Esta regra só interpreta
entradas do adaptador advisory e não reescreve URLs das AUDs.
A comparação de caminhos distintos continua um **projeto metodológico**,
não uma tendência por mesma página; o CONS produtivo permanece inalterado.

## Entrada operacional somente leitura do índice existente

Além do resolvedor puro, `consolidation.domain_comparative_index_210`
permite selecionar duas ou mais AUDs já materializadas no índice
analítico local. Exemplo:

```powershell
.\.venv\Scripts\python.exe -m rasai.consolidation.domain_comparative_index_210 `
  --audits-root .\audits `
  --audit-id AUD-PRIMEIRA `
  --audit-id AUD-SEGUNDA
```

O arquivo `.rasai/consolidated-index.db` precisa existir, ter schema
versão 1 e não possuir sidecars SQLite WAL/SHM/journal: o consumidor
utiliza URI `mode=ro&immutable=1` e não atualiza o índice nem abre
as bases das AUDs. Exige seleção explícita de AUDs únicas, cada uma
com exatamente uma URL e um dispositivo no índice, e submete os
candidatos ao resolvedor determinístico já testado.

O identificador `source_fingerprint` do cache precisa ter forma
SHA-256 hexadecimal de 64 caracteres. Valor ausente, truncado, preenchido
com espaços ou não hexadecimal bloqueia a prévia; isto valida apenas o
**formato** do identificador, não o conteúdo ou a atualidade da AUD.
O hash de cache existente deriva de metadados locais do arquivo, não é
assinatura criptográfica do pacote e não substitui conferência de manifestos.

A resposta JSON declara
`source_package_freshness_verified=false` e
`native_cons3_created=false`: um índice previamente gerado
pode estar desatualizado em relação aos pacotes AUD de origem.
Nenhum score, série longitudinal, cálculo de métrica por página,
manifest CONS ou HTML canônico é gerado nesta etapa.


## Apresentação HTML separada e opcional

O modo `--format html` escreve **somente em stdout** um documento
consultivo com tabela de AUDs, URL exata, dispositivo, horário UTC,
fingerprint do universo e indicação explícita de métricas `N/D`.
A saída é responsiva, imprimível e escapa todos os valores extraídos
do índice. A opção padrão continua `--format json`. O módulo não
cria arquivos nem altera pacote CONS, hashes, report-catalog ou AUD.

Exemplo:
```powershell
.\.venv\Scripts\python.exe -m rasai.consolidation.domain_comparative_index_210 `
  --audits-root .\audits --audit-id AUD-PRIMEIRA `
  --audit-id AUD-SEGUNDA --format html
```

**Aviso persistente:** o índice analítico previamente gerado não
atesta o frescor das fontes; URLs diferentes não compõem uma série
longitudinal e não permitem recálculo de Apdex, CWV ou scores.
Isto é um comparativo de inventário, não um modo CONS-3 produtivo.

## Conferência opcional dos arquivos físicos de origem (#210)

O modo `--verify-source-metadata` exige, **sem escrever**, a presença
física de cada `AUD-*/audit.db` original, caminho canônico coincidente com o
índice, ausência de symlinks e sidecars SQLite não verificados, e igualdade
do fingerprint atual `path|size|mtime_ns` com o registro `source_audits`.
Consulta `audits` para identificar a AUD concluída e verifica a única URL
extraída dos registros `pages`/`audit_input_urls` contra a URL do índice.
Qualquer divergência bloqueia a comparação; registros históricos incompletos
não são preenchidos nem migrados.

Exemplo:

```powershell
.\.venv\Scripts\python.exe -m rasai.consolidation.domain_comparative_index_210 `
  --audits-root .\audits --audit-id AUD-PRIMEIRA --audit-id AUD-SEGUNDA `
  --verify-source-metadata --format html
```

Esse processo melhora a rastreabilidade da prévia em relação a um índice
possivelmente obsoleto; porém o fingerprint canônico é gerado com metadados
de arquivo, **não** com hash criptográfico de todos os bytes da AUD.
Portanto, `source_package_freshness_verified=false` continua sendo a
declaração correta. O modo não comprova dispositivo persistido ou ruleset
de origem e **não** autoriza deltas audit-level ou tendência page-level.
SAME_URL/CONS-3 continuam inalterados.
