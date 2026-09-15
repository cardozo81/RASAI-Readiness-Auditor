# Guia do usuário

Guia operacional do RASAi - Search & AI Readiness Auditor para execução local, configuração do console e leitura dos resultados.

## Instalação local no Windows

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

## Abrir o console

```powershell
rasai-console
```

Menu principal:

```text
1. Preparar auditoria
2. Auditorias / histórico
3. Relatórios consolidados
4. Inteligência Artificial
5. Integrações e serviços
6. Todas as configurações
7. Sistema / restaurar padrões
H. Ajuda
Q. Sair
```

## Fluxo recomendado

1. abra **Preparar auditoria**;
2. informe entrada, projeto, `Device`, idioma/mercado e timezone;
3. selecione um ou mais catálogos `CAT-*`;
4. configure imediatamente as particularidades mostradas no submenu de cada catálogo;
5. resolva qualquer catálogo `BLOQUEADO` antes de executar;
6. configure IA somente quando o plano escolhido puder ou precisar utilizá-la;
7. salve parâmetros não sensíveis na sessão/arquivo quando fizer sentido;
8. revise o estado do plano e a previsão de consumo/custo quando o fluxo canônico a apresentar;
9. execute;
10. leia o resultado distinguindo o que foi solicitado, não solicitado, limitado, falho ou indisponível.

## Preparar auditoria

A tela atual usa:

```text
ESCOPO
CATÁLOGO DA AUDITORIA
PLANO DA PRÓXIMA AUDITORIA
EXECUÇÃO / ARMAZENAMENTO
AÇÕES
```

Não há Perfil da próxima auditoria. A seleção do usuário é o próprio plano de catálogos.

### Catálogos

```text
CAT-01 Fundamentos técnicos e descoberta
CAT-02 Acessibilidade
CAT-03 Conteúdo, semântica e dados estruturados
CAT-04 Web Performance
CAT-05 Search & AI Intelligence
CAT-06 Apdex de navegação
CAT-07 Apdex de experiência
CAT-08 Análise profunda e melhorias
CAT-09 Remediações
```

Selecionar um catálogo abre suas opções imediatamente. O operador não precisa atravessar uma sequência fixa de telas.

Cada submenu mostra estado, capacidades/fontes, configuração efetiva, uso de IA, resultado esperado, configurações relacionadas, persistência e ações.

### Estados

```text
APTO                 -> requisitos mínimos conhecidos atendidos
APTO COM LIMITAÇÕES  -> executável, mas com fonte/enriquecimento opcional indisponível
BLOQUEADO            -> falta requisito obrigatório do catálogo selecionado
NÃO SELECIONADO      -> fora do plano desta execução
```

Recurso não selecionado não deve bloquear o plano.

## Escopo e Device

`Device` pode ser:

```text
mobile
desktop
both
```

Mobile/Desktop são dimensões/resultados derivados, não catálogos separados.

## IDs de configuração

Números curtos operam a tela atual. IDs canônicos identificam a mesma variável em qualquer caminho do console.

Ao abrir um catálogo, configurações relacionadas podem ser acessadas diretamente por seus IDs sem criar cópias da variável.

## Persistência

Após uma alteração não sensível, o console permite:

```text
1. manter somente nesta sessão
2. manter na sessão e salvar no arquivo de configuração
```

Secrets nunca entram no INI. O armazenamento Windows/User continua sendo usado somente por ação explícita.

A seleção `CAT-*` pertence ao plano da próxima execução. O snapshot secret-free do AUD registra essa seleção para reutilização e futura correspondência com os relatórios.

## Inteligência Artificial

Existe uma IA principal/orquestrador por execução.

```text
none       -> sem IA
provider   -> provider explicitamente selecionado
auto       -> orquestração canônica entre providers elegíveis
```

O catálogo informa onde IA é:

```text
NONE
OPTIONAL
REQUIRED
```

`CAT-03` pode usar IA para análise semântica/contextual; `CAT-08` exige IA para análise profunda; `CAT-09` pode usar IA para enriquecimento de remediações. Selecionar Acessibilidade, Web Performance, Search & AI Intelligence ou Apdex não ativa IA por si só. IA advisory não altera evidência/scoring determinístico.

Quando somente `CAT-03` e/ou `CAT-09` tornam IA possível, o plano começa em **Executar sem IA (recomendado)**. Se a IA principal estiver configurada, use `U. Executar com IA` para ativar o enriquecimento na próxima auditoria. Ao ativar IA, a previsão de consumo/custo aparece no fluxo canônico antes da confirmação da execução. Com `CAT-08`, IA é obrigatória.

AUTO mantém a política existente de custo, elegibilidade, disponibilidade, quarentena, circuit breaker, fallback e limite de tentativas.

Quando houver consumo estimável, o preview/aceite canônico ocorre antes da execução.

## Search & AI Intelligence

`CAT-05` agrupa o objetivo do usuário, mas mantém as fontes independentes:

- Search Intelligence / SERP;
- Google Search Console;
- Visibilidade em IA;
- observabilidade externa aplicável.

### SERP

Termos, depth, região, device e classificação competitiva continuam configuráveis. A profundidade representa a posição orgânica máxima tentada (`10 = Top 10`, `20 = Top 20`).

SERP com provider/key aptos mas sem termos ainda não produz a coleta; ao selecionar `CAT-05`, o console orienta a completar uma fonte Search suficiente.

### Google Search Console

GSC depende de OAuth, property, política e cobertura estrutural da URL. SERP e GSC não são dependência um do outro.

Quando GSC é obrigatório e incompatível, o catálogo bloqueia. Quando é automático/opcional e não aplicável, não deve transformar uma fonte Search válida em falha global.

Consulte [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md).

## Web Performance

`CAT-04` usa os adapters/contratos atuais de PageSpeed, Lighthouse e CrUX conforme configuração.

Ausência de field data ou resposta externa é limitação/indisponibilidade; não deve ser convertida em score artificial.

## Apdex de navegação

`CAT-06` executa amostras sintéticas conforme thresholds, volume e carga configurados. O cálculo não depende de IA.

## Apdex de experiência

`CAT-07` depende de `CAT-06`. Selecioná-lo inclui Navigation Apdex no plano.

Enquanto o mix estiver herdado:

```text
Device=mobile   -> 100% mobile
Device=desktop  -> 100% desktop
Device=both     -> 60% mobile + 40% desktop
Tablet          -> 0% no default herdado
```

Selecionar `CAT-07` não ativa IA. Qualquer correlação por IA pertence aos catálogos consumidores que a solicitam, como `CAT-08`.

## Análise profunda e melhorias

`CAT-08` consome as evidências dos catálogos produtores selecionados. Sem fonte de evidência ou sem IA principal apta, fica `BLOQUEADO`.

## Remediações

`CAT-09` transforma achados em ações técnicas/editoriais rastreáveis. Remediações determinísticas continuam válidas sem IA; IA pode enriquecer contextualização/exemplos sem alterar scoring por opinião.

## Integrações e serviços

Use essa superfície para configurar GSC, SERP, PageSpeed/Lighthouse, CrUX, observabilidade e demais serviços publicados no catálogo técnico.

Diagnósticos de integração são consultivos: um teste bem-sucedido não garante disponibilidade futura e uma falha transitória não deve ser confundida automaticamente com erro de configuração.

## Todas as configurações

Cada variável deve informar finalidade, owner, contexto, valor/origem, estado, domínio/default e impacto. Booleanos/enums/listas fechadas usam seleção guiada; texto livre só é usado para domínios realmente abertos.

## Auditorias e histórico

Carregar configuração de um `AUD-*` prepara **nova execução**; o AUD de origem não é alterado. Credenciais não são copiadas.

Quando o snapshot contém `audit_catalog`, a lista `CAT-*` é restaurada junto da configuração não sensível.

Reprocessamento continua sendo outra operação: ele completa pendências do mesmo AUD segundo os contratos atuais.

## Relatórios

A estrutura `CAT-*` é persistida agora para permitir correspondência futura nos HTMLs. A mudança visual completa dos relatórios não faz parte desta etapa.

A direção de UX é manter equivalência semântica:

```text
pedido no console -> configuração efetiva -> evidências/resultados -> relatório
```

Leia sempre separadamente medição determinística, indisponibilidade de fonte, execução parcial e conteúdo advisory por IA.

## CLI básica

O catálogo descrito neste documento é uma UX do `rasai-console`. A CLI tradicional mantém seus contratos próprios.

```powershell
rasai audit https://example.com --project "Exemplo"
rasai audit https://example.com --device-context desktop
rasai audit https://example.com --device-context both
```

## Segurança

- não copie API keys para issues, reports ou documentação;
- o INI não contém secrets;
- Windows/User só é alterado por ação explícita;
- key configurada não garante quota/saldo;
- Synthetic Apdex deve respeitar autorização e limites de carga;
- diagnóstico de integração é observação pontual, não garantia futura.

## Documentos relacionados

- [AUDIT_CATALOG_WORKFLOW.md](AUDIT_CATALOG_WORKFLOW.md)
- [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md)
- [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md)
- [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md)
- [GSC_SCOPE_POLICY.md](GSC_SCOPE_POLICY.md)
- [CONTENT_ANALYSIS_CONTEXT.md](CONTENT_ANALYSIS_CONTEXT.md)
- [OUTPUTS_AND_ARTIFACTS.md](OUTPUTS_AND_ARTIFACTS.md)
