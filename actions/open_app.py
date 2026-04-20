import time
import subprocess
import platform
import shutil
import os

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {
    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "youtube":            {"Windows": "https://youtube.com",     "Darwin": "https://youtube.com",  "Linux": "https://youtube.com"},
    "gmail":              {"Windows": "https://gmail.com",       "Darwin": "https://gmail.com",    "Linux": "https://gmail.com"},
}

def _normalize(raw: str) -> str:
    key = raw.lower().strip()
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)
    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)
    return raw  

def _launch_windows(app_name: str) -> bool:
    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(app_name, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            return True
        except Exception: pass
    if ":" in app_name or "." in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True); time.sleep(1.0); return True
        except Exception: pass
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win"); time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05); time.sleep(0.9); pyautogui.press("enter")
        time.sleep(2.5); return True
    except Exception: pass
    return False

def _launch_macos(app_name: str) -> bool:
    for cmd in [["open", app_name], ["open", "-a", app_name], ["open", "-a", f"{app_name}.app"]]:
        try:
            if subprocess.run(cmd, capture_output=True, timeout=8).returncode == 0:
                time.sleep(1.0); return True
        except Exception: continue
    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0); return True
        except Exception: pass
    try:
        import pyautogui
        pyautogui.hotkey("command", "space"); time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05); time.sleep(0.8); pyautogui.press("enter")
        time.sleep(1.5); return True
    except Exception: pass
    return False

def _launch_linux(app_name: str) -> bool:
    if "://" in app_name or app_name.startswith("www."):
        try:
            subprocess.run(["xdg-open", app_name], capture_output=True, timeout=5)
            return True
        except Exception: pass
    binary = (shutil.which(app_name) or shutil.which(app_name.lower()) or 
              shutil.which(app_name.lower().replace(" ", "-")) or 
              shutil.which(app_name.lower().replace(" ", "_")))
    if binary:
        try:
            subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0); return True
        except Exception: pass
    if "." in app_name or "/" in app_name:
        try:
            subprocess.run(["xdg-open", app_name], capture_output=True, timeout=5)
            return True
        except Exception: pass
    for desktop_name in [app_name.lower(), app_name.lower().replace(" ", "-"), 
                         app_name.lower().replace(" ", ""), app_name.title().replace(" ", "")]:
        try:
            if subprocess.run(["gtk-launch", desktop_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return True
        except Exception: continue
    if shutil.which("xdotool"):
        try:
            subprocess.run(["xdotool", "key", "Super"], check=False); time.sleep(0.5)
            subprocess.run(["xdotool", "type", app_name], check=False); time.sleep(0.5)
            subprocess.run(["xdotool", "key", "Return"], check=False); return True
        except Exception: pass
    return False

_OS_LAUNCHERS = {"Windows": _launch_windows, "Darwin": _launch_macos, "Linux": _launch_linux}

def open_app(parameters=None, response=None, player=None, session_memory=None) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()
    if not app_name: return "No application name provided."
    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None: return f"Unsupported operating system: {_SYSTEM}"
    normalized = _normalize(app_name)
    if player: player.write_log(f"[open_app] {app_name}")
    try:
        if launcher(normalized): return f"Opened {app_name}."
        if normalized.lower() != app_name.lower() and launcher(app_name): return f"Opened {app_name}."
        return f"Could not confirm that {app_name} launched."
    except Exception as e: return f"Failed to open {app_name}: {e}"
