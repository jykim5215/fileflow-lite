from __future__ import annotations

import os
import queue
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from fileflow_lite import __version__
from fileflow_lite.core.executor import execute_plan, undo_latest
from fileflow_lite.core.flatten import plan_flatten
from fileflow_lite.core.journal import log_dir, load_latest
from fileflow_lite.core.models import OperationPlan
from fileflow_lite.core.rename import plan_sequential_rename
from fileflow_lite.integration.context_menu import (
    is_context_menu_registered,
    register_context_menu,
    unregister_context_menu,
)
from fileflow_lite.integration.updater import (
    check_for_update,
    download_verified_update,
    reveal_in_explorer,
)
from fileflow_lite.ui.theme import COLORS, apply_theme


def _format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


class ConfirmationDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, plan: OperationPlan, callback: Callable[[], None]):
        super().__init__(parent)
        self.title("최종 확인 — FileFlow Lite")
        self.geometry("560x430")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg="white")
        self.callback = callback

        header = tk.Frame(self, bg=COLORS["sidebar"], height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="4단계 · 최종 확인", bg=COLORS["sidebar"], fg="#A9C5C4", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=24, pady=(14, 0))
        tk.Label(header, text="실제로 파일을 변경할까요?", bg=COLORS["sidebar"], fg="white", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=24)

        body = tk.Frame(self, bg="white")
        body.pack(fill="both", expand=True, padx=24, pady=20)
        action = "복사" if plan.items and plan.items[0].action == "copy" else "이동" if plan.kind == "flatten" else "이름 변경"
        summary = f"{len(plan.items):,}개 파일 · {_format_size(plan.total_size)} · {action}"
        tk.Label(body, text=summary, bg="white", fg=COLORS["ink"], font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(body, text="미리보기 이후 파일 상태를 다시 검사한 뒤 적용합니다.", bg="white", fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 15))
        safety = tk.Frame(body, bg="#EFF8F5", highlightbackground="#CDE8E1", highlightthickness=1)
        safety.pack(fill="x")
        checks = [
            "기존 파일을 자동으로 덮어쓰지 않습니다.",
            "시스템 파일과 연결된 폴더는 대상에서 제외됩니다.",
            "작업 로그를 남기며 직전 작업은 실행 취소할 수 있습니다.",
        ]
        for text in checks:
            tk.Label(safety, text=f"✓  {text}", bg="#EFF8F5", fg="#21695D", anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=13, pady=5)
        if plan.warnings:
            tk.Label(body, text="\n".join(plan.warnings), bg="#FFF7E9", fg=COLORS["warning"], justify="left", anchor="w", padx=10, pady=8).pack(fill="x", pady=(13, 0))
        footer = tk.Frame(self, bg="#F8FAFB", height=64, highlightbackground=COLORS["line"], highlightthickness=1)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="취소", command=self.destroy, style="Quiet.TButton").pack(side="right", padx=(8, 20), pady=13)
        ttk.Button(footer, text="검사 후 적용", command=self._confirm, style="Accent.TButton").pack(side="right", pady=13)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _confirm(self) -> None:
        self.grab_release()
        self.destroy()
        self.callback()


class MainWindow:
    def __init__(self, root: tk.Tk, *, initial_mode: str = "flatten", initial_path: Path | None = None):
        self.root = root
        apply_theme(root)
        self.root.title(f"FileFlow Lite {__version__}")
        self.root.geometry("1240x780")
        self.root.minsize(1030, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.plan: OperationPlan | None = None
        self.files: list[Path] = []
        self.mode = initial_mode
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._build_ui()
        self.switch_mode(initial_mode)
        if initial_path:
            if initial_mode == "flatten":
                self.source_var.set(str(initial_path))
            else:
                self._load_folder_files(initial_path)
        self._refresh_undo_state()

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=COLORS["bg"])
        outer.pack(fill="both", expand=True)
        sidebar = tk.Frame(outer, bg=COLORS["sidebar"], width=218)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=COLORS["sidebar"])
        brand.pack(fill="x", padx=18, pady=(22, 24))
        tk.Label(brand, text="↘", bg="#42C6B7", fg=COLORS["sidebar"], width=3, height=1, font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(brand, text="FileFlow Lite", bg=COLORS["sidebar"], fg="white", font=("Segoe UI", 14, "bold")).pack(side="left", padx=10)
        self.nav_buttons: dict[str, tk.Button] = {}
        for mode, icon, text in (("flatten", "▱", "폴더 평탄화"), ("rename", "⇢", "순번 이름짓기")):
            button = tk.Button(sidebar, text=f"  {icon}    {text}", anchor="w", relief="flat", bd=0, bg=COLORS["sidebar"], fg="#BED0D2", activebackground=COLORS["sidebar_active"], activeforeground="white", padx=15, pady=12, command=lambda m=mode: self.switch_mode(m))
            button.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[mode] = button
        tk.Frame(sidebar, bg="#38525A", height=1).pack(fill="x", padx=18, pady=12)
        tk.Button(sidebar, text="  ↶    직전 작업 실행 취소", anchor="w", relief="flat", bd=0, bg=COLORS["sidebar"], fg="#BED0D2", activebackground=COLORS["sidebar_active"], activeforeground="white", padx=15, pady=11, command=self.undo).pack(fill="x", padx=10)
        tk.Button(sidebar, text="  ▤    작업 로그 열기", anchor="w", relief="flat", bd=0, bg=COLORS["sidebar"], fg="#BED0D2", activebackground=COLORS["sidebar_active"], activeforeground="white", padx=15, pady=11, command=self.open_logs).pack(fill="x", padx=10)
        tk.Button(sidebar, text="  ⚙    설정 및 업데이트", anchor="w", relief="flat", bd=0, bg=COLORS["sidebar"], fg="#BED0D2", activebackground=COLORS["sidebar_active"], activeforeground="white", padx=15, pady=11, command=self.open_settings).pack(fill="x", padx=10)
        tk.Label(sidebar, text="●  모든 처리는 이 PC에서\n    외부 전송 없음", justify="left", bg=COLORS["sidebar"], fg="#8FADAE", font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=22, pady=20)

        self.main = ttk.Frame(outer, style="App.TFrame")
        self.main.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(self.main, style="App.TFrame")
        top.pack(fill="x", padx=26, pady=(22, 12))
        self.title_label = ttk.Label(top, text="", style="Title.TLabel", background=COLORS["bg"])
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(top, text="", style="Subtitle.TLabel", background=COLORS["bg"])
        self.subtitle_label.pack(anchor="w", pady=(3, 0))
        self.steps_label = tk.Label(top, text="1  범위와 규칙    ───    2  미리보기    ───    3  확인    ───    4  적용", bg="#FFFFFF", fg=COLORS["accent"], anchor="w", padx=14, pady=9, font=("Segoe UI", 9, "bold"), highlightbackground=COLORS["line"], highlightthickness=1)
        self.steps_label.pack(fill="x", pady=(14, 0))

        work = ttk.Frame(self.main, style="App.TFrame")
        work.pack(fill="both", expand=True, padx=26, pady=(0, 14))
        work.columnconfigure(0, weight=4, minsize=370)
        work.columnconfigure(1, weight=7, minsize=500)
        work.rowconfigure(0, weight=1)
        self.form_card = ttk.Frame(work, style="Card.TFrame", padding=18)
        self.form_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        self.preview_card = ttk.Frame(work, style="Card.TFrame", padding=0)
        self.preview_card.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        self._build_forms()
        self._build_preview()

        footer = ttk.Frame(self.main, padding=(26, 11))
        footer.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="폴더 또는 파일을 선택해 시작하세요.")
        ttk.Label(footer, textvariable=self.status_var, style="Subtitle.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="determinate", length=160)
        self.progress.pack(side="left", padx=12)
        self.preview_button = ttk.Button(footer, text="미리보기 만들기", command=self.build_preview, style="Quiet.TButton")
        self.preview_button.pack(side="right", padx=(8, 0))
        self.apply_button = ttk.Button(footer, text="최종 확인…", command=self.confirm_apply, style="Accent.TButton", state="disabled")
        self.apply_button.pack(side="right")

    def _build_forms(self) -> None:
        self.flatten_form = ttk.Frame(self.form_card)
        self.rename_form = ttk.Frame(self.form_card)
        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.transfer_var = tk.StringVar(value="copy")
        self.collision_var = tk.StringVar(value="number")
        self.delete_empty_var = tk.BooleanVar(value=False)
        self.extensions_var = tk.StringVar()
        ttk.Label(self.flatten_form, text="정리할 위치", style="Section.TLabel").pack(anchor="w", pady=(0, 14))
        self._path_field(self.flatten_form, "원본 폴더", self.source_var, self.pick_source)
        self._path_field(self.flatten_form, "대상 폴더", self.destination_var, self.pick_destination)
        ttk.Label(self.flatten_form, text="처리 방식").pack(anchor="w", pady=(4, 5))
        transfer = ttk.Frame(self.flatten_form)
        transfer.pack(fill="x", pady=(0, 12))
        ttk.Radiobutton(transfer, text="복사 · 안전 권장", variable=self.transfer_var, value="copy", command=self._transfer_changed).pack(side="left")
        ttk.Radiobutton(transfer, text="이동", variable=self.transfer_var, value="move", command=self._transfer_changed).pack(side="left", padx=18)
        ttk.Label(self.flatten_form, text="이름 충돌 처리").pack(anchor="w", pady=(0, 5))
        ttk.Combobox(self.flatten_form, textvariable=self.collision_var, state="readonly", values=("number", "folder_prefix")).pack(fill="x", pady=(0, 4))
        ttk.Label(self.flatten_form, text="number: 순번 자동 부여 · folder_prefix: 원래 폴더명 접두어", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(self.flatten_form, text="확장자 필터 (선택, 쉼표 구분)").pack(anchor="w", pady=(0, 5))
        ttk.Entry(self.flatten_form, textvariable=self.extensions_var).pack(fill="x", pady=(0, 4))
        ttk.Label(self.flatten_form, text="예: jpg, png, heic · 비우면 모든 일반 파일", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 12))
        self.delete_check = ttk.Checkbutton(self.flatten_form, text="이동 후 빈 하위 폴더 삭제", variable=self.delete_empty_var, state="disabled")
        self.delete_check.pack(anchor="w")
        ttk.Label(self.flatten_form, text="숨김·시스템 파일과 링크/정션은 항상 제외됩니다.", style="Subtitle.TLabel").pack(anchor="w", pady=(10, 0))

        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.padding_var = tk.IntVar(value=2)
        self.start_var = tk.IntVar(value=1)
        self.sort_var = tk.StringVar(value="name")
        self.desc_var = tk.BooleanVar(value=False)
        ttk.Label(self.rename_form, text="이름 바꿀 파일", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Button(self.rename_form, text="파일 선택…", command=self.pick_files, style="Quiet.TButton").pack(fill="x")
        self.file_count_var = tk.StringVar(value="선택한 파일 없음")
        ttk.Label(self.rename_form, textvariable=self.file_count_var, style="Subtitle.TLabel").pack(anchor="w", pady=(6, 14))
        pair = ttk.Frame(self.rename_form)
        pair.pack(fill="x")
        for column in (0, 1): pair.columnconfigure(column, weight=1)
        ttk.Label(pair, text="접두어").grid(row=0, column=0, sticky="w")
        ttk.Label(pair, text="접미어").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Entry(pair, textvariable=self.prefix_var).grid(row=1, column=0, sticky="ew", pady=(5, 12))
        ttk.Entry(pair, textvariable=self.suffix_var).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(5, 12))
        ttk.Label(pair, text="번호 자릿수").grid(row=2, column=0, sticky="w")
        ttk.Label(pair, text="시작 번호").grid(row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Spinbox(pair, from_=1, to=12, textvariable=self.padding_var).grid(row=3, column=0, sticky="ew", pady=(5, 12))
        ttk.Spinbox(pair, from_=0, to=999999, textvariable=self.start_var).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(5, 12))
        ttk.Label(self.rename_form, text="정렬 기준").pack(anchor="w", pady=(0, 5))
        ttk.Combobox(self.rename_form, textvariable=self.sort_var, state="readonly", values=("name", "mtime", "size")).pack(fill="x")
        ttk.Checkbutton(self.rename_form, text="내림차순", variable=self.desc_var).pack(anchor="w", pady=10)
        self.rename_example = ttk.Label(self.rename_form, text="예시: 01.jpg, 02.png, 03.txt", style="Subtitle.TLabel")
        self.rename_example.pack(anchor="w", pady=(4, 0))

    def _path_field(self, parent, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(0, 5))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 12))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="찾기", command=command, style="Quiet.TButton").pack(side="left", padx=(6, 0))

    def _build_preview(self) -> None:
        head = ttk.Frame(self.preview_card, padding=(16, 14))
        head.pack(fill="x")
        ttk.Label(head, text="실행 전 미리보기", style="Section.TLabel").pack(side="left")
        self.preview_badge = tk.Label(head, text="미리보기 필요", bg="#EEF1F3", fg=COLORS["muted"], padx=8, pady=3, font=("Segoe UI", 8, "bold"))
        self.preview_badge.pack(side="right")
        metrics = ttk.Frame(self.preview_card, padding=(16, 8))
        metrics.pack(fill="x")
        self.count_var, self.size_var, self.warning_var = tk.StringVar(value="0"), tk.StringVar(value="0 B"), tk.StringVar(value="0")
        for title, variable in (("파일", self.count_var), ("예상 용량", self.size_var), ("경고", self.warning_var)):
            box = tk.Frame(metrics, bg="#F1F6F6", padx=12, pady=8)
            box.pack(side="left", fill="x", expand=True, padx=3)
            tk.Label(box, textvariable=variable, bg="#F1F6F6", fg=COLORS["accent"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(box, text=title, bg="#F1F6F6", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        tree_frame = ttk.Frame(self.preview_card)
        tree_frame.pack(fill="both", expand=True, padx=14, pady=(8, 14))
        self.tree = ttk.Treeview(tree_frame, columns=("before", "arrow", "after", "state"), show="headings")
        self.tree.heading("before", text="변경 전")
        self.tree.heading("arrow", text="")
        self.tree.heading("after", text="변경 후")
        self.tree.heading("state", text="상태")
        self.tree.column("before", width=210, anchor="w")
        self.tree.column("arrow", width=32, anchor="center", stretch=False)
        self.tree.column("after", width=210, anchor="w")
        self.tree.column("state", width=90, anchor="center", stretch=False)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def switch_mode(self, mode: str) -> None:
        if self._busy: return
        self.mode = mode
        self.plan = None
        self.apply_button.configure(state="disabled")
        for name, button in self.nav_buttons.items():
            active = name == mode
            button.configure(bg=COLORS["sidebar_active"] if active else COLORS["sidebar"], fg="white" if active else "#BED0D2")
        self.flatten_form.pack_forget(); self.rename_form.pack_forget()
        if mode == "flatten":
            self.title_label.configure(text="폴더 평탄화")
            self.subtitle_label.configure(text="하위 폴더의 파일을 한 곳으로 안전하게 모읍니다.")
            self.flatten_form.pack(fill="both", expand=True)
        else:
            self.title_label.configure(text="일괄 순번 이름짓기")
            self.subtitle_label.configure(text="확장자는 유지하고 선택한 순서 규칙대로 이름을 바꿉니다.")
            self.rename_form.pack(fill="both", expand=True)
        self._clear_preview()

    def _clear_preview(self) -> None:
        for row in self.tree.get_children(): self.tree.delete(row)
        self.count_var.set("0"); self.size_var.set("0 B"); self.warning_var.set("0")
        self.preview_badge.configure(text="미리보기 필요", bg="#EEF1F3", fg=COLORS["muted"])

    def pick_source(self) -> None:
        path = filedialog.askdirectory(title="평탄화할 원본 폴더 선택")
        if path: self.source_var.set(path)

    def pick_destination(self) -> None:
        path = filedialog.askdirectory(title="파일을 모을 대상 폴더 선택", mustexist=False)
        if path: self.destination_var.set(path)

    def pick_files(self) -> None:
        paths = filedialog.askopenfilenames(title="순번으로 이름 바꿀 파일 선택")
        if paths:
            self.files = [Path(p) for p in paths]
            self.file_count_var.set(f"{len(self.files):,}개 파일 선택됨")

    def _load_folder_files(self, folder: Path) -> None:
        try:
            self.files = [p for p in folder.iterdir() if p.is_file() and not p.is_symlink()]
            self.file_count_var.set(f"{len(self.files):,}개 파일 선택됨 · {folder}")
        except OSError as exc:
            messagebox.showerror("폴더 열기 실패", str(exc), parent=self.root)

    def _transfer_changed(self) -> None:
        self.delete_check.configure(state="normal" if self.transfer_var.get() == "move" else "disabled")
        if self.transfer_var.get() != "move": self.delete_empty_var.set(False)

    def build_preview(self) -> None:
        if self._busy: return
        try:
            if self.mode == "flatten":
                extensions = {p.strip() for p in self.extensions_var.get().split(",") if p.strip()} or None
                work = lambda: plan_flatten(Path(self.source_var.get()), Path(self.destination_var.get()), mode=self.transfer_var.get(), collision_policy=self.collision_var.get(), delete_empty=self.delete_empty_var.get(), extensions=extensions)
            else:
                work = lambda: plan_sequential_rename(self.files, prefix=self.prefix_var.get(), suffix=self.suffix_var.get(), padding=int(self.padding_var.get()), start=int(self.start_var.get()), sort_by=self.sort_var.get(), descending=self.desc_var.get())
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("옵션 확인", str(exc), parent=self.root); return
        self._run_worker(work, self._show_plan, "폴더와 파일을 안전하게 검사하는 중…")

    def _show_plan(self, plan: OperationPlan) -> None:
        self.plan = plan
        self._clear_preview()
        for item in plan.items:
            self.tree.insert("", "end", values=(item.source, "→", item.destination, item.note or item.action))
        self.count_var.set(f"{len(plan.items):,}")
        self.size_var.set(_format_size(plan.total_size))
        self.warning_var.set(str(len(plan.warnings)))
        self.preview_badge.configure(text="검사 완료", bg=COLORS["accent_soft"], fg=COLORS["accent"])
        self.status_var.set(f"미리보기 완료 · 제외 {len(plan.excluded):,}개 · 아직 파일은 변경되지 않았습니다.")
        self.apply_button.configure(state="normal" if plan.items else "disabled")

    def confirm_apply(self) -> None:
        if self.plan and not self._busy:
            ConfirmationDialog(self.root, self.plan, self.apply_plan)

    def apply_plan(self) -> None:
        if not self.plan: return
        plan = self.plan
        self._run_worker(lambda: execute_plan(plan, self._progress_callback), self._applied, "파일을 적용하는 중…")

    def _applied(self, journal_path: Path) -> None:
        count = len(self.plan.items) if self.plan else 0
        destination = self.plan.destination_root if self.plan else None
        messagebox.showinfo("작업 완료", f"{count:,}개 파일 작업을 완료했습니다.\n\n로그: {journal_path}", parent=self.root)
        if destination and messagebox.askyesno("결과 폴더", "결과 폴더를 탐색기에서 열까요?", parent=self.root):
            # Local folder path only; no command shell is invoked.
            os.startfile(destination)  # type: ignore[attr-defined]  # nosec B606
        self.plan = None
        self.apply_button.configure(state="disabled")
        self.status_var.set("작업 완료 · 직전 작업 실행 취소를 사용할 수 있습니다.")
        self._refresh_undo_state()

    def undo(self) -> None:
        if self._busy: return
        if not load_latest():
            messagebox.showinfo("실행 취소", "실행 취소할 직전 작업이 없습니다.", parent=self.root); return
        if not messagebox.askyesno("직전 작업 실행 취소", "직전 작업을 안전하게 되돌릴까요?\n파일이 이후 변경된 경우에는 중단됩니다.", parent=self.root): return
        self._run_worker(lambda: undo_latest(self._progress_callback), self._undone, "직전 작업을 되돌리는 중…")

    def _undone(self, count: int) -> None:
        messagebox.showinfo("실행 취소 완료", f"{count:,}개 파일을 원래 상태로 되돌렸습니다.", parent=self.root)
        self.status_var.set("직전 작업 실행 취소 완료")
        self._refresh_undo_state()

    def _refresh_undo_state(self) -> None:
        pass

    def _progress_callback(self, current: int, total: int, name: str) -> None:
        self._queue.put(("progress", current, total, name))

    def _run_worker(self, work: Callable, on_success: Callable, message: str) -> None:
        self._busy = True
        self.preview_button.configure(state="disabled"); self.apply_button.configure(state="disabled")
        self.status_var.set(message); self.progress.configure(value=0, maximum=100)
        def runner():
            try: self._queue.put(("ok", work()))
            except Exception as exc: self._queue.put(("error", exc))
        threading.Thread(target=runner, daemon=True).start()
        self._poll_worker(on_success)

    def _poll_worker(self, on_success: Callable) -> None:
        try:
            while True:
                event = self._queue.get_nowait()
                if event[0] == "progress":
                    _, current, total, name = event
                    self.progress.configure(value=(current / max(total, 1)) * 100)
                    self.status_var.set(f"{current:,}/{total:,} · {name}")
                elif event[0] == "ok":
                    self._busy = False; self.preview_button.configure(state="normal"); self.progress.configure(value=100)
                    on_success(event[1]); return
                elif event[0] == "error":
                    self._busy = False; self.preview_button.configure(state="normal"); self.progress.configure(value=0)
                    self.status_var.set("작업 중단 · 파일은 안전한 상태로 유지됩니다.")
                    messagebox.showerror("작업을 완료하지 못했습니다", str(event[1]), parent=self.root); return
        except queue.Empty:
            self.root.after(80, lambda: self._poll_worker(on_success))

    def open_logs(self) -> None:
        # App-owned local folder only; no command shell is invoked.
        os.startfile(log_dir())  # type: ignore[attr-defined]  # nosec

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.root); dialog.title("설정 및 업데이트"); dialog.geometry("520x380"); dialog.resizable(False, False); dialog.transient(self.root); dialog.configure(bg="white")
        tk.Label(dialog, text="설정 및 업데이트", bg="white", fg=COLORS["ink"], font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=24, pady=(22, 4))
        tk.Label(dialog, text="현재 사용자 범위 우클릭 메뉴는 관리자 권한이 필요하지 않습니다.", bg="white", fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=24)
        context = tk.Frame(dialog, bg="#F6F8F9", padx=14, pady=14); context.pack(fill="x", padx=24, pady=18)
        self.context_status = tk.StringVar(value="등록됨" if is_context_menu_registered() else "등록 안 됨")
        tk.Label(context, text="Windows 탐색기 우클릭 통합", bg="#F6F8F9", fg=COLORS["ink"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(context, textvariable=self.context_status, bg="#F6F8F9", fg=COLORS["accent"]).pack(anchor="w", pady=(3, 9))
        row = tk.Frame(context, bg="#F6F8F9"); row.pack(anchor="w")
        ttk.Button(row, text="메뉴 등록", command=self._register_menu, style="Accent.TButton").pack(side="left")
        ttk.Button(row, text="메뉴 해제", command=self._unregister_menu, style="Quiet.TButton").pack(side="left", padx=7)
        update = tk.Frame(dialog, bg="#F6F8F9", padx=14, pady=14); update.pack(fill="x", padx=24)
        tk.Label(update, text=f"앱 업데이트 · 현재 v{__version__}", bg="#F6F8F9", fg=COLORS["ink"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(update, text="버튼을 눌렀을 때만 GitHub Releases를 확인합니다.", bg="#F6F8F9", fg=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 9))
        ttk.Button(update, text="업데이트 확인", command=lambda: self._check_update(dialog), style="Quiet.TButton").pack(anchor="w")

    def _register_menu(self) -> None:
        try: register_context_menu(); self.context_status.set("등록됨"); messagebox.showinfo("등록 완료", "탐색기 우클릭 메뉴를 등록했습니다.", parent=self.root)
        except Exception as exc: messagebox.showerror("등록 실패", str(exc), parent=self.root)

    def _unregister_menu(self) -> None:
        try: unregister_context_menu(); self.context_status.set("등록 안 됨"); messagebox.showinfo("해제 완료", "FileFlow Lite 우클릭 메뉴를 해제했습니다.", parent=self.root)
        except Exception as exc: messagebox.showerror("해제 실패", str(exc), parent=self.root)

    def _check_update(self, parent) -> None:
        def found(release):
            if release is None: messagebox.showinfo("업데이트", "현재 최신 버전을 사용 중입니다.", parent=parent); return
            if messagebox.askyesno("업데이트 발견", f"새 버전 {release.version}이 있습니다.\n검증 가능한 휴대용 ZIP을 다운로드할까요?", parent=parent):
                if release.portable_url and release.checksum_url:
                    self._run_worker(lambda: download_verified_update(release), lambda path: self._update_downloaded(path), "업데이트를 다운로드하고 검증하는 중…")
                else: webbrowser.open(release.page_url)
        self._run_worker(check_for_update, found, "GitHub에서 업데이트를 확인하는 중…")

    def _update_downloaded(self, path: Path) -> None:
        messagebox.showinfo("업데이트 다운로드 완료", f"SHA-256 검증을 통과했습니다.\n압축을 풀고 새 실행 파일을 사용하세요.\n\n{path}", parent=self.root)
        reveal_in_explorer(path)

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showwarning("작업 진행 중", "파일 상태를 안전하게 마무리할 때까지 창을 닫을 수 없습니다.", parent=self.root)
            return
        self.root.destroy()
