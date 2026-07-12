from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path

from fileflow_lite import __version__

GITHUB_REPOSITORY = "jykim5215/fileflow-lite"
API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
USER_AGENT = f"FileFlow-Lite/{__version__}"
PORTABLE_ASSET = "FileFlow-Lite-portable.zip"
CHECKSUM_ASSET = "SHA256SUMS.txt"
ALLOWED_UPDATE_HOSTS = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    page_url: str
    portable_url: str | None
    checksum_url: str | None
    notes: str


def _validate_update_url(url: str) -> str:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("허용되지 않은 업데이트 주소입니다.") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_UPDATE_HOSTS
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise RuntimeError("허용되지 않은 업데이트 주소입니다.")
    return url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_update_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _request(url: str, *, timeout: int = 15) -> bytes:
    url = _validate_update_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    # URL and every redirect use an HTTPS GitHub host allowlist above.
    with opener.open(request, timeout=timeout) as response:  # nosec B310
        return response.read()


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(part) for part in numbers[:3])


def check_for_update() -> ReleaseInfo | None:
    data = json.loads(_request(API_URL).decode("utf-8"))
    tag = str(data.get("tag_name", "0"))
    if _version_tuple(tag) <= _version_tuple(__version__):
        return None
    assets = {asset["name"]: asset["browser_download_url"] for asset in data.get("assets", [])}
    return ReleaseInfo(
        version=tag.lstrip("vV"),
        page_url=_validate_update_url(data.get("html_url", f"https://github.com/{GITHUB_REPOSITORY}/releases")),
        portable_url=assets.get(PORTABLE_ASSET),
        checksum_url=assets.get(CHECKSUM_ASSET),
        notes=str(data.get("body", ""))[:2000],
    )


def download_verified_update(release: ReleaseInfo) -> Path:
    if not release.portable_url or not release.checksum_url:
        raise RuntimeError("릴리스에 휴대용 ZIP 또는 체크섬 파일이 없습니다.")
    download_dir = Path(tempfile.gettempdir()) / "FileFlowLite-Update"
    download_dir.mkdir(parents=True, exist_ok=True)
    archive = download_dir / PORTABLE_ASSET
    checksum_file = download_dir / CHECKSUM_ASSET
    archive.write_bytes(_request(release.portable_url, timeout=60))
    checksum_file.write_bytes(_request(release.checksum_url))
    expected = None
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == PORTABLE_ASSET:
            expected = parts[0].lower()
            break
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if not expected or actual != expected:
        archive.unlink(missing_ok=True)
        raise RuntimeError("업데이트 파일의 SHA-256 검증에 실패했습니다.")
    return archive


def reveal_in_explorer(path: Path) -> None:
    if os.name == "nt":
        # Opens a validated local folder and never invokes a command shell.
        os.startfile(path.parent)  # type: ignore[attr-defined]  # nosec B606
