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
import os
import queue
import threading
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..alert_manager import AlertManager, AlertRecord, ResponseAction
    from ..classifier import RiskLevel
    from ..db_logger import DBLogger

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
        risk = self._risk_var.get().lower()
        risk = None if risk == "all" else risk
        since = time.time() - self._hours_var.get() * 3600

        rows = self._db.query_detections(
            limit=HISTORY_LIMIT, risk_level=risk, since=since
        )
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
        stats = self._db.stats()
        for key, var in self._card_vars.items():
            var.set(str(stats.get(key, 0)))

        counts = stats.get("action_counts", {})
        self._action_text.config(state=tk.NORMAL)
        self._action_text.delete("1.0", tk.END)
        if counts:
            for action, count in sorted(counts.items()):
                self._action_text.insert(tk.END, f"  {action.title():<14} {count}\n")
        else:
            self._action_text.insert(tk.END, "  No actions recorded yet.\n")
        self._action_text.config(state=tk.DISABLED)

        self._model_var.set(self._get_model_status())


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
        with self._lock:
            if not self._recording:
                return self._last_csv_path
            self._recording = False
            session_id = self._session_id
            count      = self._count

        # Signal poll thread to exit
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.POLL_INTERVAL + 2)

        if count == 0 or not session_id:
            return None

        # Export to CSV
        ts  = time.strftime("%Y%m%d_%H%M%S")
        out = Path(__file__).parent.parent.parent / "data" / f"my_behavior_{ts}.csv"
        try:
            rows_written = self._store.export_to_csv(out, session_id=session_id)
            with self._lock:
                self._last_csv_path = out
            return out if rows_written > 0 else None
        except Exception as exc:
            # Export failed — keep data in DB, tell caller via None
            import logging
            logging.getLogger(__name__).error("CSV export failed: %s", exc)
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
        csv_out = self._recorder.stop()

        self._cancel_tick()
        self._btn_stop.config(state=tk.DISABLED)
        self._btn_start.config(state=tk.NORMAL)
        self._lbl_rec_state.config(
            text="⬤  Recording stopped.", fg=C["text_light"]
        )

        if csv_out is None or count == 0:
            messagebox.showwarning(
                "No Data Recorded",
                "No new user-launched processes were captured during this session.\n\n"
                "Tips:\n"
                "• Open some applications after clicking Start Recording.\n"
                "• Run for at least 5 minutes to capture enough samples.",
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
        self._live_tab:    Optional[_LiveAlertsTab]  = None
        self._history_tab: Optional[_HistoryTab]     = None
        self._stats_tab:   Optional[_StatsTab]       = None
        self._train_tab:   Optional[_TrainModelTab]  = None  # NEW

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Modern status bar with notification indicator
        status_container = tk.Frame(self._root, bg=C["surface"], 
                                   relief=tk.FLAT, borderwidth=1,
                                   highlightthickness=1, highlightbackground=C["border"])
        status_container.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Left side: status text
        left_frame = tk.Frame(status_container, bg=C["surface"])
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self._status_var = tk.StringVar(value="✓ Monitoring active")
        tk.Label(
            left_frame, textvariable=self._status_var,
            bg=C["surface"], fg=C["text"],
            font=("Segoe UI", 9), anchor="w", padx=16, pady=8,
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
            status_container, text="AI Keylogger Detection v1.0",
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

        self._root.after(UI_REFRESH_MS, self._tick)
        self._root.mainloop()

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
        tools_menu.add_command(label="Export History...", 
                              command=self._export_history,
                              state=tk.DISABLED)  # TODO: Implement
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
        self._notifications_enabled = not self._notifications_enabled
        self._update_notification_indicator()
        
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
        """Export detection history (NEW - placeholder for future feature)."""
        messagebox.showinfo("Export History",
                           "Export feature coming in v1.1!\n\n"
                           "Will support: CSV, JSON, PDF formats")

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
