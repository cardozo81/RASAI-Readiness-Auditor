"""Supported, isolated read-only rematerialization of an existing AUD report.

Unlike the internal low-level HTML renderer, this command installs the same canonical
report/runtime bindings as the regular audit CLI. It never executes an AUD or RPR;
the original workspace is not used for output or opened for writing.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
from typing import Iterator


def _input_files(root: Path) -> dict[str, str]:
    """Immutable input inventory: report-catalog is a generated output, not evidence."""
    result: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        relative = item.relative_to(root)
        if relative.parts[0] == "report-catalog":
            continue
        digest = hashlib.sha256()
        with item.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result[relative.as_posix()] = digest.hexdigest()
    return result


def _check_audit(source: Path) -> str:
    if not source.is_dir() or not (source / "artifacts").is_dir():
        raise ValueError("A origem precisa ser a pasta completa de uma AUD, com artifacts.")
    database = source / "audit.db"
    if not database.is_file():
        raise ValueError("audit.db ausente na origem.")
    # SQLite URI mode=ro: no schema initialization or fallback writes to the source.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT audit_id FROM audits").fetchall()
        if len(rows) != 1 or str(rows[0][0]) != source.name or not source.name.startswith("AUD-"):
            raise ValueError("Pasta e identidade persistida da AUD divergem.")
    finally:
        connection.close()
    return source.name


def _check_composition() -> None:
    """Fail closed instead of publishing a partial renderer binding silently."""
    from rasai import (
        accepted_audit_refinements as accepted,
        catalog_projection_consistency as projection,
        catalog_report_page as page,
        catalog_report_site as site,
        execution_consistency_runtime as consistency,
        post_smoke_alignment as alignment,
    )
    if not all((
        accepted._INSTALLED,
        projection._INSTALLED,
        consistency._INSTALLED,
        alignment._INSTALLED,
        getattr(site.materialize_catalog_report_site, "_rasai_execution_consistency", False),
        site._catalog_body is page._catalog_body,
        site._standards_summary is page._standards_summary,
    )):
        raise RuntimeError(
            "Composicao canonica de relatorios incompleta. "
            "Execute pelo entrypoint oficial: rasai rematerialize-report."
        )


@contextmanager
def _forbid_network() -> Iterator[None]:
    """An explicit defense against accidental egress in a reporting-only operation."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection

    def blocked(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("Coleta/rede proibida durante rematerializacao read-only.")

    socket.socket.connect = blocked  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = blocked  # type: ignore[method-assign,assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign,assignment]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign,assignment]
        socket.create_connection = original_create  # type: ignore[assignment]


def rematerialize(*, audit_dir: str | Path, output_root: str | Path) -> Path:
    """Copy first, then project with canonical bindings, preserving the original AUD."""
    from rasai import entrypoint
    from rasai.catalog_report_site import (
        _source_fingerprint, _sqlite_logical_digest, verify_catalog_report_package,
    )
    from rasai.execution_consistency_runtime import _publication_state
    from rasai.persistence import AuditWorkspace
    from rasai import report_completion

    source = Path(audit_dir).expanduser().resolve(strict=True)
    audit_id = _check_audit(source)
    output = Path(output_root).expanduser().resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError("Saida nao pode residir dentro da AUD de origem.")
    destination = output / audit_id
    if destination.exists():
        raise FileExistsError(f"Saida ja existe: {destination}")
    # Installation only: never invoke audit/reprocess or mutable data finalizers.
    entrypoint._install_audit_runtime()
    _check_composition()
    before = _input_files(source)
    if not before:
        raise ValueError("AUD de origem sem arquivos persistidos.")
    output.mkdir(parents=True, exist_ok=True)
    stage_parent = Path(tempfile.mkdtemp(prefix=".rasai-report-141-", dir=output))
    stage = stage_parent / audit_id
    try:
        shutil.copytree(source, stage, symlinks=False)
        if before != _input_files(source) or before != _input_files(stage):
            raise RuntimeError("A origem mudou durante a copia: nao publicar.")

        workspace = AuditWorkspace.open(stage)
        with _forbid_network():
            outcome = report_completion.materialize_catalog_report_projection(
                audit_id=audit_id, workspace=workspace,
            )
        if outcome.renderer_errors:
            raise RuntimeError("Projecao canonica falhou: " + "; ".join(outcome.renderer_errors))

        report = stage / "report-catalog"
        manifest = json.loads((report / "manifest.json").read_text(encoding="utf-8"))
        valid, problems = verify_catalog_report_package(report)
        if not valid:
            raise RuntimeError("Pacote inconsistente: " + "; ".join(problems))
        expected = _publication_state(workspace.database, audit_id)
        if manifest.get("freshness") != expected:
            raise RuntimeError(
                f"Estado publicado diverge do fulfillment: {manifest.get('freshness')} != {expected}"
            )
        snapshot = manifest.get("audit_snapshot") or {}
        if (manifest.get("source_fingerprint") != _source_fingerprint(workspace.database)
                or snapshot.get("source_logical_sha256") != _sqlite_logical_digest(workspace.database)):
            raise RuntimeError("Projecao nao corresponde ao audit.db persistido.")
        if before != _input_files(source) or before != _input_files(stage):
            raise RuntimeError("Materializacao alterou a evidencia persistida: nao publicar.")
        if destination.exists():
            raise FileExistsError(f"Saida passou a existir durante a materializacao: {destination}")
        stage.rename(destination)
        return destination / "report-catalog" / "index.html"
    finally:
        # Failure never publishes a staged report or alters the original source.
        shutil.rmtree(stage_parent, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rasai rematerialize-report",
        description="Regenera o HTML de uma AUD em copia isolada, sem coletar nem reprocessar.",
    )
    parser.add_argument("--audit-dir", type=Path, required=True, help="Pasta original AUD-*")
    parser.add_argument(
        "--output-root", type=Path, required=True,
        help="Pasta separada onde criar <output-root>/<AUD-ID>/report-catalog",
    )
    args = parser.parse_args(argv)
    try:
        entry = rematerialize(audit_dir=args.audit_dir, output_root=args.output_root)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(2, f"ERRO: {exc}\n")
    print("RELATORIO:", entry)
    print("MANIFESTO:", entry.parent / "manifest.json")
    print("REMODELAGEM_READ_ONLY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
