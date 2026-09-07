# PRIORITIZATION_MODEL.md

**Status:** APPROVED
**Baseline:** PRIORITY-GEO-001

## 1. Conceitos

Severity = gravidade intrínseca
Impact = alcance/consequência
Confidence = confiabilidade do finding
Effort = esforço estimado de correção
Priority = ordem recomendada

## 2. Severity

- CRITICAL = 100
- HIGH = 80
- MEDIUM = 55
- LOW = 30
- INFO = 0

LLM não altera severity arbitrariamente.

## 3. Impact

- VERY_HIGH = 100
- HIGH = 75
- MEDIUM = 50
- LOW = 25
- MINIMAL = 10

Impact pode considerar prevalência, dispositivos e efeito sobre capacidades críticas.

## 4. Confidence

- HIGH = 100
- MEDIUM = 70
- LOW = 40
- UNAVAILABLE = 0

## 5. Effort

- VERY_LOW
- LOW
- MEDIUM
- HIGH
- VERY_HIGH
- UNKNOWN

Converter para Ease:

- VERY_LOW = 100
- LOW = 80
- MEDIUM = 60
- HIGH = 35
- VERY_HIGH = 15
- UNKNOWN = 50

## 6. Fórmula

Priority Score:

Severity × 45%
+
Impact × 30%
+
Confidence × 15%
+
Ease × 10%

Resultado 0–100.

Effort nunca deve reduzir artificialmente a importância de blocker crítico.

## 7. Classes

P0 = blocker por regra especial
P1 = 75–100
P2 = 60–74.9
P3 = 40–59.9
P4 = <40
INFO = informacional

## 8. P0

Pode ser usado para CRITICAL com impacto material sobre:

- discovery;
- access;
- indexability;
- rendering;

em escopo relevante.

P0 não depende somente da fórmula.

## 9. Remediation Groups

Findings individuais permanecem rastreáveis.

Findings da mesma causa podem gerar um RemediationGroup e uma recomendação consolidada.

## 10. Root Cause

Sempre que possível:

Findings
→ Root Cause
→ Recommendation

## 11. Effort

É estimativa, não fato.

Se desconhecido:

Effort = UNKNOWN

IA pode ajudar a estimar, mas a estimativa deve permanecer identificada como tal.

## 12. Priority ≠ Score

Score mede condição agregada.

Priority define ordem de ação.

Um P0 pode existir mesmo com score agregado razoável.
