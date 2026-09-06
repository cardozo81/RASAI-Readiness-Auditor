# Validação e reversibilidade — relatórios consolidados

## Escopo da mudança

Branch:

```text
feature/consolidated-reporting
```

PR:

```text
#67
```

A mudança permanece aditiva e isolada. O único arquivo de runtime preexistente alterado é `src/searchgeo/console_entrypoint.py`, usado apenas para instalar o adapter da opção `C` antes de delegar ao mesmo console existente.

Não há alteração em:

- `audit_runner.py`;
- `persistence.py`;
- `scoring.py` / `scoring_persistence.py`;
- acquisition/rendering;
- providers de IA;
- PageSpeed/CrUX;
- Synthetic Apdex;
- schemas dos `AUD-*/audit.db`.

## Fonte de verdade e escrita

Fonte de verdade:

```text
AUD-*/audit.db
```

Leitura:

```text
SQLite mode=ro
PRAGMA query_only=ON
```

A feature só escreve em:

```text
.searchgeo/consolidated-index.db
consolidated/CONS-*/report.html
consolidated/CONS-*/manifest.json
```

O índice é derivado e reconstruível.

## Formato atual do relatório

```text
CONS-2
```

O bump de `CONS-1` para `CONS-2` foi intencional para invalidar o dedupe de snapshots antigos após a evolução de layout/metodologia.

`CONS-2` inclui:

- leitura executiva;
- navegação fixa;
- modo adaptativo Snapshot / comparação de dois pontos / série histórica;
- gráfico de Compatibilidade GEO + Cobertura quando há 2+ pontos comparáveis;
- matriz histórica das dimensões quando há base comparável;
- estatísticas avançadas expansíveis;
- destaque de amostra pequena de Apdex;
- evolução do volume de ocorrências;
- matriz de confiabilidade analítica sem inventar novo score;
- pesquisa/paginação das auditorias consideradas;
- metodologia, fórmulas, política de extremos e referências técnicas no próprio HTML.

## Comparabilidade estatística

### Compatibilidade GEO

Uma série numérica só é agregada dentro da combinação mais recente de:

```text
scoring_version
+
fingerprint do conjunto completo de URLs da auditoria
```

O HTML traduz `scoring_version` para **Versão do método de pontuação**.

Filtro parcial de URL nunca recebe uma pontuação calculada sobre páginas fora do filtro. O consolidado não reexecuta scoring.

### Média, mediana e extremos

- média = média aritmética das observações elegíveis;
- mediana = valor central das observações elegíveis;
- mínimo/máximo são preservados;
- nenhum extremo é eliminado automaticamente apenas por seu valor;
- não há trimming, winsorization ou descarte por IQR/desvio-padrão;
- dado ausente não vira zero.

### Desempenho Web

Para `Inicial`/`Atual` em métricas por URL, usa-se a média transversal da observação válida mais antiga/recente de cada URL. Isso evita que a URL com maior frequência de auditoria represente sozinha o domínio.

### Apdex

Somente mesmo perfil + T são compatíveis. O consolidado pondera o Apdex por amostras válidas e destaca `small_group` sem `final_group` como base insuficiente para conclusão robusta.

### Ocorrências

Ocorrências são estatística histórica; não recalculam SCORE-GEO. O gráfico de volume bruto contém aviso para interpretação junto com o tamanho do universo auditado.

## Transparência do SCORE-GEO

O HTML só apresenta versões efetivamente persistidas nas fontes selecionadas. `SCORE-GEO-001` não é exibido como alternativa quando não existe nos AUDs.

Quando `SCORE-GEO-002` está presente, o relatório explica:

- PASS = fator 1;
- WARNING = fator padrão 0,5;
- FAIL = fator 0;
- agrupamento de regras correlacionadas;
- fórmula da dimensão;
- fórmula da Coverage;
- exclusão de `NOT_APPLICABLE` legítimo;
- média aritmética das dimensões aplicáveis no Overall;
- thresholds de Confidence;
- natureza interna/reproduzível do método;
- ausência de validação externa estabelecida como preditor de ranking/citação.

## Dedupe

Exige igualdade de:

```text
report_format_version
+ filtros canônicos
+ conjunto/fingerprint dos AUDs elegíveis
```

Portanto:

- mesma requisição + mesmas fontes: reutiliza;
- novo AUD elegível: novo snapshot;
- mudança de filtro: novo snapshot;
- mudança de formato: novo snapshot.

## Testes automatizados

Workflow:

```text
.github/workflows/consolidated-reporting-ci.yml
```

Executa em CPython 3.13:

1. instalação do pacote;
2. `compileall` do pacote da feature/entrypoint/testes;
3. `test_consolidation*.py`;
4. regressões existentes de console/configuração.

### Cobertura específica

- geração read-only e hash dos `audit.db` inalterado;
- dedupe da mesma requisição;
- invalidação por novo AUD;
- filtro parcial de URL sem contaminação do Score;
- segregação de versão do método;
- segregação de universo de URLs;
- estado atual de Web Performance por URL;
- isolamento de banco inválido;
- período inclusivo;
- integração `C` sem interceptar escolhas antigas;
- falha do consolidado `fail-open`;
- Snapshot com `N=1` sem falsa tendência;
- `SCORE-GEO-001` ausente da UI quando não existe nas fontes;
- metodologia/política de outliers materializada no HTML/manifest;
- gráfico histórico com três pontos comparáveis;
- matriz histórica das dimensões;
- dedupe preservado no formato `CONS-2`.

### Último gate de código antes desta atualização documental

```text
14 testes da consolidação: OK
44 testes existentes do console/configuração: OK
58 testes executados: 58 OK
compileall: OK
merge-ref PR #67 x main: OK
```

A documentação final também deve passar pelo mesmo workflow antes do smoke humano.

## Smoke humano obrigatório antes de qualquer merge

Executar na branch `feature/consolidated-reporting` com AUDs reais:

1. abrir `iniciar.cmd`;
2. confirmar que menu legado permanece normal;
3. entrar em `C`;
4. gerar um consolidado com 1 AUD e confirmar modo **Snapshot**;
5. gerar com 2 AUDs comparáveis e confirmar aviso de variação, não tendência;
6. gerar com 3+ AUDs comparáveis e validar gráfico/matriz;
7. verificar Compatibilidade GEO, Coverage e Confidence contra pelo menos um `audit.db` fonte;
8. conferir Apdex small-group quando aplicável;
9. testar pesquisa/paginação de **Auditorias consideradas**;
10. conferir seção de metodologia/cálculos;
11. repetir mesmos filtros e confirmar dedupe;
12. comparar hash de `audit.db` antes/depois;
13. abrir HTML com console fechado e confirmar funcionamento estático.

## Gate de merge

O PR deve permanecer sem merge se qualquer condição não estiver comprovada:

- CI verde no HEAD final;
- smoke humano concluído;
- branch revisada contra `main` corrente;
- diff sem alteração dos motores de auditoria/scoring/persistência;
- nenhum `AUD-*/audit.db` escrito;
- nenhuma chamada de rede no pacote `consolidation`;
- integração do console preservando escolhas anteriores;
- diff final sem arquivo inesperado.

Testes verdes reduzem risco; não autorizam afirmar risco matematicamente zero.

## Rollback

Se futuramente integrado, usar preferencialmente **Squash and merge** para manter a feature como um único commit funcional em `main`.

Rollback:

1. reverter o commit squash do PR #67;
2. opcionalmente apagar `.searchgeo/consolidated-index.db`;
3. opcionalmente arquivar/remover `consolidated/CONS-*`;
4. não restaurar/migrar `AUD-*`, pois a feature nunca grava neles.
