# Investigação #321 - Apdex de carregamento versus prontidão de conteúdo

Status: **investigação de código concluída; evidência amostral insuficiente para recalibrar qualquer índice**.
Controladora: #324. Gate de release: #310 / PR #312.

## Contratos de medição encontrados (código do HEAD do PR)

- **Apdex de navegação** - `m23_apdex_profiles.PlaywrightSyntheticNavigationGateway.measure()`: cronômetro `time.monotonic()` antes de `page.goto(..., wait_until="load")`, duração encerrada imediatamente depois. Task `NAVIGATION_LOAD` mede exclusivamente navegação até `load`, não disponibilidade material do `main`, estabilidade visual ou interatividade de SPA.
- **Apdex de experiência** - `m25_apdex_experience.Playwright...` também aguarda `load` e associa requests/XHR/fetch iniciados antes de seu limite ao tempo de `USER_ACTION_DURATION`. `settle_seconds` e `network_settled` são observacionais: não equivalem a um readiness gate. LCP/CLS, quando disponíveis, não certificam que o conteúdo principal ou a interação estejam prontos; INP sem interação autorizada não é inferível.
- **Persistência** - tabelas independentes `synthetic_apdex_samples` e `synthetic_ux_apdex_samples`; `m25_persistence.py` registra KPMs, tempos e classificação. Os dois motores não partilham contexto navegador nem identidade amostral com captura renderizada/classificador de arquitetura (`page_snapshots`).
- **Evidência real de SPA #315** - a AUD `AUD-3CDB4E407A6A40FDA5CAB5D82FA672A8` registrou `CSR_SPA`, `main=0 -> 4.049` caracteres e `POST_SCREENSHOT_DOM_MATERIALIZED`. Isso demonstra risco material de renderização tardia **na coleta captura renderizada**, não mede o atraso na sessão Apdex de navegação/Apdex de experiência. Atribuir 8 a 10 segundos de carregamento a estas amostras com base nessa captura seria erro causal.
- **Integridade do índice** - um resultado `SATISFIED` pode estar correto *para a task load* e ser mal interpretado como “conteúdo pronto”. Não existe, até aqui, demonstração de fórmula Apdex quebrada; não modificar classes, thresholds, distribuição, séries históricas ou score.

## Matriz de arquiteturas e hipóteses

| Classificação classificador de arquitetura | Falha de interpretação possível | Sinal adicional necessário na MESMA amostra |
|---|---|---|
| `STATIC_OR_SSR` | Recursos tardios pós-load ou streaming parcial | Texto principal já materializado em torno de load; não esperar universalmente |
| `HYDRATED` | HTML legível antes de listeners de interação | Observar DOM e, separadamente, interação real apenas quando autorizada |
| `CSR_SPA` | `load` satisfatório com skeleton/menu e conteúdo tardio | `main/article` significativo depois de load, com janela limitada |
| `MIXED` | Conteúdo parcialmente SSR, seções críticas CSR | Qual parte foi aferida, versão de seletor/materialidade |
| `UNKNOWN` | Inferência sem classe confiável | `NOT_APPLICABLE`/ausência; nunca supor atraso |
| Todas | Erro JS/404, redirect, cache, polling infinito, XHR late, LCP insuficiente | Evidência de estado, causa de censura e limite de observação |

## Diretriz de #322

Novo método **experimental** `APP_PRIMARY_CONTENT_READINESS` separado de Apdex de navegação/Apdex de experiência. Só considerar `OBSERVED` com marca monotônica `t_primary` e `t_load` da MESMA amostra e evidência DOM textual suficiente sem skeleton; calcular `delta_post_load=max(t_primary-t_load, 0)` exclusivamente neste contexto. Estado `TIMEOUT` é censurado, jamais satisfeito. `NOT_OBSERVED` para sinais inconclusivos; `NOT_APPLICABLE` sem elegibilidade/opt-in; `ERROR` em sonda inválida. Gravar `method_version`, `sample_id`, `page_id`, `device`, `architecture`, `window_ms`, `source`, `t_load`, `t_primary`, `status`. Para SPA/HYDRATED/MIXED sinalizadas, sondagem **opt-in**, curta, com CPU/rede limitadas; cache/perfil reportado. Evitar nova navegação e rede; nenhuma medição feita por varrer dados retrospectivos.

### Limites para adoção

Uma implementação in-process requer um hook no mesmo navegador do gateway de Apdex de navegação/Apdex de experiência. Como esses gateways são homologados e a mudança amplia timebound/custo dos samples, **não ativar instrumentação neles nesta rodada sem prova de overhead, contrato de persistência separado e regressões**. Implementar primeiro schema de observações independente/funções de validação sob testes fake e relatórios explicativos. A leitura cruzada captura renderizada/classificador de arquitetura com Apdex pode estratificar risco por `page_id, device`, mas **nunca** computar diferença temporal entre amostras não pareadas.

## Limitações do material disponível

O repositório fornece código e contrato; nesta inspeção via GitHub não foram recuperadas séries SQLite da AUD real. Não há base comprovada para quantificar p50/p75/p95 de diferenças entre `t_load` e `t_primary`, gasto extra por arquitetura, falsos positivos medidos ou “equivalência Dynatrace/RUM”. A conclusão metodológica é qualitativa, não estimativa numérica. Testes e medição controlada devem ocorrer antes de habilitar sonda de produção.

**Decisão:** permitir componentes aditivos isolados em #322, manter eventuais hooks Apdex de navegação/Apdex de experiência e estimativa de custos incrementais como gate condicionado; nenhum recálculo retroativo.


## Extensão isolada do contrato #322 (09/10/2026)

O classificador experimental agora aceita um modo adicional `strict_provenance=True`,
distinto da versão anterior: `APP_PRIMARY_CONTENT_READINESS-EXPERIMENTAL-002-STRICT-PROVENANCE`.
No modo estrito, o produtor precisa fornecer `sample_id`, `context_id`,
`page_id` e `device`, e **cada checkpoint** deve coincidir com a
identidade da mesma amostra/página/dispositivo. Dados heterogêneos => `ERROR`,
sem duração `primary_content_ms` ou delta `post_load_delta_ms` fabricados.
`STATIC_OR_SSR`, `UNKNOWN` e opt-out continuam `NOT_APPLICABLE`.
O contrato v1 permanece disponível e não foi reinterpretado.

**Não há hook Playwright, medição real, persistência nem novo índice nesta
iteração.** O classificador não lê nem escreve evidências do M23/M25, SARI
ou SCORE-GEO. Não transformar testes de checkpoint fake em homologação de uma
sonda real, e não declarar p75/p95 ou economia de latência sem amostras medidas.
A etapa operacional pendente é medir overhead e materialidade *na mesma amostra*,
com autorização humana explícita, janela curta e armazenamento independente.


## Adapter isolado de observação no mesmo page - #322 (09/10/2026)

O módulo `playwright_primary_content_probe_322.py` adiciona a função
`observe_existing_playwright_page` **opt-in**, aplicada somente a um objeto
`page` fornecido explicitamente por um consumidor que já detenha aquela
sessão de navegador. Recebe do **mesmo sample** a origem
`navigation_started_monotonic_ns`, `load_ms` e identidades
`sample_id/context_id/page_id/device`. Não cria aba, navegador, navegação,
rede, screenshot, OCR, estado SQLite ou nova task Apdex.

- Classifica somente `CSR_SPA`, `HYDRATED`, `MIXED`, com janela de
  100 a 3000 ms a partir do marco `load`, polling limitado de 100 a
  500 ms e sem tentativa se o prazo já tiver expirado.
- Em `page.evaluate` lê apenas texto de `main/article/[role=main]`,
  heading e skeleton/aria-busy. Exige duas observações positivas estáveis
  em pelo menos 100 ms e não transforma timeout em observação.
- Falha de DOM, referência de página ausente, relógio inválido e material
  malformado retornam `ERROR` sem vazar exceções de navegador. Leitura
  que ultrapasse o prazo de observação é censurada.
- O método é somente um **adapter de observação não instalado**.
  Não há hook ativo no ciclo M23/M25, nem persistência, nem dados reais.
  Tests com `Page` e relógio fake comprovam limites lógicos, **não**
  comprovam baixo overhead em navegador físico.

**Gate ainda obrigatório para uso produtivo:** instrumentar origem monotônica
no *mesmo* sample/gateway de Apdex, demonstrar identidade do objeto Playwright,
quantificar CPU/latência de `page.evaluate` em cenários SPA/SSR/cache,
estabelecer mecanismo de persistência isolado com checksum e UI advisory.
Somente depois decidir se o custo de processamento justifica habilitar o
probe; jamais alterar samples históricos, timebound e pontuação Apdex
homologados. O smoke humano da UI anterior não substitui esse gate.


## Persistência advisory **fora da AUD** (#322) - pós-merge 09/10/2026

`apdex_readiness_sidecar_322.py` acrescenta um armazenamento isolado e
não instalado no coletor. O consumidor fornece explicitamente uma
`PrimaryContentReadiness` **strict provenance v2**. Após a AUD estar
logicamente `COMPLETED/COMPLETE`, íntegra e com `report-catalog` vigente
(`catalog_report_is_fresh`), o módulo oferece:

- `write_readiness_sidecar(aud_dir, observation)`: arquivo JSON
  imutável e endereçado por digest SHA-256 em diretório-irmão
  `.rasai-readiness-sidecars/AUD-*/<sha256>.json`. O replay da mesma
  observação preserva bytes; arquivo adulterado não é sobrescrito.
- `read_readiness_sidecar(aud_dir, path)`: leitura conservadora com
  verificação de digest, vínculo à AUD de origem e aos hashes de
  `audit.db` e `report-catalog/manifest.json`; nunca vincula dados de
  outra AUD. `TIMEOUT/ERROR/NOT_APPLICABLE` jamais carregam latência
  materializada como se fossem sucesso.
- **NÃO altera** `audit.db`, `report-catalog`, manifests, M23, M25,
  thresholds, pontuação, RPR ou motor AI; tampouco produz chamadas
  comerciais.
- O campo `measurement_provenance=PRODUCER_DECLARED_SAME_SAMPLE`
  explicita a limitação: o sidecar prova **integridade do registro** e
  associação à fonte, **não** prova sozinho que o objeto Playwright e o
  cronômetro vieram da mesma amostra física.

A instrumentação produtiva e o relato de tempos medidos continuam
**PENDENTES**, condicionados a hook não invasivo no gateway, prova de
overhead, validação externa e revisão de confiabilidade. Nenhuma
métrica observacional nova é exibida automaticamente no HTML a partir
deste adapter sem a coleta real.


### Publicação atômica do sidecar #322 (09/10/2026)

O escritor de observações experimentais publica arquivos de digest
em **dois estágios**: monta integralmente um arquivo temporário no
diretório-irmão, flush/fsync, e só então publica o nome definitivo
via hard-link exclusivo. Replays não substituem arquivos existentes;
falhas de I/O nunca expõem JSON parcialmente escrito sob o nome
de evidência válido. A rotina descarta staging em falhas tratadas;
em interrupção abrupta poderá restar arquivo temporário ignorado
pelo leitor. Diretórios linkados do relatório original/sidecar
não são aceitos. Nada altera o pacote da AUD nem ativa o probe M23/M25.


## Integridade estrita da arquitetura no sidecar experimental (#322)

A camada imutável de prontidão aditiva rejeita registros
`OBSERVED`, `NOT_OBSERVED` ou `TIMEOUT` com arquitetura
`STATIC_OR_SSR` ou `UNKNOWN`: uma simples indicação de
`load` ou um producer externo não pode inventar um probe
aprovado para essas classes. `OBSERVED` também exige o
motivo de estabilidade de conteúdo `stable_primary_dom_text`.
O comportamento normal do M23/M25, scores, thresholds e amostras
permanece intocado. Isso **não prova uma medição real** nem
instala o sensor físico de mesma amostra nos navegadores.


## Validação defensiva dos checkpoints experimentais (#322)

O classificador puro rejeita valores de tempo não numéricos, NaN/infinito,
booleanos como duração, flags não booleanas, contagens textuais,
skeleton não booleano e coleções com mais de 128 checkpoints. Um relógio
monotônico fisicamente absurdo (>48h) também é inválido. A consequência
é estado `ERROR` sem materializar latência nem alterar o Apdex.
Essas validações são **somente sobre dados fornecidos pelo producer**;
não constituem evidência de sensor Playwright de mesma amostra nem medição
de overhead. Gate físico de #322 permanece aberto.
