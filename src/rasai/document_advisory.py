"""Offline companion report over immutable persisted AUD evidence.

Run with ``python -m rasai.document_advisory --help``. Never opens AuditPersistence
or initializes SQLite. All historical bytes, including old HTML, are protected.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from rasai.contextual_documents import CONTRACT, digest, discover_references, reference_url, stable_id
from rasai.document_relationships import evidence_span, relate
from rasai.document_text import extract_document
from rasai.domain import AuditStatus, CompletionStatus, DeviceContext, PageSnapshot


def _discover(*, audit_id, snapshot, original, artifact_ref, surface):
    """Bound HTML parser time/memory; degrade without inferring absence."""
    if original is None:
        return discover_references(audit_id=audit_id, snapshot=snapshot, original=None,
                                   artifact_ref=artifact_ref, surface=surface)
    payload = dict(audit_id=audit_id, snapshot_id=snapshot.snapshot_id, page_id=snapshot.page_id,
                   device=snapshot.device.value, requested_url=snapshot.requested_url,
                   final_url=snapshot.final_url, captured_at=snapshot.captured_at.isoformat(),
                   original=base64.b64encode(original).decode("ascii"), artifact_ref=artifact_ref, surface=surface)
    try:
        child = subprocess.run([sys.executable, "-m", "rasai.document_discovery_worker"],
                               input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=5, check=False)
        if child.returncode == 0 and len(child.stdout) <= 5_000_000:
            return json.loads(child.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    result = discover_references(audit_id=audit_id, snapshot=snapshot, original=None,
                                 artifact_ref=artifact_ref, surface=surface)
    result["source_sha256"] = digest(original)
    result["limitations"].append("DISCOVERY_RESOURCE_OR_PARSER_LIMIT_ND")
    return result


def _plain(path: Path) -> Path:
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("symbolic link or junction forbidden")
    return path


def _member(root: Path, reference: str) -> Path:
    if (not isinstance(reference, str) or not reference or len(reference) > 260
            or any(x in reference for x in ("\\", ":", "\x00"))
            or reference.startswith("/") or any(x in {"", ".", ".."} for x in reference.split("/"))):
        raise ValueError("unsafe local artifact reference")
    member = _plain(root / reference)
    if not member.resolve().is_relative_to(root.resolve()):
        raise ValueError("artifact escapes input directory")
    return member


def _read(path: Path, limit: int) -> bytes:
    _plain(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("input unavailable or exceeds byte policy")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input grew beyond byte policy")
    return data


def _inventory(root: Path) -> dict:
    # Protect every file, including original reports. No silent symlink omission.
    entries = {}
    total = 0
    count = 0
    def walk_error(error):
        raise error
    # Inspect directory entries BEFORE descending, including Windows junctions.
    # Eager rglob sorting could enumerate an external junction before rejecting it.
    for directory, directories, files in root.walk(on_error=walk_error, follow_symlinks=False):
        _plain(directory)
        count += len(directories) + len(files)
        if count > 20_000:
            raise ValueError("source inventory exceeds local policy")
        for name in directories:
            _plain(directory / name)
        directories.sort()
        for name in sorted(files):
            file = _plain(directory / name)
            if not file.is_file():
                raise ValueError("source contains non-regular input")
            total += file.stat().st_size
            if total > 2_000_000_000:
                raise ValueError("source inventory exceeds local policy")
            from hashlib import sha256
            hasher = sha256()
            with file.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1_000_000), b""):
                    hasher.update(chunk)
            entries[file.relative_to(root).as_posix()] = hasher.hexdigest()
    return entries


def _snapshots(root: Path) -> list[PageSnapshot]:
    database = _member(root, "audit.db")
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("source must be quiescent without SQLite sidecars")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2)) as con:
        con.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 5
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        identities = con.execute("SELECT audit_id,status,completion_status FROM audits LIMIT 2").fetchall()
        if len(identities) != 1 or identities[0][0] != root.name:
            raise ValueError("physical AUD identity mismatch")
        if (identities[0][1] != AuditStatus.COMPLETED
                or identities[0][2] not in {CompletionStatus.COMPLETE, CompletionStatus.COMPLETE_WITH_LIMITATIONS}):
            raise ValueError("AUD must be COMPLETED with an accepted terminal completion status")
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT s.* FROM page_snapshots s JOIN pages p ON p.page_id=s.page_id "
            "WHERE p.audit_id=? ORDER BY s.snapshot_id LIMIT 201", (root.name,)
        ).fetchall()
        if len(rows) > 200:
            raise ValueError("snapshot cardinality exceeds local policy")
        result = []
        for row in rows:
            captured = datetime.fromisoformat(row["captured_at"])
            if captured.tzinfo is None:
                raise ValueError("capture timestamp requires timezone")
            result.append(PageSnapshot(
                snapshot_id=row["snapshot_id"], page_id=row["page_id"], device=DeviceContext(row["device"]),
                requested_url=row["requested_url"], final_url=row["final_url"], captured_at=captured,
                raw_artifact_ref=row["raw_artifact_ref"], rendered_artifact_ref=row["rendered_artifact_ref"],
                main_content_ref=row["main_content_ref"],
            ))
        return result


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _manifest(path: Path | None) -> tuple[dict, bytes | None]:
    if path is None:
        return {"documents": [], "relationships": []}, None
    raw = _read(path, 200_000)
    data = json.loads(raw, object_pairs_hook=_unique)
    if (not isinstance(data, dict) or set(data) - {"documents", "relationships", "reference_observations"}
            or not {"documents", "relationships"} <= set(data)
            or not isinstance(data["documents"], list) or len(data["documents"]) > 20
            or not isinstance(data["relationships"], list) or len(data["relationships"]) > 500):
        raise ValueError("invalid companion manifest")
    return data, raw


def build_advisory(audit_dir: Path, output: Path, *, manifest_file: Path | None = None,
                   ai: str = "none") -> dict:
    """Publish to a new external directory only after source hash parity.

    IA has no document-specific consent/profile in this release: any requested
    provider is safely unavailable; no callback or arbitrary adapter is invoked.
    """
    root, destination = _plain(audit_dir), _plain(output)
    if not root.is_dir() or not root.name.startswith("AUD-"):
        raise ValueError("complete AUD source directory required")
    if (destination.exists() or destination.resolve().is_relative_to(root.resolve())
            or any(p.name.startswith(("AUD-", "RPR-", "CONS-")) for p in (destination, *destination.parents))):
        raise ValueError("output must be new and external to historical packages")
    if ai not in {"none", "requested"}:
        raise ValueError("unsupported AI mode")
    manifest_path = _plain(manifest_file) if manifest_file else None
    manifest, manifest_raw = _manifest(manifest_path)
    before = _inventory(root)
    captures = []
    snapshots = _snapshots(root)
    for snapshot in snapshots:
        source = None
        artifact = None
        surface = "NOT_CAPTURED"
        limitations = []
        for name, ref in (("RENDERED_DOM", snapshot.rendered_artifact_ref), ("RAW_HTML_FALLBACK", snapshot.raw_artifact_ref)):
            if not ref:
                continue
            if not ref.startswith("artifacts/"):
                raise ValueError("snapshot source outside artifacts")
            path = _member(root, ref)
            if not path.exists():
                limitations.append(name + "_ARTIFACT_MISSING_ND")
                continue
            try:
                source = _read(path, 2_000_000)
            except (OSError, ValueError):
                limitations.append(name + "_UNREADABLE_OR_BYTE_LIMIT_ND")
                continue
            artifact, surface = ref, name
            break
        capture = _discover(audit_id=root.name, snapshot=snapshot, original=source,
                                      artifact_ref=artifact, surface=surface)
        capture["limitations"].extend(limitations)
        captures.append(capture)
    occurrences = {o["occurrence_id"]: (c, o) for c in captures for o in c["occurrences"]}
    observations = manifest.get("reference_observations", [])
    if not isinstance(observations, list) or len(observations) > 500:
        raise ValueError("invalid reference observations")
    for observation in observations:
        if (set(observation) != {"occurrence_id", "artifact_ref", "sha256"}
                or observation["occurrence_id"] not in occurrences
                or not observation["artifact_ref"].startswith("artifacts/")):
            raise ValueError("invalid failure observation binding")
        raw = _read(_member(root, observation["artifact_ref"]), 32_000)
        if digest(raw) != observation["sha256"]:
            raise ValueError("failure observation hash mismatch")
        failure = json.loads(raw, object_pairs_hook=_unique)
        capture, occurrence = occurrences[observation["occurrence_id"]]
        # Supplied persisted failure record is evidence of an observation only.
        # Its URL and timestamp must match this captured reference context.
        if (failure.get("requested_url") != occurrence["resolved_url"]
                or not failure.get("observed_at")
                or datetime.fromisoformat(failure["observed_at"]).tzinfo is None
                or not ((type(failure.get("http_status")) is int and 400 <= failure["http_status"] <= 599)
                        or failure.get("error") in {"TLS_ERROR", "NOT_ACCESSIBLE", "TIMEOUT"})):
            raise ValueError("failure record does not establish inaccessible reference")
        occurrence["reference_state"] = "NOT_ACCESSIBLE"
        occurrence["failure_observation"] = observation | {"basis": "PERSISTED_RECORD_NOT_INDEPENDENTLY_AUTHENTICATED"}
    documents = []
    documents_by_hash = {}
    originals = {}
    document_seals = {}
    for entry in manifest["documents"]:
        required = {"file", "sha256", "media_type", "observed_at", "acquisition_basis", "authorization_ref", "occurrence_ids"}
        if (not isinstance(entry, dict) or set(entry) - required - {"requested_url_observed", "final_url_observed"}
                or not required <= set(entry) or not manifest_path
                or entry["acquisition_basis"] not in {"LOCAL_OPERATOR_SUPPLIED", "PREVIOUSLY_AUTHORIZED"}
                or not isinstance(entry["authorization_ref"], str) or not entry["authorization_ref"].strip()
                or not isinstance(entry["occurrence_ids"], list) or len(entry["occurrence_ids"]) > 500
                or any(oid not in occurrences for oid in entry["occurrence_ids"])):
            raise ValueError("document lacks explicit local provenance or occurrence binding")
        observed = datetime.fromisoformat(entry["observed_at"])
        if observed.tzinfo is None:
            raise ValueError("document observation requires timezone")
        file = _member(manifest_path.parent, entry["file"])
        try:
            raw = _read(file, 4_000_000)
        except (OSError, ValueError):
            raw = None
        if raw is None:
            # Missing/oversized local input is not evidence of remote HTTP failure.
            # No unverified manifest hash may impersonate physical document bytes.
            doc = extract_document(b"", media_type=entry["media_type"])
            doc.update(document_id=stable_id("UNAVAILABLE_LOCAL_INPUT", entry["file"], entry["sha256"]),
                       original_sha256=None, original_bytes=None, original_ref=None,
                       reason="LOCAL_DOCUMENT_UNAVAILABLE_OR_BYTE_LIMIT_ND",
                       original_hash_operator_asserted=entry["sha256"])
        else:
            if digest(raw) != entry["sha256"]:
                raise ValueError("supplied document hash mismatch")
            document_seals[file] = digest(raw)
            doc = extract_document(raw, media_type=entry["media_type"])
        doc.update({k: entry.get(k) for k in ("observed_at", "acquisition_basis", "authorization_ref",
                                             "requested_url_observed", "final_url_observed", "occurrence_ids")})
        # URL labels are retained as operator assertions, never redirect verification.
        doc["origin_verification"] = "OPERATOR_ASSERTED_NOT_INDEPENDENTLY_VERIFIED"
        requested = entry.get("requested_url_observed")
        final = entry.get("final_url_observed")
        doc["redirect_policy"] = (reference_url(requested, final)[1]
                                  if isinstance(requested, str) and isinstance(final, str)
                                  else "REDIRECT_NOT_VERIFIED")
        if raw is not None:
            doc["original_ref"] = "originals/" + doc["document_id"] + ".bin"
            originals[doc["original_ref"]] = raw
        observation = {key: doc[key] for key in ("observed_at", "acquisition_basis", "authorization_ref",
                                                  "requested_url_observed", "final_url_observed", "origin_verification", "redirect_policy")}
        if doc["document_id"] in documents_by_hash:
            existing = documents_by_hash[doc["document_id"]]
            if existing["declared_media_type"] != doc["declared_media_type"]:
                raise ValueError("same original document has conflicting declared media types")
            existing["occurrence_ids"] = list(dict.fromkeys(existing["occurrence_ids"] + doc["occurrence_ids"]))
            existing["observations"].append(observation)
        else:
            doc["observations"] = [observation]
            doc["occurrence_ids"] = list(doc["occurrence_ids"])
            documents.append(doc)
            documents_by_hash[doc["document_id"]] = doc
        for oid in entry["occurrence_ids"]:
            occurrences[oid][1]["reference_state"] = doc["status"]
    by_id = {d["document_id"]: d for d in documents}
    relationships = []
    for edge in manifest["relationships"]:
        if not isinstance(edge, dict) or edge.get("occurrence_id") not in occurrences:
            raise ValueError("relationship occurrence not observed")
        capture, occurrence = occurrences[edge["occurrence_id"]]
        doc = by_id.get(edge.get("document_id"))
        if doc is None:
            # A requested unavailable local document cannot support an edge.
            doc = next((d for d in documents if d.get("original_hash_operator_asserted") == edge.get("document_id")
                        and edge["occurrence_id"] in d["occurrence_ids"]), None)
        if doc is None or edge["occurrence_id"] not in doc["occurrence_ids"]:
            raise ValueError("relationship document not bound to occurrence")
        if doc["status"] != "DOCUMENT_COLLECTED":
            relation = relate(occurrence_id=edge["occurrence_id"], page_id=capture["page_id"],
                             product_candidate=edge.get("product_candidate"), document=doc, spans=[],
                             applicability="INSUFFICIENT_EVIDENCE")
            relation["limitation"] = "DOCUMENT_NOT_EXTRACTED_ND"
            relation["claim_source"] = None
            relationships.append(relation)
            continue
        spans = [evidence_span(doc, **span) for span in edge.get("spans", [])]
        claim = edge.get("claim_literal")
        claim_ref = None
        if claim:
            snap = next(s for s in snapshots if s.snapshot_id == capture["snapshot_id"])
            if not snap.main_content_ref:
                raise ValueError("claim has no canonical captured text")
            claim_file = _member(root, snap.main_content_ref)
            claim_bytes = _read(claim_file, 2_000_000)
            if claim not in claim_bytes.decode("utf-8"):
                raise ValueError("claim literal absent from captured page text")
            claim_text = claim_bytes.decode("utf-8")
            claim_ref = {"artifact_ref": snap.main_content_ref, "sha256": digest(claim_bytes),
                         "start": claim_text.index(claim), "end": claim_text.index(claim) + len(claim)}
        allowed = {k: edge.get(k) for k in ("product_candidate", "version_observed", "effective_observed", "claim_literal")}
        relation = relate(occurrence_id=edge["occurrence_id"], page_id=capture["page_id"], document=doc,
                          spans=spans, applicability=edge.get("applicability", "INSUFFICIENT_EVIDENCE"),
                          basis=edge.get("basis", "OPERATOR_HYPOTHESIS"), **allowed)
        relation["claim_source"] = claim_ref
        relationships.append(relation)
    report = {"contract": CONTRACT, "audit_id": root.name, "captures": captures,
              "documents": documents, "relationships": relationships,
              "ai": {"mode": ai, "state": "DISABLED" if ai == "none" else "UNAVAILABLE",
                     "reason": "NO_DOCUMENT_CONSENT_PROFILE" if ai != "none" else None,
                     "provider_calls": 0, "cost": None},
              "source_inventory": before, "manifest_sha256": digest(manifest_raw) if manifest_raw else None,
              "source_unchanged": False, "network_requests": 0, "audit_writes": 0,
              "limitations": ["CONSULTATIVE_ONLY", "NO_INDEPENDENT_SOURCE_AUTHENTICATION",
                              "ACTIVE_ACQUISITION_DISABLED", "PRIVATE_LOCAL_OUTPUT_DO_NOT_PUBLISH"]}
    from rasai.document_advisory_html import render_advisory
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".document-advisory-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "companion"
        stage.mkdir()
        for ref, raw in originals.items():
            target = stage / ref
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(raw)
        if (_inventory(root) != before or any(digest(_read(p, 4_000_000)) != seal for p, seal in document_seals.items())
                or (manifest_path and _read(manifest_path, 200_000) != manifest_raw)):
            raise ValueError("source identity/hash changed; publication refused")
        report["source_unchanged"] = True
        (stage / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (stage / "index.html").write_text(render_advisory(report), encoding="utf-8")
        _plain(destination)
        if destination.exists() or _inventory(root) != before:
            raise ValueError("output collision or source changed before publication")
        stage.rename(destination)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inventário documental passivo, sem rede ou alteração da AUD.")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--ai", choices=("none", "requested"), default="none")
    args = parser.parse_args(argv)
    try:
        build_advisory(args.audit_dir, args.output, manifest_file=args.manifest, ai=args.ai)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        print("N/D: entrada, integridade ou limites recusados; nenhum provedor foi chamado.")
        return 2
    print("Relatório companheiro local criado; origem intacta, sem coleta ou revisão independente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
