# RASAi 0.10.0 - notas da release

**Release publicada.** `v0.10.0` foi publicada em 15/11/2026 como GitHub Release
`RASAi 0.10.0`, final (não draft e não prerelease). Estas notas preservam o
delta preparado até a base `09ff011ba1c9d12e6a6dfa07397dc9ae37ca2a42`;
o ciclo de publicação foi concluído posteriormente na `main`.

## Capacidades adicionais desde v0.9.2

- Apresentação executiva offline em `report-presentation/index.html`, com dez
  páginas, anexos sanitizados, manifesto e recursos locais. O catálogo técnico
  `report-catalog/` conserva sua função e seus caminhos.
- Publicação da apresentação com staging, validação, reutilização e atualização
  por origem/versão; recuperação de apresentações históricas somente na ação
  explícita de abertura. No console, `I` abre o catálogo, `A` a apresentação e
  `B` busca pelo Audit ID.
- Leitura contextual GEO/SEO e análise reversa do conteúdo já capturado, com
  qualificação de FAQ, hipóteses editoriais, proveniência e limites explícitos.
  Companheiros documentais offline usam fontes locais autorizadas; o extra
  opcional `documents` oferece extração de PDF sem OCR ou nova coleta.
- Proveniência de filtros solicitados à Search API separada de escopo efetivo
  comprovado. Coincidência de filtros não comprova equivalência de população,
  dispositivo, intenção ou citação generativa.
- Correções de apresentação para autoria JSON-LD, governança por identidade,
  amostragem, cronologia, custos observados/estimados e tokens desconhecidos.
  Ausência permanece N/D, distinta de zero.

## Correção de distribuição da candidata

O wheel da base pós-v0.9.2 foi construído e instalado sem modo editável fora
do checkout. A geração sintética falhou por ausência de `assets/site.css`;
também faltavam `app.js`, `thresholds.json` e `coverage-map.json`.

O preparo declara explicitamente esses quatro recursos em `package-data`.
Seus bytes, o gerador, CSS, JavaScript, layout e navegação permanecem inalterados.
O teste `tests/test_wheel_distribution.py` constrói um wheel em cópia descartável,
confere recursos de apresentação e configuração, instala em venv não editável e
executa com `python -I` a partir de outro diretório.

O gate confere versão do pacote/metadata, geração B, arquivos e hashes do
manifesto, links locais, preservação dos insumos sintéticos e reutilização.
Durante a geração, transportes e invocações do orquestrador de IA são negados.
Chromium offline exercita páginas essenciais em desktop/mobile e verifica
erros JavaScript, recursos, navegação, expansão e tema. Build/instalação podem
obter dependências Python; isso é separado da geração sem rede.

## Compatibilidade e limites

- `0.10.0` identifica novas capacidades compatíveis; não é decisão de maturidade
  pública `1.0.0`. As duas fontes canônicas da versão do auditor são atualizadas.
- `SARI-001`, `SCORE-GEO-005` vigente e `SCORE-GEO-004` histórico não mudam.
  Não há recomputação, alteração de `auditor_version` histórico ou migração
  destrutiva de AUD/RPR/CONS.
- A apresentação continua derivada, sem substituir o catálogo nem seu gate
  canônico. A API HTTP continua servindo apenas a superfície autorizada do catálogo.
- IA contextual paga e comparabilidade positiva de provider continuam sujeitas
  a autorização/evidência próprias. Testes offline não homologam faturamento,
  qualidade de modelo real, ranking ou causalidade.
- A auditoria parcial de referência conserva PRELIMINARY, score PENDING e quatro
  pendências históricas. A homologação de conteúdo da COMPLETE não a promove.
- A comprovação de distribuição usa AUD sintética descartável. Os recibos reais
  da apresentação são reaproveitados no seu SHA; não houve novo teste físico,
  coleta ou reprocessamento das auditorias homologadas.
- Ajustes documentais limitam-se à identidade da candidata, apresentação e fatos
  de versão incorretos. Não executam a sanitização global pós-1.0.0.

Resultados, HEAD exato, runs e limitações da candidata são registrados na PR.
O [checklist específico](RELEASE_CANDIDATE_V0_10_0.md) separa os gates posteriores.
