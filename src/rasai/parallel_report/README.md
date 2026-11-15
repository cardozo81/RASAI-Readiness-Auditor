# Relatório paralelo offline

```powershell
.\.venv\Scripts\python.exe -m rasai.parallel_report --audit-dir 'C:\caminho\AUD-ID'
```

O nome `rasai.parallel_report` foi autorizado para evitar sombrear o módulo
existente `rasai.report_presentation`. O finalizador da auditoria também usa este gerador.

Use uma AUD selada, sem escritor ativo nem arquivos WAL/SHM/journal. Não remova
sidecars para contornar a recusa do gerador. A entrada é `report-presentation/index.html`.
O gerador reaproveita um pacote íntegro com fontes e versão compatíveis. Quando
precisa atualizá-lo, valida a árvore em staging antes de substituir a anterior.
A mesma publicação migra as subpastas datadas das auditorias históricas.

Abra `index.html` por `file://`. São onze páginas, anexos JSON sanitizados,
assets locais, manifesto e mapa completo de cobertura. A página Rede e conectividade projeta somente observações persistidas/verificadas e mantém o aprofundamento no report-catalog. CSS/JS não usam rede.
Não publica cópias executáveis do HTML auditado. Não execute o módulo sobre
uma AUD que outro processo possa modificar durante a leitura.

Modelo: SQLite/artefatos → leitores → registros imutáveis → normalização → HTML.
Render não executa SQL. Nenhum módulo operacional é importado. Todas as
dependências de produção são da biblioteca padrão Python 3.13.

## Evidência e limites da primeira entrega

- Inventário integral de origem e hashes antes/depois, sem alterar AUD/catalog.
- Anexos contêm todos os registros consultados, com redaction de credenciais.
- Literais sanitizados não substituem a evidência original; hashes se referem
  ao original. Conteúdo binário é representado por tamanho/limitação.
- Vínculos usam identidade inequívoca; sem correspondência não há aproximação.
- Custos são conciliados por tentativa/moeda; sem token ou preço inventado.
- Faixas SARI 60/80/95 são proposta, não aplicadas ao score.
- Fonte sem estado explícito permanece não determinada, mesmo contendo dados.
- Snapshots canônicos permitem paridade de dados; paridade integral do HTML,
  aprovação visual e comparação ao ZIP ainda exigem aceite específico.
- Famílias adicionais são acessíveis por registros/anexos; layouts especializados
  para todas as variações históricas e interpretação de sidecars arbitrários
  não são certificados nesta versão.
- O wheel inclui explicitamente CSS, JavaScript, thresholds e mapa de cobertura.
  `tests/test_wheel_distribution.py` verifica os bytes dos recursos e a geração
  efetiva em venv não editável, com `python -I` fora do checkout, transporte/IA
  negados durante a geração e Chromium offline nas páginas essenciais.

## Verificação

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/report_presentation -q
```

O teste Chromium usa somente instalação existente. O manifesto não inclui
hash de si mesmo para evitar autorreferência; registra hashes de todos os
demais arquivos gerados. `source_writes=0` exclui somente a nova saída derivada.
Nunca interpretar existência de relatório como homologação da auditoria.
