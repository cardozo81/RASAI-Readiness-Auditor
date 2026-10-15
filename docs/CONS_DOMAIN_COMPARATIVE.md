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

## Pacote versionado CDOM, separado de CONS-3 (#210)

A partir do modo consultivo read-only, há uma opção **explícita de gravar**
somente uma saída derivada nova em
`audits_root/consolidated-domain/CDOM-<fingerprint>/`, fora de
`consolidated/CONS-*`, sem acionar o gerador CONS-3. O contrato é
`CONS-DOMAIN-COMPARATIVE-1` e produz `manifest.json` e
`report.html` com hash determinístico de entrada. Requer conferência
física do índice contra as AUDs de origem e recusa fontes
incompatíveis, alteradas ou inseguras.

```powershell
python -m rasai.consolidation.domain_comparative_package_210 `
  --audits-root .\audits --audit-id AUD-PRIMEIRA --audit-id AUD-SEGUNDA `
  --write-domain-package
```

Somente URLs distintas do mesmo **hostname exato** e device uniforme,
com uma URL e conclusão COMPLETE por AUD, geram pacote. A operação é
idempotente quando o manifesto e o HTML existentes são idênticos e
**não sobrescreve** arquivos divergentes nem fontes. Os fingerprints
atestam metadados `path|size|mtime_ns`; não autenticam todos os bytes
da AUD. Score/Apdex/CWV por página, melhorias e tendência temporal
continuam N/D. O pacote CDOM **não** entra no histórico CONS-3,
não habilita o modo produtivo SAME_DOMAIN, não muda SQL do CONS e não
implica conclusão da issue #210.

Os testes locais cobrindo recusa/retorno idempotente, integridade
SHA-256 de arquivos originais e isolamento de saída são executados
sem chamadas externas ou AUD reais. Para permitir consolidação
metodológica audit-level entre URLs diferentes, ainda será necessário
aprovar regras de equivalência de universo e configuração.


## Modo opcional CDOM v2 com SHA-256 local (#210)

O modo CDOM original `CONS-DOMAIN-COMPARATIVE-1` e os pacotes
`CDOM-*` já gerados não são regravados. Uma opção separada
`--verify-source-bytes`, utilizada **junto** da autorização
`--write-domain-package`, produz o contrato versionado
`CONS-DOMAIN-COMPARATIVE-2` e novo identificador de pacote,
incluindo `source_file_sha256` para cada `audit.db`.

```powershell
python -m rasai.consolidation.domain_comparative_package_210 `
  --audits-root .\audits --audit-id AUD-PRIMEIRA --audit-id AUD-SEGUNDA `
  --write-domain-package --verify-source-bytes
```

Os bytes são lidos de forma incremental com limite agregado de
512 MiB por seleção. Cada origem mantém também o fingerprint de
metadados do índice e é novamente lida/validada antes da publicação.
Fonte alterada, symlink, extrapolação do orçamento ou checksum
inconsistente recusa o pacote sem gravar artefato. Não faz chamadas
externas nem reescreve as bases.

`source_bytes_locally_verified=true` demonstra apenas que os bytes
do arquivo **local** consultado são os mesmos do pacote derivado
naquele instante. `source_package_freshness_verified=false` continua:
não existe atestação de assinatura do fornecedor, nem prova de que
os valores armazenados no índice representem toda a mesma população
de origem. Nenhum score, Apdex ou série com URLs distintas é
homologado por este hash.


### Gate SQLite entre as duas verificações SHA-256

A leitura de bytes do CDOM v2 exige ausência de
`audit.db-wal`, `audit.db-shm` e `audit.db-journal`
em **cada** passagem de hash. Mesmo sem mudanças no tamanho,
mtime ou SHA-256 do arquivo principal, o surgimento de arquivos
de transação invalida a hipótese de um snapshot físico selado.
O pacote é recusado, sem criar manifesto, substituir arquivos
existentes, realizar checkpoint ou remover journals. Essa
proteção não é uma assinatura nem garante isolamento sob um
writer que possa surgir depois da última verificação.


## Proveniência física de dispositivo (#210)

Ao acionar `--verify-source-metadata` (prévia) ou o pacote
`CDOM` opt-in, a consulta não aceita mais apenas
`devices_json` do índice analítico. A identidade de dispositivo
é conferida diretamente nas capturas físicas
`page_snapshots.device` associadas às páginas da AUD
(`pages.page_id`, `pages.audit_id`) e comparada à identidade
única indexada. Ausência de captura, vários dispositivos ou
divergência de MOBILE/DESKTOP impedem a emissão de resultado
comparável e a materialização de CDOM, mesmo quando URL, status,
hash e metadados do arquivo coincidem.

A prévia puramente indexada, sem `--verify-source-metadata`,
continua sendo apenas consultiva, sem atestação da fonte.
A correção é aplicada ao consumidor e não altera
`audit.db`, schemas produtivos, score ou CONS-3.


## Entrada pública pelo CLI RASAi (12/10/2026)

A prévia CDOM pode ser executada pelo roteador `rasai`, sem carregar
o runtime de coletores, IA ou o fluxo produtivo CONS-3:

```powershell
rasai domain-comparative --audits-root .\\audits `
  --audit-id AUD-PRIMEIRA --audit-id AUD-SEGUNDA `
  --verify-source-metadata --format html
```

A materialização **separada** exige o mesmo consentimento explícito de
escrita `--write-domain-package` do módulo offline e admite a proteção
adicional `--verify-source-bytes`:

```powershell
rasai domain-package --audits-root .\\audits `
  --audit-id AUD-PRIMEIRA --audit-id AUD-SEGUNDA `
  --write-domain-package --verify-source-bytes
```

A primeira operação não escreve arquivos. A segunda só escreve
`consolidated-domain/CDOM-*` versionado, com idempotência e
verificação física; **não** gera nem modifica `CONS-*` e não calcula
deltas Apdex, CWV, SARI ou GEO. A integração nativa ao relatório CONS
permanece sujeita à metodologia de universos de URL diferentes.


## Gate estrito de origem HTTP (#210, 12/10/2026)

Além de exigir um hostname e dispositivo comuns, o comparador
CDOM agora exige a mesma **origem HTTP normalizada**: protocolo,
hostname e porta efetiva. Mesmo hostname não comprova mesma
aplicação quando uma AUD veio de HTTPS padrão e outra de HTTP
ou HTTPS numa porta alternativa. Essa mistura retorna
`DIFFERENT_URL_ORIGINS_UNVERIFIED` e nenhuma coorte positiva.
Portas padrão são normalizadas; duas URLs com caminhos diferentes
e a mesma origem ainda podem compor inventário consultivo.

O campo aditivo `origin` só aparece preenchido em um resultado
elegível. Isso não homologa equivalência de ofertas, ruleset,
universo de scores, renderização SPA nem deltas de métricas
entre páginas. O seletor `CONS-3` e o pipeline homologado
permanecem inalterados.


## Identidade de telas SPA com fragmentos de URL (12/10/2026)

Na prévia `SAME_DOMAIN_COMPARATIVE`, URLs contendo `#` não são
identidades de página verificáveis. Em aplicações SPA com hash routing,
`/app#/produto-a` e `/app#/produto-b` podem representar telas distintas,
embora a URL HTTP sem fragmento seja a mesma. Ignorar silenciosamente o
fragmento atribuiria indevidamente essas observações à mesma página e
poderia sugerir a série longitudinal estrita. O contrato conservador
recusa esses candidatos com `UNVERIFIABLE_SINGLE_URL`, sem inferir
redirecionamentos, hidratação, equivalência de DOM ou união de universos.
Consultas que contêm `%23` **codificado** continuam sendo query strings
normais, sem interpretação como fragmento. Fixtures isoladas cobrem
fragments distintos, vazio, simples e query codificada; nenhuma alteração
no seletor CONS produtivo, na captura, em scores, Apdex, CWV ou IA.


## Leitura completa do SHA-256 na modalidade CDOM v2 (12/10/2026)

O materializador CDOM v2 (opção `--verify-source-bytes`) somente
atesta bytes locais quando a contagem **efetivamente lida** coincide
com o tamanho do `audit.db` físico registrado antes e depois da leitura.
Também rejeita sidecars SQLite WAL/SHM/journal que apareçam durante o
streaming. Duas leituras que devolvam um hash igual de um stream truncado
não comprovam o conteúdo completo da origem. A falha aborta o pacote
antes da criação de `consolidated-domain`, sem escrita nas AUDs ou
CONS nativo. Dois testes com streams truncados e acrescidos de bytes
confirmam a recusa e a preservação do arquivo de origem.

A verificação SHA-256 permanece prova de identidade dos bytes locais,
não prova autoria, frescor remoto, comparabilidade de scores/Apdex ou
legitimidade de uma consolidação longitudinal entre URLs diferentes.


## Estabilidade fisica do indice analitico em previas #210 (13/10/2026)

A previa domain_preview_from_index consulta a base local
.rasai/consolidated-index.db em modo SQLite ro&immutable=1, mas
esse modo nao bloqueia substituicao fisica do arquivo ou surgimento
de WAL enquanto as fontes AUD sao verificadas. Foi acrescentada
verificacao de st_dev, st_ino, st_size e st_mtime_ns antes da
consulta e **depois de construir o resultado**. Qualquer alteracao,
symlink ou sidecar -wal/-shm/-journal aparecendo nesse intervalo
bloqueia a emissao da previa.

Os descritores SQLite abertos pela previa e pela conferencia
opt-in de AUDs sao agora fechados explicitamente com
contextlib.closing, inclusive em excecoes, evitando reter
handles no Windows. A mudanca nao atualiza o indice,
nao abre modo de escrita, nao gera CONS nativo e nao
promove fingerprint por metadados a autenticacao de bytes.

Testes fisicos temporarios simulam substituicao atomica
por indice de conteudo identico, mudanca de mtime e
surgimento tardio de WAL, com e sem conferencia da AUD
original. A previa deve recusar todos os casos.
A fonte original da AUD e os motores homologados
permanecem inalterados. Para autenticacao forte de
conteudo, usar o contrato CDOM-v2 com hashes fisicos
ja existente; a previa analitica nao atesta isso.
