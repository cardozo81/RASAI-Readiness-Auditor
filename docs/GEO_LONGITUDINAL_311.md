# #311 - GEO longitudinal: inventário observacional conservador

Esta entrega é uma fase independente, read-only e opt-in de comparação
de snapshots GEO v5/v6/v7/v8 já persistidos em AUDs distintas. Ela não altera
`CONS-*`, não materializa nova auditoria, não chama SERP/Perplexity/IA,
não executa RPR, não modifica pontuação nem cria relatório
consolidado novo. Não pressupõe que presença em Search API
corresponda a citação em respostas generativas.

## Execução

Em um ambiente RASAi instalado:

```powershell
.\.venv\Scripts\python.exe -m rasai.geo_longitudinal_311 `C:\audits\AUD-EXEMPLO-1` `C:\audits\AUD-EXEMPLO-2`
```

Saída JSON em stdout, sem gravação no disco. O usuário fornece
explicitamente 2 a 100 pastas de AUD; nenhuma varredura automática.

## Contrato

- A AUD precisa ser `COMPLETED` e `completion_status=COMPLETE` no
  SQLite da própria pasta. Escolhe-se o snapshot mais recente por
  `created_at, analysis_id` em `geo_observation_runs`.
  Outras versões são excluídas, nunca reinterpretadas como v5.
- Cada snapshot exige mesma AUD, estado externo `SUCCESS`, query
  única, URL-alvo válida, run_id vinculado, janela entre fontes <=24h
  com timestamps offset-aware, SERP com engine/país/região/idioma/
  dispositivo explícitos e denominadores de URLs positivos. O vínculo
  é conferido novamente, somente em modo SQLite `ro`, contra os registros
  `perplexity_search_runs` e `serp_observations` da mesma AUD:
  consulta única, IDs, status, origem `OBSERVED_API`, instante,
  mercado, idioma, dispositivo e demais informações de escopo devem
  coincidir com o snapshot; discrepâncias geram abstenção. Isso
  comprova a consistência lógica local, **não** a autenticidade de
  respostas do provedor externo nem equivalência entre motores.
- Agrupamento somente entre URL-alvo exata, query, SERP engine/país/
  região/idioma/dispositivo e modo externo iguais. Grupos que
  divergirem permanecem separados.
- Uma sequência com >=2 observações apresenta somente status/contagens
  e timestamps persistidos, ordenados fisicamente. `trend_rate=N/D`
  e `trend_conclusion=N/D` em todos os grupos: amostras, intent e
  filtros reais da plataforma Perplexity não são comprovadamente
  equivalentes entre datas.
- AUDs ausentes, legadas, parciais, sem proveniência e denominadores
  inválidos entram em `excluded[]` com código determinístico. Nunca
  completar lacunas com defaults atuais.

## Limites

**Não há ainda integração de visualização no CONS-*, nem evidência
de variação de ranking ou GEO generativo.** O preview entrega
inventário por URL/consulta/escopo e razões de exclusão.
Integração CONS e métricas de tendência requerem contrato específico
de compatibilidade de versões, amostragem, provenance, deltas e
aceite metodológico.

Workflow focal `GEO Longitudinal 311 Read-Only`, sem credenciais
comerciais nem alterações dos motores homologados.


## Public CLI (#311)

O router canônico aceita o comando `rasai geo-longitudinal` (alias
`rasai geo-history`), encaminhando diretamente para a rotina read-only
**antes** da instalação de hooks de auditoria, IA ou segredos da sessão.
Exemplo no PowerShell:

```powershell
.\.venv\Scripts\python.exe -m rasai geo-longitudinal "C:\audits\AUD-1" "C:\audits\AUD-2"
```

O comando especializado `python -m rasai.geo_longitudinal_311` continua
suportado e produz o mesmo JSON. Workflow de regressão testa ambos
em Windows e Linux; não testa provedores comerciais nem instrumentação
real de navegadores.


## Diagnóstico de elegibilidade em dados históricos - #311

Para cada pasta AUD com SQLite presente, o comando aplica **abstenção**
sem reprocessar ou sobrescrever evidências. A taxonomia de exclusão
separa agora: tabela de metadados ausente, schema histórico sem colunas
obrigatórias, ausência/duplicação de linha audit, ID do banco divergente
do nome da pasta, ciclo físico não concluído, conclusão lógica parcial,
tabela GEO ausente, tabela GEO legada/incompatível e snapshot GEO ausente.
Erros SQLite residuais permanecem identificados como falhas técnicas
de leitura, **sem implicar corrupção automaticamente**.

Essa classificação não altera os critérios estritos de elegibilidade:
um banco histórico não passa a conter dados GEO v5 porque sua causa
de exclusão ficou mais específica. O motivo reflete apenas a
**primeira condição impeditiva**, não um diagnóstico completo de
todas as tabelas da AUD. A saída mantém o contrato JSON advisory v1
e o contador de zero escritas/zero chamadas externas.


## Admissão de snapshots GEO v6 - #304/#311

Novas AUDs podem materializar `RASAI-GEO-OBSERVATION-6`. A nova
metodologia escolhe o SERP observado e textualmente atribuível cuja
data/hora validada está mais próxima da requisição Search API
(na janela <=24h), em vez de preferir sempre a linha SERP mais
recente, que pode estar fora da janela. Se não houver amostra
elegível, taxas SERP x Perplexity continuam `N/D`.

O comando longitudinal aceita snapshots **v5, v6, v7 e v8** mas usa
`method_version` como chave de agrupamento. Duas observações
da mesma URL, mesmo mercado e query com versões diferentes
continuam separadas e `trend_conclusion=N/D`. Nenhuma equivalência
de mercado/idioma/dispositivo entre motores foi presumida.


## Prova de cronologia do snapshot GEO v7 (#311)

Ao encontrar mais de um `geo_observation_runs` na mesma AUD, o inventário
não pressupõe que um `analysis_id` opaco seja ordenável, nem que strings
ISO de diferentes fusos estejam em ordem cronológica. O candidato mais
recente é escolhido por `created_at` convertido a UTC somente quando
todos os instantes envolvidos possuem fuso válido, há no máximo
256 snapshots e o instante mais recente é único. Se houver empate,
timestamp ingênuo, nulo, inválido ou excesso de histórico, a AUD
fica em `excluded[]` com
`GEO_SNAPSHOT_CHRONOLOGY_UNVERIFIABLE`, sem promover resultado antigo.

Um único snapshot mantém compatibilidade legada. A visão aceita v7,
mas preserva método/versionamento como chave de agrupamento,
separando v5, v6 e v7 de qualquer inferência de tendência.
Nenhuma alteração é feita no motor CONS de mesma URL,
em AUDs seladas ou em serviços comerciais.


## v8 - fronteira metodologica de URL exata

Os novos snapshots `RASAI-GEO-OBSERVATION-8` exigem identidade exata
mais estrita, preservando a barra final do path e recusando userinfo ou
URLs de sintaxe ambigua. A comparacao longitudinal preserva a regra
de normalizacao por versao ao ler v5/v6/v7; nunca reinterpreta os
snapshots ja congelados com a politica de v8. Uma serie com versoes
diferentes permanece em grupos distintos e sem tendencia numerica
compartilhada. Nenhuma AUD ou registro GEO anterior e regravado.

### Elegibilidade pela ultima tentativa externa (#309/#311)

A sequencia longitudinal de snapshots `GEO v5-v8` nao pode promover uma
observacao Search API antiga quando a mesma AUD possui tentativa posterior.
O consumidor read-only seleciona a ultima Search API da AUD por relogios
offset-aware convertidos a UTC. Se a mais recente falhou, se nao tem
snapshot dela, ou se multiplos relogios sao nao comparaveis/empatados,
a AUD e excluida com motivo estruturado
(`GEO_LATEST_SEARCH_NOT_SUCCESSFUL`,
`GEO_SNAPSHOT_NOT_FROM_LATEST_SEARCH`,
`GEO_SEARCH_CHRONOLOGY_UNVERIFIABLE`).

O inventario nao recupera automaticamente sucesso antigo nem executa
Search API. Comprovacao de fonte adulterada continua retornando
`GEO_SOURCE_PROVENANCE_UNVERIFIED` antes de escolher coorte.
Persistencia da AUD e timestamps originais nao sao alterados. Nenhuma
metrica gerativa, ranking ou tendencia e inferida.

Suplementos externos pos-AUD seguem independentes do snapshot original,
nao entram silenciosamente na serie CONS-*: esta lacuna exige adaptador
dedicado com proveniencia completa antes de ativacao.

## HTML standalone read-only: quadro de observações para discussão de CONS (#311)

O comando existente agora aceita uma representação HTML **opcional**
sem executar auditorias nem gravar em qualquer pasta AUD ou CONS:

```powershell
.\.venv\Scripts\python.exe -m rasai geo-longitudinal --format html `
    "C:\audits\AUD-EXEMPLO-A" "C:\audits\AUD-EXEMPLO-B" `
    | Out-File -Encoding utf8 ".\geo-longitudinal-preview.html"
```

O padrão continua `--format json`, preservando consumidores automáticos.
A renderização HTML é autocontida, sanitiza texto/URL de origem, mostra
coortes equivalentes por URL exata, query, versão de método e escopo SERP,
contagens por amostra, auditorias excluídas com motivo e
**tendência N/D**. Não cria links externos navegáveis nem converte
interseções URL em taxa de visibilidade GEO.

O HTML ainda é um arquivo **independente**, não uma nova página
reconciliada em `CONS-*`. O fluxo de consolidação canônico,
manifests, hashes e cálculo de indicadores permanecem intocados.
Uma inclusão no CONS com série de tendência calibrada só poderá
ocorrer em uma entrega posterior com metodologia e aceite próprios,
porque a Search API não verifica equivalência estatística de mercado,
idioma, intenção e amostragem entre datas.


## Fonte física estável entre leitores independentes (#311)

O comparador observacional agora sela cada `audit.db` com
**SHA-256 físico e tamanho antes e depois** de consultar os
snapshots GEO e os registros SERP/Search externos da mesma AUD.
As conexões do inventário e da reconciliação de origem utilizam
`mode=ro&immutable=1`, com proibição de WAL/SHM/journal
antes e depois da leitura. Cada hash é limitado a 256 MiB.

Se o arquivo físico for modificado durante qualquer das leituras,
inclusive **sem criar sidecar**, a AUD é excluída com
`AUD_SOURCE_CHANGED_DURING_READ`. Banco além do orçamento ou
origem não verificável produz
`AUD_SOURCE_BYTES_UNVERIFIABLE`. As demais AUDs independentes
permanecem elegíveis, mas jamais recebem evidência da fonte excluída.
Isso reforça a estabilidade dos bytes locais, sem provar autenticidade
de fornecedor, selagem do pacote AUD completo ou equivalência das
populações GEO entre datas. Nenhuma tendência, score ou CONS-3
produtivo é criado ou modificado.


## Integridade total dos denominadores de origem GEO v8 (12/10/2026)

O consumidor longitudinal read-only exige que **todas** as URLs físicas
atribuídas aos conjuntos Search API e SERP do snapshot GEO v8 tenham
identidade HTTP(S) válida. Não basta recalcular taxas e contagens ignorando
uma URL com userinfo, protocolo inválido ou espaços: isso reduziria
silenciosamente a amostra e permitiria aceitar uma projeção adulterada
internamente consistente. Se qualquer membro físico for inválido, a AUD
é excluída com `GEO_SOURCE_PROVENANCE_UNVERIFIED`, preservando as outras
AUDs e mantendo `trend_rate=N/D`. O controle não reinterpreta snapshots
históricos v5-v7, não altera a normalização do produtor GEO, não escreve
AUD/CONS nem realiza chamadas externas. Quatro fixtures físicas SQLite
verificam fontes inválidas SERP/Search com métricas coerentemente
recalculadas, abstenção e integridade byte a byte das AUDs.


## Ambiguidade de chaves JSON no snapshot GEO v8 (12/10/2026)

A prévia longitudinal read-only recusa snapshots `geo_observation_runs.projection_json`
do contrato v8 contendo **qualquer chave JSON duplicada**, inclusive em
objetos internos de alvo ou denominadores SERP × Search API. Um parser que
escolhe a última chave pode ocultar uma declaração contraditória mesmo
quando os campos aceitos parecem coincidir com as tabelas físicas.
A AUD afetada é excluída com `GEO_PROJECTION_INVALID`; demais AUDs
mantêm a elegibilidade verificada, sem tendências numéricas inventadas.
A validação de snapshots v5–v7 mantém a semântica anterior e não é
reinterpretada retroativamente. Três fixtures SQLite demonstram recusa
de duplicações raiz e aninhadas, preservação byte a byte de fontes e
zero requisições/escritas.
