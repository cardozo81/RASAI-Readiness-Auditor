"""Prepare a private, UNSIGNED documentary handoff from a sealed #603 AUD.

Only the historical AUD can provide the exact snapshot identity and observed
text. Real official conditions and an authorized signed reviewer receipt must
still be furnished independently. Never output the claim or document bytes.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Sequence

from CLAIM_603_WINDOWS_ACCEPTANCE import AUD_ID, _candidates, _inspect_aud, _utc_day
from rasai.claim_aud_binding import _ref_file
from rasai.geo_query_ledger import _audit_digest

# Candidate detection is an operator convenience, NOT a legal classification.
_PATTERNS = (
    r"\b24\s*(?:horas?|h)\b",
    r"\bcancelament\w*",
    r"\bcar[êe]ncia\b",
    r"\bcobertur\w*",
    r"\bpagament\w*",
)


def _literal_candidate(raw_text: str) -> str | None:
    """Return an exact captured substring, never synthesized prose."""
    for pattern in _PATTERNS:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match is None:
            continue
        start = match.start()
        stop = match.end()
        # Bound by structural delimiters or a short distance; do not modify
        # spelling or whitespace *inside* a physically observed literal.
        left = max(0, start - 180)
        right = min(len(raw_text), stop + 180)
        for delim in ("\n", ".", "!", "?", ";"):
            idx = raw_text.rfind(delim, left, start)
            if idx >= left:
                left = max(left, idx + 1)
            idx = raw_text.find(delim, stop, right)
            if idx != -1:
                right = min(right, idx + (0 if delim == "\n" else 1))
        candidate = raw_text[left:right].strip()
        if 8 <= len(candidate) <= 512 and candidate in raw_text:
            return candidate
    return None


def prepare_private_draft(audit_dir: Path, private_dir: Path) -> dict:
    """Read only AUD, write draft exclusively to a non-repository private dir.

    A draft is NOT a signed manifest: it must never silently become proof.
    No official document or reviewer credentials are produced by this function.
    """
    status = {
        "status": "NOT_VERIFIABLE",
        "audit_writes": 0,
        "provider_requests": 0,
        "signed_receipt_created": False,
        "official_source_authenticated": False,
    }
    root = Path(audit_dir)
    target = Path(private_dir)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        if (_inspect_aud(root, AUD_ID)["aud_status"] != "SEALED_AUD_METADATA_READY"
                or target.is_symlink() or not target.is_dir()
                or any(p.is_symlink() for p in (target, *target.parents) if p.exists())):
            return status
        real_target = target.resolve()
        if (real_target == repo_root or real_target.is_relative_to(repo_root)
                or real_target == root.resolve() or real_target.is_relative_to(root.resolve())):
            return status
        # Never rewrite real reviewer material if the handoff has progressed
        # beyond draft stage. Presence alone does not establish authenticity.
        if (target / "manifest.json").exists() or (target / "manifest.json").is_symlink():
            return {**status, "status": "MANIFEST_PRESENT_USE_ACCEPTANCE_GATE"}
        db = root / "audit.db"
        before, before_size = _audit_digest(db)
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2,
        )) as connection:
            connection.execute("PRAGMA query_only=ON")
            found = connection.execute(
                "SELECT s.snapshot_id,s.captured_at,s.main_content_ref "
                "FROM page_snapshots AS s JOIN pages AS p ON p.page_id=s.page_id "
                "WHERE p.audit_id=? LIMIT 2", (AUD_ID,),
            ).fetchall()
            if len(found) != 1:
                return status
            snapshot_id, captured_at, ref = found[0]
            if (not isinstance(snapshot_id, str) or not snapshot_id.startswith("SNP-")
                    or not isinstance(ref, str) or len(ref) > 260):
                return status
            count = connection.execute(
                "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()[0]
            if count != 1:
                return status
        date_utc = _utc_day(captured_at)
        if date_utc is None:
            return status
        source = _ref_file(root, ref)
        if source is None:
            return status
        raw = source.read_bytes()
        if not 0 < len(raw) <= 2_000_000:
            return status
        candidate = _literal_candidate(raw.decode("utf-8"))
        if (source.is_symlink() or sha256(source.read_bytes()).digest() != sha256(raw).digest()
                or any(Path(str(db) + e).exists()
                       for e in ("-wal", "-shm", "-journal"))):
            return status
        after, after_size = _audit_digest(db)
        if before != after or before_size != after_size:
            return status

        manifest = {
            "audit_id": AUD_ID,
            "at_date": date_utc,
            "claims": [{
                "claim_id": "CLM-603-REVIEW-PENDING",
                "snapshot_id": snapshot_id,
                "claim_file": "claim.txt",
                "document_file": "conditions.txt",
                "receipt_file": "receipt.json",
                "product_scope": "REVISOR_DEVE_INFORMAR_PRODUTO_E_VERSAO_REAIS",
            }],
        }
        instructions = (
            "PACOTE PRIVADO #603 — RASCUNHO, SEM VALIDADE DE HOMOLOGACAO\n"
            "Manifesto/claim apenas referenciam a AUD existente, sem criar prova oficial.\n"
            "1. Revisor autorizado confere o trecho literal em claim.txt contra a AUD.\n"
            "2. Revisor identifica produto real e substitui product_scope.\n"
            "3. Revisor fornece conditions.txt UTF-8 de fonte oficial vigente,\n"
            "   preservando em meio privado a cadeia de origem do PDF/documento.\n"
            "4. Revisor verifica excerto, emissor, versao, datas e legitimidade.\n"
            "5. Revisor produz receipt.json REAL com MAC sob chave privada fora do Git.\n"
            "6. Somente apos revisao, salvar manifest.json (sem .template).\n"
            "   Nunca copiar placeholders de documento, decisao ou assinatura.\n"
            "7. Rodar o gate offline ja validado; enviar apenas JSON resumido.\n"
            "Nao colocar credenciais, claims ou documentos no GitHub/chat.\n"
        )
        # The claim is physically copied only if an actual exact candidate
        # exists. Otherwise do not invent a sentence or put a fake claim there.
        planned = [
            ("manifest.template.json", json.dumps(
                manifest, ensure_ascii=False, indent=2) + "\n"),
            ("REVIEW_REQUIRED.txt", instructions),
        ]
        if candidate is not None:
            planned.append(("claim.txt", candidate))
        # Treat earlier private drafts as resumable only when their BYTES
        # exactly equal the result derived from this same sealed AUD. Any
        # divergent/edited file may be a reviewer's work; preserve it intact.
        # Never fill missing slots when existing ones already conflict.
        reused = 0
        missing = []
        conflicts = 0
        for name, content in planned:
            dest = target / name
            if dest.is_symlink():
                conflicts += 1
                continue
            if not dest.exists():
                missing.append((name, content))
                continue
            if not dest.is_file():
                conflicts += 1
                continue
            expected = content.encode("utf-8")
            if (dest.stat().st_size > 16384
                    or dest.read_bytes() != expected):
                conflicts += 1
            else:
                reused += 1
        # When no candidate can be extracted, a pre-existing claim.txt
        # cannot be verified as literal; refuse to bless or modify it.
        if candidate is None and (
            (target / "claim.txt").exists() or (target / "claim.txt").is_symlink()
        ):
            conflicts += 1
        if conflicts:
            return {
                **status,
                "status": "DRAFT_FILES_ALREADY_PRESENT_NO_OVERWRITE",
                "existing_files_reused": reused,
                "existing_files_conflicting": conflicts,
                "draft_files_missing": len(missing),
            }
        created = []
        try:
            for name, content in missing:
                dest = target / name
                with dest.open("x", encoding="utf-8", newline="") as stream:
                    created.append(dest)
                    stream.write(content)
        except (OSError, FileExistsError):
            for dest in created:
                dest.unlink(missing_ok=True)
            return status
        outcome = (
            "UNSIGNED_PRIVATE_DRAFT_PREPARED"
            if candidate is not None else
            "UNSIGNED_TEMPLATE_PREPARED_CLAIM_REVIEW_REQUIRED"
        )
        if reused and not created:
            outcome = "UNSIGNED_PRIVATE_DRAFT_REUSED"
        elif reused and created:
            outcome = "UNSIGNED_PRIVATE_DRAFT_COMPLETED"
        return {
            **status,
            "status": outcome,
            "snapshot_count": 1,
            "utc_capture_date": date_utc,
            "literal_claim_candidate_present": candidate is not None,
            "reviewer_signature_present": False,
            "existing_files_reused": reused,
            "draft_files_created": len(created),
        }
    except (OSError, sqlite3.Error, ValueError, TypeError, UnicodeError):
        return status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare unsigned private review handoff using historic AUD"
    )
    parser.add_argument("--search-root", type=Path)
    parser.add_argument("--audit-directory", type=Path)
    parser.add_argument("--private-directory", required=True, type=Path)
    args = parser.parse_args(argv)
    directory = args.audit_directory
    if directory is None:
        directory_candidates = (
            _candidates(args.search_root, AUD_ID)
            if args.search_root is not None else []
        )
        if len(directory_candidates) != 1:
            print(json.dumps({
                "status": "AUD_DIRECTORY_NOT_UNIQUE",
                "candidate_count": len(directory_candidates),
                "provider_requests": 0, "audit_writes": 0,
            }))
            return 2
        directory = directory_candidates[0]
    output = prepare_private_draft(directory, args.private_directory)
    print(json.dumps(output, sort_keys=True, ensure_ascii=False))
    return 0 if output["status"].startswith("UNSIGNED_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
