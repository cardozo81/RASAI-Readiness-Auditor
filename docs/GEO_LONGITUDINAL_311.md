# #311 - GEO longitudinal: inventário observacional conservador

Esta entrega é uma fase independente, read-only e opt-in de comparação
de snapshots GEO v5 já persistidos em AUDs distintas. Ela não altera
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
