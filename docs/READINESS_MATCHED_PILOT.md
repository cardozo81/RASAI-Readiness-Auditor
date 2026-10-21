# #322 - Gate A/B offline de custo da sonda experimental

## Status real

`src/rasai/readiness_matched_pilot.py` adiciona um avaliador
**puramente read-only** de pares de execuções locais control/probe.
Ele pode ser utilizado após medir diferentes amostras de navegação
equivalentes com a sonda experimental de conteúdo. O avaliador não
aciona Playwright, M23, M25, Dynatrace, rede, SQLite nem gera AUD.

Os pares devem informar exatamente o mesmo `page_id`, device,
arquitetura (CSR_SPA, HYDRATED ou MIXED), browser_version,
network_profile, cpu_profile, context_profile e navigation_url.
Os IDs de amostra dos dois braços devem ser distintos, únicos e
apoiados por durações finitas medidas, não tempos inferidos entre
coletas. O braço probe deve informar `enabled=true`,
`source_page_reused=true` e a identidade **declarada** pelo produtor
`CALLER_DECLARED_NOT_ATTESTED_BY_M25`.

Por padrão, são exigidos pelo menos 5 pares (máximo 200) e um orçamento
local explícito de 30 ms. Esses valores são **critérios operacionais de
piloto**, não thresholds oficiais Dynatrace, não SLO homologado
e não substituem orçamento de produção aprovado.

### Exemplo de análise offline

```powershell
.\.venv\Scripts\python.exe -m rasai.readiness_matched_pilot `
  --json .\readiness-pairs.json `
  --budget-ms 30 `
  --min-pairs 5
```

O JSON deve ter um objeto `pairs` com itens do seguinte formato:

```json
{
  "pairs": [
    {
      "page_id": "PAGE-ONE",
      "device": "MOBILE",
      "architecture": "CSR_SPA",
      "browser_version": "Chromium TEST",
      "network_profile": "offline-fixture",
      "cpu_profile": "unthrottled-local",
      "context_profile": "viewport=390x844",
      "navigation_url": "http://localhost/fixture",
      "control": {
        "sample_id": "CTRL-1",
        "load_duration_ms": 120.0
      },
      "probe": {
        "sample_id": "PROBE-1",
        "load_duration_ms": 128.0,
        "active_probe_wall_ms": 8.0,
        "enabled": true,
        "identity_proof": "CALLER_DECLARED_NOT_ATTESTED_BY_M25",
        "source_page_reused": true
      }
    }
  ]
}
```

O exemplo de um par é insuficiente para obter estatísticas: o retorno
será `NOT_EVALUABLE`. Para N pares válidos, o diagnóstico
apresenta delta de wall time mediano/P90, overhead ativo máximo
reportado e adequação **ao orçamento declarado**.

## Gates incondicionais não satisfeitos

Mesmo que um piloto satisfaça 100% do orçamento local,
`gateway_identity_attested=false` e
`m25_production_activation_approved=false` permanecem.
A comparação não prova que os callbacks do motor M25 produziram
as identidades/relógios, nem que o perfil do navegador real da
AUD foi o mesmo. É necessário demonstrar instrumentação com
identidade material e monotonic clock da amostra M25, baseline
físico pareado, nível de overhead definido e autorização de
feature flag antes de coletar ou publicar como medida de produção.

**Proibido** recalcular Apdex, reclassificar amostras M23/M25,
afirmar pronta a página por HTTP 200/load/networkidle, misturar
tempos de browsers distintos ou modificar auditorias históricas.
Fixtures positivas/negativas e CI Linux/Windows garantem apenas
o contrato do avaliador e a separação de responsabilidades.

## Vínculo de sample_id persistido com observação física

Quando o runner M25 recebe um `advisory_same_page_observer` explícito,
o orquestrador pré-aloca um `UXA-*` único **antes da medição**, entrega
o mesmo identificador a `set_experimental_sample_scope` e grava
exatamente esse ID na linha `synthetic_ux_apdex_samples`. O callback
recebe também `audit_id`, `page_id` e `context_id`, além do relógio
monotônico e da página viva. Com opt-in desabilitado, mantém-se o
comportamento anterior de gerar `UXA-*` apenas na persistência.

Essa vinculação evita **inventar** identidade M25 a partir de
`page.url` ou capturas M3 tomadas em outra sessão. O testemunho FAQ
feito em M3 e a prontidão em M25 são **amostras distintas**, salvo
prova independente em contrário. A disponibilidade do callback não
instala uma coleta universal: sua injeção, orçamento, pareamento A/B
físico e armazenamento consultivo separado ainda dependem do operador.

## Opt-in no coletor de experiência e sidecar após o selo (#322)

A entrada `audit` permite `--experimental-readiness-architecture=CSR_SPA`
(com alternativas `HYDRATED`, `MIXED`, `STATIC_OR_SSR`, `UNKNOWN`)
e `--experimental-readiness-window-ms=1200` opcional
(intervalo de 100 a 3000 ms). O catálogo de experiência precisa estar
habilitado normalmente; em modo estático ou de arquitetura incerta,
a sondagem é dispensada em vez de inventar prontidão.

O coletor reserva uma identidade `UXA-*` antes de cada medição opt-in,
usa o mesmo contexto e relógio monotônico e grava a mesma identidade
na tabela canônica de amostras. O resultado consultivo é mantido
em memória até depois da selagem do pacote. Antes da publicação,
o publicador confere a linha física
`audit_id/sample_id/page_id/device` no SQLite somente leitura e
materializa um sidecar independente via mecanismo existente.

Os dados históricos, fórmulas, índices Apdex e métricas base são
inalterados; falhas/timeout permanecem censurados. Não é um novo
índice de experiência. Para homologação metodológica ainda é
necessária medição A/B física de overhead, no mesmo perfil e URL
autorizados, antes de disponibilização irrestrita.

## Apresentação consultiva separada do pacote homologado

Um suplemento HTML estático e sem JavaScript apresenta os sidecars
de prontidão materializada e censurada em seções de leitura
`CAT-06` e `CAT-07`, mantendo a distinção explícita
entre **Apdex de carregamento** e **prontidão de conteúdo**.
Ele é gerado automaticamente, após o selo da AUD, quando há
evidência experimental; também pode ser gerado novamente sem coleta:

```powershell
.\.venv\Scripts\python.exe -m rasai.experimental_observation_report --aud-dir .\audits\AUD-ID
```

O arquivo complementar é criado em
`.rasai-experimental-reports/<AUD-ID>/<SHA256>.html`, fora
do `report-catalog` selado. Os registros só entram na tabela
quando o verificador do sidecar confirma o SHA-256 do próprio
JSON, a fonte AUD e o manifesto. Arquivos inválidos são
contabilizados como recusados, sem promover `TIMEOUT` a sucesso.
O HTML usa escape de texto, CSP sem scripts ou rede, e
publicação atômica sem sobrescrever um relatório existente.
O CLI informa o caminho para abrir o suplemento.

Este documento **não afirma** inserção automática de elementos
dentro de `cat-06.html` / `cat-07.html`: fazê-lo após o selo
invalidaria a integridade histórica. O suplemento é a
apresentação adicional com seções rotuladas pelos catálogos,
sem substituir o relatório original. O gate físico A/B de
overhead e eventual decisão sobre integração ao pacote
principal permanecem independentes.

## Medição de custo ativo na amostra M25 real - entrega aditiva

Sob opt-in existente, o callback M25 reutiliza o observador cronometrado
`measure_existing_playwright_probe_cost`, sem criar navegador ou outra
navegação. A medição M25 normal é congelada **antes** dessa avaliação.
A espera por estabilidade DOM é separada de CPU/avaliação ativa; o status
da prontidão mantém o contrato anterior e a duração Apdex não é recalculada.

Após a selagem, o sidecar de prontidão pode conter `probe_cost`
limitado e vinculado ao mesmo `audit_id/sample_id/page_id/device`.
O suplemento CAT-06/CAT-07 apresenta o custo ativo observado; sidecars
antigos não têm telemetria e mostram N/D. Os dados são declarados pelo
produtor e **não** substituem 5 pares físicos controle/sonda, orçamento
de overhead aprovado ou aceitação de mesma amostra. Não há consultas
a provedores nem alteração do SQLite ou dos relatórios canônicos.
