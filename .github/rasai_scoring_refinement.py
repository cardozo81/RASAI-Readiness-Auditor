from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


# 1) Discovery resources: absence is no longer a PASS; invalid sitemap is a FAIL.
replace_once(
    "src/rasai/m5.py",
    '''def _evaluate_sitemaps(m2: M2ExecutionResult) -> RuleEvaluation:\n    states = [item.state for item in m2.discovery.sitemaps]\n    if any(state is SitemapState.NETWORK_ERROR for state in states):\n        result = RuleResult.UNKNOWN\n        reason = "SITEMAP_NETWORK_ERROR"\n    elif any(state in {SitemapState.INVALID, SitemapState.HTTP_ERROR} for state in states):\n        result = RuleResult.WARNING\n        reason = "SITEMAP_AVAILABLE_BUT_NOT_INTERPRETABLE"\n    else:\n        result = RuleResult.PASS\n        reason = None\n    return RuleEvaluation(\n        result=result,\n        observed_value={"sitemaps": [{"url": item.url, "state": item.state.value, "error": item.error} for item in m2.discovery.sitemaps]},\n        expected_condition="available sitemap resources are acquired and interpretable; absence alone is not failure",\n        reason=reason,\n    )\n''',
    '''def _evaluate_sitemaps(m2: M2ExecutionResult) -> RuleEvaluation:\n    states = [item.state for item in m2.discovery.sitemaps]\n    if any(state is SitemapState.NETWORK_ERROR for state in states):\n        result = RuleResult.UNKNOWN\n        reason = "SITEMAP_NETWORK_ERROR"\n    elif any(state is SitemapState.INVALID for state in states):\n        result = RuleResult.FAIL\n        reason = "SITEMAP_INVALID"\n    elif any(state is SitemapState.HTTP_ERROR for state in states):\n        result = RuleResult.WARNING\n        reason = "SITEMAP_HTTP_ERROR"\n    elif any(state is SitemapState.OBTAINED for state in states):\n        result = RuleResult.PASS\n        reason = None\n    else:\n        result = RuleResult.WARNING\n        reason = "SITEMAP_ABSENT"\n    return RuleEvaluation(\n        result=result,\n        observed_value={"sitemaps": [{"url": item.url, "state": item.state.value, "error": item.error} for item in m2.discovery.sitemaps]},\n        expected_condition=(\n            "a usable sitemap is a modest positive discovery signal; absence is a small readiness gap, "\n            "and an invalid published sitemap is materially unfavorable"\n        ),\n        reason=reason,\n    )\n''',
)
replace_once(
    "src/rasai/m5.py",
    '''def _evaluate_robots(m2: M2ExecutionResult) -> RuleEvaluation:\n    state = m2.discovery.robots.state\n    if state in {RobotsState.OBTAINED, RobotsState.ABSENT}:\n        result = RuleResult.PASS\n        reason = None\n    else:\n        result = RuleResult.UNKNOWN\n        reason = f"ROBOTS_{state.value}"\n    return RuleEvaluation(\n        result=result,\n        observed_value={"state": state.value, "url": m2.discovery.robots.url},\n        expected_condition="robots.txt is interpretable when present; absence alone is not failure",\n        reason=reason,\n    )\n''',
    '''def _evaluate_robots(m2: M2ExecutionResult) -> RuleEvaluation:\n    state = m2.discovery.robots.state\n    if state is RobotsState.OBTAINED:\n        result = RuleResult.PASS\n        reason = None\n    elif state is RobotsState.ABSENT:\n        result = RuleResult.WARNING\n        reason = "ROBOTS_ABSENT"\n    else:\n        result = RuleResult.UNKNOWN\n        reason = f"ROBOTS_{state.value}"\n    return RuleEvaluation(\n        result=result,\n        observed_value={"state": state.value, "url": m2.discovery.robots.url},\n        expected_condition=(\n            "robots.txt is interpretable when present; absence is not a crawling failure, "\n            "but it does not receive the same positive readiness factor as an explicit usable policy"\n        ),\n        reason=reason,\n    )\n''',
)

# 2) Static/versioned internal weighting. AI rules share the same group, so a positive AI
# assessment cannot double-count a deterministic PASS, while neutral/negative evidence can downgrade it.
replace_once(
    "src/rasai/scoring.py",
    '''    if number in {1, 2, 4, 52, 53, 54}:\n        return RuleScoringMetadata(None)\n    if number in {3, 5, 6, 7, 8, 17, 18, 21, 22, 50}:\n        return RuleScoringMetadata("TECHNICAL_ACCESSIBILITY", scoring_group=_technical_group(number))\n''',
    '''    if number in {1, 2, 4, 52, 53, 54}:\n        return RuleScoringMetadata(None)\n    if number in {3, 55}:\n        return RuleScoringMetadata(\n            "TECHNICAL_ACCESSIBILITY", weight=0.25, warning_factor=0.80, scoring_group="SITEMAP"\n        )\n    if number in {17, 18, 56}:\n        return RuleScoringMetadata(\n            "TECHNICAL_ACCESSIBILITY", weight=0.60, warning_factor=0.60, scoring_group="ROBOTS"\n        )\n    if number in {5, 6}:\n        return RuleScoringMetadata(\n            "TECHNICAL_ACCESSIBILITY", weight=1.25, scoring_group="PAGE_ACCESS"\n        )\n    if number in {7, 8, 21, 22, 50}:\n        return RuleScoringMetadata("TECHNICAL_ACCESSIBILITY", scoring_group=_technical_group(number))\n''',
)
replace_once(
    "src/rasai/scoring.py",
    '''    if 34 <= number <= 37:\n        return RuleScoringMetadata("STRUCTURED_DATA", scoring_group="STRUCTURED_DATA_SYNTAX" if number in {34,35} else "STRUCTURED_DATA_CONSISTENCY")\n''',
    '''    if 34 <= number <= 37:\n        return RuleScoringMetadata(\n            "STRUCTURED_DATA",\n            warning_factor=0.80 if number == 34 else 0.50,\n            scoring_group="STRUCTURED_DATA_SYNTAX" if number in {34,35} else "STRUCTURED_DATA_CONSISTENCY",\n        )\n''',
)

# 3) JSON-LD absence becomes a small measurable readiness gap instead of removing the whole dimension.
replace_once(
    "src/rasai/m7.py",
    '''    if rule_id == "BR-GEO-034":\n        if not structured["present"]:\n            result = RuleResult.NOT_APPLICABLE\n            reason = "STRUCTURED_DATA_ABSENT"\n        elif structured["invalid_blocks"]:\n            result = RuleResult.FAIL\n            reason = "STRUCTURED_DATA_NOT_INTERPRETABLE"\n        else:\n            result = RuleResult.PASS\n            reason = None\n''',
    '''    if rule_id == "BR-GEO-034":\n        if not structured["present"]:\n            result = RuleResult.WARNING\n            reason = "STRUCTURED_DATA_ABSENT"\n        elif structured["invalid_blocks"]:\n            result = RuleResult.FAIL\n            reason = "STRUCTURED_DATA_NOT_INTERPRETABLE"\n        else:\n            result = RuleResult.PASS\n            reason = None\n''',
)
replace_once(
    "src/rasai/m7.py",
    '''                reasoning_summary="Structured Data syntax is evaluated deterministically from preserved parsed blocks.",\n''',
    '''                reasoning_summary=(\n                    "Structured Data presence/syntax is evaluated deterministically from preserved JSON-LD blocks; "\n                    "absence is a modest readiness gap, not a hard failure."\n                ),\n''',
)

# 4) Technical AI contract: evidence-bound resource verdicts, never arbitrary numeric weights.
replace_once(
    "src/rasai/m24_ai.py",
    'CONTRACT_VERSION = "M24-TECHNICAL-REMEDIATION-v1"',
    'CONTRACT_VERSION = "M24-TECHNICAL-REMEDIATION-v2"',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''            "policy_note_pt": {"type": "string", "minLength": 1, "maxLength": 1600},\n        },\n        "required": ["summary_pt", "actions", "policy_note_pt"],\n''',
    '''            "resource_assessments": {\n                "type": "array",\n                "maxItems": 2,\n                "items": {\n                    "type": "object",\n                    "additionalProperties": False,\n                    "properties": {\n                        "resource": {"type": "string", "enum": ["ROBOTS", "SITEMAP"]},\n                        "verdict": {"type": "string", "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"]},\n                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},\n                        "evidence_ids": {\n                            "type": "array",\n                            "uniqueItems": True,\n                            "items": {"type": "string", "minLength": 1},\n                        },\n                        "rationale_pt": {"type": "string", "minLength": 1, "maxLength": 1600},\n                    },\n                    "required": ["resource", "verdict", "confidence", "evidence_ids", "rationale_pt"],\n                },\n            },\n            "policy_note_pt": {"type": "string", "minLength": 1, "maxLength": 1600},\n        },\n        "required": ["summary_pt", "actions", "resource_assessments", "policy_note_pt"],\n''',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''        "Não altere severidade, scoring, SCORE-GEO-004 ou SARI-001. "\n''',
    '''        "Não invente pesos numéricos nem altere a fórmula do SCORE-GEO-004/SARI-001. "\n        "Além das ações, classifique ROBOTS e/ou SITEMAP somente quando houver evidência fornecida, "\n        "usando POSITIVE, NEUTRAL ou NEGATIVE. O runtime converte essa classe por fatores estáticos/versionados. "\n''',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''            "deterministic_remediation": item.remediation,\n            "scoring_impact": "NONE",\n''',
    '''            "deterministic_remediation": item.remediation,\n            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",\n''',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''            f"contract={CONTRACT_VERSION};diagnostics={len(facts)};"\n            "scoring_impact=NONE"\n''',
    '''            f"contract={CONTRACT_VERSION};diagnostics={len(facts)};"\n            "scoring_impact=BOUNDED_STATIC_FACTORS"\n''',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''    actions = value.get("actions")\n    if not summary or not policy_note or not isinstance(actions, list):\n        raise ValueError("M24 AI response misses required fields")\n''',
    '''    actions = value.get("actions")\n    resource_assessments = value.get("resource_assessments")\n    if not summary or not policy_note or not isinstance(actions, list) or not isinstance(resource_assessments, list):\n        raise ValueError("M24 AI response misses required fields")\n''',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''    return {\n        "summary_pt": summary[:2000],\n        "actions": output_actions,\n        "policy_note_pt": policy_note[:1600],\n    }\n''',
    '''    output_resources: list[dict[str, Any]] = []\n    seen_resources: set[str] = set()\n    for raw in resource_assessments[:2]:\n        if not isinstance(raw, Mapping):\n            raise ValueError("M24 AI resource assessment must be an object")\n        resource = str(raw.get("resource") or "").strip().upper()\n        verdict = str(raw.get("verdict") or "").strip().upper()\n        if resource not in {"ROBOTS", "SITEMAP"} or verdict not in {"POSITIVE", "NEUTRAL", "NEGATIVE"}:\n            raise ValueError("M24 AI resource assessment contains invalid classification")\n        if resource in seen_resources:\n            raise ValueError("M24 AI resource assessment duplicates a resource")\n        seen_resources.add(resource)\n        rationale = str(raw.get("rationale_pt") or "").strip()\n        evidence_raw = raw.get("evidence_ids")\n        if not rationale or not isinstance(evidence_raw, list):\n            raise ValueError("M24 AI resource assessment contains invalid fields")\n        evidence_ids = tuple(str(item).strip() for item in evidence_raw if str(item).strip())\n        if not evidence_ids or not set(evidence_ids).issubset(allowed_evidence):\n            raise ValueError("M24 AI resource assessment references evidence outside supplied universe")\n        try:\n            confidence = float(raw.get("confidence"))\n        except (TypeError, ValueError) as exc:\n            raise ValueError("M24 AI resource assessment confidence is invalid") from exc\n        if not 0.0 <= confidence <= 1.0:\n            raise ValueError("M24 AI resource assessment confidence is outside 0..1")\n        output_resources.append({\n            "resource": resource,\n            "verdict": verdict,\n            "confidence": confidence,\n            "evidence_ids": list(evidence_ids),\n            "rationale_pt": rationale[:1600],\n        })\n    return {\n        "summary_pt": summary[:2000],\n        "actions": output_actions,\n        "resource_assessments": output_resources,\n        "policy_note_pt": policy_note[:1600],\n    }\n''',
)
replace_once(
    "src/rasai/m24_ai.py",
    '''        "scoring_impact": "NONE",\n''',
    '''        "scoring_impact": "BOUNDED_STATIC_FACTORS" if result.explanation and result.explanation.get("resource_assessments") else "NONE",\n''',
)

# 5) M24 run carries the validated AI assessments and can be reopened without a second paid call.
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''    external_sitemaps: tuple[str, ...]\n    scoring_impact: str = SCORING_IMPACT\n''',
    '''    external_sitemaps: tuple[str, ...]\n    scoring_impact: str = SCORING_IMPACT\n    ai_provider: str | None = None\n    ai_model: str | None = None\n    ai_assessments: tuple[dict[str, Any], ...] = ()\n''',
)
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''        ai_state = "DISABLED"\n        if technical_ai:\n''',
    '''        ai_state = "DISABLED"\n        ai_provider = None\n        ai_model = None\n        ai_assessments: tuple[dict[str, Any], ...] = ()\n        if technical_ai:\n''',
)
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''                ai_state = ai_result.state.value\n''',
    '''                ai_state = ai_result.state.value\n                ai_provider = ai_result.provider\n                ai_model = ai_result.model\n                if ai_result.explanation and isinstance(ai_result.explanation.get("resource_assessments"), list):\n                    ai_assessments = tuple(\n                        dict(item) for item in ai_result.explanation["resource_assessments"] if isinstance(item, dict)\n                    )\n''',
)
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''        with connection:\n            connection.execute(\n''',
    '''        run_scoring_impact = (\n            "BOUNDED_AI_RESOURCE_ASSESSMENT" if ai_assessments else "NONE"\n        )\n        with connection:\n            connection.execute(\n''',
)
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''                    SCORING_IMPACT,\n                    llms_state,\n''',
    '''                    run_scoring_impact,\n                    llms_state,\n''',
)
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''            external_sitemaps=external_sitemaps,\n        )\n    finally:\n''',
    '''            external_sitemaps=external_sitemaps,\n            scoring_impact=run_scoring_impact,\n            ai_provider=ai_provider,\n            ai_model=ai_model,\n            ai_assessments=ai_assessments,\n        )\n    finally:\n''',
)
# Add reopen helper before _initialize.
replace_once(
    "src/rasai/m24_crawling_discovery.py",
    '''\ndef _initialize(connection: sqlite3.Connection) -> None:\n''',
    '''\ndef load_m24_result(*, audit_id: str, workspace: AuditWorkspace) -> M24ExecutionResult | None:\n    """Reopen a completed crawling/discovery run without repeating network or AI calls."""\n    connection = sqlite3.connect(workspace.database)\n    connection.row_factory = sqlite3.Row\n    try:\n        try:\n            row = connection.execute("SELECT * FROM m24_runs WHERE audit_id=?", (audit_id,)).fetchone()\n        except sqlite3.OperationalError:\n            return None\n        if row is None:\n            return None\n        ai_row = connection.execute("SELECT * FROM m24_ai_results WHERE audit_id=?", (audit_id,)).fetchone()\n        assessments: tuple[dict[str, Any], ...] = ()\n        provider = model = None\n        if ai_row is not None:\n            provider = str(ai_row["provider"]) if ai_row["provider"] else None\n            model = str(ai_row["model"]) if ai_row["model"] else None\n            reference = ai_row["artifact_reference"]\n            if reference:\n                path = workspace.root / str(reference)\n                if path.is_file():\n                    try:\n                        payload = json.loads(path.read_text(encoding="utf-8"))\n                        raw = (payload.get("explanation") or {}).get("resource_assessments")\n                        if isinstance(raw, list):\n                            assessments = tuple(dict(item) for item in raw if isinstance(item, dict))\n                    except (OSError, ValueError, json.JSONDecodeError):\n                        assessments = ()\n        try:\n            external = tuple(str(item) for item in json.loads(str(row["external_sitemaps"])))\n        except (TypeError, ValueError, json.JSONDecodeError):\n            external = ()\n        return M24ExecutionResult(\n            status=str(row["status"]),\n            diagnostics_count=int(row["diagnostics_count"]),\n            llms_state=str(row["llms_state"]),\n            ai_enabled=bool(row["ai_enabled"]),\n            ai_state=str(row["ai_state"]),\n            external_sitemaps=external,\n            scoring_impact=str(row["scoring_impact"]),\n            ai_provider=provider,\n            ai_model=model,\n            ai_assessments=assessments,\n        )\n    finally:\n        connection.close()\n\n\ndef _initialize(connection: sqlite3.Connection) -> None:\n''',
)

# 6) New bounded bridge from validated technical AI classifications into existing scoring groups.
write(
    "src/rasai/m24_scoring.py",
    '''"""Bounded scoring bridge for optional evidence-bound crawling/discovery AI assessments."""\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom typing import Any\n\nfrom rasai.domain import EvidenceType, Finding, FindingDevice, RuleExecution, RuleResult, Severity, new_id, utc_now\nfrom rasai.evidence import EvidenceManager\nfrom rasai.persistence import AuditPersistence\n\n_RESOURCE_RULE = {"SITEMAP": "BR-GEO-055", "ROBOTS": "BR-GEO-056"}\n_VERDICT_RESULT = {"POSITIVE": RuleResult.PASS, "NEUTRAL": RuleResult.WARNING, "NEGATIVE": RuleResult.FAIL}\n\n\n@dataclass(frozen=True, slots=True)\nclass M24ScoringResult:\n    rule_execution_ids: tuple[str, ...]\n    finding_ids: tuple[str, ...]\n\n\ndef _bounded_result(verdict: str, confidence: float) -> RuleResult:\n    normalized = verdict.strip().upper()\n    result = _VERDICT_RESULT.get(normalized)\n    if result is None:\n        raise ValueError(f"unsupported technical AI verdict: {verdict}")\n    # Low-confidence model output may signal review, but never creates a hard PASS/FAIL.\n    if confidence < 0.60:\n        return RuleResult.WARNING\n    return result\n\n\ndef persist_m24_scoring_assessments(\n    *,\n    audit_id: str,\n    persistence: AuditPersistence,\n    ai_state: str,\n    provider: str | None,\n    model: str | None,\n    assessments: tuple[dict[str, Any], ...],\n) -> M24ScoringResult:\n    if ai_state != "AVAILABLE" or not assessments:\n        return M24ScoringResult((), ())\n    manager = EvidenceManager(persistence)\n    executions: list[str] = []\n    findings: list[str] = []\n    for assessment in assessments:\n        resource = str(assessment.get("resource") or "").strip().upper()\n        rule_id = _RESOURCE_RULE.get(resource)\n        if rule_id is None:\n            continue\n        verdict = str(assessment.get("verdict") or "").strip().upper()\n        try:\n            confidence = float(assessment.get("confidence"))\n        except (TypeError, ValueError):\n            continue\n        rationale = str(assessment.get("rationale_pt") or "").strip()\n        source_evidence = tuple(str(item) for item in assessment.get("evidence_ids", ()) if str(item))\n        if not source_evidence or not rationale:\n            continue\n        if any(persistence.evidence.get(evidence_id) is None for evidence_id in source_evidence):\n            continue\n        result = _bounded_result(verdict, confidence)\n        evidence = manager.record(\n            audit_id=audit_id,\n            page_id=None,\n            snapshot_id=None,\n            device=None,\n            evidence_type=EvidenceType.AI_ANALYSIS,\n            source=f"technical-discovery:{provider or 'UNKNOWN'}:{resource}",\n            observed_value={\n                "resource": resource,\n                "verdict": verdict,\n                "confidence": confidence,\n                "rationale_pt": rationale,\n                "provider": provider,\n                "model": model,\n                "source_evidence_ids": list(source_evidence),\n                "weight_policy": "STATIC_VERSIONED_SCORING_METADATA",\n                "positive_bonus_policy": "NO_DOUBLE_COUNT_SAME_SCORING_GROUP",\n            },\n        )\n        execution = RuleExecution(\n            rule_execution_id=new_id("REX"),\n            audit_id=audit_id,\n            rule_id=rule_id,\n            rule_version="1",\n            page_id=None,\n            snapshot_id=None,\n            device=None,\n            result=result,\n            observed_value={\n                "resource": resource,\n                "ai_verdict": verdict,\n                "ai_confidence": confidence,\n                "rationale_pt": rationale,\n            },\n            expected_condition=(\n                f"optional AI assessment of {resource.lower()} corroborates the deterministic resource evidence "\n                "without inventing weights or overriding hard facts"\n            ),\n            evidence_ids=(evidence.evidence_id,),\n            executed_at=utc_now(),\n            error=None,\n        )\n        persistence.rule_executions.add(execution)\n        executions.append(execution.rule_execution_id)\n        if result in {RuleResult.WARNING, RuleResult.FAIL}:\n            finding = Finding(\n                finding_id=new_id("FND"),\n                audit_id=audit_id,\n                rule_id=rule_id,\n                rule_execution_id=execution.rule_execution_id,\n                page_id=None,\n                device=FindingDevice.BOTH,\n                category=resource,\n                severity=Severity.MEDIUM if result is RuleResult.WARNING else Severity.HIGH,\n                source="evidence-bound-technical-ai",\n                title=f"Qualidade técnica de {resource.lower()} requer revisão",\n                observed_value=execution.observed_value,\n                expected_condition=execution.expected_condition,\n                evidence_ids=execution.evidence_ids,\n                status="OPEN",\n            )\n            persistence.findings.add(finding)\n            findings.append(finding.finding_id)\n    return M24ScoringResult(tuple(executions), tuple(findings))\n''',
)

# 7) Execute crawling/discovery once before scoring; the later report layer only reopens it.
replace_once(
    "src/rasai/audit_runner.py",
    '''from rasai.m20_reporting import enrich_m20_report_site\n''',
    '''from rasai.m20_reporting import enrich_m20_report_site\nfrom rasai.m24_crawling_discovery import execute_m24\nfrom rasai.m24_scoring import persist_m24_scoring_assessments\n''',
)
replace_once(
    "src/rasai/audit_runner.py",
    '''    content_remediation: bool = False,\n    discovery_engine: Any | None = None,\n''',
    '''    content_remediation: bool = False,\n    technical_remediation: bool = False,\n    discovery_engine: Any | None = None,\n''',
)
replace_once(
    "src/rasai/audit_runner.py",
    '''        content_remediation=content_remediation,\n        auditor_version=__version__,\n''',
    '''        content_remediation=content_remediation,\n        technical_remediation=technical_remediation,\n        auditor_version=__version__,\n''',
)
replace_once(
    "src/rasai/audit_runner.py",
    '''    if content_remediation:\n        capabilities.append("optional_ai_content_remediation")\n''',
    '''    if content_remediation:\n        capabilities.append("optional_ai_content_remediation")\n    if technical_remediation:\n        capabilities.append("optional_ai_technical_discovery_assessment")\n''',
)
replace_once(
    "src/rasai/audit_runner.py",
    '''            findings_before_integrity = _unique(\n                m5.finding_ids,\n                m6.finding_ids,\n                content.finding_ids,\n                m7.finding_ids,\n                m8.finding_ids,\n            )\n''',
    '''            m24 = execute_m24(\n                audit_id=audit_id,\n                workspace=workspace,\n                technical_ai=technical_remediation,\n                semantic_provider=configured_provider,\n                allow_network=not source_blocked,\n            )\n            m24_scoring = persist_m24_scoring_assessments(\n                audit_id=audit_id,\n                persistence=persistence,\n                ai_state=m24.ai_state,\n                provider=m24.ai_provider,\n                model=m24.ai_model,\n                assessments=m24.ai_assessments,\n            )\n            findings_before_integrity = _unique(\n                m5.finding_ids,\n                m6.finding_ids,\n                content.finding_ids,\n                m7.finding_ids,\n                m8.finding_ids,\n                m24_scoring.finding_ids,\n            )\n''',
)
replace_once(
    "src/rasai/audit_runner.py",
    '''                m8.rule_execution_ids,\n                pre_scoring.rule_execution_ids,\n''',
    '''                m8.rule_execution_ids,\n                m24_scoring.rule_execution_ids,\n                pre_scoring.rule_execution_ids,\n''',
)

# 8) Make the technical remediation flag native to the audit command and pass it to core execution.
replace_once(
    "src/rasai/cli.py",
    '''from rasai.m21_reporting import enrich_m21_report_site\n''',
    '''from rasai.m21_reporting import enrich_m21_report_site\nfrom rasai.m24_cli import configured_m24, register_m24_arguments\n''',
)
replace_once(
    "src/rasai/cli.py",
    '''    audit_parser.add_argument(\n        "--lighthouse-categories",\n''',
    '''    register_m24_arguments(audit_parser)\n    audit_parser.add_argument(\n        "--lighthouse-categories",\n''',
)
replace_once(
    "src/rasai/cli.py",
    '''            content_remediation = _configured_content_remediation(args.ai_content_remediation)\n            web_performance = _configured_web_performance(args)\n''',
    '''            content_remediation = _configured_content_remediation(args.ai_content_remediation)\n            technical_remediation = configured_m24(args).technical_ai\n            web_performance = _configured_web_performance(args)\n''',
)
replace_once(
    "src/rasai/cli.py",
    '''                    semantic_provider=provider,\n                    content_remediation=content_remediation,\n                )\n''',
    '''                    semantic_provider=provider,\n                    content_remediation=content_remediation,\n                    technical_remediation=technical_remediation,\n                )\n''',
)
replace_once(
    "src/rasai/m24_cli.py",
    '''def register_m24_arguments(audit_parser: argparse.ArgumentParser) -> None:\n    audit_parser.add_argument(\n''',
    '''def register_m24_arguments(audit_parser: argparse.ArgumentParser) -> None:\n    if any(getattr(action, "dest", None) == "ai_technical_remediation" for action in audit_parser._actions):\n        return\n    audit_parser.add_argument(\n''',
)

# 9) Do not execute M24/technical AI twice in the extension layer.
replace_once(
    "src/rasai/cli_extensions.py",
    '''from rasai.m24_crawling_discovery import M24ExecutionResult, execute_m24\n''',
    '''from rasai.m24_crawling_discovery import M24ExecutionResult, execute_m24, load_m24_result\n''',
)
replace_once(
    "src/rasai/cli_extensions.py",
    '''        try:\n            m24_result = execute_m24(\n                audit_id=audit_id,\n                workspace=workspace,\n                technical_ai=m24_config.technical_ai,\n                semantic_provider=configured_provider_for_m24,\n                allow_network=allow_network,\n            )\n''',
    '''        try:\n            m24_result = load_m24_result(audit_id=audit_id, workspace=workspace)\n            if m24_result is None:\n                m24_result = execute_m24(\n                    audit_id=audit_id,\n                    workspace=workspace,\n                    technical_ai=m24_config.technical_ai,\n                    semantic_provider=configured_provider_for_m24,\n                    allow_network=allow_network,\n                )\n''',
)
replace_once(
    "src/rasai/cli_extensions.py",
    '''                f"llms.txt {m24_result.llms_state}; IA técnica {m24_result.ai_state}; "\n                "impacto no score NENHUM)"\n''',
    '''                f"llms.txt {m24_result.llms_state}; IA técnica {m24_result.ai_state}; "\n                f"impacto no score {m24_result.scoring_impact})"\n''',
)

# 10) One bounded retry for transient PageSpeed/Lighthouse failures.
replace_once(
    "src/rasai/m21_web_performance.py",
    '''_CWV_THRESHOLDS = {\n''',
    '''_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})\n_PAGESPEED_MAX_ATTEMPTS = 2\n\n_CWV_THRESHOLDS = {\n''',
)
replace_once(
    "src/rasai/m21_web_performance.py",
    '''        return _request_json(\n            service="PAGESPEED_INSIGHTS",\n            request=Request(endpoint, headers={"Accept": "application/json"}),\n            timeout_seconds=timeout_seconds,\n        )\n''',
    '''        request = Request(endpoint, headers={"Accept": "application/json"})\n        last_error: ExternalServiceError | None = None\n        for attempt in range(1, _PAGESPEED_MAX_ATTEMPTS + 1):\n            try:\n                return _request_json(\n                    service="PAGESPEED_INSIGHTS",\n                    request=request,\n                    timeout_seconds=timeout_seconds,\n                )\n            except ExternalServiceError as exc:\n                last_error = exc\n                transient = exc.http_status in _TRANSIENT_HTTP_STATUSES or exc.error_code in {"TIMEOUTERROR", "URLERROR"}\n                if attempt >= _PAGESPEED_MAX_ATTEMPTS or not transient:\n                    raise\n                time.sleep(0.75)\n        assert last_error is not None\n        raise last_error\n''',
)
replace_once(
    "src/rasai/m21_web_performance.py",
    '''    """Collect external lab/field performance evidence without changing SCORE-GEO-002."""\n''',
    '''    """Collect external lab/field performance evidence without changing SARI/SCORE-GEO-004."""\n''',
)

# 11) Reporting reflects the bounded scoring relationship and new contract version.
replace_once(
    "src/rasai/m24_reporting.py",
    '''            WHERE audit_id=? AND semantic_contract_version='M24-TECHNICAL-REMEDIATION-v1'\n''',
    '''            WHERE audit_id=? AND semantic_contract_version='M24-TECHNICAL-REMEDIATION-v2'\n''',
)
replace_once(
    "src/rasai/m24_reporting.py",
    '''<p class='lead'>Diagnóstico aprofundado de robots.txt, sitemaps/feeds, coerência de descoberta e controles de crawlers. Os diagnósticos aprofundados desta página são advisory/non-scoring; porém as evidências determinísticas básicas de sitemap, robots.txt e acesso de crawlers já alimentam BR-GEO-003, BR-GEO-017 e BR-GEO-018 no SCORE-GEO-004.</p>\n''',
    '''<p class='lead'>Diagnóstico aprofundado de robots.txt, sitemaps/feeds, coerência de descoberta e controles de crawlers. As regras determinísticas BR-GEO-003, BR-GEO-017 e BR-GEO-018 alimentam o SARI. Quando a IA técnica é explicitamente habilitada, ela pode apenas corroborar ou rebaixar os mesmos grupos de sitemap/robots por classes evidence-bound convertidas em fatores estáticos; nunca escolhe pesos numéricos.</p>\n''',
)
replace_once(
    "src/rasai/m24_reporting.py",
    '''{_metric("Impacto desta camada", "NENHUM direto")}\n''',
    '''{_metric("Impacto desta camada", str(run["scoring_impact"]) if run else "NONE")}\n''',
)
replace_once(
    "src/rasai/m24_reporting.py",
    '''<div class='notice'><strong>Impacto em scoring:</strong> NENHUM. Este diagnóstico não altera regras nem o Search & AI Readiness Index.</div>\n''',
    '''<div class='notice'><strong>Impacto em scoring:</strong> o diagnóstico determinístico isolado é advisory; BR-GEO-003/017/018 são os inputs técnicos de base. Se IA técnica estiver habilitada e produzir classificação válida, somente a avaliação bounded do mesmo recurso pode compartilhar o grupo de scoring correspondente, sem bônus duplicado.</div>\n''',
)
replace_once(
    "src/rasai/m24_reporting.py",
    '''<p class='intro'>A IA técnica desta página é controlada por <code>RASAI_AI_TECHNICAL_REMEDIATION</code>, independente de <code>RASAI_AI_CONTENT_REMEDIATION</code>. Ela recebe apenas diagnósticos/evidence IDs persistidos, não pode criar fatos nem elevar Confidence por opinião. Qualquer aumento de Confidence só pode ocorrer no pipeline de scoring quando uma regra aplicável passa a ter evidência válida; a remediação técnica desta camada permanece advisory e não altera scoring.</p>\n''',
    '''<p class='intro'>A IA técnica desta página é controlada por <code>RASAI_AI_TECHNICAL_REMEDIATION</code>, independente de <code>RASAI_AI_CONTENT_REMEDIATION</code>. Ela recebe apenas diagnósticos/evidence IDs persistidos e não pode criar fatos, pesos ou elevar Confidence por opinião. Para sitemap/robots, uma classificação válida pode gerar somente PASS/WARNING/FAIL em regras auxiliares bounded que compartilham o mesmo grupo das regras determinísticas; resultado positivo não soma bônus e resultado neutro/negativo pode rebaixar o grupo.</p>\n''',
)

# 12) Scoring report explains static factors and the JSON-LD applicability refinement.
replace_once(
    "src/rasai/score_geo_004_reporting.py",
    '''<section class='panel'><h2>O que entra no score</h2><p class='intro'>Entram somente <strong>RuleExecutions aplicáveis</strong> mapeadas às dimensões do contrato e suas evidências persistidas. Para {SCORING_VERSION}, cada dimensão usa os pesos de regra persistidos em <code>score_contributions</code>; o Overall usa peso igual entre dimensões aplicáveis que tenham medição suficiente.</p>{_dimension_list(effective_version)}</section>\n''',
    '''<section class='panel'><h2>O que entra no score</h2><p class='intro'>Entram somente <strong>RuleExecutions aplicáveis</strong> mapeadas às dimensões do contrato e suas evidências persistidas. Para {SCORING_VERSION}, cada dimensão usa pesos e fatores estáticos/versionados persistidos em <code>score_contributions</code>; o Overall usa peso igual entre dimensões aplicáveis que tenham medição suficiente. Sitemap e robots usam peso interno pequeno/moderado e compartilham grupos com eventual avaliação técnica por IA, impedindo bônus duplicado. JSON-LD ausente é uma lacuna leve mensurável; JSON-LD inválido é desfavorável; consistência semântica pode usar IA evidence-bound quando disponível.</p>{_dimension_list(effective_version)}</section>\n''',
)
replace_once(
    "src/rasai/score_geo_004_reporting.py",
    '''<section class='panel'><h2>Estados de medição</h2><p><code>UNKNOWN</code> não significa FAIL. <code>NOT_APPLICABLE</code> não recebe zero. <code>NOT_CONSOLIDATED</code> indica que a evidência não sustenta consolidação. <code>UNAVAILABLE</code> indica ausência técnica do dado esperado para aquela superfície.</p></section>\n''',
    '''<section class='panel'><h2>Estados de medição</h2><p><code>UNKNOWN</code> não significa FAIL. <code>NOT_APPLICABLE</code> não recebe zero. Ausência de um recurso que o método considera uma melhoria de readiness pode ser <code>WARNING</code> com fator reduzido em vez de PASS ou zero. <code>NOT_CONSOLIDATED</code> indica que a evidência não sustenta consolidação. <code>UNAVAILABLE</code> indica ausência técnica do dado esperado para aquela superfície.</p></section>\n''',
)

# 13) Public docs: static comparison contract, refined discovery/JSON-LD semantics, external metrics remain independent.
for path in ("docs/SCORING_GUIDE.md", "docs/SARI_READINESS_INDEX.md", "docs/SCORE_GEO_004.md"):
    text = read(path)
    marker = "\n## Refinamento pré-publicação: discovery, JSON-LD e fatores estáticos\n"
    if marker not in text:
        text += marker + '''\n- `robots.txt` e sitemap ausentes não recebem o mesmo fator de um recurso encontrado e utilizável; a ausência é uma lacuna pequena, não uma falha dura de crawling.\n- Sitemap publicado porém inválido é desfavorável; falha de rede que impede avaliação continua `UNKNOWN` e reduz Coverage.\n- `script[type="application/ld+json"]` é extraído do HTML. Ausência de JSON-LD é uma lacuna leve mensurável; JSON-LD inválido é desfavorável; consistência com conteúdo/entidades pode usar IA evidence-bound quando habilitada.\n- A IA técnica não escolhe pesos. Ela só pode emitir classes contratadas e referenciadas por evidência; o runtime converte essas classes em `PASS/WARNING/FAIL` com fatores estáticos/versionados no mesmo `scoring_group`, sem bônus duplicado.\n- Lighthouse, Core Web Vitals, Accessibility e Apdex continuam independentes da aritmética do SARI. Indisponibilidade de uma API externa não é tratada como falha do website.\n- Faixas de interpretação e pesos do método são estáticos por versão. Não existe parâmetro por auditoria para alterar o conceito de excelência, preservando comparabilidade temporal.\n'''
        write(path, text)

# Update crawling docs that previously promised zero impact for every technical-AI diagnostic.
for path in ("docs/REPORT_GUIDE.md", "docs/OUTPUTS_AND_ARTIFACTS.md", "docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md"):
    text = read(path)
    text = text.replace(
        "`scoring_impact=NONE`.",
        "Os diagnósticos auxiliares continuam advisory. Quando a IA técnica estiver habilitada e produzir avaliação evidence-bound válida de robots/sitemap, somente a classe bounded do recurso pode compartilhar o grupo de scoring correspondente, com fatores estáticos e sem bônus duplicado.",
    )
    text = text.replace(
        "sem alterar a aritmética de readiness.",
        "sem permitir pesos arbitrários: robots/sitemap usam fatores estáticos do método e a IA opcional só pode corroborar/rebaixar esses mesmos grupos por evidência validada.",
    )
    write(path, text)

# 14) Regression coverage for the new methodological contract.
write(
    "tests/test_scoring_discovery_refinement_20260908.py",
    '''from __future__ import annotations\n\nfrom types import SimpleNamespace\n\nimport pytest\n\nfrom rasai.discovery import RobotsState, SitemapState\nfrom rasai.domain import RuleResult\nfrom rasai.m5 import _evaluate_robots, _evaluate_sitemaps\nfrom rasai.m7 import _deterministic_outcome\nfrom rasai.m21_web_performance import ExternalServiceError, HttpJsonResult, PageSpeedInsightsClient\nfrom rasai.m24_ai import _schema\nfrom rasai.m24_scoring import _bounded_result\nfrom rasai.scoring import _metadata\n\n\ndef _m2(*, robots: RobotsState, sitemaps: tuple[SitemapState, ...]):\n    return SimpleNamespace(\n        discovery=SimpleNamespace(\n            robots=SimpleNamespace(state=robots, url="https://example.test/robots.txt"),\n            sitemaps=tuple(\n                SimpleNamespace(url=f"https://example.test/sitemap-{index}.xml", state=state, error=None)\n                for index, state in enumerate(sitemaps)\n            ),\n        )\n    )\n\n\ndef test_absent_discovery_resources_are_not_positive_passes() -> None:\n    m2 = _m2(robots=RobotsState.ABSENT, sitemaps=(SitemapState.ABSENT,))\n    assert _evaluate_robots(m2).result is RuleResult.WARNING\n    assert _evaluate_sitemaps(m2).result is RuleResult.WARNING\n\n\ndef test_invalid_sitemap_is_materially_unfavorable() -> None:\n    m2 = _m2(robots=RobotsState.OBTAINED, sitemaps=(SitemapState.INVALID,))\n    assert _evaluate_sitemaps(m2).result is RuleResult.FAIL\n\n\ndef test_discovery_weights_are_small_static_and_ai_shares_group() -> None:\n    sitemap = _metadata("BR-GEO-003")\n    sitemap_ai = _metadata("BR-GEO-055")\n    robots = _metadata("BR-GEO-017")\n    robots_ai = _metadata("BR-GEO-056")\n    assert sitemap.weight == sitemap_ai.weight == pytest.approx(0.25)\n    assert sitemap.scoring_group == sitemap_ai.scoring_group == "SITEMAP"\n    assert robots.weight == robots_ai.weight == pytest.approx(0.60)\n    assert robots.scoring_group == robots_ai.scoring_group == "ROBOTS"\n\n\ndef test_missing_jsonld_is_measured_as_modest_warning() -> None:\n    outcome = _deterministic_outcome(\n        "BR-GEO-034",\n        "Example",\n        {"present": False, "invalid_blocks": 0, "types": []},\n        "EV-1",\n    )\n    assert outcome is not None\n    assert outcome.evaluation.result is RuleResult.WARNING\n    assert _metadata("BR-GEO-034").warning_factor == pytest.approx(0.80)\n\n\ndef test_technical_ai_schema_never_exposes_arbitrary_weight() -> None:\n    schema = _schema()\n    resource = schema["properties"]["resource_assessments"]["items"]\n    assert resource["properties"]["verdict"]["enum"] == ["POSITIVE", "NEUTRAL", "NEGATIVE"]\n    assert "weight" not in resource["properties"]\n\n\ndef test_low_confidence_ai_cannot_create_hard_pass_or_fail() -> None:\n    assert _bounded_result("POSITIVE", 0.59) is RuleResult.WARNING\n    assert _bounded_result("NEGATIVE", 0.59) is RuleResult.WARNING\n    assert _bounded_result("NEGATIVE", 0.90) is RuleResult.FAIL\n\n\ndef test_pagespeed_retries_one_transient_failure(monkeypatch) -> None:\n    calls = []\n\n    def fake_request_json(**kwargs):\n        calls.append(kwargs)\n        if len(calls) == 1:\n            raise ExternalServiceError("PAGESPEED_INSIGHTS", "temporary", http_status=500)\n        return HttpJsonResult(payload={"lighthouseResult": {}}, http_status=200, duration_ms=1)\n\n    monkeypatch.setattr("rasai.m21_web_performance._request_json", fake_request_json)\n    monkeypatch.setattr("rasai.m21_web_performance.time.sleep", lambda _value: None)\n    result = PageSpeedInsightsClient("key").run(\n        url="https://example.test/",\n        strategy="mobile",\n        categories=("performance",),\n        timeout_seconds=1.0,\n    )\n    assert result.http_status == 200\n    assert len(calls) == 2\n''',
)

print("RASAi scoring/discovery refinement applied")
