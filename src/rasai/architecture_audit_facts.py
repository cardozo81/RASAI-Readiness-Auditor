"""Read-only structured architecture facts for one AUD.

Derived exclusively from frozen M3/M6 snapshot fields and verified captured
RAW artifacts. No DNS/browser/OCI/provider access, new evidence, AUD writes,
method overrides, score recalculation or domain-specific rules.

A standalone console preview is *not* a captured AUD snapshot and is never
implicitly merged into this projection.
"""
from __future__ import annotations

import hashlib
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from rasai.architecture_raw_signals import inspect_raw_html_signals
from rasai.architecture_hypothesis import suggest_architecture_from_raw
from rasai.architecture_m6_evidence import _safe_artifact_reference
from rasai.architecture_resource_budget import MAX_ROOT_BYTES

VERSION = "architecture-audit-facts-v1"
MAX_SNAPSHOTS = 100
_SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,72}$")
_ARCH = frozenset({"CSR_SPA", "HYDRATED", "MIXED", "STATIC_OR_SSR", "UNKNOWN"})


def _code(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_CODE.fullmatch(value) else None


def _raw_from_attested_snapshot(
    audit_root: Path, reference: Any, metadata: Mapping[str, Any],
) -> str | None:
    """Require a capture-time RAW digest; never trust a current hash alone."""
    binding = metadata.get("architecture_artifact_binding")
    if not isinstance(binding, Mapping) or binding.get("version") != "m3-artifact-binding-v1":
        return None
    expected = binding.get("raw_sha256")
    if (not isinstance(expected, str) or
            not re.fullmatch(r"[0-9a-f]{64}", expected)):
        return None
    if (not isinstance(reference, str) or
            not reference.startswith("artifacts/") or
            not _safe_artifact_reference(reference)):
        return None
    root = audit_root.resolve()
    target = audit_root / reference
    try:
        current = audit_root
        for part in target.relative_to(audit_root).parts:
            current = current / part
            if current.is_symlink():
                return None
        if not target.is_file() or not target.resolve().is_relative_to(root):
            return None
        size = target.stat().st_size
        if size > MAX_ROOT_BYTES or size <= 0:
            return None
        blob = target.read_bytes()
        if len(blob) != size or hashlib.sha256(blob).hexdigest() != expected:
            return None
        # Snapshot metadata binds these bytes, but not their trust anchor.
        # Decompression is deliberately out of scope for this projection.
        return blob.decode("utf-8-sig", errors="replace")
    except (OSError, ValueError, UnicodeError):
        return None


def read_architecture_audit_facts(
    database: str | Path, audit_id: str, *, snapshot_id: str | None = None,
) -> list[dict[str, Any]]:
    """Structured advisory records, scoped to audit/page/snapshot/device.

    Results require a previously captured RAW artifact for structural claims;
    absence or mismatched digest is a declared limitation, not 'no signals'.
    """
    db = Path(database)
    if not db.is_file() or db.is_symlink() or db.parent.is_symlink():
        return []
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            fields = {r[1] for r in con.execute("PRAGMA table_info(page_snapshots)")}
            if not {"snapshot_id", "page_id", "device", "raw_artifact_ref",
                    "rendered_artifact_ref", "browser_metadata",
                    "architecture_classification"}.issubset(fields):
                return []
            sql = """
                SELECT s.snapshot_id,s.page_id,s.device,s.raw_artifact_ref,
                       s.rendered_artifact_ref,s.browser_metadata,
                       s.architecture_classification
                  FROM page_snapshots s
                  JOIN pages p ON p.page_id=s.page_id
                 WHERE p.audit_id=?
            """
            params: list[Any] = [audit_id]
            if snapshot_id is not None:
                sql += " AND s.snapshot_id=?"
                params.append(snapshot_id)
            sql += " ORDER BY s.snapshot_id LIMIT ?"
            params.append(MAX_SNAPSHOTS + 1)
            rows = con.execute(sql, tuple(params)).fetchall()
        if len(rows) > MAX_SNAPSHOTS:
            return []
    except (OSError, sqlite3.Error, ValueError):
        return []

    result = []
    for row in rows:
        try:
            metadata = json.loads(row["browser_metadata"] or "{}")
        except (ValueError, TypeError):
            metadata = None
        if not isinstance(metadata, dict):
            metadata = {}
        raw = _raw_from_attested_snapshot(db.parent, row["raw_artifact_ref"], metadata)
        binding = metadata.get("architecture_artifact_binding")
        binding = binding if isinstance(binding, dict) else {}
        raw_verified = raw is not None
        rendered_bound = bool(
            row["rendered_artifact_ref"] and isinstance(binding.get("rendered_sha256"), str)
        )
        captured = _code(row["architecture_classification"])
        classification = captured if captured in _ARCH else "UNKNOWN"
        quality = metadata.get("capture_quality")
        quality = quality if isinstance(quality, Mapping) else {}
        raw_http = metadata.get("raw_http")
        raw_http = raw_http if isinstance(raw_http, Mapping) else {}
        redirects = raw_http.get("redirect_count")
        redirects = redirects if type(redirects) is int and 0 <= redirects <= 50 else None
        http_status = raw_http.get("status")
        http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        signals = inspect_raw_html_signals(raw) if raw_verified else None
        hypothesis = (
            suggest_architecture_from_raw(signals)
            if classification == "UNKNOWN" and signals is not None else None
        )
        record = {
            "contract": VERSION,
            "audit_id": audit_id,
            "page_id": str(row["page_id"]),
            "snapshot_id": str(row["snapshot_id"]),
            "device": str(row["device"]),
            "observed_architecture": classification,
            "classification_source": "M6_PERSISTED_SNAPSHOT",
            "raw_verified_against_capture_digest": raw_verified,
            "rendered_reference_and_digest_recorded": rendered_bound,
            "raw_signals_state": signals.status if signals else "RAW_NOT_VERIFIABLE",
            "raw_signals": ({
                "main_content": signals.raw_main_text_present,
                "h1": signals.h1_present,
                "app_root": signals.app_root_marker_present,
                "framework_attribute": signals.framework_attribute_present,
                "scripts_external": signals.external_script_tags,
                "scripts_inline": signals.inline_script_tags,
                "iframes": signals.iframe_tags,
                "iframes_with_src": signals.iframe_src_tags,
                "iframes_with_srcdoc": signals.iframe_srcdoc_tags,
                "skeleton_marker": signals.hidden_placeholder_present,
            } if signals and signals.status == "RAW_STRUCTURAL_SIGNALS_OBSERVED" else None),
            "hypothesis": ({
                "candidate": hypothesis.likely.value if hypothesis.likely else None,
                "structure": hypothesis.structure,
                "alternatives": [a.value for a in hypothesis.alternatives],
                "confidence": hypothesis.confidence,
                "evidence_codes": list(hypothesis.evidence),
                "method_version": hypothesis.method_version,
            } if hypothesis else None),
            "capture_quality": _code(quality.get("state")),
            "network_error": _code(raw_http.get("network_error")),
            "http_status_observed": http_status,
            "http_redirects_observed": redirects,
            "boundary": "AUD_SNAPSHOT_ONLY_NO_STANDALONE_PREVIEW",
            "measurement_inference_authorized": False,
            "score_effect": False,
        }
        result.append(record)
    return result


def architecture_audit_facts_html(database: str | Path, audit_id: str) -> str:
    """Materialize observed application and public-HTTP facts without guessing topology."""
    from rasai.cat07_architecture_reporting import ARCH_LABELS

    facts = read_architecture_audit_facts(database, audit_id)
    lead = (
        "<div class='subsection' id='architecture-facts'>"
        "<h3>Arquitetura da aplicação e rede observada nesta captura</h3>"
        "<p class='section-lead'>Este quadro apresenta <strong>todos os fatos arquiteturais "
        "disponíveis nesta projeção</strong>, separados por evidência. "
        "A descoberta preliminar do console é independente e não é incorporada "
        "automaticamente à auditoria. Valores não comprovados permanecem N/D.</p>"
    )
    if not facts:
        return lead + (
            "<p>Não há snapshots com dados arquiteturais estruturados nesta auditoria. "
            "Rede, DNS, TLS e topologia: N/D (dados não disponíveis nesta projeção).</p></div>"
        )
    parts = [lead, """
    <style>
    #architecture-facts .architecture-observations {
      display:grid;grid-template-columns:minmax(0,1fr);gap:16px;margin:16px 0
    }
    #architecture-facts .architecture-observation {
      border:1px solid var(--line,#dce5e7);border-radius:10px;
      padding:18px 20px;min-width:0;background:var(--card,#fff)
    }
    #architecture-facts .architecture-observation h4{margin:0 0 12px;font-size:1.1rem}
    #architecture-facts .architecture-fact-grid {
      display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px
    }
    #architecture-facts .architecture-fact-group {
      min-width:0;border-top:1px solid var(--line,#dce5e7);padding-top:12px
    }
    #architecture-facts .architecture-fact-group h5{font-size:.9rem;margin:0 0 9px}
    #architecture-facts .architecture-fact-group dl{margin:0;display:grid;gap:8px}
    #architecture-facts .architecture-fact-group dl div{min-width:0}
    #architecture-facts .architecture-fact-group dt{font-size:.76rem;color:var(--muted,#4a6270)}
    #architecture-facts .architecture-fact-group dd{
      margin:2px 0 0;font-weight:600;overflow-wrap:anywhere
    }
    #architecture-facts .architecture-limit {
      border-left:3px solid var(--line-strong,#afbec5);padding:10px 13px;
      margin:14px 0 0;background:var(--surface-subtle,#f6f8fa)
    }
    @media(max-width:850px){
      #architecture-facts .architecture-fact-grid{grid-template-columns:minmax(0,1fr)}
    }
    @media print{#architecture-facts .architecture-observation{break-inside:avoid}}
    </style>
    <div class='architecture-observations'>
    """]
    for row in facts:
        def shown(value: Any) -> str:
            return escape(str(value)) if value is not None else "N/D"

        def display(name: str, value: Any) -> str:
            return "<div><dt>" + escape(name) + "</dt><dd>" + shown(value) + "</dd></div>"

        signals = row["raw_signals"] if isinstance(row["raw_signals"], dict) else None
        classification = ARCH_LABELS.get(row["observed_architecture"], ARCH_LABELS["UNKNOWN"])
        parts.append(
            "<article class='architecture-observation'><h4>Captura " + shown(row["snapshot_id"])
            + " · " + shown(row["device"]) + "</h4>"
            "<div class='architecture-fact-grid'>"
            "<section class='architecture-fact-group'><h5>Arquitetura observada</h5><dl>"
            + display("Classificação registrada nesta captura", classification)
            + display("Página de origem", row["page_id"])
            + display("Integridade do HTML inicial",
                      "Hash da captura verificado" if row["raw_verified_against_capture_digest"]
                      else "N/D (integridade não comprovada)")
            + display("DOM renderizado",
                      "Referência e hash registrados, sem nova verificação"
                      if row["rendered_reference_and_digest_recorded"]
                      else "N/D (vínculo não comprovado)")
            + "</dl></section>"
            "<section class='architecture-fact-group'><h5>Estrutura HTML observada</h5><dl>"
        )
        if signals is not None:
            parts.append(
                display("Scripts externos declarados no HTML inicial", signals["scripts_external"])
                + display("Scripts embutidos declarados no HTML inicial", signals["scripts_inline"])
                + display("Elementos iframe declarados no HTML inicial", signals["iframes"])
                + display("Iframes com endereço declarado", signals["iframes_with_src"])
                + display("Iframes com conteúdo interno", signals["iframes_with_srcdoc"])
                + display("Título H1", "Observado" if signals["h1"] else "Não observado")
                + display("Contêiner de aplicação", "Observado" if signals["app_root"] else "Não observado")
                + display("Marcador de framework", "Observado" if signals["framework_attribute"] else "Não observado")
                + display("Marcador de placeholder/skeleton",
                          "Observado" if signals["skeleton_marker"] else "Não observado")
                + display("Conteúdo principal no HTML inicial",
                          "Observado" if signals["main_content"] else "Não comprovado")
            )
        else:
            parts.append(display("Sinais estruturais", "N/D (" + str(row["raw_signals_state"]) + ")"))
        parts.append(
            "</dl></section>"
            "<section class='architecture-fact-group'><h5>HTTP e resposta pública observados</h5><dl>"
            + display("Status HTTP da captura", row["http_status_observed"])
            + display("Redirecionamentos HTTP observados", row["http_redirects_observed"])
            + display("Falha de rede registrada",
                      row["network_error"] if row["network_error"] else "Nenhuma registrada no contexto disponível")
            + display("Qualidade de captura",
                      row["capture_quality"] if row["capture_quality"] else "N/D")
            + "</dl></section>"
            "<section class='architecture-fact-group'><h5>Limites da descoberta de rede</h5><dl>"
            + display("DNS, IPs públicos e servidores", "N/D (não atestados nesta projeção)")
            + display("Detalhes do certificado e negociação TLS", "N/D (não atestados nesta projeção)")
            + display("CDN, WAF, proxy, balanceador e backend", "N/D (topologia não determinável)")
            + display("Recursos e subframes carregados em runtime",
                      "N/D (inventário de requests/frames não materializado aqui)")
            + "</dl></section></div>"
        )
        hypothesis = row.get("hypothesis")
        if isinstance(hypothesis, dict):
            parts.append(
                "<p class='architecture-limit'><strong>Hipótese preliminar, não comprovada:</strong> "
                + shown(ARCH_LABELS.get(hypothesis.get("candidate"), hypothesis.get("structure") or "N/D"))
                + "; confiança qualitativa " + shown({"LOW": "baixa"}.get(
                    hypothesis.get("confidence"), "não determinada"))
                + ". Não substitui classificação da captura.</p>"
            )
        parts.append(
            "<p class='architecture-limit'><strong>Fronteira observacional:</strong> "
            "contagens de tags no HTML inicial não demonstram carregamento bem-sucedido "
            "de CSS, JavaScript ou subframes; resposta HTTP e número de redirecionamentos "
            "não comprovam a topologia de infraestrutura. Não houve nova coleta de rede "
            "para gerar esta apresentação.</p></article>"
        )
    return "".join(parts) + "</div></div>"


__all__ = ["read_architecture_audit_facts", "architecture_audit_facts_html", "VERSION"]
