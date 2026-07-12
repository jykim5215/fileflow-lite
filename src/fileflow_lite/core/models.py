from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

OperationKind = Literal["flatten", "rename"]
TransferMode = Literal["copy", "move", "rename"]


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    mtime_ns: int

    @classmethod
    def from_path(cls, path: Path) -> "FileFingerprint":
        stat = path.stat(follow_symlinks=False)
        return cls(size=stat.st_size, mtime_ns=stat.st_mtime_ns)


@dataclass
class PlanItem:
    source: str
    destination: str
    action: TransferMode
    fingerprint: FileFingerprint
    note: str = ""

    @property
    def source_path(self) -> Path:
        return Path(self.source)

    @property
    def destination_path(self) -> Path:
        return Path(self.destination)


@dataclass
class OperationPlan:
    kind: OperationKind
    items: list[PlanItem]
    source_root: str | None = None
    destination_root: str | None = None
    delete_empty: bool = False
    warnings: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def total_size(self) -> int:
        return sum(item.fingerprint.size for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationPlan":
        items = []
        for raw in data.get("items", []):
            item = dict(raw)
            item["fingerprint"] = FileFingerprint(**item["fingerprint"])
            items.append(PlanItem(**item))
        return cls(
            kind=data["kind"],
            items=items,
            source_root=data.get("source_root"),
            destination_root=data.get("destination_root"),
            delete_empty=data.get("delete_empty", False),
            warnings=list(data.get("warnings", [])),
            excluded=list(data.get("excluded", [])),
            id=data.get("id", uuid4().hex),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )

