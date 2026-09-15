# Perfis da próxima auditoria

Perfis são presets temporários aplicados à próxima execução do `rasai-console`. Eles reduzem a quantidade de ajustes manuais sem criar uma nova fonte de verdade.

## Acesso

Na preparação:

```text
INÍCIO > PREPARAR AUDITORIA

[ PERFIL DA PRÓXIMA AUDITORIA ]
1. 00000001  Perfil base : ...
```

Perfis nomeados ficam disponíveis quando a entrada representa uma única URL explícita. Arquivo/TXT e múltiplas URLs usam configuração manual conforme o contrato atual.

## Camadas e precedência

A configuração efetiva segue:

```text
ajuste explícito feito depois da seleção do perfil
> overlay temporário do perfil
> configuração normal da sessão / INI / SO
> default canônico do produto
```

A camada vencedora vale para a execução correspondente, mas não sobrescreve persistentemente as camadas inferiores.

## O que um perfil pode fazer

Um perfil pode projetar escolhas já suportadas pelos contratos existentes, por exemplo:

- ativar módulos compatíveis;
- selecionar políticas de execução da próxima auditoria;
- solicitar Web Performance;
- solicitar capacidades de Search quando suas dependências já existem;
- solicitar experiência sintética quando os parâmetros necessários estão válidos;
- solicitar análise profunda quando há URL única e IA principal apta;
- projetar política de uso de GSC para aquela execução.

## O que um perfil não faz

Um perfil não pode:

- criar ou persistir credenciais;
- alterar `Windows/User` ou `Windows/Machine`;
- gravar o preset como nova fonte estrutural no INI;
- inventar termos SERP;
- inventar contexto editorial/YMYL específico;
- inventar parâmetros avançados de Apdex;
- alterar scoring ou metodologia;
- criar um provider de IA especializado para um módulo;
- substituir validadores ou gates do runtime.

## Readiness do catálogo

Todos os presets do catálogo permanecem visíveis. Cada item é classificado dinamicamente.

### APTO

O preset possui as dependências conhecidas necessárias e pode ser selecionado.

### CONFIGURAR

O preset continua visível, mostra as pendências operacionais e não é aplicado até que as dependências obrigatórias estejam válidas.

Isso evita iniciar uma execução com expectativa de cobertura que a configuração atual não consegue sustentar.

## Catálogo

O catálogo vigente inclui:

1. SEO / Search Readiness;
2. GEO / AI Readiness;
3. Performance;
4. Accessibility;
5. Web Quality;
6. SEO + GEO;
7. SEO + GEO + Performance;
8. Search Intelligence / SERP;
9. Synthetic Experience;
10. Deep Analysis URL;
11. Completo seguro;
12. Completo máximo;
13. Personalizado.

A ordem e os identificadores internos pertencem ao catálogo canônico. A UI usa os labels publicados por esse contrato.

## Dependências que não são fabricadas

### Search Intelligence / SERP

Exige termos Search e um contrato SERP válido. Em modo live, provider/engine e credencial também precisam atender ao preflight.

O perfil não cria termos. O operador configura Search Intelligence na capacidade correspondente da preparação.

### Synthetic Experience

Exige configuração sintética válida. Experience Apdex depende do Navigation Apdex e respeita limites de carga/amostragem.

O perfil não inventa um mix personalizado. Enquanto herdado, o mix segue `Device`.

### Deep Analysis URL

Exige:

- uma URL única explícita;
- análise profunda habilitada pelo perfil/capacidade;
- IA principal apta.

Provider, modelo e reasoning vêm da seleção principal de IA.

### GEO / contexto editorial

Contexto editorial/YMYL explícito pertence ao domínio da auditoria. `AUTO` permanece uma política de resolução; o perfil não transforma contexto desconhecido em fato.

## IA principal

Existe uma única seleção principal de IA por execução.

Perfis podem exigir IA, permitir IA se disponível ou funcionar sem IA, conforme a finalidade. Quando IA é necessária, o perfil usa a seleção principal e o runtime canônico.

Módulos como Improvement Intelligence, remediações e demais consumidores compatíveis não recebem uma seleção paralela de provider.

Em `AUTO`, a execução reutiliza:

- catálogo de providers elegíveis;
- disponibilidade/configuração;
- política de custo;
- quarentena;
- circuit breaker;
- fallback;
- limite de tentativas.

GitHub Copilot segue a elegibilidade publicada pelo provider registry; providers explicit-only não entram automaticamente no pool apenas porque estão configurados.

## Política GSC por perfil

Perfis podem projetar a política de Google Search Console da próxima execução sem reescrever a configuração global.

As políticas publicadas pelo contrato incluem comportamentos equivalentes a:

```text
usar se compatível
exigir GSC
não usar nesta execução
herdar política global
```

A projeção é aplicada no ambiente privado da execução quando necessário. A configuração da sessão principal não é regravada para simular o perfil.

## Perfil base e estado personalizado

Depois de aplicar um preset, o operador pode fazer ajustes finos. Esses ajustes vencem o overlay no domínio alterado.

A UI deve deixar claro que existe um perfil base e que a configuração efetiva pode estar personalizada. Se um ajuste posterior invalidar uma dependência obrigatória, o readiness deve voltar a `CONFIGURAR` e o preflight passa a ser a autoridade para bloquear a execução incompatível.

## Completo seguro

`Completo seguro` combina cobertura ampla sem ativar automaticamente capacidades de maior custo/carga ou que exigem inputs específicos não inventáveis, como SERP, experiência sintética pesada ou análise profunda.

A finalidade é oferecer uma composição ampla com menor necessidade de pré-parametrização especializada.

## Completo máximo

`Completo máximo` representa cobertura funcional do catálogo. Ele só fica `APTO` quando as dependências obrigatórias das capacidades incluídas estão atendidas.

“Máximo” não significa ignorar segurança, quota, limites, preflight ou validação. Ele não desativa guardrails.

## Persistência

Selecionar um perfil não grava o preset no `rasai-console.ini`. Se o usuário salvar a configuração depois de aplicar e ajustar o perfil, o writer canônico persiste apenas os parâmetros não sensíveis que fazem parte do contrato normal de configuração.

Secrets permanecem fora do arquivo.

## Execução

O perfil é consumido pela mesma execução que a configuração manual. Não existe um pipeline alternativo por perfil.

A sequência conceitual é:

```text
defaults
+ sessão/INI/SO
+ overlay do perfil
+ ajustes explícitos posteriores
-> configuração efetiva
-> preflight
-> pipeline normal do RASAi
```

Documentos relacionados: [INTERACTIVE_CONSOLE.md](INTERACTIVE_CONSOLE.md), [CONSOLE_CONFIGURATION_UX.md](CONSOLE_CONFIGURATION_UX.md), [CONSOLE_SEARCH_INTELLIGENCE.md](CONSOLE_SEARCH_INTELLIGENCE.md) e [PROVIDER_SETUP.md](PROVIDER_SETUP.md).
