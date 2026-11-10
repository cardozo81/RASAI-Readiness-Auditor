"""Resource-limited passive discovery over supplied bytes only."""
import base64
from datetime import datetime
import json
import sys

from rasai.contextual_documents import discover_references
from rasai.document_text_worker import _memory_limit
from rasai.domain import DeviceContext, PageSnapshot


def main():
    _memory_limit(268_435_456)
    payload = json.loads(sys.stdin.buffer.read(3_000_001))
    snapshot = PageSnapshot(
        snapshot_id=payload["snapshot_id"], page_id=payload["page_id"],
        device=DeviceContext(payload["device"]), requested_url=payload["requested_url"],
        final_url=payload["final_url"], captured_at=datetime.fromisoformat(payload["captured_at"]),
    )
    result = discover_references(audit_id=payload["audit_id"], snapshot=snapshot,
                                original=base64.b64decode(payload["original"], validate=True),
                                artifact_ref=payload["artifact_ref"], surface=payload["surface"])
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(2)
