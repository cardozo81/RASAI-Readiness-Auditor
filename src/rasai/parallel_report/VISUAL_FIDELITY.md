# Visual Fidelity Pass — PR #698

Referência efetivamente encontrada em Downloads, extraída exclusivamente em
diretório temporário privado em 13/11/2026:
`rasai-relatorio-reestruturado.zip`.
SHA-256 validado: `6c124ecf7d5edc7b8d1f0c49afd8f8c54f45f23064340402271b27b62839180a`.
Nenhum HTML, JSON, imagem ou dado de cliente do ZIP foi copiado para o Git.

## Inventário da referência

Antes da implementação foram lidos o CSS/JS integrais e os H2 das dez páginas.
Tokens claros/escuros, tipografia Segoe UI 14,5/1,55, sidebar 224 px, main
max-width 1380 px, padding 36 px, shell gap 28 px e rail 190 px são os valores
efetivos após a cascata original. Foram identificados top sticky, rail com
IntersectionObserver, tw, chip, org, ruler/rh/rv/zl/bar/mk/rf/nt, grid, kv,
callout, stack, details.in e classes de gráfico SVG. O original contém regras
iniciais sobrescritas no final; preservamos a cascata, não apenas os primeiros
valores do arquivo.

CSS e JavaScript são portados diretamente da referência autorizada. Adaptações:
binding de larguras/markers por atributos numéricos finitos, tratamento de
ausência sem marcador, foco de teclado, navegação até evidências recolhidas,
tema manual opcional, impressão de detalhes e tabelas filtradas, contenção
de identificadores longos e sidebar móvel corrigida após a cascata.
O sort original foi corrigido para não remover o ponto decimal dos números
persistidos. Continua aceitando Enter/Space, pt-BR e aria-sort.

## Composição dinâmica

`page_views.py` define seções editoriais próprias: contexto/indicadores/riscos
no painel; captura e entidades; descoberta/padrões; índices e composição por
dimensão; contexto e achados semânticos; laboratório/campo/Apdex; SERP,
concorrência e Perplexity; segurança passiva; ações/correções/textos; consumo,
tentativas e proveniência. Registros completos/anexos permanecem acessíveis
na última camada de detalhe, preservando âncoras e crossrefs.

`components.py` fornece chips, selos, kv, tabelas, stacks e réguas. As zonas
SARI vêm do JSON versionado da PR e continuam PRODUCT_PROPOSAL. Métricas sem
faixa aprovada recebem escala neutra, não zonas inventadas. O marcador usa
valor real e clamp visual; o valor original não é alterado. Ausência não tem
marcador. Formatação compacta de valor mantém precisão original no title e
nos detalhes. Custos mantêm moedas separadas e composição por tentativa.

## Comparação e limites

Script reproduzível: `tests/report_presentation/compare_visual.py` com
`--prototype`, `--report` e `--output` para diretório privado novo.
Compara dez páginas nos viewports 1440×900, 1920×1080, 1280×800, 820×1180 e
390×844, produzindo 100 screenshots e JSON com 13 propriedades computadas
para 14 seletores. Exercita filtro real, sort por teclado, details, tema
automático e PDF A4. Não publica screenshots/dados privados.

Shell desktop: propriedades computadas de body/aside/main/top/shell/rail
coincidiram no recorte Índices/1440. Diferenças de largura dos componentes,
altura, chips e detalhes decorrem do conteúdo real, do tipo de details
comparado e do estado efetivo, não de uma certificação pixel-perfect.
A primeira comparação detectou overflow de caminho longo em Extração/390;
o wrapping foi corrigido e a segunda passou 50 pares sem overflow, JS ou rede.

Diferenças deliberadas: não aplicar classificação de prontidão por proposta;
escalas neutras onde não há thresholds aprovados; não inventar série temporal
para reproduzir gráfico CrUX do protótipo; sem incorporar imagem de cliente
do ZIP. As classes SVG/shot foram preservadas, mas série histórica e captura
visual não receberam adaptadores novos nesta rodada. Topbar mantém alternância
manual de tema em vez do botão de impressão; impressão funciona pelo navegador.
Identidade completa e evidência literal permanecem no detalhe, mesmo quando
isso altera alturas. Fidelidade da composição é parcial e requer aceite humano.

## Fronteira

Readers, SQLite, reconciliação de custos, generator e fontes não foram alterados.
Baseline: 41 passed in 11.85s. Testes adicionais cobrem tokens, réguas, ausência,
clamp, stacks e seções. Hashes e paridade da geração real devem ser consultados
no `_geracao.json` da nova saída; não se presume integridade de uma execução
anterior. Sem alteração em arquivo que existia na main base da PR.
