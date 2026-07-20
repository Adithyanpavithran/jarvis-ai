import os
import sys
import subprocess
import webbrowser
import datetime
from pathlib import Path
from app.utils.logger import get_app_dir, log
from app.ai.tool_calls import tool_registry

# Create screenshots directory
SCREENSHOTS_DIR = get_app_dir() / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

@tool_registry.register("open_app")
def open_app(app_name: str) -> str:
    """Open a desktop application by name."""
    app_map = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe"
    }
    
    executable = app_map.get(app_name.lower(), app_name)
    try:
        subprocess.Popen(executable, shell=True)
        log.info("Opened application: %s", executable)
        return f"Successfully opened {app_name}."
    except Exception as e:
        log.error("Failed to open application %s: %s", app_name, e)
        return f"Failed to open {app_name}. Error: {e}"

@tool_registry.register("close_app")
def close_app(app_name: str) -> str:
    """Close an application process using taskkill."""
    if sys.platform != "win32":
        return "Process termination is only supported on Windows."
    
    # Map friendly names to process names
    process_map = {
        "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe",
        "calc": "CalculatorApp.exe",
        "paint": "mspaint.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "word": "winword.exe",
        "excel": "excel.exe"
    }
    
    process = process_map.get(app_name.lower(), app_name)
    if not process.endswith(".exe"):
        process += ".exe"

    try:
        subprocess.run(["taskkill", "/f", "/im", process], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("Closed application process: %s", process)
        return f"Successfully closed {app_name}."
    except Exception as e:
        log.error("Failed to close process %s: %s", process, e)
        return f"Could not find or close {app_name}."

@tool_registry.register("open_url")
def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        log.info("Opened URL: %s", url)
        return f"Opened website: {url}"
    except Exception as e:
        log.error("Failed to open URL %s: %s", url, e)
        return f"Failed to open website. Error: {e}"

@tool_registry.register("screenshot")
def take_screenshot() -> str:
    """Take a screenshot and save it to app data directory."""
    try:
        from PIL import ImageGrab
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = SCREENSHOTS_DIR / f"screenshot_{timestamp}.png"
        
        # Capture screen
        screenshot = ImageGrab.grab()
        screenshot.save(filepath)
        log.info("Screenshot saved: %s", filepath)
        
        # Display Windows notification if possible
        show_notification("Screenshot Captured", f"Saved to {filepath.name}")
        return f"Screenshot taken and saved as {filepath.name}."
    except Exception as e:
        log.error("Failed to take screenshot: %s", e)
        return f"Failed to take screenshot. Error: {e}"

@tool_registry.register("lock_pc")
def lock_pc() -> str:
    """Lock the Windows PC."""
    if sys.platform != "win32":
        return "Lock PC is only supported on Windows."
    try:
        subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
        log.info("PC Locked.")
        return "Computer locked."
    except Exception as e:
        log.error("Failed to lock PC: %s", e)
        return "Failed to lock PC."

@tool_registry.register("sleep_pc")
def sleep_pc() -> str:
    """Put the Windows PC to sleep."""
    if sys.platform != "win32":
        return "Sleep mode is only supported on Windows."
    try:
        subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        log.info("PC Suspend triggered.")
        return "Putting computer to sleep."
    except Exception as e:
        log.error("Failed to suspend PC: %s", e)
        return "Failed to trigger sleep mode."

@tool_registry.register("set_volume")
def set_volume(level: int) -> str:
    """Set the system volume to a percentage (0-100) using PowerShell."""
    if sys.platform != "win32":
        return "Volume control is only supported on Windows."
    
    # Clip level to 0-100
    level = max(0, min(100, level))
    
    # We can use PowerShell Core Audio APIs (SoundDevice or simple com shells)
    # To set exact volume, a tiny powershell script using CoreAudio is most robust
    # If CoreAudio is missing, we use standard WScript com object to nudge volume.
    # An elegant way to set exact volume via powershell:
    ps_cmd = (
        f"$w = New-Object -ComObject Wscript.Shell; "
        f"for ($i=0; $i -lt 50; $i++) {{ $w.SendKeys([char]174) }}; " # volume down 50 times to mute
        f"for ($i=0; $i -lt {int(level / 2)}; $i++) {{ $w.SendKeys([char]175) }}" # volume up to target
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        log.info("Volume set to %d%%", level)
        return f"Volume set to {level}%."
    except Exception as e:
        log.error("Failed to set volume: %s", e)
        return "Failed to set volume."

@tool_registry.register("set_brightness")
def set_brightness(level: int) -> str:
    """Set screen brightness using Windows WMI monitor service."""
    if sys.platform != "win32":
        return "Brightness control is only supported on Windows."
    
    level = max(0, min(100, level))
    ps_cmd = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        log.info("Screen brightness set to %d%%", level)
        return f"Screen brightness set to {level}%."
    except Exception as e:
        log.error("Failed to set brightness: %s", e)
        return "Failed to set brightness."

def show_notification(title: str, message: str):
    """Display a system notification using plyer."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Jarvis",
            timeout=5
        )
    except Exception as e:
        log.error("Failed to send notification: %s", e)
