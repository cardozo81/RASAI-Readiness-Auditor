"""Advisory Apdex sample sufficiency from persisted M23/M25 evidence only.

Never recalculates Apdex, samples a browser, writes audit.db or infers RUM
confidence intervals. This is an interpretation of the stored *group labels*,
not a statistical confidence interval or a measure of application correctness.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3


_TABLE = {
    "CAT-06": "synthetic_apdex_summaries",
    "CAT-07": "synthetic_ux_apdex_summaries",
}


def apdex_sampling_reliability_html(
    database: Path, audit_id: str, catalog_id: str, *, compact: bool = False,
) -> str:
    """Report evidence-backed sample sufficiency, never probabilistic confidence."""
    table = _TABLE.get(catalog_id)
    if table is None:
        return ""
    rows: list[tuple[object, object, object]] = []
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as con:
            found = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone()
            if found:
                columns = {item[1] for item in con.execute("PRAGMA table_info(" + table + ")")}
                if {"audit_id", "valid_samples", "small_group", "final_group"} <= columns:
                    where = "audit_id=?"
                    # CAT-07 population-mode outputs are not the per-URL baseline
                    # groups used to interpret the regular experience Apdex.
                    if catalog_id == "CAT-07" and "device" in columns:
                        where += " AND UPPER(COALESCE(device,'')) <> 'POPULATION'"
                    rows = con.execute(
                        "SELECT valid_samples,small_group,final_group FROM " + table
                        + " WHERE " + where + " ORDER BY rowid", (audit_id,),
                    ).fetchall()
    except (OSError, sqlite3.Error, ValueError):
        rows = []

    prefix = (
        ("<p>" if compact else "<div class='notice'>")
        + "<strong>Confiabilidade da interpretação do Apdex:</strong> "
    )
    closing_tag = "</p>" if compact else "</div>"
    if not rows:
        return prefix + (
            "não determinável nesta auditoria: resumo por grupo ausente ou "
            "esquema de evidência insuficiente. Não presumir amostra representativa." + closing_tag
        )
    try:
        parsed = [(int(v), int(s), int(f)) for v, s, f in rows]
    except (TypeError, ValueError, OverflowError):
        return prefix + (
            "indeterminada: contagens ou estados de grupos inválidos na evidência." + closing_tag
        )
    # M23: final_group means >= normal methodological minimum (100).
    # M25: final_group means configured *operational target reached*, which
    # legitimately coexists with small_group for target=3 (3/3 complete).
    # Never conflate run completion with inferential sample sufficiency.
    if any(
        v < 1 or s not in (0, 1) or f not in (0, 1)
        or (s == 1 and v >= 100) or (s == 0 and v < 100)
        or (catalog_id == "CAT-06" and (f != int(v >= 100)))
        for v, s, f in parsed
    ):
        return prefix + (
            "indeterminada: metadados de grupos inválidos ou incompatíveis "
            "com o mínimo metodológico normal. Revisar a evidência persistida." + closing_tag
        )
    n = len(parsed)
    small = sum(s for _, s, _ in parsed)
    counts = [v for v, _, _ in parsed]
    suffix = (
        f" Grupos observados: {n}; amostras válidas por grupo: "
        + (str(counts[0]) if n == 1 else f"{min(counts)}–{max(counts)}")
        + ". O contrato classifica grupo normal a partir de 100 amostras "
        "válidas por URL/dispositivo. Esse limite não produz, por si, "
        "intervalo de confiança estatística, representatividade de usuários "
        "reais ou garantia de repetibilidade."
    )
    if catalog_id == "CAT-07":
        complete = sum(f for _, _, f in parsed)
        suffix += (
            f" No CAT-07, 'grupo final' marca apenas a meta operacional "
            f"atingida ({complete}/{n} grupo(s)); não define suficiência "
            "estatística para generalização."
        )
    if small == n:
        return prefix + (
            "<strong>LIMITADA para generalização (grupos pequenos).</strong>"
            + escape(suffix)
            + " A execução pode ter cumprido integralmente a meta configurada, "
            "mas o tamanho da amostra restringe conclusões gerais; "
            "o Apdex continua sendo o índice das amostras efetivamente observadas." + closing_tag
        )
    if small:
        return prefix + (
            f"<strong>HETEROGÊNEA: {small}/{n} grupo(s) pequenos.</strong>"
            + escape(suffix)
            + " Não generalizar o resultado dos grupos pequenos como se "
            "tivessem a mesma cobertura dos demais." + closing_tag
        )
    return prefix + (
        "<strong>MÍNIMO METODOLÓGICO ATINGIDO (grupos normais).</strong>"
        + escape(suffix)
        + " A classificação normal não equivale a confiança estatística "
        "quantificada nem a dados de usuários reais." + closing_tag
    )
