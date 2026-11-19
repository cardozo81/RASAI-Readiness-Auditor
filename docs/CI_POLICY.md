# Política de CI por risco de alterações

## Finalidade e fonte normativa

Esta página descreve a seleção de regressões de **pull requests (PRs) direcionadas à `main`**. O objetivo é reduzir execução redundante para alterações exclusivamente documentais ou de apresentação **sem omitir checks de contrato nem enfraquecer o modo conservador**. Não é uma política de execução de auditorias nem autoriza gastos, chamadas externas ou alteração de dados.

A fonte executável prevalece sobre este texto: [`scripts/ci_pr_risk_scope.py`](../scripts/ci_pr_risk_scope.py), [`full-regression.yml`](../.github/workflows/full-regression.yml) e [`score-geo-validation.yml`](../.github/workflows/score-geo-validation.yml). Os casos isolados do classificador estão em [`tests/test_ci_pr_risk_scope.py`](../tests/test_ci_pr_risk_scope.py).

## Seleção de escopo

O classificador considera exclusivamente o diff entre o *merge-base* dos SHAs da base e do HEAD da PR. O checkout usa histórico completo. Não seleciona a modalidade por rótulo, nome da branch, descrição da PR ou declaração do autor.

| Modo | Condição comprovável | Execução no check `Full RASAi Regression / pytest` |
| --- | --- | --- |
| `docs` | Todos os arquivos alterados são `README.md` e/ou Markdown sob `docs/` | Instalação básica, `python -m rasai.public_contract_gate` e etapa declaratória documental; **sem `pytest -q` integral e sem instalação de Chromium** |
| `presentation` | Todos os arquivos alterados pertencem à allowlist derivada da apresentação, testes `tests/report_presentation/*.py` e/ou Markdown permitido; alterações de versão em `__init__.py`/`publication.py` são validadas linha a linha | Instalação básica, contrato público e quatro testes focais de apresentação definidos no workflow; **sem suíte integral e sem instalar Chromium** |
| `full` | Qualquer outro diff, combinação com código de núcleo, arquivo desconhecido ou condição não verificável | Dependências completas, contrato público, `pytest -q` integral e instalação de Chromium |

A allowlist de `presentation` é **fechada**. Alterações de `assets/app.js`, `assets/site.css`, gerador, SQLite, pricing, scoring, integrações, coletores, arquivo de workflow ou próprio classificador **não** qualificam para a modalidade leve. Em particular, a simples localização dentro de `parallel_report/` não basta.

### Comportamento conservador (*fail-closed*)

- Ausência de arquivos alterados, SHA inválido, evento que não seja `pull_request`, erro de `git`, falha de leitura do conteúdo ou impossibilidade de determinar o *merge-base* selecionam `full`.
- Mudança em `__init__.py` ou `publication.py` só é elegível quando o comparador confirma estritamente **uma linha permitida de versionamento**, sem alteração comportamental.
- A execução por `workflow_dispatch` seleciona `full`. Não se deve dispará-la manualmente apenas para repetir CI já aprovado.
- Os nomes originais dos workflows e jobs permanecem visíveis. A modalidade leve **omite etapas incompatíveis**, não elimina os checks.
- O workflow `SCORE-GEO-005 validation` conserva o job `score-geo-004`: na PR comprovadamente `docs` ou `presentation`, executa o controle de inaplicabilidade sem a suíte de scoring; nos demais cenários, preserva as verificações dirigidas de scoring.

## Aceitação de PR e integração

1. Comparar base, HEAD e todos os arquivos alterados; confirmar modalidade selecionada no log `CI_RISK_SCOPE=docs|presentation|full`.
2. Conferir a **conclusão `success`** de cada check aplicável **no SHA final**, inclusive contrato público, segurança e gates específicos disparados pelos filtros de caminho.
3. Validar os passos efetivamente executados: no modo leve, a ausência de `pytest -q` integral/Chromium é deliberada; falha ou ausência do job obrigatório impede o merge.
4. Confirmar que alterações fora da allowlist acionam `full`; se a classificação falhar ou o diff for ambíguo, **não fazer merge**.
5. Após integrar, consultar os workflows de `push` na `main` no SHA integrado. Um CI da PR não substitui a verificação de integração.

Os filtros dos demais workflows independentes continuam válidos. A modalidade de risco não dispensa homologação humana quando um requisito específico a exige, nem implica que branch protection esteja configurada. Não criar PR artificial apenas para provar um modo: usar uma alteração documental ou editorial que tenha finalidade própria e registrar os passos do workflow decorrente.
