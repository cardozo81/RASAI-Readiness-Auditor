# Synthetic User Experience Apdex

## 1. Finalidade

O Synthetic User Experience Apdex adiciona ao RASAi uma medição sintética calibrável, separada do Synthetic Navigation Apdex Standard.

| Domínio | Natureza | Task / população | Thresholds |
|---|---|---|---|
| Synthetic Navigation Apdex | laboratório sintético controlado | `NAVIGATION_LOAD`, por URL/dispositivo | `T` e `4T` conforme Apdex Standard |
| Synthetic User Experience Apdex | laboratório sintético enriquecido/calibrável | `SYNTHETIC_LOAD_ACTION`, mix explícito de dispositivos | Satisfied e Frustrated independentes, com baseline Dynatrace-compatible ou importação |
| Dynatrace RUM | usuários reais | Load/XHR/Custom actions observadas no período | configuração efetiva da aplicação/action |

Synthetic User Experience Apdex **não é RUM**. O objetivo é reduzir diferenças metodológicas controláveis - KPM, thresholds, política de erros, sessão e mix de dispositivos - sem manipular o score para coincidir com Dynatrace.

## 2. Baseline default Dynatrace-compatible

Quando `--apdex-experience` é habilitado e o usuário não fornece calibração própria nem importa configuração Dynatrace, o RASAi resolve automaticamente:

```text
KPM efetiva                  = USER_ACTION_DURATION
Satisfied                    = 3.0 s
Frustrated                   = 12.0 s
Errors affect Apdex          = true
Error scope                  = first-party
Samples por página           = 100
Session mode                 = cold
Device mix                   = mobile=60,desktop=35,tablet=5
Settle                       = 5 s
Delay                        = 1 s
Concurrency                  = 1
Max attempts                 = ceil(1.25 × samples)
```

A origem dos valores precisa ser entendida corretamente:

- Dynatrace documenta `VISUALLY_COMPLETE` como KPM padrão de Load Action e XHR Action em sua documentação atual de KPM;
- Dynatrace documenta que, se a KPM selecionada não for detectada, **User action duration** é usada como fallback;
- o modelo público de configuração web do Dynatrace expõe, como referência de Load Action, thresholds 3 s / 12 s e fallback 3 s / 12 s;
- o RASAi **não calcula Dynatrace Visually Complete com equivalência de fornecedor**; por isso seu baseline executável usa `USER_ACTION_DURATION` + 3 s / 12 s, registrando essa fronteira metodológica;
- `device_mix`, `session_mode`, `samples`, `settle`, `delay` e `concurrency` são defaults operacionais do RASAi. Dynatrace RUM observa população real e não possui equivalentes sintéticos universais para esses parâmetros;
- `first-party` é um escopo conservador do RASAi para erros. Dynatrace possui regras de erro mais granulares, não um único valor equivalente a esse enum.

O baseline não deve ser descrito como “Dynatrace RUM reproduzido”. Ele é **Dynatrace-compatible onde há mapeamento tecnicamente defensável**.

## 3. Cobertura do contrato Dynatrace e limitações

O RASAi executa uma Load Action sintética. A cobertura é:

| Contrato Dynatrace | RASAi | Situação |
|---|---|---|
| Load Action thresholds | sim | executável |
| Load Action KPM `USER_ACTION_DURATION` | sim | executável |
| Load Action `VISUALLY_COMPLETE` | parcial | importável como KPM solicitada; não mensurável com equivalência Dynatrace; usa fallback UAD quando os fallback thresholds existem |
| LCP, DOM Interactive, Load Event, Response Start/End | sim | KPMs temporais suportadas pelo runtime |
| Speed Index / CLS como KPM temporal de Apdex | não | não há substituição silenciosa; CLS pode ser telemetria, não KPM temporal |
| XHR Action thresholds/KPM | metadados + telemetria | XHR/fetch observado dentro da Load Action; não é uma XHR Action autônoma sem roteiro de interação |
| Custom Action | metadados | requer clickpath/script/ação explícita; não é inventada pelo crawler |
| regras de request/JavaScript errors | parcial | erros observáveis são coletados; a política Dynatrace pode ser mais granular do que `navigation/first-party/all` |
| população real de devices/redes/sessões | não | RASAi usa perfis sintéticos controlados |

Essa limitação é estrutural, não um gap simples de configuração. Implementar XHR/Custom Actions autônomas exigiria uma camada de scripted journeys/clickpaths com definição de ações e correlação de requests. Implementar `VISUALLY_COMPLETE` com equivalência Dynatrace exigiria reproduzir semântica de fornecedor; o RASAi não declara essa equivalência.

## 4. Fallback de KPM importada

Ao importar configuração Dynatrace:

1. o RASAi registra a KPM originalmente solicitada;
2. se ela for diretamente mensurável, usa os thresholds primários importados;
3. se não for mensurável com equivalência suficiente e a configuração fornecer fallback thresholds, usa explicitamente `USER_ACTION_DURATION` + fallback thresholds;
4. a origem recebe `RASAI_CAPABILITY_FALLBACK` e o HTML mostra a substituição;
5. se não houver fallback utilizável, a execução é recusada de forma fail-open.

Não existe fallback silencioso.

## 5. Console interativo

O menu de Synthetic Apdex deve exibir:

- todas as variáveis configuráveis do Synthetic User Experience Apdex;
- o valor default de cada uma;
- a origem do default (`Dynatrace-compatible`, `RASAi`, `RASAi derivado` ou `sem equivalente RUM`);
- a configuração efetiva antes da execução;
- marcação `PADRÃO` ou `CUSTOMIZADO` para os valores alteráveis;
- indicação explícita quando KPM/thresholds vierem de importação Dynatrace.

As variáveis são:

```text
RASAI_APDEX_EXPERIENCE
RASAI_APDEX_EXPERIENCE_SAMPLES
RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS
RASAI_APDEX_EXPERIENCE_MAX_PAGES
RASAI_APDEX_EXPERIENCE_DEVICE_MIX
RASAI_APDEX_EXPERIENCE_SESSION_MODE
RASAI_APDEX_EXPERIENCE_KPM
RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS
RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS
RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT
RASAI_APDEX_EXPERIENCE_ERROR_SCOPE
RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS
RASAI_APDEX_EXPERIENCE_DELAY_SECONDS
RASAI_APDEX_EXPERIENCE_CONCURRENCY
RASAI_APDEX_DYNATRACE_IMPORT
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
RASAI_DYNATRACE_CONFIG_JSON
DYNATRACE_API_TOKEN
```

`DYNATRACE_API_TOKEN` é segredo de ambiente; não é persistido em INI, SQLite, HTML, logs ou argumentos CLI.

## 6. Smoke humano recomendado

Use primeiro uma URL autorizada e baixo volume:

```powershell
python -m rasai audit "https://SEU-ALVO/" `
  --max-pages 1 `
  --device-context mobile `
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
  --apdex-experience-concurrency 1
```

Sem flags de KPM/thresholds, a execução Experience usa o baseline `USER_ACTION_DURATION`, 3 s / 12 s. Para testar customização, forneça explicitamente `--apdex-experience-kpm`, `--apdex-experience-satisfied-seconds` e `--apdex-experience-frustrated-seconds`.

Com 10 amostras e mix `60/30/10`, a alocação esperada é 6 Mobile, 3 Desktop e 1 Tablet. Um grupo com menos de 100 amostras é diagnóstico e não deve ser apresentado como baseline estatística final.

## 7. O que verificar no smoke

1. `report/apdex.html` permanece com Synthetic Navigation Apdex `T/4T`;
2. `report/apdex-experience.html` é gerado quando Experience executa;
3. KPM efetiva e thresholds 3 s / 12 s aparecem como `PADRÃO` quando não customizados;
4. qualquer valor alterado pelo usuário aparece como `CUSTOMIZADO`;
5. calibração importada aparece como `DYNATRACE IMPORT`;
6. fallback de KPM importada, quando necessário, é mostrado explicitamente;
7. Mobile/Desktop/Tablet/Population aparecem conforme o mix;
8. XHR/fetch, recursos tardios e erros aparecem somente quando observados;
9. `console.error` não força `FRUSTRATED` sozinho;
10. erro qualificável força `FRUSTRATED` quando `errors_affect_apdex=true`;
11. nenhuma alteração ocorre em `SARI-001`, SCORE-GEO-004, findings ou recomendações GEO.

## 8. Persistência

Quando executado, o domínio usa:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

As tabelas Synthetic Navigation Apdex permanecem em `synthetic_apdex_*`.

A fórmula permanece:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

A configuração persistida contém os valores efetivos necessários à rastreabilidade, mas não contém o token Dynatrace nem o payload integral de configuração.

## 9. Importação Dynatrace

### JSON exportado

É o modo preferido para auditoria reproduzível:

```powershell
python -m rasai audit "https://SEU-ALVO/" `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.0 `
  --apdex-experience `
  --apdex-dynatrace-config-json ".\dynatrace-web-application.json"
```

### Configuration API

```powershell
$env:DYNATRACE_API_TOKEN = "seu-token"

python -m rasai audit "https://SEU-ALVO/" `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.0 `
  --apdex-experience `
  --apdex-dynatrace-import `
  --dynatrace-base-url https://SEU-AMBIENTE.live.dynatrace.com `
  --dynatrace-application-id APPLICATION-XXXXXXXXXXXX
```

A importação registra contrato sanitizado de Load/XHR/Custom quando presente. Somente Load Action é executada pelo Synthetic User Experience Apdex atual.

## 10. Erros

Escopos RASAi:

- `navigation`: falha do documento/navegação;
- `first-party`: inclui JavaScript runtime errors e request/HTTP errors do host da aplicação;
- `all`: inclui também terceiros observados.

Dynatrace permite regras mais granulares de request/JavaScript errors. Quando a importação não expõe uma política global equivalente, o RASAi mantém sua política efetiva e registra a origem; não infere uma equivalência inexistente.

## 11. Cold/warm, amostragem e carga

`cold` é o baseline reproduzível: novo BrowserContext, cache desabilitado e sem storage reaproveitado. `warm` reaproveita contexto no mesmo worker/perfil.

O default é 100 amostras válidas totais por página. `1000` é suportado, mas representa carga relevante. Uma navegação carrega HTML e múltiplos subrecursos; 1000 samples não significa apenas 1000 requests HTTP.

Não execute carga relevante contra produção sem autorização e avaliação de capacidade.

## 12. Interpretação do delta para Dynatrace

Antes de interpretar diferenças, confira:

- mesma URL/ação;
- KPM efetivamente usada;
- thresholds;
- fallback aplicado ou não;
- política de erros;
- período Dynatrace;
- device mix;
- cold/warm;
- perfis de CPU/rede e geografia.

Mesmo alinhando os itens disponíveis, divergência continua esperada porque Dynatrace RUM mede condições reais e o RASAi executa laboratório sintético controlado.

## 13. Referências

- Apdex Technical Specification v1.1: `https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf`
- Dynatrace - Apdex configuration for load actions: `https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions`
- Dynatrace - Work with key performance metrics: `https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/analyze-and-use/work-with-key-performance-metrics`
- Dynatrace - Apdex ratings: `https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/scores-and-ratings/apdex-ratings`
- Dynatrace - Web application configuration API: `https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application`
- Chrome DevTools Protocol - Network / Emulation
- W3C Performance Timeline

A especificação normativa está em `docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`.
