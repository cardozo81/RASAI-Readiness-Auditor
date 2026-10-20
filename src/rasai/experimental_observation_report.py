"""Read-only consultative CAT-06/CAT-07 and FAQ companion report (#322/#652).

Only source-bound, immutable experimental sidecars are eligible. HTML stays
outside the sealed AUD and report-catalog; no scoring or provider requests.
This output cannot turn same-DOM receipt into independent human homologation.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from rasai.apdex_readiness_sidecar import (
    _original, read_readiness_sidecar,
)

_MAX_READINESS = 128
_MAX_FAQ = 2
_FAQ_LIMIT = 4 * 1024 * 1024
_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _readiness(aud: Path) -> tuple[list[dict], int]:
    folder = aud.parent / ".rasai-readiness-sidecars" / aud.name
    if folder.is_symlink() or folder.parent.is_symlink():
        raise ValueError("untrusted readiness folder")
    if not folder.exists():
        return [], 0
    if not folder.is_dir():
        raise ValueError("invalid readiness folder")
    names = sorted(folder.iterdir())
    if len(names) > _MAX_READINESS:
        raise ValueError("readiness evidence exceeds display budget")
    valid: list[dict] = []
    rejected = 0
    seen = set()
    for path in names:
        if path.name.startswith(".pending-"):
            continue
        try:
            if path.is_symlink() or not _NAME.fullmatch(path.name):
                raise ValueError("unsafe sidecar name")
            evidence = read_readiness_sidecar(aud, path)
            observation = evidence["observation"]
            sample_key = (
                observation["sample_id"], observation["page_id"],
                observation["device"],
            )
            if sample_key in seen:
                raise ValueError("ambiguous readiness sample identity")
            # A digest-bound sidecar may have been rehashed by a local actor.
            # Recheck its physical sample key against the SEALED audit.db,
            # not just against its producer-declared identity.
            with sqlite3.connect(
                (aud / "audit.db").resolve().as_uri() + "?mode=ro&immutable=1",
                uri=True, timeout=1,
            ) as connection:
                connection.execute("PRAGMA query_only=ON")
                matches = connection.execute(
                    "SELECT COUNT(*) FROM synthetic_ux_apdex_samples "
                    "WHERE audit_id=? AND sample_id=? AND page_id=? AND device=?",
                    (aud.name, observation["sample_id"], observation["page_id"],
                     observation["device"]),
                ).fetchone()[0]
            if matches != 1:
                raise ValueError("readiness sidecar does not identify exactly one persisted sample")
            seen.add(sample_key)
            valid.append(observation)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            rejected += 1
    return valid, rejected


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicated FAQ JSON key")
        result[name] = value
    return result


def _faq(aud: Path) -> tuple[list[dict], int]:
    """Hash check only; no untrusted receipt marked as externally attested."""
    folder = aud.parent / ".rasai-faq-sidecars" / aud.name
    if folder.is_symlink() or folder.parent.is_symlink():
        raise ValueError("untrusted FAQ folder")
    if not folder.exists():
        return [], 0
    if not folder.is_dir():
        raise ValueError("invalid FAQ folder")
    files = sorted(folder.iterdir())
    if len(files) > _MAX_FAQ + 8:
        raise ValueError("FAQ evidence exceeds display budget")
    observed: list[dict] = []
    rejected = 0
    for path in files:
        if path.name.startswith(".pending-"):
            continue
        try:
            if (path.is_symlink() or not _NAME.fullmatch(path.name)
                    or not path.is_file() or path.stat().st_size > _FAQ_LIMIT):
                raise ValueError("invalid FAQ sidecar")
            blob = path.read_bytes()
            if len(blob) > _FAQ_LIMIT or sha256(blob).hexdigest() + ".json" != path.name:
                raise ValueError("FAQ sidecar checksum mismatch")
            obj = json.loads(
                blob.decode("utf-8"), object_pairs_hook=_unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            )
            scope = obj["scope"]
            if (
                not isinstance(scope, dict)
                or scope.get("audit_id") != aud.name
                or obj["contract_version"] != "RASAI-FAQ-SAME-SAMPLE-SIDECAR-001"
                or obj.get("advisory_only") is not True
                or obj.get("same_persisted_browser_session_independently_attested") is not False
                or obj.get("crawler_discovery_verified") is not False
                or obj.get("score_change_authorized") is not False
            ):
                raise ValueError("FAQ evidence source or limits unverifiable")
            observed.append({
                "page_id": scope.get("page_id", ""),
                "snapshot_id": scope.get("snapshot_id", ""),
                "device": scope.get("device", ""),
                "status": "APOS_CLIQUE_DECLARADO_SEM_HOMOLOGACAO",
                "file_sha256": sha256(blob).hexdigest(),
            })
        except (OSError, UnicodeError, ValueError, TypeError, KeyError):
            rejected += 1
    return observed, rejected


def _table(headings: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    table_head = "".join("<th scope='col'>" + _e(x) + "</th>" for x in headings)
    content = "".join(
        "<tr>" + "".join("<td>" + _e(x) + "</td>" for x in row) + "</tr>"
        for row in rows
    )
    if not content:
        content = "<tr><td colspan='" + str(len(headings)) + "'>Sem evidência elegível nesta AUD.</td></tr>"
    return "<table><thead><tr>" + table_head + "</tr></thead><tbody>" + content + "</tbody></table>"


def _ms(value: object) -> str:
    return f"{value:.1f} ms" if type(value) in {float, int} else "N/D"


def _document(audit_id: str, records: list[dict], rejected: int,
              faq: list[dict], faq_rejected: int) -> bytes:
    statuses = Counter(item["status"] for item in records)
    rows = []
    for item in records:
        state = item["status"]
        meaningful = state == "OBSERVED"
        delta = item["post_load_delta_ms"] if meaningful else None
        verdict = (
            "Prontidão posterior ao load; Apdex não alterado"
            if meaningful and type(delta) in (float, int) and delta > 0
            else "Prontidão observada sem atraso pós-load"
            if meaningful else "Não observada ou não aplicável; nenhum sucesso inferido"
        )
        rows.append((
            item["sample_id"], item["page_id"], item["device"],
            item["architecture"], state, _ms(item["load_ms"]),
            _ms(item["primary_content_ms"]) if meaningful else "N/D",
            _ms(delta) if meaningful else "N/D", verdict,
        ))
    if faq:
        faq_rows = [(v["page_id"], v["snapshot_id"], v["device"],
                     "Após clique (recibo local, homologação pendente)",
                     v["file_sha256"]) for v in faq]
    else:
        faq_rows = [("N/D", "N/D", "N/D",
                     "Sem interação registrada; não equivale à ausência editorial",
                     "N/D")]
    status_line = ", ".join(f"{_e(state)}: {count}" for state,count in sorted(statuses.items()))
    if not status_line:
        status_line = "Nenhuma prontidão experimental verificada"
    style = """body{font:16px/1.5 system-ui,sans-serif;color:#172234;background:#f5f7fa;margin:0 auto;max-width:1120px;padding:34px}
h1,h2{color:#152c47}section{background:white;padding:20px;margin:18px 0;border:1px solid #d8dee9;border-radius:9px}
.badge{display:inline-block;background:#e6eef7;padding:4px 12px;border-radius:20px;color:#24466d}
.warning{border-left:4px solid #b36b09;padding:9px 12px;background:#fff5e5}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #dce2e9;padding:9px;text-align:left;word-break:break-word}th{background:#ecf2f8}
small{color:#46596e}"""
    content = (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
        "<title>Observações consultivas de experiência e FAQ</title>"
        "<style>" + style + "</style></head><body>"
        "<h1>Observações experimentais de experiência e FAQ</h1>"
        "<p class='badge'>Somente leitura / fora da AUD selada</p>"
        "<p>Auditoria: <strong>" + _e(audit_id) + "</strong>. "
        "Não recalcula SARI, Apdex, SCORE-GEO nem comprova indexação.</p>"
        "<section id='cat06'><h2>CAT-06 | Apdex de carregamento versus prontidão de conteúdo</h2>"
        "<p class='warning'>Apdex de carregamento e prontidão de conteúdo não são métricas equivalentes. "
        "O indicador experimental não modifica o índice já persistido.</p>"
        "<p>" + status_line + " | Recusados por integridade: " + str(rejected) + "</p>"
        + _table(
            ("Amostra", "Página", "Dispositivo", "Arquitetura",
             "Estado consultivo", "Load", "Conteúdo principal",
             "Atraso pós-load", "Interpretação"),
            rows,
        ) + "</section>"
        "<section id='cat07'><h2>CAT-07 | Experiência sintética e evidência física</h2>"
        "<p>Somente observações cujo sidecar e fonte AUD foram verificados em leitura. "
        "A identidade de amostra foi atribuída ao coletor, sem equivalência com RUM; "
        "observações censuradas permanecem N/D.</p>"
        "<p>Registros aceitos: <strong>" + str(len(records)) + "</strong>; "
        "recusados: " + str(rejected) + ".</p></section>"
        "<section id='faq'><h2>FAQ | Antes de interação, após clique e não verificado</h2>"
        "<p class='warning'>Recibos FAQ são de origem local, com arquivo íntegro por digest. "
        "Sem chave e homologação física externa, esta visão não revalida assinatura nem mesma sessão "
        "por autoridade independente. Ausência de clique não prova ausência editorial.</p>"
        + _table(
            ("Página", "Snapshot", "Dispositivo", "Evidência", "Digest local"),
            faq_rows,
        ) + "<p>Recibos FAQ não elegíveis: " + str(faq_rejected) + ".</p></section>"
        "<footer><small>Relatório derivado offline sem JavaScript, sem links externos e sem coleta.</small></footer>"
        "</body></html>"
    )
    return content.encode("utf-8")


def render_experimental_observation_report(aud_dir: str | Path) -> Path | None:
    """Produce one immutable hash-named supplemental HTML, never edit report-catalog."""
    aud = Path(aud_dir)
    verified_id, _, _ = _original(aud)
    if verified_id != aud.name:
        raise ValueError("AUD not sealed or physical identity changed")
    records, rejected = _readiness(aud)
    faq, faq_rejected = _faq(aud)
    if not records and not rejected and not faq and not faq_rejected:
        return None
    payload = _document(aud.name, records, rejected, faq, faq_rejected)
    folder = aud.parent / ".rasai-experimental-reports" / aud.name
    if folder.parent.is_symlink() or folder.is_symlink():
        raise ValueError("unsafe supplemental report location")
    folder.mkdir(parents=True, exist_ok=True)
    name = sha256(payload).hexdigest() + ".html"
    target = folder / name
    if target.is_symlink():
        raise ValueError("report path is a symlink")
    fd, stage = tempfile.mkstemp(prefix=".pending-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(stage, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != payload:
                raise ValueError("existing report was modified")
    finally:
        Path(stage).unlink(missing_ok=True)
    return target


def main(argv: list[str] | None = None) -> int:
    """Explicit post-AUD rendering, without provider or audit runtime."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Relatório independente CAT-06/CAT-07/FAQ consultivo."
    )
    parser.add_argument("--aud-dir", type=Path, required=True)
    opts = parser.parse_args(argv)
    try:
        path = render_experimental_observation_report(opts.aud_dir)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"fonte experimental não verificável: {type(exc).__name__}")
    if path is None:
        print("Nenhum sidecar experimental para esta AUD.")
    else:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["render_experimental_observation_report", "main"]
