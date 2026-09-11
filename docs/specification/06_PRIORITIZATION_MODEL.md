# PRIORITIZATION_MODEL.md

**Estado no baseline de desenvolvimento:** aprovado / vigente  
**Contrato:** `PRIORITY-GEO-001`

## 1. Conceitos

Os identificadores técnicos permanecem em inglês no contrato persistido:

- Severity = gravidade intrínseca;
- Impact = alcance/consequência;
- Confidence = confiabilidade do finding;
- Effort = esforço estimado de correção;
- Priority = ordem recomendada.

## 2. Severity

Valores vigentes:

| Valor | Peso | Valores permitidos | Recomendado |
|---|---:|---|---|
| `CRITICAL` | 100 | fixo no contrato | usar somente quando a semântica da regra justificar gravidade crítica |
| `HIGH` | 80 | fixo no contrato | preservar o valor definido pela regra |
| `MEDIUM` | 55 | fixo no contrato | preservar o valor definido pela regra |
| `LOW` | 30 | fixo no contrato | preservar o valor definido pela regra |
| `INFO` | 0 | fixo no contrato | usar para informação não acionável como defeito |

LLM não altera Severity arbitrariamente.

## 3. Impact

| Valor | Peso | Valores permitidos | Recomendado |
|---|---:|---|---|
| `VERY_HIGH` | 100 | fixo no contrato | usar conforme alcance material observado |
| `HIGH` | 75 | fixo no contrato | usar conforme alcance material observado |
| `MEDIUM` | 50 | fixo no contrato | usar conforme alcance material observado |
| `LOW` | 25 | fixo no contrato | usar conforme alcance material observado |
| `MINIMAL` | 10 | fixo no contrato | usar para impacto mínimo sustentado |

Impact pode considerar prevalência, dispositivos e efeito sobre capacidades críticas.

## 4. Confidence

| Valor | Peso | Valores permitidos | Recomendado |
|---|---:|---|---|
| `HIGH` | 100 | fixo no contrato | preservar a confiança derivada da evidência |
| `MEDIUM` | 70 | fixo no contrato | preservar a confiança derivada da evidência |
| `LOW` | 40 | fixo no contrato | não interpretar isoladamente como falha do website |
| `UNAVAILABLE` | 0 | fixo no contrato | preservar ausência; não fabricar confiança |

## 5. Effort

Valores permitidos:

```text
VERY_LOW
LOW
MEDIUM
HIGH
VERY_HIGH
UNKNOWN
```

Conversão vigente para Ease:

| Effort | Ease | Recomendado |
|---|---:|---|
| `VERY_LOW` | 100 | usar apenas quando o esforço for defensavelmente muito baixo |
| `LOW` | 80 | usar conforme estimativa disponível |
| `MEDIUM` | 60 | usar conforme estimativa disponível |
| `HIGH` | 35 | usar conforme estimativa disponível |
| `VERY_HIGH` | 15 | usar conforme estimativa disponível |
| `UNKNOWN` | 50 | default defensivo quando o esforço não puder ser determinado |

Effort é estimativa, não fato. IA pode ajudar a estimar, mas a estimativa deve continuar identificada como tal.

## 6. Fórmula

Priority Score vigente:

```text
Severity × 45%
+ Impact × 30%
+ Confidence × 15%
+ Ease × 10%
```

Resultado: `0..100`.

Os pesos da fórmula são fixos em `PRIORITY-GEO-001`; não são parâmetros livres do usuário. Alteração desses pesos exige novo contrato/versionamento de priorização.

Effort nunca deve reduzir artificialmente a importância de um blocker crítico.

## 7. Classes

| Classe | Critério vigente | Valores permitidos | Recomendado |
|---|---|---|---|
| `P0` | blocker por regra especial | fixo no contrato | reservar a bloqueadores críticos materiais |
| `P1` | `75..100` | fixo no contrato | preservar cálculo |
| `P2` | `60..74,9` | fixo no contrato | preservar cálculo |
| `P3` | `40..59,9` | fixo no contrato | preservar cálculo |
| `P4` | `<40` | fixo no contrato | preservar cálculo |
| `INFO` | informacional | fixo no contrato | não tratar como fila de correção obrigatória |

## 8. P0

Pode ser usado para `CRITICAL` com impacto material sobre:

- discovery;
- access;
- indexability;
- rendering;

em escopo relevante.

`P0` não depende somente da fórmula.

## 9. Remediation Groups

Findings individuais permanecem rastreáveis.

Findings da mesma causa podem gerar um `RemediationGroup` e uma recomendação consolidada.

## 10. Root Cause

Sempre que possível:

```text
Findings
→ Root Cause
→ Recommendation
```

Os nomes acima permanecem em inglês por corresponderem à terminologia técnica do domínio.

## 11. Priority ≠ Score

Score mede condição agregada.

Priority define ordem de ação.

Um `P0` pode existir mesmo com score agregado razoável.
