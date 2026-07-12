from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .journal import load_latest, mark_undone, write_journal
from .models import FileFingerprint, OperationPlan, PlanItem
from .safety import SafetyError, is_within, validate_destination

Progress = Callable[[int, int, str], None]


def _fingerprint(path: Path) -> FileFingerprint:
    return FileFingerprint.from_path(path)


def _verify_source(item: PlanItem) -> None:
    path = item.source_path
    if not path.is_file() or path.is_symlink():
        raise SafetyError(f"원본 파일이 없거나 안전하지 않습니다: {path}")
    if _fingerprint(path) != item.fingerprint:
        raise SafetyError(f"미리보기 후 파일이 변경되었습니다: {path.name}")


def _verify_plan_boundary(plan: OperationPlan, item: PlanItem) -> None:
    if plan.kind == "flatten":
        if not plan.destination_root:
            raise SafetyError("대상 폴더 정보가 없습니다.")
        validate_destination(item.destination_path, Path(plan.destination_root))
    else:
        validate_destination(item.destination_path, item.source_path.parent)


def _delete_empty_subfolders(source_root: Path) -> list[str]:
    removed: list[str] = []
    for directory, _, _ in os.walk(source_root, topdown=False, followlinks=False):
        path = Path(directory)
        if path == source_root or path.is_symlink():
            continue
        try:
            path.rmdir()
            removed.append(str(path))
        except OSError:
            pass
    return removed


def _rollback_rename(locations: list[tuple[PlanItem, Path]]) -> None:
    parked: list[tuple[Path, Path]] = []
    for item, current in locations:
        if not current.exists():
            continue
        rollback_temp = item.source_path.parent / f".fileflow-rollback-{uuid4().hex}.tmp"
        os.replace(current, rollback_temp)
        parked.append((rollback_temp, item.source_path))
    for temp, source in parked:
        if source.exists():
            raise RuntimeError(f"롤백 대상이 이미 존재합니다: {source}")
        os.replace(temp, source)


def _execute_rename(plan: OperationPlan, progress: Progress | None) -> list[dict[str, Any]]:
    active = [i for i in plan.items if os.path.normcase(i.source) != os.path.normcase(i.destination)]
    for item in active:
        _verify_source(item)
        _verify_plan_boundary(plan, item)

    source_keys = {os.path.normcase(i.source) for i in active}
    for item in active:
        if item.destination_path.exists() and os.path.normcase(item.destination) not in source_keys:
            raise SafetyError(f"변경 후 파일명이 이미 존재합니다: {item.destination_path.name}")

    staged: list[tuple[PlanItem, Path]] = []
    try:
        for item in active:
            temp = item.source_path.parent / f".fileflow-stage-{uuid4().hex}.tmp"
            os.replace(item.source_path, temp)
            staged.append((item, temp))
        completed: list[tuple[PlanItem, Path]] = []
        for index, (item, temp) in enumerate(staged, 1):
            os.replace(temp, item.destination_path)
            completed.append((item, item.destination_path))
            if progress:
                progress(index, len(active), item.destination_path.name)
    except Exception:
        current_locations = []
        completed_sources = {id(item) for item, _ in locals().get("completed", [])}
        for item, temp in staged:
            current = item.destination_path if id(item) in completed_sources else temp
            current_locations.append((item, current))
        _rollback_rename(current_locations)
        raise

    return [
        {
            "source": item.source,
            "destination": item.destination,
            "action": "rename",
            "destination_fingerprint": _fingerprint(item.destination_path).__dict__,
        }
        for item in active
    ]


def execute_plan(plan: OperationPlan, progress: Progress | None = None) -> Path:
    if not plan.items:
        raise SafetyError("적용할 파일이 없습니다.")
    completed: list[dict[str, Any]] = []
    created_destination = False
    try:
        if plan.kind == "rename":
            completed = _execute_rename(plan, progress)
        else:
            destination_root = Path(plan.destination_root or "")
            if not destination_root.exists():
                destination_root.mkdir(parents=False)
                created_destination = True
            total = len(plan.items)
            for index, item in enumerate(plan.items, 1):
                _verify_source(item)
                _verify_plan_boundary(plan, item)
                destination = item.destination_path
                if destination.exists():
                    raise SafetyError(f"대상 파일이 이미 존재합니다: {destination.name}")
                if item.action == "copy":
                    shutil.copy2(item.source_path, destination)
                elif item.action == "move":
                    shutil.move(str(item.source_path), str(destination))
                else:
                    raise SafetyError("지원하지 않는 작업입니다.")
                completed.append(
                    {
                        "source": item.source,
                        "destination": item.destination,
                        "action": item.action,
                        "destination_fingerprint": _fingerprint(destination).__dict__,
                    }
                )
                if progress:
                    progress(index, total, destination.name)

        deleted_dirs: list[str] = []
        if plan.kind == "flatten" and plan.delete_empty and plan.source_root:
            deleted_dirs = _delete_empty_subfolders(Path(plan.source_root))
        payload = {
            "id": plan.id,
            "status": "success",
            "kind": plan.kind,
            "plan": plan.to_dict(),
            "completed": completed,
            "deleted_dirs": deleted_dirs,
            "created_destination": created_destination,
        }
        return write_journal(payload)
    except Exception as exc:
        rollback_errors: list[str] = []
        if plan.kind == "flatten":
            for entry in reversed(completed):
                source = Path(entry["source"])
                destination = Path(entry["destination"])
                try:
                    if not destination.exists() or not _same_fingerprint(
                        destination, entry["destination_fingerprint"]
                    ):
                        raise SafetyError(f"롤백 대상 상태가 달라졌습니다: {destination}")
                    if entry["action"] == "copy":
                        destination.unlink()
                    elif entry["action"] == "move":
                        if source.exists():
                            raise SafetyError(f"롤백 원본 위치가 사용 중입니다: {source}")
                        source.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(destination), str(source))
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            if created_destination and plan.destination_root:
                try:
                    Path(plan.destination_root).rmdir()
                except OSError:
                    pass
        write_journal(
            {
                "id": plan.id,
                "status": "failed",
                "kind": plan.kind,
                "plan": plan.to_dict(),
                "completed": completed,
                "error": str(exc),
                "rollback_errors": rollback_errors,
                "created_destination": created_destination,
            }
        )
        if rollback_errors:
            raise RuntimeError(
                f"{exc}\n자동 롤백 중 확인이 필요한 항목: " + "; ".join(rollback_errors)
            ) from exc
        raise


def _same_fingerprint(path: Path, raw: dict[str, int]) -> bool:
    try:
        return _fingerprint(path) == FileFingerprint(**raw)
    except (OSError, TypeError):
        return False


def _undo_rename(completed: list[dict[str, Any]]) -> None:
    for entry in completed:
        destination = Path(entry["destination"])
        if not destination.is_file() or not _same_fingerprint(
            destination, entry["destination_fingerprint"]
        ):
            raise SafetyError(f"Undo 대상이 변경되었습니다: {destination.name}")

    source_keys = {os.path.normcase(entry["source"]) for entry in completed}
    destination_keys = {os.path.normcase(entry["destination"]) for entry in completed}
    for entry in completed:
        source = Path(entry["source"])
        if source.exists() and os.path.normcase(str(source)) not in destination_keys:
            raise SafetyError(f"원래 파일명이 이미 사용 중입니다: {source.name}")

    parked: list[tuple[Path, Path]] = []
    for entry in completed:
        destination = Path(entry["destination"])
        temp = destination.parent / f".fileflow-undo-{uuid4().hex}.tmp"
        os.replace(destination, temp)
        parked.append((temp, Path(entry["source"])))
    for temp, source in parked:
        os.replace(temp, source)


def undo_latest(progress: Progress | None = None) -> int:
    payload = load_latest()
    if not payload:
        raise SafetyError("실행 취소할 직전 작업이 없습니다.")
    completed = list(payload.get("completed", []))
    if payload.get("kind") == "rename":
        _undo_rename(completed)
    else:
        for entry in completed:
            source = Path(entry["source"])
            destination = Path(entry["destination"])
            if not destination.is_file() or not _same_fingerprint(
                destination, entry["destination_fingerprint"]
            ):
                raise SafetyError(f"Undo 대상이 변경되었습니다: {destination.name}")
            if entry["action"] == "move" and source.exists():
                raise SafetyError(f"원래 위치가 이미 사용 중입니다: {source}")
        for directory in reversed(payload.get("deleted_dirs", [])):
            Path(directory).mkdir(parents=True, exist_ok=True)
        for index, entry in enumerate(reversed(completed), 1):
            source = Path(entry["source"])
            destination = Path(entry["destination"])
            if entry["action"] == "copy":
                destination.unlink()
            elif entry["action"] == "move":
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            if progress:
                progress(index, len(completed), source.name)
        if payload.get("created_destination"):
            destination_root = payload.get("plan", {}).get("destination_root")
            if destination_root:
                try:
                    Path(destination_root).rmdir()
                except OSError:
                    pass
    mark_undone(payload)
    return len(completed)
