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
import threading
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


def _notification_state() -> int:
    """SHQueryUserNotificationState: 2 busy (full screen), 3 full-screen Direct3D,
    4 presentation mode, 6 Focus Assist quiet time; 0 when unknown or not Windows."""
    if sys.platform != 'win32':
        return 0
    try:
        import ctypes

        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
            return state.value
    except Exception:
        pass
    return 0


def is_dnd_active() -> bool:
    """True when Windows reports Fullscreen / Presentation / Focus Assist Quiet Time."""
    return _notification_state() in (2, 3, 4, 6)


class AppBar:
    """Dock a window to the top or bottom of its monitor and reserve that strip, as the
    taskbar does (Windows). Maximised windows then stop short of it.

    If EconPulse ends without undocking (a crash), Windows releases the strip by itself
    within a second (checked on Windows 11), so it can't leave a dead band on screen.
    """

    ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS = 0, 1, 2, 3
    EDGES = {'top': 1, 'bottom': 3}
    CALLBACK_MESSAGE = 0x8000 + 0x45  # WM_APP-based; required by ABM_NEW

    def __init__(self, window) -> None:
        self.window = window
        self.hwnd = 0

    @staticmethod
    def supported() -> bool:
        return sys.platform == 'win32'

    @staticmethod
    def _data():
        import ctypes
        from ctypes import wintypes

        class APPBARDATA(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('hWnd', wintypes.HWND),
                ('uCallbackMessage', wintypes.UINT),
                ('uEdge', wintypes.UINT),
                ('rc', wintypes.RECT),
                ('lParam', wintypes.LPARAM),
            ]

        return APPBARDATA

    def dock(self, edge: str, height: int) -> tuple[int, int, int, int] | None:
        """Reserve ``height`` pixels at ``edge`` of the window's monitor; returns the strip."""
        if not self.supported() or edge not in self.EDGES:
            return None
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

            user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
            self.window.update_idletasks()
            hwnd = user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # nearest monitor
            data_type = self._data()
            abd = data_type(ctypes.sizeof(data_type), hwnd, self.CALLBACK_MESSAGE, self.EDGES[edge])
            if not self.hwnd:
                if not shell32.SHAppBarMessage(self.ABM_NEW, ctypes.byref(abd)):
                    return None
                self.hwnd = hwnd
            m = info.rcMonitor
            abd.rc = wintypes.RECT(m.left, m.top, m.right, m.bottom)
            for message in (self.ABM_QUERYPOS, self.ABM_SETPOS):  # the shell may move it clear of the taskbar
                if edge == 'top':
                    abd.rc.bottom = abd.rc.top + height
                else:
                    abd.rc.top = abd.rc.bottom - height
                shell32.SHAppBarMessage(message, ctypes.byref(abd))
            return abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom
        except Exception:
            log.warning('could not dock the compact bar', exc_info=True)
            self.undock()
            return None

    def undock(self) -> None:
        if not self.hwnd:
            return
        try:
            import ctypes

            data_type = self._data()
            abd = data_type(ctypes.sizeof(data_type), self.hwnd)
            ctypes.windll.shell32.SHAppBarMessage(self.ABM_REMOVE, ctypes.byref(abd))
        except Exception:
            pass
        self.hwnd = 0


def fullscreen_app_active() -> bool:
    """A full-screen game, video or presentation is in front (Windows)."""
    return _notification_state() in (2, 3, 4)


class GlobalHotkey:
    """A system-wide shortcut (Windows): Ctrl+Alt+<key> calls ``callback`` from anywhere.

    Windows posts the hotkey to the thread that registered it, so registration and the
    message loop live on a small thread of their own. ``callback`` runs on that thread:
    hand the work to Tk's thread (EconPulse puts it on ``ui_queue``).
    """

    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
    WM_HOTKEY, WM_QUIT, PM_NOREMOVE = 0x0312, 0x0012, 0x0000

    def __init__(self, key: str, callback) -> None:
        self.vk = ord(key.upper())
        self.callback = callback
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.ok = False

    @staticmethod
    def supported() -> bool:
        return sys.platform == 'win32'

    def start(self) -> bool:
        """Register the shortcut; False if it can't be (another app already uses it)."""
        if not self.supported():
            return False
        self._thread = threading.Thread(target=self._run, daemon=True, name='global-hotkey')
        self._thread.start()
        self._ready.wait(2)
        return self.ok

    def stop(self) -> None:
        if self._thread is None:
            return
        try:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        except Exception:
            pass
        self._thread.join(1)
        self._thread = None

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, self.PM_NOREMOVE)  # create the message queue
        self.ok = bool(user32.RegisterHotKey(None, 1, self.MOD_CONTROL | self.MOD_ALT | self.MOD_NOREPEAT, self.vk))
        self._ready.set()
        if not self.ok:
            return
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == self.WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        log.exception('global shortcut action failed')
        finally:
            user32.UnregisterHotKey(None, 1)


def high_contrast_active() -> bool:
    """True when Windows' own High Contrast mode is on (Settings > Accessibility > Contrast themes)."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class HIGHCONTRASTW(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('dwFlags', wintypes.DWORD), ('lpszDefaultScheme', wintypes.LPWSTR)]

        info = HIGHCONTRASTW(ctypes.sizeof(HIGHCONTRASTW), 0, None)
        spi_gethighcontrast, hcf_highcontraston = 0x0042, 0x0001
        if ctypes.windll.user32.SystemParametersInfoW(spi_gethighcontrast, info.cbSize, ctypes.byref(info), 0):
            return bool(info.dwFlags & hcf_highcontraston)
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
# Secret storage: Windows DPAPI; on macOS/Linux the system keychain when the optional
# `keyring` package is installed, otherwise the private (0600) settings file.
# --------------------------------------------------------------------------
_DPAPI_PREFIX = 'dpapi:'
_KEYRING_MARK = 'keyring:'  # stored in settings.json in place of a secret kept in the keychain
_KEYRING_SERVICE, _KEYRING_NAME = 'EconPulse', 'financecalendar_key'
_keyring_value: str | None = None  # what the keychain holds, so saves don't rewrite it every time


def _keyring():
    try:
        import keyring
    except Exception:  # not installed, or no usable backend
        return None
    return keyring


def protect_secret(value: str) -> str:
    """Keep a short secret out of the settings file where the platform allows it.

    Windows: encrypted for the current user with DPAPI. macOS/Linux: stored in the system
    keychain (Keychain, Secret Service, KWallet) if `keyring` is installed and works.
    Otherwise the value is returned unchanged and lives in the private 0600 file.
    """
    global _keyring_value
    if not value or value.startswith((_DPAPI_PREFIX, _KEYRING_MARK)):
        return value
    if sys.platform != 'win32':
        keyring = _keyring()
        if keyring is None:
            return value
        try:
            if value != _keyring_value:
                keyring.set_password(_KEYRING_SERVICE, _KEYRING_NAME, value)
                _keyring_value = value
            return _KEYRING_MARK
        except Exception:
            log.warning('the system keychain is unavailable; keeping the key in the private settings file')
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
    """Read back a protected secret, or pass plaintext through (migration)."""
    global _keyring_value
    if value == _KEYRING_MARK:
        keyring = _keyring()
        try:
            _keyring_value = (keyring.get_password(_KEYRING_SERVICE, _KEYRING_NAME) if keyring else None) or ''
        except Exception:
            _keyring_value = ''
        return _keyring_value
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


def forget_secret() -> None:
    """The key was cleared in Settings: remove it from the system keychain too."""
    global _keyring_value
    if sys.platform == 'win32' or not _keyring_value:
        return
    keyring = _keyring()
    try:
        if keyring is not None:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_NAME)
    except Exception:
        pass
    _keyring_value = None
