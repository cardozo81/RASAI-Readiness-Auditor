"""#603 private draft: no fake source, review, MAC or historical AUD writes."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "CLAIM_603_PREPARE_HANDOFF.py"
AUD_ID = "AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF"


def _fixture(tmp_path, *, artifact=True, captured_at="2026-10-14T15:00:00-03:00"):
    aud = tmp_path / AUD_ID
    aud.mkdir()
    source = aud / "artifacts" / "capture" / "main.txt"
    source.parent.mkdir(parents=True)
    if artifact:
        source.write_text(
            "Condições gerais. Seguro de vida ativado em 24 horas para o "
            "produto anunciado. Consulte as condições específicas.\n",
            encoding="utf-8",
        )
    with sqlite3.connect(aud / "audit.db") as con:
        con.executescript(
            "CREATE TABLE audits(audit_id TEXT,status TEXT,completion_status TEXT);"
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,captured_at TEXT,main_content_ref TEXT);"
        )
        con.execute("INSERT INTO audits VALUES (?,'COMPLETED','COMPLETE')", (AUD_ID,))
        con.execute("INSERT INTO pages VALUES ('P-1',?)", (AUD_ID,))
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?)",
            ("SNP-603-REAL-SAMPLE", "P-1", captured_at, "artifacts/capture/main.txt"),
        )
    return aud, source


def _run(*args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True, text=True, check=False,
        timeout=12,
    )
    assert result.stdout.startswith("{"), result.stderr[:500]
    return result.returncode, json.loads(result.stdout)


def test_603_draft_reuses_physical_aud_and_never_creates_signed_evidence(tmp_path):
    aud, source = _fixture(tmp_path)
    secret_dir = tmp_path / "private"
    secret_dir.mkdir()
    before_db, before_source = (aud / "audit.db").read_bytes(), source.read_bytes()
    code, result = _run(
        "--audit-directory", aud, "--private-directory", secret_dir,
    )
    assert code == 0, result
    assert result["status"] == "UNSIGNED_PRIVATE_DRAFT_PREPARED"
    assert result["signed_receipt_created"] is False
    assert result["official_source_authenticated"] is False
    assert result["literal_claim_candidate_present"] is True
    assert result["audit_writes"] == result["provider_requests"] == 0
    draft = json.loads((secret_dir / "manifest.template.json").read_text(encoding="utf-8"))
    assert draft["audit_id"] == AUD_ID
    assert draft["at_date"] == "2026-10-14"
    assert draft["claims"][0]["snapshot_id"] == "SNP-603-REAL-SAMPLE"
    claim = (secret_dir / "claim.txt").read_text(encoding="utf-8")
    assert claim in before_source.decode("utf-8")
    assert "24 horas" in claim
    assert not (secret_dir / "receipt.json").exists()
    assert not (secret_dir / "conditions.txt").exists()
    assert not (secret_dir / "manifest.json").exists()
    assert claim not in json.dumps(result, ensure_ascii=False)
    assert (aud / "audit.db").read_bytes() == before_db
    assert source.read_bytes() == before_source


def test_603_draft_never_overwrites_reviewers_private_files(tmp_path):
    aud, _ = _fixture(tmp_path)
    secret_dir = tmp_path / "private"
    secret_dir.mkdir()
    (secret_dir / "claim.txt").write_text("Independent reviewer file", encoding="utf-8")
    code, result = _run(
        "--audit-directory", aud, "--private-directory", secret_dir,
    )
    assert code == 2
    assert result["status"] == "DRAFT_FILES_ALREADY_PRESENT_NO_OVERWRITE"
    assert (secret_dir / "claim.txt").read_text() == "Independent reviewer file"
    assert not (secret_dir / "manifest.template.json").exists()


def test_603_draft_autodiscovers_single_aud_without_outputting_claim(tmp_path):
    aud, source = _fixture(tmp_path)
    secret_dir = tmp_path / "private"
    secret_dir.mkdir()
    code, result = _run(
        "--search-root", tmp_path, "--private-directory", secret_dir,
    )
    assert code == 0
    assert result["status"] == "UNSIGNED_PRIVATE_DRAFT_PREPARED"
    assert "24 horas" not in json.dumps(result)


def test_603_missing_source_refuses_writing_any_private_file(tmp_path):
    aud, _ = _fixture(tmp_path, artifact=False)
    secret_dir = tmp_path / "private"
    secret_dir.mkdir()
    code, result = _run(
        "--audit-directory", aud, "--private-directory", secret_dir,
    )
    assert code == 2
    assert result["status"] == "NOT_VERIFIABLE"
    assert list(secret_dir.iterdir()) == []


def test_603_naive_capture_date_cannot_create_handoff(tmp_path):
    aud, _ = _fixture(tmp_path, captured_at="2026-10-14T15:00:00")
    secret_dir = tmp_path / "private"
    secret_dir.mkdir()
    code, result = _run(
        "--audit-directory", aud, "--private-directory", secret_dir,
    )
    assert code == 2
    assert result["status"] == "NOT_VERIFIABLE"
    assert list(secret_dir.iterdir()) == []
