# PR 718: cobertura editorial e homologação técnica da apresentação 0.4.14

## Escopo e causa reproduzida

Branch `fix/partial-aud-presentation-independent-715`, base inicial
`c7a695274620a20e731cd84cc06c3694ca99536a`. A PR continua sem merge.

`scope_context.editorial_evidence()` chamava o loader do companion privado.
Esse loader usa `document_advisory._snapshots()`, que exige `COMPLETED` e
conclusão terminal aceita. Na cópia isolada da AUD parcial, o erro reproduzido
foi `ValueError: AUD must be COMPLETED with an accepted terminal completion status`.
O gate disparava antes da leitura do DOM. Não era falta de captura nem falha
SQLite. Não foi alterado o contrato do companion nem o status da auditoria.

O adaptador de apresentação recebe as linhas já lidas, verifica bytes contra
o inventário inicial e hashes persistidos e reutiliza o worker estrutural
offline existente. Esse subprocesso tem limite de memória/tempo e bloqueia
rede e novos subprocessos. Não executa o loader, busca contextual, IA,
coletores, sondas ou scores. Uma projeção por snapshot é compartilhada por
Extração, Conteúdo e Search/GEO. Não existe cache global ou persistente.

## Correções e contratos

| Arquivo | Correção | Fonte e teste |
| --- | --- | --- |
| `capture_projection.py` | Adaptador para AUD parcial, leitura confinada, hashes, limites, RAW identificado e estados de erro sanitizados | Snapshot, DOM e sidecars; `test_executive_projection.py` |
| `scope_context.py` | Remove o gate terminal do caminho de apresentação; preserva FAQ/ARIA e verificações condicionais | Projeção compartilhada; testes de reconciliação e projeção |
| `page_views.py` | Achados com categoria de origem; ações aprovadas com prioridade persistida separadas de achados | `findings`, governança; teste de classificação e geração |
| `executive_evidence.py` | Sínteses específicas de extração, validação, competição, referências do AI Overview e governança | Famílias SQLite e referências verificadas; teste de amostra parcial |
| `history_projection.py` | Série CrUX reconciliada com datasets, JSON original, datas, dispositivo, escopo, métrica e p75 | Sidecar SQLite em modo imutável e JSON com SHA; testes de história válida e recusas |
| `generator.py` | Compartilhamento, recibos editoriais nos dois mapas existentes e recusa por integridade divergente | Testes de uma projeção, idempotência e preservação de publicação anterior |
| `presentation_acceptance.py`, `PRESENTATION_ACCEPTANCE.ps1` | Kit local com checkout limpo, SHA exato, fast-forward opcional, cópia, backup e validação offline | Resultado confidencial local e logs do operador |

Os novos estados distinguem fonte ausente, divergência de integridade, erro de
projeção, limite de recursos, processamento parcial, processamento não executado,
fonte materializada sem série comparável, resumo apresentado e detalhe técnico.
`PRESENT_TECHNICAL_ONLY` significa que o recibo não reivindica outra síntese
executiva. Ausência não significa resultado negativo. O recibo conserva
`certifies_editorial_completeness=false`.

Nos mapas, cada uso editorial associa página, tópico, família e estado. As fontes
incluem identidades persistidas e âncoras; capturas e sidecars incluem referência,
SHA-256 e escopo quando disponíveis. O inventário técnico continua separado do
contrato editorial. As heurísticas anteriores são substituídas pelos usos
explicitamente registrados para as famílias abrangidas, sem certificar 100%.

## Revisão dos onze HTMLs

| Página | Fonte e apresentação | Limite legítimo e regressão protegida |
| --- | --- | --- |
| `index.html` | Estado e requisitos existentes; nova síntese de achados, categorias, ações propostas/aprovadas | Achados não são riscos classificados ou ações aprovadas; sem prioridade inventada |
| `extracao.html` | Capturas, metadados e arquitetura mantidos; DOM por tag, trechos, evidências, arquivos distintos e estrutura verificada | DOM não é entidade; captura incompleta permanece explícita; dedup e cada `physical-N` preservados |
| `descoberta.html` | Métricas por ferramenta/escopo/estado e mensagens por tipo/subtipo persistido, com contagens | Sem severidade ou impacto SEO/GEO inferidos; detalhamento e serviços mantidos |
| `indices.html` | Distribuição das regras preservada e rastreada no recibo | `CORE_AUDIT=PENDING`; distribuição não equivale a score; SARI não calculado |
| `conteudo.html` | Categorias dos achados corrigidas; título, headings, canonical, qualidade, texto e tipos do sidecar quando disponíveis | Extração estrutural não executa avaliação semântica; FAQ pós-interação e intenção condicionais |
| `performance.html` | Indicadores existentes preservados; janelas CrUX de campo comparáveis com proveniência | Campo, laboratório e simulação separados; janelas sobrepostas não demonstram tendência/causalidade |
| `rede.html` | Captura passiva, TLS, IP remoto e mapa offline existentes preservados | Sem sondas, GeoIP, rota ou coordenadas fabricadas |
| HTML próprio de Search/GEO | SERP mantida; comparação com estado explícito, candidatos/páginas comparadas e referências verificadas do AI Overview; estrutura compartilhada | Resultado orgânico, referência de overview, citação do alvo e comparação executada distintos |
| `seguranca.html` | Inventário de recursos e integrações mantido e rastreado no recibo | Recursos não são vulnerabilidades; integrações não comprovam módulo completo |
| `plano.html` | Nova contagem factual de achados, ações dirigidas e aprovações; plano e governança existentes preservados | Nenhuma ação, prioridade ou decisão gerada pelo renderer |
| `ia-custos.html` | Previsão, consumo observado e tentativas preservados e rastreados | Zero parcial não significa custo final; nenhum token ou request inferido |

## Evidência real, privada

A homologação técnica usa uma cópia isolada da AUD de referência. O kit compara
o inventário completo da origem antes/depois, inclusive a apresentação anterior,
e protege o inventário de fontes da cópia. Valida `integrity_check`, identidade
de todas as linhas/esquemas, manifesto, anexos, âncoras únicas, todos os links,
onze páginas e reabertura idempotente. Os anexos não transformados têm igualdade
de bytes, enquanto HTML é comparado por seções e identidade dos registros.

Na execução local desta revisão foram demonstrados: 56 tabelas, 376 registros,
11 HTMLs, 73 hashes publicados válidos, 34 referências físicas e oito caminhos
únicos. A nova apresentação teve 2.478 referências locais válidas, zero links
ao catálogo, projeções estrutural e histórica disponíveis. O SHA do banco
permaneceu `6a334d3bae292c987d25e08803f7fb4221d0a19a455db60e667c6b02bae2419d`.
Chromium offline abriu as onze páginas em 1440 e 390 pixels, testou expansão,
modais, tema e overflow: 22 aberturas, zero requisições HTTP e zero erros JS.
Isso é homologação técnica automatizada; o aceite humano continua pendente.

A v0.4.12 foi regenerada com o último commit dessa versão antes da v0.4.13
(`6ace286`), em outra cópia isolada. O confronto com a v0.4.14 preservou os 56
anexos e todas as âncoras técnicas. As duas seções removidas foram substituídas
por títulos factuais: classificação dos achados e ações aprovadas com prioridade
persistida. Também foi comparada a apresentação real anterior v0.4.13. Não se
exige igualdade byte a byte de HTML modificado legitimamente.

Não publicar dados da captura, URLs de alvo, sidecars, screenshots, bancos,
backups nem relatórios confidenciais de aceitação no GitHub. Apenas o código,
fixtures sintéticas e este resumo sanitizado são versionados.

## Reprodução Windows

Em checkout limpo da branch obrigatória, usando o SHA integral publicado:

```powershell
& .\scripts\PRESENTATION_ACCEPTANCE.ps1 `
  -ExpectedSha '<SHA integral da PR>' `
  -AuditPath '<AUD original>' `
  -OutputPath '<nova pasta confidencial externa>'
```

`-UpdateFastForward` permite buscar a branch e atualizar somente por fast-forward,
recusando HEAD remoto diferente do SHA informado. São executados testes antes
de copiar a AUD. O destino precisa ser novo e externo à origem. O kit não
substitui a apresentação original: a saída revisável fica na cópia, com backup
confidencial. Falha técnica encerra com código diferente de zero; ausência de
Chromium não é PASS. O transporte local de wakeup do asyncio no Windows usa
socketpair; apenas loopback numérico é liberado durante o teste do navegador,
que opera offline com todas as requisições HTTP bloqueadas e contabilizadas.

Os resultados finais de pytest e dos workflows devem ser associados ao SHA
exato entregue. Falhas, skips e verificações não executadas não são aprovação.
Merge e exclusão da branch permanecem reservados à homologação humana.
