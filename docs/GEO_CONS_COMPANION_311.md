# #311 - Companheiro GEO read-only no escopo de CONS-3

## Contrato implementado

`rasai.geo_cons_companion_311.build_cons_geo_advisory` recebe o diretório
local de um `CONS-*` e a raiz das auditorias originais. Lê o
`manifest.json` de CONS-3 e utiliza **exclusivamente os identificadores
`source_audits[*].audit_id`** para selecionar as AUDs. Não utiliza
`db_path` (possivelmente absoluto/injetado), não executa busca,
Perplexity, RPR, consolidação, IA ou rematerialização e não escreve
nenhum arquivo.

O componente encaminha as AUDs ao inventário longitudinal
`geo_longitudinal_311.build_geo_longitudinal_preview` já homologado,
reutilizando exatamente a elegibilidade GEO, a proveniência,
comparabilidade, deduplicação e os filtros conservadores de snapshots.
Saída opcional JSON/HTML standalone:

```powershell
.\.venv\Scripts\python.exe -m rasai.geo_cons_companion_311 `
  --audits-root .\audits `
  --cons-dir .\audits\consolidated\CONS-REFERENCIA `
  --format html
```

Restrições: manifest/HTML local seguro, diretórios sem symlink,
`cons_id` coerente, fingerprint sintático válido, `CONS-3`,
entre 2 e 100 AUDs explicitamente listadas, identificadores sem
`../` e únicos. Relatórios/artefatos originais permanecem idênticos
mesmo quando nenhuma coorte é elegível.

O campo `cons_reference` diferencia:
- `SOURCE_AUD_IDENTITIES_ONLY`: CONS lista nomes de fontes, não
  equivale a um certificado de integridade do próprio manifesto;
- `manifest_cryptographically_attested=false`;
- `native_cons_report_modified=false`;
- `integration_status=SEPARATE_READONLY_COMPANION_NOT_NATIVE_CONS`.

## Limite técnico e aceite

Esta é uma **ponte consultiva de leitura**, não uma nova seção do CONS
canônico. Não modifica `CONS-3`, seu `report.html`, manifesto,
fingerprint de agregação ou qualquer índice longitudinal.
`trend_conclusion=N/D` permanece enquanto escopo/intenção/mercado
evolutivos não estiverem metodologicamente validados.

Para eventual integração nativa é necessária versão explícita do
contrato de CONS que inclua os dados GEO no fingerprint e na política
de invalidação de cache, sem implicar comparabilidade da Search API.
O tema está também detalhado em
`docs/GEO_LONGITUDINAL_CONS_PREFLIGHT_311.md`.

Testes: seleção de fontes, relatório sem GEO, conjunto positivo
simulado apenas para verificar o encaminhamento, isolamento
de caminhos maliciosos, duplicações, ausência de escrita,
e fluxo HTML. As fixtures positivas GEO multi-AUD existentes
permanecem na suíte `test_geo_longitudinal_311.py`.
