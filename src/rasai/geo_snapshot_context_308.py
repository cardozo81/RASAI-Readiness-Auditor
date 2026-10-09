"""#308/#309: conservative, read-only GEO snapshot cross-reference.

Only display derived GEO facts when the saved snapshot belongs to the latest
chronologically verifiable Search API attempt of THIS AUD. No provider, write,
reprocessing, retry, stale-success promotion or inference of generative cites.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import re
import sqlite3
from typing import Any

from rasai.geo_temporal_provenance import (
    _UNVERIFIABLE, _columns, _last_temporally_verified,
)

_ALLOWED_VERSIONS = frozenset(
    f"RASAI-GEO-OBSERVATION-{n}" for n in (5, 6, 7, 8)
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TARGET_STATES = frozenset({
    "EXACT_URL_OBSERVED", "DOMAIN_ALTERNATIVE_OBSERVED",
    "TARGET_NOT_IN_RETURNED_SOURCES",
})


def _validated_projection(
    audit_id: str, run_id: str, record: tuple,
) -> dict[str, Any] | None:
    analysis_id, stored_run_id, contract_version, input_sha, raw = record
    if (
        not all(isinstance(x, str) for x in (
            analysis_id, stored_run_id, contract_version, input_sha, raw
        ))
        or stored_run_id != run_id
        or contract_version not in _ALLOWED_VERSIONS
        or _SHA.fullmatch(input_sha) is None
    ):
        return None
    expected_id = "GEO-" + sha256(
        (audit_id + ":" + contract_version + ":" + input_sha).encode("utf-8")
    ).hexdigest()[:32].upper()
    if analysis_id != expected_id:
        return None
    try:
        projection = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(projection, dict)
        or projection.get("audit_id") != audit_id
        or projection.get("perplexity_run_id") != run_id
        or projection.get("contract_version") != contract_version
        or projection.get("search_status") != "SUCCESS"
        or not isinstance(projection.get("queries"), list)
        or len(projection["queries"]) != 1
        or not isinstance(projection["queries"][0], str)
        or not projection["queries"][0].strip()
        or not isinstance(projection.get("target_observation"), dict)
    ):
        return None
    target = projection["target_observation"]
    if (
        target.get("evidence_run_id") != run_id
        or target.get("status") not in _TARGET_STATES
        or not isinstance(target.get("query"), str)
        or target["query"].strip().casefold()
           != projection["queries"][0].strip().casefold()
    ):
        return None
    return projection


def persisted_geo_scope(
    con: sqlite3.Connection, audit_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Prove latest-request linkage, not provider truth or market comparability.

    Intentionally no historical backfill: an old success is not current when
    the latest attempt failed, is missing clocks, or has no valid snapshot.
    """
    run = _last_temporally_verified(
        con, table="perplexity_search_runs", audit_id=audit_id,
        columns=("run_id", "status"), time_column="started_at",
    )
    if run is _UNVERIFIABLE:
        return "LATEST_REQUEST_CHRONOLOGY_UNVERIFIABLE", None
    if run is None:
        return "NO_PERSISTED_SEARCH", None
    run_id, state = run
    if state != "SUCCESS":
        return "LATEST_SEARCH_NOT_SUCCESSFUL", None
    cols = _columns(con, "geo_observation_runs")
    if not {
        "analysis_id", "audit_id", "perplexity_run_id",
        "contract_version", "input_sha256", "projection_json",
        "created_at",
    }.issubset(cols):
        return "NO_SNAPSHOT_TABLE", None
    last = _last_temporally_verified(
        con, table="geo_observation_runs", audit_id=audit_id,
        columns=(
            "analysis_id", "perplexity_run_id", "contract_version",
            "input_sha256", "projection_json",
        ), time_column="created_at",
    )
    if last is _UNVERIFIABLE:
        return "SNAPSHOT_CHRONOLOGY_UNVERIFIABLE", None
    if last is None:
        return "NO_PERSISTED_SNAPSHOT", None
    if last[1] != run_id:
        return "SNAPSHOT_NOT_FROM_LATEST_REQUEST", None
    verified = _validated_projection(audit_id, run_id, last)
    if verified is None:
        return "SNAPSHOT_RECORD_UNVERIFIABLE", None
    return "SAME_AUD_CURRENT_SEARCH_SNAPSHOT", verified


def _text(value: object, max_len: int = 160) -> str:
    return escape(str(value or "N/D")[:max_len])


def geo_snapshot_context_html(
    con: sqlite3.Connection, audit_id: str, surface: str,
) -> str:
    """Only semantic cross-references: no new finding, priority or score."""
    if surface not in {
        "CAT-01", "CAT-03", "CAT-05", "CAT-08", "CAT-09",
        "index", "directed-analysis", "ai-integrations",
    }:
        return ""
    status, projection = persisted_geo_scope(con, audit_id)
    # A missing snapshot is not proof of missing opportunities or of GEO
    # failure. Existing catalog crossrefs remain available separately.
    if projection is None:
        return (
            "<p class='muted' data-geo-crossref='abstained'>"
            "Correlação GEO por snapshot: N/D (" + _text(status) +
            "). Não reutilizar sucesso anterior nem refazer buscas.</p>"
        )
    target = projection["target_observation"]
    target_state = target["status"]
    query = projection["queries"][0]
    raw_overlap = projection.get("descriptive_overlap")
    details = (
        "<p data-geo-crossref='snapshot'>Snapshot GEO persistido e vinculado "
        "à última busca bem-sucedida da própria AUD. Consulta: <code>"
        + _text(query) + "</code>; classificação de retorno: <code>"
        + _text(target_state) + "</code>. "
        "Fontes externas são resultados de Search API, não citações "
        "comprovadas em respostas generativas.</p>"
    )
    if surface in {"CAT-01", "CAT-03", "CAT-08", "CAT-09"}:
        if surface == "CAT-01":
            return details + (
                "<p>Esta observação não comprova defeito técnico de crawling, "
                "robots, renderização ou indexação; correlacionar apenas com "
                "evidências técnicas identificadas no CAT-01.</p>"
            )
        if surface == "CAT-03":
            if target_state == "TARGET_NOT_IN_RETURNED_SOURCES":
                return details + (
                    "<p>A URL não apareceu entre as fontes retornadas nesta "
                    "consulta observada. Revisar cobertura de intenção e "
                    "clareza da oferta; ausência não prova causa técnica.</p>"
                )
            if target_state == "DOMAIN_ALTERNATIVE_OBSERVED":
                return details + (
                    "<p>A busca retornou outra URL do domínio, não a URL exata. "
                    "Avaliar relação entre páginas e intenção sem presumir "
                    "canonical, redirecionamento ou preferência da IA.</p>"
                )
            return details + (
                "<p>A URL exata apareceu nas fontes desta consulta; não "
                "implica citação em resposta de IA nem qualidade do texto.</p>"
            )
        if surface == "CAT-08":
            return details + (
                "<p>Contexto para priorização humana: cruzar com achados "
                "evidenciados no CAT-03/CAT-05; o status externo não muda "
                "prioridade, impacto, esforço ou score de nenhuma ação.</p>"
            )
        action = target.get("recommendation")
        return details + (
            "<p>Orientação determinística da observação: "
            + _text(action, 320)
            + ". Validar com achado e responsável; isto não cria, substitui "
            "ou pontua uma recomendação canônica.</p>"
        )
    if surface in {"index", "directed-analysis", "ai-integrations"}:
        suffix = {
            "index": (
                "Indicador de fonte pontual, sem previsão de visibilidade "
                "e sem avaliação causal sobre o conteúdo."
            ),
            "directed-analysis": (
                "A presença do snapshot não demonstra que a análise "
                "direcionada o consumiu. Checar referências da análise."
            ),
            "ai-integrations": (
                "Gasto/billability dependem do ledger da integração, "
                "não deste snapshot; não somar custos nem inferir cobrança."
            ),
        }[surface]
        return details + "<p>" + suffix + "</p>"
    # CAT-05: provide observable denominators only for a single exact
    # textual query and a deliberately descriptive, temporally gated
    # overlap. Never claim equivalence of market/device/intent.
    if not isinstance(raw_overlap, dict) or raw_overlap.get("status") != "DESCRIPTIVE_ONLY":
        return details + (
            "<p>Sobreposição SERP × Perplexity: N/D. "
            "Consulta, janela ou denominadores não comparáveis.</p>"
        )
    p = raw_overlap.get("perplexity_denominator")
    s = raw_overlap.get("serp_denominator")
    common = raw_overlap.get("common_urls")
    if (
        any(type(v) is not int or v < 0 for v in (p, s, common))
        or p == 0 or s == 0 or common > min(p, s)
    ):
        return details + (
            "<p>Sobreposição SERP × Perplexity: N/D "
            "(denominadores persistidos inconsistentes).</p>"
        )
    return details + (
        "<p>Sobreposição descritiva de URLs exatas SERP × Perplexity: "
        + str(common) + " em comum; SERP " + str(common) + "/"
        + str(s) + "; Perplexity " + str(common) + "/" + str(p)
        + ". Denominadores: URLs distintas válidas retornadas por "
        "cada fonte. Coincidência textual e janela de coleta "
        "não comprovam equivalência de intenção, geografia, idioma, "
        "dispositivo, ranking ou resultado gerativo.</p>"
    )
