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

### Ação de captura no navegador (gerador 0.4.7)

O controle **Captura e prévia técnica local** abre explicitamente um `dialog` offline com **todas** as capturas persistidas, em vez de depender de um hyperlink `#capture-preview` que pode aparentar inatividade quando a seção de destino está recolhida. O modal reutiliza a infraestrutura de foco, Escape e fechamento; seus links são locais para prévia, contagens e inventário técnico. A regressão Chromium clica esse botão em desktop e mobile, verifica abertura, fechamento e navegação, inclusive com fragmento já presente. Sem chamadas de IA, rede, leituras do catálogo, mudanças em coletores, score ou UI estrutural.

### Captura visual diretamente no HTML (gerador 0.4.8)

Em `extracao.html`, **Prévia visual das páginas capturadas** fica visível na página, com imagens separadas por snapshot/dispositivo e ampliação opcional em modal. Não exige clicar para ver a miniatura e não depende de `report-catalog`. O screenshot é uma cópia byte a byte do raster original persistido (PNG/JPEG/WebP): somente referências confinadas, assinatura compatível, limite de tamanho, inventário original e SHA-256 pré/pós cópia são aceitos. Imagens ausentes ou inseguras são sinalizadas N/D, nunca inventadas. O manifesto e o verificador incluem hashes de todos os recursos visuais; nenhuma publicação é considerada íntegra se falta ou diverge um deles. A aparência segue o CSS e o modal existentes, sem redesenho geral. **Screenshots podem conter conteúdo sensível e o pacote com imagens permanece confidencial até avaliação específica para distribuição externa.**


### Arquivos físicos consolidados na extração (gerador 0.4.9)

A seção **Arquivos e referências físicas** de `extracao.html` apresenta cada caminho persistido **uma única vez**, com contagem de referências e SHA-256 (quando verificável). Ao expandir o arquivo, as observações originais permanecem individualmente acessíveis, incluindo origem, tabela/campo, trecho, cobertura e proveniência completa. Os identificadores e links existentes `#physical-N` não mudam: cada referência continua endereçável, inclusive quando o mesmo screenshot é referenciado por várias observações. Hashes divergentes e arquivos ausentes permanecem explicitamente sinalizados. É uma alteração apenas do HTML derivado; SQLite, evidências, captura, pontuação, catálogo, sanitização e IA não são alterados. A versão 0.4.9 força reconstrução de apresentações anteriores somente quando o operador chama o gerador.


### Cobertura de arquitetura e rede (gerador 0.4.10)

`extracao.html` apresenta agora um quadro executivo por captura com a **classificação arquitetural M6 efetivamente persistida**, estado de verificação RAW, contagens observacionais de recursos e hipóteses explicitamente não confirmadas quando a classe permanece `UNKNOWN`. A projeção reutiliza `read_architecture_audit_facts` sobre `audit.db`/artefatos da mesma AUD; não lê HTML técnico, não reclassifica SPA/SSR, não injeta IA ou altera coletores. IP, rota, ASN e GeoIP ficam exclusivamente em `rede.html`, com vínculo local dentro da apresentação.

`rede.html` distingue IP público **observado passivamente** de IP observado em sonda, rastreamento efetivamente persistido e causa operacional **não comprovada** na ausência do sidecar. Exibe histórico comparável somente para duas ou mais sondagens verificadas do mesmo host/porta, sem inferir causalidade ou topologia. Mapa, hops e GeoIP permanecem condicionais a coordenadas/saltos verificados. Nenhum link do HTML aponta para `report-catalog/`; o catálogo tem vida visual independente.

`0.4.10` invalida apenas manifestos anteriores de `report-presentation`, permitindo rematerialização deliberada, sem tocar em `audit.db`, `report-catalog` ou evidências-fonte.


### Mapa-múndi sem geolocalização comprovada (v0.4.11)

A página `rede.html` sempre apresenta o mapa-múndi offline Natural Earth. Na ausência de coordenadas GeoIP persistidas, o mapa é explicitamente rotulado como **cartografia de contexto sem pontos**, mesmo quando um IP público do servidor remoto foi observado passivamente. Um endereço IP isolado não fornece latitude/longitude e não identifica o IP de origem do usuário. O contexto visual não afirma geolocalização, localização física do servidor ou percurso. Quando sondas verificadas trazem coordenadas, a visualização anterior com marcadores, proveniência, raios de precisão e saltos comprovados permanece intacta. Nenhuma chamada HTTP, enriquecimento externo, coleta ou leitura do catálogo técnico ocorre no renderizador; os 11 HTMLs continuam offline.


### Comprovação de cobertura em todas as 11 páginas (gerador 0.4.12)

Cada HTML apresenta um painel local `Evidências materializadas nesta página` que deriva diretamente de tabelas persistidas e, em `rede.html`, de sidecars validados ou fallback SQLite autenticado. O painel informa **contagens por tema** e distingue ausência de registros de resultado negativo. Em Segurança, recursos do navegador são identificados como **telemetria**, não vulnerabilidades. Em Plano, não há geração de ações sem decisão/registro; a governança original permanece. As linhas detalhadas continuam acessíveis pelo inventário técnico da própria página; nenhum conjunto é copiado/duplicado nas sínteses. `anexos/dados-de-apoio/evidence-coverage.json` traz 11 recibos estruturados com estado por página e declaração explícita de que contagem técnica **não certifica completude editorial**; o arquivo integra o manifesto e seu hash de publicação. A tabela operacional `console_execution_projections`, quando presente, passa a ter inventário local no Painel em vez de apenas anexo técnico. Não há links externos ou dependência do catálogo. Toda ausência é declarada, jamais materializada por IA ou coleta silenciosa.


### Estados operacionais por página e lacunas reais (gerador 0.4.13)

Cada uma das onze páginas agora apresenta **Situação da execução e limites dos resultados**, separada da contagem de evidências. A origem é exclusivamente o contrato `audit_fulfillment_contracts` e os itens `audit_fulfillment_work_items` persistidos na mesma AUD; os motivos são traduzidos apenas para códigos canônicos conhecidos. `REQUESTED_NOT_EXECUTED`, `NOT_CONFIGURED`, `SUCCESS`, `NOT_REQUESTED` e ausência de requisito são estados distintos; nenhum é confundido com resultado negativo de medição. A capa comunica requisitos atendidos, pendentes, bloqueados, pontuação pendente e elegibilidade de consolidação. Índices separam 27 regras de scores não consolidados; segurança separa recursos da captura de uma execução formal; plano distingue ações não materializadas de ações recusadas; IA e custos distingue previsão de consumo observado; SERP não presume Perplexity ou citação generativa. Uma causa só é atribuída quando `last_error_code` a comprova, sem renderizar mensagens de erro livres ou segredos.

O recibo estruturado `anexos/dados-de-apoio/evidence-coverage.json` ganha o objeto `execution`, com estado por página e indicação explícita de que não certifica completude de coleta. Não são adicionados arquivos à publicação. O gerador permanece determinístico, sem coleta, IA, rede, alterações no banco, pontuação, catálogo ou CSS/UX. Corrigida também uma ocorrência de nomenclatura obsoleta nos identificadores internos do inventário, preservando o destino HTML canônico.


Dentro do mesmo quadro operacional da v0.4.13, os detalhes editoriais adicionais são **agregações determinísticas das fontes já persistidas**, nunca reclassificações: `indices.html` apresenta a distribuição dos 27 resultados de regras, sem fabricar índice geral; `seguranca.html` resume tipos e partes dos 87 recursos, além do estado individual das cinco integrações, sem chamar recursos de vulnerabilidades; `ia-custos.html` explicita previsão, valor parcial observado e comparabilidade do registro financeiro, sem sugerir custo final quando a AUD permanece parcial. Os anexos e os inventários de origem continuam intocados e com a mesma identidade; a síntese não repete cada ocorrência.


### Contrato 0.4.20 - anexos endereçados por conteúdo (P11/P12)

Cada família de tabela persistida tem uma entrada em `_geracao.json.table_annexes`,
associando o nome da tabela ao arquivo `anexos/<SHA-256-dos-bytes-UTF-8>.json`.
O conteúdo é sanitizado e serializado uma única vez, de modo determinístico;
tabelas com bytes idênticos compartilham o arquivo sem perder seu mapeamento.
Os anexos técnicos estruturados da apresentação continuam sob `anexos/`.

Os recibos `coverage-map.json` e `evidence-coverage.json` agora pertencem a
`anexos/dados-de-apoio/`, não a `assets/`. Os bytes desses recibos não são
reescritos pela migração de caminho; o manifesto registra seu SHA-256 efetivo.
O contrato `CONTENT_SHA256_V1` é obrigatório em pacotes novos; layouts antigos
só são reconhecidos quando a leitura de histórico explicitamente permite legado.
Nenhuma operação regrava `audit.db`, `report-catalog` ou a evidência de origem.
A formatação temporal da projeção financeira usa o timezone da apresentação,
sem modificar timestamps persistidos nem arquivos JSON anexos.


### Triagem editorial por fonte (issue #722, gerador 0.4.21)

A publicação gera `anexos/dados-de-apoio/editorial-review.json` com uma
entrada para cada família SQLite, inclusive tabelas vazias. O recibo distingue
origem, quantidade, estado registrado por linha, página, referência navegável,
campos analíticos efetivamente projetados, síntese registrada e prioridade de
revisão. Os tópicos antes classificados como `PRESENT_TECHNICAL_ONLY`
recebem classificação explícita, sem convertê-los em conclusões.

O Painel mostra as contagens do inventário e as lacunas de decisão em
expansão opcional; cada página apresenta seu mapa de fontes em `details`
fechado por padrão, reutilizando a navegação e as tabelas existentes.
Não existe dependência de `report-catalog`, mudança de pontuação, coleta,
IA ou alteração do banco. Sidecars de rede e histórico são descritos
separadamente, apenas nos estados que os recibos já comprovam.

A política editorial identifica lacunas de síntese/análise sem inventar
aprovações. Novas famílias sem política entram em revisão, nunca são
silenciosamente marcadas como técnicas. A evidência de cobertura de 100%
das famílias **não é** aceite editorial humano: ambos os recibos preservam
`certifies_editorial_completeness=false`. A homologação da AUD real,
inspeção visual e decisões de materialização ainda são obrigatórias.
