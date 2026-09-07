# Provider registry

O registry canônico centraliza metadados usados por CLI, console e adapters para evitar listas divergentes de providers, modelos, credenciais e aliases.

Arquivo principal:

```text
src/rasai/provider_registry.py
```

## Providers concretos

```text
openai
deepseek
mimo
xai
qwen
gemini
anthropic
```

Aliases:

```text
grok   -> xai
claude -> anthropic
```

## AUTO

A cadeia automática permanece deliberadamente:

```text
OpenAI -> DeepSeek -> MiMo
```

Providers adicionais permanecem `explicit-only` e não entram em AUTO enquanto a qualificação correspondente não for promovida.

## Metadados

Cada registro pode expor:

- identificador e nome humano;
- variável de credencial;
- modelos suportados;
- modelo default;
- variável de modelo;
- variável/valores de reasoning quando suportados;
- endpoint override quando aplicável;
- aliases;
- elegibilidade AUTO;
- qualificação/reliability;
- restrição de prefixo de credencial.

## Defaults públicos

A política pública atual privilegia o modelo mais simples e o menor esforço suportado quando não há override explícito. Essa política é aplicada acima dos adapters históricos para preservar compatibilidade interna.

## MiMo

O registro expõe a restrição de chave PAYG `sk-...` para impedir que Token Plan `tp-...` seja tratado como credencial compatível pelo adapter atual.

## Fonte de verdade e identificadores históricos

Os adapters e schemas existentes continuam sendo a fonte técnica de comportamento. Nomes internos de módulos/eventos podem preservar identificadores históricos para compatibilidade, mas consumidores públicos devem apresentar nomenclatura funcional.
