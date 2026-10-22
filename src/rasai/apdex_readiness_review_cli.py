"""Offline one-sidecar content-readiness review; original Apdex untouched."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from rasai.apdex_readiness_review import inspect_content_readiness_review


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Consulta sidecar experimental vinculado à AUD sem executar Apdex"
    )
    parser.add_argument("--audit-directory", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "html"), default="json")
    args = parser.parse_args(argv)
    viewed = inspect_content_readiness_review(args.audit_directory, args.sidecar)
    if args.format == "html":
        from rasai.apdex_readiness_review_html import content_readiness_review_html
        print(content_readiness_review_html(viewed))
    else:
        print(json.dumps(viewed, ensure_ascii=False, sort_keys=True))
    return 0 if viewed["status"] == "DOCUMENTARY_SIDECAR_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
