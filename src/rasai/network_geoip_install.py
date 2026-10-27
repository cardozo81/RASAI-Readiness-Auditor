"""Install official MaxMind geoipupdate in RASAi-owned operational storage.

Explicit acquisition consent is mandatory. A GitHub release API digest is used
for transport-integrity checking, not as an independent signature attestation.
No installation or download occurs in the audit execution path.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import tarfile
import tempfile
from urllib.request import Request, urlopen
import zipfile

from rasai.network_geoip_operations import updater_executable

RELEASE_API = "https://api.github.com/repos/maxmind/geoipupdate/releases/latest"
MAX_DOWNLOAD = 32 * 1024 * 1024


def _asset_platform() -> tuple[str, str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64",
            "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if system not in ("windows", "linux") or arch is None:
        raise ValueError("Sistema ou arquitetura não suportada")
    return system, arch, "zip" if system == "windows" else "tar.gz"


def _download(url: str, limit: int) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "RASAi-GeoIP-Maintenance",
                                       "Accept": "application/vnd.github+json"}), timeout=20) as reply:
        length = reply.headers.get("Content-Length")
        if length and int(length) > limit:
            raise ValueError("Pacote maior que o limite")
        data = reply.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Pacote maior que o limite")
    return data


def install_official_updater(*, acquisition_authorized: bool) -> dict:
    """Idempotent, fail closed and never overwrite a working binary blindly."""
    target = updater_executable()
    if target.is_symlink():
        return {"state": "FAILED", "error": "UNSAFE_EXECUTABLE_PATH"}
    if target.is_file() and target.stat().st_size > 0:
        return {"state": "READY", "error": None}
    if not acquisition_authorized:
        return {"state": "NOT_AUTHORIZED", "error": "SOFTWARE_ACQUISITION_CONSENT_REQUIRED"}
    try:
        system, arch, extension = _asset_platform()
        release = json.loads(_download(RELEASE_API, 512_000))
        if not isinstance(release, dict) or not isinstance(release.get("assets"), list):
            raise ValueError("Manifesto de release inválido")
        version = release.get("tag_name")
        if not isinstance(version, str) or not version.startswith("v"):
            raise ValueError("Versão de release inválida")
        prefix = "geoipupdate_" + version.removeprefix("v") + "_" + system + "_" + arch
        assets = [asset for asset in release["assets"] if isinstance(asset, dict)
                  and asset.get("name") == prefix + "." + extension]
        if len(assets) != 1:
            raise ValueError("Distribuição oficial não identificada")
        asset = assets[0]
        url, digest = asset.get("browser_download_url"), asset.get("digest")
        if (not isinstance(url, str)
                or not url.startswith("https://github.com/maxmind/geoipupdate/releases/download/")
                or not isinstance(digest, str) or not digest.startswith("sha256:")
                or len(digest) != 71):
            raise ValueError("Integridade da distribuição indisponível")
        payload = _download(url, MAX_DOWNLOAD)
        if hashlib.sha256(payload).hexdigest() != digest[7:]:
            raise ValueError("Hash da distribuição divergente")
        executable = "geoipupdate.exe" if system == "windows" else "geoipupdate"
        if extension == "zip":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                entries = [name for name in archive.namelist()
                           if Path(name).name == executable and not name.endswith("/")]
                if len(entries) != 1:
                    raise ValueError("Executável inválido")
                binary = archive.read(entries[0])
        else:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                entries = [member for member in archive.getmembers()
                           if Path(member.name).name == executable and member.isfile()
                           and not member.issym() and not member.islnk()]
                if len(entries) != 1:
                    raise ValueError("Executável inválido")
                stream = archive.extractfile(entries[0])
                if stream is None:
                    raise ValueError("Executável ausente")
                binary = stream.read(MAX_DOWNLOAD + 1)
        if not 100_000 <= len(binary) <= MAX_DOWNLOAD:
            raise ValueError("Tamanho de executável inválido")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise ValueError("Diretório operacional simbólico")
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".geoipupdate-",
                                         delete=False) as temp:
            staging = Path(temp.name)
            temp.write(binary)
            temp.flush()
            os.fsync(temp.fileno())
        try:
            if system != "windows":
                staging.chmod(staging.stat().st_mode | stat.S_IXUSR)
            os.replace(staging, target)
        finally:
            staging.unlink(missing_ok=True)
        return {"state": "INSTALLED", "version": version, "error": None}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            zipfile.BadZipFile, tarfile.TarError):
        return {"state": "FAILED", "error": "OFFICIAL_INSTALLATION_FAILED"}
