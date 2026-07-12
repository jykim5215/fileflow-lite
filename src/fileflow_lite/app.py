from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk

from fileflow_lite.ui.main_window import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FileFlow Lite")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--flatten", metavar="FOLDER", type=Path)
    group.add_argument("--rename-folder", metavar="FOLDER", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mode = "rename" if args.rename_folder else "flatten"
    initial_path = args.rename_folder or args.flatten
    root = tk.Tk()
    MainWindow(root, initial_mode=mode, initial_path=initial_path)
    root.mainloop()


if __name__ == "__main__":
    main()

