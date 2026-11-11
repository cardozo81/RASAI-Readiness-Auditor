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
    parsed = []
    result = observe_content(audit_id=payload["audit_id"], snapshot=snapshot,
        original=base64.b64decode(payload["original"], validate=True),
        source_ref=payload["source_ref"], surface=payload["surface"], _parsed=parsed)
    raw_v1 = json.dumps(result, ensure_ascii=True).encode("ascii")
    from rasai.contextual_semantics import qualify_capture
    try:
        overlay = qualify_capture(result, parsed[0] if parsed else None)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        overlay = qualify_capture(result)
    result["semantic_overlay_v2"] = overlay
    from rasai.contextual_faq_aria import qualify_capture as qualify_aria
    try:
        result["faq_aria_overlay_v3"] = qualify_aria(result, parsed[0] if parsed else None)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        result["faq_aria_overlay_v3"] = qualify_aria(result)
    from rasai.contextual_page_structure import qualify_capture as qualify_structure
    try:
        result["page_structure_overlay_v3"] = qualify_structure(result, parsed[0] if parsed else None)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        result["page_structure_overlay_v3"] = qualify_structure(result)
    combined = json.dumps(result, ensure_ascii=True).encode("ascii")
    # An optional overlay must never displace a v1 packet within its existing
    # output budget. Missing v2 trace degrades to N/D in the parent consumer.
    sys.stdout.buffer.write(combined if len(combined) <= 5_000_000 else raw_v1)
    return job


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(2)
