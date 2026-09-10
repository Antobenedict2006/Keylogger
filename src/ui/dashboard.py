"""
dashboard.py
============
Tkinter dashboard + pystray system-tray icon.

Tabs
----
  Tab 1 – Live Alerts       : real-time threat list + Terminate/Quarantine/Whitelist/Dismiss
  Tab 2 – Detection History : filterable SQLite query view, double-click for detail popup
  Tab 3 – Statistics        : summary cards + action breakdown + model status

System Tray
-----------
  pystray icon with: Open Dashboard | Pause/Resume | Quit

Thread safety
-------------
  Tkinter mainloop runs on the main thread.
  Background threads push updates via a queue.Queue drained by after().
"""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..alert_manager import AlertManager, AlertRecord, ResponseAction
    from ..classifier import RiskLevel
    from ..db_logger import DBLogger

# ---------------------------------------------------------------------------
# Colour palette  (dark theme)
# ---------------------------------------------------------------------------
C = {
    "bg":           "#1e1e2e",
    "surface":      "#2a2a3e",
    "border":       "#3a3a5c",
    "text":         "#cdd6f4",
    "text_dim":     "#7f849c",
    "safe":         "#a6e3a1",
    "suspicious":   "#f9e2af",
    "malicious":    "#f38ba8",
    "accent":       "#89b4fa",
    "btn_bg":       "#313244",
    "btn_hover":    "#45475a",
}

UI_REFRESH_MS  = 2_000
HISTORY_LIMIT  = 200


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _risk_colour(risk: str) -> str:
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
    def __init__(self, parent: tk.Widget, row: Dict) -> None:
        super().__init__(parent)
        self.title(f"Detection Detail — {row.get('process_name','?')}")
        self.configure(bg=C["bg"])
        self.geometry("640x440")
        self.resizable(True, True)

        frm = tk.Frame(self, bg=C["bg"], padx=16, pady=12)
        frm.pack(fill=tk.BOTH, expand=True)

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
            r = tk.Frame(frm, bg=C["bg"])
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=f"{label}:", width=14, anchor="w",
                     bg=C["bg"], fg=C["text_dim"],
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
            colour = _risk_colour(str(value)) if label == "Risk Level" else C["text"]
            tk.Label(r, text=str(value), anchor="w",
                     bg=C["bg"], fg=colour,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)

        tk.Label(frm, text="Indicators:", anchor="w",
                 bg=C["bg"], fg=C["text_dim"],
                 font=("Segoe UI", 9, "bold")).pack(fill=tk.X, pady=(10, 2))

        reasons = row.get("reasons", [])
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except Exception:
                reasons = [reasons]

        tb = tk.Text(frm, height=8, bg=C["surface"], fg=C["text"],
                     relief=tk.FLAT, font=("Segoe UI", 9), wrap=tk.WORD)
        tb.pack(fill=tk.BOTH, expand=True)
        for r in reasons:
            tb.insert(tk.END, f"• {r}\n")
        if not reasons:
            tb.insert(tk.END, "No specific indicators recorded.")
        tb.config(state=tk.DISABLED)

        tk.Button(frm, text="Close", command=self.destroy,
                  bg=C["btn_bg"], fg=C["text"], relief=tk.FLAT,
                  padx=12, pady=4).pack(anchor="e", pady=(8, 0))


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
        tf = tk.Frame(self, bg=C["bg"])
        tf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        self._tree = ttk.Treeview(tf, columns=self.COLS, show="headings",
                                  selectmode="browse", style="Dark.Treeview")
        for col, w, hdr in zip(self.COLS, self.WIDTHS, self.HEADERS):
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, minwidth=40, anchor="w")

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.tag_configure("malicious",  foreground=C["malicious"])
        self._tree.tag_configure("suspicious", foreground=C["suspicious"])
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>",          self._on_dbl)

        # Toolbar
        bar = tk.Frame(self, bg=C["surface"], pady=6)
        bar.pack(fill=tk.X, padx=8, pady=6)

        bs = dict(bg=C["btn_bg"], fg=C["text"], relief=tk.FLAT,
                  padx=14, pady=5, font=("Segoe UI", 9), cursor="hand2")
        self._btn_terminate  = tk.Button(bar, text="🗙 Terminate",  command=self._terminate,  **bs)
        self._btn_quarantine = tk.Button(bar, text="🔒 Quarantine", command=self._quarantine, **bs)
        self._btn_whitelist  = tk.Button(bar, text="✓ Whitelist",  command=self._whitelist,  **bs)
        self._btn_dismiss    = tk.Button(bar, text="✕ Dismiss",    command=self._dismiss,    **bs)
        self._btn_clear      = tk.Button(bar, text="Clear All",    command=self._clear,      **bs)

        for b in (self._btn_terminate, self._btn_quarantine,
                  self._btn_whitelist, self._btn_dismiss):
            b.pack(side=tk.LEFT, padx=4)
        self._btn_clear.pack(side=tk.RIGHT, padx=4)

        self._status = tk.StringVar(value="No threats detected.")
        tk.Label(self, textvariable=self._status,
                 bg=C["bg"], fg=C["text_dim"],
                 font=("Segoe UI", 8), anchor="w").pack(fill=tk.X, padx=10, pady=(0, 4))

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
        super().__init__(parent, style="Dark.TFrame")
        self._db = db_logger
        self._cache: List[Dict] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Filter bar
        fb = tk.Frame(self, bg=C["surface"], pady=6, padx=8)
        fb.pack(fill=tk.X, padx=8, pady=(8, 2))

        tk.Label(fb, text="Risk:", bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._risk_var = tk.StringVar(value="All")
        ttk.Combobox(fb, textvariable=self._risk_var,
                     values=["All", "Malicious", "Suspicious"],
                     state="readonly", width=12).pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(fb, text="Last (hrs):", bg=C["surface"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._hours_var = tk.IntVar(value=24)
        tk.Spinbox(fb, from_=1, to=720, textvariable=self._hours_var,
                   width=6, bg=C["btn_bg"], fg=C["text"],
                   relief=tk.FLAT).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(fb, text="Refresh", command=self.refresh,
                  bg=C["accent"], fg=C["bg"], relief=tk.FLAT,
                  padx=10, pady=3,
                  font=("Segoe UI", 9, "bold"),
                  cursor="hand2").pack(side=tk.LEFT)

        # Treeview
        tf = tk.Frame(self, bg=C["bg"])
        tf.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._tree = ttk.Treeview(tf, columns=self.COLS, show="headings",
                                  selectmode="browse", style="Dark.Treeview")
        for col, w, hdr in zip(self.COLS, self.WIDTHS, self.HEADERS):
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, minwidth=40, anchor="w")

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.tag_configure("malicious",  foreground=C["malicious"])
        self._tree.tag_configure("suspicious", foreground=C["suspicious"])
        self._tree.bind("<Double-1>", self._on_dbl)

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

    def __init__(self, parent, db_logger: "DBLogger",
                 get_model_status: Callable[[], str]) -> None:
        super().__init__(parent, style="Dark.TFrame")
        self._db = db_logger
        self._get_model_status = get_model_status
        self._build()

    def _build(self) -> None:
        outer = tk.Frame(self, bg=C["bg"], padx=20, pady=20)
        outer.pack(fill=tk.BOTH, expand=True)

        # Summary cards
        cards_row = tk.Frame(outer, bg=C["bg"])
        cards_row.pack(fill=tk.X, pady=(0, 20))

        self._card_vars: Dict[str, tk.StringVar] = {}
        defs = [
            ("total_detections", "Total Detections", C["accent"]),
            ("malicious_count",  "Malicious",        C["malicious"]),
            ("suspicious_count", "Suspicious",       C["suspicious"]),
            ("actioned_count",   "Actioned",         C["safe"]),
        ]
        for key, label, colour in defs:
            var = tk.StringVar(value="0")
            self._card_vars[key] = var
            card = tk.Frame(cards_row, bg=C["surface"], padx=18, pady=14)
            card.pack(side=tk.LEFT, padx=8)
            tk.Label(card, textvariable=var, bg=C["surface"],
                     fg=colour, font=("Segoe UI", 28, "bold")).pack()
            tk.Label(card, text=label, bg=C["surface"],
                     fg=C["text_dim"], font=("Segoe UI", 9)).pack()

        # Action breakdown
        tk.Label(outer, text="Actions Taken", bg=C["bg"],
                 fg=C["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 4))
        self._action_text = tk.Text(outer, height=5, bg=C["surface"],
                                    fg=C["text"], relief=tk.FLAT,
                                    font=("Segoe UI", 9), state=tk.DISABLED)
        self._action_text.pack(fill=tk.X)

        # Model status
        tk.Label(outer, text="Detection Engine", bg=C["bg"],
                 fg=C["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(16, 4))
        self._model_var = tk.StringVar(value="Initialising…")
        tk.Label(outer, textvariable=self._model_var,
                 bg=C["bg"], fg=C["accent"],
                 font=("Segoe UI", 9)).pack(anchor="w")

        tk.Button(outer, text="Refresh Stats", command=self.refresh,
                  bg=C["btn_bg"], fg=C["text"], relief=tk.FLAT,
                  padx=12, pady=4,
                  font=("Segoe UI", 9),
                  cursor="hand2").pack(anchor="w", pady=(16, 0))

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
    ) -> None:
        self._am   = alert_manager
        self._db   = db_logger
        self._get_model_status = get_model_status
        self._on_pause = on_pause or (lambda _p: None)
        self._on_quit  = on_quit  or (lambda: None)

        self._root: Optional[tk.Tk] = None
        self._tray: Optional[_SystemTray] = None
        self._q: queue.Queue = queue.Queue()

        # Tabs (set after build)
        self._live_tab:    Optional[_LiveAlertsTab] = None
        self._history_tab: Optional[_HistoryTab]    = None
        self._stats_tab:   Optional[_StatsTab]      = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build window and enter mainloop (blocks)."""
        self._root = self._build_root()
        self._apply_styles()

        nb = ttk.Notebook(self._root, style="TNotebook")

        self._live_tab    = _LiveAlertsTab(nb, self._am, self._db)
        self._history_tab = _HistoryTab(nb, self._db)
        self._stats_tab   = _StatsTab(nb, self._db, self._get_model_status)

        nb.add(self._live_tab,    text="  🚨 Live Alerts  ")
        nb.add(self._history_tab, text="  📋 History  ")
        nb.add(self._stats_tab,   text="  📊 Statistics  ")
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Status bar
        self._status_var = tk.StringVar(value="Monitoring active…")
        tk.Label(
            self._root, textvariable=self._status_var,
            bg=C["surface"], fg=C["text_dim"],
            font=("Segoe UI", 8), anchor="w", padx=10, pady=3,
        ).pack(fill=tk.X, side=tk.BOTTOM)

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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_root(self) -> tk.Tk:
        root = tk.Tk()
        root.title("AI Keylogger Detection System")
        root.geometry("980x640")
        root.minsize(780, 500)
        root.configure(bg=C["bg"])
        try:
            img = _tray_image()
            if img:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(img)
                root.iconphoto(True, photo)
        except Exception:
            pass
        return root

    def _apply_styles(self) -> None:
        style = ttk.Style(self._root)
        style.theme_use("clam")

        style.configure("Dark.TFrame",       background=C["bg"])
        style.configure("TNotebook",         background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",     background=C["surface"],
                        foreground=C["text"], padding=(10, 5),
                        font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", C["border"])],
                  foreground=[("selected", C["accent"])])
        style.configure("Dark.Treeview",
                        background=C["surface"], foreground=C["text"],
                        fieldbackground=C["surface"], rowheight=22,
                        font=("Segoe UI", 9))
        style.configure("Dark.Treeview.Heading",
                        background=C["border"], foreground=C["accent"],
                        font=("Segoe UI", 9, "bold"))
        style.map("Dark.Treeview",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", C["bg"])])

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
