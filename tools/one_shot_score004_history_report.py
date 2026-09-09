from __future__ import annotations

from pathlib import Path
import re
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def replace_section(path: str, heading: str, replacement: str) -> None:
    text = read(path)
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    if not pattern.search(text):
        raise RuntimeError(f"section not found in {path}: {heading}")
    write(path, pattern.sub(replacement.rstrip() + "\n\n", text, count=1))


def tracked_text_paths() -> list[Path]:
    suffixes = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".ini", ".cmd", ".ps1"}
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    paths: list[Path] = []
    for item in raw:
        if not item:
            continue
        path = ROOT / item.decode("utf-8")
        if path.is_file() and path.suffix.lower() in suffixes:
            paths.append(path)
    return paths


# The former unsupported/historical scoring fixture is intentionally removed.
# There is one scoring contract only; corruption/integrity guards may remain generic.
historical = "tests/test_historical_scoring_report_contract.py"
historical_text = read(historical)
historical_text = re.sub(
    r"(?ms)^def test_unsupported_scoring_version_is_not_promoted_or_rendered_as_public_history\(\) -> None:\n.*?(?=^def |\Z)",
    "",
    historical_text,
    count=1,
)
write(historical, historical_text)

# Normalize every concrete SCORE-GEO numeric identifier to the sole valid contract.
# The generic rejection regex itself is not a concrete version and remains a guard.
concrete_score = re.compile(r"SCORE-GEO-(?!004)\d{3}", re.I)
for path in tracked_text_paths():
    if path.name.startswith("one-shot-score004-history-report") or path.name == Path(__file__).name:
        continue
    text = path.read_text(encoding="utf-8")
    updated = concrete_score.sub("SCORE-GEO-004", text)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")

# Rename the old test file so the test suite itself no longer advertises a historical scoring contract.
old_test = ROOT / historical
new_test = ROOT / "tests/test_scoring_report_contract.py"
if old_test.exists():
    old_test.rename(new_test)

# Quality must consume the canonical scoring constant rather than another hard-coded version.
quality_path = "src/rasai/quality/analysis.py"
quality = read(quality_path)
if "from rasai.score_geo_004 import SCORING_VERSION" not in quality:
    quality = quality.replace(
        "from typing import Any\n",
        "from typing import Any\n\nfrom rasai.score_geo_004 import SCORING_VERSION\n",
        1,
    )
quality = quality.replace(
    'all(version == "SCORE-GEO-004" for version in versions)',
    "all(version == SCORING_VERSION for version in versions)",
)
write(quality_path, quality)

# Old absence assertions collapse into a contradiction once only 004 exists; remove them.
m26_path = "tests/test_m26_observed_generative_visibility.py"
m26 = read(m26_path)
m26 = re.sub(r'(?m)^\s*assert "SCORE-GEO-004" not in html\n', "", m26)
write(m26_path, m26)

# Replace a test that was named around an obsolete version with a generic current-only guard.
backlog_path = "tests/test_consolidated_backlog_regressions.py"
backlog = read(backlog_path)
if "import re\n" not in backlog:
    backlog = backlog.replace("from tempfile import TemporaryDirectory\n", "from tempfile import TemporaryDirectory\nimport re\n", 1)
backlog = backlog.replace(
    "def test_current_runtime_files_do_not_claim_score_geo_002(self) -> None:",
    "def test_current_runtime_files_expose_only_score_geo_004(self) -> None:",
)
backlog = backlog.replace(
    'self.assertNotIn("SCORE-GEO-004", (root / relative).read_text(encoding="utf-8"))',
    'self.assertIsNone(re.search(r"SCORE-GEO-(?!004)\\d{3}", (root / relative).read_text(encoding="utf-8")))',
)
write(backlog_path, backlog)

# Strengthen the public contract gate: no legacy exception and no non-004 concrete scoring ID anywhere.
gate_path = "src/rasai/public_contract_gate.py"
gate = read(gate_path)
if '"src/rasai/search_intelligence/history_reporting.py",' not in gate:
    gate = gate.replace(
        '    "src/rasai/search_intelligence/reporting.py",\n',
        '    "src/rasai/search_intelligence/reporting.py",\n    "src/rasai/search_intelligence/history_reporting.py",\n',
        1,
    )
for doc_line in (
    '    "docs/ENVIRONMENT_VARIABLES.md",\n',
    '    "docs/SERP_OBSERVATION.md",\n',
    '    "docs/COMPETITIVE_SEARCH_INTELLIGENCE.md",\n',
    '    "docs/COMPETITIVE_AI_INTELLIGENCE.md",\n',
):
    if doc_line.strip() not in gate:
        gate = gate.replace('    "docs/CLI_REFERENCE.md",\n', '    "docs/CLI_REFERENCE.md",\n' + doc_line, 1)

gate = re.sub(
    r'(?ms)    for obsolete in \("rasai scoring dataset", "rasai scoring calibrate"\):\n        for line in cli_doc\.splitlines\(\):\n            if obsolete in line and not re\.search\(r"hist\[oó\]ric\|legad\|003", line, re\.I\):\n                errors\.append\(f"CLI histórica anunciada como corrente: \{line\.strip\(\)\}"\)\n',
    '    for obsolete in ("rasai scoring dataset", "rasai scoring calibrate"):\n        if obsolete in cli_doc:\n            errors.append(f"CLI de scoring não suportada exposta na documentação: {obsolete}")\n',
    gate,
    count=1,
)

if "def _check_single_scoring_contract" not in gate:
    marker = "\n\ndef validate_public_contract(root: str | Path | None = None) -> tuple[str, ...]:\n"
    if marker not in gate:
        raise RuntimeError("public contract validation marker not found")
    extra = r'''

_SCORING_SCAN_SUFFIXES = frozenset({
    ".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".ini", ".cmd", ".ps1"
})


def _check_single_scoring_contract(root: Path, errors: list[str]) -> None:
    """Only SCORE-GEO-004 may be named as a concrete scoring contract."""
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SCORING_SCAN_SUFFIXES:
            continue
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = _OLD_VERSION_RE.search(text)
        if match:
            errors.append(
                f"contrato de scoring inválido {match.group(0)!r}: {path.relative_to(root)}; "
                f"somente {EXPECTED_SCORING_VERSION} é válido"
            )

    stale_reporting_claims = (
        "No Search Intelligence-specific HTML report is introduced yet",
        "no Search Intelligence-specific HTML report yet",
        "não há Search Intelligence HTML específico",
        "no dedicated historical HTML report is generated yet",
    )
    for relative in (
        "docs/SERP_OBSERVATION.md",
        "docs/COMPETITIVE_SEARCH_INTELLIGENCE.md",
        "docs/COMPETITIVE_AI_INTELLIGENCE.md",
        "docs/SEARCH_INTELLIGENCE_HISTORY.md",
    ):
        text = _read(root, relative)
        for claim in stale_reporting_claims:
            if claim in text:
                errors.append(f"documentação anuncia limitação já implementada em {relative}: {claim}")
'''
    gate = gate.replace(marker, textwrap.dedent(extra) + marker, 1)

if "_check_single_scoring_contract(repository, errors)" not in gate:
    gate = gate.replace(
        "    _check_generators(repository, errors)\n    return tuple(errors)\n",
        "    _check_generators(repository, errors)\n    _check_single_scoring_contract(repository, errors)\n    return tuple(errors)\n",
        1,
    )
write(gate_path, gate)

# New pair-level Search Intelligence historical HTML/manifest projection.
history_reporting = r'''"""Standalone HTML and manifest projection for Search Intelligence History."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
from typing import Any

from rasai.report_presentation import humanize_report_html
from rasai.score_geo_004 import SCORING_VERSION

from .history import SearchHistoryComparison, SearchHistoryEvent

FORMAT_VERSION = "RASAI-SEARCH-HISTORY-REPORT-001"


@dataclass(frozen=True, slots=True)
class SearchHistoryReportResult:
    report_dir: Path
    report_path: Path
    manifest_path: Path


def _event_dict(event: SearchHistoryEvent) -> dict[str, Any]:
    return {
        "context_key": event.context_key,
        "query": event.query,
        "status": event.status,
        "label": event.label,
        "before": event.before,
        "after": event.after,
        "delta": event.delta,
        "unit": event.unit,
        "note": event.note,
    }


def write_search_history_report(
    audits_root: str | Path,
    result: SearchHistoryComparison,
    *,
    report_root: str | Path | None = None,
    milestone_id: str | None = None,
    baseline_mode: str | None = None,
) -> SearchHistoryReportResult:
    """Materialize a deterministic standalone report without mutating either AUD."""
    root = Path(audits_root)
    output_root = Path(report_root) if report_root is not None else root / "search-history"
    material_payload = {
        "format": FORMAT_VERSION,
        "method": result.method,
        "baseline": result.baseline_audit_id,
        "current": result.current_audit_id,
        "milestone_id": milestone_id,
        "baseline_mode": baseline_mode,
        "events": [_event_dict(event) for event in result.events],
        "compatibility_notes": list(result.compatibility_notes),
    }
    material = json.dumps(
        material_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    report_dir = output_root / f"SH-{digest[:16].upper()}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.html"
    manifest_path = report_dir / "manifest.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    counts = Counter(event.status for event in result.events)
    manifest = {
        "format_version": FORMAT_VERSION,
        "generated_at": generated_at,
        "methodology": result.method,
        "baseline_audit_id": result.baseline_audit_id,
        "current_audit_id": result.current_audit_id,
        "milestone_id": milestone_id,
        "baseline_mode": baseline_mode,
        "comparable_contexts": result.comparable_contexts,
        "non_comparable_contexts": result.non_comparable_contexts,
        "compatibility_notes": list(result.compatibility_notes),
        "event_counts": dict(sorted(counts.items())),
        "events": [_event_dict(event) for event in result.events],
        "source_policy": "AUD-*/audit.db opened read-only; no Search/content/AI provider calls",
        "causality_policy": result.interpretation_policy,
        "scoring_boundary": f"Search History is non-scoring and does not modify SARI-001/{SCORING_VERSION}",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        _html(result, generated_at, counts, milestone_id=milestone_id, baseline_mode=baseline_mode),
        encoding="utf-8",
        newline="\n",
    )
    return SearchHistoryReportResult(report_dir, report_path, manifest_path)


def _status_label(status: str) -> str:
    return {
        "POSITION_IMPROVED": "Posição melhorou",
        "POSITION_REGRESSED": "Posição piorou",
        "POSITION_UNCHANGED": "Posição estável",
        "ENTERED_OBSERVED_DEPTH": "Entrou na profundidade observada",
        "LEFT_OBSERVED_DEPTH": "Saiu da profundidade observada",
        "OBSERVED_DEPTH_STATE_UNCHANGED": "Estado de profundidade estável",
        "DOMAIN_STATUS_CHANGED": "Estado do domínio mudou",
        "CONTENT_SIGNAL_CHANGED": "Sinal determinístico mudou",
        "CONTENT_VOLUME_CHANGED": "Volume observado mudou",
        "STRUCTURED_DATA_CHANGED": "Dados estruturados mudaram",
        "DETERMINISTIC_GAP_ADDED": "Gap determinístico adicionado",
        "DETERMINISTIC_GAP_RESOLVED": "Gap determinístico resolvido",
        "NEW_CONTEXT": "Novo contexto",
        "MISSING_CURRENT_CONTEXT": "Contexto ausente no atual",
        "NOT_COMPARABLE": "Não comparável",
    }.get(status, status)


def _status_class(status: str) -> str:
    if status in {"POSITION_IMPROVED", "ENTERED_OBSERVED_DEPTH", "DETERMINISTIC_GAP_RESOLVED"}:
        return "good"
    if status in {"POSITION_REGRESSED", "LEFT_OBSERVED_DEPTH", "DETERMINISTIC_GAP_ADDED"}:
        return "bad"
    if status in {"NOT_COMPARABLE", "NEW_CONTEXT", "MISSING_CURRENT_CONTEXT"}:
        return "warn"
    return "neutral"


def _value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "—"
    if isinstance(value, (tuple, list)):
        text = ", ".join(str(item) for item in value) or "—"
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    if not unit:
        return text
    unit_label = {"positions": "posições", "words": "palavras", "ratio": "proporção"}.get(unit, unit)
    return f"{text} {unit_label}"


def _delta(event: SearchHistoryEvent) -> str:
    if event.delta is None:
        return "—"
    prefix = "+" if event.delta > 0 else ""
    value = f"{event.delta:.4f}".rstrip("0").rstrip(".")
    unit = {"positions": "posições", "words": "palavras", "ratio": "proporção"}.get(event.unit or "", event.unit or "")
    return f"{prefix}{value} {unit}".strip()


def _event_row(event: SearchHistoryEvent) -> str:
    css = _status_class(event.status)
    return "".join((
        "<tr>",
        f"<td><span class='badge {css}'>{escape(_status_label(event.status))}</span></td>",
        f"<td>{escape(event.query)}</td>",
        f"<td>{escape(event.label)}</td>",
        f"<td>{escape(_value(event.before, event.unit))}</td>",
        f"<td>{escape(_value(event.after, event.unit))}</td>",
        f"<td>{escape(_delta(event))}</td>",
        f"<td>{escape(event.note or '—')}</td>",
        f"<td class='mono'>{escape(event.context_key)}</td>",
        "</tr>",
    ))


def _metric(label: str, value: Any, css: str = "") -> str:
    return f"<div class='metric {css}'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"


def _html(
    result: SearchHistoryComparison,
    generated_at: str,
    counts: Counter[str],
    *,
    milestone_id: str | None,
    baseline_mode: str | None,
) -> str:
    rows = "".join(_event_row(event) for event in result.events) or "<tr><td colspan='8'>Nenhum evento comparável materializado.</td></tr>"
    notes = "".join(f"<li>{escape(note)}</li>" for note in result.compatibility_notes) or "<li>Nenhuma limitação adicional de comparabilidade detectada.</li>"
    milestone = escape(milestone_id or "não informado")
    selection = escape(baseline_mode or "comparação direta")
    positive = counts.get("POSITION_IMPROVED", 0) + counts.get("ENTERED_OBSERVED_DEPTH", 0)
    negative = counts.get("POSITION_REGRESSED", 0) + counts.get("LEFT_OBSERVED_DEPTH", 0)
    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi · Histórico de Search Intelligence</title><style>{_CSS}</style></head><body><main>
<header class='hero'>
  <div class='eyebrow'>Search Intelligence History · {escape(result.method)}</div>
  <h1>Evolução observada de Search Intelligence</h1>
  <p>Comparação determinística e read-only entre duas auditorias. Variações de posição, conteúdo e gaps são observações temporais; proximidade com deploy ou alteração de conteúdo não demonstra causalidade.</p>
  <div class='metrics'>
    {_metric('Baseline', result.baseline_audit_id)}
    {_metric('Atual', result.current_audit_id)}
    {_metric('Contextos comparáveis', result.comparable_contexts, 'good' if result.comparable_contexts else 'neutral')}
    {_metric('Não comparáveis', result.non_comparable_contexts, 'warn' if result.non_comparable_contexts else 'neutral')}
    {_metric('Melhoras/entradas', positive, 'good')}
    {_metric('Pioras/saídas', negative, 'bad' if negative else 'neutral')}
  </div>
</header>
<section class='panel'><h2>Contexto da comparação</h2>
  <p><strong>Milestone/deploy:</strong> {milestone} · <strong>modo de seleção:</strong> {selection}</p>
  <p>Delta numérico de posição só existe quando query, engine, país, região, idioma, device, profundidade, domínio, provider, data mode e estado observacional são compatíveis.</p>
</section>
<section class='panel'><h2>Eventos observados</h2><div class='table-wrap'><table><thead><tr>
  <th>Estado</th><th>Query</th><th>Sinal</th><th>Antes</th><th>Depois</th><th>Delta</th><th>Interpretação</th><th>Contexto exato</th>
</tr></thead><tbody>{rows}</tbody></table></div></section>
<section class='panel'><h2>Comparabilidade e limitações</h2><ul>{notes}</ul>
  <ul><li><code>NOT_FOUND_WITHIN_DEPTH</code> nunca vira posição artificial.</li><li>Search é volátil e pode variar por tempo, localização, personalização e provider.</li><li>Word count é volume, não qualidade.</li><li>Mudança de JSON-LD é evidência de diferença, não recomendação automática.</li><li>Gaps determinísticos são correlacionais.</li></ul>
</section>
<section class='panel'><h2>Fronteira metodológica</h2>
  <p><strong>{escape(result.method)}</strong> não altera <strong>SARI-001</strong> nem <strong>{escape(SCORING_VERSION)}</strong>. O relatório não chama Search provider, páginas públicas ou IA e não regrava os <code>audit.db</code> fonte.</p>
  <p>{escape(result.interpretation_policy)}</p>
</section>
<footer>Gerado em {escape(generated_at)} · fonte: dois audit.db abertos read-only · RASAi Search Intelligence.</footer>
</main></body></html>"""
    return humanize_report_html(html, page_name="search-history-report.html")


_CSS = """
:root{--bg:#f5f7fa;--surface:#fff;--ink:#273449;--muted:#6d7786;--line:#e1e6ec;--good:#eaf5ee;--bad:#faecec;--warn:#faf3e7;--neutral:#eef2fb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1500px;margin:auto;padding:34px}.hero,.panel{background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:24px;margin-bottom:16px}.hero{box-shadow:0 8px 24px rgba(39,52,73,.05)}h1{font-size:30px;margin:.2rem 0 1rem}h2{font-size:20px;margin-top:0}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:9px;margin-top:18px}.metric{background:#f7f8fb;border-radius:6px;padding:11px}.metric span{display:block;color:var(--muted);font-size:12px}.metric strong{font-size:16px}.metric.good,.badge.good{background:var(--good)}.metric.bad,.badge.bad{background:var(--bad)}.metric.warn,.badge.warn{background:var(--warn)}.metric.neutral,.badge.neutral{background:var(--neutral)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse;min-width:1200px}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f7f8fb;position:sticky;top:0}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;max-width:360px;word-break:break-word}.badge{display:inline-block;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700}code{background:#f1f3f6;padding:1px 4px;border-radius:4px}footer{color:var(--muted);padding:12px 4px 24px}@media(max-width:700px){main{padding:16px}.hero,.panel{padding:17px}}
"""
'''
write("src/rasai/search_intelligence/history_reporting.py", history_reporting)

# CLI materializes standalone report/manifest after every successful comparison.
history_cli_path = "src/rasai/search_intelligence/history_cli.py"
history_cli = read(history_cli_path)
if "from .history_reporting import write_search_history_report" not in history_cli:
    history_cli = history_cli.replace(
        "from .history import compare_search_deployment_pair, compare_search_workspaces\n",
        "from .history import compare_search_deployment_pair, compare_search_workspaces\nfrom .history_reporting import write_search_history_report\n",
        1,
    )
if 'parser.add_argument("--report-root"' not in history_cli:
    history_cli = history_cli.replace(
        '    parser.add_argument("--json", dest="json_path", help="optional output JSON file")\n',
        '    parser.add_argument("--json", dest="json_path", help="optional output JSON file")\n    parser.add_argument("--report-root", help="optional root for SH-*; default <audits-root>/search-history")\n',
        1,
    )
old_tail = "        _write(_payload(result), args.json_path)\n        return 0\n"
new_tail = '''        report = write_search_history_report(
            args.audits_root,
            result,
            report_root=args.report_root,
            milestone_id=args.milestone if milestone else None,
            baseline_mode=args.baseline_mode if milestone else None,
        )
        payload = _payload(result)
        payload["report"] = {
            "report_dir": str(report.report_dir),
            "report_path": str(report.report_path),
            "manifest_path": str(report.manifest_path),
        }
        _write(payload, args.json_path)
        print(f"RASAi Search history report: {report.report_path}")
        return 0
'''
if old_tail in history_cli:
    history_cli = history_cli.replace(old_tail, new_tail, 1)
write(history_cli_path, history_cli)

# Extend history regression coverage.
history_test_path = "tests/test_search_intelligence_history.py"
history_test = read(history_test_path)
if "history_reporting import write_search_history_report" not in history_test:
    history_test = history_test.replace(
        "from rasai.search_intelligence.history import compare_search_workspaces\n",
        "from rasai.search_intelligence.history import compare_search_workspaces\nfrom rasai.search_intelligence.history_reporting import write_search_history_report\n",
        1,
    )
if 'reports = tmp_path / "reports"' not in history_test:
    history_test = history_test.replace(
        '    output = tmp_path / "history.json"\n',
        '    output = tmp_path / "history.json"\n    reports = tmp_path / "reports"\n',
        1,
    )
    history_test = history_test.replace(
        '            "--json",\n            str(output),\n',
        '            "--json",\n            str(output),\n            "--report-root",\n            str(reports),\n',
        1,
    )
    history_test = history_test.replace(
        '    assert payload["events"][0]["status"] == "POSITION_IMPROVED"\n    assert "SEARCH-HISTORY-001" in capsys.readouterr().out\n',
        '''    assert payload["events"][0]["status"] == "POSITION_IMPROVED"
    assert Path(payload["report"]["report_path"]).is_file()
    assert Path(payload["report"]["manifest_path"]).is_file()
    assert "SEARCH-HISTORY-001" in capsys.readouterr().out
''',
        1,
    )
if "def test_search_history_html_and_manifest_preserve_non_causal_boundary" not in history_test:
    history_test += r'''


def test_search_history_html_and_manifest_preserve_non_causal_boundary(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path, "baseline-report", position=8, domain_status="FOUND")
    current = _workspace(tmp_path, "current-report", position=4, domain_status="FOUND")
    result = compare_search_workspaces(baseline, current)

    output = write_search_history_report(
        tmp_path,
        result,
        report_root=tmp_path / "search-history",
        milestone_id="DEPLOY-2026-09",
        baseline_mode="AUTO",
    )

    html = output.report_path.read_text(encoding="utf-8")
    manifest = json.loads(output.manifest_path.read_text(encoding="utf-8"))
    assert output.report_dir.name.startswith("SH-")
    assert "Evolução observada de Search Intelligence" in html
    assert "não demonstra causalidade" in html
    assert "SCORE-GEO-004" in html
    assert manifest["methodology"] == "SEARCH-HISTORY-001"
    assert manifest["milestone_id"] == "DEPLOY-2026-09"
    assert manifest["baseline_mode"] == "AUTO"
    assert "read-only" in manifest["source_policy"]
    assert "SCORE-GEO-004" in manifest["scoring_boundary"]
'''
write(history_test_path, history_test)

# Documentation contract: no scoring legacy and current Search Intelligence surfaces.
docs_readme_path = "docs/README.md"
docs_readme = read(docs_readme_path)
docs_readme = re.sub(
    r"(?ms)^## Estado do produto\n.*?(?=^## Ordem de leitura recomendada)",
    """## Estado do produto

O RASAi está em **desenvolvimento e validação**. O único contrato de scoring válido no produto, no runtime, nos testes e na documentação é `SCORE-GEO-004`. Não há suporte documental ou operacional a versões anteriores de cálculo.

O baseline funcional vigente usa:

- índice público `SARI-001`;
- método de scoring `SCORE-GEO-004`;
- `report/readiness.html` como superfície canônica do índice;
- `report/scoring.html` como superfície canônica da metodologia;
- HTML em português do Brasil, mantendo em inglês apenas nomes técnicos consolidados, identificadores, APIs, formatos e termos cujo uso técnico melhora a precisão.

""",
    docs_readme,
    count=1,
)
write(docs_readme_path, docs_readme)

replace_section("docs/SERP_OBSERVATION.md", "14. HTML report decision", """## 14. HTML report

The canonical point-in-time Search Intelligence surface is implemented at:

```text
report/search-intelligence.html
```

It is generated from persisted Search Intelligence evidence and does not call the Search provider or AI provider during rendering. SERP Observation, deterministic competitive evidence and optional Competitive AI are progressively projected when available.

Historical comparison is implemented separately under `SEARCH-HISTORY-001` and materializes a standalone read-only report plus manifest. Keeping point-in-time and temporal contracts separate avoids implying that a later observed movement was caused by a deployment.""")
replace_section("docs/SERP_OBSERVATION.md", "15. Known limitations", """## 15. Known limitations

- current live SERP adapter is Google via SerpApi;
- normalized SERP rows focus on organic results;
- no SERP-provider billing/quota endpoint integration;
- Search Console/Bing Webmaster ingestion remains separate from this provider adapter;
- competitive classification is a bounded heuristic, not a commercial entity graph;
- content comparison uses static HTTP HTML, not browser-rendered DOM;
- Competitive AI live support initially uses OpenAI behind a provider-neutral contract;
- Competitive AI receives extracted features rather than full raw HTML;
- historical semantic comparison of Competitive AI output is not yet a stable contract;
- no distributed regional probes.""")
replace_section("docs/SERP_OBSERVATION.md", "16. Next evolution", """## 16. Next evolution

Point-in-time Search Intelligence, deterministic before/after comparison and the standalone historical HTML/manifest surface are now implemented. The next product extension should build periodic query observation on top of these stable contracts:

```text
scheduled exact Search context
-> repeated persisted observations
-> SEARCH-HISTORY-001 compatible comparisons
-> trend view
-> bounded alerts for material observed movement
```

Scheduling must preserve query/engine/market/language/device/depth identity and provider provenance. Search volatility remains observational; an alert must never be presented as proof of ranking causality.""")

replace_section("docs/COMPETITIVE_SEARCH_INTELLIGENCE.md", "16. Current limitations", """## 16. Current limitations

- result classification remains a small heuristic taxonomy;
- no entity/business-equivalence graph yet;
- content extraction uses static HTTP HTML, not rendered browser DOM;
- no canonical/hreflang/link-graph comparison yet;
- Competitive AI live support starts with OpenAI; other adapters can be added behind the same contract;
- AI sees extracted features rather than full raw HTML;
- historical comparison and its standalone HTML/manifest are deterministic; semantic before/after comparison of Competitive AI output is not yet a stable contract;
- public-IP validation still requires network-layer reinforcement before multi-tenant SaaS.

The product platform milestone and before/after audit model is reused by Search Intelligence History. No parallel deployment-marker model is introduced.""")

replace_section("docs/COMPETITIVE_AI_INTELLIGENCE.md", "13. Limitações atuais", """## 13. Limitações atuais

- adapter de Competitive AI ao vivo disponível inicialmente para OpenAI;
- não há comparação semântica histórica entre duas execuções nesta camada;
- não há entity/business-equivalence graph;
- não há browser-rendered competitive content;
- `report/search-intelligence.html` projeta a evidência semântica persistida, mas não executa IA durante o rendering;
- `SEARCH-HISTORY-001` e seu relatório histórico comparam evidência determinística; não transformam recomendações de IA em score temporal;
- a IA não recebe o corpo integral da página, apenas features determinísticas;
- não existe garantia de ganho de ranking a partir das recomendações.

A arquitetura de plataforma reutiliza os marcos de deploy e a resolução before/after existentes. Não existe um segundo sistema de marcos para Search Intelligence.""")

sir_path = "docs/SEARCH_INTELLIGENCE_REPORT.md"
sir = read(sir_path)
sir = sir.replace(
    "The Competitive AI runtime should follow the same contract: after semantic evidence is persisted, refresh the report from persisted state rather than passing an in-memory AI object directly into the renderer.",
    "The Competitive AI runtime follows the same contract: after semantic evidence is persisted, it refreshes the report from persisted state rather than passing an in-memory AI object directly into the renderer.",
)
write(sir_path, sir)

history_doc_path = "docs/SEARCH_INTELLIGENCE_HISTORY.md"
history_doc = read(history_doc_path)
if "audits/search-history/SH-*/" not in history_doc:
    history_doc = history_doc.replace(
        "Optional JSON output:\n",
        "Every successful comparison also materializes a standalone HTML report and manifest under `audits/search-history/SH-*/`. Use `--report-root PATH` to override that output root.\n\nOptional JSON output:\n",
        1,
    )
    history_doc = history_doc.replace(
        "Each event can contain:\n",
        """Standalone output:

```text
audits/search-history/SH-*/
├─ report.html
└─ manifest.json
```

The pair-level manifest records baseline/current audit IDs, methodology, milestone metadata when supplied, comparability, event counts, events, source policy, scoring boundary and causality policy.

Each event can contain:
""",
        1,
    )
history_doc = history_doc.replace(
    "A future historical HTML surface can render this persisted/computed comparison contract without changing its semantics.",
    "`audits/search-history/SH-*/report.html` renders this comparison contract, while `manifest.json` preserves machine-readable provenance and methodological boundaries. The standalone surface belongs to the pair, not to either source AUD.",
)
history_doc = history_doc.replace(
    "- no dedicated historical HTML page is generated yet;\n",
    "- the historical HTML is deterministic and pair-level; it does not yet provide multi-run trend charts across three or more observations;\n",
)
write(history_doc_path, history_doc)

report_guide_path = "docs/REPORT_GUIDE.md"
report_guide = read(report_guide_path)
report_guide = report_guide.replace(
    "├─ web-performance.html        # condicional\n├─ apdex.html",
    "├─ web-performance.html        # condicional\n├─ search-intelligence.html    # condicional\n├─ apdex.html",
    1,
)
if "| Search Intelligence | `search-intelligence.html`" not in report_guide:
    report_guide = report_guide.replace(
        "| Core Web Vitals / Lighthouse | `web-performance.html` | lab + field data separados |\n",
        "| Core Web Vitals / Lighthouse | `web-performance.html` | lab + field data separados |\n| Search Intelligence | `search-intelligence.html` | SERP observado + comparação determinística + IA evidence-bound opcional; non-scoring |\n",
        1,
    )
if "## Search Intelligence History\n" not in report_guide:
    history_section = """## Search Intelligence History

Comparações entre dois AUDs são superfícies standalone, porque pertencem ao par e não a um único workspace:

```text
audits/search-history/SH-*/report.html
                            manifest.json
```

`SEARCH-HISTORY-001` exige identidade exata de query, engine, país, região, idioma, device, profundidade e domínio, além de provider/data mode compatíveis. `NOT_FOUND_WITHIN_DEPTH` nunca é convertido em posição numérica artificial.

O relatório pode mostrar posição antes/depois, entrada/saída da profundidade observada, mudanças determinísticas de conteúdo, JSON-LD e gaps adicionados/resolvidos. Milestone/deploy estabelece cronologia, não causalidade. A superfície é read-only e não altera `SARI-001`/`SCORE-GEO-004`.

"""
    report_guide = report_guide.replace("## RASAi Monitor\n", history_section + "## RASAi Monitor\n", 1)
report_guide = report_guide.replace("Web Performance\nApdex de navegação", "Web Performance\nSearch Intelligence\nApdex de navegação", 1)
report_guide = report_guide.replace(
    "2 x audit.db read-only\n→ MON-*/report.html + manifest/impact\n→ VER-*/report.html\n",
    "2 x audit.db read-only\n→ SH-*/report.html + manifest.json\n→ MON-*/report.html + manifest/impact\n→ VER-*/report.html\n",
    1,
)
write(report_guide_path, report_guide)

outputs_path = "docs/OUTPUTS_AND_ARTIFACTS.md"
outputs = read(outputs_path)
outputs = outputs.replace(
    "   ├─ web-performance.html     # condicional\n   ├─ apdex.html",
    "   ├─ web-performance.html     # condicional\n   ├─ search-intelligence.html # condicional\n   ├─ apdex.html",
    1,
)
if "### `search-intelligence.html`" not in outputs:
    outputs = outputs.replace(
        "### `apdex.html`\n",
        "### `search-intelligence.html`\n\nSuperfície point-in-time de SERP Observation, classificação competitiva, evidência determinística de conteúdo e Competitive AI persistida quando habilitada. Non-scoring; não altera `SARI-001`/`SCORE-GEO-004`.\n\n### `apdex.html`\n",
        1,
    )
if "## Search Intelligence History\n" not in outputs:
    standalone = """## Search Intelligence History

```text
audits/search-history/SH-*/
├─ report.html
└─ manifest.json
```

Comparação pair-level `SEARCH-HISTORY-001`, determinística e read-only. O manifest preserva baseline/current, milestone quando informado, comparabilidade, eventos e fronteiras de causalidade/scoring. Não chama Search provider, páginas públicas ou IA.

"""
    outputs = outputs.replace("## RASAi Monitor\n", standalone + "## RASAi Monitor\n", 1)
outputs = outputs.replace("Web Performance\nApdex de navegação", "Web Performance\nSearch Intelligence\nApdex de navegação", 1)
outputs = outputs.replace(
    "- Monitoring, Quality, Timeline, Verification e consolidation abrem bancos fonte read-only;\n",
    "- Search Intelligence History, Monitoring, Quality, Timeline, Verification e consolidation abrem bancos fonte read-only;\n",
    1,
)
write(outputs_path, outputs)

cli_path = "docs/CLI_REFERENCE.md"
cli_doc = read(cli_path)
if "audits/search-history/SH-*/report.html" not in cli_doc:
    cli_doc = cli_doc.replace(
        "  --current-workspace audits/AUD-CURRENT\n```\n\nCom saída JSON opcional:",
        "  --current-workspace audits/AUD-CURRENT\n```\n\nPor padrão, uma execução bem-sucedida gera `audits/search-history/SH-*/report.html` e `manifest.json`. Use `--report-root PATH` para alterar a raiz dessa saída standalone.\n\nCom saída JSON opcional:",
        1,
    )
cli_doc = cli_doc.replace(
    "O comando é read-only sobre `audit.db` e não chama Search provider, AI provider ou páginas públicas.",
    "O comando é read-only sobre `audit.db`, não chama Search provider, AI provider ou páginas públicas e nunca altera `SARI-001`/`SCORE-GEO-004`.",
)
write(cli_path, cli_doc)

env_path = "docs/ENVIRONMENT_VARIABLES.md"
env_doc = read(env_path)
if "## Search Intelligence / SERP" not in env_doc:
    env_doc += """

## Search Intelligence / SERP

As variáveis abaixo são reconhecidas pela superfície `rasai search`. Search Intelligence é opt-in e permanece independente do scoring: nenhuma delas altera `SARI-001` ou `SCORE-GEO-004`.

| Variável | Valores / tipo | Default efetivo | Finalidade |
|---|---|---:|---|
| `RASAI_SERP_MODE` | `disabled`, `live`, `fixture` | `disabled` | habilita explicitamente observação SERP |
| `RASAI_SERP_PROVIDER` | provider ID | `serpapi` | adapter live; atualmente SerpApi/Google |
| `RASAI_SERPAPI_API_KEY` | segredo BYOK | sem default | credencial SerpApi no modo live |
| `RASAI_SERP_FIXTURE_PATH` | caminho | sem default | fixture canônica no modo fixture |
| `RASAI_SERP_MAX_QUERIES` | inteiro `>0` | `10` | teto de queries por execução |
| `RASAI_SERP_MAX_REQUESTS` | inteiro `>0` | `10` | orçamento máximo de tentativas HTTP do provider |
| `RASAI_SERP_MAX_DEPTH` | inteiro `>0` | `20` | profundidade máxima observável solicitada |
| `RASAI_SERP_MAX_COMPETITORS` | inteiro `>=0` | `10` | teto de candidatos derivados |
| `RASAI_SERP_TIMEOUT_SECONDS` | número finito `>0` | `20` | timeout por tentativa do provider |
| `RASAI_SERP_RETRIES` | inteiro `>=0` | `1` | retries limitados do provider |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | número finito `>=0` | `1` | intervalo mínimo entre inícios de requests |
| `RASAI_SEARCH_AI_PROVIDER` | `none`, `fixture`, `openai` | `none` | provider da camada Competitive AI opt-in |

`RASAI_SERPAPI_API_KEY` e `OPENAI_API_KEY` são segredos e não devem ser persistidos em `audit.db`, artifacts ou HTML. `--dry-run` valida orçamento sem chamar Search provider, páginas ou Competitive AI. Conteúdo competitivo e IA exigem flags explícitas (`--compare-content`, `--ai-competitive`).

O cálculo de pior caso do provider live permanece limitado por profundidade, paginação e retries; o runtime bloqueia a execução quando o teto projetado excede `RASAI_SERP_MAX_REQUESTS`.
"""
write(env_path, env_doc)

# Final local guard: no concrete scoring version except 004 anywhere in tracked product text.
invalid: list[str] = []
for path in tracked_text_paths():
    if path.name.startswith("one-shot-score004-history-report") or path.name == Path(__file__).name:
        continue
    match = concrete_score.search(path.read_text(encoding="utf-8"))
    if match:
        invalid.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
if invalid:
    raise RuntimeError("non-canonical scoring identifiers remain:\n" + "\n".join(invalid))
