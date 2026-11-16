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
assets locais, manifesto e mapa completo de cobertura. A página Rede e conectividade projeta somente observações persistidas/verificadas e mantém o detalhamento na própria apresentação. CSS/JS não usam rede.
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


## Paridade semântica após a #710

O HTML do `report-catalog` **não é fonte de fatos para este gerador**. Quadros executivos recebem registros diretamente de `audit.db` e sidecars verificados. Nenhum hyperlink de detalhe técnico exige o catálogo. Prévia, modal, inventário local e anexos JSON compõem uma navegação autônoma.

O `coverage-map.json` versão **3** distingue anexo preservado, registro navegável, síntese editorial e conclusão/decisão; existência de tabela ou link não certifica autonomia executiva. Propostas sem decisão permanecem fora do plano aprovado. A projeção contextual SEO/GEO mantém hipóteses condicionais e estado de verificação; a consulta de rede reaproveita um avaliador determinístico sobre observações já persistidas. Geração não faz consultas de IA nem novas medições.

O gerador interno `0.4.1` invalida pacotes de apresentação antigos da linha `0.4.0`; a versão do produto não muda. A homologação semântica da AUD real e o aceite visual continuam gates independentes do manifesto e do CI.


### Vocabulário e rede independente (gerador 0.4.3)

Todas as superfícies executivas usam rótulos pt-BR por campo, inclusive cabeçalhos, tabelas, chip, tooltip e modal. O JSON original e os IDs canônicos ficam sob seções declaradamente técnicas. O botão de rede abre modal local; o mapa SVG offline é exibido quando a sonda autorizada persistiu coordenadas válidas, ou há justificativa explícita de ausência. Não requer `report-catalog` para esta funcionalidade. A versão do gerador força atualizar os históricos sem recalcular pontuação ou realizar nova coleta.

## Autonomia editorial (gerador 0.4.6)

A navegação para detalhe técnico é local, sem links para report-catalog. Classificação competitiva e motivos conhecidos são interpretados por regras determinísticas pt-BR, sem inferir concorrência comercial. Timestamps tipados visíveis são exibidos no fuso IANA persistido na auditoria; os valores originais permanecem nos anexos e SQLite. A pontuação, os motores de coleta e a sanitização de credenciais não foram alterados. Travessões U+2014 são substituídos por hífens somente no HTML da apresentação.
