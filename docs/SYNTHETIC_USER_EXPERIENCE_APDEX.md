# Synthetic User Experience Apdex

## 1. Finalidade

Synthetic User Experience Apdex adiciona ao RASAi uma medição sintética calibrável, separada de Synthetic Navigation Apdex.

| Domínio | Natureza | Task / população | Thresholds |
|---|---|---|---|
| Synthetic Navigation Apdex | laboratório sintético controlado | `NAVIGATION_LOAD`, por URL/dispositivo | `T` e `4T` conforme Apdex |
| Synthetic User Experience Apdex | laboratório sintético enriquecido/calibrável | `SYNTHETIC_LOAD_ACTION`, mix explícito de dispositivos | limites Satisfied/Frustrated independentes, com baseline compatível com referências Dynatrace ou importação |
| Dynatrace RUM | usuários reais | Load/XHR/Custom actions observadas no período | configuração efetiva da aplicação/ação |

Synthetic User Experience Apdex **não é RUM**. O objetivo é reduzir diferenças metodológicas controláveis - KPM, thresholds, política de erros, sessão e mix de dispositivos - sem manipular o score para coincidir com Dynatrace.

A partir de `M25-PROFILE-003`, a fronteira temporal de `USER_ACTION_DURATION` foi explicitada e versionada. Resultados produzidos por versões anteriores do perfil devem ser tratados como metodologicamente distintos para comparação longitudinal.

## 2. Baseline padrão compatível com referências Dynatrace

Quando `--apdex-experience` é habilitado e o usuário não fornece calibração própria nem importa configuração Dynatrace, o runtime resolve:

| Parâmetro | Default efetivo | Valores permitidos | Recomendado | Origem |
|---|---|---|---|---|
| KPM | `USER_ACTION_DURATION` | KPM temporal suportada pelo runtime | default quando não houver importação | fallback executável compatível com a regra pública Dynatrace; não é a KPM primária do fornecedor |
| Satisfied | `3.0 s` | número `> 0` | `3.0 s` quando o objetivo for o baseline compatível; calibrar quando houver SLO/configuração real | referência/fallback Load Action |
| Frustrated | `12.0 s` | número `> Satisfied` | `12.0 s` no baseline compatível | referência/fallback Load Action |
| erros afetam Apdex | `true` | booleano | `true`, salvo política deliberadamente diferente | alinhamento semântico; Dynatrace pode possuir regras mais granulares |
| escopo de erro | `first-party` | `navigation`, `first-party`, `all` | `first-party` | escopo RASAi para request/HTTP errors; JavaScript runtime errors e `console.error` observados são globais quando a política de erros está ativa |
| amostras por página | `100` | inteiro `>= 1` | `100`; reduzir somente em smoke controlado | política operacional RASAi |
| máximo de tentativas | `ceil(1.25 × samples)` | inteiro `>= 1` e validado pela configuração | default derivado | política operacional RASAi |
| máximo de páginas | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline de carga | política operacional RASAi |
| mix de dispositivos | `mobile=60,desktop=35,tablet=5` | percentuais não negativos para Mobile/Desktop/Tablet somando exatamente 100 | usar distribuição observada real quando o objetivo for comparar com uma aplicação específica | política sintética RASAi |
| modo de sessão | `cold` | `cold`, `warm` | `cold` para maior reprodutibilidade | política sintética RASAi |
| settle | `5.0 s` | número `> 0` | `5.0 s` | janela de observação pós-load; não estende por si só a `USER_ACTION_DURATION` |
| delay | `1.0 s` | número `>= 0` | `1.0 s` ou maior conforme capacidade do alvo | política de carga RASAi |
| concorrência | `1` | `1`, `2` | `1` | política de carga RASAi |

A classificação temporal do Synthetic User Experience Apdex segue a semântica publicada dos thresholds Dynatrace para Load Action:

```text
valor < limiar Satisfied                         -> SATISFIED
limiar Satisfied <= valor <= limiar Frustrated  -> TOLERATING
valor > limiar Frustrated                        -> FRUSTRATED
```

Um erro qualificável pode forçar `FRUSTRATED` independentemente da duração quando a política de erros efetiva estiver habilitada. Essa fronteira é intencionalmente diferente do Synthetic Navigation Apdex clássico, cuja classificação permanece baseada em `T` e `4T` conforme a especificação Apdex.

### 2.1 Fronteira temporal de `USER_ACTION_DURATION`

Para Load Action, a documentação Dynatrace define o início em `navigationStart`. O término usa `loadEventEnd` ou, quando um XHR iniciado durante o processo permanece ativo depois do `loadEventEnd`, o término desse XHR.

No `M25-PROFILE-003`, o RASAi aplica a aproximação executável correspondente:

```text
actionStart = navigationStart
loadBoundary = loadEventEnd
userActionEnd = max(loadBoundary, término do último XHR/fetch iniciado antes de loadEventEnd)
USER_ACTION_DURATION = userActionEnd - actionStart
```

Requests iniciados **depois** do `loadEventEnd` continuam observáveis durante a janela `settle`, inclusive para telemetria de erros e recursos tardios, mas não estendem automaticamente a `USER_ACTION_DURATION`. Isso evita que analytics, beacons, polling ou tráfego tardio arbitrário sejam incorporados ao tempo da Load Action apenas porque terminaram durante o `settle`.

Fontes oficiais:

- Dynatrace - User actions in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-actions>
- Dynatrace - User action metrics in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-action-metrics>

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

**Disclaimer - texto original da fonte Dynatrace:**

> “Visually complete is the default metric for load and XHR actions.”

**Tradução/adaptação pt-BR:** o Dynatrace documenta **Visually Complete** como métrica padrão para ações Load e XHR no contrato de KPM correspondente. O RASAi não declara equivalência de fornecedor para essa métrica.

Fonte: Dynatrace - Key performance metrics (`builtin:synthetic.browser.kpms`): <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-synthetic-browser-kpms>

**Disclaimer - texto original da fonte Dynatrace:**

> “If the selected key performance metric is not detected, the User action duration metric is used instead.”

**Tradução/adaptação pt-BR:** quando a KPM selecionada não é detectada, a documentação do Dynatrace define **User action duration** como fallback. Essa regra sustenta a escolha do RASAi de manter a KPM solicitada e registrar explicitamente `USER_ACTION_DURATION` como KPM efetiva quando o fallback for necessário e tecnicamente válido.

Fonte: Dynatrace - Apdex configuration for load actions: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions>

O modelo público da Web Application Configuration API do Dynatrace expõe valores de 3.000 ms e 12.000 ms para os thresholds e fallback thresholds de Load Action. O RASAi converte esses valores explicitamente para `3.0 s` e `12.0 s` em seu baseline compatível.

Fonte: <https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application>

Os parâmetros `device_mix`, `session_mode`, `samples`, `settle`, `delay`, `concurrency`, o escopo `first-party` e o tratamento de `console.error` são políticas do RASAi e **não** devem ser atribuídos ao Dynatrace RUM.

## 3. Cobertura do contrato Dynatrace e limitações

O RASAi executa uma Load Action sintética. A cobertura é:

| Contrato Dynatrace | RASAi | Situação |
|---|---|---|
| Load Action thresholds | sim | executável |
| Load Action KPM `USER_ACTION_DURATION` | sim | executável; `M25-PROFILE-003` usa `loadEventEnd` ou último XHR/fetch iniciado antes do load e concluído depois |
| Load Action `VISUALLY_COMPLETE` | parcial | importável como KPM solicitada; não mensurável com equivalência Dynatrace; usa fallback UAD quando fallback thresholds utilizáveis existem |
| LCP, DOM Interactive, Load Event, Response Start/End | sim | KPMs temporais suportadas pelo runtime |
| Speed Index / CLS como KPM temporal de Apdex | não | não há substituição silenciosa; CLS pode ser telemetria, não KPM temporal |
| XHR Action thresholds/KPM | metadados + telemetria | XHR/fetch observado dentro da Load Action; não é XHR Action autônoma sem roteiro de interação |
| Custom Action | metadados | requer clickpath/script/ação explícita; não é inventada pelo crawler |
| JavaScript runtime errors | sim | `pageerror` é observado globalmente e pode forçar `FRUSTRATED` quando erros afetam Apdex |
| `console.error` | extensão RASAi | observado globalmente e pode forçar `FRUSTRATED` quando erros afetam Apdex; não é declarado como equivalência 1:1 ao Dynatrace |
| request/HTTP errors | parcial | escopo `navigation/first-party/all`; Dynatrace possui regras de captura/impacto no Apdex mais granulares |
| população real de devices/redes/sessões | não | o RASAi usa perfis sintéticos controlados |

Implementar XHR/Custom Actions autônomas exigiria scripted journeys/clickpaths com definição de ações e correlação de requests. Implementar `VISUALLY_COMPLETE` com equivalência Dynatrace exigiria reproduzir semântica específica do fornecedor; o RASAi não declara essa equivalência.

A documentação Dynatrace permite incluir/excluir request errors do Apdex por regras e expõe `impactApdex` por regra. O RASAi não deve apresentar `navigation/first-party/all` como enum equivalente ao fornecedor.

Fonte: Dynatrace - Request errors (`builtin:rum.web.request-errors`): <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-request-errors>

## 4. Fallback de KPM importada

Ao importar configuração Dynatrace:

1. o RASAi registra a KPM originalmente solicitada;
2. se ela for diretamente mensurável, usa os thresholds primários importados;
3. se não for mensurável com equivalência suficiente e a configuração fornecer fallback thresholds válidos, usa explicitamente `USER_ACTION_DURATION` com os fallback thresholds;
4. a origem recebe `RASAI_CAPABILITY_FALLBACK` e o HTML mostra a substituição;
5. se não houver fallback utilizável, a execução Experience falha de forma fail-open, sem alterar o audit principal.

Não existe fallback silencioso.

## 5. KPMs temporais suportadas

O conjunto executável é validado pelo runtime. A documentação canônica de valores permitidos é [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md). Entre as KPMs temporais suportadas estão:

```text
USER_ACTION_DURATION
DOM_INTERACTIVE
LOAD_EVENT_START
LOAD_EVENT_END
RESPONSE_START
RESPONSE_END
LARGEST_CONTENTFUL_PAINT
```

`VISUALLY_COMPLETE`, `SPEED_INDEX` e `CUMULATIVE_LAYOUT_SHIFT` não podem ser substituídas silenciosamente por outra métrica quando não houver equivalência suficiente. CLS pode permanecer telemetria observada sem se tornar KPM temporal de Apdex.

## 6. Console interativo

O menu de Synthetic Apdex deve expor:

- todas as variáveis configuráveis de Synthetic User Experience Apdex;
- default e valor efetivo;
- domínio permitido quando houver enum/faixa;
- origem (`Dynatrace-compatible`, `RASAi`, `RASAi derivado` ou sem equivalente RUM);
- marcação `PADRÃO`, `CUSTOMIZADO` ou `DYNATRACE IMPORT`;
- indicação explícita quando KPM/thresholds vierem de importação Dynatrace;
- secrets apenas como estado de configuração, nunca como valor.

Variáveis:

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

`DYNATRACE_API_TOKEN` é segredo de ambiente: não é persistido em INI, SQLite, HTML, logs nem argumentos CLI.

## 7. Smoke humano recomendado

Use URL autorizada e baixo volume:

```powershell
python -m rasai audit "https://SEU-ALVO/" `
  --max-pages 1 `
  --device-context both `
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

Com `--device-context both`, 10 amostras e mix `60/30/10`, a alocação Experience esperada é 6 Mobile, 3 Desktop e 1 Tablet. O core da auditoria continua tendo apenas snapshots Mobile e Desktop; Tablet pertence exclusivamente à população `PROFILE_MEASUREMENT` do Experience Apdex. Grupo com menos de 100 amostras é diagnóstico, não baseline estatístico final.

Se o mesmo teste usar `--device-context mobile`, a população Experience é deliberadamente restrita a 100% Mobile, independentemente do mix configurado; `desktop` aplica a regra equivalente.

## 8. O que verificar no smoke

1. `report/apdex.html` permanece com Synthetic Navigation Apdex `T/4T`;
2. `report/apdex-experience.html` é gerado quando Experience executa;
3. KPM efetiva e thresholds padrão aparecem como `PADRÃO` quando não customizados;
4. valor alterado pelo usuário aparece como `CUSTOMIZADO`;
5. calibração importada aparece como `DYNATRACE IMPORT`;
6. fallback importado é mostrado explicitamente;
7. Mobile/Desktop/Tablet/Population refletem o mix quando `device-context=both`;
8. XHR/fetch, recursos tardios e erros aparecem somente quando observados;
9. `console.error` força `FRUSTRATED` quando `errors_affect_apdex=true` e o escopo não é `navigation`;
10. JavaScript runtime error força `FRUSTRATED` sob a mesma política;
11. request/HTTP error respeita `navigation/first-party/all` e permanece distinguível dos runtime errors;
12. request iniciado após `loadEventEnd` pode ser observado no `settle`, mas não estende sozinho `USER_ACTION_DURATION`;
13. igualdade com o limiar inferior fica em `TOLERATING`, e igualdade com o limiar Frustrated também permanece `TOLERATING`;
14. `SARI-001`, `SCORE-GEO-004`, findings e recomendações GEO permanecem inalterados.

## 9. Persistência

Tabelas:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

Synthetic Navigation Apdex permanece em `synthetic_apdex_*`.

Fórmula:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

A configuração persistida contém os valores efetivos necessários à rastreabilidade, inclusive o `measurement_contract` do M25, mas não contém token Dynatrace nem payload integral de configuração. O ambiente persiste `m25_profile_version`; mudanças metodológicas devem alterar essa versão.

## 10. Importação Dynatrace

### JSON exportado

Modo recomendado para auditoria reproduzível:

```powershell
python -m rasai audit "https://SEU-ALVO/" `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.0 `
  --apdex-experience `
  --apdex-dynatrace-config-json ".\dynatrace-web-application.json"
```

### API de configuração

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

A importação registra contrato sanitizado de Load/XHR/Custom quando presente. Somente Load Action é executada pela implementação atual de Synthetic User Experience Apdex.

## 11. Erros

A política M25 separa runtime errors de request/HTTP errors:

- `navigation`: somente falha do documento/navegação força erro por política; runtime/request errors observados não ampliam esse escopo;
- `first-party`: JavaScript runtime errors (`pageerror`) e `console.error` observados são globais; request/HTTP errors só qualificam quando pertencem ao host da aplicação;
- `all`: JavaScript runtime errors e `console.error` continuam globais e request/HTTP errors de terceiros também podem qualificar.

`console.error` é uma **extensão de política RASAi**, solicitada para tornar a coleta sintética mais sensível a falhas explicitamente emitidas no console. A documentação Dynatrace oficial distingue JavaScript errors e request errors e permite regras de inclusão/exclusão no Apdex; portanto o RASAi não declara `console.error` como equivalência de fornecedor.

Dynatrace permite regras de request error mais granulares, inclusive filtros e `impactApdex`. Quando a importação não expõe política global equivalente, o RASAi mantém sua política efetiva e registra a origem; não infere equivalência inexistente.

Fontes oficiais:

- JavaScript/HTTP error rules: <https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/error-rules/get-configuration>
- Request error settings: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-request-errors>

## 12. Cold/warm, amostragem e carga

`cold` é o baseline reproduzível: novo BrowserContext, cache desabilitado e sem storage reaproveitado. `warm` reutiliza contexto no mesmo worker/perfil.

O default é 100 amostras válidas totais por página. `1000` é aceito por ser inteiro positivo, mas representa carga relevante. Uma navegação carrega HTML e múltiplos subrecursos; 1.000 samples não significam somente 1.000 requests HTTP.

Não execute carga relevante contra produção sem autorização e avaliação de capacidade.

## 13. Interpretação do delta em relação ao Dynatrace

Antes de interpretar diferenças, confira:

- mesma URL/ação;
- versão metodológica `m25_profile_version`;
- KPM solicitada e efetiva;
- thresholds e fallback;
- política de erros;
- período Dynatrace;
- device mix;
- cold/warm;
- perfis de CPU/rede e geografia.
