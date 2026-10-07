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

Não criar release/tag automaticamente apenas por incrementar o código. **Bump de versão e decisão de publicação são decisões distintas.** Release e tag representam uma decisão explícita de publicação/distribuição e devem ser feitos somente quando o estado estiver aprovado para aquele marco.

Uma tag/release publicada identifica um commit imutável. Depois de publicada:

- a tag histórica não deve ser movida, recriada sobre outro commit nem acompanhada até a HEAD;
- o GitHub Release deve continuar associado ao mesmo baseline histórico;
- alterações posteriores pertencem a um estado **unreleased** até que outro marco seja aprovado;
- um estado funcionalmente diferente não deve ser apresentado como se fosse o mesmo release;
- o próximo SemVer só deve ser escolhido depois de classificar e validar as mudanças acumuladas desde o último release.

A versão declarada no código, isoladamente, não prova que a HEAD atual foi publicada. Enquanto não houver novo gate de release, a HEAD pode continuar declarando a última versão de pacote conhecida e, ainda assim, representar desenvolvimento pós-release não publicado. Esse intervalo deve ser tratado explicitamente como `unreleased`.

## Marcos históricos e estado pós-v0.7.0

Estado reconciliado em 2026-10-06 para a governança da issue #243:

| Marco | Commit canônico | Publicação verificada |
| --- | --- | --- |
| `v0.5.1` | `1f40e9bf69e0859b1a959bff4c302c0291435bb1` | tag anotada e GitHub Release `RASAi 0.5.1` |
| `v0.6.0` | `f345fd0b8acfa550ea340853547c6f8589c7462e` | tag anotada; nenhum GitHub Release encontrado na reconciliação |
| `v0.7.0` | `c66188e6e3088603b08eb750eece272451d6342c` | tag anotada e GitHub Release `RASAi 0.7.0`; baseline histórico confirmado |

O commit `c66188e6e3088603b08eb750eece272451d6342c` é o baseline histórico do package/runtime `0.7.0`. A `main` avançou funcionalmente depois dele. Portanto:

```text
main posterior a c66188e6... = pós-v0.7.0 / unreleased
```

A HEAD posterior não deve receber nem reutilizar a tag `v0.7.0`. A publicação histórica `v0.7.0` foi reconciliada e representa exclusivamente `c66188e6e3088603b08eb750eece272451d6342c`.

## Imutabilidade de releases

Para novos marcos SemVer, o repositório deve usar o recurso **Immutable Releases** do GitHub antes da publicação. O fluxo canônico é:

```text
estado tecnicamente aprovado
-> definir SemVer
-> criar release como draft
-> validar tag/commit e anexar assets aplicáveis
-> publicar release imutável
-> verificar integridade do release
```

Regras:

- release publicado não pode depender apenas de convenção humana para impedir movimentação da tag;
- assets devem ser anexados antes da publicação, porque releases imutáveis bloqueiam alteração posterior dos assets;
- a tag específica do release deve ficar bloqueada ao commit publicado;
- `gh release verify <tag>` ou verificação equivalente deve fazer parte do fechamento do marco quando o release for imutável;
- releases históricos anteriores à habilitação do recurso não devem ser apagados/republicados apenas para obter imutabilidade retroativa, salvo decisão específica de governança com análise de risco;
- notas e metadados editoriais podem continuar ajustáveis quando o GitHub permitir, mas o baseline técnico (tag, commit e assets publicados) permanece congelado.

A issue #247 controla a habilitação administrativa de Immutable Releases antes do próximo marco pós-`v0.7.0`.

Nenhum próximo número de versão é inferido deste estado. Antes de novo bump/publicação, deve existir validação técnica da `main` cobrindo a integridade do processo de auditoria, a coerência entre configuração, coleta, persistência, derivação e apresentação, e a classificação das mudanças desde o último baseline publicado.
