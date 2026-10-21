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
