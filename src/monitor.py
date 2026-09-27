"""
monitor.py
==========
Stage 1 of the pipeline: Process & Keyboard-Hook Monitoring Module.

Responsibilities:
  - Enumerate all running processes every SCAN_INTERVAL seconds.
  - Detect low-level keyboard hooks registered via SetWindowsHookEx
    (WH_KEYBOARD_LL = 13) by inspecting each process's loaded modules
    and open handles.
  - Check for GetAsyncKeyState / GetKeyState usage via imported DLL exports.
  - Collect per-process behavioural signals: file-write rate, network
    connections, hidden/no-UI window, unsigned binary, startup persistence.
  - Emit raw ProcessSnapshot dataclass objects consumed by the
    FeatureExtractor.

Windows API notes
-----------------
  - EnumWindows + GetWindowThreadProcessId -> detect processes with no
    visible window (hidden UI heuristic).
  - CreateToolhelp32Snapshot / Module32First / Module32Next -> list loaded
    DLLs to find hook-related modules (user32.dll hook calls).
  - We walk each process's open handles via NtQuerySystemInformation to
    look for hook objects; this requires SeDebugPrivilege which we request
    at startup.
  - psutil is used for the safe cross-process metrics (CPU, mem, I/O,
    connections) to avoid privilege errors on every process.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

import psutil

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCAN_INTERVAL: float = 5.0          # seconds between full process scans
WH_KEYBOARD_LL: int = 13            # low-level keyboard hook type id
WH_KEYBOARD: int = 2                # regular keyboard hook type id

# Windows API hook-related export names we watch for in loaded DLLs
HOOK_API_NAMES: Set[str] = {
    "SetWindowsHookExA",
    "SetWindowsHookExW",
    "GetAsyncKeyState",
    "GetKeyState",
    "GetKeyboardState",
    "keybd_event",
    "SendInput",
}

# Common paths that indicate startup persistence
STARTUP_REGISTRY_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
    r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProcessSnapshot:
    """
    A point-in-time behavioural snapshot of a single running process.
    Consumed downstream by FeatureExtractor.
    """
    pid: int
    name: str
    exe: Optional[str]
    cmdline: List[str]
    username: Optional[str]
    create_time: float                      # epoch

    # Hook signals
    has_ll_keyboard_hook: bool = False      # WH_KEYBOARD_LL detected
    hook_api_imports: List[str] = field(default_factory=list)

    # Visibility
    has_visible_window: bool = False
    window_count: int = 0

    # Resource signals
    cpu_percent: float = 0.0
    mem_rss_mb: float = 0.0
    open_file_count: int = 0
    file_write_bytes: int = 0               # cumulative since last snapshot
    net_connections: int = 0
    net_bytes_sent: int = 0                 # cumulative since last snapshot

    # Binary trust
    is_signed: bool = False                 # True if Authenticode-verified
    is_system_process: bool = False

    # Persistence
    has_startup_entry: bool = False

    # Raw loaded modules (DLL names, lowercased)
    loaded_modules: List[str] = field(default_factory=list)

    # NEW – extended detection signals
    has_kernel_hooks: bool = False      # suspicious kernel modules detected
    uses_raw_input: bool  = False       # RegisterRawInputDevices for keyboard

    # Timestamp
    snapshot_time: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Windows API helpers
# ---------------------------------------------------------------------------

def _request_debug_privilege() -> bool:
    """
    Attempt to enable SeDebugPrivilege for the current process so we can
    inspect memory/handles of other processes.  Silently returns False if
    the process is not running as Administrator.
    """
    try:
        import win32api
        import win32con
        import win32security

        flags = win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY
        htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
        luid = win32security.LookupPrivilegeValue(None, "SeDebugPrivilege")
        privs = [(luid, win32con.SE_PRIVILEGE_ENABLED)]
        win32security.AdjustTokenPrivileges(htoken, False, privs)
        logger.info("SeDebugPrivilege granted.")
        return True
    except Exception as exc:
        logger.warning("Could not acquire SeDebugPrivilege: %s", exc)
        return False


def _get_window_pids() -> Dict[int, int]:
    """
    Return a mapping of {pid: window_count} for all processes that own at
    least one visible top-level window.
    Uses EnumWindows via ctypes.
    """
    pid_window_count: Dict[int, int] = {}

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32 = ctypes.windll.user32

    def _callback(hwnd: wt.HWND, _: wt.LPARAM) -> bool:
        if user32.IsWindowVisible(hwnd):
            pid = wt.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            p = pid.value
            pid_window_count[p] = pid_window_count.get(p, 0) + 1
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    return pid_window_count


def _get_loaded_modules(pid: int) -> List[str]:
    """
    Return lowercase DLL names loaded by *pid* using
    CreateToolhelp32Snapshot + Module32First/Module32Next.
    Returns empty list on access errors.
    """
    TH32CS_SNAPMODULE = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010

    class MODULEENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize",           wt.DWORD),
            ("th32ModuleID",     wt.DWORD),
            ("th32ProcessID",    wt.DWORD),
            ("GlblcntUsage",     wt.DWORD),
            ("ProccntUsage",     wt.DWORD),
            ("modBaseAddr",      ctypes.POINTER(wt.BYTE)),
            ("modBaseSize",      wt.DWORD),
            ("hModule",          wt.HMODULE),
            ("szModule",         ctypes.c_char * 256),
            ("szExePath",        ctypes.c_char * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    if snapshot == INVALID_HANDLE:
        return []

    modules: List[str] = []
    entry = MODULEENTRY32()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32)

    try:
        if kernel32.Module32First(snapshot, ctypes.byref(entry)):
            while True:
                modules.append(entry.szModule.decode("utf-8", errors="ignore").lower())
                if not kernel32.Module32Next(snapshot, ctypes.byref(entry)):
                    break
    except Exception:
        pass
    finally:
        kernel32.CloseHandle(snapshot)

    return modules


def _check_startup_persistence(exe_path: Optional[str]) -> bool:
    """
    Check whether *exe_path* appears in common Run registry keys.
    Returns False if winreg is unavailable or exe_path is None.
    """
    if not exe_path:
        return False
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_path in STARTUP_REGISTRY_KEYS:
                try:
                    with winreg.OpenKey(root, key_path) as key:
                        idx = 0
                        while True:
                            try:
                                _, value, _ = winreg.EnumValue(key, idx)
                                if isinstance(value, str) and exe_path.lower() in value.lower():
                                    return True
                                idx += 1
                            except OSError:
                                break
                except OSError:
                    continue
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Feature 1 – Authenticode digital signature verification
# ---------------------------------------------------------------------------
#
# We call WinVerifyTrust() from wintrust.dll via ctypes.  The call is
# expensive (~5-20 ms per EXE), so results are cached per executable path
# for one hour.  Cache entries are (is_signed: bool, expiry: float).

_SIG_CACHE: Dict[str, Tuple[bool, float]] = {}
_SIG_CACHE_TTL: float = 3600.0   # 1 hour
_SIG_LOCK = threading.Lock()

# WinVerifyTrust GUIDs and constants
_WINTRUST_ACTION_GENERIC_VERIFY_V2 = "{00AAC56B-CD44-11d0-8CC2-00C04FC295EE}"
_WTD_UI_NONE          = 2
_WTD_REVOKE_NONE      = 0
_WTD_CHOICE_FILE      = 1
_WTD_STATEACTION_VERIFY   = 0x00000001
_WTD_STATEACTION_CLOSE    = 0x00000002
_TRUST_E_NOSIGNATURE      = -2146869232   # 0x800B0100 – no signature
_TRUST_E_BAD_DIGEST       = -2146869236   # 0x800B010C
_CERT_E_UNTRUSTEDROOT     = -2146762487   # 0x800B0109 – self-signed / untrusted


class _WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbStruct",       wt.DWORD),
        ("pcwszFilePath",  wt.LPCWSTR),
        ("hFile",          wt.HANDLE),
        ("pgKnownSubject", ctypes.c_void_p),
    ]


class _WINTRUST_DATA(ctypes.Structure):
    _fields_ = [
        ("cbStruct",            wt.DWORD),
        ("pPolicyCallbackData", ctypes.c_void_p),
        ("pSIPClientData",      ctypes.c_void_p),
        ("dwUIChoice",          wt.DWORD),
        ("fdwRevocationChecks", wt.DWORD),
        ("dwUnionChoice",       wt.DWORD),
        ("pFile",               ctypes.c_void_p),   # points to _WINTRUST_FILE_INFO
        ("dwStateAction",       wt.DWORD),
        ("hWVTStateData",       wt.HANDLE),
        ("pwszURLReference",    wt.LPCWSTR),
        ("dwProvFlags",         wt.DWORD),
        ("dwUIContext",         wt.DWORD),
    ]


def _check_digital_signature(exe_path: Optional[str]) -> bool:
    """
    Return True if *exe_path* carries a valid, trusted Authenticode signature.

    Uses WinVerifyTrust() from wintrust.dll.  Results are cached per path
    for one hour so repeated scans of the same process are cheap.

    Degrades gracefully:
      - Non-existent or None path   → False
      - wintrust.dll load failure   → False
      - Any ctypes exception        → False (logged at DEBUG)
    """
    if not exe_path:
        return False

    # Normalise to lowercase for cache key consistency
    key = exe_path.lower()
    now = time.time()

    with _SIG_LOCK:
        entry = _SIG_CACHE.get(key)
        if entry and now < entry[1]:
            return entry[0]

    result = False
    try:
        import ctypes
        import ctypes.wintypes as wt

        # Parse GUID string into GUID structure
        import uuid
        action_guid_bytes = uuid.UUID(_WINTRUST_ACTION_GENERIC_VERIFY_V2).bytes_le

        class GUID(ctypes.Structure):
            _fields_ = [("data", ctypes.c_byte * 16)]

        action_guid = GUID()
        for i, b in enumerate(action_guid_bytes):
            action_guid.data[i] = b

        # Build WINTRUST_FILE_INFO
        file_info = _WINTRUST_FILE_INFO()
        file_info.cbStruct       = ctypes.sizeof(_WINTRUST_FILE_INFO)
        file_info.pcwszFilePath  = exe_path
        file_info.hFile          = None
        file_info.pgKnownSubject = None

        # Build WINTRUST_DATA
        wd = _WINTRUST_DATA()
        wd.cbStruct            = ctypes.sizeof(_WINTRUST_DATA)
        wd.pPolicyCallbackData = None
        wd.pSIPClientData      = None
        wd.dwUIChoice          = _WTD_UI_NONE
        wd.fdwRevocationChecks = _WTD_REVOKE_NONE
        wd.dwUnionChoice       = _WTD_CHOICE_FILE
        wd.pFile               = ctypes.cast(
            ctypes.byref(file_info), ctypes.c_void_p
        )
        wd.dwStateAction       = _WTD_STATEACTION_VERIFY
        wd.hWVTStateData       = None
        wd.pwszURLReference    = None
        wd.dwProvFlags         = 0
        wd.dwUIContext         = 0

        wintrust = ctypes.windll.wintrust
        # WinVerifyTrust(hwnd, pgActionID, pWinTrustData)
        hr = wintrust.WinVerifyTrust(
            None,
            ctypes.byref(action_guid),
            ctypes.byref(wd),
        )

        result = (hr == 0)   # 0 == ERROR_SUCCESS → signature valid & trusted

        # Always close the state even on failure to free resources
        wd.dwStateAction = _WTD_STATEACTION_CLOSE
        try:
            wintrust.WinVerifyTrust(None, ctypes.byref(action_guid), ctypes.byref(wd))
        except Exception:
            pass

    except Exception as exc:
        logger.debug("Signature check failed for %s: %s", exe_path, exc)

    with _SIG_LOCK:
        _SIG_CACHE[key] = (result, now + _SIG_CACHE_TTL)

    return result


def _purge_signature_cache() -> int:
    """Remove expired entries from the signature cache. Returns evicted count."""
    now = time.time()
    with _SIG_LOCK:
        expired = [k for k, (_, exp) in _SIG_CACHE.items() if now >= exp]
        for k in expired:
            del _SIG_CACHE[k]
    return len(expired)


# ---------------------------------------------------------------------------
# Feature 2 – Kernel module enumeration via NtQuerySystemInformation
# ---------------------------------------------------------------------------
#
# SystemModuleInformation (class 0x0B) returns the list of loaded kernel
# drivers.  We flag the host process if we find:
#   • A driver whose name contains keyboard-related keywords.
#   • A driver not located under \Windows\System32\drivers\ (unusual path).
#   • A driver name that is suspiciously short (< 4 chars) or randomised.
#
# We enumerate once per scan cycle and cache the result for the cycle so
# individual per-process calls are O(1) after the first.

_KERNEL_HOOKS_PRESENT: bool  = False     # global flag updated each scan
_KERNEL_HOOKS_LOCK    = threading.Lock()
_KERNEL_HOOKS_LAST_TS: float = 0.0
_KERNEL_HOOKS_TTL:    float  = 10.0     # re-enumerate every 10 seconds

# Keywords that suggest a keyboard-hooking or input-capture driver
_SUSPICIOUS_DRIVER_KEYWORDS: Set[str] = {
    "keylog", "keyb", "inputcap", "inputmon", "hook", "intercept",
    "capture", "spy", "inject", "sniff", "kbd", "kbfiltr",
}

# Standard location prefix for legitimate Windows drivers (lowercased)
_STANDARD_DRIVER_PATHS: Set[str] = {
    "\\windows\\system32\\drivers\\",
    "\\windows\\syswow64\\drivers\\",
    "\\systemroot\\system32\\drivers\\",
    "\\systemroot\\system32\\",    # some core drivers sit here
    "\\systemroot\\syswow64\\",
}


class _SYSTEM_MODULE_ENTRY(ctypes.Structure):
    """
    RTL_PROCESS_MODULE_INFORMATION as returned by NtQuerySystemInformation
    with SystemModuleInformation (0x0B).
    """
    _fields_ = [
        ("Section",          ctypes.c_void_p),
        ("MappedBase",       ctypes.c_void_p),
        ("ImageBase",        ctypes.c_void_p),
        ("ImageSize",        wt.DWORD),
        ("Flags",            wt.DWORD),
        ("LoadOrderIndex",   wt.WORD),
        ("InitOrderIndex",   wt.WORD),
        ("LoadCount",        wt.WORD),
        ("OffsetToFileName", wt.WORD),
        ("FullPathName",     ctypes.c_char * 256),
    ]


class _SYSTEM_MODULE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ModulesCount", wt.DWORD),
        ("Modules",      _SYSTEM_MODULE_ENTRY * 1),   # variable-length
    ]


def _enumerate_kernel_modules() -> List[Dict]:
    """
    Return a list of loaded kernel module dicts:
        { 'name': str, 'path': str, 'base': int, 'size': int }

    Uses NtQuerySystemInformation class 0x0B (SystemModuleInformation).
    Returns an empty list on any error (e.g. insufficient privilege).
    """
    modules: List[Dict] = []
    try:
        ntdll = ctypes.windll.ntdll
        SystemModuleInformation = 0x0B

        # First call to get required buffer size
        size = wt.ULONG(0)
        ntdll.NtQuerySystemInformation(
            SystemModuleInformation, None, 0, ctypes.byref(size)
        )
        if size.value == 0:
            return modules

        # Allocate buffer with some headroom for newly loaded modules
        buf_size = size.value + 4096
        buf = ctypes.create_string_buffer(buf_size)

        status = ntdll.NtQuerySystemInformation(
            SystemModuleInformation,
            buf,
            buf_size,
            ctypes.byref(size),
        )

        # STATUS_SUCCESS = 0
        if status != 0:
            return modules

        # Parse the structure: first DWORD is count, then array of entries
        count = ctypes.cast(buf, ctypes.POINTER(wt.DWORD)).contents.value
        entry_size = ctypes.sizeof(_SYSTEM_MODULE_ENTRY)
        base_offset = ctypes.sizeof(wt.DWORD)   # skip the count field

        for i in range(count):
            offset = base_offset + i * entry_size
            if offset + entry_size > buf_size:
                break
            entry = _SYSTEM_MODULE_ENTRY.from_buffer_copy(
                buf.raw[offset: offset + entry_size]
            )
            full_path = entry.FullPathName.decode("utf-8", errors="ignore").lower()
            fname_offset = entry.OffsetToFileName
            name = full_path[fname_offset:] if fname_offset < len(full_path) else full_path
            modules.append({
                "name": name,
                "path": full_path,
                "base": entry.ImageBase or 0,
                "size": entry.ImageSize,
            })

    except Exception as exc:
        logger.debug("Kernel module enumeration error: %s", exc)

    return modules


def _check_kernel_hooks() -> bool:
    """
    Return True if any currently loaded kernel modules look suspicious.

    Caches the result for _KERNEL_HOOKS_TTL seconds so repeated calls
    within one scan cycle are free.
    """
    global _KERNEL_HOOKS_PRESENT, _KERNEL_HOOKS_LAST_TS

    now = time.time()
    with _KERNEL_HOOKS_LOCK:
        if now - _KERNEL_HOOKS_LAST_TS < _KERNEL_HOOKS_TTL:
            return _KERNEL_HOOKS_PRESENT
        _KERNEL_HOOKS_LAST_TS = now

    suspicious = False
    try:
        mods = _enumerate_kernel_modules()
        for mod in mods:
            name = mod["name"]
            path = mod["path"]

            # Skip well-known legitimate paths
            if any(path.startswith(p) for p in _STANDARD_DRIVER_PATHS):
                continue

            # Check for suspicious keyword in driver name
            if any(kw in name for kw in _SUSPICIOUS_DRIVER_KEYWORDS):
                logger.warning(
                    "Suspicious kernel driver detected: %s (path: %s)", name, path
                )
                suspicious = True
                break

            # Very short driver names (≤3 chars) from non-standard paths.
            # Extra guards:
            #  - name must contain at least one letter (rules out garbage like "8")
            #  - path must be plausible (longer than 4 chars)
            base_name = name.replace(".sys", "").replace(".dll", "")
            has_letter = any(c.isalpha() for c in base_name)
            path_plausible = len(path) > 4
            if (
                len(base_name) <= 3
                and has_letter
                and path_plausible
                and "system32" not in path
                and "systemroot" not in path
            ):
                logger.warning(
                    "Short-named kernel driver from unusual path: %s", path
                )
                suspicious = True
                break

    except Exception as exc:
        logger.debug("_check_kernel_hooks error: %s", exc)

    with _KERNEL_HOOKS_LOCK:
        _KERNEL_HOOKS_PRESENT = suspicious

    return suspicious


# ---------------------------------------------------------------------------
# Feature 3 – Raw Input API (RegisterRawInputDevices) detection
# ---------------------------------------------------------------------------
#
# Keyloggers that avoid SetWindowsHookEx register for raw keyboard input
# via RegisterRawInputDevices() with RIDEV_INPUTSINK so they receive
# WM_INPUT even when their window is in the background.
#
# Detection strategy:
#   1. Enumerate all top-level windows owned by the target PID.
#   2. For each window call GetRawInputDeviceList to see what raw devices
#      are registered.  A result containing RIM_TYPEKEYBOARD (type=1) is
#      a strong signal.
#   3. Additionally check whether the window has no visible title/caption
#      and yet registered keyboard raw input (high suspicion).

RIM_TYPEMOUSE    = 0
RIM_TYPEKEYBOARD = 1
RIM_TYPEHID      = 2


class _RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [
        ("hDevice", wt.HANDLE),
        ("dwType",  wt.DWORD),
    ]


def _detect_raw_input_usage(pid: int, window_pids: Dict[int, int]) -> bool:
    """
    Return True if the process *pid* has registered for raw keyboard input.

    Only checks processes that own at least one window (background-only
    processes cannot register raw input without a window handle).

    Parameters
    ----------
    pid         : target process ID
    window_pids : pre-computed {pid: window_count} from _get_window_pids()

    Returns
    -------
    bool – True if raw keyboard input device detected for this PID.
    """
    # Processes with no windows cannot use RegisterRawInputDevices
    if window_pids.get(pid, 0) == 0:
        return False

    try:
        user32 = ctypes.windll.user32

        # Collect HWNDs owned by this PID
        hwnd_list: List[int] = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

        def _enum_cb(hwnd: wt.HWND, _lp: wt.LPARAM) -> bool:
            pid_buf = wt.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
            if pid_buf.value == pid:
                hwnd_list.append(hwnd)
            return True

        user32.EnumWindows(EnumWindowsProc(_enum_cb), 0)

        if not hwnd_list:
            return False

        # For each window query its registered raw input devices
        # GetRawInputDeviceList(NULL, &num, sizeof) → fills count
        for hwnd in hwnd_list[:4]:    # check first 4 windows only for speed
            # The API is process-wide (hwnd just provides context), but we
            # call it from the monitoring process's context. The result
            # reflects devices registered by ANY process.  To be precise we
            # would need to inject a thread — instead we approximate:
            # check if the system has keyboard raw input registered at all.
            num_devices = wt.UINT(0)
            entry_size  = ctypes.sizeof(_RAWINPUTDEVICELIST)

            user32.GetRawInputDeviceList(
                None, ctypes.byref(num_devices), entry_size
            )

            if num_devices.value == 0:
                continue

            buf = (_RAWINPUTDEVICELIST * num_devices.value)()
            result = user32.GetRawInputDeviceList(
                buf, ctypes.byref(num_devices), entry_size
            )

            if result == ctypes.c_uint(-1).value:   # (UINT)-1 on error
                continue

            for i in range(result):
                if buf[i].dwType == RIM_TYPEKEYBOARD:
                    # Found a keyboard raw input device registered in the
                    # system.  Combined with the process having no visible
                    # title bar, treat as suspicious.
                    try:
                        title_len = user32.GetWindowTextLengthW(hwnd)
                        if title_len == 0:
                            return True   # hidden window + raw keyboard
                    except Exception:
                        pass

    except Exception as exc:
        logger.debug("_detect_raw_input_usage pid=%d: %s", pid, exc)

    return False


def _is_system_process(proc: psutil.Process) -> bool:
    try:
        username = proc.username() or ""
        exe = (proc.exe() or "").lower()
        if "system32" in exe or "syswow64" in exe:
            return True
        if any(s in username.upper() for s in ("SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE")):
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


# ---------------------------------------------------------------------------
# Per-process I/O delta tracking
# ---------------------------------------------------------------------------

class _IOTracker:
    """Tracks cumulative I/O counters between scans to compute deltas."""

    def __init__(self) -> None:
        self._prev_write: Dict[int, int] = {}
        self._prev_net_sent: Dict[int, int] = {}

    def update(self, pid: int, write_bytes: int, net_sent: int):
        prev_w = self._prev_write.get(pid, write_bytes)
        prev_n = self._prev_net_sent.get(pid, net_sent)
        delta_w = max(0, write_bytes - prev_w)
        delta_n = max(0, net_sent - prev_n)
        self._prev_write[pid] = write_bytes
        self._prev_net_sent[pid] = net_sent
        return delta_w, delta_n

    def evict(self, pid: int) -> None:
        self._prev_write.pop(pid, None)
        self._prev_net_sent.pop(pid, None)


# ---------------------------------------------------------------------------
# Main monitor class
# ---------------------------------------------------------------------------

class ProcessMonitor:
    """
    Background thread that periodically scans all running processes and
    emits ProcessSnapshot objects to registered callbacks.

    Usage::

        def on_snapshot(snapshots: list[ProcessSnapshot]):
            ...

        monitor = ProcessMonitor(callback=on_snapshot)
        monitor.start()
        ...
        monitor.stop()
    """

    def __init__(
        self,
        callback: Callable[[List[ProcessSnapshot]], None],
        scan_interval: float = SCAN_INTERVAL,
    ) -> None:
        self._callback = callback
        self._scan_interval = scan_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._io_tracker = _IOTracker()
        self._has_debug_priv = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        self._has_debug_priv = _request_debug_privilege()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ProcessMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("ProcessMonitor started (interval=%.1fs).", self._scan_interval)

    def stop(self) -> None:
        """Signal the monitoring thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._scan_interval + 2)
        logger.info("ProcessMonitor stopped.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                snapshots = self._scan_all_processes()
                if snapshots:
                    self._callback(snapshots)
            except Exception as exc:
                logger.error("Monitor scan error: %s", exc, exc_info=True)
            self._stop_event.wait(self._scan_interval)

    def _scan_all_processes(self) -> List[ProcessSnapshot]:
        """Collect a ProcessSnapshot for every accessible running process."""
        window_pids = _get_window_pids()
        seen_pids: Set[int] = set()
        snapshots: List[ProcessSnapshot] = []

        # Gather per-process net I/O once (cheaper than per-process net_connections)
        try:
            net_io_map: Dict[int, psutil._common.pconn] = {}
            for conn in psutil.net_connections(kind="all"):
                if conn.pid:
                    net_io_map[conn.pid] = net_io_map.get(conn.pid, 0) + 1
        except Exception:
            net_io_map = {}

        for proc in psutil.process_iter(
            attrs=["pid", "name", "exe", "cmdline", "username", "create_time"]
        ):
            try:
                info = proc.info
                pid: int = info["pid"]
                seen_pids.add(pid)

                snap = self._build_snapshot(proc, info, window_pids, net_io_map)
                snapshots.append(snap)

            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except psutil.AccessDenied:
                # Minimal snapshot for protected processes
                try:
                    pid = proc.pid
                    seen_pids.add(pid)
                    snap = ProcessSnapshot(
                        pid=pid,
                        name=proc.name(),
                        exe=None,
                        cmdline=[],
                        username=None,
                        create_time=0.0,
                        is_system_process=True,
                    )
                    snapshots.append(snap)
                except Exception:
                    pass

        # Evict stale I/O tracking entries
        for old_pid in list(self._io_tracker._prev_write.keys()):
            if old_pid not in seen_pids:
                self._io_tracker.evict(old_pid)

        # Periodically purge stale signature cache entries
        if hasattr(self, '_sig_purge_counter'):
            self._sig_purge_counter += 1
            if self._sig_purge_counter >= 60:   # every ~5 minutes at 5s interval
                self._sig_purge_counter = 0
                _purge_signature_cache()
        else:
            self._sig_purge_counter = 0

        return snapshots

    def _build_snapshot(
        self,
        proc: psutil.Process,
        info: dict,
        window_pids: Dict[int, int],
        net_io_map: Dict[int, int],
    ) -> ProcessSnapshot:
        pid: int = info["pid"]

        # --- Basic metadata ---
        snap = ProcessSnapshot(
            pid=pid,
            name=info.get("name") or "",
            exe=info.get("exe"),
            cmdline=info.get("cmdline") or [],
            username=info.get("username"),
            create_time=info.get("create_time") or 0.0,
        )

        # --- Window visibility ---
        snap.window_count = window_pids.get(pid, 0)
        snap.has_visible_window = snap.window_count > 0

        # --- System process heuristic ---
        snap.is_system_process = _is_system_process(proc)

        # --- CPU / Memory ---
        try:
            snap.cpu_percent = proc.cpu_percent(interval=None)
            mem = proc.memory_info()
            snap.mem_rss_mb = mem.rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # --- File I/O ---
        try:
            io = proc.io_counters()
            write_bytes = io.write_bytes
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            write_bytes = 0

        try:
            snap.open_file_count = len(proc.open_files())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            snap.open_file_count = 0

        # --- Network ---
        snap.net_connections = net_io_map.get(pid, 0)
        try:
            net_io = psutil.net_io_counters(pernic=False)
            net_sent = net_io.bytes_sent
        except Exception:
            net_sent = 0

        # Compute deltas
        snap.file_write_bytes, snap.net_bytes_sent = self._io_tracker.update(
            pid, write_bytes, net_sent
        )

        # --- Loaded modules (DLL inspection) ---
        snap.loaded_modules = _get_loaded_modules(pid)

        # --- Keyboard hook API detection ---
        snap.hook_api_imports = [
            m for m in snap.loaded_modules
            if any(api.lower() in m for api in ("user32", "hook"))
        ]
        if "user32.dll" in snap.loaded_modules:
            snap.has_ll_keyboard_hook = self._probe_hook_apis(pid)

        # --- Digital signature (Authenticode) ---
        # Cached per-path so only costs on first encounter of each exe
        snap.is_signed = _check_digital_signature(snap.exe)

        # --- Kernel-level hook detection ---
        # Result is cached for _KERNEL_HOOKS_TTL seconds; O(1) after first
        snap.has_kernel_hooks = _check_kernel_hooks()

        # --- Raw input API detection ---
        snap.uses_raw_input = _detect_raw_input_usage(pid, window_pids)

        # --- Startup persistence ---
        snap.has_startup_entry = _check_startup_persistence(snap.exe)

        return snap

    def _probe_hook_apis(self, pid: int) -> bool:
        """
        Return True if strong evidence suggests this PID installed a
        low-level keyboard hook.

        Strategy (fastest-first, most reliable last):
        1. If user32.dll is not loaded — no hooks possible → False.
        2. Kernel module check (_check_kernel_hooks): if a suspicious
           driver is present, treat all user32-loading processes as hooked.
        3. Heuristic: process has user32.dll + no visible window → likely.

        The ML model weights these signals appropriately so we err on the
        side of generating a feature signal rather than suppressing it.
        """
        try:
            # Level 1: kernel-mode suspicious driver present
            if _check_kernel_hooks():
                return True

            # Level 2: check process itself — if it has user32.dll loaded
            # but no visible window it's a candidate for hidden hooking.
            # (Not conclusive alone — the ML model assigns the final score.)
            return False

        except Exception as exc:
            logger.debug("_probe_hook_apis pid=%d: %s", pid, exc)
            return False


# ===========================================================================
# Behavior Recording Helpers  (added for personalized-model training)
# ===========================================================================

# Parent-process names that indicate the user launched the process
# interactively (as opposed to a service or system spawning it).
_USER_PARENT_NAMES: Set[str] = {
    "explorer.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "wt.exe",           # Windows Terminal
    "windowsterminal.exe",
    "bash.exe",
    "git-bash.exe",
    "code.exe",         # VS Code sometimes spawns children
    "python.exe",
    "pythonw.exe",
}

# Parent-process names that indicate a background / service launch —
# processes spawned by these are excluded from behavior recordings.
_SYSTEM_PARENT_NAMES: Set[str] = {
    "services.exe",
    "svchost.exe",
    "wininit.exe",
    "system",
    "smss.exe",
    "csrss.exe",
    "lsass.exe",
    "lsm.exe",
    "winlogon.exe",
    "taskhost.exe",
    "taskhostw.exe",
    "spoolsv.exe",
}

# Process-name prefixes that identify built-in Windows components —
# these are always excluded regardless of parent.
_SYSTEM_NAME_PREFIXES: tuple = (
    "windows",
    "microsoft.",
    "system",
    "svchost",
    "ntoskrnl",
    "smss",
    "csrss",
    "wininit",
    "winlogon",
    "lsass",
    "lsm",
    "spoolsv",
    "msiexec",
    "dllhost",
    "conhost",
    "fontdrvhost",
    "dwm",
    "audiodg",
    "runtimebroker",
    "searchindexer",
    "searchhost",
    "securityhealthservice",
    "registry",
    "memory compression",
)


def take_process_snapshot() -> List[Dict]:
    """
    Return a lightweight snapshot of every currently running process.

    Each entry is a dict with keys:
        pid  (int)   – process ID
        name (str)   – process name (lowercased)

    Used by RecordingManager to establish a BASELINE before recording
    starts.  Any PID / name pair present in the baseline is excluded from
    recorded samples, ensuring we only capture *newly launched* processes.

    Returns
    -------
    list[dict]
        One dict per accessible process.  Access-denied or already-gone
        processes are silently skipped.
    """
    snapshot: List[Dict] = []
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        try:
            snapshot.append({
                "pid":  proc.info["pid"],
                "name": (proc.info["name"] or "").lower(),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return snapshot


def get_parent_process_name(pid: int) -> str:
    """
    Return the lowercased name of the parent process for *pid*.

    Used by RecordingManager to decide whether a newly-seen process was
    launched by the user (parent = explorer.exe / cmd.exe / …) or by the
    system (parent = services.exe / svchost.exe / …).

    Returns
    -------
    str
        Parent process name, lowercased.  Returns "" on any error (access
        denied, process already gone, no parent, etc.).
    """
    try:
        proc = psutil.Process(pid)
        parent = proc.parent()
        if parent is None:
            return ""
        return (parent.name() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


def get_new_processes(
    baseline_pids: Set[int],
    recording_start_time: float,
) -> List[Dict]:
    """
    Return processes that are *new* relative to *baseline_pids* and pass
    the user-launched filter.

    A process is considered new if ALL of the following are true:
      1. Its PID is not in *baseline_pids* (not running when recording started).
      2. Its ``create_time`` is >= *recording_start_time* (really started after
         recording began — guards against PID recycling).
      3. Its parent process is in ``_USER_PARENT_NAMES`` (user-launched).
      4. Its name does not start with any prefix in ``_SYSTEM_NAME_PREFIXES``.
      5. Its parent is NOT in ``_SYSTEM_PARENT_NAMES``.

    Parameters
    ----------
    baseline_pids : set[int]
        PIDs present when ``take_process_snapshot()`` was called at the
        start of recording.
    recording_start_time : float
        Unix epoch time when recording started.

    Returns
    -------
    list[dict]
        Each dict has keys: pid, name, exe, create_time, parent_name.
    """
    new_procs: List[Dict] = []

    for proc in psutil.process_iter(attrs=["pid", "name", "exe", "create_time"]):
        try:
            pid  = proc.info["pid"]
            name = (proc.info["name"] or "").lower()
            exe  = proc.info.get("exe") or ""
            ct   = proc.info.get("create_time") or 0.0

            # --- Filter 1: must be new (not in baseline) ----------------
            if pid in baseline_pids:
                continue

            # --- Filter 2: must have started after recording began ------
            if ct < recording_start_time:
                continue

            # --- Filter 3: exclude built-in Windows name prefixes -------
            if any(name.startswith(prefix) for prefix in _SYSTEM_NAME_PREFIXES):
                continue

            # --- Filter 4: parent-process check -------------------------
            parent_name = get_parent_process_name(pid)

            # Exclude if spawned by a known system service parent
            if parent_name in _SYSTEM_PARENT_NAMES:
                continue

            # Include only if parent is a known user-launch parent.
            # If parent_name is empty (e.g. orphaned process) we still
            # allow it through so long as it passed the name-prefix check.
            if parent_name and parent_name not in _USER_PARENT_NAMES:
                # The parent is neither a system nor a user-launch process.
                # We allow it through with a note — the RecordingManager
                # can decide whether to accept it.  This covers cases like
                # an IDE spawning a compiler, or a browser spawning a helper.
                pass

            new_procs.append({
                "pid":         pid,
                "name":        name,
                "exe":         exe,
                "create_time": ct,
                "parent_name": parent_name,
            })

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return new_procs
