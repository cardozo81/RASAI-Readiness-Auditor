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
- Perfis de Execução temporários para uma URL explícita, incluindo `Completo seguro` e `Completo máximo`;
- estado `APTO`/`CONFIGURAR` e pendências visíveis antes da seleção;
- descrição, dependências e custo/exposição antes de aplicar um perfil;
- ajuste fino posterior, sem persistir o preset no INI ou no sistema operacional;
- provider/modelo/esforço/timeout da IA principal;
- dependência explícita da remediação textual em relação à IA;
- configuração de Web Performance e timeout PageSpeed/Lighthouse;
- configuração guiada de Synthetic Apdex;
- progresso por etapa;
- estimativa de custo/quota/carga;
- arquivo `rasai-console.ini` para parâmetros não sensíveis;
- aviso de alterações não salvas;
- atalhos para abrir pasta e relatório.

Credenciais não são gravadas no INI. Elas podem ser configuradas em `Integrações / credenciais` e aparecem somente como `[SET]`.

### Preparar auditoria

O dashboard `INÍCIO > PREPARAR AUDITORIA` segue uma regra única de navegação:

```text
números = parâmetros da próxima auditoria
letras  = ações e navegação
```

Os parâmetros são agrupados por contexto e numerados continuamente:

```text
[ ESCOPO ]
 1. Entrada
 2. Projeto
 3. Dispositivo
 4. Idioma / mercado
 5. Timezone apresentação

[ INTELIGÊNCIA ARTIFICIAL ]
 6. IA
 7. Remediações IA
 8. Análise profunda URL

[ WEB PERFORMANCE ]
 9. Web Performance
10. Máx. páginas da auditoria
11. Máx. páginas em Web Performance
12. Synthetic Apdex

[ SEARCH INTELLIGENCE ]
13. Termos SERP

[ ARMAZENAMENTO / EXECUÇÃO ]
14. Raiz auditorias

[ PERFIL DA PRÓXIMA EXECUÇÃO ]
15. Perfil da execução
```

As ações são apresentadas separadamente:

```text
R. Executar
S. Salvar configuração INI
L. Carregar configuração de AUD
E. Integrações / credenciais
C. Histórico / relatórios consolidados
H. Ajuda / custos
V. Voltar ao início
Q. Sair
```

A restauração global do produto não faz parte desta tela. `Restaurar padrões do RASAi` fica somente em `INÍCIO > Sistema / restaurar padrões`.

### Perfis de Execução

Quando **Entrada** contém uma única URL explícita, o menu oferece:

```text
15. Perfil da execução
```

O perfil é um overlay somente da sessão. Ele não altera defaults do RASAi, não grava o preset no `rasai-console.ini`, não modifica `Windows/User` ou `Windows/Machine` e não cria/troca credenciais.

Todos os presets permanecem visíveis. Um preset `APTO` pode ser selecionado. Um preset `CONFIGURAR` continua aparecendo para orientar a parametrização, mostra exatamente o que falta e **não pode ser aplicado** até que as dependências obrigatórias sejam resolvidas.

Dependências humanas ou operacionais continuam explícitas: Search Intelligence não inventa termos SERP e usa o item 13; GEO não transforma contexto YMYL `AUTO` em fato; Experiência sintética não inventa parâmetros de carga; Análise profunda exige o item 8, uma URL única e a IA principal apta no item 6.

`Completo seguro` combina SEO, GEO, Performance, Acessibilidade e Web Quality sem ativar automaticamente SERP, carga sintética ou análise profunda.

`Completo máximo` combina todos os módulos do catálogo. Ele permanece `CONFIGURAR` até Search Intelligence, Experiência sintética e Análise profunda estarem aptos. O nome "máximo" indica cobertura funcional, não redução de segurança ou limites.

Existe uma única seleção principal de IA por execução. Improvement Intelligence e demais consumidores compatíveis usam essa mesma seleção. Quando a análise profunda faz parte do perfil, ela não possui provider/model/reasoning próprios e não pode ser desativada por uma escolha de “sem IA opcional” para os demais módulos. Em `AUTO`, ela reutiliza a política central de custo, elegibilidade, quarentena, circuit breaker e fallback.

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

A auditoria pode rodar com `--ai-provider none` quando nenhuma capacidade selecionada exigir IA.

Quando IA é habilitada, o provider pode ser explícito ou `auto`. O console usa o registry canônico para disponibilidade, modelos e reasoning. O modo `AUTO` aplica a política central de custo/saúde/fallback; módulos especializados não criam uma segunda escolha de provider.

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

Um perfil `APTO` significa que as dependências conhecidas estavam válidas antes da execução; não é garantia de sucesso de rede/provider. Se uma integração falhar em runtime, o HTML deve mostrar falha/parcialidade em vez de fabricar dados.

## Acessibilidade

A página `accessibility.html` reutiliza evidência Lighthouse persistida. Não é certificação WCAG.

Se o artifact Lighthouse não existir, o relatório deve dizer por que não foi obtido em vez de exibir somente valores vazios.

## Web Performance

`web-performance.html` apresenta Lighthouse lab e CrUX/CWV quando disponíveis. Apdex permanece em página própria e não deve ser apresentado como métrica derivada de Lighthouse.

## Uso de IA

`ai-usage.html` apresenta provider, modelo, tentativas, tokens e custo estimado quando disponíveis e distingue finalidades não solicitadas de chamadas efetivamente realizadas/falhas.

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
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI_REFERENCE.md](CLI_REFERENCE.md)
- [REPORT_GUIDE.md](REPORT_GUIDE.md)
- [AI_GUIDE.md](AI_GUIDE.md)
