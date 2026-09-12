# Guia do usuário

Guia operacional do RASAi - Search & AI Readiness Auditor para execução local e leitura dos resultados.

## Fluxo recomendado

1. instalar dependências e Chromium;
2. escolher URL, conjunto de URLs ou arquivo TXT;
3. selecionar `mobile`, `desktop` ou `both`;
4. para URL única, decidir se um Perfil de Execução temporário será usado;
5. decidir se IA será usada;
6. decidir se remediação textual por IA será habilitada;
7. decidir se Web Performance/Lighthouse/CrUX será coletado;
8. decidir se Synthetic Apdex será executado;
9. revisar limites, timeouts, volume e exposição financeira;
10. executar;
11. conferir **Configuração × resultado obtido** no report;
12. revisar findings, recomendações e limitações operacionais.

## Instalação

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

## Console interativo

```powershell
rasai-console
```

O console oferece:

- configuração em uma tela por vez;
- preflight;
- Perfis de Execução temporários para uma URL explícita, incluindo SEO, GEO, Performance, Acessibilidade, Web Quality e combinações;
- descrição, dependências e custo/exposição antes de aplicar um perfil;
- ajuste fino posterior, sem persistir o preset no INI ou no sistema operacional;
- provider/modelo/esforço/timeout de IA;
- dependência explícita da remediação textual em relação à IA;
- configuração de Web Performance e timeout PageSpeed/Lighthouse;
- configuração guiada de Synthetic Apdex;
- progresso por etapa;
- estimativa de custo/quota/carga;
- arquivo `rasai-console.ini` para parâmetros não sensíveis;
- aviso de alterações não salvas;
- atalhos para abrir pasta e relatório.

Credenciais não são gravadas no INI. Elas podem ser configuradas no menu de variáveis e aparecem somente como `[SET]`.

### Perfis de Execução

Quando **Entrada** contém uma única URL explícita, o menu oferece:

```text
F. Perfil da execução
```

O perfil é um overlay somente da sessão. Ele não altera defaults do RASAi, não grava o preset no `rasai-console.ini`, não modifica `Windows/User` ou `Windows/Machine` e não cria/troca credenciais.

Dependências que exigem informação humana ou configuração prévia continuam explícitas. Por exemplo, Search Intelligence não inventa termos SERP, GEO não transforma contexto YMYL `AUTO` em fato, Experiência sintética não inventa parâmetros de carga e Análise profunda exige o item 13 previamente configurado. Se uma dependência obrigatória faltar, o perfil pode permanecer selecionado, mas a execução aparece como `CONFIGURAR` até a correção.

A IA padrão do perfil pode ficar desligada ou ser usada somente se houver provider `APTO`; a ausência de IA nesse segundo modo não bloqueia o core. Improvement Intelligence continua usando sua configuração de IA própria e independente.

Detalhes dos perfis: [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md).

Detalhes gerais do console: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md).

## Execução pela CLI

### Básica

```powershell
rasai audit https://example.com --project "Exemplo"
```

### Desktop

```powershell
rasai audit https://example.com --device-context desktop
```

### Ambos os dispositivos

```powershell
rasai audit https://example.com --device-context both
```

### Várias URLs

```powershell
rasai audit `
  https://example.com/ `
  https://example.com/produto `
  --max-pages 2
```

## IA

A auditoria pode rodar com `--ai-provider none`.

Quando IA é habilitada, o default público privilegia o modelo mais simples e o menor esforço suportado. O console permite escolher valores maiores quando necessário.

A remediação textual por IA é opcional e exige provider apto.

## Web Performance e Lighthouse

Habilite com:

```powershell
rasai audit https://example.com --web-performance
```

Default de timeout externo:

```text
120 s por chamada PageSpeed/CrUX
```

Se PageSpeed exceder o timeout, o RASAi registra a tentativa como erro operacional. CrUX direto pode continuar disponível. Lighthouse lab e Acessibilidade automatizada ficam indisponíveis quando não há artifact PageSpeed e o report deve informar a causa.

A ausência de dado não é transformada em score artificial.

## Synthetic Apdex

Synthetic Apdex é OFF por padrão e exige `T` explícito.

Para smoke:

```powershell
rasai audit https://example.com `
  --synthetic-apdex `
  --apdex-threshold-seconds 1.5 `
  --apdex-samples-per-context 5 `
  --apdex-max-attempts-per-context 7 `
  --apdex-max-pages 1 `
  --apdex-concurrency 1
```

Grupos abaixo de 100 amostras válidas são diagnóstico small-group `*`.

## Como ler o relatório

Comece por `report/index.html`.

Observe separadamente:

- Score GEO;
- Coverage;
- Confidence;
- findings e recomendações;
- Acessibilidade;
- Web Performance/Lighthouse/CrUX;
- Synthetic Apdex;
- Uso de IA;
- **Configuração × resultado obtido**.

Essa última seção é importante para distinguir:

```text
não configurado
configurado e obtido
configurado, mas não obtido
parcial
indisponível por timeout/quota/HTTP/ausência de artifact
```

## Acessibilidade

A página `accessibility.html` reutiliza evidência Lighthouse persistida. Não é certificação WCAG.

Se o artifact Lighthouse não existir, o relatório deve dizer por que não foi obtido em vez de exibir somente valores vazios.

## Web Performance

`web-performance.html` apresenta Lighthouse lab e CrUX/CWV quando disponíveis. Apdex permanece em página própria e não deve ser apresentado como métrica derivada de Lighthouse.

## Uso de IA

`ai-usage.html` apresenta provider, modelo, tentativas, tokens e custo estimado quando disponíveis.

Custo é estimativa técnica; não substitui billing/invoice do provider.

## Segurança

- não copie API keys para reports, issues ou documentação;
- use variáveis de ambiente/secret manager para secrets;
- o INI não persiste credenciais;
- Perfis de Execução não persistem credenciais nem alteram variáveis do SO;
- não assuma que key configurada implica saldo;
- use Synthetic Apdex em produção somente com autorização.

## Documentos relacionados

- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI_REFERENCE.md](CLI_REFERENCE.md)
- [REPORT_GUIDE.md](REPORT_GUIDE.md)
- [AI_GUIDE.md](AI_GUIDE.md)
