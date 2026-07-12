from __future__ import annotations

import os
import re
from pathlib import Path

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class SafetyError(ValueError):
    """Raised when a requested operation violates a safety boundary."""


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_within(path: Path, root: Path) -> bool:
    try:
        resolved(path).relative_to(resolved(root))
        return True
    except ValueError:
        return False


def _same(path_a: Path, path_b: Path) -> bool:
    return os.path.normcase(str(resolved(path_a))) == os.path.normcase(str(resolved(path_b)))


def _protected_roots() -> list[Path]:
    candidates = [
        os.environ.get("WINDIR"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramData"),
    ]
    return [resolved(Path(value)) for value in candidates if value]


def validate_user_root(path: Path, *, must_exist: bool, label: str) -> Path:
    root = resolved(path)
    if must_exist and not root.is_dir():
        raise SafetyError(f"{label} 폴더가 존재하지 않습니다: {root}")
    if root.parent == root:
        raise SafetyError(f"드라이브 루트는 {label} 폴더로 사용할 수 없습니다.")
    for protected in _protected_roots():
        if is_within(root, protected):
            raise SafetyError(f"Windows 보호 영역은 {label} 폴더로 사용할 수 없습니다.")
    return root


def validate_flatten_roots(source: Path, destination: Path) -> tuple[Path, Path]:
    src = validate_user_root(source, must_exist=True, label="원본")
    dst = validate_user_root(destination, must_exist=False, label="대상")
    if _same(src, dst):
        raise SafetyError("원본과 대상 폴더는 서로 달라야 합니다.")
    if is_within(dst, src):
        raise SafetyError("대상 폴더를 원본 폴더 안에 둘 수 없습니다.")
    if dst.exists() and not dst.is_dir():
        raise SafetyError("대상 경로가 폴더가 아닙니다.")
    if not dst.parent.exists():
        raise SafetyError("대상 폴더의 상위 폴더가 존재하지 않습니다.")
    return src, dst


def windows_attributes(path: Path) -> int:
    try:
        return int(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0))
    except OSError:
        return 0


def exclusion_reason(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return "심볼릭 링크"
        attrs = windows_attributes(path)
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
            return "연결된 폴더/재분석 지점"
        if attrs & FILE_ATTRIBUTE_SYSTEM:
            return "시스템 파일"
        if attrs & FILE_ATTRIBUTE_HIDDEN or path.name.startswith("."):
            return "숨김 파일"
    except OSError as exc:
        return f"읽기 오류: {exc}"
    return None


def validate_component(value: str, *, label: str) -> str:
    if INVALID_CHARS.search(value):
        raise SafetyError(f"{label}에 Windows 파일명 금지 문자가 있습니다.")
    if value.endswith((" ", ".")):
        raise SafetyError(f"{label}은 공백이나 마침표로 끝날 수 없습니다.")
    if value.upper() in RESERVED_NAMES:
        raise SafetyError(f"{label}에 Windows 예약 이름을 사용할 수 없습니다.")
    return value


def validate_destination(path: Path, root: Path) -> None:
    if not is_within(path, root):
        raise SafetyError("계획된 대상 경로가 허용된 폴더를 벗어났습니다.")
    if len(str(path)) >= 240:
        raise SafetyError("안전한 Windows 경로 길이를 초과합니다.")

