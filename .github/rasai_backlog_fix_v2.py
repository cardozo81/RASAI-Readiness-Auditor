from __future__ import annotations

from pathlib import Path

ROOT = Path('.')


def load(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def save(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding='utf-8', newline='\n')


def replace_once(path: str, old: str, new: str) -> None:
    text = load(path)
    if old not in text:
        raise RuntimeError(f'expected text not found in {path}: {old[:160]!r}')
    save(path, text.replace(old, new, 1))


def replace_between(path: str, start_token: str, end_token: str, replacement: str) -> None:
    text = load(path)
    start = text.find(start_token)
    if start < 0:
        raise RuntimeError(f'start token not found in {path}: {start_token!r}')
    end = text.find(end_token, start)
    if end < 0:
        raise RuntimeError(f'end token not found in {path}: {end_token!r}')
    save(path, text[:start] + replacement + text[end:])


# ---------------------------------------------------------------------------
# P0 - SCORE-GEO-004 / soft-404 consistency
# ---------------------------------------------------------------------------
p = 'src/rasai/m5.py'
text = load(p)
if 'from rasai.javascript_spa import JavascriptSpaAnalyzer\n' not in text:
    text = text.replace(
        'from rasai.extraction import ContentExtractor\n',
        'from rasai.extraction import ContentExtractor\nfrom rasai.javascript_spa import JavascriptSpaAnalyzer\n',
        1,
    )
text = text.replace(
    '("BR-GEO-016", _deferred_soft404()),',
    '("BR-GEO-016", _evaluate_soft404(snapshot, acquisition, workspace)),',
    1,
)
start = text.find('\ndef _deferred_soft404() -> RuleEvaluation:')
if start < 0:
    raise RuntimeError('BR-GEO-016 deferred helper not found')
end = text.find('\n\ndef _evaluate_robots', start)
if end < 0:
    raise RuntimeError('BR-GEO-016 helper boundary not found')
soft404_helper = '''
def _evaluate_soft404(snapshot: Any, acquisition: Any, workspace: AuditWorkspace) -> RuleEvaluation:
    rendered = _artifact_text(workspace, snapshot.rendered_artifact_ref)
    if rendered is None:
        return RuleEvaluation(
            RuleResult.UNKNOWN,
            {"http_status": acquisition.status, "rendered_available": False},
            "error-like pages do not masquerade as valid indexable pages",
            reason="RENDERED_UNAVAILABLE",
        )
    detected = JavascriptSpaAnalyzer().soft404(
        http_status=acquisition.status,
        rendered_html=rendered,
    )
    return RuleEvaluation(
        RuleResult.FAIL if detected else RuleResult.PASS,
        {"http_status": acquisition.status, "soft_404": detected, "rendered_available": True},
        "error-like pages do not masquerade as valid indexable pages",
        reason="STRONG_SOFT_404_SIGNAL" if detected else None,
    )
'''
text = text[:start] + soft404_helper.rstrip() + text[end:]
save(p, text)

p = 'src/rasai/scoring.py'
replace_once(
    p,
    'if number in {3, 5, 6, 7, 8, 17, 18, 21, 22, 23, 50}:\n        return RuleScoringMetadata("TECHNICAL_ACCESSIBILITY", scoring_group=_technical_group(number))\n    if 11 <= number <= 16:',
    'if number in {3, 5, 6, 7, 8, 17, 18, 21, 22, 50}:\n        return RuleScoringMetadata("TECHNICAL_ACCESSIBILITY", scoring_group=_technical_group(number))\n    if 11 <= number <= 16 or number == 23:',
)
replace_once(
    p,
    '17: "ROBOTS", 18: "ROBOTS", 21: "SPA_ROUTE", 22: "SPA_NAVIGATION", 23: "SOFT_ERROR", 50: "INTERNAL_LINKS",',
    '17: "ROBOTS", 18: "ROBOTS", 21: "SPA_ROUTE", 22: "SPA_NAVIGATION", 50: "INTERNAL_LINKS",',
)


# ---------------------------------------------------------------------------
# P1 - DOMAIN scope: make rendered-only discovery gaps explicit.
# ---------------------------------------------------------------------------
p = 'src/rasai/m6.py'
text = load(p)
text = text.replace('from dataclasses import dataclass\n', 'from dataclasses import dataclass, replace\n', 1)
if 'from rasai.url_utils import normalize_url\n' not in text:
    text = text.replace(
        'from rasai.spa_persistence import SnapshotArchitectureWriter\n',
        'from rasai.spa_persistence import SnapshotArchitectureWriter\nfrom rasai.url_utils import normalize_url\n',
        1,
    )
marker = '    architecture: dict[str, ArchitectureClassification] = {}\n\n    for discovered in m2_result.discovery.pages:'
if marker not in text:
    raise RuntimeError('M6 architecture marker not found')
text = text.replace(
    marker,
    '    architecture: dict[str, ArchitectureClassification] = {}\n'
    '    audited_urls = {item.normalized_url for item in m2_result.discovery.pages}\n'
    '    rendered_outside_audit: set[str] = set()\n\n'
    '    for discovered in m2_result.discovery.pages:',
    1,
)
marker = '            lazy_after: str | None = None\n'
if marker not in text:
    raise RuntimeError('M6 lazy marker not found')
text = text.replace(
    marker,
    '            nav_observed = evaluations["BR-GEO-022"].observed_value\n'
    '            if isinstance(nav_observed, dict):\n'
    '                for candidate in nav_observed.get("crawlable_internal_links", ()):\n'
    '                    if not isinstance(candidate, str):\n'
    '                        continue\n'
    '                    try:\n'
    '                        normalized_candidate = normalize_url(candidate)\n'
    '                    except ValueError:\n'
    '                        continue\n'
    '                    if normalized_candidate not in audited_urls:\n'
    '                        rendered_outside_audit.add(normalized_candidate)\n\n'
    + marker,
    1,
)
marker = '    return M6ExecutionResult(tuple(execution_ids), tuple(finding_ids), architecture)\n'
if marker not in text:
    raise RuntimeError('M6 return marker not found')
text = text.replace(
    marker,
    '    if rendered_outside_audit:\n'
    '        audit = persistence.audits.get(audit_id)\n'
    '        if audit is not None:\n'
    '            reason = (\n'
    '                f"RENDERED_LINKS_OUTSIDE_AUDIT_UNIVERSE_MAX_PAGES:{len(rendered_outside_audit)}"\n'
    '                if m2_result.discovery.limit_reached\n'
    '                else f"RENDERED_DISCOVERY_GAP:{len(rendered_outside_audit)}"\n'
    '            )\n'
    '            persistence.audits.update(\n'
    '                replace(audit, limitations=tuple(dict.fromkeys((*audit.limitations, reason))))\n'
    '            )\n\n'
    + marker,
    1,
)
save(p, text)


# ---------------------------------------------------------------------------
# P0 - Evidence-bound AI: prevent unknown evidence ids at schema level.
# ---------------------------------------------------------------------------
p = 'src/rasai/openai_provider.py'
replace_between(
    p,
    'def hardened_semantic_output_schema() -> dict[str, Any]:',
    '\n\nclass OpenAIProvider',
    '''def hardened_semantic_output_schema(
    allowed_evidence_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return the strict semantic schema, optionally bound to input evidence ids."""

    schema = json.loads(json.dumps(semantic_output_schema()))
    assessments = schema["properties"]["assessments"]
    assessments["minItems"] = len(SEMANTIC_RULE_IDS)
    assessments["maxItems"] = len(SEMANTIC_RULE_IDS)
    if allowed_evidence_ids:
        allowed = sorted(allowed_evidence_ids)
        assessments["items"]["properties"]["evidence_ids"]["items"]["enum"] = allowed
        schema["properties"]["entities"]["items"]["properties"]["evidence_ids"]["items"]["enum"] = allowed
    return schema
'''.rstrip(),
)
replace_once(
    p,
    '"schema": hardened_semantic_output_schema(),',
    '"schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),',
)

p = 'src/rasai/m18_ai.py'
text = load(p)
text = text.replace(
    'def _deepseek_semantic_output_schema() -> dict[str, Any]:',
    'def _deepseek_semantic_output_schema(allowed_evidence_ids: frozenset[str] | None = None) -> dict[str, Any]:',
    1,
)
text = text.replace(
    'schema = json.loads(json.dumps(hardened_semantic_output_schema()))',
    'schema = json.loads(json.dumps(hardened_semantic_output_schema(allowed_evidence_ids)))',
    1,
)
text = text.replace(
    '        semantic_schema = hardened_semantic_output_schema()\n        if self.name == "DEEPSEEK":\n            semantic_schema = _deepseek_semantic_output_schema()',
    '        semantic_schema = hardened_semantic_output_schema(semantic_input.allowed_evidence_ids)\n        if self.name == "DEEPSEEK":\n            semantic_schema = _deepseek_semantic_output_schema(semantic_input.allowed_evidence_ids)',
    1,
)
save(p, text)

p = 'src/rasai/provider_extensions.py'
text = load(p)
if 'hardened_semantic_output_schema()' not in text:
    raise RuntimeError('provider extension schema call not found')
text = text.replace(
    'hardened_semantic_output_schema()',
    'hardened_semantic_output_schema(semantic_input.allowed_evidence_ids)',
)
save(p, text)


# ---------------------------------------------------------------------------
# P1 - Reporting: provider configured/called/rejected != NO_AI.
# ---------------------------------------------------------------------------
p = 'src/rasai/m11.py'
text = load(p)
anchor = 'reporting_module.TEMPLATE_VERSION = TEMPLATE_VERSION\n\n'
helper = '''_NON_EXTERNAL_SEMANTIC_PROVIDERS = frozenset({
    "", "NONE", "FALLBACK", "UNAVAILABLE", "DETERMINISTIC", "DETERMINISTIC_BASELINE"
})


def _external_semantic_providers(semantic: list[sqlite3.Row]) -> set[str]:
    return {
        str(row["provider"]).upper()
        for row in semantic
        if row["provider"] and str(row["provider"]).upper() not in _NON_EXTERNAL_SEMANTIC_PROVIDERS
    }


'''
if '_NON_EXTERNAL_SEMANTIC_PROVIDERS' not in text:
    if anchor not in text:
        raise RuntimeError('m11 helper anchor not found')
    text = text.replace(anchor, anchor + helper, 1)

start = text.find('def _ai_usage_status(')
end = text.find('\n\ndef _configured_semantic_provider', start)
if start < 0 or end < 0:
    raise RuntimeError('m11 ai usage function boundaries not found')
usage_function = '''def _ai_usage_status(semantic: list[sqlite3.Row]) -> str:
    """Return the human state of external semantic AI for this audit report."""
    providers = {str(row["provider"]).upper() for row in semantic if row["provider"]}
    if _external_semantic_providers(semantic):
        return "SIM"
    if "UNAVAILABLE" in providers:
        return "TENTATIVA SEM SUCESSO"
    return "NÃO"
'''
text = text[:start] + usage_function.rstrip() + text[end:]

start = text.find('def _configured_semantic_provider(')
end = text.find('\n\n\nclass _PersistedInputAwareReportBuilder', start)
if start < 0 or end < 0:
    raise RuntimeError('m11 configured provider boundaries not found')
provider_function = '''def _configured_semantic_provider(audit: sqlite3.Row, semantic: list[sqlite3.Row]) -> str:
    """Resolve provider configuration independently from provider call outcome."""
    capabilities = tuple(str(item) for item in _json_list(audit["capabilities"]))
    for capability in capabilities:
        if capability.startswith("semantic_provider:"):
            return capability.split(":", 1)[1].strip().upper() or "NÃO INFORMADO"
    external = _external_semantic_providers(semantic)
    if external:
        return ", ".join(sorted(external))
    providers = {str(row["provider"]).upper() for row in semantic if row["provider"]}
    if "UNAVAILABLE" in providers:
        return "PROVIDER EXTERNO NÃO IDENTIFICADO"
    return "NÃO INFORMADO"
'''
text = text[:start] + provider_function.rstrip() + text[end:]

start_token = '        if configured_provider == "OPENAI" and usage_status == "TENTATIVA SEM SUCESSO":'
start = text.find(start_token)
end = text.find('        html = html.replace(', start)
if start < 0 or end < 0:
    raise RuntimeError('m11 provider/model display block boundaries not found')
provider_display_block = '''        configured_external = configured_provider not in {"NÃO INFORMADO", "NONE", "NÃO", ""}
        if configured_external and usage_status == "TENTATIVA SEM SUCESSO":
            provider_display = f"{configured_provider} - CHAMADA/RESPOSTA INDISPONÍVEL"
        elif configured_external and usage_status == "SIM" and "UNAVAILABLE" in {item.upper() for item in providers}:
            provider_display = f"{configured_provider} - SUCESSO PARCIAL"
        else:
            provider_display = configured_provider

        if models:
            model_display = ", ".join(models)
        elif configured_external:
            model_display = "CONFIGURADO · NÃO CONFIRMADO POR RESPOSTA VÁLIDA"
        else:
            model_display = "NÃO APLICÁVEL"

'''
text = text[:start] + provider_display_block + text[end:]
save(p, text)

p = 'src/rasai/m17_reporting.py'
replace_between(
    p,
    'def _ai_disclaimer(rows: list[Any]) -> str:',
    '\n\ndef _inject_actionability_metrics',
    '''def _ai_disclaimer(rows: list[Any]) -> str:
    providers = {str(row["provider"]).upper() for row in rows if row["provider"]}
    external = sorted(
        item for item in providers
        if item not in {"", "NONE", "FALLBACK", "UNAVAILABLE", "DETERMINISTIC", "DETERMINISTIC_BASELINE"}
    )
    unavailable = "UNAVAILABLE" in providers
    if external and unavailable:
        return (
            f"Provider(s) externo(s) {', '.join(external)} produziram resultados válidos em parte da auditoria, mas também houve chamadas ou respostas rejeitadas/indisponíveis. "
            "Somente respostas normalizadas e persistidas são consideradas análises externas concluídas."
        )
    if external:
        return (
            f"Análises semânticas externas foram concluídas e persistidas com provider(s) {', '.join(external)}. "
            "O relatório não realiza chamada livre adicional para redigir remediações."
        )
    if unavailable:
        return (
            "O provider externo foi configurado e houve tentativa de uso, mas nenhuma análise semântica externa válida foi concluída nesta auditoria. "
            "A resposta foi indisponível ou rejeitada pelo contrato evidence-bound; o baseline determinístico permanece o fallback quando aplicável."
        )
    return (
        "Nenhuma análise semântica externa concluída foi persistida nesta auditoria. "
        "Ausência de IA pode reduzir cobertura sem penalizar automaticamente o website."
    )
'''.rstrip(),
)

p = 'src/rasai/reporting.py'
text = load(p)
old = '''        if audit_mode in {AuditMode.FULL, AuditMode.DEGRADED} and any(
            "OPENAI" in value.upper() or "AI_PROVIDER" in value.upper()
            for value in capabilities
        ):
            return (
                "Análises semânticas utilizaram o provider externo configurado. O relatório reutiliza somente resultados normalizados e persistidos; "
                "credenciais não são incluídas e nenhuma chamada livre adicional é feita para redigir remediações."
            )
'''
new = '''        provider_configured = any(
            value.upper().startswith("SEMANTIC_PROVIDER:") and not value.upper().endswith(":NONE")
            for value in capabilities
        )
        if audit_mode is AuditMode.DEGRADED and provider_configured:
            return (
                "Um provider externo foi configurado e houve tentativa de análise, mas ao menos um contexto ficou indisponível ou teve a resposta rejeitada pelo contrato evidence-bound. "
                "Somente resultados externos válidos são reutilizados; o baseline determinístico permanece disponível como fallback onde houver evidência suficiente."
            )
        if audit_mode is AuditMode.FULL and provider_configured:
            return (
                "Análises semânticas utilizaram o provider externo configurado. O relatório reutiliza somente resultados normalizados e persistidos; "
                "credenciais não são incluídas e nenhuma chamada livre adicional é feita para redigir remediações."
            )
'''
if old not in text:
    raise RuntimeError('reporting AI disclaimer block not found')
text = text.replace(old, new, 1)
old = '''            note = (
                "Entidades e intenções semânticas não ficaram disponíveis em modo NO_AI; isso é uma limitação da auditoria, não um defeito do site."
                if audit_mode is AuditMode.NO_AI
                else "Nenhuma entidade ou intenção persistida está disponível."
            )
'''
new = '''            if audit_mode is AuditMode.NO_AI:
                note = "Entidades e intenções semânticas não ficaram disponíveis em modo NO_AI; isso é uma limitação da auditoria, não um defeito do site."
            elif audit_mode is AuditMode.DEGRADED:
                note = "O provider externo foi configurado, mas a análise válida não ficou disponível para este contexto; o estado é DEGRADED, não NO_AI."
            else:
                note = "Nenhuma entidade ou intenção persistida está disponível."
'''
if old not in text:
    raise RuntimeError('reporting entity note block not found')
text = text.replace(old, new, 1)
save(p, text)


# ---------------------------------------------------------------------------
# P2 - Apdex small-group semantics and P3 runtime browser provenance.
# ---------------------------------------------------------------------------
p = 'src/rasai/m23_apdex.py'
text = load(p)
text = text.replace(
    '    attempted_total = valid_total = invalid_total = 0\n    complete_contexts = small_groups = 0',
    '    attempted_total = valid_total = invalid_total = 0\n    complete_contexts = target_met_contexts = small_groups = 0',
    1,
)
text = text.replace(
    '                if summary.final_group:\n                    complete_contexts += 1\n                if summary.small_group and summary.valid_samples:\n                    small_groups += 1',
    '                if summary.final_group:\n                    complete_contexts += 1\n                if summary.valid_samples >= cfg.target_valid_samples:\n                    target_met_contexts += 1\n                if summary.small_group and summary.valid_samples:\n                    small_groups += 1',
    1,
)
old = '''            if not contexts:
                status, reason = "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
            elif complete_contexts == len(contexts) and invalid_total == 0:
                status, reason = "SUCCESS", None
            elif valid_total == 0:
                status, reason = "UNAVAILABLE", "NO_VALID_SYNTHETIC_SAMPLES"
            else:
                status, reason = "PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE_OR_INVALID"
'''
new = '''            status, reason = _run_status(
                context_count=len(contexts),
                final_contexts=complete_contexts,
                target_met_contexts=target_met_contexts,
                small_groups=small_groups,
                valid_total=valid_total,
                invalid_total=invalid_total,
            )
'''
if old not in text:
    raise RuntimeError('M23 status block not found')
text = text.replace(old, new, 1)
marker = '\n\ndef _measure_context(\n'
if marker not in text:
    raise RuntimeError('M23 helper insertion marker not found')
helper = '''

def _run_status(
    *,
    context_count: int,
    final_contexts: int,
    target_met_contexts: int,
    small_groups: int,
    valid_total: int,
    invalid_total: int,
) -> tuple[str, str | None]:
    if context_count == 0:
        return "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
    if final_contexts == context_count and invalid_total == 0:
        return "SUCCESS", None
    if valid_total == 0:
        return "UNAVAILABLE", "NO_VALID_SYNTHETIC_SAMPLES"
    if target_met_contexts == context_count and invalid_total == 0 and small_groups:
        return "PARTIAL", "SMALL_GROUP_BELOW_NORMAL_MINIMUM"
    return "PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE_OR_INVALID"
'''
text = text.replace(marker, helper + marker, 1)
save(p, text)

p = 'src/rasai/m23_reporting.py'
replace_once(
    p,
    '    if status == "PARTIAL":\n        return "<div class=\'notice warn\'><strong>Coleta Apdex parcial.</strong> Há grupos incompletos ou amostras excluídas por integridade da ferramenta/perfil. Consulte os detalhes.</div>"',
    '    if status == "PARTIAL":\n        if run is not None and str(run["reason"] or "") == "SMALL_GROUP_BELOW_NORMAL_MINIMUM":\n            return "<div class=\'notice warn\'><strong>Coleta Apdex válida em grupo pequeno.</strong> O alvo configurado de amostras válidas foi atingido sem exclusões, mas o grupo permanece abaixo do mínimo normal de 100 amostras e é diagnóstico, não baseline final.</div>"\n        return "<div class=\'notice warn\'><strong>Coleta Apdex parcial.</strong> Um ou mais contextos não atingiram o alvo configurado ou houve amostras inválidas/excluídas. Consulte os detalhes.</div>"',
)

p = 'src/rasai/m23_apdex_profiles.py'
replace_once(
    p,
    '            "user_agent": self.browser_profile.user_agent,\n            "browser_identity_strategy": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",',
    '            "user_agent": self.browser_profile.user_agent,\n            "user_agent_role": "PROFILE_TEMPLATE_ONLY_NOT_EFFECTIVE_RUNTIME_VALUE",\n            "effective_user_agent_source": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",\n            "effective_user_agent_persisted": False,\n            "browser_identity_strategy": "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER",',
)

p = 'src/rasai/report_semantics.py'
replace_once(
    p,
    '        "BrowserContext novo · cache OFF · randomização NONE"\n    )',
    '        "BrowserContext novo · cache OFF · randomização NONE · UA efetivo resolvido em runtime; UA do perfil é template"\n    )',
)


# ---------------------------------------------------------------------------
# P2 - External report metadata/counters are neutral, not quality scores.
# ---------------------------------------------------------------------------
p = 'src/rasai/external_metrics_integrity.py'
replace_once(
    p,
    'return f"<div class=\'metric\'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"',
    'return f"<div class=\'metric result-state-neutral\'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"',
)


# ---------------------------------------------------------------------------
# P1 - Current runtime/reporting surfaces must use SCORE-GEO-004.
# Historical specification references are intentionally untouched.
# ---------------------------------------------------------------------------
for path in (
    'src/rasai/m11.py',
    'src/rasai/m19_reporting.py',
    'src/rasai/m20_reporting.py',
    'src/rasai/m23_reporting.py',
    'src/rasai/m24_reporting.py',
    'src/rasai/m25_reporting.py',
    'src/rasai/external_metrics_integrity.py',
    'src/rasai/content_context.py',
    'src/rasai/cli_extensions.py',
):
    data = load(path)
    save(path, data.replace('SCORE-GEO-002', 'SCORE-GEO-004'))


# ---------------------------------------------------------------------------
# Documentation alignment.
# ---------------------------------------------------------------------------
p = 'docs/SCORING_GUIDE.md'
text = load(p)
anchor = 'Estado insuficiente nunca vira zero.\n'
addition = '''

### Soft-404 e Coverage de Indexability

`BR-GEO-016` é avaliada com evidência de estado renderizado quando disponível. Ela não pode permanecer `UNKNOWN` apenas por fronteira interna entre módulos. `BR-GEO-016` e `BR-GEO-023` pertencem ao grupo `INDEXABILITY / SOFT_ERROR`; o agrupamento impede peso duplicado quando ambas observam o mesmo contexto de soft-404.
'''
if '### Soft-404 e Coverage de Indexability' not in text:
    if anchor not in text:
        raise RuntimeError('SCORING_GUIDE anchor not found')
    text = text.replace(anchor, anchor + addition, 1)
save(p, text)

p = 'docs/AI_GUIDE.md'
text = load(p)
anchor = 'Falha de provider não deve ser convertida em finding do website;\n'
addition = '''
- `evidence_ids` retornados por provider são limitados ao conjunto exato fornecido naquele contexto; referência a ID externo ao input invalida a resposta, não a evidência local;
- provider configurado/chamado com resposta indisponível ou rejeitada por contrato deve aparecer como execução `DEGRADED`, e não como `NO_AI`;
'''
if 'evidence_ids` retornados por provider' not in text:
    if anchor not in text:
        raise RuntimeError('AI_GUIDE anchor not found')
    text = text.replace(anchor, anchor + addition, 1)
save(p, text)

p = 'docs/SYNTHETIC_APDEX.md'
text = load(p)
anchor = 'Grupos entre 1 e 99 amostras válidas são diagnóstico small-group e recebem marcador `*`. O objetivo é impedir que um smoke curto pareça uma baseline final.\n'
addition = '''

Quando o alvo configurado é menor que 100 e é integralmente atingido sem amostras inválidas, o run permanece `PARTIAL` por `SMALL_GROUP_BELOW_NORMAL_MINIMUM`. Esse estado é diferente de coleta incompleta ou amostra inválida.
'''
if 'SMALL_GROUP_BELOW_NORMAL_MINIMUM' not in text:
    if anchor not in text:
        raise RuntimeError('SYNTHETIC_APDEX anchor not found')
    text = text.replace(anchor, anchor + addition, 1)
save(p, text)

p = 'docs/REPORT_GUIDE.md'
text = load(p)
anchor = 'Observed Generative Visibility **não altera SARI-001/SCORE-GEO-004**.\n'
addition = '''

Em auditorias de domínio, destinos internos observados apenas após rendering e que ficaram fora do universo auditado são expostos como limitação de cobertura (`RENDERED_DISCOVERY_GAP` ou limite equivalente). O relatório não deve apresentar uma homepage isolada como cobertura implícita de todo o domínio.
'''
if 'RENDERED_DISCOVERY_GAP' not in text:
    if anchor not in text:
        raise RuntimeError('REPORT_GUIDE anchor not found')
    text = text.replace(anchor, anchor + addition, 1)
save(p, text)


# ---------------------------------------------------------------------------
# Regression tests for the consolidated backlog.
# ---------------------------------------------------------------------------
test_path = ROOT / 'tests/test_consolidated_backlog_regressions.py'
test_path.write_text('''from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.m11 import _ai_usage_status
from rasai.m23_apdex import _run_status
from rasai.m23_apdex_profiles import MOBILE_STANDARD_PROFILE
from rasai.openai_provider import OpenAIProvider, hardened_semantic_output_schema
from rasai.report_semantics import enhance_report_html
from rasai.scoring import _metadata
from rasai.semantic import SemanticEvidenceInput, SemanticInput


class ConsolidatedBacklogRegressionTests(unittest.TestCase):
    def test_soft_error_rules_share_indexability_group(self) -> None:
        self.assertEqual(_metadata("BR-GEO-016").dimension, "INDEXABILITY")
        self.assertEqual(_metadata("BR-GEO-016").scoring_group, "SOFT_ERROR")
        self.assertEqual(_metadata("BR-GEO-023").dimension, "INDEXABILITY")
        self.assertEqual(_metadata("BR-GEO-023").scoring_group, "SOFT_ERROR")

    def test_semantic_schema_binds_allowed_evidence_ids(self) -> None:
        schema = hardened_semantic_output_schema(frozenset({"EV-1", "EV-2"}))
        assessment_ids = schema["properties"]["assessments"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
        entity_ids = schema["properties"]["entities"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
        self.assertEqual(assessment_ids, ["EV-1", "EV-2"])
        self.assertEqual(entity_ids, ["EV-1", "EV-2"])

    def test_openai_request_schema_is_bound_to_context_evidence(self) -> None:
        semantic = SemanticInput(
            snapshot_id="SNP-1",
            page_url="https://example.test/",
            title="Example",
            main_content="Evidence",
            structured_data=None,
            primary_language="pt-BR",
            market="BR",
            evidence=(SemanticEvidenceInput("EV-ONLY", "TEXT_EXCERPT", "test", {"text": "Evidence"}),),
        )
        provider = OpenAIProvider(model="gpt-5.6-luna", api_key="x")
        payload = provider._request_payload(semantic)
        ids = payload["text"]["format"]["schema"]["properties"]["assessments"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
        self.assertEqual(ids, ["EV-ONLY"])

    def test_ai_usage_is_provider_neutral_and_distinguishes_rejection(self) -> None:
        self.assertEqual(_ai_usage_status([{"provider": "DEEPSEEK"}]), "SIM")
        self.assertEqual(_ai_usage_status([{"provider": "MIMO"}, {"provider": "UNAVAILABLE"}]), "SIM")
        self.assertEqual(_ai_usage_status([{"provider": "UNAVAILABLE"}]), "TENTATIVA SEM SUCESSO")
        self.assertEqual(_ai_usage_status([{"provider": "DETERMINISTIC_BASELINE"}]), "NÃO")

    def test_apdex_small_group_is_not_invalid_sampling(self) -> None:
        self.assertEqual(
            _run_status(
                context_count=1, final_contexts=0, target_met_contexts=1,
                small_groups=1, valid_total=20, invalid_total=0,
            ),
            ("PARTIAL", "SMALL_GROUP_BELOW_NORMAL_MINIMUM"),
        )
        self.assertEqual(
            _run_status(
                context_count=1, final_contexts=0, target_met_contexts=0,
                small_groups=1, valid_total=15, invalid_total=5,
            ),
            ("PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE_OR_INVALID"),
        )

    def test_synthetic_profile_declares_user_agent_provenance(self) -> None:
        data = MOBILE_STANDARD_PROFILE.as_dict()
        self.assertEqual(data["user_agent_role"], "PROFILE_TEMPLATE_ONLY_NOT_EFFECTIVE_RUNTIME_VALUE")
        self.assertEqual(data["effective_user_agent_source"], "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER")
        self.assertFalse(data["effective_user_agent_persisted"])

    def test_web_performance_metadata_is_not_scored_as_bad(self) -> None:
        html = """<html><head><style></style></head><body>
        <div class='metric'><small>Performance</small><strong>42/100</strong></div>
        <div class='metric'><small>Escopo</small><strong>URL</strong></div>
        <div class='metric'><small>Fonte</small><strong>PAGESPEED_CRUX</strong></div>
        </body></html>"""
        with TemporaryDirectory() as tmp:
            output = enhance_report_html(html, page_name="web-performance.html", report_dir=Path(tmp))
        self.assertEqual(output.count("Ruim (0-49)"), 1)
        self.assertNotIn("<small>Escopo</small><strong>URL</strong><span class='result-tag bad'>", output)
        self.assertNotIn("<small>Fonte</small><strong>PAGESPEED_CRUX</strong><span class='result-tag bad'>", output)

    def test_current_runtime_files_do_not_claim_score_geo_002(self) -> None:
        selected = [
            "src/rasai/m20_reporting.py", "src/rasai/m23_reporting.py",
            "src/rasai/m24_reporting.py", "src/rasai/m25_reporting.py",
            "src/rasai/external_metrics_integrity.py", "src/rasai/cli_extensions.py",
        ]
        root = Path(__file__).resolve().parents[1]
        for relative in selected:
            with self.subTest(relative=relative):
                self.assertNotIn("SCORE-GEO-002", (root / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
''', encoding='utf-8', newline='\n')

print('Consolidated backlog patch applied.')
