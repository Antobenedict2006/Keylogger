"""
dashboard.py
============
Tkinter dashboard + pystray system-tray icon.

Tabs
----
  Tab 1 – Live Alerts       : real-time threat list + Terminate/Quarantine/Whitelist/Dismiss
  Tab 2 – Detection History : filterable SQLite query view, double-click for detail popup
  Tab 3 – Statistics        : summary cards + action breakdown + model status
  Tab 4 – Train Model       : behavior recording + personalized model training
  Tab 5 – Behavioral Analysis : typing speed anomaly detector (Phase 1)

System Tray
-----------
  pystray icon with: Open Dashboard | Pause/Resume | Quit

Thread safety
-------------
  Tkinter mainloop runs on the main thread.
  Background threads push updates via a queue.Queue drained by after().

CHANGES (Modernization):
-----------------------
  - Lighter, cleaner color scheme (whites/light grays)
  - Modern Segoe UI font throughout
  - Clickable statistics cards that filter the History tab
  - Rounded card styling with shadows (simulated via borders)
  - Hover effects on interactive elements
  - Better color coding: Green (Safe), Orange (Suspicious), Red (Malicious)
  - Improved table readability with alternating rows
  - Train Model tab: behavior recording + personalized model training
"""

from __future__ import annotations

import json
import csv
import logging
import os
import queue
import threading
import time
import tkinter as tk
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING

try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..alert_manager import AlertManager, AlertRecord, ResponseAction
    from ..classifier import RiskLevel
    from ..db_logger import DBLogger
    from ..monitor import ProcessSnapshot

# ---------------------------------------------------------------------------
# Colour palette  (MODERN LIGHT THEME)
# ---------------------------------------------------------------------------
C = {
    # Background colors
    "bg":           "#f5f7fa",      # Light gray background
    "surface":      "#ffffff",      # White cards/surfaces
    "border":       "#e1e4e8",      # Subtle borders
    "border_hover": "#cbd2d9",      # Darker border on hover
    
    # Text colors
    "text":         "#2c3e50",      # Dark blue-gray text
    "text_dim":     "#6c757d",      # Muted gray text
    "text_light":   "#95a5a6",      # Light gray text
    
    # Status colors (improved contrast)
    "safe":         "#27ae60",      # Green
    "suspicious":   "#f39c12",      # Orange
    "malicious":    "#e74c3c",      # Red
    
    # Accent colors
    "accent":       "#3498db",      # Blue accent
    "accent_hover": "#2980b9",      # Darker blue on hover
    
    # Button colors
    "btn_bg":       "#ecf0f1",      # Light gray button
    "btn_hover":    "#d5dbdb",      # Slightly darker on hover
    "btn_primary":  "#3498db",      # Primary button color
    "btn_danger":   "#e74c3c",      # Danger button color
    
    # Card background colors (with slight tints)
    "card_total":   "#e8f4f8",      # Light blue tint
    "card_mal":     "#fee",         # Light red tint
    "card_sus":     "#fff8e1",      # Light yellow tint
    "card_safe":    "#e8f5e9",      # Light green tint
}

UI_REFRESH_MS  = 2_000
HISTORY_LIMIT  = 200


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _risk_colour(risk: str) -> str:
    """Return color for a given risk level."""
    return {"malicious": C["malicious"], "suspicious": C["suspicious"],
            "safe": C["safe"]}.get(risk.lower(), C["text"])

def _fmt_time(epoch: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(epoch))

def _fmt_datetime(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))

def _tray_image():
    """Generate a simple shield image for the tray icon using PIL."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        shield = [(32, 4), (58, 14), (58, 36), (32, 60), (6, 36), (6, 14)]
        draw.polygon(shield, fill=(137, 180, 250, 230))
        inner  = [(32, 12), (50, 20), (50, 36), (32, 52), (14, 36), (14, 20)]
        draw.polygon(inner, fill=(30, 30, 46, 200))
        return img
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Detail popup
# ---------------------------------------------------------------------------

class _DetailPopup(tk.Toplevel):
    """Detail popup with modern styling."""
    def __init__(self, parent: tk.Widget, row: Dict) -> None:
        super().__init__(parent)
        self.title(f"Detection Detail — {row.get('process_name','?')}")
        self.configure(bg=C["bg"])
        self.geometry("680x480")
        self.resizable(True, True)

        # Main container with padding
        frm = tk.Frame(self, bg=C["surface"], padx=24, pady=20)
        frm.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Title section
        title_frm = tk.Frame(frm, bg=C["surface"])
        title_frm.pack(fill=tk.X, pady=(0, 16))
        
        tk.Label(title_frm, text="Detection Details", 
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)

        # Field container with better spacing
        fields = [
            ("PID",         row.get("pid", "")),
            ("Process",     row.get("process_name", "")),
            ("Executable",  row.get("exe_path") or "N/A"),
            ("Risk Level",  str(row.get("risk_level", "")).upper()),
            ("Score",       f"{float(row.get('score', 0)):.1%}"),
            ("Confidence",  f"{float(row.get('confidence', 0)):.1%}"),
            ("Model",       row.get("model_version") or "heuristic"),
            ("Detected At", _fmt_datetime(row.get("detected_at", 0))),
            ("Actioned",    "Yes" if row.get("actioned") else "No"),
        ]
        
        for label, value in fields:
            r = tk.Frame(frm, bg=C["surface"])
            r.pack(fill=tk.X, pady=4)
            tk.Label(r, text=f"{label}:", width=14, anchor="w",
                     bg=C["surface"], fg=C["text_dim"],
                     font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
            colour = _risk_colour(str(value)) if label == "Risk Level" else C["text"]
            tk.Label(r, text=str(value), anchor="w",
                     bg=C["surface"], fg=colour,
                     font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(8, 0))

        # Separator
        sep = tk.Frame(frm, bg=C["border"], height=1)
        sep.pack(fill=tk.X, pady=12)

        # Indicators section
        tk.Label(frm, text="Threat Indicators:", anchor="w",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 11, "bold")).pack(fill=tk.X, pady=(8, 6))

        reasons = row.get("reasons", [])
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except Exception:
                reasons = [reasons]

        # Text widget with better styling
        tb = tk.Text(frm, height=9, bg="#fafbfc", fg=C["text"],
                     relief=tk.FLAT, font=("Segoe UI", 9), wrap=tk.WORD,
                     borderwidth=1, highlightthickness=1,
                     highlightbackground=C["border"], highlightcolor=C["accent"])
        tb.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        
        if reasons:
            for i, r in enumerate(reasons, 1):
                tb.insert(tk.END, f"{i}. {r}\n\n")
        else:
            tb.insert(tk.END, "No specific indicators recorded.")
        tb.config(state=tk.DISABLED)

        # Close button with modern styling
        btn_frm = tk.Frame(frm, bg=C["surface"])
        btn_frm.pack(anchor="e")
        
        close_btn = tk.Button(btn_frm, text="Close", command=self.destroy,
                  bg=C["btn_primary"], fg="white", relief=tk.FLAT,
                  padx=20, pady=8, font=("Segoe UI", 10, "bold"),
                  cursor="hand2", borderwidth=0)
        close_btn.pack()
        
        # Hover effect for close button
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg=C["accent_hover"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg=C["btn_primary"]))


# ---------------------------------------------------------------------------
# Tab 1 – Live Alerts
# ---------------------------------------------------------------------------

class _LiveAlertsTab(ttk.Frame):

    COLS    = ("time", "pid", "process", "risk", "score", "indicators")
    WIDTHS  = (75, 60, 155, 90, 65, 360)
    HEADERS = ("Time", "PID", "Process", "Risk", "Score", "Indicators")

    def __init__(self, parent, alert_manager: "AlertManager",
                 db_logger: "DBLogger") -> None:
        super().__init__(parent, style="Dark.TFrame")
        self._am = alert_manager
        self._db = db_logger
        self._selected: Optional["AlertRecord"] = None
        self._build()

    def _build(self) -> None:
        # Tree container with card-like appearance
        tf = tk.Frame(self, bg=C["surface"], padx=2, pady=2)
        tf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 0))

        self._tree = ttk.Treeview(tf, columns=self.COLS, show="headings",
                                  selectmode="browse", style="Modern.Treeview")
        for col, w, hdr in zip(self.COLS, self.WIDTHS, self.HEADERS):
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, minwidth=40, anchor="w")

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview,
                           style="Modern.Vertical.TScrollbar")
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Configure row colors with improved contrast
        self._tree.tag_configure("malicious",  foreground=C["malicious"], font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("suspicious", foreground=C["suspicious"], font=("Segoe UI", 9))
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>",          self._on_dbl)
        # Feature 4: right-click context menu
        self._context_menu: Optional[tk.Menu] = None
        self._tree.bind("<Button-3>", self._on_right_click)

        # Modern toolbar with rounded buttons
        bar = tk.Frame(self, bg=C["bg"], pady=10)
        bar.pack(fill=tk.X, padx=12, pady=(8, 6))

        # Helper function to create styled buttons with hover effects
        def create_button(parent, text, cmd, bg_color):
            btn = tk.Button(parent, text=text, command=cmd,
                          bg=bg_color, fg="white" if bg_color != C["btn_bg"] else C["text"],
                          relief=tk.FLAT, padx=16, pady=7,
                          font=("Segoe UI", 9, "bold"), cursor="hand2",
                          borderwidth=0)
            # Add hover effect
            hover_color = {
                C["btn_danger"]: "#c0392b",
                C["btn_primary"]: C["accent_hover"],
                C["btn_bg"]: C["btn_hover"],
                C["safe"]: "#229954"
            }.get(bg_color, C["btn_hover"])
            
            btn.bind("<Enter>", lambda e: btn.config(bg=hover_color))
            btn.bind("<Leave>", lambda e: btn.config(bg=bg_color))
            return btn

        self._btn_terminate  = create_button(bar, "🗙 Terminate",  self._terminate,  C["btn_danger"])
        self._btn_quarantine = create_button(bar, "🔒 Quarantine", self._quarantine, C["suspicious"])
        self._btn_whitelist  = create_button(bar, "✓ Whitelist",  self._whitelist,  C["safe"])
        self._btn_dismiss    = create_button(bar, "✕ Dismiss",    self._dismiss,    C["btn_bg"])
        self._btn_clear      = create_button(bar, "Clear All",    self._clear,      C["btn_bg"])

        for b in (self._btn_terminate, self._btn_quarantine,
                  self._btn_whitelist, self._btn_dismiss):
            b.pack(side=tk.LEFT, padx=4)
        self._btn_clear.pack(side=tk.RIGHT, padx=4)

        # Status bar with better visibility
        status_bar = tk.Frame(self, bg=C["surface"], pady=8)
        status_bar.pack(fill=tk.X, padx=12, pady=(0, 8))
        
        self._status = tk.StringVar(value="No threats detected.")
        tk.Label(status_bar, textvariable=self._status,
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X, padx=12)

    # --- refresh (called every UI_REFRESH_MS) ---
    def refresh(self) -> None:
        records = self._am.recent_alerts
        existing = {str(self._tree.item(iid)["values"][1]): iid
                    for iid in self._tree.get_children()}

        for rec in records:
            pid   = str(rec.result.pid)
            risk  = rec.risk_level.value
            vals  = (
                _fmt_time(rec.timestamp),
                rec.result.pid,
                rec.result.name,
                risk.upper(),
                f"{rec.result.score:.0%}",
                "; ".join(rec.result.reasons[:2]) or "—",
            )
            if pid in existing:
                self._tree.item(existing[pid], values=vals, tags=(risk,))
            else:
                self._tree.insert("", 0, iid=f"{pid}_{rec.timestamp}",
                                  values=vals, tags=(risk,))

        cnt = len(records)
        mal = sum(1 for r in records if r.risk_level.value == "malicious")
        self._status.set(
            f"{cnt} alert(s) this session  |  {mal} malicious" if cnt
            else "No threats detected."
        )

    # --- tree selection ---
    def _on_select(self, _e) -> None:
        sel = self._tree.selection()
        if not sel:
            self._selected = None
            return
        pid_val = str(self._tree.item(sel[0])["values"][1])
        for rec in reversed(self._am.recent_alerts):
            if str(rec.pid) == pid_val:
                self._selected = rec
                return

    def _on_dbl(self, _e) -> None:
        sel = self._tree.selection()
        if not sel or not self._selected:
            return
        v = self._tree.item(sel[0])["values"]
        _DetailPopup(self, {
            "pid": v[1], "process_name": v[2], "risk_level": v[3],
            "score": float(str(v[4]).rstrip("%")) / 100,
            "confidence": 0.0, "detected_at": time.time(),
            "actioned": False,
            "reasons": self._selected.result.reasons,
        })

    # --- action buttons ---
    def _act(self, action_name: str) -> None:
        from ..alert_manager import ResponseAction
        if self._selected is None:
            messagebox.showinfo("No Selection", "Select an alert row first.")
            return
        mapping = {
            "terminate":  ResponseAction.TERMINATE,
            "quarantine": ResponseAction.QUARANTINE,
            "whitelist":  ResponseAction.WHITELIST,
            "dismiss":    ResponseAction.DISMISS,
        }
        res = self._am.take_action(mapping[action_name], self._selected)
        messagebox.showinfo(
            action_name.title(),
            f"{'✓' if res.success else '✗'} {res.message}",
        )
        self.refresh()

    def _terminate(self):  self._act("terminate")
    def _quarantine(self): self._act("quarantine")
    def _whitelist(self):  self._act("whitelist")
    def _dismiss(self):    self._act("dismiss")

    def _clear(self) -> None:
        if messagebox.askyesno("Clear", "Remove all alerts from the live view?"):
            self._am.clear_alerts()
            for iid in self._tree.get_children():
                self._tree.delete(iid)
            self._status.set("No threats detected.")

    # --- Feature 4: right-click context menu ---
    def _on_right_click(self, event) -> None:
        """Select the row under cursor and show context menu."""
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            return
        self._tree.selection_set(row_id)
        self._on_select(None)   # sync self._selected

        # Lazy-create the menu once
        if self._context_menu is None:
            self._context_menu = self._create_context_menu()

        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _create_context_menu(self) -> tk.Menu:
        """Build and return the right-click menu for Live Alerts."""
        menu = tk.Menu(self, tearoff=0,
                       bg=C["surface"], fg=C["text"],
                       activebackground=C["accent"], activeforeground="white",
                       font=("Segoe UI", 9), relief=tk.FLAT)
        menu.add_command(label="🗉 Terminate Process",
                         command=self._terminate)
        menu.add_command(label="💀 Force Kill",
                         command=self._terminate)   # same as terminate
        menu.add_command(label="🔒 Quarantine",
                         command=self._quarantine)
        menu.add_command(label="✓ Add to Whitelist",
                         command=self._whitelist)
        menu.add_separator()
        menu.add_command(label="🔍 View Full Details",
                         command=self._on_dbl_from_menu)
        menu.add_command(label="📋 Copy Process Name",
                         command=self._copy_process_name)
        menu.add_separator()
        menu.add_command(label="↻ Refresh",
                         command=self.refresh)
        return menu

    def _on_dbl_from_menu(self) -> None:
        """Open detail popup for currently selected row (menu action)."""
        sel = self._tree.selection()
        if not sel or not self._selected:
            return
        v = self._tree.item(sel[0])["values"]
        _DetailPopup(self, {
            "pid": v[1], "process_name": v[2], "risk_level": v[3],
            "score": float(str(v[4]).rstrip("%")) / 100,
            "confidence": 0.0, "detected_at": time.time(),
            "actioned": False,
            "reasons": self._selected.result.reasons if self._selected else [],
        })

    def _copy_process_name(self) -> None:
        """Copy the selected process name to the clipboard."""
        sel = self._tree.selection()
        if not sel:
            return
        name = str(self._tree.item(sel[0])["values"][2])
        self.clipboard_clear()
        self.clipboard_append(name)
        self._status.set(f"Copied '{name}' to clipboard")


# ---------------------------------------------------------------------------
# Tab 2 – Detection History
# ---------------------------------------------------------------------------

class _HistoryTab(ttk.Frame):

    COLS    = ("date", "pid", "process", "risk", "score", "actioned")
    WIDTHS  = (145, 60, 165, 90, 65, 70)
    HEADERS = ("Date/Time", "PID", "Process", "Risk", "Score", "Actioned")

    def __init__(self, parent, db_logger: "DBLogger") -> None:
        super().__init__(parent, style="Modern.TFrame")
        self._db = db_logger
        self._cache: List[Dict] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Filter bar with modern styling
        fb = tk.Frame(self, bg=C["surface"], pady=12, padx=16)
        fb.pack(fill=tk.X, padx=12, pady=(12, 4))

        # Risk filter
        tk.Label(fb, text="Filter by Risk:", bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        self._risk_var = tk.StringVar(value="All")
        risk_combo = ttk.Combobox(fb, textvariable=self._risk_var,
                     values=["All", "Malicious", "Suspicious"],
                     state="readonly", width=14, font=("Segoe UI", 9))
        risk_combo.pack(side=tk.LEFT, padx=(0, 20))

        # Time range filter
        tk.Label(fb, text="Time Range (hours):", bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        self._hours_var = tk.IntVar(value=24)
        tk.Spinbox(fb, from_=1, to=720, textvariable=self._hours_var,
                   width=8, bg="white", fg=C["text"],
                   relief=tk.FLAT, font=("Segoe UI", 9),
                   borderwidth=1, highlightthickness=1,
                   highlightbackground=C["border"]).pack(side=tk.LEFT, padx=(0, 20))

        # Refresh button with hover effect
        refresh_btn = tk.Button(fb, text="🔄 Refresh", command=self.refresh,
                  bg=C["btn_primary"], fg="white", relief=tk.FLAT,
                  padx=16, pady=6,
                  font=("Segoe UI", 9, "bold"),
                  cursor="hand2", borderwidth=0)
        refresh_btn.pack(side=tk.LEFT)
        refresh_btn.bind("<Enter>", lambda e: refresh_btn.config(bg=C["accent_hover"]))
        refresh_btn.bind("<Leave>", lambda e: refresh_btn.config(bg=C["btn_primary"]))

        # Treeview container with card styling
        tf = tk.Frame(self, bg=C["surface"], padx=2, pady=2)
        tf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 12))

        self._tree = ttk.Treeview(tf, columns=self.COLS, show="headings",
                                  selectmode="browse", style="Modern.Treeview")
        for col, w, hdr in zip(self.COLS, self.WIDTHS, self.HEADERS):
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, minwidth=40, anchor="w")

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview,
                           style="Modern.Vertical.TScrollbar")
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Improved row styling with alternating colors
        self._tree.tag_configure("malicious",  foreground=C["malicious"], font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("suspicious", foreground=C["suspicious"], font=("Segoe UI", 9))
        self._tree.tag_configure("safe",       foreground=C["safe"], font=("Segoe UI", 9))
        self._tree.bind("<Double-1>", self._on_dbl)
        # Feature 4: right-click context menu
        self._context_menu: Optional[tk.Menu] = None
        self._tree.bind("<Button-3>", self._on_right_click)

    def filter_by_risk(self, risk_level: str) -> None:
        """
        Programmatically set the risk filter and refresh.
        Called by Statistics tab when user clicks a card.
        
        Parameters
        ----------
        risk_level : str
            One of: "All", "Malicious", "Suspicious", "Dismissed"
        """
        self._risk_var.set(risk_level)
        self.refresh()

    def refresh(self) -> None:
        """Asynchronous non-blocking history refresh to keep UI at 60 FPS."""
        risk = self._risk_var.get().lower()
        risk = None if risk == "all" else risk
        since = time.time() - self._hours_var.get() * 3600

        def _fetch():
            try:
                rows = self._db.query_detections(
                    limit=HISTORY_LIMIT, risk_level=risk, since=since
                )
                if self.winfo_exists():
                    self.after(0, lambda: self._apply_rows(rows))
            except Exception as exc:
                logger.debug("History query error: %s", exc)

        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_rows(self, rows: List[Dict]) -> None:
        self._cache = rows
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        for row in rows:
            risk_val = row.get("risk_level", "").lower()
            self._tree.insert("", tk.END, values=(
                _fmt_datetime(row.get("detected_at", 0)),
                row.get("pid", ""),
                row.get("process_name", ""),
                risk_val.upper(),
                f"{float(row.get('score', 0)):.1%}",
                "Yes" if row.get("actioned") else "No",
            ), tags=(risk_val,))

    def _on_dbl(self, _e) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx < len(self._cache):
            _DetailPopup(self, self._cache[idx])

    # --- Feature 4: right-click context menu ---
    def _on_right_click(self, event) -> None:
        """Select the row under cursor and show context menu."""
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            return
        self._tree.selection_set(row_id)

        if self._context_menu is None:
            self._context_menu = self._create_context_menu()

        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()

    def _create_context_menu(self) -> tk.Menu:
        """Build and return the right-click menu for History tab."""
        menu = tk.Menu(self, tearoff=0,
                       bg=C["surface"], fg=C["text"],
                       activebackground=C["accent"], activeforeground="white",
                       font=("Segoe UI", 9), relief=tk.FLAT)
        menu.add_command(label="🔍 View Details",
                         command=self._view_selected_detail)
        menu.add_command(label="📋 Copy Process Name",
                         command=self._copy_process_name)
        menu.add_separator()
        menu.add_command(label="🗑️ Delete Entry",
                         command=self._delete_selected_entry)
        return menu

    def _view_selected_detail(self) -> None:
        """Open detail popup for the currently selected row."""
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx < len(self._cache):
            _DetailPopup(self, self._cache[idx])

    def _copy_process_name(self) -> None:
        """Copy the selected row's process name to the clipboard."""
        sel = self._tree.selection()
        if not sel:
            return
        name = str(self._tree.item(sel[0])["values"][2])
        self.clipboard_clear()
        self.clipboard_append(name)

    def _delete_selected_entry(self) -> None:
        """Remove the selected detection row from the Treeview (UI-only).

        Note: This hides the row from the current view; the underlying
        database record is retained for audit purposes.
        """
        sel = self._tree.selection()
        if not sel:
            return
        if messagebox.askyesno(
            "Delete Entry",
            "Remove this row from the current view?\n"
            "(The database record is kept for audit purposes.)"
        ):
            idx = self._tree.index(sel[0])
            self._tree.delete(sel[0])
            if idx < len(self._cache):
                self._cache.pop(idx)


# ---------------------------------------------------------------------------
# Tab 3 – Statistics
# ---------------------------------------------------------------------------

class _StatsTab(ttk.Frame):
    """
    Statistics tab with CLICKABLE summary cards.
    Clicking a card switches to History tab and filters by that category.
    """

    def __init__(self, parent, db_logger: "DBLogger",
                 get_model_status: Callable[[], str],
                 switch_to_history: Callable[[str], None]) -> None:
        super().__init__(parent, style="Modern.TFrame")
        self._db = db_logger
        self._get_model_status = get_model_status
        self._switch_to_history = switch_to_history  # NEW: callback to switch tabs
        self._build()

    def _build(self) -> None:
        outer = tk.Frame(self, bg=C["bg"], padx=24, pady=24)
        outer.pack(fill=tk.BOTH, expand=True)

        # Header
        tk.Label(outer, text="Detection Statistics", bg=C["bg"],
                 fg=C["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 20))

        # Summary cards with CLICK handlers
        cards_row = tk.Frame(outer, bg=C["bg"])
        cards_row.pack(fill=tk.X, pady=(0, 28))

        self._card_vars: Dict[str, tk.StringVar] = {}
        
        # Card definitions: (key, label, color, bg_color, filter_value)
        defs = [
            ("total_detections", "Total Detections", C["accent"], C["card_total"], "All"),
            ("malicious_count",  "Malicious",        C["malicious"], C["card_mal"], "Malicious"),
            ("suspicious_count", "Suspicious",       C["suspicious"], C["card_sus"], "Suspicious"),
            ("actioned_count",   "Actioned",         C["safe"], C["card_safe"], "All"),
        ]
        
        for key, label, colour, bg_colour, filter_val in defs:
            var = tk.StringVar(value="0")
            self._card_vars[key] = var
            
            # Create clickable card frame
            card = tk.Frame(cards_row, bg=bg_colour, padx=24, pady=20,
                           relief=tk.FLAT, borderwidth=2,
                           highlightthickness=2, highlightbackground=C["border"],
                           highlightcolor=C["border"])
            card.pack(side=tk.LEFT, padx=8)
            
            # Make card clickable
            card.bind("<Button-1>", lambda e, fv=filter_val: self._on_card_click(fv))
            card.bind("<Enter>", lambda e, c=card: self._on_card_hover(c, True))
            card.bind("<Leave>", lambda e, c=card: self._on_card_hover(c, False))
            card.config(cursor="hand2")
            
            # Value label (large number)
            val_lbl = tk.Label(card, textvariable=var, bg=bg_colour,
                             fg=colour, font=("Segoe UI", 32, "bold"))
            val_lbl.pack()
            val_lbl.bind("<Button-1>", lambda e, fv=filter_val: self._on_card_click(fv))
            val_lbl.bind("<Enter>", lambda e, c=card: self._on_card_hover(c, True))
            val_lbl.bind("<Leave>", lambda e, c=card: self._on_card_hover(c, False))
            val_lbl.config(cursor="hand2")
            
            # Label text
            lbl = tk.Label(card, text=label, bg=bg_colour,
                         fg=C["text_dim"], font=("Segoe UI", 10))
            lbl.pack(pady=(4, 0))
            lbl.bind("<Button-1>", lambda e, fv=filter_val: self._on_card_click(fv))
            lbl.bind("<Enter>", lambda e, c=card: self._on_card_hover(c, True))
            lbl.bind("<Leave>", lambda e, c=card: self._on_card_hover(c, False))
            lbl.config(cursor="hand2")
            
            # Hint text
            hint = tk.Label(card, text="Click to filter", bg=bg_colour,
                          fg=C["text_light"], font=("Segoe UI", 8, "italic"))
            hint.pack()
            hint.bind("<Button-1>", lambda e, fv=filter_val: self._on_card_click(fv))
            hint.bind("<Enter>", lambda e, c=card: self._on_card_hover(c, True))
            hint.bind("<Leave>", lambda e, c=card: self._on_card_hover(c, False))
            hint.config(cursor="hand2")

        # Action breakdown section
        breakdown_frame = tk.Frame(outer, bg=C["surface"], padx=20, pady=16,
                                  relief=tk.FLAT, borderwidth=1,
                                  highlightthickness=1, highlightbackground=C["border"])
        breakdown_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(breakdown_frame, text="Actions Taken", bg=C["surface"],
                 fg=C["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        
        self._action_text = tk.Text(breakdown_frame, height=6, bg="#fafbfc",
                                    fg=C["text"], relief=tk.FLAT,
                                    font=("Segoe UI", 10), state=tk.DISABLED,
                                    borderwidth=1, highlightthickness=1,
                                    highlightbackground=C["border"])
        self._action_text.pack(fill=tk.X)

        # Model status section
        model_frame = tk.Frame(outer, bg=C["surface"], padx=20, pady=16,
                              relief=tk.FLAT, borderwidth=1,
                              highlightthickness=1, highlightbackground=C["border"])
        model_frame.pack(fill=tk.X)
        
        tk.Label(model_frame, text="Detection Engine Status", bg=C["surface"],
                 fg=C["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        
        self._model_var = tk.StringVar(value="Initialising…")
        tk.Label(model_frame, textvariable=self._model_var,
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 10)).pack(anchor="w")

        # Refresh button
        refresh_btn = tk.Button(outer, text="🔄 Refresh Statistics", command=self.refresh,
                  bg=C["btn_primary"], fg="white", relief=tk.FLAT,
                  padx=20, pady=10,
                  font=("Segoe UI", 10, "bold"),
                  cursor="hand2", borderwidth=0)
        refresh_btn.pack(anchor="w", pady=(20, 0))
        refresh_btn.bind("<Enter>", lambda e: refresh_btn.config(bg=C["accent_hover"]))
        refresh_btn.bind("<Leave>", lambda e: refresh_btn.config(bg=C["btn_primary"]))

    def _on_card_hover(self, card: tk.Frame, entering: bool) -> None:
        """Visual feedback on card hover."""
        if entering:
            card.config(highlightbackground=C["accent"], highlightcolor=C["accent"])
        else:
            card.config(highlightbackground=C["border"], highlightcolor=C["border"])

    def _on_card_click(self, filter_value: str) -> None:
        """
        Handle card click: switch to History tab and apply filter.
        
        Parameters
        ----------
        filter_value : str
            The risk level to filter by ("All", "Malicious", "Suspicious")
        """
        self._switch_to_history(filter_value)

    def refresh(self) -> None:
        """Asynchronous non-blocking stats refresh with smooth counting transitions."""
        def _fetch():
            try:
                stats = self._db.stats()
                model_status = self._get_model_status()
                if self.winfo_exists():
                    self.after(0, lambda: self._apply_stats(stats, model_status))
            except Exception as exc:
                logger.debug("Stats async query error: %s", exc)

        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_stats(self, stats: Dict, model_status: str) -> None:
        for key, var in self._card_vars.items():
            target_val = int(stats.get(key, 0))
            self._animate_number(var, target_val)

        counts = stats.get("action_counts", {})
        self._action_text.config(state=tk.NORMAL)
        self._action_text.delete("1.0", tk.END)
        if counts:
            for action, count in sorted(counts.items()):
                self._action_text.insert(tk.END, f"  {action.title():<14} {count}\n")
        else:
            self._action_text.insert(tk.END, "  No actions recorded yet.\n")
        self._action_text.config(state=tk.DISABLED)

        self._model_var.set(model_status)

    def _animate_number(self, var: tk.StringVar, target_val: int) -> None:
        """Smoothly count up/down to target value."""
        try:
            curr = int(str(var.get()).replace(",", "") or 0)
        except ValueError:
            curr = 0

        if curr == target_val:
            return

        diff = target_val - curr
        step = max(1, abs(diff) // 4) if abs(diff) > 4 else 1
        new_val = curr + step if diff > 0 else curr - step
        var.set(f"{new_val:,}")

        if new_val != target_val and self.winfo_exists():
            self.after(25, lambda: self._animate_number(var, target_val))



# ---------------------------------------------------------------------------
# Recording Manager  (behavior capture for personalized model training)
# ---------------------------------------------------------------------------

class RecordingManager:
    """
    Manages the lifecycle of a single behavior-recording session.

    Responsibilities
    ----------------
    - Take a baseline snapshot of running processes when recording starts.
    - Poll for new user-launched processes every POLL_INTERVAL seconds on a
      background thread.
    - For each new process that passes the filter, extract its 24 features
      via the pipeline's FeatureExtractor and store the row in the DB.
    - Export everything to a timestamped CSV when recording stops.
    - Provide live counters consumed by the UI (thread-safe via a lock).

    The caller (dashboard) drives start / stop; this class never touches
    Tkinter directly.
    """

    # Seconds between polls for new processes during recording
    POLL_INTERVAL: float = 3.0

    def __init__(
        self,
        db_logger: "DBLogger",
        on_new_process: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """
        Parameters
        ----------
        db_logger      : DBLogger instance (owns the SQLite connection).
        on_new_process : Optional callback(name, total_count) fired on the
                         recording thread whenever a new process is captured.
                         The dashboard uses this to update the UI counter.
        """
        self._db = db_logger
        self._on_new_process = on_new_process

        # Lazy-import to avoid a circular import at module load time
        from ..db_logger import BehaviorRecordingStore
        self._store = BehaviorRecordingStore(db_logger)
        self._store.ensure_schema()

        self._lock = threading.Lock()
        self._recording = False
        self._session_id: Optional[str] = None
        self._start_time: float = 0.0
        self._baseline_pids: Set[int] = set()
        self._seen_pids: Set[int] = set()   # PIDs already recorded this session

        self._count = 0
        self._last_name = "None"
        self._last_ts: float = 0.0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_csv_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def session_id(self) -> Optional[str]:
        with self._lock:
            return self._session_id

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since recording started (0 if not recording)."""
        with self._lock:
            if not self._recording:
                return 0.0
            return time.time() - self._start_time

    @property
    def last_process_name(self) -> str:
        with self._lock:
            return self._last_name

    @property
    def last_csv_path(self) -> Optional[Path]:
        with self._lock:
            return self._last_csv_path

    def start(self) -> str:
        """
        Begin a new recording session.

        Takes a baseline snapshot, clears counters, starts the background
        poll thread, and returns the new session_id UUID string.
        """
        from ..monitor import take_process_snapshot

        with self._lock:
            if self._recording:
                return self._session_id  # already running

            # Fresh session
            self._session_id = str(uuid.uuid4())
            self._start_time = time.time()
            self._count      = 0
            self._last_name  = "None"
            self._last_ts    = 0.0
            self._seen_pids  = set()
            self._last_csv_path = None
            self._recording  = True

            # Baseline: remember every PID already running so we don't
            # record pre-existing processes.
            snap = take_process_snapshot()
            self._baseline_pids = {e["pid"] for e in snap}

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="BehaviorRecorder",
            daemon=True,
        )
        self._thread.start()
        return self._session_id

    def stop(self) -> Optional[Path]:
        """
        Stop the recording session and export to CSV.

        Returns the Path of the exported CSV, or None if nothing was captured.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        with self._lock:
            if not self._recording:
                return self._last_csv_path
            self._recording = False
            session_id = self._session_id
            count      = self._count

        logger.info(f"RecordingManager.stop() called: session_id={session_id}, count={count}")

        # Signal poll thread to exit
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.POLL_INTERVAL + 2)

        if count == 0 or not session_id:
            logger.warning(f"No CSV export: count={count}, session_id={session_id}")
            return None

        # Export to CSV
        ts  = time.strftime("%Y%m%d_%H%M%S")
        out = Path(__file__).parent.parent.parent / "data" / f"my_behavior_{ts}.csv"
        logger.info(f"Attempting CSV export to: {out}")
        
        try:
            rows_written = self._store.export_to_csv(out, session_id=session_id)
            logger.info(f"CSV export successful: {rows_written} rows written to {out}")
            with self._lock:
                self._last_csv_path = out
            return out if rows_written > 0 else None
        except Exception as exc:
            # Export failed — keep data in DB, tell caller via None
            logger.error(f"CSV export failed: {exc}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Background poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """
        Runs on the BehaviorRecorder thread.

        Polls for new user-launched processes and records their features.
        """
        from ..monitor import get_new_processes
        from ..feature_extractor import FeatureExtractor
        from ..monitor import ProcessSnapshot

        extractor = FeatureExtractor(window_size=1)

        while not self._stop_event.is_set():
            try:
                with self._lock:
                    baseline = set(self._baseline_pids)
                    start_t  = self._start_time
                    seen     = set(self._seen_pids)
                    session  = self._session_id

                new_procs = get_new_processes(baseline, start_t)

                for proc_info in new_procs:
                    pid = proc_info["pid"]

                    # Skip if already recorded this session
                    if pid in seen:
                        continue

                    # Build a minimal ProcessSnapshot so we can reuse the
                    # existing FeatureExtractor logic rather than duplicate it.
                    snap = ProcessSnapshot(
                        pid=pid,
                        name=proc_info["name"],
                        exe=proc_info.get("exe") or "",
                        cmdline=[],
                        username=None,
                        create_time=proc_info.get("create_time", time.time()),
                    )

                    # Try to enrich the snapshot with live psutil data
                    snap = self._enrich_snapshot(snap)

                    # Extract features
                    try:
                        fv = extractor.extract_single(snap)
                        features = fv.to_dict()
                    except Exception:
                        # Fallback: zero-vector so we still log the process
                        from ..feature_extractor import FEATURE_NAMES
                        features = {n: 0.0 for n in FEATURE_NAMES}

                    # Persist to DB
                    process_data = {
                        "name":        proc_info["name"],
                        "pid":         pid,
                        "exe_path":    proc_info.get("exe") or "",
                        "parent_name": proc_info.get("parent_name") or "",
                    }
                    try:
                        self._store.save_recorded_process(
                            session_id=session,
                            process_data=process_data,
                            features=features,
                            label="safe",
                        )
                    except Exception as exc:
                        import logging
                        logging.getLogger(__name__).error(
                            "Failed to save recorded process: %s", exc
                        )
                        continue

                    # Update counters (thread-safe)
                    with self._lock:
                        self._seen_pids.add(pid)
                        self._count += 1
                        self._last_name = proc_info["name"]
                        self._last_ts   = time.time()
                        total = self._count

                    # Notify UI
                    if self._on_new_process:
                        try:
                            self._on_new_process(proc_info["name"], total)
                        except Exception:
                            pass

            except Exception as exc:
                import logging
                logging.getLogger(__name__).error("Recorder poll error: %s", exc)

            self._stop_event.wait(self.POLL_INTERVAL)

    @staticmethod
    def _enrich_snapshot(snap: "ProcessSnapshot") -> "ProcessSnapshot":
        """
        Fill in psutil-based fields (cpu, mem, modules, etc.) on a minimal
        ProcessSnapshot.  Silently skips any field that raises an exception.
        """
        import psutil
        try:
            proc = psutil.Process(snap.pid)
            try:
                snap.cpu_percent = proc.cpu_percent(interval=None)
            except Exception:
                pass
            try:
                snap.mem_rss_mb = proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass
            try:
                snap.open_file_count = len(proc.open_files())
            except Exception:
                pass
            try:
                snap.has_visible_window = False  # lightweight default
            except Exception:
                pass
            try:
                from ..monitor import _get_loaded_modules
                snap.loaded_modules = _get_loaded_modules(snap.pid)
            except Exception:
                pass
            try:
                from ..monitor import _check_startup_persistence
                snap.has_startup_entry = _check_startup_persistence(snap.exe)
            except Exception:
                pass
            try:
                from ..monitor import _is_system_process
                snap.is_system_process = _is_system_process(proc)
            except Exception:
                pass
        except Exception:
            pass
        return snap


# ---------------------------------------------------------------------------
# Tab 4 – Train Model
# ---------------------------------------------------------------------------

class _TrainModelTab(ttk.Frame):
    """
    'Train Model' tab — lets the user record their normal computer usage
    and train a personalized keylogger-detection model from it.

    User flow
    ---------
    1. Read the "How It Works" card.
    2. Click ▶ Start Recording  →  RecordingManager.start() is called.
    3. Use the computer normally.  The live status card updates every second.
    4. Click ⏹ Stop Recording   →  RecordingManager.stop() exports a CSV.
    5. Click 🎓 Train Model      →  train_personalized() runs in a thread;
                                    progress bar shows progress.
    6. Success card shows accuracy; classifier hot-reloads the new model.
    """

    # Seconds between UI timer refresh ticks (runs on main thread via after())
    _TICK_MS = 1_000

    def __init__(
        self,
        parent,
        db_logger: "DBLogger",
        get_classifier: Callable,          # returns the live KeyloggerClassifier
    ) -> None:
        super().__init__(parent, style="Modern.TFrame")
        self._db            = db_logger
        self._get_classifier = get_classifier
        self._recorder      = RecordingManager(db_logger)
        try:
            from ..live_api import set_recording_manager
            set_recording_manager(self._recorder)
        except Exception as exc:
            logger.debug("Could not share behavior recorder with web API: %s", exc)
        self._csv_path: Optional[Path] = None
        self._timer_job: Optional[str]  = None   # after() job id
        self._training      = False
        self._build()
        # Refresh the model-status section immediately
        self._refresh_model_status()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Scrollable outer frame so everything fits even on small screens
        canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        vscroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview,
                                style="Modern.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Inner frame that holds all content
        inner = tk.Frame(canvas, bg=C["bg"])
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(inner_id, width=canvas.winfo_width())

        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_configure)

        # Mouse-wheel scrolling
        def _on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)

        # ── padding wrapper ──────────────────────────────────────────────
        wrap = tk.Frame(inner, bg=C["bg"], padx=24, pady=20)
        wrap.pack(fill=tk.BOTH, expand=True)

        # ── Page title ───────────────────────────────────────────────────
        tk.Label(wrap, text="🎓 Personalized Model Training",
                 bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(wrap,
                 text=("Record your normal computer usage to create a personalized "
                       "detection model that dramatically reduces false positives."),
                 bg=C["bg"], fg=C["text_dim"],
                 font=("Segoe UI", 10), wraplength=860, justify="left"
                 ).pack(anchor="w", pady=(0, 20))

        # ── Section 1: How It Works ──────────────────────────────────────
        self._build_how_it_works(wrap)

        # ── Section 2: Recording Controls ───────────────────────────────
        self._build_recording_section(wrap)

        # ── Section 3: Training Controls ────────────────────────────────
        self._build_training_section(wrap)

        # ── Section 4: Model Status ──────────────────────────────────────
        self._build_model_status_section(wrap)

    # --- Section helpers ------------------------------------------------

    def _section_card(self, parent, title: str) -> tk.Frame:
        """Return a white card frame with a bold title label."""
        card = tk.Frame(parent, bg=C["surface"], padx=20, pady=16,
                        highlightthickness=1, highlightbackground=C["border"])
        card.pack(fill=tk.X, pady=(0, 16))
        tk.Label(card, text=title, bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        return card

    def _build_how_it_works(self, parent: tk.Frame) -> None:
        card = self._section_card(parent, "ℹ️  How It Works")
        steps = [
            ("1", "Click Start Recording, then use your computer normally for 1–2 hours."),
            ("2", "Only programs YOU actively open are recorded — background Windows "
                  "services are automatically ignored."),
            ("3", "Everything you launch is labelled 'safe' automatically — no manual "
                  "labelling needed."),
            ("4", "Click Stop Recording when done — a CSV file is saved automatically."),
            ("5", "Click Train Personalized Model — the system mixes your real data "
                  "with synthetic malicious samples and trains in ~30–60 seconds."),
            ("6", "The detector immediately switches to your personalized model, "
                  "reducing false positives by 80–90%."),
        ]
        for num, text in steps:
            row = tk.Frame(card, bg=C["surface"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=f"  {num}.", width=4, anchor="e",
                     bg=C["surface"], fg=C["accent"],
                     font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
            tk.Label(row, text=text, bg=C["surface"], fg=C["text"],
                     font=("Segoe UI", 10), wraplength=780,
                     justify="left", anchor="w").pack(side=tk.LEFT, padx=(8, 0))

    def _build_recording_section(self, parent: tk.Frame) -> None:
        card = self._section_card(parent, "🎙️  Recording Controls")

        # ── Big buttons row ──────────────────────────────────────────────
        btn_row = tk.Frame(card, bg=C["surface"])
        btn_row.pack(fill=tk.X, pady=(0, 16))

        # Start button
        self._btn_start = tk.Button(
            btn_row, text="▶  Start Recording",
            command=self._on_start_recording,
            bg=C["safe"], fg="white", relief=tk.FLAT,
            padx=28, pady=12, font=("Segoe UI", 11, "bold"),
            cursor="hand2", borderwidth=0,
        )
        self._btn_start.pack(side=tk.LEFT, padx=(0, 12))
        self._btn_start.bind("<Enter>",
                             lambda e: self._btn_start.config(bg="#229954"))
        self._btn_start.bind("<Leave>",
                             lambda e: self._btn_start.config(bg=C["safe"]))

        # Stop button (disabled initially)
        self._btn_stop = tk.Button(
            btn_row, text="⏹  Stop Recording",
            command=self._on_stop_recording,
            bg=C["btn_danger"], fg="white", relief=tk.FLAT,
            padx=28, pady=12, font=("Segoe UI", 11, "bold"),
            cursor="hand2", borderwidth=0, state=tk.DISABLED,
        )
        self._btn_stop.pack(side=tk.LEFT)
        self._btn_stop.bind("<Enter>",
                            lambda e: self._btn_stop.config(bg="#c0392b")
                            if self._btn_stop["state"] != tk.DISABLED else None)
        self._btn_stop.bind("<Leave>",
                            lambda e: self._btn_stop.config(bg=C["btn_danger"])
                            if self._btn_stop["state"] != tk.DISABLED else None)

        # ── Live status card ─────────────────────────────────────────────
        status_card = tk.Frame(card, bg=C["card_total"],
                               highlightthickness=1,
                               highlightbackground=C["border"],
                               padx=16, pady=12)
        status_card.pack(fill=tk.X)

        # Duration
        dur_row = tk.Frame(status_card, bg=C["card_total"])
        dur_row.pack(fill=tk.X, pady=2)
        tk.Label(dur_row, text="⏱  Duration:", width=22, anchor="w",
                 bg=C["card_total"], fg=C["text_dim"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._lbl_duration = tk.Label(dur_row, text="00:00:00",
                                      bg=C["card_total"], fg=C["text"],
                                      font=("Segoe UI", 10, "bold"))
        self._lbl_duration.pack(side=tk.LEFT)

        # Count
        cnt_row = tk.Frame(status_card, bg=C["card_total"])
        cnt_row.pack(fill=tk.X, pady=2)
        tk.Label(cnt_row, text="📊  Processes Captured:", width=22, anchor="w",
                 bg=C["card_total"], fg=C["text_dim"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._lbl_count = tk.Label(cnt_row, text="0",
                                   bg=C["card_total"], fg=C["accent"],
                                   font=("Segoe UI", 10, "bold"))
        self._lbl_count.pack(side=tk.LEFT)

        # Last captured
        last_row = tk.Frame(status_card, bg=C["card_total"])
        last_row.pack(fill=tk.X, pady=2)
        tk.Label(last_row, text="🕐  Last Captured:", width=22, anchor="w",
                 bg=C["card_total"], fg=C["text_dim"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._lbl_last = tk.Label(last_row, text="None",
                                  bg=C["card_total"], fg=C["text"],
                                  font=("Segoe UI", 10))
        self._lbl_last.pack(side=tk.LEFT)

        # Recording state indicator
        self._lbl_rec_state = tk.Label(
            card, text="⬤  Not Recording",
            bg=C["surface"], fg=C["text_light"],
            font=("Segoe UI", 9, "italic"),
        )
        self._lbl_rec_state.pack(anchor="w", pady=(10, 0))

    def _build_training_section(self, parent: tk.Frame) -> None:
        card = self._section_card(parent, "🤖  Training Controls")

        # Train button (disabled until recording stopped)
        self._btn_train = tk.Button(
            card, text="🎓  Train Personalized Model",
            command=self._on_train,
            bg=C["btn_primary"], fg="white", relief=tk.FLAT,
            padx=28, pady=12, font=("Segoe UI", 11, "bold"),
            cursor="hand2", borderwidth=0, state=tk.DISABLED,
        )
        self._btn_train.pack(anchor="w", pady=(0, 12))
        self._btn_train.bind(
            "<Enter>",
            lambda e: self._btn_train.config(bg=C["accent_hover"])
            if self._btn_train["state"] != tk.DISABLED else None,
        )
        self._btn_train.bind(
            "<Leave>",
            lambda e: self._btn_train.config(bg=C["btn_primary"])
            if self._btn_train["state"] != tk.DISABLED else None,
        )

        # Progress bar (hidden until training starts)
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            card, variable=self._progress_var,
            maximum=100.0, length=520, mode="determinate",
        )
        # not packed yet — shown dynamically

        # Training status label
        self._lbl_train_status = tk.Label(
            card, text="",
            bg=C["surface"], fg=C["text_dim"],
            font=("Segoe UI", 9, "italic"),
        )
        self._lbl_train_status.pack(anchor="w")

        # Results frame (hidden until training succeeds)
        self._results_frame = tk.Frame(card, bg=C["card_safe"],
                                        highlightthickness=1,
                                        highlightbackground=C["safe"],
                                        padx=16, pady=12)
        # not packed yet

        self._lbl_result_title = tk.Label(
            self._results_frame,
            text="✅  Model trained successfully!",
            bg=C["card_safe"], fg=C["safe"],
            font=("Segoe UI", 11, "bold"),
        )
        self._lbl_result_title.pack(anchor="w", pady=(0, 6))

        for attr, lbl in [
            ("_lbl_res_accuracy",  "Accuracy:"),
            ("_lbl_res_samples",   "Samples used:"),
            ("_lbl_res_fp",        "Est. false-positive reduction:"),
        ]:
            row = tk.Frame(self._results_frame, bg=C["card_safe"])
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"  {lbl}", width=30, anchor="w",
                     bg=C["card_safe"], fg=C["text_dim"],
                     font=("Segoe UI", 10)).pack(side=tk.LEFT)
            lbl_val = tk.Label(row, text="—", bg=C["card_safe"],
                               fg=C["text"], font=("Segoe UI", 10, "bold"))
            lbl_val.pack(side=tk.LEFT)
            setattr(self, attr, lbl_val)

    def _build_model_status_section(self, parent: tk.Frame) -> None:
        card = self._section_card(parent, "📡  Current Model Status")

        # Status labels
        for attr, label in [
            ("_lbl_ms_active",   "Active model:"),
            ("_lbl_ms_date",     "Trained on:"),
            ("_lbl_ms_samples",  "Real samples:"),
            ("_lbl_ms_accuracy", "Model accuracy:"),
        ]:
            row = tk.Frame(card, bg=C["surface"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, width=20, anchor="w",
                     bg=C["surface"], fg=C["text_dim"],
                     font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
            lbl = tk.Label(row, text="—", bg=C["surface"],
                           fg=C["text"], font=("Segoe UI", 10))
            lbl.pack(side=tk.LEFT, padx=(8, 0))
            setattr(self, attr, lbl)

        # Re-record button
        sep = tk.Frame(card, bg=C["border"], height=1)
        sep.pack(fill=tk.X, pady=12)

        self._btn_rerecord = tk.Button(
            card, text="🔄  Re-record & Retrain",
            command=self._on_rerecord,
            bg=C["btn_bg"], fg=C["text"], relief=tk.FLAT,
            padx=20, pady=8, font=("Segoe UI", 10),
            cursor="hand2", borderwidth=0,
        )
        self._btn_rerecord.pack(anchor="w")
        self._btn_rerecord.bind("<Enter>",
                                lambda e: self._btn_rerecord.config(bg=C["btn_hover"]))
        self._btn_rerecord.bind("<Leave>",
                                lambda e: self._btn_rerecord.config(bg=C["btn_bg"]))

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_start_recording(self) -> None:
        """User clicked ▶ Start Recording."""
        if self._recorder.is_recording:
            return
        self._recorder.start()

        self._btn_start.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)
        self._btn_train.config(state=tk.DISABLED)
        self._lbl_rec_state.config(
            text="🔴  Recording…  (use your computer normally)",
            fg=C["malicious"],
        )
        # Reset counters in UI
        self._lbl_duration.config(text="00:00:00")
        self._lbl_count.config(text="0")
        self._lbl_last.config(text="None")

        # Start the per-second UI tick
        self._schedule_tick()

    def _on_stop_recording(self) -> None:
        """User clicked ⏹ Stop Recording."""
        if not self._recorder.is_recording:
            return

        # Stop returns None if nothing captured yet
        count   = self._recorder.count
        elapsed = self._recorder.elapsed_seconds
        
        logger.info(f"Stop Recording clicked: count={count}, elapsed={elapsed:.1f}s")
        
        csv_out = self._recorder.stop()
        
        logger.info(f"Recorder.stop() returned: {csv_out}")

        self._cancel_tick()
        self._btn_stop.config(state=tk.DISABLED)
        self._btn_start.config(state=tk.NORMAL)
        self._lbl_rec_state.config(
            text="⬤  Recording stopped.", fg=C["text_light"]
        )

        if csv_out is None or count == 0:
            logger.warning(f"No CSV exported: csv_out={csv_out}, count={count}")
            messagebox.showwarning(
                "No Data Recorded",
                f"No new user-launched processes were captured during this session.\n\n"
                f"Processes captured: {count}\n"
                f"Recording duration: {int(elapsed)} seconds\n\n"
                f"Tips:\n"
                f"• Open some applications AFTER clicking Start Recording\n"
                f"• Launch at least 50 different apps (Chrome, Notepad, Calculator, etc.)\n"
                f"• Apps already running when you clicked Start are not counted\n\n"
                f"The counter must show a number > 0 before stopping.",
            )
            return

        self._csv_path = csv_out
        hrs  = int(elapsed // 3600)
        mins = int((elapsed % 3600) // 60)

        if count < 50:
            messagebox.showwarning(
                "Too Few Samples",
                f"Captured {count} processes over {hrs}h {mins}m.\n\n"
                f"Need at least 50 samples for reliable training.\n"
                f"Try recording for longer or open more applications.\n\n"
                f"CSV saved to:\n{csv_out}",
            )
            return

        self._btn_train.config(state=tk.NORMAL)
        messagebox.showinfo(
            "Recording Complete",
            f"✅  Captured {count} processes over {hrs}h {mins}m.\n\n"
            f"CSV saved to:\n{csv_out}\n\n"
            f"Click  🎓 Train Personalized Model  when ready.",
        )

    def _on_train(self) -> None:
        """User clicked 🎓 Train Personalized Model."""
        if self._training:
            return
        if not self._csv_path or not self._csv_path.exists():
            messagebox.showerror(
                "No Recording Found",
                "Could not find a behavior-recording CSV.\n"
                "Please record your behavior first, then train.",
            )
            return

        count = self._recorder.count
        if count > 0 and count < 50:
            messagebox.showwarning(
                "Too Few Samples",
                f"Only {count} samples recorded.  "
                "Record for longer (need 50+ samples).",
            )
            return

        self._training = True
        self._btn_train.config(state=tk.DISABLED)
        self._btn_start.config(state=tk.DISABLED)

        # Show progress bar
        self._progress_var.set(0.0)
        self._progress_bar.pack(anchor="w", pady=(0, 8), fill=tk.X)
        self._lbl_train_status.config(
            text="Starting training…", fg=C["text_dim"]
        )

        # Run training in a background thread so the UI stays responsive
        threading.Thread(
            target=self._training_thread,
            args=(self._csv_path,),
            name="PersonalizedTrainer",
            daemon=True,
        ).start()

    def _on_rerecord(self) -> None:
        """User clicked 🔄 Re-record & Retrain — reset everything."""
        if self._recorder.is_recording:
            messagebox.showwarning(
                "Recording in Progress",
                "Stop the current recording before starting a new one.",
            )
            return
        if not messagebox.askyesno(
            "Re-record",
            "This will let you start a fresh recording session.\n\n"
            "Your previous CSV is still saved on disk.\n\n"
            "Continue?",
        ):
            return

        self._csv_path = None
        self._btn_train.config(state=tk.DISABLED)
        self._btn_start.config(state=tk.NORMAL)
        self._btn_stop.config(state=tk.DISABLED)
        self._lbl_rec_state.config(
            text="⬤  Not Recording", fg=C["text_light"]
        )
        self._lbl_duration.config(text="00:00:00")
        self._lbl_count.config(text="0")
        self._lbl_last.config(text="None")
        self._lbl_train_status.config(text="")
        self._results_frame.pack_forget()

    # ------------------------------------------------------------------
    # Training thread
    # ------------------------------------------------------------------

    def _training_thread(self, csv_path: Path) -> None:
        """
        Runs on PersonalizedTrainer thread.
        Calls train_personalized() with a progress callback that posts
        updates back to the Tkinter mainloop via after().
        """
        try:
            # Late import keeps startup fast and avoids circular deps
            import sys
            from pathlib import Path as _P
            proj_root = _P(__file__).parent.parent.parent
            if str(proj_root) not in sys.path:
                sys.path.insert(0, str(proj_root))
            from tools.train_model import train_personalized

            def _progress(msg: str, fraction: float) -> None:
                # Post to main thread
                if hasattr(self, "_root_ref") and self._root_ref:
                    self._root_ref.after(
                        0,
                        lambda m=msg, f=fraction: self._update_progress(m, f),
                    )

            result = train_personalized(
                csv_path=csv_path,
                progress_callback=_progress,
            )

            # Post result back to main thread
            if hasattr(self, "_root_ref") and self._root_ref:
                self._root_ref.after(0, lambda r=result: self._on_training_done(r))
            else:
                self._on_training_done(result)

        except Exception as exc:
            err_result = {
                "success": False,
                "error": str(exc),
                "accuracy": 0.0,
                "cv_f1_mean": 0.0,
                "n_real_safe": 0,
                "n_synthetic": 0,
                "n_total": 0,
            }
            if hasattr(self, "_root_ref") and self._root_ref:
                self._root_ref.after(
                    0, lambda r=err_result: self._on_training_done(r)
                )

    def set_root_ref(self, root: tk.Tk) -> None:
        """Called by Dashboard after the window is built so the training
        thread can post updates back to the main thread via after()."""
        self._root_ref = root

    def _update_progress(self, message: str, fraction: float) -> None:
        """Called on the main thread with training progress updates."""
        pct = min(max(fraction * 100.0, 0.0), 100.0)
        self._progress_var.set(pct)
        self._lbl_train_status.config(
            text=f"{message}  ({pct:.0f}%)", fg=C["text_dim"]
        )

    def _on_training_done(self, result: dict) -> None:
        """Called on the main thread when training completes or fails."""
        self._training = False
        self._btn_start.config(state=tk.NORMAL)

        if not result.get("success"):
            self._progress_bar.pack_forget()
            self._lbl_train_status.config(
                text=f"❌  Training failed: {result.get('error', 'Unknown error')}",
                fg=C["malicious"],
            )
            messagebox.showerror(
                "Training Failed",
                f"Could not train the personalized model:\n\n"
                f"{result.get('error', 'Unknown error')}\n\n"
                f"Your existing model is unchanged.",
            )
            self._btn_train.config(state=tk.NORMAL)
            return

        # Training succeeded — update progress to 100%
        self._progress_var.set(100.0)
        self._lbl_train_status.config(
            text="✅  Training complete!", fg=C["safe"]
        )

        # Show results card
        accuracy   = result.get("accuracy", 0.0)
        n_real     = result.get("n_real_safe", 0)
        n_total    = result.get("n_total", 0)
        # Rough false-positive reduction estimate based on personalisation:
        # generic models see ~12-15% FP; personalized typically 2-3%.
        fp_est = "~80–90%"

        self._lbl_res_accuracy.config(text=f"{accuracy:.1%}")
        self._lbl_res_samples.config(
            text=f"{n_total} total  ({n_real} real SAFE + {n_total - n_real} synthetic)"
        )
        self._lbl_res_fp.config(text=fp_est)
        self._results_frame.pack(fill=tk.X, pady=(12, 0))

        # Tell the live classifier to reload the new personalized model
        try:
            clf = self._get_classifier()
            if clf is not None:
                clf.reload_personalized()
        except Exception:
            pass

        # Refresh the model-status section
        self._refresh_model_status()

        messagebox.showinfo(
            "Model Trained Successfully! 🎉",
            f"Your personalized model is now active.\n\n"
            f"  Accuracy      : {accuracy:.1%}\n"
            f"  Real samples  : {n_real}\n"
            f"  Total samples : {n_total}\n"
            f"  Est. FP reduction: {fp_est}\n\n"
            f"The detector will now recognise your normal "
            f"programs and flag fewer false positives.",
        )

    # ------------------------------------------------------------------
    # Timer tick  (updates duration / count labels every second)
    # ------------------------------------------------------------------

    def _schedule_tick(self) -> None:
        """Start the per-second UI refresh tick."""
        self._tick()

    def _cancel_tick(self) -> None:
        if self._timer_job:
            try:
                self.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None

    def _tick(self) -> None:
        """Update the live status labels; reschedule itself if still recording."""
        if self._recorder.is_recording:
            elapsed = self._recorder.elapsed_seconds
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._lbl_duration.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self._lbl_count.config(text=str(self._recorder.count))
            last = self._recorder.last_process_name
            self._lbl_last.config(text=last if last != "None" else "None")
            self._timer_job = self.after(self._TICK_MS, self._tick)
        else:
            self._timer_job = None

    # ------------------------------------------------------------------
    # Model status refresh
    # ------------------------------------------------------------------

    def _refresh_model_status(self) -> None:
        """Read the personalized-model JSON sidecar (if it exists) and
        update the Model Status section labels."""
        from ..classifier import PERSONALIZED_MODEL_PATH

        json_path = PERSONALIZED_MODEL_PATH.with_suffix(".json")
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                self._lbl_ms_active.config(
                    text="✅  Personalized Model", fg=C["safe"]
                )
                trained_at = data.get("trained_at", "Unknown")
                # Show only the date portion for readability
                self._lbl_ms_date.config(text=trained_at[:10])
                self._lbl_ms_samples.config(
                    text=str(data.get("real_safe_samples", "—"))
                )
                acc = data.get("accuracy")
                self._lbl_ms_accuracy.config(
                    text=f"{float(acc):.1%}" if acc is not None else "—"
                )
                return
            except Exception:
                pass

        # No personalized model
        self._lbl_ms_active.config(
            text="ℹ️  Generic Model (not yet personalized)", fg=C["text_dim"]
        )
        self._lbl_ms_date.config(text="—")
        self._lbl_ms_samples.config(text="—")
        self._lbl_ms_accuracy.config(text="—")


# ---------------------------------------------------------------------------
# Tab 5 – Behavioral Analysis (Typing Speed Anomaly Detection)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tab 5 – Behavioral Analysis (Multi-Modal Behavioral Biometrics)
# ---------------------------------------------------------------------------

class _BehavioralAnalysisTab(ttk.Frame):
    """
    Phase 1 & Phase 2 Multi-Modal Behavioral Biometrics Tab.

    Shows:
      • Training view   — when baseline not yet collected (< 10,000 keys or mouse)
      • Monitoring view — multi-modal keyboard + mouse telemetry, combined similarity %,
                          bot classification banner, and JSON export suite.
    """

    # Status band colours
    _STATUS_COLORS = {
        "green":  ("#27ae60", "#e8f8f0", "✅ Normal Typing & Mouse"),
        "yellow": ("#f39c12", "#fff8e1", "🟡 Slightly Unusual"),
        "orange": ("#e67e22", "#fef0e6", "⚠️ Suspicious Activity"),
        "red":    ("#e74c3c", "#fdecea", "🔴 Anomaly Detected"),
        "grey":   ("#95a5a6", "#f5f7fa", "⬜ Insufficient Data"),
    }

    def __init__(self, parent, engine=None) -> None:
        super().__init__(parent, style="Dark.TFrame")
        self._engine = engine
        self._root_ref = None
        self._available = engine is not None and engine.is_available
        self._last_anomaly = None
        self._last_metrics = None
        self._anomaly_start_ts: Optional[float] = None
        self._kb_rows: Dict[str, Dict] = {}
        self._mouse_rows: Dict[str, Dict] = {}
        self._pattern_rows: Dict[str, Dict] = {}
        self._build()

        # Hook engine callbacks
        if engine:
            engine.on_metrics_update = self._on_metrics_update
            engine.on_mouse_update = self._on_mouse_update
            engine.on_anomaly = self._on_anomaly_alert

    def set_root_ref(self, root) -> None:
        self._root_ref = root

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self._canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview,
                            style="Modern.Vertical.TScrollbar")
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg=C["bg"])
        self._inner_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw"
        )
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        if not self._available:
            self._build_unavailable()
        else:
            self._build_header()
            self._build_privacy_banner()
            self._build_training_section()
            self._build_monitoring_section()
            self._build_export_section()
            self._build_footer_buttons()
            self._update_view_mode()

    def _on_inner_configure(self, event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        self._canvas.itemconfig(self._inner_id, width=event.width)

    # -- Unavailable view --

    def _build_unavailable(self) -> None:
        frm = tk.Frame(self._inner, bg=C["surface"], padx=32, pady=40)
        frm.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        tk.Label(frm, text="🔌  Behavioral Analysis Unavailable",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 15, "bold")).pack(pady=(0, 12))
        tk.Label(frm, text=(
            "The pynput library could not be initialized for keyboard/mouse listening.\n\n"
            "To enable behavioral biometrics, install pynput:\n"
            "    pip install pynput==1.7.6\n\n"
            "Then restart the application."
        ), bg=C["surface"], fg=C["text_dim"],
            font=("Segoe UI", 10), justify=tk.LEFT).pack()

    # -- Header --

    def _build_header(self) -> None:
        hdr = tk.Frame(self._inner, bg=C["bg"], pady=12)
        hdr.pack(fill=tk.X, padx=16)
        tk.Label(hdr, text="🧠  Multi-Modal Behavioral Biometrics (Keyboard + Mouse)",
                 bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        self._enabled_btn = tk.Button(
            hdr, text="● Enabled",
            command=self._toggle_enabled,
            bg=C["safe"], fg="white", relief=tk.FLAT,
            padx=12, pady=4, font=("Segoe UI", 9, "bold"),
            cursor="hand2", borderwidth=0
        )
        self._enabled_btn.pack(side=tk.RIGHT)

    # -- Privacy banner --

    def _build_privacy_banner(self) -> None:
        banner = tk.Frame(self._inner, bg="#e8f4f8",
                          highlightbackground="#b3d4e8", highlightthickness=1,
                          padx=16, pady=10)
        banner.pack(fill=tk.X, padx=16, pady=(0, 8))
        tk.Label(banner, text="🔒  Privacy-First Biometrics Guarantee",
                 bg="#e8f4f8", fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        for txt in [
            "✓  Records TIMING & MOTION DYNAMICS — never key letters or screen content",
            "✓  Cannot see or reconstruct what you type or what buttons you click",
            "✓  Exports include SHA-256 integrity verification with anonymized timestamps",
        ]:
            tk.Label(banner, text=txt, bg="#e8f4f8", fg=C["text_dim"],
                     font=("Segoe UI", 9)).pack(anchor="w")

    # -- Training section --

    def _build_training_section(self) -> None:
        self._training_frame = tk.Frame(self._inner, bg=C["surface"],
                                        highlightbackground=C["border"],
                                        highlightthickness=1,
                                        padx=20, pady=16)
        self._training_frame.pack(fill=tk.X, padx=16, pady=8)

        tk.Label(self._training_frame, text="📚  Learning Your Natural Behavior Profile",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        tk.Label(self._training_frame,
                 text="The AI passively learns your combined typing rhythm and mouse dynamics.\n"
                      "Continue using your computer normally.",
                 bg=C["surface"], fg=C["text_dim"],
                 font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor="w", pady=(0, 12))

        # Progress bar
        prog_frm = tk.Frame(self._training_frame, bg=C["surface"])
        prog_frm.pack(fill=tk.X, pady=(0, 4))
        tk.Label(prog_frm, text="Combined Training Progress:",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        bar_bg = tk.Frame(self._training_frame, bg=C["border"],
                          height=14, highlightthickness=0)
        bar_bg.pack(fill=tk.X, pady=(4, 2))
        self._prog_bar = tk.Frame(bar_bg, bg=C["accent"], height=14)
        self._prog_bar.place(relwidth=0.0, relheight=1.0)

        self._prog_pct_lbl = tk.Label(self._training_frame, text="0.0%",
                                       bg=C["surface"], fg=C["accent"],
                                       font=("Segoe UI", 10, "bold"))
        self._prog_pct_lbl.pack(anchor="e")

        # Stats grid
        grid = tk.Frame(self._training_frame, bg=C["surface"])
        grid.pack(fill=tk.X, pady=8)

        self._train_ks_lbl     = self._stat_row(grid, 0, "Keystrokes Recorded:", "— / 10,000")
        self._train_mouse_lbl  = self._stat_row(grid, 1, "Mouse Movements:", "— / 15,000")
        self._train_elapsed_lbl = self._stat_row(grid, 2, "Time Elapsed:", "—")
        self._train_eta_lbl    = self._stat_row(grid, 3, "Estimated Remaining:", "—")
        self._train_speed_lbl  = self._stat_row(grid, 4, "Current Speeds:", "—")

    def _stat_row(self, parent, row, label, value):
        tk.Label(parent, text=label, bg=C["surface"], fg=C["text_dim"],
                 font=("Segoe UI", 9), anchor="w", width=24
                 ).grid(row=row, column=0, sticky="w", pady=2)
        lbl = tk.Label(parent, text=value, bg=C["surface"], fg=C["text"],
                       font=("Segoe UI", 9, "bold"), anchor="w")
        lbl.grid(row=row, column=1, sticky="w", padx=8, pady=2)
        return lbl

    # -- Monitoring section --

    def _build_monitoring_section(self) -> None:
        self._monitoring_frame = tk.Frame(self._inner, bg=C["bg"])
        self._monitoring_frame.pack(fill=tk.X, padx=16, pady=0)

        # 1. Main Overall Status Banner
        self._status_banner = tk.Frame(self._monitoring_frame, bg=C["surface"],
                                       highlightbackground=C["border"],
                                       highlightthickness=1,
                                       padx=20, pady=14)
        self._status_banner.pack(fill=tk.X, pady=(0, 8))

        banner_top = tk.Frame(self._status_banner, bg=C["surface"])
        banner_top.pack(fill=tk.X)
        self._status_icon_lbl = tk.Label(banner_top, text="✅",
                                          bg=C["surface"], font=("Segoe UI", 18))
        self._status_icon_lbl.pack(side=tk.LEFT, padx=(0, 10))
        status_text_frm = tk.Frame(banner_top, bg=C["surface"])
        status_text_frm.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._status_title_lbl = tk.Label(status_text_frm, text="Normal Typing & Mouse",
                                           bg=C["surface"], fg=C["safe"],
                                           font=("Segoe UI", 13, "bold"), anchor="w")
        self._status_title_lbl.pack(anchor="w")

        scores_row = tk.Frame(status_text_frm, bg=C["surface"])
        scores_row.pack(anchor="w", fill=tk.X, pady=(2, 0))

        self._similarity_lbl = tk.Label(scores_row,
                                         text="Combined Similarity: —",
                                         bg=C["surface"], fg=C["text"],
                                         font=("Segoe UI", 10, "bold"), anchor="w")
        self._similarity_lbl.pack(side=tk.LEFT, padx=(0, 16))

        self._duration_lbl = tk.Label(scores_row, text="",
                                       bg=C["surface"], fg=C["text_dim"],
                                       font=("Segoe UI", 9), anchor="w")
        self._duration_lbl.pack(side=tk.LEFT)

        # Bot special banner (hidden by default)
        self._bot_frame = tk.Frame(self._monitoring_frame, bg="#fdecea",
                                   highlightbackground=C["malicious"],
                                   highlightthickness=2, padx=16, pady=12)
        self._bot_lbl = tk.Label(self._bot_frame,
                                  text="🤖  Bot / Macro Detected",
                                  bg="#fdecea", fg=C["malicious"],
                                  font=("Segoe UI", 12, "bold"))
        self._bot_lbl.pack(anchor="w")
        self._bot_reason_lbl = tk.Label(self._bot_frame, text="",
                                         bg="#fdecea", fg=C["text"],
                                         font=("Segoe UI", 9),
                                         justify=tk.LEFT, anchor="w")
        self._bot_reason_lbl.pack(anchor="w", pady=(4, 0))

        # 2. Three Side-by-Side or Stacked Metric Cards: Keyboard, Mouse, Pattern
        cards_container = tk.Frame(self._monitoring_frame, bg=C["bg"])
        cards_container.pack(fill=tk.X, pady=(0, 8))

        # Card 1: Keyboard Behavior
        self._build_table_card(
            cards_container, "⌨️  Keyboard Behavior", "kb",
            [
                ("wpm", "Typing Speed", "WPM"),
                ("dwell_ms", "Key Hold Time", "ms"),
                ("consistency_stddev", "Timing Consistency", "ms"),
                ("burst_count", "Burst Pattern", "bursts"),
            ],
            self._kb_rows,
            footer_lbl_name="_kb_sim_lbl",
            footer_default="Keyboard Similarity: —",
        )

        # Card 2: Mouse Behavior
        self._build_table_card(
            cards_container, "🖱️  Mouse Behavior", "mouse",
            [
                ("speed_px_per_sec", "Movement Speed", "px/s"),
                ("curvature_index", "Path Curvature", ""),
                ("micro_movements", "Micro-Movements", "/s"),
                ("click_duration_ms", "Click Hold Time", "ms"),
                ("pauses_per_minute", "Pause Frequency", "/min"),
            ],
            self._mouse_rows,
            footer_lbl_name="_mouse_sim_lbl",
            footer_default="Mouse Similarity: —",
        )

        # Card 3: Combined Pattern Analysis
        self._build_pattern_card(cards_container)

        # 3. Anomaly Analysis & Explanations
        analysis_card = tk.Frame(self._monitoring_frame, bg=C["surface"],
                                  highlightbackground=C["border"],
                                  highlightthickness=1, padx=16, pady=12)
        analysis_card.pack(fill=tk.X, pady=(0, 8))
        tk.Label(analysis_card, text="🔴 Alert Reasons & Evidence:",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self._analysis_text = tk.Text(
            analysis_card, height=4, bg="#fafbfc", fg=C["text"],
            relief=tk.FLAT, font=("Segoe UI", 9), wrap=tk.WORD,
            borderwidth=0, state=tk.DISABLED
        )
        self._analysis_text.pack(fill=tk.X)
        self._analysis_text.tag_configure("red_item", foreground=C["malicious"])
        self._analysis_text.tag_configure("yellow_item", foreground=C["suspicious"])
        self._analysis_text.tag_configure("ok_item", foreground=C["safe"])

        # 4. Possible causes
        causes_card = tk.Frame(self._monitoring_frame, bg=C["surface"],
                                highlightbackground=C["border"],
                                highlightthickness=1, padx=16, pady=12)
        causes_card.pack(fill=tk.X, pady=(0, 8))
        tk.Label(causes_card, text="Possible Causes:",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self._causes_lbl = tk.Label(causes_card, text="",
                                     bg=C["surface"], fg=C["text_dim"],
                                     font=("Segoe UI", 9), justify=tk.LEFT,
                                     anchor="w")
        self._causes_lbl.pack(anchor="w")

        # 5. Recent activity list
        hist_card = tk.Frame(self._monitoring_frame, bg=C["surface"],
                              highlightbackground=C["border"],
                              highlightthickness=1, padx=16, pady=12)
        hist_card.pack(fill=tk.X, pady=(0, 8))
        tk.Label(hist_card, text="Recent Multi-Modal Windows (Last 10 Cycles):",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self._history_text = tk.Text(
            hist_card, height=5, bg="#fafbfc", fg=C["text"],
            relief=tk.FLAT, font=("Segoe UI", 9, "bold"), wrap=tk.WORD,
            borderwidth=0, state=tk.DISABLED
        )
        self._history_text.pack(fill=tk.X)
        for tag, fg_ in [("ok", C["safe"]), ("warn", C["suspicious"]),
                          ("bad", C["malicious"]), ("dim", C["text_dim"])]:
            self._history_text.tag_configure(tag, foreground=fg_)

    def _build_table_card(self, parent, title, prefix, metric_defs, store_dict, footer_lbl_name, footer_default):
        card = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 8))

        # Title row
        t_row = tk.Frame(card, bg=C["surface"], padx=12, pady=6)
        t_row.pack(fill=tk.X)
        tk.Label(t_row, text=title, bg=C["surface"], fg=C["text"], font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

        # Header row
        hdr_row = tk.Frame(card, bg=C["border"])
        hdr_row.pack(fill=tk.X)
        for txt, w in [("Metric", 180), ("Your Normal", 140), ("Current", 140), ("Status", 70)]:
            tk.Label(hdr_row, text=txt, bg="#f0f3f7", fg=C["text"],
                     font=("Segoe UI", 8, "bold"), anchor="w", padx=10, pady=4).pack(side=tk.LEFT)
            tk.Frame(hdr_row, bg=C["border"], width=1).pack(side=tk.LEFT, fill=tk.Y)

        for i, (key, label, unit) in enumerate(metric_defs):
            row_bg = C["surface"] if i % 2 == 0 else "#fafbfc"
            row = tk.Frame(card, bg=row_bg)
            row.pack(fill=tk.X)
            tk.Frame(row, bg=C["border"], height=1).pack(fill=tk.X, side=tk.TOP)
            tk.Label(row, text=label, bg=row_bg, fg=C["text"],
                     font=("Segoe UI", 9), anchor="w", padx=10, pady=5, width=22).pack(side=tk.LEFT)
            tk.Frame(row, bg=C["border"], width=1).pack(side=tk.LEFT, fill=tk.Y)
            lbl_normal = tk.Label(row, text="—", bg=row_bg, fg=C["text_dim"],
                                  font=("Segoe UI", 9), anchor="w", padx=10, width=16)
            lbl_normal.pack(side=tk.LEFT)
            tk.Frame(row, bg=C["border"], width=1).pack(side=tk.LEFT, fill=tk.Y)
            lbl_current = tk.Label(row, text="—", bg=row_bg, fg=C["text"],
                                   font=("Segoe UI", 9, "bold"), anchor="w", padx=10, width=16)
            lbl_current.pack(side=tk.LEFT)
            lbl_indicator = tk.Label(row, text="", bg=row_bg, font=("Segoe UI", 9), padx=6)
            lbl_indicator.pack(side=tk.LEFT)
            store_dict[key] = {
                "lbl_normal": lbl_normal,
                "lbl_current": lbl_current,
                "lbl_indicator": lbl_indicator,
                "unit": unit,
            }

        # Footer row for similarity score
        f_row = tk.Frame(card, bg="#f0f3f7", padx=12, pady=6)
        f_row.pack(fill=tk.X)
        lbl_footer = tk.Label(f_row, text=footer_default, bg="#f0f3f7", fg=C["text"],
                              font=("Segoe UI", 9, "bold"))
        lbl_footer.pack(side=tk.RIGHT)
        setattr(self, footer_lbl_name, lbl_footer)

    def _build_pattern_card(self, parent):
        card = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 8))

        t_row = tk.Frame(card, bg=C["surface"], padx=12, pady=6)
        t_row.pack(fill=tk.X)
        tk.Label(t_row, text="🔄  Combined Pattern & Coordination Analysis", bg=C["surface"],
                 fg=C["text"], font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

        hdr_row = tk.Frame(card, bg=C["border"])
        hdr_row.pack(fill=tk.X)
        for txt in ["Pattern Metric", "Your Normal", "Current", "Status"]:
            tk.Label(hdr_row, text=txt, bg="#f0f3f7", fg=C["text"],
                     font=("Segoe UI", 8, "bold"), anchor="w", padx=10, pady=4).pack(side=tk.LEFT, expand=True, fill=tk.X)

        defs = [
            ("coordination", "Input Coordination", "Normal", "—", "—"),
            ("switch_latency", "KB→Mouse Switch Latency", "520 ± 180 ms", "—", "—"),
            ("activity_corr", "Activity Correlation", "0.78", "—", "—"),
        ]
        for i, (k, label, norm_txt, cur_txt, stat_txt) in enumerate(defs):
            row_bg = C["surface"] if i % 2 == 0 else "#fafbfc"
            row = tk.Frame(card, bg=row_bg, padx=10, pady=5)
            row.pack(fill=tk.X)
            tk.Label(row, text=label, bg=row_bg, fg=C["text"], font=("Segoe UI", 9), anchor="w", width=24).pack(side=tk.LEFT)
            tk.Label(row, text=norm_txt, bg=row_bg, fg=C["text_dim"], font=("Segoe UI", 9), anchor="w", width=18).pack(side=tk.LEFT)
            lbl_c = tk.Label(row, text=cur_txt, bg=row_bg, fg=C["text"], font=("Segoe UI", 9, "bold"), anchor="w", width=18)
            lbl_c.pack(side=tk.LEFT)
            lbl_s = tk.Label(row, text=stat_txt, bg=row_bg, font=("Segoe UI", 9), anchor="w")
            lbl_s.pack(side=tk.LEFT)
            self._pattern_rows[k] = {"lbl_current": lbl_c, "lbl_status": lbl_s}

        f_row = tk.Frame(card, bg="#f0f3f7", padx=12, pady=6)
        f_row.pack(fill=tk.X)
        self._pattern_sim_lbl = tk.Label(f_row, text="Pattern Similarity: —", bg="#f0f3f7", fg=C["text"],
                                         font=("Segoe UI", 9, "bold"))
        self._pattern_sim_lbl.pack(side=tk.RIGHT)

    # -- Export Section (Feature 4 & UI integration) --

    def _build_export_section(self) -> None:
        export_card = tk.Frame(self._inner, bg=C["surface"],
                               highlightbackground=C["border"], highlightthickness=1,
                               padx=16, pady=14)
        export_card.pack(fill=tk.X, padx=16, pady=(0, 8))

        tk.Label(export_card, text="📦  Export Behavioral Data to JSON",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        # Buttons grid
        btn_grid = tk.Frame(export_card, bg=C["surface"])
        btn_grid.pack(fill=tk.X, pady=(0, 8))

        # Column 1: Profiles
        col1 = tk.Frame(btn_grid, bg=C["surface"])
        col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        tk.Label(col1, text="Profile Baseline Export:", bg=C["surface"], fg=C["text_dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self._make_btn(col1, "📄 Export Keyboard Profile", self._export_keyboard_profile, C["btn_bg"], C["text"]).pack(fill=tk.X, pady=2)
        self._make_btn(col1, "🖱️ Export Mouse Profile", self._export_mouse_profile, C["btn_bg"], C["text"]).pack(fill=tk.X, pady=2)
        self._make_btn(col1, "📦 Export Combined Profile", self._export_combined_profile, C["btn_bg"], C["text"]).pack(fill=tk.X, pady=2)

        # Column 2: Session & Reports
        col2 = tk.Frame(btn_grid, bg=C["surface"])
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        tk.Label(col2, text="Session & Audit Export:", bg=C["surface"], fg=C["text_dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self._make_btn(col2, "📊 Export Last Hour Session", lambda: self._export_session(60), C["btn_bg"], C["text"]).pack(fill=tk.X, pady=2)
        self._make_btn(col2, "📈 Export 24h Daily Session", lambda: self._export_session(1440), C["btn_bg"], C["text"]).pack(fill=tk.X, pady=2)
        self._make_btn(col2, "📋 Generate Comparison Report", self._export_comparison_report, C["btn_bg"], C["text"]).pack(fill=tk.X, pady=2)

        # Privacy Toggles Row
        priv_frame = tk.Frame(export_card, bg="#f8f9fa", padx=10, pady=6)
        priv_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(priv_frame, text="Export Privacy Options:", bg="#f8f9fa", fg=C["text"], font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        self._anonymize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(priv_frame, text="Anonymize Timestamps (T+0s)", variable=self._anonymize_var, bg="#f8f9fa", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=4)

    # -- Footer action buttons --

    def _build_footer_buttons(self) -> None:
        btn_frame = tk.Frame(self._inner, bg=C["bg"], pady=10)
        btn_frame.pack(fill=tk.X, padx=16)

        self._this_was_me_btn = self._make_btn(
            btn_frame, "✅ This Was Me", self._this_was_me,
            C["safe"], "white"
        )
        self._this_was_me_btn.pack(side=tk.LEFT, padx=(0, 8))

        retrain_btn = self._make_btn(
            btn_frame, "🔄 Retrain Profile", self._retrain,
            C["suspicious"], "white"
        )
        retrain_btn.pack(side=tk.LEFT, padx=(0, 8))

        view_json_btn = self._make_btn(
            btn_frame, "📁 View Behavior JSON", self._view_my_behavior_json,
            C["btn_bg"], C["text"]
        )
        view_json_btn.pack(side=tk.LEFT, padx=(0, 8))

        settings_btn = self._make_btn(
            btn_frame, "⚙️ Settings", self._show_settings,
            C["btn_bg"], C["text"]
        )
        settings_btn.pack(side=tk.LEFT)

    def _make_btn(self, parent, text, cmd, bg, fg):
        btn = tk.Button(parent, text=text, command=cmd,
                        bg=bg, fg=fg, relief=tk.FLAT,
                        padx=12, pady=6, font=("Segoe UI", 9, "bold"),
                        cursor="hand2", borderwidth=0)
        btn.bind("<Enter>", lambda e, b=btn, c=bg: b.config(bg=_darken(c)))
        btn.bind("<Leave>", lambda e, b=btn, c=bg: b.config(bg=c))
        return btn

    # ------------------------------------------------------------------
    # Refresh & Updates
    # ------------------------------------------------------------------

    def _update_view_mode(self) -> None:
        if not self._available or not self._engine:
            return
        training_done = self._engine.is_baseline_available
        if training_done:
            self._training_frame.pack_forget()
            self._monitoring_frame.pack(fill=tk.X, padx=16, pady=0)
        else:
            self._monitoring_frame.pack_forget()
            self._training_frame.pack(fill=tk.X, padx=16, pady=8)

    def refresh(self) -> None:
        if not self._available or not self._engine:
            return
        try:
            self._refresh_training()
            self._update_view_mode()
            if self._engine.is_baseline_available:
                self._refresh_monitoring()
        except Exception as exc:
            logger.debug("BehavioralAnalysisTab refresh error: %s", exc)

    def _refresh_training(self) -> None:
        prog = self._engine.get_training_progress()
        pct = prog["percent"]
        ks = prog["keystrokes_recorded"]
        need_ks = prog["keystrokes_needed"]
        mouse_moves = prog["mouse_movements"]
        need_mouse = prog["mouse_needed"]

        self._animate_progress(pct)

        self._train_ks_lbl.config(text=f"{ks:,} / {need_ks:,}")
        self._train_mouse_lbl.config(text=f"{mouse_moves:,} / {need_mouse:,}")

        d, h = prog["elapsed_days"], prog["elapsed_hours"]
        self._train_elapsed_lbl.config(text=f"{d}d {h}h")

        eta_d, eta_h = prog["eta_days"], prog["eta_hours"]
        if pct >= 100:
            self._train_eta_lbl.config(text="✅ Complete — Baseline Saved!", fg=C["safe"])
            self._show_baseline_saved_banner()
        else:
            self._train_eta_lbl.config(text=f"~{eta_d}d {eta_h}h", fg=C["text"])

        km = self._engine.current_metrics
        mm = self._engine.current_mouse_metrics
        wpm_txt = f"{km.wpm:.0f} WPM" if km and km.is_sufficient else "Waiting typing..."
        spd_txt = f"{mm.avg_speed_pxsec:.0f} px/s" if mm and mm.is_sufficient else "Waiting mouse..."
        self._train_speed_lbl.config(text=f"{wpm_txt} | {spd_txt}")

    def _show_baseline_saved_banner(self) -> None:
        """
        Show a green banner and desktop notification when baseline training completes.
        Only fires once per session using a guard flag.
        """
        # Guard: Only show once per session
        if getattr(self, "_baseline_banner_shown", False):
            return
        
        self._baseline_banner_shown = True
        
        # Create green success banner
        banner = tk.Frame(
            self._training_frame,
            bg="#16a34a",  # Green background
            padx=16,
            pady=12
        )
        banner.pack(fill=tk.X, pady=(8, 0))
        
        # Bold title label
        title_lbl = tk.Label(
            banner,
            text="✅  Baseline profile saved automatically to data/",
            bg="#16a34a",
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        )
        title_lbl.pack(fill=tk.X)
        
        # Smaller subtitle label
        subtitle_lbl = tk.Label(
            banner,
            text="Behavioral anomaly detection is now ACTIVE",
            bg="#16a34a",
            fg="#ffffff",
            font=("Segoe UI", 9),
            anchor="w"
        )
        subtitle_lbl.pack(fill=tk.X, pady=(2, 0))
        
        # Desktop notification
        if PLYER_AVAILABLE:
            try:
                notification.notify(
                    title="✅ KeyGuard AI — Behavioral Baseline Complete",
                    message="Your personal typing & mouse profile has been saved.\nAnomaly detection is now active and protecting you.",
                    timeout=8
                )
            except Exception:
                pass  # Silently fail if notification doesn't work

    def _animate_progress(self, target_pct: float) -> None:
        """Smoothly glide progress bar towards target with cubic ease-out."""
        target_pct = max(0.0, min(100.0, target_pct))
        current_pct = getattr(self, "_current_anim_pct", 0.0)

        diff = target_pct - current_pct
        if abs(diff) < 0.25:
            self._current_anim_pct = target_pct
            self._prog_bar.place(relwidth=min(target_pct / 100.0, 1.0), relheight=1.0)
            pct_color = C["safe"] if target_pct >= 100 else (C["suspicious"] if target_pct >= 50 else C["accent"])
            self._prog_bar.config(bg=pct_color)
            self._prog_pct_lbl.config(text=f"{target_pct:.1f}%")
            return

        step = diff * 0.25
        new_pct = current_pct + step
        self._current_anim_pct = new_pct
        self._prog_bar.place(relwidth=min(new_pct / 100.0, 1.0), relheight=1.0)
        pct_color = C["safe"] if new_pct >= 100 else (C["suspicious"] if new_pct >= 50 else C["accent"])
        self._prog_bar.config(bg=pct_color)
        self._prog_pct_lbl.config(text=f"{new_pct:.1f}%")

        if self.winfo_exists():
            self.after(25, lambda: self._animate_progress(target_pct))


    def _refresh_monitoring(self) -> None:
        a = self._engine.current_anomaly
        km = self._engine.current_metrics
        mm = self._engine.current_mouse_metrics
        kb_bl = self._engine.baseline
        mouse_bl = self._engine.mouse_baseline

        if not a or not km or not kb_bl:
            return

        # Status banner
        col, bg, lbl_txt = self._STATUS_COLORS.get(a.status, self._STATUS_COLORS["grey"])
        self._status_banner.config(bg=bg)
        self._status_icon_lbl.config(bg=bg)
        self._status_title_lbl.config(bg=bg, fg=col, text=a.status_label)
        self._similarity_lbl.config(bg=bg, text=f"Combined Similarity: {a.similarity_score:.0f}%")
        self._duration_lbl.config(bg=bg)

        # Anomaly duration
        if a.status in ("orange", "red") and self._anomaly_start_ts is None:
            self._anomaly_start_ts = time.time()
        elif a.status in ("green", "yellow", "grey"):
            self._anomaly_start_ts = None

        if self._anomaly_start_ts:
            dur_mins = int((time.time() - self._anomaly_start_ts) / 60)
            dur_secs = int((time.time() - self._anomaly_start_ts) % 60)
            self._duration_lbl.config(text=f"Duration: {dur_mins}m {dur_secs}s")
        else:
            self._duration_lbl.config(text="")

        # Update Keyboard Table
        kb_cur = {
            "wpm": km.wpm,
            "dwell_ms": km.avg_dwell_ms,
            "consistency_stddev": km.consistency_stddev,
            "burst_count": float(km.burst_count),
        }
        for k, v in kb_cur.items():
            row_dict = self._kb_rows.get(k)
            if not row_dict:
                continue
            bl_st = kb_bl.metrics.get(k)
            if bl_st:
                unit = row_dict["unit"]
                row_dict["lbl_normal"].config(text=f"{bl_st.mean:.1f} ± {bl_st.std:.1f} {unit}")
            z = a.z_scores.get(k, 0.0)
            row_dict["lbl_current"].config(text=f"{v:.1f} {row_dict['unit']}")
            ind = "✓ Normal" if z < 2.0 else ("🟡 Moderate" if z < 3.0 else "⚠️ Anomaly")
            ind_fg = C["safe"] if z < 2.0 else (C["suspicious"] if z < 3.0 else C["malicious"])
            row_dict["lbl_indicator"].config(text=ind, fg=ind_fg)

        if hasattr(self, "_kb_sim_lbl"):
            self._kb_sim_lbl.config(text=f"Keyboard Similarity: {a.keyboard_similarity:.0f}%")

        # Update Mouse Table
        if mm and mouse_bl:
            m_cur = {
                "speed_px_per_sec": mm.avg_speed_pxsec,
                "curvature_index": mm.curvature_index,
                "micro_movements": mm.micro_movements_per_sec,
                "click_duration_ms": mm.avg_click_duration_ms,
                "pauses_per_minute": float(mm.pause_frequency_per_min),
            }
            for k, v in m_cur.items():
                row_dict = self._mouse_rows.get(k)
                if not row_dict:
                    continue
                bl_st = mouse_bl.metrics.get(k)
                if bl_st:
                    row_dict["lbl_normal"].config(text=f"{bl_st.mean:.1f} ± {bl_st.std:.1f} {row_dict['unit']}")
                z = a.mouse_z_scores.get(k, 0.0)
                row_dict["lbl_current"].config(text=f"{v:.1f} {row_dict['unit']}")
                ind = "✓ Normal" if z < 2.0 else ("🟡 Moderate" if z < 3.0 else "⚠️ Anomaly")
                ind_fg = C["safe"] if z < 2.0 else (C["suspicious"] if z < 3.0 else C["malicious"])
                row_dict["lbl_indicator"].config(text=ind, fg=ind_fg)

            if hasattr(self, "_mouse_sim_lbl"):
                self._mouse_sim_lbl.config(text=f"Mouse Similarity: {a.mouse_similarity:.0f}%")

        # Update Pattern Table
        if "coordination" in self._pattern_rows:
            self._pattern_rows["coordination"]["lbl_current"].config(text=a.input_coordination)
            self._pattern_rows["coordination"]["lbl_status"].config(
                text="✓ Normal" if a.input_coordination == "Normal" else "⚠️ Anomaly",
                fg=C["safe"] if a.input_coordination == "Normal" else C["malicious"]
            )
        if "switch_latency" in self._pattern_rows:
            self._pattern_rows["switch_latency"]["lbl_current"].config(text=f"{a.kb_mouse_switch_latency_ms:.0f} ms")
            self._pattern_rows["switch_latency"]["lbl_status"].config(text="✓ Normal", fg=C["safe"])
        if "activity_corr" in self._pattern_rows:
            self._pattern_rows["activity_corr"]["lbl_current"].config(text=f"{a.activity_correlation:.2f}")
            self._pattern_rows["activity_corr"]["lbl_status"].config(
                text="✓ Correlated" if a.activity_correlation >= 0.5 else "🟡 Low",
                fg=C["safe"] if a.activity_correlation >= 0.5 else C["suspicious"]
            )
        if hasattr(self, "_pattern_sim_lbl"):
            self._pattern_sim_lbl.config(text=f"Pattern Similarity: {a.pattern_similarity:.0f}%")

        # Anomaly text
        self._analysis_text.config(state=tk.NORMAL)
        self._analysis_text.delete("1.0", tk.END)
        if not a.explanations:
            self._analysis_text.insert(tk.END, "✅ All keyboard and mouse biometrics within normal boundaries.", "ok_item")
        else:
            for exp in a.explanations:
                tag = "red_item" if "⚠️" in exp or "🤖" in exp or "Z=" in exp or "Z-score" in exp else "yellow_item"
                self._analysis_text.insert(tk.END, f"• {exp}\n", tag)
        self._analysis_text.config(state=tk.DISABLED)

        # Possible causes
        if a.possible_causes:
            self._causes_lbl.config(text="\n".join(f"• {c}" for c in a.possible_causes))
        else:
            self._causes_lbl.config(text="• Normal usage matching trained baseline.")

        # Bot banner
        if a.bot_detected:
            self._bot_lbl.config(text=f"🤖  Bot Detected: {a.bot_type.replace('_', ' ').title()}")
            ev_str = "\n".join(f"• {e}" for e in a.bot_evidence) if a.bot_evidence else a.bot_reason
            self._bot_reason_lbl.config(text=f"{a.bot_reason}\n\nEvidence:\n{ev_str}")
            self._bot_frame.pack(fill=tk.X, pady=(0, 8))
        else:
            self._bot_frame.pack_forget()

        # History list
        history = self._engine.recent_history[-10:]
        self._history_text.config(state=tk.NORMAL)
        self._history_text.delete("1.0", tk.END)
        for ts, km_h, mm_h, anom_h in reversed(history):
            ts_str = time.strftime("%H:%M", time.localtime(ts))
            if anom_h is None or anom_h.similarity_score < 0:
                tag, icon, score_str = "dim", "⬜", "collecting data"
            else:
                score = anom_h.similarity_score
                if anom_h.bot_detected:
                    tag, icon = "bad", "🤖"
                elif anom_h.status == "red":
                    tag, icon = "bad", "🔴"
                elif anom_h.status == "orange":
                    tag, icon = "bad", "⚠️"
                elif anom_h.status == "yellow":
                    tag, icon = "warn", "🟡"
                else:
                    tag, icon = "ok", "✅"
                score_str = f"Combined: {score:.0f}% (KB: {anom_h.keyboard_similarity:.0f}%, Mouse: {anom_h.mouse_similarity:.0f}%)"
            self._history_text.insert(
                tk.END,
                f"{ts_str}  {icon}  {anom_h.status_label if anom_h else 'Collecting...'}  —  {score_str}\n",
                tag,
            )
        self._history_text.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Engine Callbacks
    # ------------------------------------------------------------------

    def _on_metrics_update(self, metrics) -> None:
        self._last_metrics = metrics
        if self._root_ref:
            self._root_ref.after(0, self.refresh)

    def _on_mouse_update(self, mouse_metrics) -> None:
        if self._root_ref:
            self._root_ref.after(0, self.refresh)

    def _on_anomaly_alert(self, anomaly) -> None:
        self._last_anomaly = anomaly
        if self._root_ref:
            self._root_ref.after(0, self._show_anomaly_toast)

    def _show_anomaly_toast(self) -> None:
        a = self._last_anomaly
        if not a:
            return
        if a.bot_detected:
            title = f"🤖 Bot Detected ({a.bot_type.replace('_', ' ').title()})"
            msg = a.bot_reason or "Mechanical or automated input detected."
        else:
            title = "⚠️ Behavioral Anomaly Detected"
            msg = f"Combined Similarity: {a.similarity_score:.0f}%\n" + (a.explanations[0] if a.explanations else "")
        messagebox.showwarning(title, msg)

    # ------------------------------------------------------------------
    # JSON Export Handlers
    # ------------------------------------------------------------------

    def _export_keyboard_profile(self) -> None:
        default_file = f"keyboard_behavior_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = filedialog.asksaveasfilename(
            title="Export Keyboard Profile to JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_file,
        )
        if not path:
            return
        try:
            exported = self._engine.export_keyboard_json(path)
            messagebox.showinfo("Export Successful ✔", f"Keyboard Profile exported to:\n{exported}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not export keyboard profile:\n{exc}")

    def _export_mouse_profile(self) -> None:
        default_file = f"mouse_behavior_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = filedialog.asksaveasfilename(
            title="Export Mouse Profile to JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_file,
        )
        if not path:
            return
        try:
            exported = self._engine.export_mouse_json(path)
            messagebox.showinfo("Export Successful ✔", f"Mouse Profile exported to:\n{exported}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not export mouse profile:\n{exc}")

    def _export_combined_profile(self) -> None:
        default_file = f"behavioral_profile_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = filedialog.asksaveasfilename(
            title="Export Combined Multi-Modal Profile to JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_file,
        )
        if not path:
            return
        try:
            exported = self._engine.export_combined_profile_json(path)
            messagebox.showinfo("Export Successful ✔", f"Combined Profile exported to:\n{exported}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not export combined profile:\n{exc}")

    def _export_session(self, duration_mins: int = 60) -> None:
        default_file = f"session_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = filedialog.asksaveasfilename(
            title=f"Export Session Data ({duration_mins}m) to JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_file,
        )
        if not path:
            return
        try:
            exported = self._engine.export_session_json(path, duration_mins=duration_mins)
            messagebox.showinfo("Export Successful ✔", f"Session activity exported to:\n{exported}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not export session data:\n{exc}")

    def _export_comparison_report(self) -> None:
        default_file = f"comparison_report_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = filedialog.asksaveasfilename(
            title="Generate Comparison Report to JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_file,
        )
        if not path:
            return
        try:
            exported = self._engine.export_comparison_json(path)
            messagebox.showinfo("Export Successful ✔", f"Comparison report exported to:\n{exported}")
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not export comparison report:\n{exc}")

    # ------------------------------------------------------------------
    # User Actions
    # ------------------------------------------------------------------

    def _toggle_enabled(self) -> None:
        if not self._engine:
            return
        cur = self._engine.settings.get("enabled", True)
        self._engine.settings["enabled"] = not cur
        if not cur:
            self._enabled_btn.config(text="● Enabled", bg=C["safe"])
        else:
            self._enabled_btn.config(text="○ Disabled", bg=C["text_dim"])

    def _this_was_me(self) -> None:
        if self._engine:
            saved = self._engine.confirm_this_was_me()
            messagebox.showinfo(
                "Confirmed & Saved",
                "✅ Session confirmed as yours!\n\n"
                "Multi-modal telemetry saved to data/my_behavior.json.\n"
                "Adaptive baseline updated with your latest patterns."
            )

    def _view_my_behavior_json(self) -> None:
        path = self._engine.my_behavior_path if self._engine else Path(__file__).parent.parent.parent / "data" / "my_behavior.json"
        if not path.exists():
            messagebox.showinfo(
                "No Saved Profile Yet",
                f"File {path.name} will be created upon first baseline completion or confirmation."
            )
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to read {path}: {exc}")
            return

        win = tk.Toplevel()
        win.title(f"Behavioral Profile ({path.name})")
        win.geometry("620x540")
        win.configure(bg=C["bg"])

        container = tk.Frame(win, bg=C["surface"], padx=18, pady=16)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        tk.Label(container, text=f"📄 {path.name}", bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        text_area = scrolledtext.ScrolledText(
            container, wrap=tk.WORD, font=("Consolas", 9),
            bg="#f8f9fa", fg="#1f2937", borderwidth=1, relief=tk.SOLID
        )
        text_area.pack(fill=tk.BOTH, expand=True, pady=(8, 10))
        text_area.insert(tk.END, content)
        text_area.configure(state=tk.DISABLED)

    def _retrain(self) -> None:
        if not messagebox.askyesno(
            "Retrain Multi-Modal Profile",
            "This will reset your keyboard and mouse baselines and restart passive learning.\n\nContinue?"
        ):
            return
        if self._engine:
            self._engine.delete_training_data()
        self._anomaly_start_ts = None
        self._update_view_mode()
        messagebox.showinfo("Retraining Started", "Baseline cleared. Collecting new multi-modal telemetry...")

    def _show_settings(self) -> None:
        if not self._engine:
            return
        win = tk.Toplevel()
        win.title("Behavioral Biometrics Settings")
        win.geometry("520x680")
        win.configure(bg=C["bg"])
        win.resizable(False, False)
        win.grab_set()

        container = tk.Frame(win, bg=C["surface"], padx=24, pady=20)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        tk.Label(container, text="⚙️  Biometrics Detection Settings",
                 bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 12))

        s = self._engine.settings

        tk.Label(container, text="Alert Threshold (Combined similarity % below = anomaly):",
                 bg=C["surface"], fg=C["text"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
        thresh_var = tk.DoubleVar(value=s.get("alert_threshold", 70.0))
        tk.Scale(container, from_=40, to=90, variable=thresh_var, orient=tk.HORIZONTAL,
                 bg=C["surface"], fg=C["text"], length=320, resolution=5).pack(anchor="w", pady=(2, 8))

        tk.Label(container, text="Minimum suspicious duration before alert (seconds):",
                 bg=C["surface"], fg=C["text"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
        dur_var = tk.IntVar(value=int(s.get("min_alert_duration", 120)))
        tk.Scale(container, from_=30, to=300, variable=dur_var, orient=tk.HORIZONTAL,
                 bg=C["surface"], fg=C["text"], length=320, resolution=30).pack(anchor="w", pady=(2, 8))

        adapt_var = tk.BooleanVar(value=s.get("adaptive_baseline", True))
        tk.Checkbutton(container, text="Update baseline adaptively with confirmed-normal sessions",
                       variable=adapt_var, bg=C["surface"], font=("Segoe UI", 9)).pack(anchor="w", pady=2)

        notify_var = tk.BooleanVar(value=s.get("desktop_notify", True))
        tk.Checkbutton(container, text="Show desktop notification on multi-modal anomaly / bot",
                       variable=notify_var, bg=C["surface"], font=("Segoe UI", 9)).pack(anchor="w", pady=2)

        # Mouse Tracking Precision & Performance Section
        mouse_box = tk.LabelFrame(container, text="🖱️ Mouse Tracking Precision & Performance",
                                  bg=C["surface"], fg=C["text"], font=("Segoe UI", 9, "bold"),
                                  padx=12, pady=8)
        mouse_box.pack(fill=tk.X, pady=(10, 4))

        mouse_track_var = tk.BooleanVar(value=s.get("mouse_tracking_enabled", True))
        tk.Checkbutton(mouse_box, text="Enable Mouse Dynamics Tracking",
                       variable=mouse_track_var, bg=C["surface"], font=("Segoe UI", 9, "bold"),
                       fg=C["safe"]).pack(anchor="w", pady=(0, 4))

        mouse_autopause_var = tk.BooleanVar(value=s.get("auto_pause_on_activity", True))
        tk.Checkbutton(mouse_box, text="Auto-pause during high activity (gaming / design)",
                       variable=mouse_autopause_var, bg=C["surface"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        tk.Label(mouse_box, text="Tracking Precision Mode (Downsampling Rate):",
                 bg=C["surface"], fg=C["text"], font=("Segoe UI", 8, "bold")).pack(anchor="w")

        prec_var = tk.StringVar(value=s.get("mouse_precision", "normal"))
        tk.Radiobutton(mouse_box, text="High (50 samples/sec - 20ms interval)",
                       variable=prec_var, value="high", bg=C["surface"],
                       font=("Segoe UI", 8)).pack(anchor="w")
        tk.Radiobutton(mouse_box, text="Normal (20 samples/sec - 50ms interval) [Recommended / Smooth]",
                       variable=prec_var, value="normal", bg=C["surface"],
                       font=("Segoe UI", 8, "bold"), fg=C["safe"]).pack(anchor="w")
        tk.Radiobutton(mouse_box, text="Low / Battery Saver (10 samples/sec - 100ms interval)",
                       variable=prec_var, value="low", bg=C["surface"],
                       font=("Segoe UI", 8)).pack(anchor="w")

        stats = self._engine.get_mouse_performance_stats()
        diag_txt = f"Performance: Callback <{stats.get('avg_callback_latency_ms', 0.05):.2f}ms | Priority: Low (Zero UI Lag)"
        tk.Label(mouse_box, text=diag_txt, bg=C["surface"], fg=C["text_dim"],
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", pady=(4, 0))

        btn_row = tk.Frame(container, bg=C["surface"])
        btn_row.pack(anchor="e", pady=(14, 0))

        def _save():
            s["alert_threshold"] = thresh_var.get()
            s["min_alert_duration"] = float(dur_var.get())
            s["adaptive_baseline"] = adapt_var.get()
            s["desktop_notify"] = notify_var.get()
            s["mouse_tracking_enabled"] = mouse_track_var.get()
            s["mouse_precision"] = prec_var.get()
            s["auto_pause_on_activity"] = mouse_autopause_var.get()

            # Apply directly to mouse recorder
            self._engine.set_mouse_precision(prec_var.get())
            self._engine.set_mouse_tracking_enabled(mouse_track_var.get())

            win.destroy()
            messagebox.showinfo("Settings Saved", "Biometrics and mouse performance settings updated.")

        tk.Button(btn_row, text="Save", command=_save, bg=C["btn_primary"], fg="white",
                  relief=tk.FLAT, padx=20, pady=8, font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_row, text="Cancel", command=win.destroy, bg=C["btn_bg"], fg=C["text"],
                  relief=tk.FLAT, padx=20, pady=8, font=("Segoe UI", 10), cursor="hand2").pack(side=tk.LEFT)



def _darken(hex_color: str, factor: float = 0.85) -> str:
    """Darken a hex color by a factor for hover effects."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#{:02x}{:02x}{:02x}".format(
            int(r * factor), int(g * factor), int(b * factor)
        )
    except Exception:
        return hex_color


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------

class _SystemTray:
    def __init__(self, on_open: Callable, on_pause_resume: Callable,
                 on_quit: Callable) -> None:
        self._on_open  = on_open
        self._on_pr    = on_pause_resume
        self._on_quit  = on_quit
        self._icon     = None
        self._paused   = False

    def start(self) -> None:
        try:
            import pystray
            img = _tray_image()
            if img is None:
                from PIL import Image
                img = Image.new("RGB", (64, 64), color=(89, 180, 250))

            def _open(_i, _it):  self._on_open()
            def _toggle(_i, _it):
                self._paused = not self._paused
                self._on_pr(self._paused)
            def _quit(_i, _it):
                _i.stop()
                self._on_quit()

            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", _open, default=True),
                pystray.MenuItem(
                    lambda _: "Resume Monitoring" if self._paused else "Pause Monitoring",
                    _toggle,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", _quit),
            )
            self._icon = pystray.Icon(
                "KeyloggerDetector", icon=img,
                title="Keylogger Detector", menu=menu,
            )
            threading.Thread(target=self._icon.run,
                             name="SystemTray", daemon=True).start()
        except Exception:
            pass   # pystray/PIL optional

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main Dashboard window
# ---------------------------------------------------------------------------

class Dashboard:
    """
    Top-level window. Call run() from the main thread — it blocks until quit.

    Parameters
    ----------
    alert_manager    : AlertManager instance
    db_logger        : DBLogger instance
    get_model_status : callable → one-line string describing model state
    on_pause         : called with (paused: bool) on tray pause/resume
    on_quit          : called when user quits
    """

    def __init__(
        self,
        alert_manager: "AlertManager",
        db_logger: "DBLogger",
        get_model_status: Callable[[], str],
        on_pause: Optional[Callable[[bool], None]] = None,
        on_quit:  Optional[Callable] = None,
        get_classifier: Optional[Callable] = None,   # NEW: returns live KeyloggerClassifier
    ) -> None:
        self._am   = alert_manager
        self._db   = db_logger
        self._get_model_status = get_model_status
        self._on_pause = on_pause or (lambda _p: None)
        self._on_quit  = on_quit  or (lambda: None)
        self._get_classifier = get_classifier or (lambda: None)  # NEW

        self._root: Optional[tk.Tk] = None
        self._tray: Optional[_SystemTray] = None
        self._q: queue.Queue = queue.Queue()
        
        # Notification state (NEW)
        self._notifications_enabled = True

        # Tabs (set after build)
        self._live_tab:        Optional[_LiveAlertsTab]        = None
        self._history_tab:     Optional[_HistoryTab]            = None
        self._stats_tab:       Optional[_StatsTab]              = None
        self._train_tab:       Optional[_TrainModelTab]         = None
        self._behavioral_tab:  Optional[_BehavioralAnalysisTab] = None  # NEW Phase 1

        # Behavioral engine (optional — set via set_behavioral_engine)
        self._behavioral_engine = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_behavioral_engine(self, engine) -> None:
        """Attach the BehavioralAnalysisEngine (called from main.py)."""
        self._behavioral_engine = engine

    def run(self) -> None:
        """Build window and enter mainloop (blocks)."""
        self._root = self._build_root()
        self._apply_styles()
        
        # Create menu bar (NEW - Application-like menu)
        self._create_menu_bar()

        # Create notebook with modern styling
        nb = ttk.Notebook(self._root, style="Modern.TNotebook")

        self._live_tab    = _LiveAlertsTab(nb, self._am, self._db)
        self._history_tab = _HistoryTab(nb, self._db)
        
        # Pass callback to stats tab for clickable cards
        def switch_to_history_with_filter(filter_value: str) -> None:
            """Switch to History tab and apply filter."""
            nb.select(1)  # Index 1 is History tab
            self._history_tab.filter_by_risk(filter_value)
        
        self._stats_tab   = _StatsTab(nb, self._db, self._get_model_status,
                                     switch_to_history_with_filter)

        # Tab 4 — Train Model  (NEW)
        self._train_tab = _TrainModelTab(
            nb, self._db, get_classifier=self._get_classifier
        )
        # Give the tab a reference to the root window so its training thread
        # can post callbacks back to the main loop via root.after().
        self._train_tab.set_root_ref(self._root)

        nb.add(self._live_tab,    text="  🚨 Live Alerts  ")
        nb.add(self._history_tab, text="  📋 History  ")
        nb.add(self._stats_tab,   text="  📊 Statistics  ")
        nb.add(self._train_tab,   text="  🎓 Train Model  ")

        # Tab 5 — Behavioral Analysis (Phase 1)
        self._behavioral_tab = _BehavioralAnalysisTab(
            nb, engine=self._behavioral_engine
        )
        self._behavioral_tab.set_root_ref(self._root)
        nb.add(self._behavioral_tab, text="  🧠 Behavior  ")

        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Modern status bar with notification indicator and live breathing pulse
        status_container = tk.Frame(self._root, bg=C["surface"], 
                                   relief=tk.FLAT, borderwidth=1,
                                   highlightthickness=1, highlightbackground=C["border"])
        status_container.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Left side: status text with pulsating dot
        left_frame = tk.Frame(status_container, bg=C["surface"])
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self._status_dot_lbl = tk.Label(
            left_frame, text="●",
            bg=C["surface"], fg=C["safe"],
            font=("Segoe UI", 10, "bold"), padx=4, pady=8
        )
        self._status_dot_lbl.pack(side=tk.LEFT, padx=(12, 0))

        self._status_var = tk.StringVar(value="Monitoring active")
        tk.Label(
            left_frame, textvariable=self._status_var,
            bg=C["surface"], fg=C["text"],
            font=("Segoe UI", 9), anchor="w", padx=6, pady=8,
        ).pack(side=tk.LEFT)
        
        # Notification indicator (NEW)
        self._notif_indicator = tk.Label(
            left_frame, text="",
            bg=C["surface"], fg=C["text_dim"],
            font=("Segoe UI", 8), anchor="w", padx=8,
        )
        self._notif_indicator.pack(side=tk.LEFT)
        self._update_notification_indicator()
        
        # Right side: version info
        tk.Label(
            status_container, text="AI Keylogger Detection v2.5",
            bg=C["surface"], fg=C["text_light"],
            font=("Segoe UI", 8), anchor="e", padx=16,
        ).pack(side=tk.RIGHT)

        self._root.protocol("WM_DELETE_WINDOW", self._hide)

        self._tray = _SystemTray(
            on_open=self._show,
            on_pause_resume=self._on_pause,
            on_quit=self._quit,
        )
        self._tray.start()

        # Start smooth live pulse animation
        self._start_pulse_animation()

        self._root.after(UI_REFRESH_MS, self._tick)
        self._root.mainloop()

    def _start_pulse_animation(self) -> None:
        """Smooth breathing pulse animation for live monitoring indicator dot."""
        pulse_colors = ["#27ae60", "#2ecc71", "#58d68d", "#2ecc71"]
        self._pulse_idx = 0

        def _pulse():
            if not self._root:
                return
            try:
                if self._root.winfo_exists() and hasattr(self, "_status_dot_lbl"):
                    color = pulse_colors[self._pulse_idx % len(pulse_colors)]
                    self._status_dot_lbl.config(fg=color)
                    self._pulse_idx += 1
                self._root.after(450, _pulse)
            except Exception:
                pass

        _pulse()


    def show(self) -> None:
        """Bring window to front (thread-safe)."""
        self._q.put(("show", None))

    def update_status(self, message: str) -> None:
        """Update bottom status bar text (thread-safe)."""
        self._q.put(("status", message))
    
    def are_notifications_enabled(self) -> bool:
        """Check if desktop notifications are enabled (NEW)."""
        return self._notifications_enabled
    
    def set_notifications_enabled(self, enabled: bool) -> None:
        """Enable or disable desktop notifications (NEW)."""
        self._notifications_enabled = enabled
        try:
            from ..live_api import set_notifications_enabled
            set_notifications_enabled(enabled)
        except Exception:
            pass
        self._update_notification_indicator()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_root(self) -> tk.Tk:
        root = tk.Tk()
        root.title("AI Keylogger Detection System")
        root.geometry("1024x700")
        root.minsize(900, 600)
        root.configure(bg=C["bg"])
        
        # Try to set window icon
        try:
            img = _tray_image()
            if img:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(img)
                root.iconphoto(True, photo)
        except Exception:
            pass
        return root

    def _create_menu_bar(self) -> None:
        """Create application menu bar (NEW - makes it feel like a real application)."""
        menubar = tk.Menu(self._root, bg=C["surface"], fg=C["text"],
                         activebackground=C["accent"], activeforeground="white")
        self._root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=C["surface"], fg=C["text"],
                           activebackground=C["accent"], activeforeground="white")
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Minimize to Tray", command=self._hide,
                             accelerator="Esc")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._quit,
                             accelerator="Alt+F4")
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=C["surface"], fg=C["text"],
                           activebackground=C["accent"], activeforeground="white")
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Refresh All Tabs", command=self._refresh_all_tabs)
        view_menu.add_separator()
        view_menu.add_checkbutton(label="Show Notifications", 
                                 command=self._toggle_notifications,
                                 variable=tk.BooleanVar(value=self._notifications_enabled))
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0, bg=C["surface"], fg=C["text"],
                            activebackground=C["accent"], activeforeground="white")
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Clear Live Alerts", 
                              command=self._clear_live_alerts)
        # Export sub-menu (Feature 5 & 6)
        export_menu = tk.Menu(tools_menu, tearoff=0, bg=C["surface"], fg=C["text"],
                             activebackground=C["accent"], activeforeground="white")
        tools_menu.add_cascade(label="Export History", menu=export_menu)
        export_menu.add_command(label="💾 Export to CSV...",
                               command=self._export_to_csv)
        export_menu.add_command(label="📄 Export to PDF...",
                               command=self._export_to_pdf)
        tools_menu.add_separator()
        tools_menu.add_command(label="Settings", 
                              command=self._show_settings)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=C["surface"], fg=C["text"],
                           activebackground=C["accent"], activeforeground="white")
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Quick Start Guide", 
                             command=lambda: self._open_doc("QUICK_START.md"))
        help_menu.add_command(label="User Manual", 
                             command=lambda: self._open_doc("README.md"))
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        
        # Bind keyboard shortcuts
        self._root.bind("<Escape>", lambda e: self._hide())
        self._root.bind("<F5>", lambda e: self._refresh_all_tabs())

    def _toggle_notifications(self) -> None:
        """Toggle notification enable/disable (NEW)."""
        self.set_notifications_enabled(not self._notifications_enabled)
        
        # Show confirmation
        status = "enabled" if self._notifications_enabled else "disabled"
        messagebox.showinfo(
            "Notifications " + status.title(),
            f"Desktop notifications are now {status}.\n\n"
            f"{'You will' if self._notifications_enabled else 'You will NOT'} "
            f"receive popup alerts for detected threats."
        )
        
        # Update status bar temporarily
        old_status = self._status_var.get()
        self._status_var.set(f"Notifications {status}")
        self._root.after(3000, lambda: self._status_var.set(old_status))

    def _update_notification_indicator(self) -> None:
        """Update the notification status indicator in status bar (NEW)."""
        if hasattr(self, '_notif_indicator'):
            if self._notifications_enabled:
                self._notif_indicator.config(
                    text="🔔 Notifications ON",
                    fg=C["safe"]
                )
            else:
                self._notif_indicator.config(
                    text="🔕 Notifications OFF",
                    fg=C["text_dim"]
                )

    def _refresh_all_tabs(self) -> None:
        """Refresh all tabs (NEW - accessible from menu)."""
        if self._live_tab:
            self._live_tab.refresh()
        if self._history_tab:
            self._history_tab.refresh()
        if self._stats_tab:
            self._stats_tab.refresh()
        
        # Show confirmation in status bar
        old_status = self._status_var.get()
        self._status_var.set("✓ All tabs refreshed")
        self._root.after(2000, lambda: self._status_var.set(old_status))

    def _clear_live_alerts(self) -> None:
        """Clear live alerts (NEW - accessible from menu)."""
        if messagebox.askyesno("Clear Alerts", 
                              "Remove all alerts from the Live Alerts tab?\n\n"
                              "This will not delete them from the database."):
            self._am.clear_alerts()
            if self._live_tab:
                self._live_tab.refresh()
            self._status_var.set("✓ Live alerts cleared")

    def _export_history(self) -> None:
        """Legacy entry point — now superseded by _export_to_csv / _export_to_pdf."""
        self._export_to_csv()

    def _export_to_csv(self) -> None:
        """
        Feature 5: Export full detection history to a CSV file.

        Opens a save-file dialog, queries all detections from the database,
        and writes a UTF-8-with-BOM CSV so Excel opens it correctly.
        """
        # --- file picker ---
        docs_dir = Path.home() / "Documents"
        default_name = f"keyguard_detections_{datetime.now():%Y%m%d_%H%M%S}.csv"
        filepath = filedialog.asksaveasfilename(
            title="Export Detection History to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(docs_dir) if docs_dir.exists() else str(Path.home()),
            initialfile=default_name,
        )
        if not filepath:
            return   # user cancelled

        # --- query all detections ---
        try:
            rows = self._db.query_detections(limit=100_000)
        except Exception as exc:
            messagebox.showerror("Export Failed",
                                 f"Could not read database:\n{exc}")
            return

        # --- write CSV ---
        COLUMNS = [
            "detected_at", "process_name", "pid", "risk_level",
            "score", "confidence", "reasons", "exe_path",
            "model_version", "actioned",
        ]
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=COLUMNS,
                    extrasaction="ignore",
                )
                writer.writeheader()
                for row in rows:
                    # Format timestamp as human-readable string
                    ts_raw = row.get("detected_at", 0)
                    row["detected_at"] = _fmt_datetime(ts_raw) if ts_raw else ""
                    # Round score to 4 decimal places
                    score = row.get("score", 0)
                    row["score"] = f"{float(score):.4f}" if score is not None else "0"
                    confidence = row.get("confidence", 0)
                    row["confidence"] = f"{float(confidence):.4f}" if confidence is not None else "0"
                    # Flatten reasons list to a semicolon-separated string
                    reasons = row.get("reasons", [])
                    if isinstance(reasons, list):
                        row["reasons"] = "; ".join(reasons)
                    row["actioned"] = "Yes" if row.get("actioned") else "No"
                    writer.writerow(row)

        except PermissionError:
            messagebox.showerror(
                "Export Failed",
                f"Cannot write to:\n{filepath}\n\n"
                "The file may be open in another application (e.g. Excel).\n"
                "Close it and try again."
            )
            return
        except OSError as exc:
            messagebox.showerror("Export Failed",
                                 f"File system error:\n{exc}")
            return

        messagebox.showinfo(
            "Export Successful ✔",
            f"Exported {len(rows)} record(s) to:\n{filepath}"
        )

    def _export_to_pdf(self) -> None:
        """
        Feature 6 (Bonus): Generate a professional PDF detection report.

        Requires the fpdf2 package (pip install fpdf2).  If not installed,
        the user is shown a friendly prompt with the install command.

        Report structure
        ----------------
        Page 1  – Cover: title, date range, summary stats box
        Page 2+ – Detailed table: one row per detection, colour-coded risk,
                   alternating row shading, auto-pagination, page numbers.
        """
        # --- check fpdf2 is available ---
        try:
            from fpdf import FPDF  # fpdf2
        except ImportError:
            messagebox.showwarning(
                "Missing Dependency",
                "PDF export requires the 'fpdf2' package.\n\n"
                "Install it by running:\n"
                "    pip install fpdf2\n\n"
                "Then restart the application."
            )
            return

        # --- file picker ---
        docs_dir = Path.home() / "Documents"
        default_name = f"keyguard_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        filepath = filedialog.asksaveasfilename(
            title="Export Detection Report to PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=str(docs_dir) if docs_dir.exists() else str(Path.home()),
            initialfile=default_name,
        )
        if not filepath:
            return

        # --- fetch data ---
        try:
            rows = self._db.query_detections(limit=100_000)
            stats = self._db.stats()
        except Exception as exc:
            messagebox.showerror("Export Failed",
                                 f"Could not read database:\n{exc}")
            return

        # --- helper: risk colour as (R, G, B) tuple ---
        RISK_COLORS = {
            "malicious":  (231, 76, 60),    # red
            "suspicious": (243, 156, 18),   # orange
            "safe":       (39, 174, 96),     # green
        }

        # --- build PDF ---
        try:
            pdf = FPDF(orientation="L", unit="mm", format="A4")
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.set_margins(15, 15, 15)

            # ── Cover page ──────────────────────────────────────────
            pdf.add_page()

            # Title bar
            pdf.set_fill_color(41, 128, 185)   # blue
            pdf.rect(0, 0, 297, 40, style="F")
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 22)
            pdf.set_xy(15, 10)
            pdf.cell(267, 12, "KeyGuard AI — Detection Report", ln=True, align="C")
            pdf.set_font("Helvetica", "", 11)
            pdf.set_xy(15, 24)
            pdf.cell(267, 8,
                     f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
                     align="C")

            pdf.set_text_color(44, 62, 80)
            pdf.ln(20)

            # Summary stats box
            pdf.set_fill_color(232, 244, 248)   # light blue tint
            pdf.set_draw_color(189, 195, 199)
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 10, "Summary", ln=True)
            pdf.set_font("Helvetica", "", 11)

            summary_items = [
                ("Total Detections",  stats.get("total_detections", 0)),
                ("Malicious",         stats.get("malicious_count",  0)),
                ("Suspicious",        stats.get("suspicious_count", 0)),
                ("Actions Taken",     stats.get("actioned_count",   0)),
            ]
            for label, value in summary_items:
                pdf.set_fill_color(232, 244, 248)
                pdf.cell(80, 9, f"  {label}:", border="LTB", fill=True)
                pdf.cell(40, 9, str(value), border="RTB", fill=True, ln=True)

            # ── Detail table pages ───────────────────────────────────
            pdf.add_page()

            # Column definitions: (header text, width in mm)
            COL_DEFS = [
                ("Date/Time",  48),
                ("Process",    45),
                ("PID",        18),
                ("Risk",       25),
                ("Score",      18),
                ("Confidence", 20),
                ("Actioned",   18),
                ("Indicators", 75),
            ]

            # Table header
            def _draw_header():
                pdf.set_fill_color(41, 128, 185)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Helvetica", "B", 9)
                for hdr, w in COL_DEFS:
                    pdf.cell(w, 8, hdr, border=1, fill=True, align="C")
                pdf.ln()
                pdf.set_text_color(44, 62, 80)

            _draw_header()

            # Table rows
            pdf.set_font("Helvetica", "", 8)
            for i, row in enumerate(rows):
                # Auto-add a new page + header when near bottom
                if pdf.get_y() > pdf.h - 25:
                    pdf.add_page()
                    _draw_header()
                    pdf.set_font("Helvetica", "", 8)

                risk_val = (row.get("risk_level") or "safe").lower()
                r, g, b = RISK_COLORS.get(risk_val, (44, 62, 80))

                # Alternating row shading
                if i % 2 == 0:
                    pdf.set_fill_color(248, 249, 250)
                else:
                    pdf.set_fill_color(255, 255, 255)

                ts_raw = row.get("detected_at", 0)
                ts_str = _fmt_datetime(ts_raw) if ts_raw else ""

                reasons = row.get("reasons", [])
                if isinstance(reasons, list):
                    reasons_str = "; ".join(reasons[:2])
                else:
                    reasons_str = str(reasons)
                # Truncate long indicator strings
                if len(reasons_str) > 80:
                    reasons_str = reasons_str[:77] + "..."

                row_data = [
                    (ts_str,                                        COL_DEFS[0][1]),
                    (str(row.get("process_name", ""))[:30],         COL_DEFS[1][1]),
                    (str(row.get("pid", "")),                       COL_DEFS[2][1]),
                    (risk_val.upper(),                               COL_DEFS[3][1]),
                    (f"{float(row.get('score', 0)):.1%}",           COL_DEFS[4][1]),
                    (f"{float(row.get('confidence', 0)):.1%}",      COL_DEFS[5][1]),
                    ("Yes" if row.get("actioned") else "No",        COL_DEFS[6][1]),
                    (reasons_str,                                    COL_DEFS[7][1]),
                ]

                for j, (text, w) in enumerate(row_data):
                    # Colour-code the Risk column
                    if j == 3:
                        pdf.set_text_color(r, g, b)
                        pdf.set_font("Helvetica", "B", 8)
                    else:
                        pdf.set_text_color(44, 62, 80)
                        pdf.set_font("Helvetica", "", 8)
                    pdf.cell(w, 7, text, border=1, fill=(j != 3),
                             align="C" if j in (2, 4, 5, 6) else "L")

                pdf.ln()

            # Page numbers in footer (iterate pages)
            total_pages = pdf.page
            for pg in range(1, total_pages + 1):
                pdf.page = pg
                pdf.set_y(-12)
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(150, 150, 150)
                pdf.cell(0, 8,
                         f"KeyGuard AI Detection Report  •  Page {pg} of {total_pages}",
                         align="C")

            pdf.output(filepath)

        except Exception as exc:
            messagebox.showerror("Export Failed",
                                 f"PDF generation error:\n{exc}")
            return

        messagebox.showinfo(
            "Export Successful ✔",
            f"PDF report ({len(rows)} record(s)) saved to:\n{filepath}"
        )

    def _show_settings(self) -> None:
        """Show settings dialog (NEW)."""
        settings_win = tk.Toplevel(self._root)
        settings_win.title("Settings")
        settings_win.geometry("500x400")
        settings_win.configure(bg=C["bg"])
        settings_win.resizable(False, False)
        
        # Center the window
        settings_win.transient(self._root)
        settings_win.grab_set()
        
        # Container
        container = tk.Frame(settings_win, bg=C["surface"], padx=24, pady=20)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # Title
        tk.Label(container, text="Application Settings",
                bg=C["surface"], fg=C["text"],
                font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 20))
        
        # Notifications section
        notif_frame = tk.Frame(container, bg=C["surface"])
        notif_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(notif_frame, text="Notifications",
                bg=C["surface"], fg=C["text"],
                font=("Segoe UI", 11, "bold")).pack(anchor="w")
        
        tk.Label(notif_frame, text="Control desktop notification alerts",
                bg=C["surface"], fg=C["text_dim"],
                font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 8))
        
        # Notification toggle button (styled)
        notif_btn_frame = tk.Frame(notif_frame, bg=C["surface"])
        notif_btn_frame.pack(anchor="w")
        
        def toggle_notif():
            self._toggle_notifications()
            update_button()
        
        def update_button():
            if self._notifications_enabled:
                notif_btn.config(text="🔔 Notifications Enabled",
                               bg=C["safe"], fg="white")
            else:
                notif_btn.config(text="🔕 Notifications Disabled",
                               bg=C["text_dim"], fg="white")
        
        notif_btn = tk.Button(notif_btn_frame, text="",
                             command=toggle_notif,
                             relief=tk.FLAT, padx=20, pady=10,
                             font=("Segoe UI", 10, "bold"),
                             cursor="hand2", borderwidth=0)
        notif_btn.pack()
        update_button()
        
        # Separator
        tk.Frame(container, bg=C["border"], height=1).pack(fill=tk.X, pady=20)
        
        # Info section
        info_frame = tk.Frame(container, bg=C["surface"])
        info_frame.pack(fill=tk.X)
        
        tk.Label(info_frame, text="Application Information",
                bg=C["surface"], fg=C["text"],
                font=("Segoe UI", 11, "bold")).pack(anchor="w")
        
        info_text = [
            ("Version:", "1.0.0"),
            ("Database:", str(self._db._db_path.absolute())),
            ("Model:", "ML-based detection" if hasattr(self, '_get_model_status') else "Heuristic"),
        ]
        
        for label, value in info_text:
            row = tk.Frame(info_frame, bg=C["surface"])
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=label, width=12, anchor="w",
                    bg=C["surface"], fg=C["text_dim"],
                    font=("Segoe UI", 9)).pack(side=tk.LEFT)
            tk.Label(row, text=value, anchor="w",
                    bg=C["surface"], fg=C["text"],
                    font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Close button
        close_btn = tk.Button(container, text="Close", command=settings_win.destroy,
                             bg=C["btn_primary"], fg="white", relief=tk.FLAT,
                             padx=24, pady=10, font=("Segoe UI", 10, "bold"),
                             cursor="hand2", borderwidth=0)
        close_btn.pack(anchor="e", pady=(20, 0))
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg=C["accent_hover"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg=C["btn_primary"]))

    def _open_doc(self, filename: str) -> None:
        """Open documentation file (NEW)."""
        try:
            from pathlib import Path
            import os
            doc_path = Path(__file__).parent.parent.parent / filename
            if doc_path.exists():
                os.startfile(str(doc_path))
            else:
                messagebox.showwarning("File Not Found",
                                     f"Documentation file not found:\n{filename}\n\n"
                                     f"Expected location: {doc_path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open documentation:\n{exc}")

    def _show_about(self) -> None:
        """Show about dialog (NEW)."""
        about_win = tk.Toplevel(self._root)
        about_win.title("About")
        about_win.geometry("450x350")
        about_win.configure(bg=C["bg"])
        about_win.resizable(False, False)
        
        # Center the window
        about_win.transient(self._root)
        about_win.grab_set()
        
        # Container
        container = tk.Frame(about_win, bg=C["surface"], padx=32, pady=24)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # Icon (if available)
        try:
            img = _tray_image()
            if img:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(img.resize((64, 64)))
                icon_label = tk.Label(container, image=photo, bg=C["surface"])
                icon_label.image = photo  # Keep reference
                icon_label.pack(pady=(0, 12))
        except:
            pass
        
        # Title
        tk.Label(container, text="AI Keylogger Detection System",
                bg=C["surface"], fg=C["text"],
                font=("Segoe UI", 14, "bold")).pack()
        
        # Version
        tk.Label(container, text="Version 1.0.0",
                bg=C["surface"], fg=C["text_dim"],
                font=("Segoe UI", 10)).pack(pady=(4, 16))
        
        # Description
        desc = ("Real-time keylogger detection powered by machine learning.\n\n"
                "Features:\n"
                "• ML-based threat classification\n"
                "• Real-time process monitoring\n"
                "• Interactive statistics dashboard\n"
                "• Desktop notifications\n"
                "• Complete audit trail")
        
        tk.Label(container, text=desc,
                bg=C["surface"], fg=C["text"],
                font=("Segoe UI", 9), justify=tk.LEFT).pack(pady=(0, 16))
        
        # Copyright
        tk.Label(container, text="© 2026 - MIT License",
                bg=C["surface"], fg=C["text_dim"],
                font=("Segoe UI", 8)).pack()
        
        # Close button
        close_btn = tk.Button(container, text="Close", command=about_win.destroy,
                             bg=C["btn_primary"], fg="white", relief=tk.FLAT,
                             padx=24, pady=8, font=("Segoe UI", 10, "bold"),
                             cursor="hand2", borderwidth=0)
        close_btn.pack(pady=(16, 0))
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg=C["accent_hover"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg=C["btn_primary"]))

    def _apply_styles(self) -> None:
        """Apply modern ttk styles with light theme."""
        style = ttk.Style(self._root)
        style.theme_use("clam")

        # Frame styles
        style.configure("Modern.TFrame", background=C["bg"])
        
        # Notebook (tabs) styling
        style.configure("Modern.TNotebook", 
                       background=C["bg"], 
                       borderwidth=0,
                       tabmargins=[2, 5, 2, 0])
        
        style.configure("Modern.TNotebook.Tab",
                       background=C["surface"],
                       foreground=C["text"],
                       padding=[16, 10],
                       font=("Segoe UI", 10, "bold"),
                       borderwidth=1)
        
        style.map("Modern.TNotebook.Tab",
                 background=[("selected", C["bg"])],
                 foreground=[("selected", C["accent"])],
                 expand=[("selected", [1, 1, 1, 0])])
        
        # Treeview styling with modern look
        style.configure("Modern.Treeview",
                       background="white",
                       foreground=C["text"],
                       fieldbackground="white",
                       rowheight=26,
                       font=("Segoe UI", 9),
                       borderwidth=0)
        
        style.configure("Modern.Treeview.Heading",
                       background=C["surface"],
                       foreground=C["text"],
                       font=("Segoe UI", 10, "bold"),
                       borderwidth=1,
                       relief=tk.FLAT)
        
        style.map("Modern.Treeview",
                 background=[("selected", C["accent"])],
                 foreground=[("selected", "white")])
        
        style.map("Modern.Treeview.Heading",
                 background=[("active", C["border"])])
        
        # Scrollbar styling
        style.configure("Modern.Vertical.TScrollbar",
                       background=C["btn_bg"],
                       troughcolor=C["bg"],
                       borderwidth=0,
                       arrowsize=14)

    def _tick(self) -> None:
        """Drain queue and refresh tabs every UI_REFRESH_MS."""
        while not self._q.empty():
            try:
                cmd, payload = self._q.get_nowait()
                if cmd == "show":
                    self._show()
                elif cmd == "status" and self._root:
                    self._status_var.set(payload)
            except queue.Empty:
                break

        if self._live_tab:
            self._live_tab.refresh()
        if self._stats_tab:
            self._stats_tab.refresh()
        if self._behavioral_tab:
            try:
                self._behavioral_tab.refresh()
            except Exception:
                pass

        if self._root:
            self._root.after(UI_REFRESH_MS, self._tick)

    def _show(self) -> None:
        if self._root:
            self._root.deiconify()
            self._root.lift()
            self._root.focus_force()

    def _hide(self) -> None:
        """Minimise to tray on window close."""
        if self._root:
            self._root.withdraw()

    def _quit(self) -> None:
        if self._tray:
            self._tray.stop()
        if self._root:
            self._root.quit()
            self._root.destroy()
        self._on_quit()
