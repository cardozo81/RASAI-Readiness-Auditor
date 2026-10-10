# #322 - Gate A/B offline de custo da sonda experimental

## Status real

`src/rasai/readiness_matched_pilot_322.py` adiciona um avaliador
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
.\.venv\Scripts\python.exe -m rasai.readiness_matched_pilot_322 `
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
