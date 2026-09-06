# Synthetic User Experience Apdex — M25

## 1. Finalidade

O M25 adiciona ao SearchGEO um **Synthetic User Experience Apdex calibrável**, separado do M23 `Synthetic Navigation Apdex` Standard.

A distinção é obrigatória:

| Domínio | Natureza | Task / população | Thresholds |
|---|---|---|---|
| M23 | laboratório sintético controlado | `NAVIGATION_LOAD`, por URL/dispositivo | `T` e `4T` conforme Apdex Standard |
| M25 | laboratório sintético enriquecido/calibrável | `SYNTHETIC_LOAD_ACTION`, mix explícito de dispositivos | Satisfied e Frustrated independentes ou importados |
| Dynatrace RUM | usuários reais | user actions reais observadas no período | configuração efetiva da aplicação/action |

M25 **não é RUM** e não deve ser usado para prometer igualdade numérica com Dynatrace. Ele reduz diferenças metodológicas controláveis — KPM, thresholds, política de erros, sessão e mix de dispositivos — para tornar o delta restante mais interpretável.

## 2. Pré-requisitos

- dependências normais do SearchGEO instaladas;
- Chromium Playwright disponível;
- autorização para executar navegações repetidas contra o alvo;
- M23 habilitado com `T` explícito;
- quando houver importação live do Dynatrace, `DYNATRACE_API_TOKEN` definido no ambiente.

O token Dynatrace não possui flag CLI e não é persistido pelo SearchGEO.

## 3. Smoke humano recomendado — calibração manual

Use primeiro uma URL autorizada e um volume baixo. O objetivo do smoke é validar fluxo, persistência e relatório, não estabilizar estatisticamente o score.

PowerShell:

```powershell
python -m searchgeo audit "https://SEU-ALVO/" `
  --max-pages 1 `
  --device-context mobile `
  --ai-provider none `
  --no-web-performance `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.0 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-delay-seconds 1 `
  --apdex-concurrency 1 `
  --apdex-experience `
  --apdex-experience-samples 10 `
  --apdex-experience-max-attempts 13 `
  --apdex-experience-max-pages 1 `
  --apdex-experience-device-mix "mobile=60,desktop=30,tablet=10" `
  --apdex-experience-session-mode cold `
  --apdex-experience-kpm USER_ACTION_DURATION `
  --apdex-experience-satisfied-seconds 2.0 `
  --apdex-experience-frustrated-seconds 6.0 `
  --apdex-experience-errors `
  --apdex-experience-error-scope first-party `
  --apdex-experience-settle-seconds 5 `
  --apdex-experience-delay-seconds 1 `
  --apdex-experience-concurrency 1
```

`1.0`, `2.0` e `6.0` acima são **valores de smoke**, não recomendações universais e não são declarados como defaults do Dynatrace. Para comparação real, substitua-os pela configuração efetiva conhecida da aplicação.

Com 10 amostras M25 e mix `60/30/10`, a alocação esperada é:

```text
MOBILE  = 6
DESKTOP = 3
TABLET  = 1
TOTAL   = 10
```

O M23 com 5 amostras será corretamente marcado como grupo pequeno diagnóstico; isso é esperado no smoke.

## 4. O que verificar no smoke

Após a execução:

1. a auditoria principal continua concluindo independentemente do M25;
2. `report/apdex.html` existe e mantém a metodologia M23 `T/4T`;
3. `report/apdex-experience.html` existe;
4. o menu do report contém `Apdex calibrado` somente quando a página existe;
5. `apdex-experience.html` mostra KPM, Satisfied/Frustrated, error policy, session mode e mix;
6. aparecem grupos `POPULATION`, `MOBILE`, `DESKTOP` e `TABLET` conforme o mix;
7. o total das amostras válidas da população corresponde à soma dos devices;
8. a página M25 mostra o score M23 Standard quando o contexto equivalente estiver disponível;
9. XHR/fetch, recursos tardios e erros aparecem somente quando observados;
10. `console.error` não força `Frustrated` sozinho;
11. erro qualificável força `Frustrated` quando `errors_affect_apdex=true`;
12. nenhuma alteração ocorre em `SCORE-GEO-002`, `SGRI-001`, findings ou recomendações GEO.

## 5. Verificação de persistência

No `audit.db`, quando M25 executa, devem existir:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

As tabelas M23 continuam separadas em `synthetic_apdex_*`.

O grupo consolidado por página usa:

```text
device = POPULATION
profile_id = MIXED_DEVICE_POPULATION
```

A fórmula permanece:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

## 6. Conferência de segredo Dynatrace

Quando usar importação Dynatrace, defina o token apenas no ambiente:

```powershell
$env:DYNATRACE_API_TOKEN = "seu-token"
```

O SearchGEO não deve gravar o token em INI, SQLite, HTML, logs ou argumentos CLI.

Para procurar acidentalmente pelo **valor real** do token nos artefatos de uma auditoria:

```powershell
$token = $env:DYNATRACE_API_TOKEN
Get-ChildItem ".\audits\AUD-SEU-ID" -Recurse -File |
  Select-String -SimpleMatch $token
```

Resultado esperado: **nenhuma ocorrência**.

Também é aceitável procurar o nome da variável para diferenciar documentação de vazamento de valor:

```powershell
Get-ChildItem ".\audits\AUD-SEU-ID" -Recurse -File |
  Select-String -SimpleMatch "DYNATRACE_API_TOKEN"
```

O nome pode aparecer em texto explicativo do relatório/documentação; o **valor secreto jamais**.

## 7. Calibração por JSON exportado do Dynatrace

O modo preferido para auditoria reproduzível é um JSON de configuração exportado previamente:

```powershell
python -m searchgeo audit "https://SEU-ALVO/" `
  --max-pages 1 `
  --ai-provider none `
  --no-web-performance `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.0 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-experience `
  --apdex-experience-samples 10 `
  --apdex-experience-max-attempts 13 `
  --apdex-experience-device-mix "mobile=60,desktop=30,tablet=10" `
  --apdex-dynatrace-config-json ".\dynatrace-web-application.json" `
  --apdex-experience-error-scope first-party `
  --apdex-experience-concurrency 1
```

Quando o JSON contém KPM/thresholds compatíveis, eles substituem a calibração manual. Se a KPM não puder ser medida pelo M25 com equivalência suficiente, a execução M25 é recusada de forma fail-open; não há fallback silencioso para outra KPM.

## 8. Importação live pela Configuration API Dynatrace

Configure primeiro o segredo:

```powershell
$env:DYNATRACE_API_TOKEN = "seu-token"
```

Depois execute com:

```text
--apdex-dynatrace-import
--dynatrace-base-url https://SEU-AMBIENTE.live.dynatrace.com
--dynatrace-application-id APPLICATION-XXXXXXXXXXXX
```

O M25 lê apenas dados necessários à calibração e persiste somente metadados sanitizados. O payload integral da configuração não é copiado para o audit workspace.

## 9. Cold versus warm

`cold` é o baseline conservador/reprodutível:

- novo BrowserContext por amostra;
- cache do browser desabilitado;
- sem cookies/storage reaproveitados.

`warm` reutiliza contexto dentro do mesmo worker/perfil e permite cache/cookies/storage entre amostras. Use `warm` somente quando essa semântica fizer parte do cenário que está sendo comparado.

## 10. Escopo de erro

- `navigation`: somente falha do documento/navegação;
- `first-party`: inclui JavaScript runtime errors e request/HTTP errors do host da aplicação;
- `all`: inclui também terceiros observados.

Para comparação com APM/RUM, configure o escopo que melhor represente a política real conhecida. Não amplie para `all` apenas para reduzir o score.

## 11. Grupos de 100 e 1000 amostras

M25 usa 100 amostras totais por página como default. `1000` é suportado, mas deve ser tratado como execução de carga relevante.

Exemplo de distribuição:

```text
--apdex-experience-samples 1000
--apdex-experience-device-mix mobile=62,desktop=31,tablet=7
```

produz:

```text
620 Mobile
310 Desktop
 70 Tablet
```

Não execute 100/1000 amostras em produção sem autorização e avaliação de capacidade. Uma navegação carrega HTML e múltiplos subrecursos; `1000 samples` não significa `1000 requests HTTP`.

Aumentar N reduz ruído amostral do laboratório. Não transforma o conjunto sintético em população RUM.

## 12. Interpretação do delta para Dynatrace

Antes de interpretar `SearchGEO M25 != Dynatrace`, confira:

- mesma URL/user action;
- mesma KPM;
- mesmos thresholds;
- mesma política de erros;
- período Dynatrace conhecido;
- mix de dispositivos compatível;
- semântica cold/warm coerente;
- escopo first-party/third-party conhecido.

Mesmo com esses itens alinhados, divergência é esperada porque o Dynatrace RUM observa redes, dispositivos, geografias, sessões e condições operacionais reais que o laboratório controlado não reproduz integralmente.

## 13. Referências

A especificação normativa do M25 está em `docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md` e referencia a Apdex Technical Specification, documentação Dynatrace de RUM/Apdex/configuração, Chrome DevTools Protocol e W3C Performance Timeline.
