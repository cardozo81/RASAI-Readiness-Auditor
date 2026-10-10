# Gate auditável de integridade local — #375

## Evidência comparável à última release tagueada

Em 10/10/2026 a última **release publicada** no GitHub é
`v0.8.0`, publicada em 07/10/2026, SHA canônico
`4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08`.
O baseline contém os invariantes de AUD, fulfillment/RPR,
CAT-01..CAT-10, report-catalog auto-verificável, Snapshot
SQLite, SARI-001 e SCORE-GEO-004.
A main `ff74e15d0a3d07be67b70a231d11ea7f59fbfc9d` está
46 commits à frente da tag e não descarta nenhum commit da tag
(consulta `compare/v0.8.0...main`).

A equivalência de contratos não significa que a AUD local foi verificada
pelo agente. **Sem os arquivos `audit.db` e `report-catalog`
dessa AUD, não é possível declarar integridade material específica.**

## Modo somente leitura

Com a **AUD concluída, console sem execução ativa e main local
atualizada**, execute:

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m rasai.audit_integrity_review_375 `
    --audit-dir ".\audits\AUD-3C3DD03BD7DC4A3082747AD28D545DBA" `
    --expected-ai-attempts 8 `
    --expected-web-calls 1 `
    --expected-navigation-attempts 10
```

O programa não abre conexão de rede, não executa processo RPR,
não reaudita a URL e não grava `audit.db`, HTML ou manifests.
Integra o verificador canônico `verify_catalog_report_package`
com `catalog_report_is_fresh` e efetua:
1. `PRAGMA integrity_check` integral, `PRAGMA foreign_key_check`, exatamente
   uma identidade AUD coincidente com o diretório;
2. `completion_status=COMPLETE`, quando a auditoria é declarada
   completa no console;
3. contagem M23 e M25: tentativas = válidas + inválidas =
   contagem de samples com `audit_id` na tabela correspondente,
   quando as tabelas e campos estão disponíveis;
4. manifesto, SHA-256 de arquivos, snapshot lógico SQLite,
   assurance, fingerprint da fonte e dependências de artefatos
   segundo o **código canônico atual**;
5. `actual_usage`: 2 ledgers IA (`ai_provider_attempts`
   e `content_remediation_attempts`), input/cache/output/
   reasoning/total tokens, custos técnicos estimados
   e tentativas externas WebPerf;
6. quantidade de runs Perplexity com `audit_id` quando persistida
   (zero significa nenhuma observação naquele audit.db, **não**
   comprova que a chave/configuração esteja desligada);
7. hashes de arquivos críticos antes/depois da leitura. Mudanças
   concorrentes impedem aprovação do gate.

O status `STRUCTURALLY_VERIFIED` exige aprovação conjunta das
verificações aplicáveis. `NOT_VERIFIED` com `errors` significa
necessidade de análise, não autoriza rematerializar, regenerar
dados nem excluir o diretório original. O resultado JSON não inclui
API keys ou conteúdos de IA, apenas contadores/estado técnico.

## O que não podemos concluir automaticamente

- SHA-256 e banco íntegro não comprovam que o modelo IA recomendou
  a estratégia correta, que o alvo respondeu corretamente ou que
  preço estimado equivale a invoice do fornecedor.
- O status **PARTIAL** de M23/M25 pode ser metodologia/suficiência
  amostral; não equivale a corrupção de registros.
- Se a Perplexity estiver `enabled=true`, chave presente, mas a
  próxima AUD **não tiver queries explicitamente solicitadas**
  no CAT-05, a operação correta é `NOT_REQUESTED` sem chamada
  comercial. Não existe herança automática de consultas SERP.
- O relatório GEO sem fonte Perplexity persistida deve informar
  ausência/N/D, não fabricar evidência.
- `v0.8.0` é benchmark de contrato, não checksum dos dados novos;
  comparar SHA-256 da AUD nova com a release não faz sentido.

## Operação após a verificação

Anexe ou cole o JSON gerado, preferivelmente junto de
`report-catalog/manifest.json` e `audit.db`, caso se deseje
análise mais profunda do conteúdo da AUD.
O reviewer não modifica bases históricas; se quiser exportar
um resultado faça redirecionamento explícito do terminal
para um caminho **fora da AUD**.

O console recebeu na #374 um gate final C/V mesmo quando não há
forecast monetário. Isso é separado da solicitação Perplexity:
sem pedidos explícitos não há POST Search API, independentemente de
`RASAI_PERPLEXITY_ENABLED=true`.
