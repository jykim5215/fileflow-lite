from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS = {
    "bg": "#F3F6F9",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFB",
    "ink": "#17232E",
    "muted": "#667685",
    "line": "#DCE4EA",
    "accent": "#087E72",
    "accent_hover": "#066B61",
    "accent_soft": "#DFF4EF",
    "sidebar": "#17313A",
    "sidebar_active": "#29505A",
    "warning": "#B45F06",
    "danger": "#B42318",
}


def apply_theme(root: tk.Tk) -> ttk.Style:
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.option_add("*Font", "{Segoe UI} 10")
    style.configure("TFrame", background=COLORS["surface"])
    style.configure("App.TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["surface"], relief="solid", borderwidth=1)
    style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["ink"])
    style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground=COLORS["ink"])
    style.configure("Subtitle.TLabel", foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Metric.TLabel", font=("Segoe UI", 16, "bold"), foreground=COLORS["accent"])
    style.configure("TButton", padding=(11, 8), borderwidth=1)
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="white", font=("Segoe UI", 9, "bold"), bordercolor=COLORS["accent"])
    style.map("Accent.TButton", background=[("active", COLORS["accent_hover"]), ("disabled", "#AAB8B6")])
    style.configure("Quiet.TButton", background=COLORS["surface"], foreground=COLORS["ink"], bordercolor=COLORS["line"])
    style.configure("Danger.TButton", background="#FFF0EE", foreground=COLORS["danger"], bordercolor="#F2C9C4")
    style.configure("TEntry", padding=7, fieldbackground="white", bordercolor="#CBD7DD")
    style.configure("TCombobox", padding=6, fieldbackground="white", bordercolor="#CBD7DD")
    style.configure("Treeview", rowheight=30, background="white", fieldbackground="white", bordercolor=COLORS["line"])
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#F3F6F8", foreground="#536672", padding=7)
    style.map("Treeview", background=[("selected", "#DFF4EF")], foreground=[("selected", COLORS["ink"])])
    style.configure("Horizontal.TProgressbar", background=COLORS["accent"], troughcolor="#E5ECEE")
    return style

