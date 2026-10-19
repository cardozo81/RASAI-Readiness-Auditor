# Política de nomes estáveis para arquivos versionados

## Contrato

O nome físico de um arquivo versionado deve indicar sua responsabilidade funcional,
não o evento que motivou sua criação. Não adicionar ao nome de arquivo números
de issues, números de PRs, datas de implementação, IDs internos de controle nem
sufixos artificiais de rastreamento. Exemplos corretos:
`faq_observation.py`, `report_catalog_visual_smoke.py` e
`REPORT_DESIGN_SYSTEM.md`. O vínculo com demandas deve ficar no texto
de issues, mensagens de commit, PRs e documentação, nunca no basename.

Nomes técnicos que fazem parte de contratos públicos e realmente estáveis
não devem ser renomeados de forma automática. Uma exceção futura exige
identificar o contrato externo, seu consumidor, sua estabilidade, o risco de
quebra e o motivo para manter o identificador no nome físico. A exceção deve
ser revisada explicitamente e adicionada ao inventário e ao gate no mesmo PR.
A simples existência anterior de um nome inadequado não constitui exceção.

## Gate incremental

`tests/test_repository_filename_policy.py` inspeciona somente paths adicionados
ou destinos de rename/copy em um diff Git entre commits verificados. Procura
marcadores de issue/PR/tarefa, sequências numéricas isoladas com pelo menos
três dígitos e datas YYYYMMDD. Os casos existentes não alterados não são
motivo de falha; isso permite migrar a dívida por lotes.

A comparação usa `git diff --name-status -z --find-renames`, evitando
ambiguidade de espaços e quebras de linha. Falhas de leitura do diff reprovam
o gate. O checker não edita nem consulta o runtime da auditoria.

Na PR, a base é `github.event.pull_request.base.sha`. Em push, a comparação
é com `github.event.before`. Na execução manual, utiliza-se o pai do HEAD
apenas para uma checagem pontual, não para declarar conformidade de toda a
história. O checkout do workflow precisa disponibilizar as revisões envolvidas.

Comando local de validação direcionada:

```bash
python tests/test_repository_filename_policy.py --base <sha-base> --head HEAD
python -m pytest -q tests/test_repository_filename_policy.py
```

**Limites explícitos:** a detecção automática não comprova que todo sufixo
alfanumérico seja semântico. Revisão humana ainda é necessária para nomes
opacos, IDs não numéricos, referências externas e contratos versionados. Não
se pode concluir que a dívida total foi eliminada apenas porque o gate
incremental está verde.

## Migração por lotes

O baseline da integração de 15/10/2026 contém 243 paths com padrão numérico
histórico, segundo o inventário realizado no checkpoint. A contagem é
referencial, não certifica todas as classes de identificadores. A sequência
aprovada para evolução é:

1. Documentação: inventário de links de entrada/saída e renomeações pequenas,
   corrigindo links e referências textuais.
2. Workflows: verificar triggers por path, nomes de jobs, badges, referências
   cruzadas e invocações em documentos.
3. Scripts e testes: revisar chamadas de CLI, `pytest`, imports, fixtures,
   arquivos de configuração e coletores de evidência.
4. Python executável: mapear imports estáticos/dinâmicos, módulos `python -m`,
   entrypoints, consumidores Windows e contratos de API antes de mover.
5. Outros recursos: verificar caminhos persistidos, URLs e referências públicas
   antes de cada mudança.

Em cada lote, registrar tabela origem/destino, consumidores encontrados,
testes de regressão pertinentes, resultado do CI, confirmação de links e
eventuais impedimentos. Não aplicar renomeação cega por regex. Arquivos
que compõem o contrato de output de AUDs antigas requerem avaliação
individual. O relatório HTML aprovado de 19 páginas não está no escopo
de refatoração de nomes.

## Estado do primeiro lote

A primeira mudança apenas estabelece a regra incremental, seus testes
sintéticos e a verificação no CI. **Nenhum dos 243 paths históricos foi
renomeado neste lote.** A conclusão integral exige inventário por
dependência e redução das violações remanescentes a zero ou justificativa
formal de exceção. O gate parcial não autoriza fechar a issue de migração.

## Atualização da migração em PR aberta - 16/10/2026

O parágrafo do primeiro lote acima descreve apenas o checkpoint inicial, **não** o estado corrente da PR. A comparação `main...chore/acceptance-evidence-reconciliation` retornou uma branch com 200 commits à frente e listagem limitada a 300 arquivos, dos quais **210** estão classificados como renomeados. Esse recorte mostra migração real de workflows e módulos e não deve ser tratado como inventário completo; a API limita a resposta e o número de paths remanescentes **não está comprovado como zero**. O aceite definitivo requer `git ls-tree -r --name-only -z HEAD`, o gate `--full-tree`, busca de referências e CI Linux/Windows, todos sobre o HEAD efetivamente integrado. Os 243 paths citados no baseline não devem ser subtraídos aritmeticamente dos 210 renames parciais.

## Fronteira de compatibilidade após a migração

Os contratos de distribuição que o projeto publica explicitamente em
`pyproject.toml` são o pacote `rasai-readiness-auditor`, o namespace Python
`rasai` e os comandos `rasai` e `rasai-console`. Os entrypoints chamam,
respectivamente, `rasai.entrypoint:main` e
`rasai.console_entrypoint:main`. O teste
`tests/test_rasai_namespace_contract.py` protege esses nomes.

A importabilidade de um módulo sob `src/rasai/` **não estabelece**, por si
só, uma API pública estável. Renomeações de módulos internos exigem revisão
das referências no repositório e execução dos testes de seus consumidores.
Compatibilidade de consumidores externos conhecidos deve ser inventariada
separadamente: nome do consumidor, versão, import/CLI efetivamente utilizado,
contrato publicado e teste de migração ou decisão de descontinuação. Não
introduzir aliases para imports históricos hipotéticos sem consumidor
identificado e contrato verificável.

Os verificadores de filenames, namespaces e workflows e a CI verde atestam
apenas a superfície coberta pelos testes. Não certificam scripts não
versionados do operador, imports dinâmicos de terceiros ou clientes externos.
O inventário por padrão de nomes não comprova ausência de nomes opacos que
não correspondam à regex. Uma issue de migração só poderá ser fechada após
reconciliar expressamente essas fronteiras e os critérios de aceite integrais.

## Estado verificável da árvore completa

A verificação independente pela GitHub Git Trees API no HEAD
`98c73e95f46fe68670ace6016979532e9a91404e` enumerou **1.509
arquivos versionados**, sem truncamento, e encontrou **zero** ocorrências
do padrão numérico anterior. A allowlist de exceções continua vazia.

A partir desta reconciliação, a suíte
`tests/test_repository_filename_policy.py` também varre
**toda a árvore Git do HEAD** em execução normal do pytest, além do
gate incremental já existente. Assim, uma futura introdução de um
basename de issue/PR/data reprova a execução mesmo quando não houver
uma comparação incremental disponível.

**Limite da comprovação:** a regex protege tokens de tracking
numéricos, prefixos issue/PR e datas. Não demonstra ausência de todos
os nomes opacos alfanuméricos; consumidor externo não versionado e
compatibilidade com scripts particulares exigem inventário separado.
O requisito de conferir `main` após merge não pode ser satisfeito
antes do próprio merge. Portanto, a issue de migração só deve ser
encerrada quando a verificação pós-integração e a avaliação de
compatibilidade externa estiverem concluídas.

## Reconciliação de compatibilidade na branch de aceitação

O gate estático de referências literais em GitHub Actions agora inclui
ambas as extensões `.yml` e `.yaml`, evitando uma lacuna no inventário
sem renomear arquivos ou importar módulos históricos artificialmente.
O teste de política preserva identificadores curtos de módulos canônicos
(`m23`, `m25`) e nomes funcionais, enquanto proíbe IDs de tracking
nos basenames versionados. Isto é apenas reconciliação de CI/paths:
não comprova compatibilidade de importadores externos ou scripts Windows
não versionados, que permanecem como gates explícitos de #639.

## Evidência de compatibilidade em runners Windows

Na reconciliação do HEAD `27b9729`, os workflows Windows Console Navigation
e Audit Fulfillment and Reprocessing reprovaram a mesma regressão de teste
na validação de caracteres de controle de consultas históricas. A correção
é tratada na issue de configuração, não como renomeação de arquivo: nenhum
nome de módulo, entrypoint ou arquivo histórico precisa ser modificado.
O aceite de #639 continua condicionado à inspeção das referências reais e
à conclusão dos gates do HEAD final, e não a uma interpretação de 29 workflows
verdes como aprovação integral.

## Teste comportamental dos caminhos de workflows

O inventário positivo de caminhos Python em Actions foi extraído para
`missing_workflow_python_paths(root)`, permitindo validar em diretório
isolado as duas extensões `.yml` e `.yaml`, arquivos realmente existentes
e guardas negativos intencionais. Isso substitui a verificação anterior
que apenas procurava literais no próprio código-fonte do teste.
A inspeção não executa workflows, não cobre comandos construídos
dinamicamente e não afirma compatibilidade de consumidores externos.
