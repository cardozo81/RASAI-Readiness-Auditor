# Versionamento do RASAi

## Objetivo

O RASAi mantém dois eixos de versão independentes porque eles respondem a perguntas diferentes:

- **versão do pacote/auditor** - identifica o código executável que produziu uma auditoria;
- **versões metodológicas** - identificam contratos de índice, scoring, agregação, pesos, regras e demais metodologias persistidas.

Esses eixos não devem ser acoplados artificialmente.

## Versão do pacote/auditor

A versão canônica do produto Python é mantida de forma consistente em:

```text
pyproject.toml                -> [project].version
src/rasai/__init__.py         -> rasai.__version__
```

A CLI `rasai --version` usa `rasai.__version__`. Novas auditorias persistem essa mesma versão como `auditor_version`.

Consequência: depois que um commit é estabelecido como marco RC/release, qualquer alteração funcional no código que possa mudar comportamento de execução deve receber nova versão do pacote antes de ser tratada como novo estado publicável. Dois estados funcionalmente diferentes do auditor não devem materializar o mesmo `auditor_version`.

### Incremento

O projeto usa versionamento semântico no formato `MAJOR.MINOR.PATCH` para o pacote:

- **PATCH** - correção compatível de bug, hardening ou ajuste funcional sem quebra de contrato público;
- **MINOR** - nova capacidade compatível ou ampliação relevante de superfície pública;
- **MAJOR** - mudança incompatível de contrato público.

O incremento é aplicado ao estado publicável, não a cada commit intermediário de uma branch de trabalho. Um bugfix posterior ao marco `0.1.0 RC`, por exemplo, passa a identificar o auditor como `0.1.1` quando integrado ao estado vigente.

## Versões metodológicas

Identificadores como os abaixo possuem ciclo próprio e **não** são alterados apenas porque o pacote recebeu patch/minor:

```text
SARI-001
SCORE-GEO-004
HIERARCHICAL_WEIGHTED_READINESS_V1
BR-GEO-*
```

Uma versão metodológica só muda quando o próprio contrato metodológico muda: fórmula, agregação, pesos, regra, interpretação ou outro elemento que exija distinguir resultados metodologicamente.

Bugfix de console, persistência, UX ou infraestrutura que não altera esses contratos não muda suas versões públicas.

## Protótipos

Versões em `prototypes/**/package.json` pertencem aos protótipos privados e não acompanham automaticamente a versão do pacote Python. Elas só devem mudar quando houver decisão específica de versionar/publicar aquele workspace.

## Testes e fixtures

Valores de versão usados como **dados históricos ou fixtures** em testes não devem ser substituídos mecanicamente em um bump. Só os pontos canônicos do produto devem mudar, salvo quando um teste estiver explicitamente validando a versão vigente.

## Rastreabilidade de publicação

Toda alteração de versão deve deixar rastreabilidade no GitHub por issue/PR ou outro registro equivalente, indicando:

- versão anterior e nova;
- motivo do incremento;
- se houve ou não mudança metodológica;
- relação com bugs/features que motivaram a mudança;
- checks relevantes executados.

Não criar release/tag automaticamente apenas por incrementar o código. Release e tag representam uma decisão de publicação/distribuição e devem ser feitos quando o estado estiver aprovado para esse marco.
