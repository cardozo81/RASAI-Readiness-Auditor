# Contrato de UX para configuração no console

Este documento define a arquitetura de informação e o sistema de interação do `rasai-console`.

O runtime e os registries canônicos são a fonte de verdade. A interface organiza e explica essas capacidades; ela não redefine execução, scoring, providers, retries, quarentena, fulfillment ou metodologia.

## 1. Modelo mental

A navegação usa dois eixos complementares:

1. **objetivo/capacidade do usuário**, para preparar a auditoria e entender o resultado esperado;
2. **owner canônico da configuração**, para editar a variável uma única vez.

Uma capacidade pode depender de configurações pertencentes a vários serviços. A tela da capacidade referencia essas dependências e abre seus owners; ela não duplica variáveis.

Regra estrutural:

> Cada configuração possui um único owner canônico. Capacidades consumidoras apenas referenciam esse owner.

## 2. Primeiro nível

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

`Inteligência Artificial` é uma macroárea transversal. `Integrações e serviços` concentra dependências externas. `Todas as configurações` é a visão técnica completa.

## 3. Preparar auditoria

A ordem da tela é:

```text
PERFIL DA PRÓXIMA AUDITORIA
ESCOPO
ANÁLISES / RESULTADOS
RESULTADOS SISTÊMICOS
EXECUÇÃO / ARMAZENAMENTO
AÇÕES
```

O perfil aparece antes dos ajustes porque funciona como preset/base. Alterações explícitas posteriores podem personalizar a próxima execução sem alterar o contrato do preset armazenado.

### 3.1 Convenção de seleção

```text
número curto = escolha contextual da tela
ID de 8 dígitos = identidade estável da configuração
letra = ação/navegação
— = linha informativa, automática ou derivada
```

Os números curtos ajudam a operar a tela. IDs estáveis permitem localizar a mesma configuração por caminhos diferentes.

### 3.2 IDs estáveis

Variáveis do catálogo recebem um ID numérico de 8 dígitos calculado a partir do nome canônico. O ID não depende de ordem alfabética, owner, filtro ou caminho de navegação.

Configurações-base do console usam IDs reservados, por exemplo:

```text
00000001 Perfil
00000002 Entrada
00000003 Projeto
00000004 Device
00000005 Idioma / mercado
00000006 Timezone
00000007 Raiz de auditorias
00000008 IA principal
00000009 Web Performance
00000010 Inputs Search
00000011 Apdex navegação
00000012 Apdex experiência
00000013 Análise profunda
00000014 Remediações
```

## 4. Device como autoridade

`Device` aceita somente:

```text
mobile
desktop
both
```

Os relatórios Mobile e Desktop são resultados derivados:

| Device | Mobile | Desktop |
|---|---|---|
| `mobile` | `INCLUÍDO` | `NÃO APLICÁVEL` |
| `desktop` | `NÃO APLICÁVEL` | `INCLUÍDO` |
| `both` | `INCLUÍDO` | `INCLUÍDO` |

Não existe seleção independente desses dois relatórios.

## 5. Apdex de experiência

O mix normal de Experience Apdex herda `Device`:

```text
mobile  -> mobile=100,desktop=0,tablet=0
desktop -> mobile=0,desktop=100,tablet=0
both    -> mobile=60,desktop=40,tablet=0
```

Esse valor é **derivado-customizável**:

- enquanto herdado, acompanha `Device`;
- alterar outros parâmetros do Apdex não quebra a herança;
- alterar o próprio mix cria um override;
- mix herdado não é materializado no INI como override;
- `tablet` permanece apenas como opção avançada da população de Experience Apdex.

## 6. Análises e resultados

A preparação expõe capacidades com estados calculados pelos contratos existentes. Exemplos:

```text
Domínio e descoberta       INCLUÍDO
Acessibilidade             INCLUÍDO
Web Performance            APTO / DESABILITADO / CONFIGURAR
Search Intelligence        APTO / DESABILITADO / CONFIGURAR
Apdex de navegação         APTO / DESABILITADO / CONFIGURAR
Apdex de experiência       APTO / DESABILITADO / CONFIGURAR
Quality & decisão          DERIVADO
```

Uma capacidade automática não recebe checkbox apenas para reproduzir algo que o pipeline já gera. Uma capacidade opcional mostra readiness e permite abrir os parâmetros que efetivamente controla.

## 7. Tela de capacidade

A estrutura é:

```text
ESTADO
INFORMAÇÃO
CONFIGURAÇÃO DA ANÁLISE         # quando existe handler próprio
DEPENDÊNCIAS / CONFIGURAÇÕES RELACIONADAS
AÇÕES
```

Somente configurações consumidas por aquela capacidade devem aparecer. O usuário pode selecionar o ID relacionado e editar a variável no owner canônico.

## 8. Catálogo de configurações

As visualizações disponíveis são:

```text
Por owner funcional
Ordem alfabética
Por estado
Somente modificadas
Somente pendentes
Localizar por ID/nome/finalidade
```

Os owners representam responsabilidade funcional, não fabricante como eixo obrigatório. Exemplos:

```text
Inteligência Artificial / provider
Search / Google Search Console
Search / SERP
Web / PageSpeed-Lighthouse
Web / CrUX
Synthetic Apdex / Navigation
Synthetic Apdex / User Experience
Identity / OIDC
Plataforma / Control plane
```

Fornecedor pode aparecer no nome do recurso, mas não deve fragmentar a arquitetura de informação.

## 9. Tela de variável

Todo editor canônico segue quatro blocos:

### INFORMAÇÃO

- para que serve;
- owner;
- contexto;
- quando é necessária;
- impacto de custo, quota, carga ou segurança;
- observações.

### ESTADO ATUAL

- valor ou indicação redigida;
- origem;
- estado de decisão/readiness.

### DOMÍNIO / INPUT

- tipo;
- valores aceitos;
- default;
- exemplo/referência/documentação quando disponível.

### AÇÕES

- definir/alterar;
- limpar override da sessão;
- restaurar default/ausência canônica;
- gerenciar Windows/User para secrets;
- abrir documentação;
- voltar.

## 10. Configurações fechadas e abertas

Nenhuma configuração com domínio fechado deve depender de texto livre.

Ordem preferencial:

1. booleano guiado;
2. enum guiado;
3. lista fechada;
4. provider/model/reasoning derivados do registry;
5. valor dependente recalculado a partir da seleção vigente;
6. texto livre apenas quando o domínio realmente é aberto.

Valores abertos incluem URL, path, property, locale, identificador externo, secret e números de faixa contínua.

## 11. Estado, cor e símbolo

Cor é reforço, nunca informação exclusiva.

| Estado | Semântica visual |
|---|---|
| `APTO`, `INCLUÍDO`, `CONCLUÍDO`, `HABILITADO` | sucesso/disponível |
| `CONFIGURAR`, `PARCIAL`, `APTO COM LIMITAÇÕES` | atenção |
| `ERRO`, `INDISPONÍVEL`, `BLOQUEADO` | impedimento |
| `AUTOMÁTICO`, `HERDADO`, `DERIVADO`, `PERSONALIZADO` | composição/origem |
| `DESABILITADO`, `NÃO APLICÁVEL`, `PADRÃO` | neutro |

`CONFIGURAR` significa que uma dependência conhecida exige ação; não é sinônimo de falha do website.

## 12. Origem

A UI pode indicar:

```text
SESSÃO
ARQUIVO
WINDOWS/USER
WINDOWS/MACHINE
DEFAULT
NÃO CONFIGURADO
```

A origem deve ser mostrada especialmente quando um valor efetivo pode surpreender o operador por precedência.

## 13. Persistência e destino da alteração

Após uma edição não sensível, o console oferece:

```text
1. Aplicar somente nesta sessão
2. Aplicar na sessão e salvar no arquivo de configuração
```

Secrets usam destino próprio e nunca entram no INI.

O comando geral `Salvar configuração` persiste o estado não sensível da próxima auditoria, incluindo inputs Search configurados na sessão.

## 14. Search Intelligence

A UI separa:

- **inputs da próxima execução**: termos, depth, região, device e análise competitiva;
- **governança/provider**: `RASAI_SERP_*` e registry SERP;
- **credencial**: variável secreta do provider;
- **IA principal**: usada somente quando alguma extensão compatível realmente exige IA.

Os inputs Search são session-first. A persistência no INI ocorre somente por ação explícita de salvar configuração.

## 15. Inteligência Artificial

Existe uma seleção principal de IA por execução. O console não cria providers especializados por módulo.

`AUTO` reutiliza o runtime central para:

- elegibilidade;
- custo estimado;
- disponibilidade;
- quarentena;
- circuit breaker;
- fallback e limite de tentativas.

Provider, modelo e reasoning são derivados do registry. A configuração de uma capacidade consumidora referencia essa seleção principal.

## 16. Perfis

Perfis são presets da próxima auditoria, não uma fonte persistente paralela.

A precedência efetiva é:

```text
ajuste explícito posterior ao perfil
> overlay do perfil
> configuração normal de sessão / INI / SO
> default canônico
```

A camada vencedora não sobrescreve persistentemente as inferiores. Perfil `CONFIGURAR` fica visível para orientação, mas não é aplicado até resolver as dependências obrigatórias.

## 17. Secrets

Regras obrigatórias:

- nunca mostrar conteúdo real após a entrada;
- nunca gravar secret em `rasai-console.ini`;
- nunca copiar secret de snapshot de AUD;
- Windows/User exige ação explícita;
- Windows/Machine é somente observado;
- cancelamento ocorre antes de substituir o valor vigente sempre que a edição usa fluxo staged.

## 18. Restauração

Restauração por variável devolve o valor ao default/ausência canônica e aplica o mesmo mecanismo de configuração usado pelo restante do console.

A restauração integral da baseline do produto pertence a:

```text
INÍCIO > Sistema / restaurar padrões
```

Ela não é uma ação da preparação da auditoria.

## 19. Critério de aderência

Uma superfície de configuração é aderente quando:

- usa o owner canônico da variável;
- oferece ajuda e impacto antes da edição;
- guia domínios fechados;
- mostra estado e origem;
- distingue automático, derivado, herdado e personalizado;
- não duplica provider/configuração em módulos consumidores;
- preserva secrets;
- usa readiness real existente;
- retorna ao contexto de navegação de origem;
- não cria comportamento funcional fora do runtime.

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md), [CONSOLE_VARIABLE_RESET.md](CONSOLE_VARIABLE_RESET.md), [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
