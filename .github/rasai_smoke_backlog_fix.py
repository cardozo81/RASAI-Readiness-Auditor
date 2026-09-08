from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def save(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_exact(path: str, old: str, new: str, *, count: int = 1) -> None:
    text = load(path)
    found = text.count(old)
    if found < count:
        raise RuntimeError(f"{path}: expected at least {count} occurrence(s), found {found}: {old[:120]!r}")
    save(path, text.replace(old, new, count))


def replace_regex(path: str, pattern: str, replacement: str, *, count: int = 1) -> None:
    text = load(path)
    updated, changed = re.subn(pattern, replacement, text, count=count, flags=re.DOTALL)
    if changed != count:
        raise RuntimeError(f"{path}: regex expected {count} replacement(s), got {changed}: {pattern[:120]!r}")
    save(path, updated)


def append_section(path: str, marker: str, body: str) -> None:
    text = load(path)
    if marker in text:
        return
    save(path, text.rstrip() + "\n\n" + marker + "\n" + body.strip() + "\n")


# ---------------------------------------------------------------------------
# 1. Executive dashboard: correct Lighthouse scale + metric-specific semantics.
# ---------------------------------------------------------------------------
replace_exact(
    "src/rasai/rasai_readiness_reporting.py",
    "<article class='ref-card'><h3>Confidence</h3><p>O Overall usa a menor Confidence entre as dimensões aplicáveis. Para consolidar, exige Coverage média de pelo menos 80% e Confidence mínima MEDIUM.</p></article>",
    "<article class='ref-card'><h3>Confidence</h3><p>O Overall usa a menor Confidence entre as dimensões aplicáveis. Para consolidar, exige Coverage média de pelo menos 80% e Confidence mínima MEDIUM. A presença de IA não é requisito: uma execução NO_AI pode atingir MEDIUM/HIGH quando Coverage, evidências e integridade da execução forem suficientes.</p></article>",
)

new_dashboard = r'''def _dashboard(data: dict[str, Any], report_dir: Path) -> str:
    cards: list[str] = []
    scores = data["scores"]
    for device in ("MOBILE", "DESKTOP"):
        row = next(
            (
                item for item in scores
                if str(item["device"]).upper() == device
                and str(item["dimension"]) == "OVERALL_READINESS"
            ), None,
        )
        if row is None:
            continue
        label = "Mobile" if device == "MOBILE" else "Desktop"
        coverage = f"{float(row['coverage']) * 100:.0f}%"
        confidence = _STATUS_LABELS.get(str(row["confidence"]), str(row["confidence"]))
        if row["value"] is None:
            value = "NÃO CONSOLIDADO"
            detail = f"Coverage {coverage} - Confidence {confidence}"
        else:
            value = f"{float(row['value']):.1f}/100"
            status = _STATUS_LABELS.get(str(row["consolidation_status"]), str(row["consolidation_status"]))
            detail = f"Coverage {coverage} - Confidence {confidence} - {status}"
        condition, condition_label = _sari_condition(row)
        cards.append(_indicator_card(
            f"Search & AI Readiness - {label}", value, detail, RASAI_FILE,
            "RASAi - SARI-001", condition, condition_label,
        ))

    web = data["web"]
    cwv_values = [str(row["cwv_assessment"]) for row in web if str(row["cwv_assessment"]) in {"PASS", "FAIL"}]
    if cwv_values:
        passed = sum(value == "PASS" for value in cwv_values)
        total = len(cwv_values)
        cwv_value = f"{passed}/{total} aprovados"
        cwv_detail = "Aprovação exige LCP, INP e CLS p75 dentro dos limites Core Web Vitals no contexto."
        cwv_condition, cwv_label = _cwv_condition(passed, total)
    else:
        cwv_value, cwv_detail = "NÃO DISPONÍVEL", _external_status(data["web_run"])
        cwv_condition, cwv_label = "neutral", "Sem dados suficientes"
    cards.append(_indicator_card(
        "Core Web Vitals", cwv_value, cwv_detail, "web-performance.html", "Chrome / web.dev",
        cwv_condition, cwv_label,
    ))

    perf = _device_ranges(web, "performance_score", scale=1.0, suffix="/100")
    perf_condition, perf_label = _lighthouse_condition(web, "performance_score")
    cards.append(_indicator_card(
        "Lighthouse Performance", perf[0], perf[1], "web-performance.html", "Chrome Lighthouse",
        perf_condition, perf_label,
    ))
    a11y = _device_ranges(web, "accessibility_score", scale=1.0, suffix="/100")
    a11y_condition, a11y_label = _lighthouse_condition(web, "accessibility_score")
    cards.append(_indicator_card(
        "Lighthouse Accessibility", a11y[0], a11y[1], "accessibility.html", "Chrome Lighthouse + WCAG 2.2",
        a11y_condition, a11y_label,
    ))

    apdex_run = data["apdex_run"]
    all_apdex_rows = [row for row in data["apdex"] if row["apdex_score"] is not None]
    final_rows = [row for row in all_apdex_rows if _truthy(row, "final_group")]
    apdex_rows = final_rows or all_apdex_rows
    small_group_only = bool(apdex_rows) and not bool(final_rows)
    if apdex_rows:
        apdex_value, apdex_detail = _device_ranges(apdex_rows, "apdex_score", scale=1.0, suffix="", digits=3)
        if small_group_only:
            apdex_detail += "; grupo pequeno (<100 válidas/contexto), leitura diagnóstica"
        apdex_condition, apdex_label = _apdex_condition(apdex_rows, small_group_only=small_group_only)
    elif apdex_run is not None and not bool(apdex_run["enabled"]):
        apdex_value, apdex_detail = "DESABILITADO", "Medição opcional não executada"
        apdex_condition, apdex_label = "neutral", "Não executado"
    else:
        apdex_value, apdex_detail = "NÃO DISPONÍVEL", "Sem grupo Apdex materializado"
        apdex_condition, apdex_label = "neutral", "Sem dados suficientes"
    apdex_link = "apdex.html" if (report_dir / "apdex.html").is_file() else "web-performance.html"
    cards.append(_indicator_card(
        "Synthetic Navigation Apdex", apdex_value, apdex_detail, apdex_link,
        "Apdex Technical Specification", apdex_condition, apdex_label,
    ))

    return (
        _DASHBOARD_START
        + "<section id='executive-indicator-dashboard' class='panel'><div class='kicker'>Dashboard executivo</div><h2>Resultados finais por indicador</h2><p class='intro'>O painel resume resultados sem misturar metodologias. A condição visual é calculada separadamente para cada indicador; no Lighthouse, a subdivisão de valores Poor abaixo de 25 como crítico é somente severidade visual do RASAi e não uma quarta faixa oficial do Lighthouse. Nenhum indicador externo é convertido no SARI-001.</p>"
        + f"<div class='grid indicator-grid'>{''.join(cards)}</div></section>"
        + _DASHBOARD_END
    )


def _indicator_card(
    title: str,
    value: str,
    detail: str,
    href: str,
    source: str,
    condition: str = "neutral",
    condition_label: str = "Informativo",
) -> str:
    value_markup = _indicator_value_markup(value)
    return (
        f"<article class='ref-card indicator-card condition-{escape(condition, quote=True)}'>"
        f"<div class='kicker'>{escape(source)}</div><h3>{escape(title)}</h3>"
        f"{value_markup}<span class='indicator-condition'>{escape(condition_label)}</span>"
        f"<p class='intro'>{escape(detail)}</p><p><a href='{escape(href, quote=True)}'>Analisar detalhes</a></p></article>"
    )


def _indicator_value_markup(value: str) -> str:
    parts = [item.strip() for item in value.split(" - ") if item.strip()]
    rendered: list[str] = []
    for part in parts:
        match = re.fullmatch(r"(Mobile|Desktop|Global)\s+(.+)", part)
        if match is None:
            rendered = []
            break
        rendered.append(
            "<span class='indicator-device'>"
            f"<small>{escape(match.group(1))}</small><strong>{escape(match.group(2))}</strong></span>"
        )
    if rendered:
        return "<div class='indicator-values'>" + "".join(rendered) + "</div>"
    return f"<div class='score-number indicator-score'>{escape(value)}</div>"


def _sari_condition(row: sqlite3.Row) -> tuple[str, str]:
    value = float(row["value"]) if row["value"] is not None else None
    consolidation = str(row["consolidation_status"] or "")
    confidence = str(row["confidence"] or "")
    if value is None or consolidation == "NOT_CONSOLIDATED" or confidence == "UNAVAILABLE":
        return "critical", "Crítico - não consolidado"
    if value < 40:
        return "critical", "Crítico"
    if value < 75:
        return "below", "Abaixo do esperado"
    if consolidation != "CONSOLIDATED" or confidence == "LOW":
        return "near", "Quase no esperado - medição parcial"
    return "expected", "Dentro do esperado"


def _cwv_condition(passed: int, total: int) -> tuple[str, str]:
    if total <= 0:
        return "neutral", "Sem dados suficientes"
    if passed == total:
        return "expected", "Dentro do esperado"
    if passed == 0:
        return "critical", "Crítico - nenhum contexto aprovado"
    ratio = passed / total
    return ("near", "Quase no esperado") if ratio >= 0.75 else ("below", "Abaixo do esperado")


def _numeric_values(rows: list[sqlite3.Row], column: str) -> list[float]:
    output: list[float] = []
    for row in rows:
        try:
            value = row[column]
        except (IndexError, KeyError):
            continue
        if value is not None:
            output.append(float(value))
    return output


def _lighthouse_condition(rows: list[sqlite3.Row], column: str) -> tuple[str, str]:
    values = _numeric_values(rows, column)
    if not values:
        return "neutral", "Sem dados suficientes"
    worst = min(values)
    if worst >= 90:
        return "expected", "Dentro do esperado - Good"
    if worst >= 50:
        return "near", "Quase no esperado - Needs Improvement"
    if worst >= 25:
        return "below", "Abaixo do esperado - Poor"
    return "critical", "Crítico - Poor (severidade visual RASAi)"


def _apdex_condition(rows: list[sqlite3.Row], *, small_group_only: bool) -> tuple[str, str]:
    values = _numeric_values(rows, "apdex_score")
    if not values:
        return "neutral", "Sem dados suficientes"
    worst = min(values)
    if worst >= 0.85:
        condition = ("expected", "Dentro do esperado - Good/Excellent")
    elif worst >= 0.70:
        condition = ("near", "Quase no esperado - Fair")
    elif worst >= 0.50:
        condition = ("below", "Abaixo do esperado - Poor")
    else:
        condition = ("critical", "Crítico - Unacceptable")
    if small_group_only and condition[0] == "expected":
        return "near", "Quase no esperado - grupo pequeno"
    return condition
'''
replace_regex(
    "src/rasai/rasai_readiness_reporting.py",
    r"def _dashboard\(data: dict\[str, Any\], report_dir: Path\) -> str:.*?(?=def _device_ranges\()",
    new_dashboard + "\n\n",
)

# Dashboard-specific presentation CSS; score values do not wrap through the middle.
replace_exact(
    "src/rasai/report_semantics.py",
    ".apdex-threshold-note{margin-top:12px}.apdex-threshold-note code{font-weight:650}.apdex-card.apdex-conflict{box-shadow:0 7px 20px rgba(182,138,80,.08),inset 3px 0 0 rgba(182,138,80,.72)}\n",
    ".apdex-threshold-note{margin-top:12px}.apdex-threshold-note code{font-weight:650}.apdex-card.apdex-conflict{box-shadow:0 7px 20px rgba(182,138,80,.08),inset 3px 0 0 rgba(182,138,80,.72)}\n"
    ".indicator-grid{grid-template-columns:repeat(auto-fit,minmax(280px,1fr));align-items:stretch}.indicator-card{display:flex;flex-direction:column;min-width:0}.indicator-card h3{font-size:1rem;line-height:1.25;min-height:2.5em}.indicator-card .intro{font-size:.88rem}.indicator-score{font-size:clamp(1.35rem,2.3vw,2rem)!important;line-height:1.08;overflow-wrap:normal;word-break:normal;white-space:nowrap}.indicator-values{display:flex;gap:12px;flex-wrap:wrap;margin:.45rem 0}.indicator-device{display:flex;flex-direction:column;gap:2px;min-width:92px}.indicator-device small{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.04em}.indicator-device strong{font-size:clamp(1.25rem,2vw,1.8rem);line-height:1.05;white-space:nowrap}.indicator-condition{display:inline-flex;width:max-content;max-width:100%;margin:.35rem 0 .2rem;padding:3px 8px;border-radius:999px;font-size:.7rem;font-weight:760;line-height:1.35}.indicator-card.condition-expected{border-top:4px solid var(--green);background:var(--soft-green)}.indicator-card.condition-near{border-top:4px solid var(--amber);background:var(--soft-amber)}.indicator-card.condition-below{border-top:4px solid #a96f38;background:rgba(169,111,56,.08)}.indicator-card.condition-critical{border-top:4px solid var(--red);background:var(--soft-red)}.indicator-card.condition-neutral{border-top:4px solid var(--blue);background:var(--soft-blue)}.condition-expected .indicator-condition{background:rgba(95,150,116,.16);color:#3f7452}.condition-near .indicator-condition{background:rgba(182,138,80,.18);color:#855f2c}.condition-below .indicator-condition{background:rgba(169,111,56,.17);color:#815126}.condition-critical .indicator-condition{background:rgba(191,111,112,.18);color:#98494c}.condition-neutral .indicator-condition{background:rgba(101,127,198,.15);color:#4d65a0}\n",
)

# Existing semantic layer is deliberately label-whitelisted: metadata/counts stay neutral.
# Add a regression-friendly comment making this boundary explicit.
replace_exact(
    "src/rasai/report_semantics.py",
    "def _metric_state(page_name: str, label: str, value: str) -> tuple[str | None, str, bool]:\n",
    "def _metric_state(page_name: str, label: str, value: str) -> tuple[str | None, str, bool]:\n    # Only metric labels explicitly listed below receive result semantics. Metadata, provenance,\n    # scopes, sources and integrity counters must remain neutral unless a specific contract says otherwise.\n",
)

# ---------------------------------------------------------------------------
# 2. M20 content remediation: request-bounded IDs + precise contract codes.
# ---------------------------------------------------------------------------
replace_exact(
    "src/rasai/m20_ai.py",
    'CONTENT_REMEDIATION_CONTRACT_VERSION = "M20-CONTENT-REMEDIATION-v2"',
    'CONTENT_REMEDIATION_CONTRACT_VERSION = "M20-CONTENT-REMEDIATION-v3"',
)

schema_and_validation = r'''class ContentRemediationContractError(ValueError):
    """Safe, persisted M20 contract failure with no provider response leakage."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def content_remediation_schema(request: ContentRemediationRequest | None = None) -> dict[str, Any]:
    finding_id_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    evidence_id_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if request is not None:
        finding_ids = sorted(request.allowed_finding_ids)
        evidence_ids = sorted({item for values in request.evidence_by_finding.values() for item in values})
        if finding_ids:
            finding_id_schema["enum"] = finding_ids
        if evidence_ids:
            evidence_id_schema["enum"] = evidence_ids
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "finding_id": finding_id_schema,
                        "objective": {"type": "string", "minLength": 1, "maxLength": 1200},
                        "target_location": {"type": "string", "minLength": 1, "maxLength": 700},
                        "proposed_text": {"type": "string", "minLength": 1, "maxLength": 8000},
                        "evidence_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": evidence_id_schema,
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "review_note": {"type": "string", "minLength": 1, "maxLength": 1200},
                    },
                    "required": [
                        "finding_id", "objective", "target_location", "proposed_text",
                        "evidence_ids", "confidence", "review_note",
                    ],
                },
            }
        },
        "required": ["suggestions"],
    }


def _validate_response(payload: Any, request: ContentRemediationRequest) -> tuple[ContentSuggestion, ...]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("suggestions"), list):
        raise ContentRemediationContractError("M20_INVALID_ROOT_SCHEMA", "M20 response has invalid root schema")
    evidence_by_finding = request.evidence_by_finding
    source_corpus = request.source_corpus.casefold()
    seen: set[str] = set()
    output: list[ContentSuggestion] = []
    for raw in payload["suggestions"]:
        if not isinstance(raw, Mapping):
            raise ContentRemediationContractError("M20_INVALID_SUGGESTION_ITEM", "M20 suggestion item must be an object")
        finding_id = str(raw.get("finding_id") or "").strip()
        if finding_id not in request.allowed_finding_ids:
            raise ContentRemediationContractError("M20_INVALID_FINDING_REFERENCE", "M20 suggestion references unknown finding")
        if finding_id in seen:
            raise ContentRemediationContractError("M20_DUPLICATE_FINDING_REFERENCE", "M20 suggestion duplicates finding")
        seen.add(finding_id)
        evidence_raw = raw.get("evidence_ids")
        if not isinstance(evidence_raw, list) or not evidence_raw:
            raise ContentRemediationContractError("M20_MISSING_EVIDENCE_IDS", "M20 suggestion requires evidence_ids")
        evidence_ids = tuple(str(item).strip() for item in evidence_raw if str(item).strip())
        if not evidence_ids or not set(evidence_ids).issubset(evidence_by_finding[finding_id]):
            raise ContentRemediationContractError("M20_EVIDENCE_OUTSIDE_FINDING", "M20 suggestion references evidence outside its finding")
        proposed_text = str(raw.get("proposed_text") or "").strip()
        objective = str(raw.get("objective") or "").strip()
        target_location = str(raw.get("target_location") or "").strip()
        review_note = str(raw.get("review_note") or "").strip()
        if not proposed_text or not objective or not target_location or not review_note:
            raise ContentRemediationContractError("M20_EMPTY_REQUIRED_TEXT", "M20 suggestion contains empty required text")
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ContentRemediationContractError("M20_INVALID_CONFIDENCE", "M20 confidence is not numeric") from exc
        if not 0 <= confidence <= 1:
            raise ContentRemediationContractError("M20_INVALID_CONFIDENCE", "M20 confidence must be between 0 and 1")
        if any(token.casefold() not in source_corpus for token in _NUMERIC_TOKEN.findall(proposed_text)):
            raise ContentRemediationContractError("M20_UNSUPPORTED_NUMERIC_CLAIM", "M20 suggestion introduces unsupported numeric claim")
        output.append(ContentSuggestion(
            finding_id=finding_id,
            objective=objective,
            target_location=target_location,
            proposed_text=proposed_text,
            evidence_ids=evidence_ids,
            confidence=confidence,
            review_note=review_note,
        ))
    return tuple(output)
'''
replace_regex(
    "src/rasai/m20_ai.py",
    r"def content_remediation_schema\(\) -> dict\[str, Any\]:.*?(?=class ContentRemediationProvider:)",
    schema_and_validation + "\n\n",
)
replace_exact(
    "src/rasai/m20_ai.py",
    "        schema = content_remediation_schema()\n",
    "        schema = content_remediation_schema(request)\n",
)
replace_exact(
    "src/rasai/m20_ai.py",
    "        try:\n            suggestions = _validate_response(_extract_json_payload(dict(raw)), request)\n        except Exception as exc:\n            return self._failure(request, started_at, started_perf, summary, payload_hash, ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__), AttemptStatus.CONTRACT_ERROR, usage=usage)\n",
    "        try:\n            suggestions = _validate_response(_extract_json_payload(dict(raw)), request)\n        except ContentRemediationContractError as exc:\n            return self._failure(\n                request, started_at, started_perf, summary, payload_hash,\n                ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__, error_code=exc.code),\n                AttemptStatus.CONTRACT_ERROR, usage=usage,\n            )\n        except Exception as exc:\n            return self._failure(\n                request, started_at, started_perf, summary, payload_hash,\n                ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__, error_code=\"M20_UNEXPECTED_CONTRACT_ERROR\"),\n                AttemptStatus.CONTRACT_ERROR, usage=usage,\n            )\n",
)
replace_exact(
    "src/rasai/provider_extensions_m20.py",
    "    ContentRemediationRequest,\n    ContentRemediationResult,\n",
    "    ContentRemediationRequest,\n    ContentRemediationResult,\n    ContentRemediationContractError,\n",
)
replace_exact(
    "src/rasai/provider_extensions_m20.py",
    "        schema = content_remediation_schema()\n",
    "        schema = content_remediation_schema(request)\n",
)
replace_exact(
    "src/rasai/provider_extensions_m20.py",
    "        try:\n            suggestions = _validate_response(self.base._extract_payload(raw), request)\n        except Exception as exc:\n            return self._failure(\n                request, started_at, started_perf, summary, payload_hash,\n                ProviderDiagnostic(\n                    ProviderErrorClass.CONTRACT_ERROR,\n                    error_type=type(exc).__name__,\n                ),\n                AttemptStatus.CONTRACT_ERROR,\n                usage=usage,\n            )\n",
    "        try:\n            suggestions = _validate_response(self.base._extract_payload(raw), request)\n        except ContentRemediationContractError as exc:\n            return self._failure(\n                request, started_at, started_perf, summary, payload_hash,\n                ProviderDiagnostic(\n                    ProviderErrorClass.CONTRACT_ERROR,\n                    error_type=type(exc).__name__,\n                    error_code=exc.code,\n                ),\n                AttemptStatus.CONTRACT_ERROR,\n                usage=usage,\n            )\n        except Exception as exc:\n            return self._failure(\n                request, started_at, started_perf, summary, payload_hash,\n                ProviderDiagnostic(\n                    ProviderErrorClass.CONTRACT_ERROR,\n                    error_type=type(exc).__name__,\n                    error_code=\"M20_UNEXPECTED_CONTRACT_ERROR\",\n                ),\n                AttemptStatus.CONTRACT_ERROR,\n                usage=usage,\n            )\n",
)

# M20 report: make content AI activation and degraded contract failures explicit.
replace_exact(
    "src/rasai/m20_reporting.py",
    "    context_html = _context_panel(data[\"context\"])\n",
    "    context_html = _context_panel(data[\"context\"])\n    attempt_error = _attempt_error_summary(data[\"attempts\"])\n",
)
replace_regex(
    "src/rasai/m20_reporting.py",
    r"    if not enabled:\n        ai_notice = .*?\n\n    shortcuts =",
    '''    if not enabled:\n        ai_notice = "<div class='notice'><strong>IA de conteúdo desabilitada.</strong> Ative com <code>RASAI_AI_CONTENT_REMEDIATION=true</code> ou <code>--ai-content-remediation</code>. A revisão JSON-LD determinística permanece independente.</div>"\n    elif run_status == "NOT_CONFIGURED":\n        ai_notice = "<div class='notice warn'><strong>IA de conteúdo foi habilitada, mas não havia provider saudável/configurado.</strong> A variável <code>RASAI_AI_CONTENT_REMEDIATION</code> controla esta finalidade; ela é independente da IA técnica de crawling.</div>"\n    elif run_status == "DEGRADED":\n        suffix = f" Motivo persistido: <code>{escape(attempt_error)}</code>." if attempt_error else ""\n        ai_notice = "<div class='notice warn'><strong>IA de conteúdo habilitada e chamada, mas o resultado foi degradado/rejeitado.</strong> Isso não significa que a IA estava desabilitada." + suffix + " Consulte a telemetria abaixo; nenhuma sugestão rejeitada altera score ou finding.</div>"\n    else:\n        ai_notice = "<div class='notice warn'><strong>Conteúdo sugerido é advisory.</strong> Esta finalidade é controlada por <code>RASAI_AI_CONTENT_REMEDIATION</code>, não por <code>RASAI_AI_TECHNICAL_REMEDIATION</code>. Não altera score/findings e requer validação humana.</div>"\n\n    shortcuts =''',
)
replace_exact(
    "src/rasai/m20_reporting.py",
    "{_metric('Remediação por IA','Habilitada' if enabled else 'Desabilitada')}",
    "{_metric('IA de conteúdo','Habilitada' if enabled else 'Desabilitada')}",
)
replace_exact(
    "src/rasai/m20_reporting.py",
    "def _context_panel(record: tuple[Any, dict[str, Any]] | None) -> str:\n",
    '''def _attempt_error_summary(attempts: list[sqlite3.Row]) -> str:\n    for row in reversed(attempts):\n        values = []\n        for key in ("error_class", "error_type", "error_code"):\n            try:\n                value = row[key]\n            except (IndexError, KeyError):\n                value = None\n            if value not in (None, ""):\n                values.append(str(value))\n        if values:\n            return ":".join(values)\n    return ""\n\n\ndef _context_panel(record: tuple[Any, dict[str, Any]] | None) -> str:\n''',
)
replace_exact(
    "src/rasai/m20_reporting.py",
    "Telemetria desta finalidade é separada da análise semântica Análise semântica por IA, roteamento e telemetria. O recurso é default OFF e não executa chamadas apenas porque Confidence está baixa.",
    "Telemetria desta finalidade é separada da análise semântica e da IA técnica de crawling. O recurso é controlado por RASAI_AI_CONTENT_REMEDIATION, é default OFF e não executa chamadas apenas porque Confidence está baixa.",
)

# M24 report: clarify score boundary and the independent technical-AI toggle.
replace_exact(
    "src/rasai/m24_reporting.py",
    "<header class='hero'><div class='eyebrow'>Rastreamento, descoberta e acesso de crawlers · diagnóstico técnico não-scoring</div>",
    "<header class='hero'><div class='eyebrow'>Rastreamento, descoberta e acesso de crawlers · diagnóstico técnico complementar</div>",
)
replace_exact(
    "src/rasai/m24_reporting.py",
    "<p class='lead'>Diagnóstico determinístico de robots.txt, sitemaps/feeds, coerência de descoberta e controles de crawlers. Esta página não altera SCORE-GEO-004, SARI-001, Coverage, Confidence ou Consolidation.</p>",
    "<p class='lead'>Diagnóstico aprofundado de robots.txt, sitemaps/feeds, coerência de descoberta e controles de crawlers. Os diagnósticos M24 desta página são advisory/non-scoring; porém as evidências determinísticas básicas de sitemap, robots.txt e acesso de crawlers já alimentam BR-GEO-003, BR-GEO-017 e BR-GEO-018 no SCORE-GEO-004.</p>",
)
replace_exact(
    "src/rasai/m24_reporting.py",
    '{_metric("Impacto no score", "NENHUM")}',
    '{_metric("Impacto M24", "NENHUM direto")}',
)
replace_exact(
    "src/rasai/m24_reporting.py",
    "<p class='intro'>A IA recebe apenas diagnósticos/evidence IDs Rastreamento, descoberta e acesso de crawlers persistidos. Ela não pode criar fatos, decidir política de treinamento do publisher nem alterar scoring. Revisão humana permanece obrigatória.</p>",
    "<p class='intro'>A IA técnica desta página é controlada por <code>RASAI_AI_TECHNICAL_REMEDIATION</code>, independente de <code>RASAI_AI_CONTENT_REMEDIATION</code>. Ela recebe apenas diagnósticos/evidence IDs persistidos, não pode criar fatos nem elevar Confidence por opinião. Qualquer aumento de Confidence só pode ocorrer no pipeline de scoring quando uma regra aplicável passa a ter evidência válida; a remediação M24 permanece advisory e não altera scoring.</p>",
)

# ---------------------------------------------------------------------------
# 3. Apdex: errors/integrity + Web Performance correlation + T sensitivity.
# ---------------------------------------------------------------------------
replace_exact(
    "src/rasai/m23_reporting.py",
    "    final_badge = \"GRUPO FINAL\" if bool(row[\"final_group\"]) else \"GRUPO PEQUENO *\"\n",
    "    final_badge = \"GRUPO FINAL\" if bool(row[\"final_group\"]) else \"GRUPO PEQUENO *\"\n    sensitivity = _apdex_sensitivity_table(valid_samples, float(row[\"threshold_seconds\"]))\n    web_link = \"<p><a href='web-performance.html'>Revisar Core Web Vitals e diagnósticos Web Performance deste contexto →</a></p>\" if web is not None else \"\"\n",
)
replace_exact(
    "src/rasai/m23_reporting.py",
    "<p class='intro'><strong>Perfil sintético:</strong> {escape(profile_text)}</p><div class='analysis-grid'>{''.join(f'<div class=\"notice\"><strong>{escape(title)}</strong><span>{escape(text)}</span></div>' for title, text in diagnostics)}</div><details>",
    "<p class='intro'><strong>Perfil sintético:</strong> {escape(profile_text)}</p><h4>Sensibilidade ao threshold T</h4>{sensitivity}<div class='analysis-grid'>{''.join(f'<div class=\"notice\"><strong>{escape(title)}</strong><span>{escape(text)}</span></div>' for title, text in diagnostics)}</div>{web_link}<details>",
)

new_diagnostics = r'''def _diagnostic_notes(row: sqlite3.Row, web: sqlite3.Row | None) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    valid = max(int(row["valid_samples"]), 1)
    frustrated_share = int(row["frustrated_count"]) / valid
    tolerating_share = int(row["tolerating_count"]) / valid
    cv = float(row["coefficient_of_variation"]) if row["coefficient_of_variation"] is not None else None
    median = float(row["median_ms"]) if row["median_ms"] is not None else None
    p95 = float(row["p95_ms"]) if row["p95_ms"] is not None else None
    trend = float(row["trend_percent"]) if row["trend_percent"] is not None else None
    application_errors = int(row["application_error_count"] or 0)
    timeouts = int(row["timeout_count"] or 0)
    navigation_errors = int(row["navigation_error_count"] or 0)
    invalid = int(row["invalid_samples"] or 0)
    notes.append((
        "Erros e integridade da execução",
        f"application errors={application_errors}; timeouts={timeouts}; navigation errors={navigation_errors}; amostras inválidas/excluídas={invalid}. "
        + ("Nenhum erro de aplicação/navegação/timeout foi observado; a nota decorre da distribuição temporal em relação a T." if application_errors + timeouts + navigation_errors == 0 else "Erros válidos da aplicação/navegação são tratados como Frustrated; falhas da ferramenta ficam fora do denominador."),
    ))
    if application_errors:
        notes.append(("Erros da aplicação", f"{application_errors} amostra(s) retornaram erro HTTP da aplicação e foram classificadas como Frustrated. Investigue disponibilidade, redirects e respostas 4xx/5xx."))
    if timeouts:
        notes.append(("Timeouts", f"{timeouts} amostra(s) ultrapassaram o timeout configurado. Investigue cauda longa, recursos bloqueantes, backend e dependências externas."))
    if navigation_errors:
        notes.append(("Erros de navegação", f"{navigation_errors} amostra(s) tiveram erro de navegação com perfil aplicado e foram classificadas como Frustrated. Verifique conectividade, redirects, TLS e falhas de carregamento."))
    if invalid:
        notes.append(("Amostras excluídas", f"{invalid} tentativa(s) foram excluídas do denominador por falha/integridade da ferramenta ou perfil. Elas não devem ser confundidas com erro do website."))
    if frustrated_share >= 0.10:
        notes.append(("Fração Frustrated", f"{frustrated_share:.1%} das amostras válidas ficaram em Frustrated. Priorize reduzir a cauda e eliminar falhas antes de otimizações marginais."))
    elif tolerating_share >= 0.20:
        notes.append(("Fração Tolerating", f"{tolerating_share:.1%} das amostras ficaram entre T e 4T. Há oportunidade de deslocar a distribuição para Satisfied."))
    if cv is not None and cv >= 0.25:
        notes.append(("Variabilidade", f"Coeficiente de variação {cv:.1%}. O comportamento é instável; investigue backend, terceiros, CDN/cache de origem e contenção de recursos. O indicador não identifica sozinho a causa."))
    if median and p95 and p95 >= median * 2:
        notes.append(("Cauda longa", f"p95 ({p95:.0f} ms) é pelo menos 2× a mediana ({median:.0f} ms). A média pode ocultar uma parcela relevante de experiências lentas."))
    if trend is not None and trend >= 15:
        notes.append(("Degradação ao longo da sequência", f"A média da segunda metade ficou {trend:.1f}% acima da primeira. Investigue throttling, saturação ou variabilidade temporal; não atribua causa sem evidência adicional."))
    if web is not None:
        def web_value(name: str):
            try:
                return web[name]
            except (IndexError, KeyError):
                return None
        cwv = str(web_value("cwv_assessment") or "-")
        perf = web_value("performance_score")
        lcp = web_value("lcp_p75_ms")
        inp = web_value("inp_p75_ms")
        cls = web_value("cls_p75")
        if cwv == "FAIL" or (perf is not None and float(perf) < 90):
            pieces = [f"CWV={cwv}"]
            if perf is not None:
                pieces.append(f"Lighthouse Performance={float(perf):.0f}/100")
            if lcp is not None:
                pieces.append(f"LCP p75={float(lcp):.0f} ms")
            if inp is not None:
                pieces.append(f"INP p75={float(inp):.0f} ms")
            if cls is not None:
                pieces.append(f"CLS p75={float(cls):.3f}")
            notes.append(("Revisar Web Performance", "; ".join(pieces) + ". Estes sinais não são os mesmos erros do Apdex e não entram na sua fórmula; use a página Web Performance para diagnóstico causal."))
    return notes


def _apdex_sensitivity_table(samples: list[sqlite3.Row], threshold: float) -> str:
    if threshold <= 0 or not samples:
        return "<p class='intro'>Sensibilidade indisponível sem T e amostras válidas.</p>"
    rows: list[str] = []
    usable = 0
    for multiplier in (0.80, 0.90, 1.00, 1.10, 1.20):
        t_seconds = threshold * multiplier
        satisfied = tolerating = frustrated = 0
        for sample in samples:
            status = str(sample["status"] or "").upper()
            duration = sample["duration_ms"]
            if status in {"APPLICATION_ERROR", "TIMEOUT", "NAVIGATION_ERROR"}:
                frustrated += 1
                continue
            if duration is None:
                continue
            seconds = float(duration) / 1000.0
            if seconds <= t_seconds:
                satisfied += 1
            elif seconds <= 4 * t_seconds:
                tolerating += 1
            else:
                frustrated += 1
        total = satisfied + tolerating + frustrated
        usable = max(usable, total)
        score = (satisfied + 0.5 * tolerating) / total if total else None
        marker = " (configurado)" if abs(multiplier - 1.0) < 1e-9 else ""
        score_text = "-" if score is None else f"{score:.3f}"
        rows.append(
            f"<tr{' class=\"configured-threshold\"' if marker else ''}><td>{t_seconds:.3g} s{marker}</td><td>{satisfied}/{tolerating}/{frustrated}</td><td><strong>{score_text}</strong></td></tr>"
        )
    if not usable:
        return "<p class='intro'>Sensibilidade indisponível sem duração válida.</p>"
    return (
        "<div class='notice'><strong>Diagnóstico de sensibilidade, não calibração por resultado.</strong> "
        "A tabela recalcula somente estas amostras em T±10%/20% para mostrar quanto o índice depende do threshold. Escolha T pelo SLO/KPM/Dynatrace comparável, nunca pelo Apdex que deseja obter.</div>"
        "<div class='table-wrap'><table><thead><tr><th>T hipotético</th><th>S/T/F</th><th>Apdex</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div>"
    )


'''
replace_regex(
    "src/rasai/m23_reporting.py",
    r"def _diagnostic_notes\(row: sqlite3.Row, web: sqlite3.Row \| None\) -> list\[tuple\[str, str\]\]:.*?(?=def _distribution_bar\()",
    new_diagnostics,
)

# ---------------------------------------------------------------------------
# 4. Console: direct CrUX API versus CrUX embedded in PageSpeed response.
# ---------------------------------------------------------------------------
replace_exact(
    "src/rasai/console_collection.py",
    "    crux_successes: int\n    accessibility_requested: bool\n",
    "    crux_successes: int\n    crux_via_pagespeed: int\n    accessibility_requested: bool\n",
)
replace_exact(
    "src/rasai/console_collection.py",
    '            observations = list(db.execute("SELECT accessibility_score,pagespeed_artifact_reference,error_summary FROM web_performance_observations").fetchall())\n',
    '            observations = list(db.execute("SELECT * FROM web_performance_observations").fetchall())\n',
)
replace_exact(
    "src/rasai/console_collection.py",
    "    crux = [row for row in attempts if str(row[\"service\"]).upper() == \"CRUX_API\"]\n    return CollectionCoverage(\n",
    "    crux = [row for row in attempts if str(row[\"service\"]).upper() == \"CRUX_API\"]\n    crux_via_pagespeed = sum(\n        str(row[\"field_source\"] or \"\").upper() == \"PAGESPEED_CRUX\"\n        for row in observations\n        if \"field_source\" in row.keys()\n    )\n    return CollectionCoverage(\n",
)
replace_exact(
    "src/rasai/console_collection.py",
    "        crux_successes=sum(str(row[\"status\"]) == \"SUCCESS\" for row in crux),\n        accessibility_requested=a11y_requested,\n",
    "        crux_successes=sum(str(row[\"status\"]) == \"SUCCESS\" for row in crux),\n        crux_via_pagespeed=crux_via_pagespeed,\n        accessibility_requested=a11y_requested,\n",
)
replace_exact(
    "src/rasai/interactive_console.py",
    '        print(f"Web Performance     : {coverage.web_status} | PageSpeed {coverage.pagespeed_successes}/{coverage.pagespeed_attempts} | CrUX {coverage.crux_successes}/{coverage.crux_attempts}")\n',
    '        print(f"Web Performance     : {coverage.web_status} | PageSpeed {coverage.pagespeed_successes}/{coverage.pagespeed_attempts} | CrUX via PageSpeed {coverage.crux_via_pagespeed} | CrUX API direta {coverage.crux_successes}/{coverage.crux_attempts}")\n',
)

# ---------------------------------------------------------------------------
# 5. Documentation alignment.
# ---------------------------------------------------------------------------
append_section(
    "docs/SCORING_GUIDE.md",
    "<!-- rasai-confidence-ai-robots-20260908 -->",
    """
## Confidence, IA, robots.txt e sitemap

A `Confidence` do SARI-001 **não depende da presença de IA**. O runtime deriva Confidence de Coverage, completude das evidências avaliadas e erros de execução. Uma auditoria `NO_AI` pode atingir `MEDIUM` ou `HIGH` e consolidar normalmente quando as regras aplicáveis possuem evidência suficiente.

A IA pode, em regras explicitamente semânticas, ajudar a transformar uma avaliação que ficaria `UNKNOWN` em uma execução evidence-bound válida. Nesse caso a Confidence pode aumentar como consequência da Coverage/evidência adicional, nunca porque o provider declarou uma confiança subjetiva.

`robots.txt` e sitemap já participam do `SCORE-GEO-004` por regras determinísticas:

- `BR-GEO-003`: aquisição/interpretação de sitemap quando disponível;
- `BR-GEO-017`: interpretabilidade de `robots.txt` quando presente;
- `BR-GEO-018`: resolução independente de acesso por crawler.

A ausência isolada de `robots.txt` ou sitemap não recebe `FAIL` automático. Recurso existente porém inválido, não interpretável, inacessível ou com controle de crawler materialmente problemático pode produzir `WARNING`, `UNKNOWN` ou outra conclusão prevista na regra. Os diagnósticos aprofundados M24 permanecem advisory e não alteram diretamente Score/Coverage/Confidence.
""",
)
append_section(
    "docs/AI_GUIDE.md",
    "<!-- rasai-ai-purpose-separation-20260908 -->",
    """
## Separação das remediações por IA

As finalidades são independentes:

- `RASAI_AI_CONTENT_REMEDIATION`: sugestões textuais evidence-bound para findings de conteúdo elegíveis;
- `RASAI_AI_TECHNICAL_REMEDIATION`: explicação/remediação advisory de crawling, discovery, `robots.txt`, sitemap e controles de crawlers.

`DEGRADED` ou `CONTRACT_ERROR` significa que a finalidade foi habilitada e houve tentativa de provider, mas a resposta não foi aceita pelo contrato; isso não deve ser apresentado como "IA desabilitada". O M20 restringe `finding_id` e `evidence_ids` ao universo enviado e persiste reason codes seguros para falhas contratuais, sem armazenar conteúdo privado da resposta rejeitada.

A IA técnica M24 não possui autoridade para elevar Confidence ou SARI por julgamento. Ela permanece advisory; somente evidência válida incorporada por uma regra de scoring pode alterar Coverage/Confidence.
""",
)
append_section(
    "docs/SYNTHETIC_APDEX.md",
    "<!-- rasai-apdex-diagnostics-sensitivity-20260908 -->",
    """
## Diagnóstico de erros e sensibilidade ao T

`apdex.html` separa problemas da própria execução Synthetic Navigation Apdex de sinais relacionados de Web Performance. São mostrados application errors, timeouts, navigation errors, amostras inválidas/excluídas, fração Tolerating/Frustrated, variabilidade e cauda. Core Web Vitals/Lighthouse aparecem como correlação separada e não são duplicados nem entram na fórmula Apdex.

O relatório também apresenta uma análise de sensibilidade em torno do `T` configurado (`T ±10%/20%`) usando as mesmas amostras. Essa tabela é somente diagnóstico metodológico: não deve ser usada para escolher um threshold que produza a nota desejada. O `T` deve representar SLO/KPM ou a configuração comparável do APM/Dynatrace.
""",
)
append_section(
    "docs/INTERACTIVE_CONSOLE.md",
    "<!-- rasai-console-crux-ai-separation-20260908 -->",
    """
## Leitura de CrUX e finalidades de IA após a execução

No resumo persistido, o console diferencia:

- `CrUX via PageSpeed`: field data CrUX veio incorporado na resposta PageSpeed;
- `CrUX API direta`: quantidade de chamadas/sucessos feitos diretamente ao endpoint CrUX.

Assim, `CrUX API direta 0/0` não significa ausência de Core Web Vitals quando a observação persistida informa `PAGESPEED_CRUX`.

Também não confunda `RASAI_AI_CONTENT_REMEDIATION` com `RASAI_AI_TECHNICAL_REMEDIATION`: a primeira controla sugestões de conteúdo e a segunda controla remediação técnica advisory de crawling/discovery.
""",
)

# ---------------------------------------------------------------------------
# 6. Regression fixtures and dedicated tests.
# ---------------------------------------------------------------------------
replace_exact(
    "tests/test_rasai_readiness_reporting.py",
    "('W1','AUD-SARI','P1','MOBILE','PASS',0.81,0.94),\n              ('W2','AUD-SARI','P2','MOBILE','FAIL',0.88,0.97),\n              ('W3','AUD-SARI','P1','DESKTOP','PASS',0.95,1.00);",
    "('W1','AUD-SARI','P1','MOBILE','PASS',81.0,94.0),\n              ('W2','AUD-SARI','P2','MOBILE','FAIL',88.0,97.0),\n              ('W3','AUD-SARI','P1','DESKTOP','PASS',95.0,100.0);",
)
replace_exact(
    "tests/test_m20_content_remediation.py",
    '"M20-CONTENT-REMEDIATION-v2"',
    '"M20-CONTENT-REMEDIATION-v3"',
)

test_file = r'''from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

import pytest

from rasai.console_collection import load_collection_coverage
from rasai.m20_ai import (
    ContentEvidenceInput,
    ContentFindingInput,
    ContentRemediationContractError,
    ContentRemediationRequest,
    _validate_response,
    content_remediation_schema,
)
from rasai.m23_reporting import _apdex_sensitivity_table, _diagnostic_notes
from rasai.rasai_readiness_reporting import _dashboard
from rasai.scoring import _metadata


def _request() -> ContentRemediationRequest:
    return ContentRemediationRequest(
        snapshot_id="S1",
        page_id="P1",
        page_url="https://example.test/",
        device="mobile",
        title="Produto 2026",
        main_content="Texto observado 2026.",
        findings=(ContentFindingInput(
            finding_id="F1", rule_id="BR-GEO-041", title="Finding", severity="MEDIUM",
            expected_condition="cond", observed_value={"x": "y"}, evidence_ids=("E1",),
        ),),
        evidence=(ContentEvidenceInput("E1", "CONTENT", "snapshot", {"text": "2026"}),),
    )


def test_dashboard_uses_persisted_lighthouse_scale_and_metric_conditions(tmp_path: Path) -> None:
    data = {
        "scores": [{
            "device": "MOBILE", "dimension": "OVERALL_READINESS", "coverage": 0.963,
            "confidence": "LOW", "consolidation_status": "PARTIAL", "value": 90.7,
        }],
        "web": [{
            "device": "mobile", "cwv_assessment": "FAIL", "performance_score": 5.0,
            "accessibility_score": 78.0,
        }],
        "web_run": {"enabled": 1, "status": "SUCCESS"},
        "apdex_run": {"enabled": 1},
        "apdex": [{"device": "mobile", "apdex_score": 0.825, "final_group": 0}],
    }
    html = _dashboard(data, tmp_path)
    assert "500/100" not in html
    assert "7800/100" not in html
    assert "<strong>5/100</strong>" in html
    assert "<strong>78/100</strong>" in html
    assert "Crítico - nenhum contexto aprovado" in html
    assert "Crítico - Poor (severidade visual RASAi)" in html
    assert "Quase no esperado - Needs Improvement" in html
    assert "Quase no esperado - Fair" in html
    assert "Quase no esperado - medição parcial" in html


def test_m20_schema_is_bounded_to_request_ids() -> None:
    schema = content_remediation_schema(_request())
    props = schema["properties"]["suggestions"]["items"]["properties"]
    assert props["finding_id"]["enum"] == ["F1"]
    assert props["evidence_ids"]["items"]["enum"] == ["E1"]


def test_m20_contract_error_has_safe_specific_code() -> None:
    payload = {
        "suggestions": [{
            "finding_id": "F-UNKNOWN", "objective": "x", "target_location": "body",
            "proposed_text": "Texto 2026", "evidence_ids": ["E1"], "confidence": 0.8,
            "review_note": "review",
        }]
    }
    with pytest.raises(ContentRemediationContractError) as error:
        _validate_response(payload, _request())
    assert error.value.code == "M20_INVALID_FINDING_REFERENCE"


def test_console_distinguishes_crux_embedded_from_direct_api() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = sqlite3.connect(root / "audit.db")
        db.executescript("""
            CREATE TABLE web_performance_runs(
              audit_id TEXT, enabled INTEGER, status TEXT, reason TEXT, categories TEXT, updated_at TEXT
            );
            INSERT INTO web_performance_runs VALUES('A',1,'SUCCESS',NULL,'["performance","accessibility"]','2026-09-08T00:00:00Z');
            CREATE TABLE web_performance_attempts(service TEXT,status TEXT);
            INSERT INTO web_performance_attempts VALUES('PAGESPEED_INSIGHTS','SUCCESS');
            CREATE TABLE web_performance_observations(
              accessibility_score REAL,pagespeed_artifact_reference TEXT,error_summary TEXT,field_source TEXT
            );
            INSERT INTO web_performance_observations VALUES(78,'artifacts/psi.json',NULL,'PAGESPEED_CRUX');
        """)
        db.commit(); db.close()
        coverage = load_collection_coverage(root)
        assert coverage is not None
        assert coverage.pagespeed_successes == 1
        assert coverage.crux_via_pagespeed == 1
        assert coverage.crux_attempts == 0
        assert coverage.crux_successes == 0


def test_apdex_diagnostics_separate_execution_errors_from_web_signals() -> None:
    row = {
        "valid_samples": 20, "frustrated_count": 0, "tolerating_count": 7,
        "coefficient_of_variation": 0.316, "median_ms": 2451, "p95_ms": 3213,
        "trend_percent": 2.0, "application_error_count": 0, "timeout_count": 0,
        "navigation_error_count": 0, "invalid_samples": 0,
    }
    web = {
        "cwv_assessment": "FAIL", "performance_score": 5.0, "lcp_p75_ms": 3071,
        "inp_p75_ms": 390, "cls_p75": 0.9,
    }
    notes = dict(_diagnostic_notes(row, web))
    assert "Nenhum erro de aplicação/navegação/timeout" in notes["Erros e integridade da execução"]
    assert "Lighthouse Performance=5/100" in notes["Revisar Web Performance"]
    assert "não entram na sua fórmula" in notes["Revisar Web Performance"]


def test_apdex_sensitivity_marks_configured_threshold() -> None:
    samples = [
        {"status": "SUCCESS", "duration_ms": 2200, "classification": "SATISFIED"},
        {"status": "SUCCESS", "duration_ms": 2600, "classification": "TOLERATING"},
        {"status": "SUCCESS", "duration_ms": 6100, "classification": "TOLERATING"},
    ]
    html = _apdex_sensitivity_table(samples, 2.5)
    assert "2.5 s (configurado)" in html
    assert "não calibração por resultado" in html
    assert "T±10%/20%" not in html  # wording lives in docs; HTML shows concrete rows


def test_robots_and_sitemap_are_already_score_inputs_without_ai_dependency() -> None:
    for rule_id in ("BR-GEO-003", "BR-GEO-017", "BR-GEO-018"):
        metadata = _metadata(rule_id)
        assert metadata.dimension == "TECHNICAL_ACCESSIBILITY"
'''
save("tests/test_smoke_backlog_20260908.py", test_file)

print("RASAi consolidated smoke backlog patch applied successfully")
