"""Internal subprocess boundary for untrusted document parsing; no network API."""
from __future__ import annotations

import io
import json
import os
import sys


def _memory_limit(size: int):
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (size, size))
        return None
    # Windows Job Object: hard per-process commit limit, released on exit.
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64),
                    ("flags", w.DWORD), ("min_ws", c.c_size_t), ("max_ws", c.c_size_t),
                    ("active", w.DWORD), ("affinity", c.c_size_t),
                    ("priority", w.DWORD), ("scheduling", w.DWORD)]

    class IO(c.Structure):
        _fields_ = [(name, c.c_uint64) for name in ("ro", "wo", "oo", "rb", "wb", "ob")]

    class Extended(c.Structure):
        _fields_ = [("basic", Basic), ("io", IO), ("process_memory", c.c_size_t),
                    ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    config = Extended()
    config.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    config.process_memory = size
    if (not handle or not kernel.SetInformationJobObject(handle, 9, c.byref(config), c.sizeof(config))
            or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())):
        raise RuntimeError("memory isolation unavailable")
    return handle


def main():
    from rasai.contextual_documents import digest
    kind, limits = sys.argv[1], json.loads(sys.argv[2])
    job = _memory_limit(limits["memory_bytes"])
    del job  # OS handle stays open until process exit.
    data = sys.stdin.buffer.read(limits["max_bytes"] + 1)
    if len(data) > limits["max_bytes"]:
        raise ValueError("byte limit")
    pages = []
    tool = None
    if kind == "application/pdf":
        import pypdf
        pypdf.Configuration.zlib_maximum_output_length = limits["max_stream_bytes"]
        pypdf.Configuration.lzw_maximum_output_length = limits["max_stream_bytes"]
        pypdf.Configuration.run_length_maximum_output_length = limits["max_stream_bytes"]
        pypdf.Configuration.maximum_declared_stream_length = limits["max_stream_bytes"]
        pypdf.Configuration.stream_decoding_work_maximum_length = limits["max_stream_bytes"] * 4
        pypdf.Configuration.page_tree_maximum_depth = 30
        pypdf.Configuration.page_tree_maximum_entries = limits["max_pages"] * 4
        pypdf.Configuration.xform_maximum_invocations_per_extraction = 100
        reader = pypdf.PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted")
        if len(reader.pages) > limits["max_pages"]:
            raise ValueError("page limit")
        tool = {"name": "pypdf", "version": pypdf.__version__, "mode": "plain"}
        total = 0
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > limits["max_stream_bytes"]:
                raise ValueError("stream complexity limit")
            text = page.extract_text(extraction_mode="plain") or ""
            total += len(text)
            if total > limits["max_chars"]:
                raise ValueError("character limit")
            pages.append(text)
    else:
        from rasai.acquisition import decode_captured_text
        from rasai.extraction import ContentExtractor
        page = ContentExtractor().extract(decode_captured_text(data))
        # Fragments are valid supplied HTML; preserve canonical extraction when
        # a body exists, otherwise parse the fragment inside a synthetic body.
        if not page.main_content and not page.text_blocks:
            page = ContentExtractor().extract("<html><body>" + decode_captured_text(data) + "</body></html>")
        pages = [page.main_content or "\n".join(page.text_blocks)]
        tool = {"name": "rasai.ContentExtractor", "version": "contextual-documents-v1", "mode": "captured-html"}
    text = "\n\f\n".join(pages)
    if not text.strip() or len(text) > limits["max_chars"]:
        raise ValueError("no text or character limit")
    offset = 0
    sections = []
    for index, page in enumerate(pages):
        sections.append({"page": index + 1, "start": offset, "end": offset + len(page),
                         "text_sha256": digest(page.encode())})
        offset += len(page) + 3
    print(json.dumps({"status": "DOCUMENT_COLLECTED", "reason": None, "text": text,
                      "text_sha256": digest(text.encode()), "pages": sections, "tool": tool}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never print private parser diagnostics, filenames, document text or passwords.
        sys.exit(2)
