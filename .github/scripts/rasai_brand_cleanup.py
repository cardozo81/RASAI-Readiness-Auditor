from pathlib import Path


def load(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def save(path: str, text: str) -> None:
    Path(path).write_text(text, encoding='utf-8', newline='\n')


def repl(path: str, old: str, new: str) -> None:
    text = load(path)
    if old in text:
        save(path, text.replace(old, new))


def replace_token(path: str, old: str, new: str) -> None:
    text = load(path)
    if old in text:
        save(path, text.replace(old, new))

# Current-only wording for domains that are explicitly independent from SARI/scoring.
replace_token('docs/ACCESSIBILITY_PERFORMANCE_DOMAINS.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/SYNTHETIC_APDEX.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/CONTENT_ANALYSIS_CONTEXT.md', 'SCORE-GEO-002', 'SARI-001')
repl('docs/SYNTHETIC_USER_EXPERIENCE_APDEX.md', '`SCORE-GEO-002`, `SARI-001`', '`SARI-001`')
replace_token('docs/SYNTHETIC_USER_EXPERIENCE_APDEX.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/SECURE_REDIRECT_RECOVERY.md', 'SCORE-GEO-002', 'SCORE-GEO-003')
replace_token('docs/SOURCE_QUALITY_AND_REDIRECTS.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/GEO_MINIMUM_REQUIREMENTS.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/EXTERNAL_METRICS_INTEGRITY.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/AI_GUIDE.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/specification/11_REPORTING_LANGUAGE_GLOSSARY.md', 'SCORE-GEO-002', 'SARI-001')
replace_token('docs/specification/15_ERROR_CENTRIC_REPORT_UX.md', 'SCORE-GEO-002', 'SARI-001')

# Scoring guide: describe only the active contract.
repl('docs/SCORING_GUIDE.md', '`SCORE-GEO-002` permanece histórico e não é recalculado.\n', '')
repl(
    'docs/SCORING_GUIDE.md',
    'Relatórios consolidados devem segmentar séries por `scoring_version`. `SCORE-GEO-002` e `SCORE-GEO-003` não devem ser tratados como a mesma série sem ressalva explícita.',
    'Relatórios consolidados preservam e segmentam resultados por `scoring_version`, `model_version` e `dataset_version`, sem conversão silenciosa entre contratos metodológicos.'
)

# Report/output guides: remove unreleased predecessor labels.
repl('docs/REPORT_GUIDE.md', 'SCORE-GEO-002  = histórico\n', '')
repl('docs/OUTPUTS_AND_ARTIFACTS.md', 'SCORE-GEO-002  = histórico\n', '')

# Provenance: current public index + active scoring engine only.
repl(
    'docs/INDICATOR_PROVENANCE.md',
    '`SARI-001` é a identidade pública da metodologia. Enquanto a fórmula não mudar, o banco continua registrando `SCORE-GEO-002` como versão do motor de cálculo persistido para preservar compatibilidade e comparabilidade histórica.',
    '`SARI-001` é a identidade pública da metodologia e `SCORE-GEO-003` é o método de scoring persistido. Provenance, model artifact, dataset e evidências permanecem rastreáveis.'
)
repl(
    'docs/INDICATOR_PROVENANCE.md',
    '> SARI-001: índice heurístico interno, evidence-based e reprodutível do RASAi; motor persistido SCORE-GEO-002.',
    '> SARI-001: índice proprietário, evidence-based e reprodutível do RASAi; método de scoring persistido SCORE-GEO-003.'
)

repl(
    'docs/CONFIGURATION.md',
    'Identificadores históricos podem permanecer em tabelas, eventos e documentação normativa por compatibilidade. A interface pública deve preferir nomes funcionais e tratar `SCORE-GEO-002` apenas como histórico.',
    'Identificadores técnicos persistidos podem permanecer em tabelas e eventos por compatibilidade operacional. A interface pública usa a nomenclatura funcional do RASAi e do SARI.'
)
repl(
    'docs/CLI_REFERENCE.md',
    'Novas auditorias usam `SCORE-GEO-003`; `SCORE-GEO-002` é histórico e não existe fallback silencioso para a aritmética anterior.',
    'As auditorias usam `SCORE-GEO-003`. Sem model artifact `VALIDATED`, o Overall permanece `NOT_CONSOLIDATED`; nenhum resultado substituto é produzido.'
)

repl('docs/RULES_GUIDE.md', '- histórico: `SCORE-GEO-002`.\n', '')
repl(
    'docs/RULES_GUIDE.md',
    '- auditoria histórica: pode conter `SCORE-GEO-002`.',
    '- cada auditoria expõe o `scoring_version` efetivamente persistido para rastreabilidade.'
)
repl(
    'docs/SCORING_VALIDATION.md',
    '`SCORE-GEO-002` não é removido dos AUDs históricos.',
    'A validação não recalcula nem reescreve automaticamente os AUDs usados como fonte.'
)

# SCORE-GEO-003 reference document without predecessor narrative.
repl(
    'docs/SCORE_GEO_003.md',
    'As dez dimensões continuam determinísticas, evidence-backed e calculadas com a mesma semântica consolidada no `SCORE-GEO-002`:',
    'As dez dimensões são determinísticas, evidence-backed e calculadas a partir das regras e evidências persistidas:'
)
repl(
    'docs/SCORE_GEO_003.md',
    'O programa não inventa coeficientes e não faz fallback silencioso para o Overall do `SCORE-GEO-002`.',
    'O programa não inventa coeficientes e não produz um Overall substituto quando o model artifact não satisfaz o contrato de validação.'
)
repl(
    'docs/SCORE_GEO_003.md',
    '`SCORE-GEO-002` permanece como versão histórica. Auditorias antigas não são recalculadas.',
    'Auditorias persistidas não são recalculadas automaticamente pela calibração ou pela geração de relatórios.'
)

repl(
    'docs/CONSOLIDATED_REPORTING_VALIDATION.md',
    'Quando `SCORE-GEO-002` está presente, o relatório explica:',
    'Quando diferentes `scoring_version` estão presentes, o relatório explica:'
)
repl(
    'docs/CONSOLIDATED_REPORTING.md',
    '`SCORE-GEO-002` permanece **histórico**. Ele pode aparecer em auditorias antigas e em séries históricas, mas não deve ser descrito como baseline vigente nem agregado à mesma série do `SCORE-GEO-003` sem quebra metodológica explícita.',
    'Séries com contratos de scoring distintos permanecem segmentadas por `scoring_version` e não são convertidas ou agregadas silenciosamente.'
)
repl(
    'docs/CONSOLIDATED_REPORTING.md',
    'Uma mudança de `SCORE-GEO-002` para `SCORE-GEO-003` é quebra metodológica. O HTML deve permitir leitura histórica, mas não sugerir uma evolução numérica contínua entre métodos diferentes.',
    'Uma mudança de `scoring_version`, `model_version` ou `dataset_version` define uma fronteira metodológica. O HTML deve explicitar essa fronteira e não sugerir continuidade numérica sem fundamento.'
)

repl(
    'docs/MONITORING_OBSERVABILITY.md',
    'Different scoring versions are not silently converted. `SCORE-GEO-002` remains historical and is not treated as methodologically equivalent to `SCORE-GEO-003`.',
    'Different scoring versions are not silently converted or treated as methodologically equivalent.'
)
repl(
    'docs/MONITORING_OBSERVABILITY.md',
    '11. verify `SCORE-GEO-003` current and `SCORE-GEO-002` historical only;',
    '11. verify `SCORE-GEO-003` as the scoring method declared by the current pipeline;'
)

repl(
    'docs/IMPLEMENTATION_ROADMAP_MONITORING.md',
    '- no SCORE-GEO-002↔003 silent conversion;',
    '- no silent conversion between scoring contracts;'
)
repl('docs/IMPLEMENTATION_ROADMAP_MONITORING.md', '- `SCORE-GEO-002` is historical;', '- `SCORE-GEO-003` is the scoring method used by the current pipeline;')

# Web Performance spec: normalize to the active scoring method and remove historical phrasing.
replace_token('docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md', 'SCORE-GEO-002', 'SCORE-GEO-003')
repl('docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md', 'todos os comandos históricos continuam válidos', 'os demais comandos continuam válidos')
repl('docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md', 'preservação do resultado histórico `SCORE-GEO-003`', 'preservação do resultado persistido `SCORE-GEO-003`')

repl(
    'docs/specification/18_MULTI_AI_PROVIDER_ROUTING.md',
    'O scoring vigente para novas auditorias é `SCORE-GEO-003`; `SCORE-GEO-002` permanece histórico.',
    'O método de scoring usado pela auditoria é `SCORE-GEO-003`.'
)
replace_token('docs/specification/20_AI_CONTENT_REMEDIATION.md', 'SCORE-GEO-002', 'SCORE-GEO-003')
replace_token('docs/specification/07_FUNCTIONAL_REQUIREMENTS.md', 'SCORE-GEO-002', 'SCORE-GEO-003')
replace_token('docs/specification/22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md', 'SCORE-GEO-002', 'SCORE-GEO-003')

repl(
    'docs/specification/05_SCORING_MODEL.md',
    'As regras de `scoring_group`, `MAX_IMPACT`, pré-requisitos, site-level rules e prevenção de cascading failure permanecem compatíveis com a semântica consolidada no `SCORE-GEO-002`.',
    'As regras de `scoring_group`, `MAX_IMPACT`, pré-requisitos, site-level rules e prevenção de cascading failure fazem parte do contrato determinístico das dimensões.'
)
repl(
    'docs/specification/05_SCORING_MODEL.md',
    'Não existe fallback silencioso para a média simples do `SCORE-GEO-002`.',
    'Não existe fallback silencioso para outro cálculo de Overall.'
)
repl(
    'docs/specification/05_SCORING_MODEL.md',
    '`SCORE-GEO-002` permanece histórico. Nenhum AUD antigo é recalculado automaticamente.',
    'Nenhum AUD persistido é recalculado automaticamente por mudança de model artifact ou geração de relatório.'
)

repl('docs/specification/12_AI_HANDOFF.md', '- `SCORE-GEO-002` permanece apenas histórico e não deve ser descrito como baseline vigente;\n', '')
repl(
    'docs/specification/12_AI_HANDOFF.md',
    'A transição de `SCORE-GEO-002` para `SCORE-GEO-003` é quebra metodológica real. Dimensões permanecem evidence-bound; o Overall vigente depende do contrato/model artifact calibrado e dos gates definidos em `SCORE_GEO_003.md`.',
    'As dimensões permanecem evidence-bound; o Overall depende do contrato/model artifact calibrado e dos gates definidos em `SCORE_GEO_003.md`.'
)

replace_token('docs/specification/23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md', 'SCORE-GEO-002', 'SARI-001')
repl('docs/specification/23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md', '`SARI-001`, `SARI-001`', '`SARI-001`')

# Decision log: retain current decisions, remove unreleased-version evolution narrative.
decisions = 'docs/specification/10_DECISIONS.md'
repl(decisions, '### D-037 — SCORE-GEO-002 e aplicabilidade de dimensões\n\n`SCORE-GEO-001` é superseded por `SCORE-GEO-002` quanto à aplicabilidade e agregação das dimensões.\n\nAs dez dimensões permanecem no modelo, preservando D-008. Entretanto, uma dimensão cujas RuleExecutions existam e estejam **todas legitimamente `NOT_APPLICABLE`** não pode ser tratada como `NOT_CONSOLIDATED` nem bloquear o Overall.', '### D-037 — Aplicabilidade de dimensões no SARI\n\nAs dez dimensões permanecem no modelo, preservando D-008. Uma dimensão cujas RuleExecutions existam e estejam **todas legitimamente `NOT_APPLICABLE`** não pode ser tratada como `NOT_CONSOLIDATED` nem bloquear o Overall.')
repl(decisions, '### D-038 — Web Performance externo Web Performance externo e preservação do SCORE-GEO-002', '### D-038 — Web Performance externo e separação metodológica')
repl(decisions, 'Core Web Vitals/CrUX e Lighthouse entram como **evidência externa complementar** e não como substituição, calibração implícita ou nova fórmula do `SCORE-GEO-002`.', 'Core Web Vitals/CrUX e Lighthouse entram como **evidência externa complementar** e não como substituição ou calibração implícita do `SARI-001`/`SCORE-GEO-003`.')
repl(decisions, '1. `SCORE-GEO-002` permanece baseline oficial interna do RASAi para Readiness;', '1. `SARI-001` é o índice de Readiness e `SCORE-GEO-003` é o método de scoring aplicado;')
repl(decisions, 'sem criar um novo índice nem recalibrar `SCORE-GEO-002`/`SARI-001`.', 'sem criar um novo índice nem recalibrar `SARI-001`/`SCORE-GEO-003`.')
repl(decisions, 'separado do `SARI-001`/`SCORE-GEO-002`.', 'separado do `SARI-001` e sem alterar `SCORE-GEO-003`.')
repl(decisions, '- métricas PageSpeed/CrUX/Lighthouse não alteram `SCORE-GEO-002` sem nova decisão/versionamento explícito;', '- métricas PageSpeed/CrUX/Lighthouse não alteram `SARI-001`/`SCORE-GEO-003` sem decisão e contrato metodológico explícitos;')
repl(decisions, '- diagnósticos de rastreamento e descoberta também não alteram `SCORE-GEO-002`/`SARI-001` sem nova decisão/versionamento explícito;', '- diagnósticos de rastreamento e descoberta também não alteram `SARI-001`/`SCORE-GEO-003` sem decisão e contrato metodológico explícitos;')
repl(decisions, '- outcomes Observed Generative Visibility não alteram `SCORE-GEO-002`/`SARI-001` e não podem ser apresentados como causalidade/predição sem validação empírica específica.', '- outcomes Observed Generative Visibility não alteram `SARI-001`/`SCORE-GEO-003` e não podem ser apresentados como causalidade/predição sem validação empírica específica.')

repl('docs/specification/27_MONITORING_OBSERVABILITY.md', '- `SCORE-GEO-002` permanece histórico;\n', '')
repl('docs/specification/08_TECHNICAL_ARCHITECTURE.md', '- `SCORE-GEO-002`: historical only.\n', '')
repl('docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md', '`SCORE-GEO-002`, `SARI-001`', '`SARI-001`')
replace_token('docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md', 'SCORE-GEO-002', 'SARI-001')
repl('docs/specification/00_SPEC_INDEX.md', '- `SCORE-GEO-002` permanece histórico e não é recalculado;\n', '')

repl(
    'docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md',
    'Rastreamento, descoberta e acesso de crawlers não cria um novo score GEO, não altera `SARI-001` e não recalibra `SCORE-GEO-003`. `SCORE-GEO-002` permanece somente histórico.',
    'Rastreamento, descoberta e acesso de crawlers não cria um novo score, não altera `SARI-001` e não recalibra `SCORE-GEO-003`.'
)
repl(
    'docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md',
    'Elas não homologam `SARI-001`, `SCORE-GEO-003`, o histórico `SCORE-GEO-002`, severidades Rastreamento, descoberta e acesso de crawlers nem qualquer índice proprietário do RASAi.',
    'Elas não homologam `SARI-001`, `SCORE-GEO-003`, severidades de rastreamento/descoberta nem qualquer índice proprietário do RASAi.'
)

repl(
    'docs/specification/04_WORKFLOWS.md',
    'As dez dimensões continuam com cálculo determinístico baseado em regras. O Overall `SCORE-GEO-003` é calibrado e não possui fallback silencioso para média simples. Sem model artifact `VALIDATED`, o Overall permanece `NOT_CONSOLIDATED`. `SCORE-GEO-002` é histórico e não é recalculado.',
    'As dez dimensões usam cálculo determinístico baseado em regras. O Overall `SCORE-GEO-003` é calibrado e não possui fallback silencioso para outro cálculo. Sem model artifact `VALIDATED`, o Overall permanece `NOT_CONSOLIDATED`.'
)
repl(
    'docs/specification/04_WORKFLOWS.md',
    'Coverage não pode substituir a nota. Séries `SCORE-GEO-002` e `SCORE-GEO-003` não são misturadas silenciosamente.',
    'Coverage não pode substituir a nota. Séries com contratos de scoring distintos não são misturadas silenciosamente.'
)

# Applicability spec: current principle only.
app = 'docs/specification/19_SCORE_APPLICABILITY_GEO_MINIMUMS.md'
repl(app, '**Historical predecessor:** `SCORE-GEO-002` introduced the applicability model and remains historical only.\n', '')
repl(app, 'A evolução iniciada no `SCORE-GEO-002` separou corretamente uma dimensão **não aplicável** de uma dimensão que **não conseguiu consolidar**. Esse princípio permanece válido no `SCORE-GEO-003`, embora o Overall atual não seja mais definido pela antiga média simples do `002`.', 'O modelo separa uma dimensão **não aplicável** de uma dimensão que **não conseguiu consolidar**. No `SCORE-GEO-003`, o Overall depende do contrato calibrado e não de média simples das dimensões.')
repl(app, 'A antiga regra do `SCORE-GEO-002` de Overall por média aritmética simples é histórica e não deve ser reaplicada a novas auditorias `SCORE-GEO-003`.', 'O Overall do `SCORE-GEO-003` depende de model artifact `VALIDATED`; não existe fallback para média aritmética simples das dimensões.')
repl(app, 'BR-GEO-054 valida integridade/reprodutibilidade do scoring persistido. Para novas auditorias, a referência vigente é `SCORE-GEO-003`; `SCORE-GEO-002` deve ser reconhecido somente em fontes históricas.', 'BR-GEO-054 valida a integridade e a reprodutibilidade do scoring persistido. A referência metodológica é `SCORE-GEO-003`.')
repl(app, '11. auditoria `SCORE-GEO-002` histórica não é misturada silenciosamente com `SCORE-GEO-003`.', '11. resultados com `scoring_version` distinto não são misturados silenciosamente.')

# No public docs should narrate unreleased predecessor identifiers.
banned = ('SCORE-GEO-001', 'SCORE-GEO-002', 'SGRI-001')
hits = []
for path in [Path('README.md'), *Path('docs').rglob('*.md')]:
    text = path.read_text(encoding='utf-8')
    for token in banned:
        if token in text:
            lines = [f'{i}: {line}' for i, line in enumerate(text.splitlines(), 1) if token in line]
            hits.append(f'{path} :: {token}\n' + '\n'.join(lines))
if hits:
    print('\n\n'.join(hits))
    raise SystemExit('Unreleased predecessor identifiers remain in public documentation')
