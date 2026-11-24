"""Operating-system integration: DPI, native window chrome, monitors, single instance,
start-at-login and logging. Windows gets the full treatment; macOS and Linux get
equivalents where they exist and quiet no-ops where they don't.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

# Fixed programs only; never invoked through a shell.
import subprocess  # nosec B404
import sys
from urllib.parse import urlsplit
import webbrowser

from . import APP_NAME
from .storage import data_dir

log = logging.getLogger('econpulse')


def native_titlebar(win, palette, is_dark):
    """Dark/coloured title bar on Windows 10 (dark mode) and 11 (caption colour)."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes

        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        dwm = ctypes.windll.dwmapi
        flag = ctypes.c_int(1 if is_dark else 0)
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(flag), ctypes.sizeof(flag)) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(flag), ctypes.sizeof(flag))

        def colorref(hex_colour):
            r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
            return ctypes.c_int(r | g << 8 | b << 16)

        for attribute, colour in ((35, palette['side']), (36, palette['text']), (34, palette['line_strong'])):
            value = colorref(colour)  # caption, text, border (Windows 11 only; ignored elsewhere)
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def native_round(win, border='', small=False) -> bool:
    """Windows 11 rounded corners + hairline border for a borderless window.

    Returns False where unsupported (Windows 10, Linux) so callers can draw
    their own 1px frame instead.
    """
    if sys.platform != 'win32':
        return False
    try:
        import ctypes

        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        pref = ctypes.c_int(3 if small else 2)
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4) != 0:
            return False
        if border:
            r, g, b = (int(border[i : i + 2], 16) for i in (1, 3, 5))
            colour = ctypes.c_int(r | g << 8 | b << 16)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(colour), 4)
        return True
    except Exception:
        return False


def setup_logging():
    try:
        path = data_dir() / 'econpulse.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=256_000, backupCount=1, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    except OSError:
        pass


_instance_mutex = None


def acquire_single_instance(name='Local\\EconPulse.SingleInstance') -> bool:
    """Prevent a second copy (e.g. Startup + manual launch) from creating a
    duplicate tray icon and double-firing every alert."""
    global _instance_mutex
    if sys.platform != 'win32':
        return _acquire_lock_file()
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        handle = kernel32.CreateMutexW(None, False, name)
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            return False
        _instance_mutex = handle  # keep alive for the process lifetime
    except Exception:
        pass
    return True


def _acquire_lock_file() -> bool:
    """macOS/Linux: an advisory lock held for the process lifetime."""
    global _instance_mutex
    try:
        import fcntl

        path = data_dir() / 'instance.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, 'a+')  # noqa: SIM115 - must stay open while the app runs
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        _instance_mutex = handle
    except (ImportError, OSError):
        pass
    return True


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------
def workarea(root):
    """(left, top, right, bottom) of the primary screen minus the taskbar."""
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
    return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())


def all_workareas(root):
    """Work areas of every monitor (Windows); the primary screen elsewhere."""
    if sys.platform != 'win32':
        return [workarea(root)]
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT),
                ('dwFlags', wintypes.DWORD),
            ]

        areas = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
        )

        def callback(hmon, _hdc, _rect, _data):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcWork
                areas.append((r.left, r.top, r.right, r.bottom))
            return True

        ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_type(callback), 0)
        return areas or [workarea(root)]
    except Exception:
        return [workarea(root)]


# --------------------------------------------------------------------------
# Start at login (Windows Run key, Linux XDG autostart, macOS LaunchAgent)
# --------------------------------------------------------------------------
_RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
_LAUNCH_AGENT = 'io.github.econpulse'


def startup_supported() -> bool:
    return sys.platform in ('win32', 'darwin') or sys.platform.startswith('linux')


def startup_args() -> list[str]:
    """How to start this copy of EconPulse straight into the widget."""
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--widget']
    interpreter = Path(sys.executable)
    if sys.platform == 'win32' and interpreter.with_name('pythonw.exe').exists():
        interpreter = interpreter.with_name('pythonw.exe')
    launcher = Path(__file__).resolve().parent.parent / 'main.py'
    if launcher.exists():  # source checkout
        return [str(interpreter), str(launcher), '--widget']
    return [str(interpreter), '-m', 'econpulse', '--widget']  # installed package


def startup_command() -> str:
    return subprocess.list2cmdline(startup_args())


def autostart_file() -> Path:
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'LaunchAgents' / f'{_LAUNCH_AGENT}.plist'
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'autostart' / 'econpulse.desktop'


def desktop_entry(args) -> str:
    """XDG .desktop file text; Exec arguments quoted per the Desktop Entry spec."""

    def quote(arg):
        if any(ch in arg for ch in ' \t"\'\\$`'):
            escaped = arg.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
            return f'"{escaped}"'
        return arg

    return (
        '[Desktop Entry]\nType=Application\nName=EconPulse\nComment=Economic calendar widget\n'
        f'Exec={" ".join(quote(a) for a in args)}\nX-GNOME-Autostart-enabled=true\nTerminal=false\n'
    )


def launch_agent(args) -> bytes:
    import plistlib

    return plistlib.dumps({'Label': _LAUNCH_AGENT, 'ProgramArguments': list(args), 'RunAtLoad': True})


def get_startup() -> bool:
    if sys.platform == 'win32':
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                return bool(winreg.QueryValueEx(key, APP_NAME)[0])
        except OSError:
            return False
    return startup_supported() and autostart_file().exists()


def set_startup(enabled: bool) -> None:
    if not startup_supported():
        raise RuntimeError('Starting at login is not supported on this system')
    if sys.platform == 'win32':
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return
    path = autostart_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'darwin':
            path.write_bytes(launch_agent(startup_args()))
        else:
            path.write_text(desktop_entry(startup_args()), encoding='utf-8')
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def repair_startup() -> bool:
    """Point an existing Windows Startup entry at this executable if the app
    folder was moved. Only the packaged app does this; a source checkout never
    takes over the entry. Returns True when the entry was rewritten."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
        ) as key:
            current = winreg.QueryValueEx(key, APP_NAME)[0]
            wanted = startup_command()
            if not current or current == wanted:
                return False
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, wanted)
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# Small conveniences
# --------------------------------------------------------------------------
def play_alert_sound(widget) -> None:
    if is_dnd_active():
        return
    if sys.platform == 'win32':
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
        except Exception:
            pass
    try:
        widget.bell()
    except Exception:
        pass


def is_dnd_active() -> bool:
    """True when Windows reports Fullscreen / Presentation / Focus Assist Quiet Time."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes

        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
            # 2=BUSY, 3=RUNNING_D3D_FULL_SCREEN, 4=PRESENTATION_MODE, 6=QUIET_TIME
            return state.value in (2, 3, 4, 6)
    except Exception:
        pass
    return False


def is_safe_url(url) -> bool:
    """Only plain https links to a real public host are ever opened."""
    if not isinstance(url, str) or len(url) > 2000 or any(ch.isspace() for ch in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        return False
    host = parts.hostname.rstrip('.').lower()
    if host == 'localhost' or host.endswith('.localhost'):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


def url_host(url) -> str:
    try:
        return (urlsplit(url).hostname or '').removeprefix('www.')
    except ValueError:
        return ''


def safe_open(url) -> bool:
    """Open a link in the browser only if it passes :func:`is_safe_url`."""
    if not is_safe_url(url):
        log.warning('refused to open a non-https link')
        return False
    return bool(webbrowser.open(url))


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        # Opens only our own local data folder.
        os.startfile(str(path))  # noqa: S606  # nosec B606
    else:
        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
        # Fixed OS opener with no shell.
        subprocess.Popen([opener, str(path)])  # noqa: S603  # nosec B603


# --------------------------------------------------------------------------
# Secret storage (Windows DPAPI; POSIX relies on 0600 file permissions)
# --------------------------------------------------------------------------
_DPAPI_PREFIX = 'dpapi:'


def protect_secret(value: str) -> str:
    """Encrypt a short secret for the current Windows user with DPAPI.

    Returns plaintext unchanged on non-Windows platforms (where files are
    written 0600) or if empty.
    """
    if not value or sys.platform != 'win32' or value.startswith(_DPAPI_PREFIX):
        return value
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

        raw = value.encode('utf-8')
        buf = ctypes.create_string_buffer(raw, len(raw))
        blob_in = DATA_BLOB(len(raw), buf)
        blob_out = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptProtectData(
            ctypes.byref(blob_in), 'EconPulse', None, None, None, 0x1, ctypes.byref(blob_out)
        ):
            return value
        try:
            encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            return _DPAPI_PREFIX + base64.b64encode(encrypted).decode('ascii')
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return value


def unprotect_secret(value: str) -> str:
    """Decrypt a DPAPI-protected secret, or pass plaintext through (migration)."""
    if not isinstance(value, str) or not value.startswith(_DPAPI_PREFIX):
        return value if isinstance(value, str) else ''
    if sys.platform != 'win32':
        return ''
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

        raw = base64.b64decode(value[len(_DPAPI_PREFIX) :].encode('ascii'))
        buf = ctypes.create_string_buffer(raw, len(raw))
        blob_in = DATA_BLOB(len(raw), buf)
        blob_out = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
            return ''
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode('utf-8')
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return ''
