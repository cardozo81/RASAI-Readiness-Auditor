# #311 - Pacote GEO consultivo derivado de uma seleção CONS

O comando `python -m rasai.geo_cons_package` produz um artefato
**independente** em `audits_root/consolidated-geo-companions/
GCOMP-<fingerprint>/{manifest.json,report.html}`.

A entrada é o manifesto de um relatório `CONS-3` já existente,
com 2 a 100 IDs de AUD explicitamente indicados, mesma seleção
read-only da prévia `geo_cons_companion`. Não lê caminhos
arbitrários do manifesto: cada base fonte é procurada somente em
`audits_root/AUD-.../audit.db`. A ausência de GEO verificável
resulta em exclusão com motivo e resultado N/D, não em
uma série sintética.

O manifesto versionado armazena hashes SHA-256 dos bytes do
manifesto e HTML do CONS original, das AUDs físicas que existirem,
IDs e fingerprint de requisição do CONS, e a projeção observacional
GEO completa. O HTML autônomo reaproveita o renderer com escaping
de texto não confiável. Uma seleção/source idêntica pode reutilizar
o pacote sem sobrescrita; conteúdo divergente é rejeitado.

Limites explícitos:

- **Não modifica** `CONS-*/manifest.json`, `CONS-*/report.html`,
  `audit.db`, snapshots GEO ou índices.
- `native_cons_modified=false` e `geo_trends_calibrated=false`.
  Nenhuma nova métrica GEO entra no score ou metodologia do CONS-3.
- Hashes locais confirmam quais bytes foram consultados, mas não
  autenticam a origem ou a equivalência externa dos dados de Search
  API/SERP. Relógios, intenção, market, locale e amostragem
  entre provedores continuam limitantes.
- Não há reprocessamento nem chamadas HTTP comerciais. Saídas
  são versionadas, sem alteração retroativa de auditorias anteriores.

Exemplo offline com habilitação explícita:

```powershell
python -m rasai.geo_cons_package `
  --audits-root .\audits `
  --cons-dir .\audits\consolidated\CONS-EXEMPLO `
  --write-geo-companion
```

A CI testa dados sintéticos com ausência de GEO, fontes faltantes,
identidade CONS adulterada, sidecars SQLite, symlinks e
idempotência byte a byte em Linux e Windows.

O pacote é um **companion consultivo separado**, não uma integração
nativa ao formato `CONS-3` produtivo. A issue #311 continua OPEN
para critérios metodológicos de tendências calibradas e eventual
integração formal sem romper fingerprints/contratos existentes.


## Checagem de concorrência e proveniência do GCOMP

O manifesto GCOMP não pode associar uma projeção GEO de um instante
aos hashes de uma versão posterior do banco. Além de comparar o
SHA-256 das origens, o materializador agora **recalcula a mesma
projeção read-only** após capturar os hashes e a compara integralmente
à primeira projeção. Em seguida, revalida todos os hashes e a
ausência de sidecars SQLite, antes de publicar **ou retornar um
pacote idempotente existente**.

Se uma AUD ou CONS for modificada, se a segunda interpretação GEO
divergir ou se aparecerem journals SQLite, a saída é recusada, sem
modificar os artefatos existentes. A verificação permanece local,
sem novas requisições de IA/Perplexity/SERP nem replay de coleta.
O contrato `RASAI-CONS-GEO-COMPANION-PACKAGE-311-001` continua
compatível: esta correção de integridade não reescreve manifestos
GCOMP históricos nem converte tendências N/D em métricas.


## Verificação imediatamente antes da publicação (#311)

A integridade das fontes CONS/AUD não é garantida apenas
pela comparação inicial da prévia: processos externos podem
alterar `CONS-*/report.html` ou criar um journal SQLite
durante a escrita dos arquivos temporários `GCOMP`.
O publicador agora chama novamente `reverify_sources()`
**após** escrever os arquivos de staging e **antes** do
`os.rename` atômico. A mudança ou perda de integridade
rejeita a publicação e remove os arquivos temporários.

Fixtures físicas reproduzem uma alteração no relatório CONS
e o aparecimento de `audit.db-journal` exatamente entre
a serialização e o rename, sem emitir pacote inconsistente.
Isto não constitui lock concorrente global nem substitui
comprovação de equivalência metodológica entre observações GEO.


## Acesso público ao companion GEO via CLI (12/10/2026)

A seleção CONS existente pode ser inspecionada diretamente pelo
roteador `rasai`, sem inicializar coletores, providers ou runtime de
auditoria, e sem escrever no CONS original:

```powershell
rasai geo-cons-review --audits-root .\\audits `
  --cons-dir .\\audits\\consolidated\\CONS-EXEMPLO --format html
```

Para materializar **somente um companion independente GCOMP**, o usuário
deve acionar expressamente a flag `--write-geo-companion`:

```powershell
rasai geo-cons-package --audits-root .\\audits `
  --cons-dir .\\audits\\consolidated\\CONS-EXEMPLO `
  --write-geo-companion
```

A segunda chamada com as mesmas fontes retorna `IDEMPOTENT_EXISTING`
quando bytes e manifestos permanecem idênticos. O pacote continua
separado em `consolidated-geo-companions/GCOMP-*`, e não promove
`trend_conclusion=N/D` a tendência calibrada ou métrica CONS-3.


## Segundo parse físico do manifest CONS (12/10/2026)

O materializador GCOMP consulta o companion GEO em modo read-only e, em
seguida, lê novamente o `manifest.json` canônico para compor seu pacote de
hashes. Esse **segundo parse** aplica a mesma rejeição de chaves JSON duplicadas
do leitor consultivo, inclusive `source_audits` e `audit_id` aninhados.
Um manifesto alterado ou ambíguo entre as leituras não pode trocar
silenciosamente a lista de AUDs dentro do pacote. Três testes com substituição
controlada apenas na segunda leitura verificam recusa antes da publicação,
ausência de requisições comerciais e preservação byte a byte das fontes.
A verificação SHA-256 e os gates anteriores/posteriores de publicação permanecem.
Nenhum arquivo CONS-3, AUD ou índice é alterado.


## Consistência do tamanho físico em ambas as extremidades do SHA-256 (12/10/2026)

O leitor local `_file_digest` exige, além do limite de bytes, que
**tamanho inicial = bytes efetivamente lidos = tamanho final**. Uma
truncagem ou ampliação de `manifest.json`, `report.html` ou
`audit.db` entre o primeiro `stat` e a abertura do stream não pode
ser aceita apenas porque o novo tamanho final coincide com a quantidade
lida. A recusa ocorre antes da publicação do companion GCOMP; não
modifica nenhum pacote CONS-3 ou AUD e não comprova autenticidade
externa. Duas regressões isoladas substituem bytes físicos justamente
nesse intervalo e verificam o bloqueio, sem rede ou coleta.
