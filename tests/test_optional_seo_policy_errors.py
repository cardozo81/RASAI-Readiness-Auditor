"""Read-only optional SEO evidence must abstain on acquisition failures."""
import json

import pytest

from rasai.optional_seo_policy import classify_seo_evidence


@pytest.mark.parametrize(
    ("rule_id", "evidence"),
    [
        ("BR-GEO-003", {"sitemaps": [{"state": "ABSENT"}]}),
        ("BR-GEO-013", {"canonicals": []}),
        ("BR-GEO-017", {"state": "ABSENT"}),
    ],
)
def test_acquisition_error_is_not_optional_absence(rule_id: str, evidence: dict) -> None:
    assert classify_seo_evidence(rule_id, evidence) == "OPTIONAL_ABSENCE"
    failed = {**evidence, "error": "NETWORK_TIMEOUT"}
    assert classify_seo_evidence(rule_id, failed) == "UNKNOWN"
    assert classify_seo_evidence(rule_id, json.dumps(failed)) == "UNKNOWN"


def test_duplicate_json_keys_are_not_evidence() -> None:
    assert classify_seo_evidence(
        "BR-GEO-013", '{"canonicals":[],"canonicals":[]}'
    ) == "UNKNOWN"


def test_optional_replay_hash_rejects_same_size_mutation(tmp_path, monkeypatch):
    """Do not trust size-only checks on immutable AUD replay sources."""
    from pathlib import Path
    import os
    from rasai.optional_seo_audit_replay import _read_hash

    path = tmp_path / "audit.db"
    path.write_bytes(b"unchanged-bytes")
    initial_open = Path.open
    mutated = []

    class Intercept:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def __getattr__(self, key):
            return getattr(self.stream, key)
        def read(self, n=-1):
            result = self.stream.read(n)
            if result and not mutated:
                mutated.append(True)
                stamp = path.stat()
                with initial_open(path, "r+b") as writer:
                    writer.write(b"X")
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 10000000))
            return result

    def checked_open(self, *args, **kwargs):
        opened = initial_open(self, *args, **kwargs)
        if self == path and args and args[0] == "rb":
            return Intercept(opened)
        return opened

    monkeypatch.setattr(Path, "open", checked_open)
    with pytest.raises(ValueError, match="AUD SQLite source changed"):
        _read_hash(path)
    assert mutated


def test_optional_seo_projection_rejects_missing_and_symlinked_database(tmp_path):
    """A presentation helper cannot create or follow an AUD database."""
    from rasai.optional_seo_interpretation import optional_seo_penalties
    missing = tmp_path / "missing.db"
    assert optional_seo_penalties(missing, "AUD-A") == []
    assert not missing.exists()
    source = tmp_path / "physical.db"
    source.write_bytes(b"not a database")
    alias = tmp_path / "alias.db"
    try:
        alias.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    assert optional_seo_penalties(alias, "AUD-A") == []
    assert source.read_bytes() == b"not a database"


def test_optional_seo_projection_never_attributes_other_aud_rule_to_score(tmp_path):
    """An otherwise valid absence from a foreign AUD is not this AUD's evidence."""
    import sqlite3
    from rasai.optional_seo_interpretation import optional_seo_penalties

    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE scores (
                score_id TEXT, audit_id TEXT, dimension TEXT, device TEXT,
                scoring_version TEXT
            );
            CREATE TABLE rule_executions (
                rule_execution_id TEXT, audit_id TEXT, rule_id TEXT,
                observed_value TEXT
            );
            CREATE TABLE score_contributions (
                score_id TEXT, rule_execution_id TEXT, rule_id TEXT,
                dimension TEXT, device TEXT, weight REAL, result_factor REAL,
                result TEXT
            );
        """)
        con.execute("INSERT INTO scores VALUES (?,?,?,?,?)",
                    ("S-A", "AUD-A", "INDEXABILITY", "MOBILE", "SCORE-GEO-004"))
        con.executemany("INSERT INTO rule_executions VALUES (?,?,?,?)", [
            ("R-A", "AUD-A", "BR-GEO-013", '{"canonicals":[]}'),
            ("R-B", "AUD-OTHER", "BR-GEO-013", '{"canonicals":[]}'),
        ])
        con.executemany("INSERT INTO score_contributions VALUES (?,?,?,?,?,?,?,?)", [
            ("S-A", "R-A", "BR-GEO-013", "INDEXABILITY", "MOBILE", .3, .5, "WARNING"),
            ("S-A", "R-B", "BR-GEO-013", "INDEXABILITY", "MOBILE", .3, .5, "WARNING"),
        ])
    physical = db.read_bytes()
    observed = optional_seo_penalties(db, "AUD-A")
    assert len(observed) == 1
    assert observed[0]["isolated_discount_points"] == 15.0
    assert db.read_bytes() == physical
    (tmp_path / "audit.db-wal").write_bytes(b"uncheckpointed")
    assert optional_seo_penalties(db, "AUD-A") == []



def test_602_full_policy_evidence_matrix_is_not_a_new_scoring_contract(tmp_path):
    import sqlite3
    from rasai.optional_seo_evidence_matrix import (
        inspect_optional_seo_evidence, optional_seo_evidence_matrix_html,
    )
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE scores(
                score_id TEXT,audit_id TEXT,dimension TEXT,device TEXT,
                scoring_version TEXT
            );
            CREATE TABLE rule_executions(
                rule_execution_id TEXT,audit_id TEXT,rule_id TEXT,
                observed_value TEXT
            );
            CREATE TABLE score_contributions(
                score_id TEXT,rule_execution_id TEXT,rule_id TEXT,
                dimension TEXT,device TEXT,result TEXT
            );
        """)
        con.executemany("INSERT INTO scores VALUES (?,?,?,?,?)", [
            ("S-D", "AUD-602", "DISCOVERY_ACCESS", "MOBILE", "SCORE-GEO-004"),
            ("S-I", "AUD-602", "INDEXABILITY", "MOBILE", "SCORE-GEO-004"),
        ])
        con.executemany("INSERT INTO rule_executions VALUES (?,?,?,?)", [
            ("R-ROBOTS", "AUD-602", "BR-GEO-017", '{"state":"ABSENT"}'),
            ("R-SITEMAP", "AUD-602", "BR-GEO-003",
             '{"sitemaps":[{"state":"OBTAINED"}]}'),
            ("R-CANONICAL", "AUD-602", "BR-GEO-013",
             '{"declared":["https://a.test","https://b.test"],'
             '"normalized":["https://a.test","https://b.test"],'
             '"invalid":[],"canonicals":["https://a.test","https://b.test"]}'),
            ("R-FOREIGN", "OTHER-AUD", "BR-GEO-017", '{"state":"ABSENT"}'),
        ])
        con.executemany(
            "INSERT INTO score_contributions VALUES (?,?,?,?,?,?)",
            [
                ("S-D", "R-ROBOTS", "BR-GEO-017", "DISCOVERY_ACCESS", "MOBILE", "WARNING"),
                ("S-D", "R-SITEMAP", "BR-GEO-003", "DISCOVERY_ACCESS", "MOBILE", "PASS"),
                ("S-I", "R-CANONICAL", "BR-GEO-013", "INDEXABILITY", "MOBILE", "WARNING"),
                ("S-D", "R-FOREIGN", "BR-GEO-017", "DISCOVERY_ACCESS", "MOBILE", "WARNING"),
            ],
        )
    original = db.read_bytes()
    matrix = inspect_optional_seo_evidence(db, "AUD-602")
    assert len(matrix) == 3
    assert {row["evidence"] for row in matrix} == {
        "Ausência opcional no escopo observado",
        "Conflito técnico observado",
        "Sinal encontrado no escopo observado",
    }
    assert {row["current_result"] for row in matrix} == {
        "Advertência no contrato atual", "Aprovado no contrato atual",
    }
    html = optional_seo_evidence_matrix_html(db, "AUD-602")
    assert "Evidências dos sinais SEO opcionais" in html
    assert "SCORE-GEO-004" in html
    assert "não é recalculado" in html
    assert "R-FOREIGN" not in html
    assert db.read_bytes() == original


def test_602_optional_inventory_abstains_on_missing_or_uncheckpointed_sqlite(tmp_path):
    from rasai.optional_seo_evidence_matrix import (
        inspect_optional_seo_evidence, optional_seo_evidence_matrix_html,
    )
    missing = tmp_path / "audit.db"
    assert inspect_optional_seo_evidence(missing, "AUD-602") == ()
    assert not missing.exists()
    missing.write_bytes(b"broken sqlite")
    assert inspect_optional_seo_evidence(missing, "AUD-602") == ()
    (tmp_path / "audit.db-shm").write_bytes(b"pending")
    assert optional_seo_evidence_matrix_html(missing, "AUD-602") == ""
    assert missing.read_bytes() == b"broken sqlite"
