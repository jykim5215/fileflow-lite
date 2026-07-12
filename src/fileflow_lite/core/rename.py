from __future__ import annotations

import os
from pathlib import Path

from .models import FileFingerprint, OperationPlan, PlanItem
from .safety import (
    SafetyError,
    exclusion_reason,
    validate_component,
    validate_destination,
    validate_user_root,
)


def plan_sequential_rename(
    files: list[Path],
    *,
    prefix: str = "",
    suffix: str = "",
    padding: int = 1,
    start: int = 1,
    sort_by: str = "name",
    descending: bool = False,
) -> OperationPlan:
    if not files:
        raise SafetyError("이름을 바꿀 파일을 선택해 주세요.")
    if not 1 <= padding <= 12:
        raise SafetyError("번호 자릿수는 1~12 사이여야 합니다.")
    if start < 0:
        raise SafetyError("시작 번호는 0 이상이어야 합니다.")
    validate_component(prefix, label="접두어")
    validate_component(suffix, label="접미어")

    unique: dict[str, Path] = {}
    excluded: list[str] = []
    for raw in files:
        path = raw.expanduser().resolve(strict=False)
        key = os.path.normcase(str(path))
        if key in unique:
            continue
        if not path.is_file():
            excluded.append(f"{path} — 일반 파일이 아님")
            continue
        reason = exclusion_reason(path)
        if reason:
            excluded.append(f"{path} — {reason}")
            continue
        validate_user_root(path.parent, must_exist=True, label="파일 위치")
        unique[key] = path

    selected = list(unique.values())
    if not selected:
        raise SafetyError("안전하게 이름을 바꿀 수 있는 파일이 없습니다.")
    if sort_by == "name":
        key_fn = lambda p: (p.name.casefold(), str(p).casefold())
    elif sort_by == "mtime":
        key_fn = lambda p: (p.stat().st_mtime_ns, p.name.casefold())
    elif sort_by == "size":
        key_fn = lambda p: (p.stat().st_size, p.name.casefold())
    else:
        raise SafetyError("지원하지 않는 정렬 기준입니다.")
    selected.sort(key=key_fn, reverse=descending)

    selected_keys = {os.path.normcase(str(p)) for p in selected}
    occupied_by_parent: dict[str, set[str]] = {}
    for path in selected:
        parent_key = os.path.normcase(str(path.parent))
        if parent_key not in occupied_by_parent:
            occupied_by_parent[parent_key] = {
                os.path.normcase(str(p))
                for p in path.parent.iterdir()
                if os.path.normcase(str(p)) not in selected_keys
            }

    reserved: set[str] = set()
    items: list[PlanItem] = []
    for offset, path in enumerate(selected):
        number = str(start + offset).zfill(padding)
        filename = f"{prefix}{number}{suffix}{path.suffix}"
        validate_component(filename, label="변경 후 파일명")
        destination = path.parent / filename
        validate_destination(destination, path.parent)
        dest_key = os.path.normcase(str(destination))
        parent_key = os.path.normcase(str(path.parent))
        if dest_key in occupied_by_parent[parent_key] or dest_key in reserved:
            raise SafetyError(f"변경 후 이름이 기존 파일과 충돌합니다: {filename}")
        reserved.add(dest_key)
        items.append(
            PlanItem(
                source=str(path),
                destination=str(destination),
                action="rename",
                fingerprint=FileFingerprint.from_path(path),
                note="변경 없음" if os.path.normcase(str(path)) == dest_key else "",
            )
        )

    warnings = [f"보호 항목 {len(excluded)}개를 제외했습니다."] if excluded else []
    roots = {str(path.parent) for path in selected}
    return OperationPlan(
        kind="rename",
        items=items,
        source_root=next(iter(roots)) if len(roots) == 1 else None,
        warnings=warnings,
        excluded=excluded,
    )

