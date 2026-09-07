# GOOGLE_API_KEYS.md

Guia operacional para criar, restringir e configurar as chaves Google usadas pelo **Web Performance externo — Web Performance externo** do RASAi — Search & AI Readiness Auditor.

> Verificado em 2026-09-03 contra a documentação oficial do Google. Nomes de menus podem aparecer em português ou inglês conforme o idioma da conta, mas a estrutura é `APIs e serviços / APIs & Services`.

## O que o RASAi usa

| Serviço Google | Uso no RASAi | Variável de ambiente | Chave obrigatória? |
|---|---|---|---|
| PageSpeed Insights API | Lighthouse de laboratório e, enquanto o Google ainda fornecer, field data CrUX presente na resposta PageSpeed | `SEARCHGEO_PAGESPEED_API_KEY` | Não para uso ad hoc/baixo volume; recomendada para automação frequente |
| Chrome UX Report API (CrUX) | Core Web Vitals de campo via consulta direta | `SEARCHGEO_CRUX_API_KEY` | Sim para chamada direta à CrUX API |

Essas chaves **não são chaves de IA** e não substituem `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` ou `MIMO_API_KEY`.

## URLs oficiais

- Google Cloud Console: <https://console.cloud.google.com/>
- Biblioteca de APIs: <https://console.cloud.google.com/apis/library>
- Credenciais: <https://console.cloud.google.com/apis/credentials>
- PageSpeed Insights API — guia oficial: <https://developers.google.com/speed/docs/insights/v5/get-started>
- PageSpeed Insights API — serviço REST: <https://developers.google.com/speed/docs/insights/rest>
- CrUX API — guia oficial: <https://developer.chrome.com/docs/crux/api>
- Google Cloud — criação e restrição de API keys: <https://docs.cloud.google.com/docs/authentication/api-keys>
- Google Cloud — boas práticas para API keys: <https://docs.cloud.google.com/docs/authentication/api-keys-best-practices>

## Recomendação de provisionamento

Para o RASAi, prefira **duas chaves independentes**:

```text
searchgeo-pagespeed → restrita à PageSpeed Insights API
searchgeo-crux      → restrita à Chrome UX Report API
```

Uma única chave Google pode, tecnicamente, ser restrita às duas APIs e configurada nas duas variáveis. Isso não é o padrão recomendado porque aumenta o blast radius de um vazamento e acopla quota, rotação e troubleshooting de dois serviços independentes.

## Passo 1 — entrar no Google Cloud e selecionar o projeto

1. Acesse <https://console.cloud.google.com/>.
2. Entre com a conta Google que administrará as credenciais.
3. No seletor de projeto no topo da tela, escolha um projeto existente ou selecione **Novo projeto / New Project**.
4. Se criar um projeto, defina um nome reconhecível, por exemplo `searchgeo-readiness-auditor`, e conclua a criação.
5. Confirme que o projeto correto continua selecionado antes de habilitar APIs ou criar chaves.

Permissões, políticas de organização e eventual exigência de billing são controladas pelo Google Cloud e pela organização da conta. Ter acesso ao Console não garante permissão para criar API keys.

## Passo 2 — habilitar a PageSpeed Insights API

Faça este passo se pretende usar uma chave em `SEARCHGEO_PAGESPEED_API_KEY`.

1. No menu do Google Cloud, abra **APIs e serviços / APIs & Services**.
2. Selecione **Biblioteca / Library**.
3. Pesquise exatamente por **PageSpeed Insights API**.
4. Abra a API correspondente.
5. Clique em **Ativar / Enable** se ainda não estiver habilitada.
6. Confirme que o serviço habilitado é o PageSpeed Insights. O endpoint oficial documentado usa o serviço `pagespeedonline.googleapis.com`.

Documentação oficial: <https://developers.google.com/speed/docs/insights/rest>

## Passo 3 — criar a chave do PageSpeed

1. Ainda em **APIs e serviços / APIs & Services**, abra **Credenciais / Credentials**.
2. Clique em **Criar credenciais / Create credentials**.
3. Selecione **Chave de API / API key**.
4. Dê um nome identificável à chave, por exemplo `searchgeo-pagespeed`.
5. Em **Restrições de API / API restrictions**, escolha **Restringir chave / Restrict key**.
6. Selecione **PageSpeed Insights API** e nenhuma API adicional para esta chave.
7. Em **Restrições de aplicativo / Application restrictions**:
   - para execução em servidor ou máquina com **IP público de saída fixo**, prefira **Endereços IP / IP addresses** e cadastre o IP de saída;
   - para notebook/desktop em rede com IP público dinâmico, uma restrição por IP pode quebrar após a troca do IP. Não use **Websites / HTTP referrers** apenas para “ter uma restrição”: o RASAi é uma CLI, não uma aplicação JavaScript executada no navegador;
   - se não houver uma restrição de aplicativo operacionalmente estável, mantenha ao menos a **restrição por API**, armazene a chave somente no ambiente local e faça rotação se houver suspeita de exposição.
8. Clique em **Salvar / Save**.
9. Copie a chave somente para armazenamento seguro. Não a grave em README, issue, commit, screenshot, log ou arquivo versionado.

O Google recomenda restringir API keys por API e, quando viável, também pelo contexto da aplicação.

## Passo 4 — habilitar a Chrome UX Report API

Faça este passo para consulta CrUX direta.

1. Abra **APIs e serviços / APIs & Services** → **Biblioteca / Library**.
2. Pesquise exatamente por **Chrome UX Report API**.
3. Abra a API correspondente.
4. Clique em **Ativar / Enable** se ainda não estiver habilitada.
5. Confirme que a API selecionada é a Chrome UX Report API. A documentação do CrUX exige uma Google Cloud API key provisionada para esse serviço.

Documentação oficial: <https://developer.chrome.com/docs/crux/api>

## Passo 5 — criar a chave do CrUX

1. Abra **APIs e serviços / APIs & Services** → **Credenciais / Credentials**.
2. Clique em **Criar credenciais / Create credentials** → **Chave de API / API key**.
3. Nomeie a chave, por exemplo `searchgeo-crux`.
4. Em **Restrições de API / API restrictions**, selecione **Restringir chave / Restrict key**.
5. Selecione **Chrome UX Report API** e nenhuma API adicional para esta chave.
6. Em **Restrições de aplicativo / Application restrictions**, aplique a mesma regra operacional descrita para PageSpeed: IP fixo quando disponível; não use HTTP referrer para a CLI.
7. Salve e copie a chave para armazenamento seguro.

## Passo 6 — configurar as chaves no PowerShell

As variáveis abaixo valem para a sessão atual do PowerShell:

```powershell
$env:SEARCHGEO_PAGESPEED_API_KEY = "<chave-pagespeed>"
$env:SEARCHGEO_CRUX_API_KEY = "<chave-crux>"
```

Não exiba o valor da chave para “testar”. Verifique apenas se a variável existe:

```powershell
Test-Path Env:SEARCHGEO_PAGESPEED_API_KEY
Test-Path Env:SEARCHGEO_CRUX_API_KEY
```

Resultado esperado quando configuradas:

```text
True
True
```

Se quiser remover as variáveis da sessão atual:

```powershell
Remove-Item Env:SEARCHGEO_PAGESPEED_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SEARCHGEO_CRUX_API_KEY -ErrorAction SilentlyContinue
```

## Passo 7 — escolher a forma de uso no RASAi

### PageSpeed/Lighthouse sem CrUX direto

```powershell
$env:SEARCHGEO_PAGESPEED_API_KEY = "<chave-pagespeed>"
rasai audit https://example.com `
  --web-performance `
  --web-performance-field-source pagespeed
```

`pagespeed` não faz fallback para a CrUX API direta.

### Modo recomendado `auto`

```powershell
$env:SEARCHGEO_PAGESPEED_API_KEY = "<chave-pagespeed>"
$env:SEARCHGEO_CRUX_API_KEY = "<chave-crux>"
rasai audit https://example.com `
  --web-performance `
  --web-performance-field-source auto
```

Em `auto`:

1. o RASAi executa PageSpeed para Lighthouse;
2. usa field data CrUX presente na resposta PageSpeed enquanto disponível;
3. se esse field data não vier e `SEARCHGEO_CRUX_API_KEY` existir, tenta a CrUX API direta;
4. ausência de amostra CrUX não é transformada em `FAIL` do website.

### CrUX direto como fonte de field data

```powershell
$env:SEARCHGEO_CRUX_API_KEY = "<chave-crux>"
rasai audit https://example.com `
  --web-performance `
  --web-performance-field-source crux
```

`--web-performance-field-source crux` exige `SEARCHGEO_CRUX_API_KEY`. PageSpeed continua sendo usado para Lighthouse lab enquanto Web Performance externo estiver habilitado.

### Sem field data

```powershell
rasai audit https://example.com `
  --web-performance `
  --web-performance-field-source none
```

Nesse modo, o RASAi mantém Lighthouse lab e não processa Core Web Vitals de campo.

## PageSpeed sem chave

A documentação oficial permite usar PageSpeed Insights API com ou sem API key, mas recomenda chave para consultas frequentes/automatizadas. Portanto:

- `SEARCHGEO_PAGESPEED_API_KEY` continua opcional;
- para uso recorrente do RASAi com `--web-performance`, configure a chave para melhor governança de quota e rastreabilidade no projeto Google Cloud;
- `SEARCHGEO_CRUX_API_KEY` continua necessária quando a CrUX API direta for chamada.

## Validação após configurar

Execute primeiro uma auditoria pequena:

```powershell
rasai audit https://example.com `
  --device-context mobile `
  --web-performance `
  --web-performance-max-pages 1 `
  --web-performance-field-source auto
```

Ao final, revise:

```text
audits/<AUD-ID>/report/web-performance.html
audits/<AUD-ID>/logs/audit.log
```

O log operacional registra status HTTP, duração e erro sanitizado, mas não deve registrar a API key.

## Erros comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| `403` / API não habilitada | API não foi ativada no projeto da chave | Habilitar a API correta em `APIs e serviços → Biblioteca` |
| `403` / key not authorized | Restrição da chave não contém a API chamada | Revisar `Credenciais → chave → Restrições de API` |
| Chave funciona em um serviço e falha no outro | Chave restrita apenas a uma das APIs | Usar chaves separadas ou, se conscientemente compartilhada, permitir ambas as APIs |
| Falha após mudança de rede | Restrição por IP aponta para IP público antigo | Atualizar IP permitido ou usar uma estratégia de egress estável |
| `field_source=crux` é rejeitado antes da auditoria | `SEARCHGEO_CRUX_API_KEY` ausente | Configurar a variável CrUX |
| CrUX retorna sem dados | URL/origem sem amostra suficiente no dataset | Tratar como indisponibilidade de field data, não como falha do website |
| PageSpeed timeout | Serviço não respondeu dentro do timeout configurado | Ajustar `--web-performance-timeout-seconds`; não há retry automático |

## Segurança e rotação

- Nunca versione chaves em Git.
- Não grave chaves em `searchgeo.toml`, `.md`, HTML, screenshots de suporte ou comandos salvos em histórico compartilhado.
- Restrinja a chave às APIs estritamente necessárias.
- Use IP de saída fixo como restrição de aplicativo quando operacionalmente possível.
- Separe PageSpeed e CrUX para reduzir blast radius.
- Rotacione a chave se houver suspeita de exposição.
- Remova chaves que não são mais usadas.

O RASAi mantém `SEARCHGEO_PAGESPEED_API_KEY` e `SEARCHGEO_CRUX_API_KEY` isoladas e não as reutiliza como credenciais de IA.
