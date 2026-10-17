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
