from __future__ import annotations

import os
from pathlib import Path

from .models import FileFingerprint, OperationPlan, PlanItem
from .safety import (
    SafetyError,
    exclusion_reason,
    validate_component,
    validate_destination,
    validate_flatten_roots,
)


def _iter_files(root: Path, excluded: list[str]):
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            excluded.append(f"{directory} — 읽기 실패: {exc}")
            continue
        for entry in entries:
            path = Path(entry.path)
            reason = exclusion_reason(path)
            if reason:
                excluded.append(f"{path} — {reason}")
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    yield path
            except OSError as exc:
                excluded.append(f"{path} — 상태 확인 실패: {exc}")


def _available_destination(
    source: Path,
    destination_root: Path,
    occupied: set[str],
    policy: str,
) -> tuple[Path, bool]:
    stem, suffix = source.stem, source.suffix
    candidate = destination_root / source.name
    key = os.path.normcase(str(candidate))
    if key not in occupied:
        occupied.add(key)
        return candidate, False

    if policy == "folder_prefix":
        prefix = validate_component(source.parent.name or "folder", label="폴더명 접두어")
        candidate = destination_root / f"{prefix}_{source.name}"
        key = os.path.normcase(str(candidate))
        if key not in occupied:
            occupied.add(key)
            return candidate, True
        base_stem = f"{prefix}_{stem}"
    elif policy == "number":
        base_stem = stem
    else:
        raise SafetyError("지원하지 않는 이름 충돌 정책입니다.")

    index = 2
    while True:
        candidate = destination_root / f"{base_stem} ({index}){suffix}"
        key = os.path.normcase(str(candidate))
        if key not in occupied:
            occupied.add(key)
            return candidate, True
        index += 1


def plan_flatten(
    source: Path,
    destination: Path,
    *,
    mode: str = "copy",
    collision_policy: str = "number",
    delete_empty: bool = False,
    extensions: set[str] | None = None,
) -> OperationPlan:
    if mode not in {"copy", "move"}:
        raise SafetyError("처리 방식은 복사 또는 이동이어야 합니다.")
    src, dst = validate_flatten_roots(source, destination)
    excluded: list[str] = []
    occupied: set[str] = set()
    if dst.exists():
        occupied.update(os.path.normcase(str(p)) for p in dst.iterdir())

    normalized_exts = None
    if extensions:
        normalized_exts = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions
        }

    items: list[PlanItem] = []
    collisions = 0
    for file_path in _iter_files(src, excluded):
        if normalized_exts and file_path.suffix.lower() not in normalized_exts:
            excluded.append(f"{file_path} — 확장자 필터")
            continue
        dest, adjusted = _available_destination(
            file_path, dst, occupied, collision_policy
        )
        validate_destination(dest, dst)
        if adjusted:
            collisions += 1
        items.append(
            PlanItem(
                source=str(file_path),
                destination=str(dest),
                action=mode,  # type: ignore[arg-type]
                fingerprint=FileFingerprint.from_path(file_path),
                note="이름 충돌 자동 해결" if adjusted else "",
            )
        )

    warnings = []
    if collisions:
        warnings.append(f"이름 충돌 {collisions}개를 안전하게 조정했습니다.")
    if excluded:
        warnings.append(f"보호/필터 항목 {len(excluded)}개를 제외했습니다.")
    return OperationPlan(
        kind="flatten",
        items=items,
        source_root=str(src),
        destination_root=str(dst),
        delete_empty=bool(delete_empty and mode == "move"),
        warnings=warnings,
        excluded=excluded,
    )

