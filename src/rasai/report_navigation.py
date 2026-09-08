"""Canonical navigation and shared presentation polish for generated reports.

All report pages use the same ordered menu. Optional pages are included only when
their HTML file exists, exactly the current page is marked active, and the final
normalization pass also applies the shared report presentation contract.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from rasai.report_contract import CANONICAL_NAV_ITEMS, REPORT_ALIASES
from rasai.report_semantics import SEMANTIC_CSS, enhance_report_html


NAV_ITEMS: tuple[tuple[str, str], ...] = CANONICAL_NAV_ITEMS

BRASILIA_TIMEZONE = ZoneInfo("America/Sao_Paulo")

_NAV_ASIDE_RE = re.compile(
    r"<aside\b[^>]*>.*?<nav\b[^>]*>.*?</nav>.*?</aside>",
    flags=re.IGNORECASE | re.DOTALL,
)
_BR_RULE_RE = re.compile(r"\b(BR-GEO-\d{3})\b")
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)", flags=re.DOTALL)
_AI_COST_TOTAL_RE = re.compile(
    r"<section class='notice cost-total' data-api-cost-total='true'>.*?</section>",
    flags=re.DOTALL,
)
_M18_COST_RE = re.compile(
    r"<small>Custo estimado total</small><strong>([0-9]+(?:\.[0-9]+)?) USD</strong>"
)
_M20_SECTION_RE = re.compile(r"<section id='remediation-ai-telemetry'.*?</section>", flags=re.DOTALL)
_M20_COST_RE = re.compile(
    r"<small>Custo estimado</small><strong>([0-9]+(?:\.[0-9]+)?) USD</strong>"
)
_FOOTER_RE = re.compile(
    r"<footer\b[^>]*class=(['\"])[^'\"]*\bfooter\b[^'\"]*\1[^>]*>.*?</footer>",
    flags=re.IGNORECASE | re.DOTALL,
)
_PRESENTATION_MARKER = "/* rasai-premium-report-v2 */"
_SEMANTIC_MARKER = "/* rasai-result-semantics-v1 */"

_RULE_TOOLTIPS: dict[str, str] = {
    "BR-GEO-001": "Severidade CRITICAL · Valida se o target da auditoria é válido e está normalizado.",
    "BR-GEO-002": "Severidade INFO · Exige rastreabilidade da origem de cada URL descoberta.",
    "BR-GEO-003": "Severidade LOW · Verifica aquisição e interpretação de sitemap quando disponível.",
    "BR-GEO-004": "Severidade INFO · Garante preservação dos artifacts HTTP necessários à reprodutibilidade.",
    "BR-GEO-005": "Severidade HIGH · Verifica se a página é tecnicamente recuperável.",
    "BR-GEO-006": "Severidade HIGH · Verifica se a resposta HTTP final é utilizável para o conteúdo esperado.",
    "BR-GEO-007": "Severidade HIGH · Verifica se redirects resolvem sem loop ou hop inválido.",
    "BR-GEO-008": "Severidade LOW · Detecta problemas materiais introduzidos pela cadeia de redirects.",
    "BR-GEO-009": "Severidade HIGH · Verifica se documentos HTML esperados oferecem conteúdo analisável.",
    "BR-GEO-010": "Severidade HIGH · Detecta falhas de rendering que impedem acesso a conteúdo essencial.",
    "BR-GEO-011": "Severidade HIGH · Resolve e valida diretivas de indexabilidade.",
    "BR-GEO-012": "Severidade MEDIUM · Identifica corretamente diretivas noindex explícitas.",
    "BR-GEO-013": "Severidade MEDIUM · Verifica se declarações canonical são interpretáveis e não conflitantes.",
    "BR-GEO-014": "Severidade MEDIUM · Verifica validade técnica e plausibilidade do canonical target.",
    "BR-GEO-015": "Severidade HIGH · Detecta conflitos de canonical/indexabilidade introduzidos por JavaScript.",
    "BR-GEO-016": "Severidade MEDIUM · Detecta páginas error-like que se apresentam como indexáveis.",
    "BR-GEO-017": "Severidade MEDIUM · Verifica se robots.txt é interpretável quando presente.",
    "BR-GEO-018": "Severidade HIGH · Resolve acesso separadamente para cada crawler configurado.",
    "BR-GEO-019": "Severidade HIGH · Compara RAW e RENDERED para consistência semântica material.",
    "BR-GEO-020": "Severidade HIGH · Verifica se conteúdo essencial permanece recuperável após JavaScript.",
    "BR-GEO-021": "Severidade HIGH · Verifica se rotas client-side indexáveis funcionam por acesso direto.",
    "BR-GEO-022": "Severidade MEDIUM · Verifica se navegação interna importante expõe destinos crawlable.",
    "BR-GEO-023": "Severidade HIGH · Detecta soft-404 enganoso criado por client-side routing.",
    "BR-GEO-024": "Severidade MEDIUM · Verifica se lazy loading preserva conteúdo essencial recuperável.",
    "BR-GEO-025": "Severidade HIGH · Verifica se o conteúdo principal pode ser identificado.",
    "BR-GEO-026": "Severidade HIGH · Verifica se existe conteúdo significativo além de boilerplate.",
    "BR-GEO-027": "Severidade MEDIUM · Verifica se informação essencial sobrevive à extração.",
    "BR-GEO-028": "Severidade HIGH · Verifica presença e representatividade semântica do title.",
    "BR-GEO-029": "Severidade MEDIUM · Avalia se a hierarquia semântica da página é compreensível.",
    "BR-GEO-030": "Severidade MEDIUM · Avalia se tópico principal e seções são identificáveis.",
    "BR-GEO-031": "Severidade MEDIUM · Avalia se a entidade principal é identificável quando aplicável.",
    "BR-GEO-032": "Severidade MEDIUM · Verifica contexto suficiente para tipos e relações de entidades.",
    "BR-GEO-033": "Severidade MEDIUM · Detecta ambiguidade material de entidade com evidência.",
    "BR-GEO-034": "Severidade MEDIUM · Verifica se Structured Data é sintaticamente interpretável.",
    "BR-GEO-035": "Severidade LOW · Identifica tipos e propriedades presentes em Structured Data.",
    "BR-GEO-036": "Severidade MEDIUM · Verifica consistência entre Structured Data e conteúdo visível.",
    "BR-GEO-037": "Severidade MEDIUM · Verifica consistência entre entidades estruturadas e observadas.",
    "BR-GEO-038": "Severidade HIGH · Avalia se a intenção primária da página é identificável.",
    "BR-GEO-039": "Severidade MEDIUM · Verifica se perguntas primárias relevantes recebem resposta explícita.",
    "BR-GEO-040": "Severidade MEDIUM · Verifica se respostas possuem contexto suficiente.",
    "BR-GEO-041": "Severidade LOW · Identifica claims factuais materiais quando presentes.",
    "BR-GEO-042": "Severidade MEDIUM · Verifica se claims factuais possuem contexto suficiente.",
    "BR-GEO-043": "Severidade MEDIUM · Verifica qualificadores de claims numéricos e temporais.",
    "BR-GEO-044": "Severidade MEDIUM · Detecta informação importante que exige inferência excessiva.",
    "BR-GEO-045": "Severidade MEDIUM · Verifica atribuição ou suporte para claims materiais quando requerido.",
    "BR-GEO-046": "Severidade LOW · Verifica publisher, author ou responsável quando relevante.",
    "BR-GEO-047": "Severidade MEDIUM · Verifica consistência dos sinais de publicação e freshness.",
    "BR-GEO-048": "Severidade MEDIUM · Avalia cobertura das intenções primária e secundárias.",
    "BR-GEO-049": "Severidade MEDIUM · Exige evidência para gaps materiais de intenção.",
    "BR-GEO-050": "Severidade MEDIUM · Verifica se links internos expõem destinos tecnicamente utilizáveis.",
    "BR-GEO-051": "Severidade MEDIUM · Identifica duplicatas e near-duplicates materiais no universo auditado.",
    "BR-GEO-052": "Severidade MEDIUM · Detecta e classifica diferenças materiais entre Desktop e Mobile.",
    "BR-GEO-053": "Severidade CRITICAL · Verifica rastreabilidade e reabertura de Findings, RuleExecutions e Evidences.",
    "BR-GEO-054": "Integridade do auditor · Verifica a reprodutibilidade do SCORE-GEO-004 persistido.",
    "BR-GEO-055": "Severidade dinâmica · Avalia, de forma evidence-bound e opcional por IA, a qualidade técnica do sitemap sem criar peso adicional no grupo SITEMAP.",
    "BR-GEO-056": "Severidade dinâmica · Avalia, de forma evidence-bound e opcional por IA, a qualidade técnica de robots.txt sem criar peso adicional no grupo ROBOTS.",
}

_PREMIUM_CSS = r"""
/* rasai-premium-report-v2 */
:root{
  --bg:#f6f7fb;--surface:#fffefd;--ink:#273449;--muted:#6f7b8d;
  --line:rgba(111,123,141,.16);--blue:#657fc6;--green:#5f9674;
  --amber:#b68a50;--red:#bf6f70;--slate:#7d899a;--radius:5px;
  --shadow:0 6px 18px rgba(47,58,78,.045);
  --soft-blue:#eef2fb;--soft-green:#edf6f0;--soft-amber:#fbf4e8;
  --soft-red:#fbefef;--soft-slate:#f1f3f6;
}
body{background:var(--bg);color:var(--ink);font-size:14.5px;line-height:1.56}
.app-nav{background:#2f3a4d;color:#e8edf4;border-right:0;box-shadow:6px 0 24px rgba(30,41,59,.08)}
.brand{border-bottom-color:rgba(255,255,255,.12)}.brand small{color:#bac4d2}.brand strong{font-weight:650}
.app-nav a{color:#d8e0ea;font-weight:520}.app-nav a:hover,.app-nav a:focus,.app-nav a.active{background:#46536a;color:#fff}
.app-main{max-width:1720px;padding:32px clamp(20px,3vw,42px) 60px}.app-main>*{width:100%;max-width:100%;margin-left:auto;margin-right:auto}
h1{font-weight:650;letter-spacing:-.025em}h2{font-weight:630;letter-spacing:-.012em}h3,h4,h5{font-weight:620}
strong{font-weight:640}.lead,.intro,.hero>p,.panel>p,.page-card>p,.detail-body>p,.notice>p{max-width:100%;width:100%}
.panel ul,.panel ol,.detail-body ul,.detail-body ol{max-width:100%;width:100%;padding-right:clamp(4px,1vw,14px)}
.hero,.panel,.page-card,.ref-card{border-color:var(--line);border-radius:var(--radius);background:var(--surface)}
.hero{padding:25px clamp(22px,2.2vw,30px);box-shadow:0 8px 24px rgba(47,58,78,.05)}
.panel{padding:22px clamp(18px,2vw,26px);box-shadow:0 3px 12px rgba(47,58,78,.035)}
.page-card{padding:20px clamp(17px,1.8vw,24px);box-shadow:0 2px 10px rgba(47,58,78,.03)}
.page-card+.page-card{margin-top:16px}.ref-card{box-shadow:0 2px 9px rgba(47,58,78,.025)}
.panel>.metric-grid,.panel>.grid,.panel>.score-grid,.panel>.table-wrap,.panel>.notice,.panel>.page-card,.panel>details{margin-block:14px}
.panel>:is(.metric-grid,.grid,.score-grid,.table-wrap,.notice,.page-card,details)+:is(.metric-grid,.grid,.score-grid,.table-wrap,.notice,.page-card,details){margin-top:16px}
.metric,.score-meta div,.page-summary div,.remediation-grid>div,.confidence-explain>div,.ref-card{overflow-wrap:anywhere;word-break:normal}
.config-accordion-stack{display:grid;grid-template-columns:1fr;gap:10px;margin:14px 0 18px}
.config-accordion{display:block;width:100%;min-width:0;margin:0!important;border:1px solid var(--line);border-radius:7px;background:#fbfbfc;overflow:hidden}
.config-accordion>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;cursor:pointer;background:#f5f6f8;font-size:.9rem;font-weight:680;list-style:none}
.config-accordion>summary::-webkit-details-marker{display:none}.config-accordion>summary::after{content:'+';font-size:1.05rem;color:var(--muted);font-weight:500}.config-accordion[open]>summary::after{content:'−'}
.config-accordion-body{padding:14px 15px 16px;background:#fff}.config-accordion-body>:first-child{margin-top:0}.config-accordion-body>:last-child{margin-bottom:0}
.config-accordion-body .metric-grid,.config-accordion-body .grid{margin-block:10px;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))}
.config-accordion-body code,.config-accordion-body strong,.config-accordion-body span{overflow-wrap:anywhere}
.metric-grid{grid-template-columns:repeat(auto-fit,minmax(min(190px,100%),1fr));gap:9px}
#remediation-ai-telemetry .table-wrap{margin-top:14px}
.grid{grid-template-columns:repeat(auto-fit,minmax(min(250px,100%),1fr));gap:11px}
.score-grid{grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:11px}
.metric,.score-meta div,.page-summary div,.remediation-grid>div,.confidence-explain>div{border:0;background:#f7f8fb;border-radius:5px}
.metric{padding:12px 13px}.metric small,.label,.score-meta small,.page-summary small,.remediation-grid small{color:var(--muted)}
.metric strong{font-size:.96rem;font-weight:650}.score-number{font-weight:680}.score-card{border:1px solid var(--line);border-left-width:4px;border-radius:5px;box-shadow:0 3px 12px rgba(47,58,78,.03)}
.score-card.good{background:var(--soft-green)}.score-card.warn{background:var(--soft-amber)}.score-card.bad{background:var(--soft-red)}
.page-url{margin-top:.18rem;margin-bottom:11px;font-size:clamp(.9rem,1vw,.98rem);font-weight:610;color:#3f5067}
.page-summary{grid-template-columns:minmax(74px,.55fr) minmax(240px,2.2fr) minmax(88px,.65fr) minmax(220px,1.8fr);gap:8px;margin:10px 0 15px}
.page-summary>div{padding:9px 10px;min-height:54px}.page-summary>div:nth-child(2) strong{font-size:.78rem;font-weight:580}.page-summary>div:nth-child(4) strong{font-size:.77rem;font-weight:580}
.snapshot{display:grid;grid-template-columns:minmax(0,1fr) minmax(320px,390px);gap:20px;align-items:start;margin-top:12px}
.snapshot>div{grid-column:1;grid-row:1;min-width:0}.snapshot>figure{grid-column:2;grid-row:1;margin:0;align-self:start;position:sticky;top:20px;border:1px solid var(--line);border-radius:5px;overflow:hidden;background:#f3f5f8;box-shadow:0 6px 18px rgba(47,58,78,.045)}
.snapshot>figure a{display:block;padding:8px;background:#f3f5f8}
.snapshot>figure img{display:block;width:100%;height:auto;max-height:520px;object-fit:contain;object-position:top center;border-radius:7px;background:#fff}
.snapshot>figure figcaption{padding:8px 10px;border-top:1px solid var(--line);background:#fff;color:var(--muted);font-size:.71rem;letter-spacing:.01em}
.snapshot:not(:has(>figure)){grid-template-columns:1fr}.snapshot:not(:has(>figure))>div{grid-column:1}
.finding{padding:12px 0}.finding-title{max-width:72ch}.finding-head>span:last-child{display:flex;gap:5px;align-items:center;flex-wrap:wrap}
.notice{border-color:rgba(101,127,198,.20);background:var(--soft-blue);border-radius:5px}.notice.good{border-color:rgba(95,150,116,.25);background:var(--soft-green)}.notice.warn{border-color:rgba(182,138,80,.30);background:var(--soft-amber)}.notice.bad{border-color:rgba(191,111,112,.32);background:var(--soft-red)}
.badge{background:var(--soft-slate);color:#465365;font-weight:620}.badge.info{background:var(--soft-blue);color:#526ba8}.badge.good{background:var(--soft-green);color:#47785a}.badge.warn{background:var(--soft-amber);color:#8c662f}.badge.bad{background:var(--soft-red);color:#9f4f52}
.badge.bad,.badge.priority-high,.priority-high,.required{font-weight:720;box-shadow:inset 0 0 0 1px rgba(191,111,112,.28)}
.notice.bad,.score-card.bad,details:has(.badge.bad),.page-card:has(.badge.priority-high){box-shadow:0 7px 20px rgba(191,111,112,.09),inset 3px 0 0 rgba(191,111,112,.72)}
.notice.warn,.score-card.warn,.review{box-shadow:0 5px 16px rgba(182,138,80,.06)}
.table-wrap{border-color:var(--line);border-radius:0;box-shadow:none}table{border-radius:0}th{background:#f4f6f9;color:#596678;font-weight:650}th,td{border-bottom-color:rgba(111,123,141,.11)}
details{border-color:var(--line);border-radius:5px;background:#fbfbfc}summary{font-weight:620}.snapshot figure{border-color:var(--line)}
pre{background:#2f394a;color:#edf1f7;border-radius:9px}.footer{max-width:100%;width:100%}
.cost-total{margin-top:-4px;margin-bottom:18px;background:#eef2fb;border-color:rgba(101,127,198,.24);box-shadow:0 6px 18px rgba(88,104,150,.05)}
.cost-total strong{color:#40598e}.cost-total .cost-breakdown{display:block;margin-top:4px;color:var(--muted);font-size:.82rem}
.br-rule-tooltip{position:relative;display:inline-flex;align-items:center;border-bottom:1px dotted rgba(82,107,168,.6);color:#4965a4;font-weight:650;cursor:help;outline:none}
.br-rule-tooltip:focus{border-radius:4px;box-shadow:0 0 0 3px rgba(101,127,198,.16)}
.br-rule-tooltip__content{position:absolute;left:0;top:calc(100% + 8px);z-index:60;width:min(360px,78vw);padding:10px 12px;border:1px solid rgba(75,91,118,.16);border-radius:10px;background:#303b4d;color:#f5f7fb;box-shadow:0 12px 30px rgba(31,41,55,.18);font-size:.77rem;font-weight:430;line-height:1.45;opacity:0;visibility:hidden;transform:translateY(-3px);transition:opacity .12s ease,transform .12s ease,visibility .12s ease;pointer-events:none}
.br-rule-tooltip__content strong{display:block;margin-bottom:3px;color:#fff;font-size:.76rem}.br-rule-tooltip:hover .br-rule-tooltip__content,.br-rule-tooltip:focus .br-rule-tooltip__content{opacity:1;visibility:visible;transform:translateY(0)}
@media(min-width:1380px){.snapshot{grid-template-columns:minmax(0,1fr) minmax(360px,430px);gap:24px}.page-summary{grid-template-columns:minmax(78px,.5fr) minmax(280px,2.4fr) minmax(90px,.6fr) minmax(250px,1.8fr)}}
@media(max-width:1120px){.app-main>*{width:100%}.page-summary{grid-template-columns:minmax(72px,.55fr) minmax(220px,2fr) minmax(84px,.6fr) minmax(180px,1.45fr)}.snapshot{grid-template-columns:minmax(0,1fr) minmax(280px,330px);gap:16px}.snapshot>figure img{max-height:460px}}
@media(max-width:900px){.app-main>*{width:100%}.hero{padding:21px 18px}.panel{padding:18px 16px}.page-card{padding:16px}.page-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.page-summary>div:nth-child(2),.page-summary>div:nth-child(4){grid-column:span 1}.snapshot{grid-template-columns:minmax(0,1fr) minmax(250px,300px);gap:14px}.snapshot>figure{position:static;top:auto}.br-rule-tooltip__content{position:fixed;left:12px;right:12px;top:auto;bottom:16px;width:auto}}
@media(max-width:700px){.app-main{padding-left:12px;padding-right:12px}.page-summary{grid-template-columns:1fr 1fr}.page-summary>div:nth-child(2),.page-summary>div:nth-child(4){grid-column:1/-1}.snapshot{grid-template-columns:1fr}.snapshot>figure{grid-column:1;grid-row:1;margin-bottom:2px}.snapshot>div{grid-column:1;grid-row:2}.snapshot>figure img{max-height:none}.metric-grid,.score-grid,.grid,.ref-grid{grid-template-columns:1fr}.table-wrap{border-radius:0}}
@media print{.br-rule-tooltip{color:inherit;border:0}.br-rule-tooltip__content{display:none}.cost-total{box-shadow:none}.snapshot{grid-template-columns:minmax(0,1fr) 280px}.snapshot>figure{position:static}}
"""


_CONFIG_PANEL_RE = re.compile(
    r"<section(?P<attrs>[^>]*\bclass=(?P<q>['\"])[^'\"]*\bpanel\b[^'\"]*(?P=q)[^>]*)>(?P<body>.*?)</section>",
    flags=re.IGNORECASE | re.DOTALL,
)
_CONFIG_CARD_RE = re.compile(
    r"<article(?P<attrs>[^>]*\bclass=(?P<q>['\"])[^'\"]*\bref-card\b[^'\"]*(?P=q)[^>]*)>(?P<body>.*?)</article>",
    flags=re.IGNORECASE | re.DOTALL,
)
_CONFIG_TITLE_RE = re.compile(r"<h3[^>]*>(?P<title>.*?)</h3>", flags=re.IGNORECASE | re.DOTALL)
_CONFIG_HEADING_HINTS = (
    "auditoria", "ia semântica", "ia semantica", "remediação", "remediacao",
    "web performance", "apdex", "contexto editorial", "pagespeed", "crux",
)


def _plain_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).replace("&nbsp;", " ").strip()


def _enhance_configuration_accordions(html: str) -> str:
    def replace_panel(match: re.Match[str]) -> str:
        body = match.group("body")
        cards = list(_CONFIG_CARD_RE.finditer(body))
        if len(cards) < 3:
            return match.group(0)
        titles: list[str] = []
        for card in cards:
            title_match = _CONFIG_TITLE_RE.search(card.group("body"))
            titles.append(_plain_html(title_match.group("title")) if title_match else "")
        recognized = sum(any(hint in title.casefold() for hint in _CONFIG_HEADING_HINTS) for title in titles)
        panel_text = _plain_html(body).casefold()
        if recognized < 2 or "configura" not in panel_text:
            return match.group(0)

        def replace_card(card_match: re.Match[str]) -> str:
            card_body = card_match.group("body")
            title_match = _CONFIG_TITLE_RE.search(card_body)
            if title_match is None:
                return card_match.group(0)
            title_html = title_match.group("title")
            remainder = card_body[:title_match.start()] + card_body[title_match.end():]
            return (
                "<details class='config-accordion'>"
                f"<summary>{title_html}</summary>"
                f"<div class='config-accordion-body'>{remainder}</div></details>"
            )

        converted = _CONFIG_CARD_RE.sub(replace_card, body)
        converted = re.sub(
            r"<div\s+class=(['\"])grid\1>",
            "<div class='config-accordion-stack'>",
            converted,
            count=1,
            flags=re.IGNORECASE,
        )
        return f"<section{match.group('attrs')}>{converted}</section>"

    return _CONFIG_PANEL_RE.sub(replace_panel, html)


def available_navigation(report_dir: Path, current: str | None = None) -> tuple[tuple[str, str], ...]:
    """Return canonical menu items available in the current report projection."""
    return tuple(
        (label, filename)
        for label, filename in CANONICAL_NAV_ITEMS
        if (report_dir / filename).is_file() or filename == current
    )


def format_report_generated_at(generated_at: datetime | None = None) -> str:
    """Return the report generation timestamp in Brasília time."""
    instant = generated_at or datetime.now(BRASILIA_TIMEZONE)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=BRASILIA_TIMEZONE)
    else:
        instant = instant.astimezone(BRASILIA_TIMEZONE)
    return instant.strftime("%d/%m/%Y %H:%M:%S")


def render_report_navigation(
    report_dir: Path,
    current: str,
    *,
    generated_at: datetime | None = None,
    software_version: str | None = None,
) -> str:
    """Render the canonical report menu with timestamp and active item."""
    links = available_navigation(report_dir, current)
    rendered = "".join(
        f"<a class='{'active' if filename == current else ''}' href='{escape(filename)}'>{escape(label)}</a>"
        for label, filename in links
    )
    generated_label = format_report_generated_at(generated_at)
    return (
        "<aside class='app-nav' aria-label='Navegação do relatório'>"
        "<div class='brand'>"
        "<small>RASAi Auditor</small>"
        "<strong>Relatório da auditoria</strong>"
        f"<small>Gerado em {escape(generated_label)} - Horário de Brasília</small>"
        "</div>"
        f"<nav>{rendered}</nav></aside>"
    )


def normalize_report_navigation(
    report_dir: Path,
    *,
    generated_at: datetime | None = None,
    software_version: str | None = None,
) -> None:
    """Normalize menu, semantic results, shared presentation, tooltips and API cost."""
    global NAV_ITEMS
    NAV_ITEMS = CANONICAL_NAV_ITEMS
    final_generated_at = generated_at or datetime.now(BRASILIA_TIMEZONE)
    _ensure_premium_css(report_dir)
    _enhance_ai_cost_total(report_dir)
    # Pré-publicação: remover alias versionado residual de audits locais antigos.
    (report_dir / "score-geo-004.html").unlink(missing_ok=True)
    for html_path in sorted(report_dir.glob("*.html")):
        if html_path.name in REPORT_ALIASES:
            continue
        html = html_path.read_text(encoding="utf-8")
        navigation = render_report_navigation(
            report_dir,
            html_path.name,
            generated_at=final_generated_at,
            software_version=software_version,
        )
        normalized, replacements = _NAV_ASIDE_RE.subn(navigation, html, count=1)
        if replacements != 1:
            raise ValueError(f"report page has no replaceable navigation: {html_path}")
        normalized = enhance_report_html(normalized, page_name=html_path.name, report_dir=report_dir)
        normalized = _enhance_configuration_accordions(normalized)
        normalized = _enhance_rule_tooltips(normalized)
        normalized = _move_footer_to_end_of_main(normalized)
        normalized = normalized.replace("—", "-").replace("–", "-")
        html_path.write_text(normalized, encoding="utf-8", newline="\n")


def _move_footer_to_end_of_main(html: str) -> str:
    """Keep the report footer as the final element inside main after enrichers."""
    match = _FOOTER_RE.search(html)
    if match is None:
        return html
    footer = match.group(0)
    without_footer = html[: match.start()] + html[match.end() :]
    if "</main>" not in without_footer:
        return html
    return without_footer.replace("</main>", footer + "</main>", 1)


def _ensure_premium_css(report_dir: Path) -> None:
    css_path = report_dir / "css" / "site.css"
    if not css_path.is_file():
        return
    css = css_path.read_text(encoding="utf-8")
    additions: list[str] = []
    if _PRESENTATION_MARKER not in css:
        additions.append(_PREMIUM_CSS.strip())
    if _SEMANTIC_MARKER not in css:
        additions.append(SEMANTIC_CSS.strip())
    if not additions:
        return
    css_path.write_text(css.rstrip() + "\n\n" + "\n\n".join(additions) + "\n", encoding="utf-8", newline="\n")


def _enhance_ai_cost_total(report_dir: Path) -> None:
    path = report_dir / "ai-usage.html"
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    html = _AI_COST_TOTAL_RE.sub("", html)
    m18_cost = _first_decimal(_M18_COST_RE, html)
    m20_cost = None
    m20_section = _M20_SECTION_RE.search(html)
    if m20_section is not None:
        m20_cost = _first_decimal(_M20_COST_RE, m20_section.group(0))
    costs = [value for value in (m18_cost, m20_cost) if value is not None]
    if not costs:
        path.write_text(html, encoding="utf-8", newline="\n")
        return
    total = sum(costs, Decimal("0"))
    breakdown = []
    if m18_cost is not None:
        breakdown.append(f"Análise semântica por IA {_format_cost(m18_cost)} USD")
    if m20_cost is not None:
        breakdown.append(f"Remediação textual por IA {_format_cost(m20_cost)} USD")
    banner = (
        "<section class='notice cost-total' data-api-cost-total='true'>"
        f"<strong>Consumo projetado total de APIs com custo estimado: {_format_cost(total)} USD</strong>"
        f"<span class='cost-breakdown'>{escape(' + '.join(breakdown))}. "
        "Estimativa local; não substitui billing/invoice e não inclui integrações sem estimated_cost persistido.</span>"
        "</section>"
    )
    html = html.replace("</header>", "</header>" + banner, 1)
    path.write_text(html, encoding="utf-8", newline="\n")


def _first_decimal(pattern: re.Pattern[str], text: str) -> Decimal | None:
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def _format_cost(value: Decimal) -> str:
    return f"{value:.8f}"


def _enhance_rule_tooltips(html: str) -> str:
    if "br-rule-tooltip" in html:
        return html
    parts = _TAG_SPLIT_RE.split(html)
    blocked_depth = 0
    rendered: list[str] = []
    for part in parts:
        if part.startswith("<"):
            lowered = part.lower()
            if re.match(r"<(script|style|pre|code)\b", lowered):
                blocked_depth += 1
            elif re.match(r"</(script|style|pre|code)\b", lowered):
                blocked_depth = max(0, blocked_depth - 1)
            rendered.append(part)
            continue
        if blocked_depth:
            rendered.append(part)
            continue
        rendered.append(_BR_RULE_RE.sub(_rule_tooltip_markup, part))
    return "".join(rendered)


def _rule_tooltip_markup(match: re.Match[str]) -> str:
    rule_id = match.group(1)
    detail = _RULE_TOOLTIPS.get(
        rule_id,
        "Business Rule do RASAi. Consulte o bloco atual para resultado, evidência e remediação aplicável.",
    )
    aria = escape(f"{rule_id}: {detail}", quote=True)
    return (
        f"<span class='br-rule-tooltip' tabindex='0' aria-label='{aria}'>"
        f"{rule_id}<span class='br-rule-tooltip__content' role='tooltip'>"
        f"<strong>{rule_id}</strong><span>{escape(detail)}</span></span></span>"
    )