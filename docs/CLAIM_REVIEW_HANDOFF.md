# Entrega ao revisor independente de alegacoes comerciais

**Issue:** #603 (integracao consultiva #604).
**Situacao:** modelo de encaminhamento, **nao e documento oficial**,
revisao autenticada, atestado SUSEP ou decisao juridica. O RASAi nao
assina ou autentica a fonte primaria em nome do revisor. Nao adquirir
documentos externos sem autorizacao distinta.

## 1. Arquivos por alegacao

O responsavel prepara uma pasta local privada **fora** da AUD selada
e do Git, contendo o manifesto e, para cada alegacao, `claim.txt`
(literal exato da captura), `conditions.txt` (bytes fisicos da
fonte primaria, sem normalizar) e `receipt.json` (decisao
independente assinada). Ate 50 alegacoes por manifesto. Identificar
versao do produto e documento, responsavel, vigencia, data de coleta
e base da autenticacao externa. Segredos devem ficar exclusivamente
no cofre do revisor/verificador.

### Modelo de manifest.json

```json
{
  "audit_id": "AUD-SUBSTITUIR-PELO-ID-REAL",
  "at_date": "2026-10-14",
  "claims": [
    {
      "claim_id": "CLM-A",
      "snapshot_id": "SNP-SUBSTITUIR-PELO-SNAPSHOT-REAL",
      "claim_file": "claim.txt",
      "document_file": "conditions.txt",
      "receipt_file": "receipt.json",
      "product_scope": "PRODUTO-E-VERSAO-EXATOS"
    }
  ]
}
```

O identificador do manifesto e apenas um rotulo ate ser confrontado
com `audit.db` e o artefato de `main_content_ref` da mesma AUD.
Os caminhos devem ser relativos sem symlink ou travessia.

### Modelo inicial de receipt.json (deliberadamente NAO ASSINADO)

```json
{
  "review": {
    "source_url": "https://fonte-oficial.example.invalid/condicoes",
    "document_sha256": "SUBSTITUIR-PELO-SHA256-REAL-DO-ARQUIVO",
    "effective_from": "YYYY-MM-DD",
    "effective_until": "YYYY-MM-DD",
    "reviewed_on": "YYYY-MM-DD",
    "collected_on": "YYYY-MM-DD",
    "product_scope": "PRODUTO-E-VERSAO-EXATOS",
    "claim_text": "TRANSCRICAO-LITERAL-EXATA-DA-AUD",
    "document_version": "VERSAO-OFICIAL-COMPROVADA",
    "issuer": "EMISSOR-VALIDADO-PELO-REVISOR",
    "reviewer_receipt_id": "ID-UNICO-DA-REVISAO",
    "reviewer_id": "ID-DO-REVISOR-INDEPENDENTE",
    "matched_excerpt": "EXCERTO-LITERAL-PRESENTE-NO-DOCUMENTO",
    "review_decision": "UNREVIEWED",
    "independent_source_authenticity_verified": false
  },
  "mac": ""
}
```

**ATENCAO:** este recibo nao passa no verificador enquanto houver
placeholders, `UNREVIEWED`, `false`, MAC vazio ou data nao valida.
Isso e intencional. Somente um revisor realmente habilitado pode
fundamentar a verificacao de autenticidade, escolher
`CORROBORATES` ou `CONTRADICTS` conforme o documento, indicar
um excerto literal e assinar a revisao com credencial privada
controlada fora do RASAi. O operador nao deve alterar a decisao
ou inventar dados para obter PASS.

## 2. Protocolo de assinatura independente

O emissor autorizado assina com **HMAC-SHA256** os bytes da
serializacao canonica do objeto `review`: UTF-8,
`json.dumps(review, ensure_ascii=False, sort_keys=True,
separators=(",", ":"), allow_nan=False)`.
A chave deve ter no minimo 32 bytes, estar sob custodia
independente e nunca acompanhar o pacote, aparecer no CLI,
em logs, issues, GitHub ou dentro da AUD. O campo `mac`
e o SHA-256 hexadecimal do HMAC da serializacao inteira.
Qualquer edicao do `review` apos assinatura invalida o MAC.

O documento e a identidade da fonte oficial devem ter
**autenticacao independente documentada** pelo responsavel.
Uma assinatura HMAC nao prova automaticamente legitimidade de
SUSEP, do segurador, nem conformidade legal.

## 3. Verificacao local apos recebimento

O operador injeta a chave em `RASAI_CLAIM_REVIEW_HMAC_KEY_HEX`
e IDs de revisores autorizados em
`RASAI_CLAIM_REVIEWER_ALLOWLIST` por ambiente privado,
sem expor seus valores. Em AUD fechada, ja existente:

```powershell
& ".\.venv\Scripts\python.exe" -m rasai.claim_review_batch `
    --manifest "C:\\REVIEW_PRIVADO\\manifest.json" `
    --audit-directory ".\\audits\\AUD-ID" `
    --require-collection-date --format json
```

Para resumir estados no contexto executivo consultivo (sem
alterar os HTMLs selados ou score):

```powershell
& ".\.venv\Scripts\python.exe" -m rasai.report_decision_matrix_cli `
    ".\\audits\\AUD-ID" `
    --claim-review-manifest "C:\\REVIEW_PRIVADO\\manifest.json"
```

**Aceite:** claims literalmente observadas no snapshot e
decisoes documentais autenticadas sao **eixos separados**;
sem fonte valida ⇒ `CLAIM_UNVERIFIED_EXTERNAL`, nao falsidade.
Nenhum codigo considera o recibo certificacao regulatoria.
Reter evidencias primarias/parecer sob custodia apropriada.


## 4. Revisao retrospectiva real (sem antedatar recibo)

A data da AUD em `manifest.at_date` e o marco **historico** de
aplicabilidade do documento (`effective_from <= at_date <= effective_until`).
O revisor independente pode emitir a revisao **depois da AUD**, com
`reviewed_on` real. Nunca usar uma data antiga ficticia so para obter
PASS. `collected_on` tambem deve ser real, nao posterior a
`reviewed_on`, e ambos devem acompanhar os fatos e a assinatura.
O verificador rejeita `reviewed_on` no futuro, assim como documento
fora da vigencia na data original da AUD. A revisao retrospectiva
nao reescreve a captura, nao prova legalidade e nao declara que o
revisor participou da auditoria historica.

**Contrato de fonte primaria:** o verificador atual exige
`document_file` com texto UTF-8 literal e tamanho ate 4 MiB para
confirmar `matched_excerpt` nos bytes apresentados. Um PDF binario
isolado NAO atende automaticamente esse contrato. Se o documento
original for PDF, revisor e custodiante devem documentar a cadeia
PDF oficial -> extracao/texto conferido, reter o PDF original, os
respectivos hashes e a proveniencia da extracao em registro privado;
nao declarar que hash de texto derivado autentica por si o PDF
oficial. Nao assinar um recibo sobre bytes diferentes dos fornecidos
para a verificacao. Ausencia de cadeia confiavel => N/D.

## 5. Gate automatizado de aceitacao documental e data fisica

O `manifest.at_date` nao e mais autoridade isolada quando o operador
exige `--audit-directory`. O verificador confronta **cada**
`snapshot_id` com `page_snapshots.captured_at` em UTC. A data do
manifesto deve ser igual a data UTC efetiva daquela captura M3;
falta de timestamp, timezone ausente, data de outra amostra e
coluna inexistente impedem promocao de corroboração/contradição.
Texto literalmente presente continua `CLAIM_OBSERVED`, mesmo com
`capture_date_matches_manifest=false`: o erro temporal nao apaga
o que foi realmente observado, mas impede atribuir a esta captura
um parecer documental de vigencia nao conferida.
Uma assinatura de revisor valida nao contorna esta verificacao.

Quando houver documento oficial versionado e recibo realmente assinado
pelo revisor externo, a homologacao de **integracao tecnica** pode
ser executada em uma unica chamada focal (offline, somente leitura):

```powershell
git pull --ff-only
& ".\.venv\Scripts\python.exe" -m rasai.claim_review_physical_gate `
    --audit-directory "C:\AUDS_PRIVADOS\AUD-ID" `
    --manifest "C:\REVISAO_PRIVADA\manifest.json"
```

Credenciais obrigatorias continuam restritas ao ambiente privado
(`RASAI_CLAIM_REVIEW_HMAC_KEY_HEX` e
`RASAI_CLAIM_REVIEWER_ALLOWLIST`); este comando nao assina em nome do
revisor e nao imprime claim literal, arquivo de origem, URL,
`reviewer_id` ou segredo. Estado
`AUTHENTICATED_REVIEW_AND_AUD_LINK_VERIFIED` so ocorre com
ao menos uma decisao assinada por revisor allowlisted, documento
versionado e texto literal vinculado a snapshot existente, data
de coleta obrigatoria e verificacao da integridade fisica apos o
consumo. Decisoes sem documento e sem recibo sao contadas como
nao verificadas, nunca como falsas. `NOT_VERIFIABLE` ou
`REVIEW_PACKET_OBSERVATIONS_ONLY_NOT_HOMOLOGATED` retornam exit 2.

**Limites:** este gate prova integracao dos contratos e a assinatura
do relato do revisor; nao certifica por si so identidade real do
emissor, documento oficial em portal ou capacidade juridica do
revisor. A autenticacao externa oficial, a fundamentacao e o aceite
independente precisam estar documentados fora do RASAi antes de
declarar homologacao regulatoria. Nenhum GET/SUSEP/API/IA, nenhum
reprocessamento de AUD historica e nenhum dado privado no GitHub.

## 6. Preflight automatizado, sem expor o pacote privado (22/10/2026)

Executar **uma vez** a descoberta read-only no Windows, com a branch
atualizada. O script opera sobre o armazenamento local indicado, sem rede,
sem downloads e sem alterar a AUD:

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
git pull --ff-only
& ".\.venv\Scripts\python.exe" ".\scripts\CLAIM_603_WINDOWS_ACCEPTANCE.py" --search-root "C:\IA-PROJETOS"
```

Quando a AUD tiver sido localizada fora dessa pasta, informar seu caminho
explicitamente com `--audit-directory "C:\CAMINHO\AUD-EAF..."`.
O resultado **PRIVATE_SIGNED_PACKET_REQUIRED** significa que o
vínculo físico está preparado, mas não existe ainda pacote documental
assinado pelo revisor. Não interpretar esse estado como teste reprovado
da implementação ou como fonte oficial validada.

Quando o revisor fornecer em diretório **privado fora do Git** um
`manifest.json` mais os `claim_file`, `document_file`, `receipt_file`
indicados (nenhum placeholder), executar uma única vez:

```powershell
& ".\.venv\Scripts\python.exe" ".\scripts\CLAIM_603_WINDOWS_ACCEPTANCE.py" `
  --audit-directory "C:\CAMINHO\AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF" `
  --manifest "C:\REVISAO_PRIVADA\manifest.json"
```

A chave de revisão real deve ser provida pelo **revisor**, em
`RASAI_CLAIM_REVIEW_HMAC_KEY_HEX`, junto da allowlist
`RASAI_CLAIM_REVIEWER_ALLOWLIST`. Nunca compartilhar seus valores
nem registrar os documentos no GitHub/chat; o script imprime apenas
metadados de captura, contagens e resultados redigidos. As variáveis
devem ser removidas do processo após o teste. Sem chave ou revisão real
retorna `PRIVATE_REVIEW_CREDENTIALS_REQUIRED` e não promove alegações.

Apenas `AUTHENTICATED_REVIEW_AND_AUD_LINK_VERIFIED` (exit 0)
com o comprovante independente real permite solicitar o aceite final
externo. O algoritmo verifica integridade e vínculo local; continua
**não** certificando origem legal/regulatória em nome da SUSEP.


## 7. Preparacao automatica do rascunho privado (22/10/2026)

A criacao de uma pasta vazia em `C:\RASAI-PRIVADO\603` NAO
cria `manifest.json`, fontes primarias ou recibos.
A execucao anterior com `--manifest` em caminho inexistente retorna
`PRIVATE_MANIFEST_MISSING` (em versoes anteriores:
`PRIVATE_PACKET_NOT_READY`). Os dois manifestos genericos
encontrados antes eram de outro contrato.

Para evitar gerar manualmente metadados de captura e para reaproveitar
a AUD ja homologada, o operador executa **uma unica preparacao local**:

```powershell
cd C:\IA-PROJETOS\github\RASAI-Readiness-Auditor
git pull --ff-only
& ".\.venv\Scripts\python.exe" ".\scripts\CLAIM_603_PREPARE_HANDOFF.py" `
    --search-root "C:\IA-PROJETOS" `
    --private-directory "C:\RASAI-PRIVADO\603"
```

O script le a AUD em SQLite `immutable=1`, verifica SHA-256
do banco/artefato antes/depois, identifica snapshot unico e
data UTC real, e grava **somente em pasta privada fora do Git**:
`manifest.template.json`, `REVIEW_REQUIRED.txt` e, se
houver texto literal apropriado no artefato observado, um
`claim.txt` **candidato ainda nao revisado**. O algoritmo de
selecao por termo nao autentica a interpretacao do texto.
Nunca escreve em `audit.db`, arquivo selado ou no diretorio Git;
nao sobrescreve arquivos existentes, nao faz HTTP, nao gera
`conditions.txt`, `receipt.json` ou `manifest.json`.

**Somente o revisor autorizado** pode conferir/corrigir a
alegacao, preencher o escopo exato de produto, obter documento
oficial autentico aplicavel a data historica, fundamentar a
correspondencia e assinar um recibo real fora do RASAi.
Ao concluir essa tarefa, o responsavel produz
`manifest.json` real (nao o modelo template) e preenche
os arquivos faltantes, respeitando o contrato desta pagina.
Sem isso `PRIVATE_MANIFEST_MISSING` e normal e
nao autoriza fechamento da #603. Nao levar estes arquivos
ao GitHub nem compartilhar claims/segredos no chat.
