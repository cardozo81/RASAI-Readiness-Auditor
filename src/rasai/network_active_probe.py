"""#659 G2 — explicitly authorized, process-bounded DNS/TCP/TLS observation.

Never called by AUD, RPR, CONS or report rematerialization. One public
hostname from an existing audit, one destination port, one pinned DNS result.
No HTTP request, redirects, raw sockets, ICMP, implicit provider or GeoIP.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit

CONTRACT = "rasai-network-active-probe-v1"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TIMEOUT_SECONDS = 10
_MAX_RESULT_BYTES = 16000


def _host(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Destino inválido")
    host = value.lower().rstrip(".")
    if (len(host) > 253 or "." not in host or
            host.endswith((".local", ".internal", ".localhost", ".test", ".invalid")) or
            any(not _LABEL.fullmatch(part) for part in host.split("."))):
        raise ValueError("Destino público inválido")
    return host


def _public_ips(addresses: list[tuple]) -> list[tuple[int, str]]:
    """Fail closed for mixed/private DNS answers, before any socket connect."""
    candidates = []
    for family, _kind, _proto, _name, sockaddr in addresses[:32]:
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise ValueError("Família de rede não autorizada")
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            raise ValueError("Resolução contém endereço não público")
        candidate = (family, str(ip))
        if candidate not in candidates:
            candidates.append(candidate)
    if not candidates or len(addresses) > 32:
        raise ValueError("Resolução não utilizável")
    return candidates


def _metric(state: str = "NOT_OBSERVED", value=None, error: str | None = None) -> dict:
    return {"state": state, "value": value if state == "OBSERVED" else None,
            "error": error}


def _worker_probe(host: str, port: int) -> dict:
    """Worker only: pinned public-IP connection with valid SNI and TLS checks."""
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metrics = {
        "dns_resolution": _metric(), "dns_elapsed_ms": _metric(),
        "connected_public_ip": _metric(), "tcp_handshake_ms": _metric(),
        "tls_handshake_ms": _metric(), "tls_protocol": _metric(),
        "traceroute": _metric(), "asn": _metric(), "geoip": _metric(),
    }
    record = {
        "contract": CONTRACT, "hostname": host, "port": port,
        "capture_utc": started, "measurement_origin": "LOCAL_OPERATOR_PROCESS",
        "method": "EXPLICIT_DNS_TCP_TLS_PROBE", "source": "LOCAL_SOCKET_STACK",
        "origin_network_state": "PROXY_VPN_EGRESS_NOT_VERIFIED",
        "state": "INCONCLUSIVE", "ip_version": None, "metrics": metrics,
        "limits": [
            "Medição efetuada a partir do processo executor, não do navegador da auditoria.",
            "DNS pode usar cache local; endereço público pode pertencer a CDN ou proxy.",
            "Não mede RTT de cada hop nem localização geográfica.",
        ],
    }
    try:
        t0 = time.monotonic()
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM,
                                      proto=socket.IPPROTO_TCP)
        elapsed = round((time.monotonic() - t0) * 1000, 2)
        ips = _public_ips(resolved)
        metrics["dns_resolution"] = _metric("OBSERVED", [ip for _, ip in ips])
        metrics["dns_elapsed_ms"] = _metric("OBSERVED", elapsed)
        family, ip = ips[0]
        record["ip_version"] = 4 if family == socket.AF_INET else 6
    except ValueError:
        record["state"] = "BLOCKED"
        metrics["dns_resolution"] = _metric("BLOCKED", error="UNSAFE_DNS_ANSWER")
        return record
    except (OSError, socket.gaierror):
        record["state"] = "COLLECTION_FAILED"
        metrics["dns_resolution"] = _metric("COLLECTION_FAILED", error="DNS_LOOKUP_FAILED")
        return record

    sock = None
    try:
        # Always connect to the vetted numeric IP; no hostname re-resolution.
        sock = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        sock.settimeout(2.5)
        target = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
        t0 = time.monotonic()
        sock.connect(target)
        tcp_ms = round((time.monotonic() - t0) * 1000, 2)
        metrics["connected_public_ip"] = _metric("OBSERVED", ip)
        metrics["tcp_handshake_ms"] = _metric("OBSERVED", tcp_ms)
        if port == 443:
            context = ssl.create_default_context()
            t0 = time.monotonic()
            with context.wrap_socket(sock, server_hostname=host) as secure:
                sock = None
                tls_ms = round((time.monotonic() - t0) * 1000, 2)
                metrics["tls_handshake_ms"] = _metric("OBSERVED", tls_ms)
                metrics["tls_protocol"] = _metric("OBSERVED", secure.version())
        else:
            metrics["tls_handshake_ms"] = _metric("NOT_APPLICABLE")
            metrics["tls_protocol"] = _metric("NOT_APPLICABLE")
        record["state"] = "OBSERVED"
    except (OSError, ssl.SSLError):
        record["state"] = "COLLECTION_FAILED"
        if metrics["tcp_handshake_ms"]["state"] != "OBSERVED":
            metrics["tcp_handshake_ms"] = _metric("COLLECTION_FAILED", error="TCP_CONNECT_FAILED")
        else:
            metrics["tls_handshake_ms"] = _metric("COLLECTION_FAILED", error="TLS_HANDSHAKE_FAILED")
    finally:
        if sock is not None:
            sock.close()
    return record


def _audit_has_target(workspace: Path, audit_id: str, host: str) -> bool:
    db = workspace / "audit.db"
    if (workspace.is_symlink() or db.is_symlink() or not db.is_file()
            or (workspace / "artifacts").is_symlink()):
        return False
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as cx:
            cx.execute("PRAGMA query_only=ON")
            audit = cx.execute("SELECT 1 FROM audits WHERE audit_id=?", (audit_id,)).fetchone()
            rows = cx.execute(
                "SELECT normalized_url FROM pages WHERE audit_id=? LIMIT 251", (audit_id,)
            ).fetchall()
            if not audit or len(rows) > 250:
                return False
            for (url,) in rows:
                try:
                    if _host(urlsplit(url).hostname or "") == host:
                        return True
                except (ValueError, TypeError):
                    continue
    except (sqlite3.Error, OSError, ValueError):
        return False
    return False


def probe_path(workspace: Path, audit_id: str, host: str, port: int) -> Path:
    fingerprint = hashlib.sha256(f"{audit_id}\n{host}\n{port}".encode()).hexdigest()[:32]
    return workspace / "artifacts" / "network" / "probes" / (fingerprint + ".json")


def _canonical(row: dict) -> bytes:
    return json.dumps(row, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def collect_authorized_probe(
    workspace: str | Path, audit_id: str, hostname: str, *,
    permitted_hostname: str, authorized: bool, port: int = 443,
) -> Path:
    """Explicit operator consent and exact AUD target scope. No silent retries."""
    host = _host(hostname)
    if (not authorized or _host(permitted_hostname) != host or
            not _ID.fullmatch(audit_id) or type(port) is not int or port not in (80, 443)):
        raise ValueError("Sondagem não autorizada para o destino informado")
    root = Path(workspace)
    if not _audit_has_target(root, audit_id, host):
        raise ValueError("Destino não vinculado à auditoria informada")
    path = probe_path(root, audit_id, host, port)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Sondagem já registrada; pacote imutável")
    cmd = [sys.executable, "-m", "rasai.network_active_probe", "--worker",
           "--host", host, "--port", str(port)]
    try:
        child = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("Limite total de sondagem excedido") from exc
    if child.returncode or len(child.stdout) > _MAX_RESULT_BYTES:
        raise RuntimeError("Sondagem não concluída de forma verificável")
    try:
        record = json.loads(child.stdout)
    except ValueError as exc:
        raise RuntimeError("Resposta da sondagem inválida") from exc
    if (not isinstance(record, dict) or record.get("contract") != CONTRACT
            or record.get("hostname") != host or record.get("port") != port
            or record.get("state") not in
            {"OBSERVED", "INCONCLUSIVE", "BLOCKED", "COLLECTION_FAILED"}):
        raise RuntimeError("Proveniência da sondagem inválida")
    record["audit_id"] = audit_id
    # Digest is for integrity, never identity of the collector/author.
    record["sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    record["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
    if path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError("Diretório de destino simbólico não permitido")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        output.flush()
        os.fsync(output.fileno())
    return path


def read_authorized_probes(workspace: str | Path, audit_id: str) -> list[dict]:
    root = Path(workspace)
    directory = root / "artifacts" / "network" / "probes"
    if (not _ID.fullmatch(audit_id) or root.is_symlink()
            or directory.is_symlink() or not directory.is_dir()):
        return []
    rows = []
    # Fail closed for unexpectedly large collections.
    paths = list(directory.iterdir())
    if len(paths) > 32:
        return []
    for path in sorted(paths):
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > _MAX_RESULT_BYTES:
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(row, dict) or row.get("audit_id") != audit_id:
                continue
            if row.get("contract") != CONTRACT or row.get("digest_scope") != "INTEGRITY_ONLY_NOT_AUTHORSHIP":
                continue
            host = _host(row.get("hostname"))
            port = row.get("port")
            if port not in (80, 443) or probe_path(root, audit_id, host, port) != path:
                continue
            sha = row.pop("sha256", None)
            digest_scope = row.pop("digest_scope", None)
            if not isinstance(sha, str) or not hmac.compare_digest(
                    hashlib.sha256(_canonical(row)).hexdigest(), sha):
                continue
            row["sha256"] = sha
            row["digest_scope"] = digest_scope
            rows.append(row)
        except (ValueError, TypeError, OSError, UnicodeError):
            continue
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Sondagem de rede autorizada da AUD")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, choices=(80, 443), default=443)
    parser.add_argument("--audit-id")
    parser.add_argument("--workspace")
    parser.add_argument("--permit-exact-host")
    parser.add_argument("--authorize-active-network", action="store_true")
    args = parser.parse_args()
    if args.worker:
        # Worker is an implementation boundary; it does not write artifacts.
        print(json.dumps(_worker_probe(_host(args.host), args.port), ensure_ascii=False))
    else:
        if not args.workspace or not args.audit_id or not args.permit_exact_host:
            parser.error("workspace, audit-id e permit-exact-host são obrigatórios")
        path = collect_authorized_probe(
            args.workspace, args.audit_id, args.host,
            permitted_hostname=args.permit_exact_host,
            authorized=args.authorize_active_network, port=args.port,
        )
        print("Pacote complementar persistido:", path)


if __name__ == "__main__":
    main()
