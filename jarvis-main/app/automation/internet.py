import os
import sys
import json
import shutil
import tempfile
import subprocess
import webbrowser
import urllib.request
import urllib.parse
from pathlib import Path
from app.utils.logger import log
from app.ai.tool_calls import tool_registry
from app.config.settings import settings_manager

@tool_registry.register("web_search")
def web_search(query: str) -> str:
    """Search DuckDuckGo (API or HTML) for a query and return summaries."""
    log.info("Searching the web for: %s", query)
    try:
        # Use DuckDuckGo HTML or Instant Answer API
        safe_query = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={safe_query}&format=json"
        
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            
            abstract = data.get("AbstractText", "")
            if abstract:
                return f"DuckDuckGo Abstract: {abstract}"
            
            related = data.get("RelatedTopics", [])
            summaries = []
            for r in related[:3]:
                if "Text" in r:
                    summaries.append(r["Text"])
            
            if summaries:
                return "DuckDuckGo Results:\n" + "\n".join(f"- {s}" for s in summaries)
            
        return f"No direct abstract found. You can search online at: https://duckduckgo.com/?q={safe_query}"
    except Exception as e:
        log.error("Failed to perform DDG search: %s", e)
        return f"Failed to search: {e}"

@tool_registry.register("weather")
def get_weather(city: str) -> str:
    """Fetch current weather for a city using wttr.in (no API key required)."""
    log.info("Fetching weather for: %s", city)
    try:
        # Get weather in simple text format (1 line) or json
        safe_city = urllib.parse.quote_plus(city.strip())
        url = f"https://wttr.in/{safe_city}?format=%C+%t+(feels+like+%f),+humidity+%h,+wind+%w"
        
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "curl/7.79.1"} # wttr.in likes curl User-Agent for raw output
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res = response.read().decode("utf-8").strip()
            return f"Weather in {city}: {res}"
    except Exception as e:
        log.error("Failed to get weather for %s: %s", city, e)
        return f"Could not fetch weather for {city}. Error: {e}"

@tool_registry.register("wiki_search")
def wiki_search(query: str) -> str:
    """Search Wikipedia for a brief summary of a topic."""
    log.info("Searching Wikipedia for: %s", query)
    try:
        safe_query = urllib.parse.quote_plus(query)
        # Search Wikipedia API
        url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=1&explaintext=1&titles={safe_query}"
        
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id != "-1":
                    extract = page_data.get("extract", "")
                    if extract:
                        # Limit output to 400 characters
                        return f"Wikipedia ({page_data['title']}): {extract[:400]}..."
            
        # Fallback to search list
        search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={safe_query}&limit=1&namespace=0&format=json"
        with urllib.request.urlopen(search_url, timeout=10) as response:
            search_data = json.loads(response.read().decode("utf-8"))
            if len(search_data) > 3 and search_data[3]:
                return f"Wikipedia page found: {search_data[1][0]} - {search_data[3][0]}"
                
        return "No Wikipedia page matches found."
    except Exception as e:
        log.error("Wikipedia search failed: %s", e)
        return f"Failed to search Wikipedia. Error: {e}"

def _chrome_executable() -> str | None:
    if sys.platform == "win32":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("google-chrome") or shutil.which("chrome")


def _win32_sorted_monitor_rects() -> list[tuple[int, int, int, int]]:
    """Each monitor as (left, top, right, bottom), sorted left-to-right then top-to-bottom."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    collected: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
    def _cb(_hm, _hdc, lprc, _lp):
        r = lprc.contents
        collected.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, _cb, 0)
    collected.sort(key=lambda t: (t[0], t[1]))
    return collected


def _chrome_monitor_bounds(one_based_index: int) -> tuple[int, int, int, int]:
    """Monitor N as (left, top, right, bottom), 1-based index."""
    rects = _win32_sorted_monitor_rects()
    if not rects:
        return (0, 0, 1920, 1080)
    idx = one_based_index - 1
    if idx < 0:
        idx = 0
    if idx >= len(rects):
        log.warning(
            "Monitor %d requested but only %d found; using last monitor.",
            one_based_index,
            len(rects),
        )
        idx = len(rects) - 1
    return rects[idx]


def _chrome_monitor_top_left(one_based_index: int) -> tuple[int, int]:
    l, t, _, _ = _chrome_monitor_bounds(one_based_index)
    return (l, t)


def _chrome_monitor_pixel_size(one_based_index: int) -> tuple[int, int]:
    l, t, r, b = _chrome_monitor_bounds(one_based_index)
    return (max(320, r - l), max(240, b - t))


def _chrome_window_size() -> tuple[int, int]:
    w = (os.environ.get("CHROME_WINDOW_WIDTH") or "1400").strip()
    h = (os.environ.get("CHROME_WINDOW_HEIGHT") or "900").strip()
    try:
        return (max(400, int(w)), max(300, int(h)))
    except ValueError:
        return (1400, 900)


def _chrome_site_user_data_dir(site_key: str) -> str:
    p = Path(tempfile.gettempdir()) / "clap-trigger-chrome" / site_key
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _chrome_new_window_wait_timeout_s() -> float:
    try:
        return max(3.0, float((os.environ.get("CHROME_NEW_WINDOW_WAIT_S") or "25").strip()))
    except ValueError:
        return 25.0


def _chrome_top_level_browser_hwnds_win32() -> set[int]:
    """HWND ints for visible-or-minimized top-level Chrome browser windows."""
    if sys.platform != "win32":
        return set()
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    found: set[int] = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        except Exception:
            return True
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "chrome.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 80 or h < 80:
            return True
        found.add(int(hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def _wait_new_chrome_hwnd_win32(before: set[int], timeout: float) -> int | None:
    deadline = time_monotonic() + timeout
    while time_monotonic() < deadline:
        time_sleep(0.12)
        now = _chrome_top_level_browser_hwnds_win32()
        new = now - before
        if not new:
            continue
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        best: int | None = None
        best_area = 0
        for h in new:
            r = wintypes.RECT()
            if user32.GetWindowRect(h, ctypes.byref(r)):
                a = max(0, r.right - r.left) * max(0, r.bottom - r.top)
                if a > best_area:
                    best_area = a
                    best = h
        if best is not None:
            return best
    return None

def time_monotonic():
    import time
    return time.monotonic()

def time_sleep(seconds: float):
    import time
    time.sleep(seconds)


def _chrome_snap_window_to_monitor_win32(
    hwnd: int,
    one_based_monitor: int,
    *,
    fullscreen: bool,
    windowed_size: tuple[int, int] | None,
) -> None:
    import ctypes
    from ctypes import wintypes

    ml, mt, mr, mb = _chrome_monitor_bounds(one_based_monitor)
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    SW_SHOWMAXIMIZED = 3
    HWND_TOP = 0
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED

    user32.ShowWindow(hwnd, SW_RESTORE)
    if fullscreen:
        w, h = mr - ml, mb - mt
        x, y = ml, mt
    else:
        ww, wh = windowed_size or _chrome_window_size()
        w, h = ww, wh
        x = ml + max(0, (mr - ml - w) // 2)
        y = mt + max(0, (mb - mt - h) // 2)
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, flags)

    if fullscreen:
        user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
        KEYEVENTF_KEYUP = 0x0002
        VK_F11 = 0x7A
        fg = user32.GetForegroundWindow()
        tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, True)
        user32.SetForegroundWindow(hwnd)
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, False)
        user32.keybd_event(VK_F11, 0, 0, 0)
        user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _open_url_in_chrome(
    url: str,
    *,
    new_window: bool = True,
    label: str = "URL",
    window_position: tuple[int, int] | None = None,
    window_size: tuple[int, int] | None = None,
    fullscreen: bool = False,
    win32_post_fullscreen_monitor: int | None = None,
    user_data_dir: str | None = None,
) -> None:
    u = url.strip()
    if not u:
        return
    chrome = _chrome_executable()
    try:
        if chrome:
            args = [chrome]
            if user_data_dir:
                args.append(f"--user-data-dir={user_data_dir}")
                args.append("--no-first-run")
            if new_window:
                args.append("--new-window")
            if window_position is not None:
                x, y = window_position
                args.append(f"--window-position={x},{y}")
            if window_size:
                args.append(f"--window-size={window_size[0]},{window_size[1]}")
            if fullscreen and not (
                sys.platform == "win32" and win32_post_fullscreen_monitor is not None
            ):
                args.append("--start-fullscreen")
            args.append(u)
            popen_kw: dict = {
                "args": args,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            before: set[int] | None = None
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                before = _chrome_top_level_browser_hwnds_win32()
            subprocess.Popen(**popen_kw)
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                mon = win32_post_fullscreen_monitor
                hwnd = _wait_new_chrome_hwnd_win32(before, _chrome_new_window_wait_timeout_s())
                if hwnd is not None:
                    _chrome_snap_window_to_monitor_win32(
                        hwnd,
                        mon,
                        fullscreen=fullscreen,
                        windowed_size=window_size if not fullscreen else None,
                    )
                else:
                    log.warning(
                        "Chrome: timed out waiting for new window (%s); check "
                        "CHROME_NEW_WINDOW_WAIT_S or close extra Chrome instances.",
                        label,
                    )
        else:
            log.warning("Chrome not found; opening %s in default browser.", label)
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open %s in Chrome: %s", label, e)


@tool_registry.register("open_claude")
def open_claude_in_chrome() -> str:
    """Open Claude in Google Chrome snapped to the configured monitor."""
    url = settings_manager.get("claude_code_url", "https://claude.ai/new").strip()
    fs = settings_manager.get("open_chrome_fullscreen", True)
    monitor = settings_manager.get("claude_chrome_monitor", 1)
    sep_profiles = settings_manager.get("chrome_separate_site_profiles", False)

    pos: tuple[int, int] | None = None
    size: tuple[int, int] | None = None
    post_mon: int | None = None
    user_data: str | None = None
    
    if sys.platform == "win32":
        post_mon = monitor
        pos = _chrome_monitor_top_left(monitor)
        if fs:
            size = _chrome_monitor_pixel_size(monitor)
        else:
            size = _chrome_window_size()
        if sep_profiles:
            user_data = _chrome_site_user_data_dir("claude")
    elif not fs:
        size = _chrome_window_size()
    else:
        size = None
        
    log.info("Opening Claude in Chrome: monitor=%s, url=%s", monitor, url)
    _open_url_in_chrome(
        url,
        new_window=True,
        label="Claude",
        window_position=pos,
        window_size=size,
        fullscreen=fs,
        win32_post_fullscreen_monitor=post_mon,
        user_data_dir=user_data,
    )
    return "Opened Claude in Chrome."
