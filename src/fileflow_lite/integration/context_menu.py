from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only feature
    winreg = None  # type: ignore[assignment]

MENU_KEYS = (
    r"Software\Classes\Directory\shell\FileFlowLite.Flatten",
    r"Software\Classes\Directory\shell\FileFlowLite.Rename",
    r"Software\Classes\Directory\Background\shell\FileFlowLite.Rename",
)


def executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.executable).resolve()


def _command(mode: str, placeholder: str) -> str:
    exe = executable_path()
    if getattr(sys, "frozen", False):
        return f'"{exe}" {mode} "{placeholder}"'
    module_root = Path(__file__).resolve().parents[2]
    return f'"{exe}" -m fileflow_lite {mode} "{placeholder}"'


def _set_menu(key_path: str, label: str, command: str) -> None:
    if winreg is None:
        raise OSError("Windows에서만 탐색기 메뉴를 등록할 수 있습니다.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, label)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, str(executable_path()))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def register_context_menu() -> None:
    _set_menu(
        MENU_KEYS[0],
        "FileFlow Lite로 이 폴더 평탄화",
        _command("--flatten", "%1"),
    )
    _set_menu(
        MENU_KEYS[1],
        "FileFlow Lite 순번 이름짓기",
        _command("--rename-folder", "%1"),
    )
    _set_menu(
        MENU_KEYS[2],
        "FileFlow Lite 순번 이름짓기",
        _command("--rename-folder", "%V"),
    )


def _delete_tree(root, path: str) -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + child)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def unregister_context_menu() -> None:
    if winreg is None:
        raise OSError("Windows에서만 탐색기 메뉴를 해제할 수 있습니다.")
    for key_path in MENU_KEYS:
        _delete_tree(winreg.HKEY_CURRENT_USER, key_path)


def is_context_menu_registered() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEYS[0]):
            return True
    except FileNotFoundError:
        return False

