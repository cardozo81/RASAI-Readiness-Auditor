"""Private bounded worker. Supplied captured bytes only; never a provider."""
import base64
from datetime import datetime
import json
import sys

from rasai.contextual_content import observe_content
from rasai.document_text_worker import _memory_limit
from rasai.domain import DeviceContext, PageSnapshot


def main():
    job = _memory_limit(268_435_456)
    def offline_boundary(event, args):
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen"}:
            raise PermissionError("offline contextual worker")
    sys.addaudithook(offline_boundary)
    payload = json.loads(sys.stdin.buffer.read(5_000_001))
    if len(sys.argv) == 3 and sys.argv[1] == "--search":
        from pathlib import Path
        from rasai.contextual_search import correlate_persisted
        result = correlate_persisted(Path(sys.argv[2]), payload)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("ascii"))
        return job
    snapshot = PageSnapshot(snapshot_id=payload["snapshot_id"], page_id=payload["page_id"],
        device=DeviceContext(payload["device"]), requested_url=payload["requested_url"],
        final_url=payload["final_url"], captured_at=datetime.fromisoformat(payload["captured_at"]))
    result = observe_content(audit_id=payload["audit_id"], snapshot=snapshot,
        original=base64.b64decode(payload["original"], validate=True),
        source_ref=payload["source_ref"], surface=payload["surface"])
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("ascii"))
    return job


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(2)
