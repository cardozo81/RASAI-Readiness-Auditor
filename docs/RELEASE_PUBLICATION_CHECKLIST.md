# Checklist de preparação e publicação da candidata v0.9.0

> **REGISTRO HISTÓRICO PRÉ-PUBLICAÇÃO:** a [release `v0.9.0`](https://github.com/cardozo81/RASAI-Readiness-Auditor/releases/tag/v0.9.0) foi publicada em 29/10/2026, `immutable=true`, sobre `5da8e6247094c20dcdbe770474ac31e7f93383b2`. As declarações `DRAFT`, `NO-GO`, branch de preparação e CI pendente abaixo descrevem decisões anteriores à publicação e são preservadas para rastreabilidade, não como status atual.

**Estado:** PREPARAÇÃO, NÃO PUBLICADO. Este roteiro é um artefato operacional, não uma autorização de criação de tag ou de GitHub Release.

## 1. Referências verificadas

| Referência | Estado / SHA |
| --- | --- |
| Última GitHub Release pública | `v0.8.0` (tag imutável, `4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08`) |
| Baseline de `main` após a PR #675 | `810cc076052df93f1d18c6807c18e63b225d9473` |
| Homologação completa anterior | PR #675, 37/37 workflows e 46/46 jobs aprovados; 5.649 testes aprovados, 29 ignorados, 134 subtestes |
| CI do merge em `main` | 18/18 workflows de evento `push` aprovados no SHA acima |
| Branch exclusiva de preparo | `release/prepare-v0.9.0` |
| Versão de pacote proposta | `0.9.0` em `pyproject.toml` e `src/rasai/__init__.py` |
| Método de scoring vigente | `SCORE-GEO-005` para novas AUDs; `SCORE-GEO-004` para replay histórico |
| Publicação `v0.9.0` | **NÃO AUTORIZADA E NÃO REALIZADA** |

A CI anterior não certifica automaticamente o novo SHA que altera a versão. O release deve ser identificado pelo commit exato que estiver em `main` depois de integração autorizada.

## 2. Inventário e notas

A comparação `v0.8.0...main@810cc076` informa 1.501 commits à frente e zero atrás; a API limita sua lista de arquivos a 300. O inventário local prévio em [RELEASE_CHANGE_INVENTORY.tsv](RELEASE_CHANGE_INVENTORY.tsv) cobre 822 entradas do diff entre a tag e `02d2a7fb1a00abe907a5595602dbbab6bcae0603`. O [delta incremental](RELEASE_CHANGE_DELTA_V0_9_0.tsv) registra 6 commits e 22 caminhos entre essa baseline e a `main` integrada. Os 22 caminhos podem já constar do inventário original e não devem ser somados como arquivos únicos.

Revisar [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md) como texto-fonte de release, preservando limites de funcionalidades, ressalvas da homologação física e compatibilidade. O changelog de 1.501 commits não pode ser interpretado como 1.501 novas funcionalidades; o inventário é por arquivos, não por contratos publicados.

## 3. Gate da branch candidata

- [x] Abrir branch exclusiva derivada de `main@810cc076052df93f1d18c6807c18e63b225d9473`.
- [x] Atualizar os dois identificadores canônicos do pacote para `0.9.0` sem tocar nas versões metodológicas.
- [x] Registrar notas de mudanças, delta pós-inventário e decisões históricas sem transformar evidência limitada em aceitação irrestrita.
- [ ] Executar o fluxo `Public Contract Consistency` e testes de versão na PR da candidata.
- [ ] Executar `Full RASAi Regression` (`pytest -q`, Chromium, Python 3.13) no **SHA exato** da candidata.
- [ ] Conferir todos os workflows e jobs aplicáveis como `completed/success`, sem falhas/pendências.
- [ ] Conferir `rasai --version`, `python -c "import rasai; print(rasai.__version__)"` e `pip check` num ambiente isolado, quando o workflow operacional aplicável executar.
- [ ] Revisar no diff final as notas, links internos e declarações de versão; preservar documentos históricos imutáveis.
- [ ] Registrar autorização expressa de merge da **nova PR**; nenhuma autorização anterior para #675 se estende a ela.

Não executar auditorias externas ou providers tarifados para a certificação deste bump; os testes devem reutilizar o baseline sintético/offline já homologado.

## 4. Gate pós-integração

Depois do merge expressamente autorizado, verificar a `main` e os workflows de `push` no commit final, além de sincronizar o ambiente local com `git pull --ff-only origin main`. A aprovação da branch sem a confirmação do HEAD integrado não basta para publicação.

A publicação ainda exige verificar pelo GitHub que a proteção **Immutable Releases** está habilitada para a próxima release. O fato de `v0.8.0` possuir `immutable=true` é evidência da release histórica, não garantia de configuração do próximo marco. Registrar na decisão final a identidade da tag, o SHA definitivo, o estado do setting e os assets efetivamente autorizados.

## 5. Decisão e publicação (somente após autorização específica)

- [ ] Operador autoriza explicitamente **criar a tag e uma GitHub Release draft** da `v0.9.0` no SHA final aprovado.
- [ ] Conferir que a tag `v0.9.0` e a release ainda não existem; jamais mover ou substituir uma tag publicada.
- [ ] Criar a release inicialmente como **draft**, apontada ao SHA aprovado; anexar e conferir todos os assets autorizados antes da publicação.
- [ ] Operador autoriza explicitamente **publicar** a GitHub Release `v0.9.0`.
- [ ] Publicar uma única vez e verificar o estado `immutable` e a integridade da publicação por `gh release verify v0.9.0` ou equivalente.
- [ ] Confirmar tag, release, link, timestamp e identidade dos assets; somente então atualizar documentação pública que afirma `v0.9.0` como publicada.

**Distribuição em PyPI, Docker registry ou qualquer canal externo não está incluída** sem escopo e consentimento específicos.

## 6. Restrições de segurança e rollback

Não alterar `audit.db` ou `CONS-*` históricos, contratos de score, versões SARI/GEO históricas, preços de providers, variáveis sensíveis ou perfis de rede. Não reexecutar testes físicos já aprovados sem mudança invalidante. Rollback do runtime pode retornar ao código da tag anterior, mas não autoriza downgrade destrutivo de evidência produzida por versão posterior.

**Decisão atual: NO-GO PARA PUBLICAÇÃO.** Esta branch produz apenas artefatos de preparação submetidos à revisão e à CI.
