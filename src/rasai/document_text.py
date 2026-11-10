"""Bounded, isolated extraction of supplied HTML and textual PDF bytes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import subprocess
import sys

from rasai.contextual_documents import digest


@dataclass(frozen=True)
class DocumentLimits:
    max_bytes: int = 4_000_000
    max_pages: int = 100
    max_chars: int = 200_000
    max_stream_bytes: int = 1_000_000
    seconds: int = 10
    memory_bytes: int = 268_435_456

    def __post_init__(self):
        ceiling = (4_000_000, 100, 200_000, 1_000_000, 10, 268_435_456)
        if any(type(v) is not int or v < 1 or v > cap
               for v, cap in zip(asdict(self).values(), ceiling)):
            raise ValueError("document limits outside policy")


def extract_document(original: bytes, *, media_type: str | None,
                     limits: DocumentLimits = DocumentLimits()) -> dict:
    """No extension inference; timeout kills the parser process, stderr is discarded.

    Original bytes remain the caller's immutable artifact. Text and page offsets
    are derived evidence, never a replacement document or authenticity proof.
    """
    result = {"document_id": digest(original), "original_sha256": digest(original),
              "original_bytes": len(original), "declared_media_type": media_type,
              "verified_media_type": None, "status": "NOT_VERIFIED", "reason": None,
              "text": "", "text_sha256": None, "pages": [], "tool": None,
              "parameters": asdict(limits), "limitations": ["AUTHENTICITY_NOT_VERIFIED", "NO_OCR"]}
    if not original or len(original) > limits.max_bytes:
        result["reason"] = "BYTE_LIMIT_OR_EMPTY_ND"
        return result
    if original.startswith(b"%PDF-"):
        kind = "application/pdf"
    elif media_type and media_type.split(";", 1)[0].strip().lower() == "text/html" and original.lstrip().startswith(b"<"):
        kind = "text/html"
    else:
        result["reason"] = "FORMAT_NOT_VERIFIED_ND"
        return result
    try:
        child = subprocess.run(
            [sys.executable, "-m", "rasai.document_text_worker", kind, json.dumps(asdict(limits))],
            input=original, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=limits.seconds, check=False,
        )
        if child.returncode or len(child.stdout) > limits.max_chars * 8 + 100_000:
            result["reason"] = "PARSER_RESOURCE_OR_FORMAT_ERROR_ND"
            return result
        parsed = json.loads(child.stdout)
        result.update(parsed)
        result["verified_media_type"] = kind if parsed["status"] == "DOCUMENT_COLLECTED" else None
    except subprocess.TimeoutExpired:
        result["reason"] = "EXTRACTION_TIMEOUT_ND"
    except (OSError, ValueError, KeyError):
        result["reason"] = "PARSER_UNAVAILABLE_ND"
    return result
