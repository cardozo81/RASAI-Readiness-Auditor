"""Read-only triage of machine-like tokens in eleven presentation HTML surfaces.

A candidate is NOT a proven public-language defect: technical identifiers may
be legitimate audit evidence. Never rewrite HTML, SQLite, annexes or source text.
The receipt stores locations and types, not snippets or private source values.
"""
from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import argparse
import json
from pathlib import Path
import re

EXPECTED_PAGES = frozenset({
    "index.html", "extracao.html", "descoberta.html", "indices.html",
    "conteudo.html", "performance.html", "rede.html", "search-geo.html",
    "seguranca.html", "plano.html", "ia-custos.html",
})
_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?:SEMANTIC_M[0-9]{1,3}|CAT-(?:0[1-9]|10)|M[0-9]{1,3}|"
    r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"
    r"(?![A-Za-z0-9_./-])"
)
_TECHNICAL = frozenset({"pre", "code", "samp", "script", "style", "textarea", "blockquote"})
_VALUE = frozenset({"td", "dd"})
_ATTRIBUTES = frozenset({"title", "aria-label", "alt", "placeholder"})
_VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})
_LIMIT = 800


def _kind(token):
    if token.startswith("SEMANTIC_M"):
        return "SEMANTIC_MODULE"
    if token.startswith("CAT-"):
        return "CATALOG_REFERENCE"
    if re.fullmatch(r"M[0-9]{1,3}", token):
        return "MODULE_REFERENCE"
    return "MACHINE_ENUM_CANDIDATE"


class _Surface(HTMLParser):
    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.stack = []
        self.counts = Counter()
        self.examples = []

    def _context(self):
        tags = {item[0] for item in self.stack}
        if tags & _TECHNICAL:
            return "LITERAL_OR_TECHNICAL"
        if tags & _VALUE:
            return "PERSISTED_VALUE_REVIEW"
        return "EDITORIAL_COPY_REVIEW"

    def _family(self):
        for _, attrs in reversed(self.stack):
            family = attrs.get("data-analytical-family")
            if family:
                return family[:90]
        return None

    def _scan(self, value, *, element, attribute=None):
        if not isinstance(value, str):
            return
        context = self._context()
        for found in _TOKEN.finditer(value):
            token = found.group(0)
            self.counts[context] += 1
            if context == "LITERAL_OR_TECHNICAL" or len(self.examples) >= _LIMIT:
                continue
            kind = _kind(token)
            item = {
                "page": self.page, "line": self.getpos()[0],
                "element": element, "surface": attribute or "text",
                "context": context, "kind": kind,
                "token_sha256": sha256(token.encode("utf-8")).hexdigest(),
            }
            if kind != "MACHINE_ENUM_CANDIDATE":
                item["known_reference"] = token
            family = self._family()
            if family:
                item["analytical_family"] = family
            self.examples.append(item)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.stack.append((tag, attrs))
        for name in _ATTRIBUTES:
            if name in attrs:
                self._scan(attrs[name], element=tag, attribute=name)
        if tag in _VOID:
            self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if self.stack:
            self._scan(data, element=self.stack[-1][0])


def inspect_presentation(folder):
    """Classify all known public HTML pages, without modifying or certifying them."""
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("presentation root must be a directory")
    files = sorted(root.glob("*.html"))
    names = {item.name for item in files}
    if names != EXPECTED_PAGES:
        raise ValueError("eleven expected presentation HTML pages required")
    totals = Counter()
    candidates, pages = [], {}
    for page in files:
        original = page.read_bytes()
        scan = _Surface(page.name)
        scan.feed(original.decode("utf-8"))
        scan.close()
        totals.update(scan.counts)
        candidates.extend(scan.examples)
        pages[page.name] = {
            "html_sha256": sha256(original).hexdigest(),
            "candidates_by_context": dict(sorted(scan.counts.items())),
            "candidates_total": sum(v for k, v in scan.counts.items()
                                    if k != "LITERAL_OR_TECHNICAL"),
        }
    visible = totals["EDITORIAL_COPY_REVIEW"] + totals["PERSISTED_VALUE_REVIEW"]
    return {
        "contract": "RASAI_EDITORIAL_SURFACE_TRIAGE_V1",
        "pages_reviewed": len(pages), "pages": pages,
        "candidate_count": visible,
        "candidates_by_context": dict(sorted(totals.items())),
        "sample_limit_per_page": _LIMIT,
        "samples_truncated": any(
            pages[name]["candidates_total"] >
            sum(item["page"] == name for item in candidates)
            for name in pages
        ),
        "candidates": candidates,
        "raw_snippets_included": False,
        "automatic_replacement_performed": False,
        "certifies_humanization": False,
        "human_editorial_acceptance": "PENDING",
        "limitation": (
            "Triagem de padrões, não certificação: revisar cada candidato contra "
            "o domínio e a fonte persistida; ausência de padrões não prova clareza editorial."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    source = args.presentation.resolve(strict=True)
    target = args.output.resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        parser.error("output must be outside the presentation folder")
    if target.exists():
        parser.error("new output file required; existing receipts cannot be overwritten")
    report = inspect_presentation(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "pages_reviewed": report["pages_reviewed"],
        "candidate_count": report["candidate_count"],
        "samples_truncated": report["samples_truncated"],
        "certifies_humanization": False,
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
