"""Conservative, offline candidate for an externally reviewed catalog export.

This is deliberately separate from report-catalog integrity/freshness and does
not rewrite the canonical report or the audit evidence. Automated scanning is
not a substitute for a recipient-specific privacy/declassification review.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import tempfile
from typing import Mapping
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo, BadZipFile

from rasai.secret_safety import detect_secret_exposures

CONTRACT = "RASAI-PUBLIC-CATALOG-EXPORT-001"
MANIFEST = "export-manifest.json"
_ALLOWED = frozenset({".html", ".css", ".txt", ".md", ".json"})
_MAX_FILE = 32 * 1024 * 1024
_MAX_TOTAL = 256 * 1024 * 1024
_MAX_WITHHELD_PAGES = 5
_SAFE_ANCHOR = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_DOCUMENT_ID = re.compile(r"\b(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b")
_OPAQUE_FIELD = re.compile(r"(?i)\b(?:encrypted_content|private_key|access_token|refresh_token)\b")
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
_CSS_IMPORT = re.compile(r"(?i)@import\b")


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _safe_path(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and all(
        part not in ("", ".", "..") and not part.startswith(".")
        for part in name.split("/")
    ) and path.as_posix() == name)


def _exportable(name: str) -> bool:
    if not _safe_path(name):
        return False
    if name.casefold() in {"manifest.json", MANIFEST.casefold()}:
        return False
    if any(part.casefold() == "integrity" for part in name.split("/")):
        return False
    return PurePosixPath(name).suffix.casefold() in _ALLOWED


def _scan(name: str, data: bytes) -> str:
    if len(data) > _MAX_FILE or b"\0" in data:
        raise ValueError("exportação recusada: arquivo não textual ou acima do limite")
    try:
        body = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("exportação recusada: arquivo sem UTF-8 íntegro") from error
    if (detect_secret_exposures(
        body, path=name, strict=True, html_dom_context=name.casefold().endswith(".html")
    ) or _EMAIL.search(body) or _DOCUMENT_ID.search(body) or _OPAQUE_FIELD.search(body)):
        raise ValueError("exportação recusada: conteúdo potencialmente sensível")
    return body


class _References(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.refs: list[tuple[str, str, str]] = []
        self.scripts: list[str] = []
        self._script_parts: list[str] | None = None
        self._style_parts: list[str] | None = None
        self.style_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if len(fields) != len(attrs) or any(
            key.startswith("on") or key in {"srcdoc", "nonce"}
            for key, _value in attrs
        ):
            raise ValueError("exportação recusada: atributo de execução ou repetido")
        if tag == "script":
            if self._script_parts is not None or attrs:
                raise ValueError("exportação recusada: script dinâmico ou aninhado")
            self._script_parts = []
        if tag == "style":
            if self._style_parts is not None or attrs:
                raise ValueError("exportação recusada: estilo dinâmico")
            self._style_parts = []
        if fields.get("id"):
            self.ids.add(str(fields["id"]))
        if "srcset" in fields or (tag == "meta" and
                                 str(fields.get("http-equiv") or "").casefold() == "refresh"):
            raise ValueError("exportação recusada: navegação automática ou srcset não verificado")
        if tag in {"iframe", "object", "embed", "base", "svg", "math", "form"}:
            raise ValueError("exportação recusada: recurso embutido ou formulário não suportado")
        for key in ("href", "src", "poster", "action", "formaction", "xlink:href"):
            if fields.get(key):
                self.refs.append((tag, key, str(fields[key])))
        if fields.get("style"):
            inline_style = str(fields["style"])
            if _CSS_IMPORT.search(inline_style):
                raise ValueError("exportação recusada: importação CSS inline")
            for css_match in _CSS_URL.finditer(inline_style):
                self.refs.append(("style", "url", css_match.group(2)))

    def handle_data(self, data: str) -> None:
        if self._script_parts is not None:
            self._script_parts.append(data)
        if self._style_parts is not None:
            self._style_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self._script_parts is None:
                raise ValueError("exportação recusada: fechamento de script inválido")
            self.scripts.append("".join(self._script_parts))
            self._script_parts = None
        if tag == "style":
            if self._style_parts is None:
                raise ValueError("exportação recusada: fechamento de estilo inválido")
            self.style_blocks.append("".join(self._style_parts))
            self._style_parts = None


def _local_ref(source: str, tag: str, attribute: str, ref: str) -> tuple[str, str] | None:
    ref = ref.strip()
    if not ref or "\\" in ref or "\0" in ref:
        raise ValueError("exportação recusada: referência inválida")
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc:
        if (tag == "a" and attribute == "href" and
                parsed.scheme.casefold() in {"https", "http", "mailto", "tel"}):
            return None
        raise ValueError("exportação recusada: recurso remoto ou esquema ativo")
    if parsed.path.startswith("/") or ref.startswith("//"):
        raise ValueError("exportação recusada: referência absoluta")
    local = unquote(parsed.path)
    if "\\" in local or "\0" in local:
        raise ValueError("exportação recusada: referência codificada inválida")
    target = posixpath.normpath(posixpath.join(
        posixpath.dirname(source), local
    )) if local else source
    if not _safe_path(target):
        raise ValueError("exportação recusada: caminho fora do pacote")
    return target, unquote(parsed.fragment)


def _validate_links(contents: Mapping[str, bytes], text: Mapping[str, str]) -> None:
    html: dict[str, _References] = {}
    from rasai.catalog_report_style import _JS as _TRUSTED_UI_SCRIPT

    for path, body in text.items():
        if path.casefold().endswith(".html"):
            parser = _References()
            parser.feed(body)
            parser.close()
            if parser._script_parts is not None or parser._style_parts is not None:
                raise ValueError("exportação recusada: script/estilo não fechado")
            # Catalogs normally write LF explicitly. A preexisting canonical
            # Windows report may instead carry CRLF inside this same script;
            # normalize only its line breaks for the trust comparison.
            if [script.replace("\r\n", "\n") for script in parser.scripts] != [_TRUSTED_UI_SCRIPT]:
                # Every catalog page contains exactly the canonical, offline
                # navigation/dialog helper. Reject extra or modified code.
                raise ValueError("exportação recusada: script fora do contrato do relatório")
            html[path] = parser
    if "index.html" not in html:
        raise ValueError("exportação recusada: index.html ausente")
    for path, parser in html.items():
        for style_block in parser.style_blocks:
            if _CSS_IMPORT.search(style_block):
                raise ValueError("exportação recusada: importação CSS incorporada")
            for match in _CSS_URL.finditer(style_block):
                parser.refs.append(("style", "url", match.group(2)))
        for tag, attribute, ref in parser.refs:
            checked = _local_ref(path, tag, attribute, ref)
            if checked is None:
                continue
            target, fragment = checked
            if target not in contents:
                raise ValueError("exportação recusada: referência local ausente")
            if fragment and target in html and fragment not in html[target].ids:
                raise ValueError("exportação recusada: âncora local ausente")
    for path, body in text.items():
        if not path.casefold().endswith(".css"):
            continue
        if _CSS_IMPORT.search(body):
            raise ValueError("exportação recusada: importação CSS não verificada")
        for match in _CSS_URL.finditer(body):
            checked = _local_ref(path, "css", "url", match.group(2))
            if checked is not None and checked[0] not in contents:
                raise ValueError("exportação recusada: recurso CSS local ausente")



def _withheld_page(anchors: set[str]) -> bytes:
    """Inert replacement: never copy original page content into the candidate."""
    from html import escape
    from rasai.catalog_report_style import _JS as trusted_script

    safe = sorted(anchors)
    if any(not _SAFE_ANCHOR.fullmatch(anchor) for anchor in safe):
        raise ValueError("exportação recusada: âncora não publicável")
    markers = "".join(
        '<span id="' + escape(fragment, quote=True) + '"></span>' for fragment in safe
    )
    html = (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Conteúdo não incluído na exportação</title></head><body>"
        "<main id='report-main'><h1>Conteúdo não incluído na exportação</h1>"
        "<p>Esta página permanece exclusivamente no relatório interno. "
        "A exportação é parcial e exige revisão de privacidade antes de qualquer distribuição.</p>"
        + markers + "</main><script>" + trusted_script + "</script></body></html>"
    )
    return html.encode("utf-8")


def _withhold_unexportable_pages(
    contents: dict[str, bytes],
    text: dict[str, str],
    initially_withheld: set[str],
) -> tuple[list[str], dict[str, bytes], dict[str, str]]:
    """Explicit review-only profile, retaining unsafe pages only in the source.

    Never export their original bytes. A bounded number of canonical,
    non-index pages are replaced by visibly unavailable placeholders.
    """
    from rasai.catalog_report_contract import CATALOG_REPORT_FILENAMES
    from rasai.catalog_report_style import _JS as trusted_script

    allowed = set(CATALOG_REPORT_FILENAMES) - {"index.html"}
    withheld: set[str] = set()

    def quarantine(name: str) -> None:
        if name not in allowed:
            raise ValueError("exportação recusada: recurso não substituível")
        withheld.add(name)
        if len(withheld) > _MAX_WITHHELD_PAGES:
            raise ValueError("exportação recusada: relatório externo excessivamente incompleto")

    for name in initially_withheld:
        quarantine(name)
    parsers: dict[str, _References] = {}
    for name, body in text.items():
        if not name.endswith(".html") or name in withheld:
            continue
        parser = _References()
        try:
            parser.feed(body)
            parser.close()
            valid_script = (
                parser._script_parts is None
                and parser._style_parts is None
                and [part.replace("\r\n", "\n") for part in parser.scripts] == [trusted_script]
            )
        except ValueError:
            valid_script = False
        if not valid_script:
            quarantine(name)
        else:
            parsers[name] = parser

    changed = True
    while changed:
        changed = False
        for name, parser in list(parsers.items()):
            if name in withheld:
                continue
            refs = list(parser.refs)
            for style in parser.style_blocks:
                if _CSS_IMPORT.search(style):
                    quarantine(name)
                    changed = True
                    break
                refs.extend(
                    ("style", "url", match.group(2))
                    for match in _CSS_URL.finditer(style)
                )
            if name in withheld:
                continue
            for tag, attribute, reference in refs:
                try:
                    checked = _local_ref(name, tag, attribute, reference)
                    if checked is None:
                        continue
                    target, fragment = checked
                    if target not in contents:
                        raise ValueError("referência ausente no pacote")
                    if fragment and target in parsers and target not in withheld:
                        if fragment not in parsers[target].ids:
                            raise ValueError("âncora de destino ausente")
                except ValueError:
                    quarantine(name)
                    changed = True
                    break

    # The only target anchors made available for withheld pages are requested
    # by non-withheld HTML that has passed both the data and parser gates.
    wanted: dict[str, set[str]] = {name: set() for name in withheld}
    for name, parser in parsers.items():
        if name in withheld:
            continue
        for tag, attribute, reference in parser.refs:
            checked = _local_ref(name, tag, attribute, reference)
            if checked is None:
                continue
            target, fragment = checked
            if fragment and target in withheld:
                wanted[target].add(fragment)
    for name in sorted(withheld):
        data = _withheld_page(wanted[name])
        contents[name] = data
        text[name] = data.decode("utf-8")
    _validate_links(contents, text)
    return sorted(withheld), contents, text


def _inventory(root: Path) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("origem inválida")
    result: dict[str, bytes] = {}
    seen: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("exportação recusada: symlink na origem")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if not _safe_path(name) or name.casefold() in seen:
            raise ValueError("exportação recusada: caminho inseguro/duplicado")
        seen.add(name.casefold())
        if path.stat().st_size > _MAX_FILE and _exportable(name):
            raise ValueError("exportação recusada: arquivo acima do limite")
        result[name] = path.read_bytes() if (
            _exportable(name) or name in {"manifest.json", "integrity/catalog-assurance.json"}
        ) else b""
    return result


def _prepare(root: Path, *, withhold_unsafe_pages: bool = False) -> tuple[dict[str, bytes], dict]:
    from rasai.catalog_report_site import verify_catalog_report_package

    ok, _errors = verify_catalog_report_package(root)
    if not ok:
        raise ValueError("exportação recusada: catálogo canônico não íntegro")
    original = _inventory(root)
    try:
        source_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assurance = json.loads(
            (root / "integrity" / "catalog-assurance.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as error:
        raise ValueError("exportação recusada: comprovação de origem inválida") from error
    if assurance.get("global_output_security", {}).get("passed") is not True:
        raise ValueError("exportação recusada: segurança da projeção não aprovada")
    if source_manifest.get("freshness") != "FINAL":
        raise ValueError("exportação recusada: relatório canônico não final")
    snapshot = source_manifest.get("audit_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("exportação recusada: snapshot de origem não verificável")
    logical = snapshot.get("logical_sha256")
    source_logical = snapshot.get("source_logical_sha256")
    if (not isinstance(logical, str) or len(logical) != 64
            or logical != source_logical
            or assurance.get("package_integrity", {}).get("final_source_snapshot_match") is not True):
        raise ValueError("exportação recusada: equivalência lógica da origem não comprovada")
    recorded = source_manifest.get("packaged_files", [])
    if not isinstance(recorded, list):
        raise ValueError("exportação recusada: inventário de origem inválido")
    expected = {}
    for entry in recorded:
        if not isinstance(entry, dict):
            raise ValueError("exportação recusada: inventário de origem inválido")
        name = entry.get("path")
        if not isinstance(name, str) or not _safe_path(name) or name in expected:
            raise ValueError("exportação recusada: inventário de origem inválido")
        expected[name] = entry
    if set(original) != set(expected) | {"manifest.json"}:
        raise ValueError("exportação recusada: arquivos não inventariados no catálogo")
    contents: dict[str, bytes] = {}
    text: dict[str, str] = {}
    initially_withheld: set[str] = set()
    total = 0
    for name, entry in expected.items():
        if not _exportable(name):
            continue
        data = original[name]
        if _digest(data) != entry.get("sha256") or len(data) != entry.get("size_bytes"):
            raise ValueError("exportação recusada: origem modificada")
        total += len(data)
        if total > _MAX_TOTAL:
            raise ValueError("exportação recusada: tamanho agregado excedido")
        try:
            text[name] = _scan(name, data)
        except ValueError:
            if not withhold_unsafe_pages or not name.endswith(".html") or name == "index.html":
                raise
            initially_withheld.add(name)
        contents[name] = data
    if not contents:
        raise ValueError("exportação recusada: nenhum documento elegível")
    withheld_pages: list[str] = []
    if withhold_unsafe_pages:
        withheld_pages, contents, text = _withhold_unexportable_pages(
            contents, text, initially_withheld
        )
    else:
        _validate_links(contents, text)
    source_bytes = (root / "manifest.json").read_bytes()
    receipt = {
        "contract": CONTRACT,
        "profile": "external-candidate",
        "audit_id": source_manifest.get("audit_id"),
        "source_manifest_sha256": _digest(source_bytes),
        "source_package": "report-catalog (internal, not included)",
        "forensic_equivalence": False,
        "privacy_review": "REQUIRED_BEFORE_DISTRIBUTION",
        "export_mode": "withheld-pages-review-only" if withheld_pages else "strict",
        "withheld_pages": withheld_pages,
        "automated_checks": "allowlist + inventory + UTF-8 + secret/PII patterns + local links",
        "files": [
            {"path": name, "sha256": _digest(data), "size_bytes": len(data)}
            for name, data in sorted(contents.items())
        ],
    }
    return contents, receipt


def _canonical_zip(contents: Mapping[str, bytes], receipt: Mapping[str, object]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(contents.items()):
            entry = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data)
        entry = ZipInfo(MANIFEST, (1980, 1, 1, 0, 0, 0))
        entry.compress_type = ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        archive.writestr(
            entry,
            (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        )
    return buffer.getvalue()


def verify_public_catalog_export(zip_path: str | Path) -> tuple[bool, tuple[str, ...]]:
    """Verify a candidate using only its own archive, inventory and content."""
    try:
        with ZipFile(zip_path) as archive:
            if archive.comment:
                raise ValueError("comentário ZIP não inventariado")
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (len(names) != len(set(name.casefold() for name in names)) or
                    MANIFEST not in names or any(
                        not _safe_path(name) or
                        (name != MANIFEST and not _exportable(name)) or
                        stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK or
                        entry.file_size > _MAX_FILE or bool(entry.extra) or bool(entry.comment)
                        for name, entry in zip(names, entries)
                    )):
                raise ValueError("inventário do arquivo ZIP inválido")
            if sum(entry.file_size for entry in entries) > _MAX_TOTAL:
                raise ValueError("tamanho agregado inválido")
            raw_manifest = archive.read(MANIFEST)
            manifest = json.loads(raw_manifest.decode("utf-8"))
            if (manifest.get("contract") != CONTRACT or
                    manifest.get("forensic_equivalence") is not False or
                    manifest.get("privacy_review") != "REQUIRED_BEFORE_DISTRIBUTION" or
                    not isinstance(manifest.get("files"), list)):
                raise ValueError("contrato de exportação inválido")
            mode = manifest.get("export_mode", "strict")
            withheld = manifest.get("withheld_pages", [])
            if (mode not in {"strict", "withheld-pages-review-only"}
                    or not isinstance(withheld, list)
                    or len(withheld) > _MAX_WITHHELD_PAGES
                    or len(withheld) != len(set(withheld))
                    or (mode == "strict" and withheld)
                    or (mode == "withheld-pages-review-only" and not withheld)
                    or any(not isinstance(n, str) or not _safe_path(n)
                           for n in withheld)):
                raise ValueError("contrato de páginas retidas inválido")
            declared = {}
            for record in manifest["files"]:
                if not isinstance(record, dict):
                    raise ValueError("registro de exportação inválido")
                name = record.get("path")
                if not isinstance(name, str) or name in declared or not _exportable(name):
                    raise ValueError("registro de exportação inválido/duplicado")
                declared[name] = record
            if set(names) != set(declared) | {MANIFEST}:
                raise ValueError("inventário da exportação divergente")
            contents = {}
            text = {}
            for name, record in declared.items():
                data = archive.read(name)
                if len(data) != record.get("size_bytes") or _digest(data) != record.get("sha256"):
                    raise ValueError("hash da exportação divergente")
                contents[name] = data
                text[name] = _scan(name, data)
            if withheld:
                from rasai.catalog_report_contract import CATALOG_REPORT_FILENAMES
                if any(n not in CATALOG_REPORT_FILENAMES or n == "index.html"
                       or n not in contents for n in withheld):
                    raise ValueError("página retida inválida")
                for name in withheld:
                    parser = _References()
                    parser.feed(text[name])
                    parser.close()
                    anchors = parser.ids - {"report-main"}
                    if contents[name] != _withheld_page(anchors):
                        raise ValueError("substituição não-canônica de página restrita")
            _validate_links(contents, text)
            # Exact canonical bytes also reject ZIP comments, arbitrary stubs,
            # overlays, extra metadata, nonstandard order and hidden trailing data.
            if Path(zip_path).read_bytes() != _canonical_zip(contents, manifest):
                raise ValueError("estrutura ZIP não canônica")
        return True, ()
    except (OSError, ValueError, UnicodeDecodeError, BadZipFile, KeyError, TypeError,
            RuntimeError) as error:
        # Never include the payload or secret findings in public logs.
        return False, (f"exportação inválida: {type(error).__name__}",)


def export_public_catalog(
    report_dir: str | Path, destination: str | Path, *,
    withhold_unsafe_pages: bool = False,
) -> Path:
    """Prepare a deterministic, self-verifiable candidate; never publish it."""
    if Path(report_dir).is_symlink():
        raise ValueError("origem com symlink não permitida")
    source = Path(report_dir).resolve()
    output = Path(destination).absolute()
    if output.suffix.casefold() != ".zip" or not output.parent.is_dir():
        raise ValueError("destino ZIP inválido")
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(source):
        raise ValueError("destino já existe ou pertence à origem")
    contents, receipt = _prepare(source, withhold_unsafe_pages=withhold_unsafe_pages)
    # The source remains the authority. Review-only placeholders intentionally
    # differ from source pages, so verify the *whole canonical source package*
    # again rather than confusing the derived public view with the originals.
    for name, data in contents.items():
        if name in receipt["withheld_pages"]:
            continue
        if (source / name).read_bytes() != data:
            raise ValueError("origem modificada durante exportação")
    from rasai.catalog_report_site import verify_catalog_report_package
    source_ok, _source_errors = verify_catalog_report_package(source)
    if not source_ok or _digest((source / "manifest.json").read_bytes()) != receipt["source_manifest_sha256"]:
        raise ValueError("origem alterada durante exportação")
    package_bytes = _canonical_zip(contents, receipt)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".tmp", prefix=".rasai-public-", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(package_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        ok, errors = verify_public_catalog_export(temporary)
        if not ok:
            raise ValueError("falha na validação do ZIP gerado: " + "; ".join(errors))
        # Atomic create-if-absent in the same directory. In particular this
        # must not replace a target created by another process (POSIX rename
        # would silently overwrite in that race).
        os.link(temporary, output)
        temporary.unlink()
        temporary = None
        return output
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exportação candidata offline, requer revisão de privacidade.")
    parser.add_argument("--catalog-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--withhold-unsafe-pages", action="store_true", help="Prévia parcial: substituir páginas não publicáveis por aviso sem fatos")
    args = parser.parse_args(argv)
    try:
        result = export_public_catalog(
            args.catalog_dir, args.output,
            withhold_unsafe_pages=args.withhold_unsafe_pages,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"EXPORT_CANDIDATE=BLOCKED ({type(error).__name__})")
        return 2
    print("EXPORT_CANDIDATE=READY_FOR_PRIVACY_REVIEW")
    if args.withhold_unsafe_pages:
        print("EXPORT_MODE=REVIEW_ONLY_WITH_POSSIBLE_WITHHOLDING")
    print(f"OUTPUT={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
