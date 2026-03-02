# actions/desktop.py
# AI-powered desktop & wallpaper management
#
# Flow for unknown tasks:
#   User request → Gemini generates Python/pyautogui code → Safety check → Execute
#
# Built-in: wallpaper change, icon arrangement, desktop cleanup, organize by type

import os
import sys
import json
import shutil
import subprocess
import ctypes
import tempfile
import pyautogui
from pathlib import Path
from datetime import datetime


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_desktop() -> Path:
    return Path.home() / "Desktop"


BLOCKED_KEYWORDS = [
    "os.remove", "shutil.rmtree", "shutil.rm",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "os.system", "exec(", "eval(",
    "import os", "import subprocess",
    "__import__", "open(",
    "sys.exit", "quit()",
]


def _is_safe_code(code: str) -> tuple[bool, str]:
    code_lower = code.lower()
    for keyword in BLOCKED_KEYWORDS:
        if keyword.lower() in code_lower:
            return False, f"Blocked operation: '{keyword}'"
    return True, "OK"


def _ask_gemini_for_desktop_action(task: str) -> str:
    """
    Asks Gemini to generate safe Python/pyautogui code
    to accomplish a desktop-related task.
    """
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash")

    desktop = str(_get_desktop())

    prompt = f"""You are a Windows desktop automation expert.
Generate safe Python code using ONLY these allowed modules:
- pyautogui (mouse, keyboard, screenshots)
- pathlib.Path (already imported as Path)
- shutil (ONLY: copy2, copytree, move, disk_usage)
- os.path (ONLY: exists, join, dirname, basename, splitext)
- time (sleep only)
- ctypes (Windows API calls only)
- winreg (registry READ only)

Desktop path: {desktop}

Rules:
- Output ONLY the Python code. No explanation, no markdown, no backticks.
- NO file deletion (os.remove, shutil.rmtree, unlink, etc.)
- NO subprocess calls
- NO exec() or eval()
- NO file write operations
- If task cannot be done safely, output exactly: UNSAFE

Task: {task}

Python code:"""

    try:
        response = model.generate_content(prompt)
        code = response.text.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1]).strip()
        return code
    except Exception as e:
        return f"ERROR: {e}"


def _execute_generated_code(code: str) -> str:
    """Safely executes Gemini-generated desktop automation code."""
    safe, reason = _is_safe_code(code)
    if not safe:
        return f"⛔ Blocked for safety: {reason}"

    allowed_globals = {
        "pyautogui": pyautogui,
        "Path": Path,
        "shutil": shutil,
        "ctypes": ctypes,
        "time": __import__("time"),
        "os": type("os", (), {
            "path": os.path,
            "listdir": os.listdir,
            "getcwd": os.getcwd,
            "environ": os.environ,
        })(),
        "__builtins__": {
            "print": print,
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "range": range,
            "enumerate": enumerate,
            "sorted": sorted,
            "isinstance": isinstance,
            "hasattr": hasattr,
            "getattr": getattr,
            "max": max,
            "min": min,
            "sum": sum,
        }
    }

    output_lines = []
    allowed_globals["print"] = lambda *args: output_lines.append(" ".join(str(a) for a in args))

    try:
        exec(code, allowed_globals)
        return "\n".join(output_lines) if output_lines else "Task completed successfully."
    except Exception as e:
        return f"Execution error: {e}\n\nCode attempted:\n{code[:200]}"

def set_wallpaper(image_path: str) -> str:
    """Sets desktop wallpaper from a local image path."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return f"Image not found: {image_path}"
    if path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".bmp"]:
        return f"Unsupported format: {path.suffix}. Use jpg, png or bmp."

    try:
        if sys.platform == "win32":

            abs_path = str(path.resolve())
            ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
            return f"Wallpaper set: {path.name}"

        elif sys.platform == "darwin":
            script = f'tell application "Finder" to set desktop picture to POSIX file "{path}"'
            subprocess.run(["osascript", "-e", script])
            return f"Wallpaper set: {path.name}"

        else:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                          "picture-uri", f"file://{path}"])
            return f"Wallpaper set: {path.name}"

    except Exception as e:
        return f"Could not set wallpaper: {e}"


def set_wallpaper_from_web(url: str) -> str:
    """Downloads an image from URL and sets it as wallpaper."""
    try:
        import urllib.request
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        tmp    = Path(tempfile.mktemp(suffix=suffix))
        urllib.request.urlretrieve(url, str(tmp))
        result = set_wallpaper(str(tmp))
        return result
    except Exception as e:
        return f"Could not download wallpaper: {e}"


def get_current_wallpaper() -> str:
    """Returns the current wallpaper path."""
    try:
        if sys.platform == "win32":
            import winreg
            key  = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                  r"Control Panel\Desktop")
            val, _ = winreg.QueryValueEx(key, "Wallpaper")
            return f"Current wallpaper: {val}"
        else:
            return "Wallpaper path retrieval not supported on this OS."
    except Exception as e:
        return f"Could not get wallpaper: {e}"


FILE_TYPE_MAP = {
    "Images":    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".odt"],
    "Videos":    [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"],
    "Music":     [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "Archives":  [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "Code":      [".py", ".js", ".html", ".css", ".json", ".xml", ".ts", ".cpp", ".java", ".cs", ".php"],
    "Executables": [".exe", ".msi", ".bat", ".cmd", ".sh"],
}


def organize_desktop(mode: str = "by_type") -> str:
    """
    Organizes desktop files.
    mode: 'by_type' — groups by file type (Images, Documents, etc.)
          'by_date'  — groups by month (2024-01, 2024-02, etc.)
    """
    desktop = _get_desktop()
    moved   = []
    skipped = []

    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue

        if item.suffix.lower() == ".lnk":
            continue

        if mode == "by_date":
            mtime      = datetime.fromtimestamp(item.stat().st_mtime)
            folder_name = mtime.strftime("%Y-%m")
        else:
            ext        = item.suffix.lower()
            folder_name = "Others"
            for folder, exts in FILE_TYPE_MAP.items():
                if ext in exts:
                    folder_name = folder
                    break

        target_dir = desktop / folder_name
        target_dir.mkdir(exist_ok=True)
        new_path = target_dir / item.name

        if new_path.exists():
            skipped.append(item.name)
            continue

        shutil.move(str(item), str(new_path))
        moved.append(f"{item.name} → {folder_name}/")

    result = f"Desktop organized ({mode}). {len(moved)} files moved."
    if moved:
        preview = moved[:8]
        result += "\n" + "\n".join(preview)
        if len(moved) > 8:
            result += f"\n... and {len(moved)-8} more."
    if skipped:
        result += f"\n{len(skipped)} files skipped (name conflict)."
    return result


def list_desktop() -> str:
    """Lists everything on the desktop."""
    desktop = _get_desktop()
    items   = []

    for item in sorted(desktop.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            count = len(list(item.iterdir()))
            items.append(f"📁 {item.name}/ ({count} items)")
        else:
            size = item.stat().st_size
            size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
            items.append(f"📄 {item.name} ({size_str})")

    if not items:
        return "Desktop is empty."
    return f"Desktop ({len(items)} items):\n" + "\n".join(items)


def clean_desktop() -> str:
    """
    Moves all files on desktop into a 'Desktop Archive' folder
    with today's date — fast cleanup without deleting anything.
    """
    desktop     = _get_desktop()
    today       = datetime.now().strftime("%Y-%m-%d")
    archive_dir = desktop / f"Desktop Archive {today}"
    archive_dir.mkdir(exist_ok=True)

    moved = 0
    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() == ".lnk":
            continue
        new_path = archive_dir / item.name
        if not new_path.exists():
            shutil.move(str(item), str(new_path))
            moved += 1

    return f"Desktop cleaned. {moved} files moved to '{archive_dir.name}'."


def get_desktop_stats() -> str:
    """Returns stats about the desktop."""
    desktop     = _get_desktop()
    files       = [i for i in desktop.iterdir() if i.is_file()]
    folders     = [i for i in desktop.iterdir() if i.is_dir()]
    total_size  = sum(f.stat().st_size for f in files)
    size_str    = f"{total_size/1024:.1f} KB" if total_size < 1024*1024 else f"{total_size/1024/1024:.1f} MB"

    return (
        f"Desktop stats:\n"
        f"  Files   : {len(files)}\n"
        f"  Folders : {len(folders)}\n"
        f"  Total size: {size_str}"
    )


def desktop_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None
) -> str:
    """
    Called from main.py.

    parameters:
        action      : wallpaper | wallpaper_url | current_wallpaper |
                      organize | clean | list | stats |
                      task (AI-powered — anything else)

        path        : image path for 'wallpaper'
        url         : image URL for 'wallpaper_url'
        mode        : 'by_type' or 'by_date' for 'organize'
        task        : Natural language description for AI-powered actions.
                      Example: "arrange icons by size"
                               "show me what's on my desktop"
                               "move all screenshots to a folder"
    """
    action = (parameters or {}).get("action", "").lower().strip()
    task   = (parameters or {}).get("task", "").strip()

    result = "Unknown action."

    try:
        if action == "wallpaper":
            path   = parameters.get("path", "")
            result = set_wallpaper(path) if path else "No image path provided."

        elif action == "wallpaper_url":
            url    = parameters.get("url", "")
            result = set_wallpaper_from_web(url) if url else "No URL provided."

        elif action == "current_wallpaper":
            result = get_current_wallpaper()

        elif action == "organize":
            mode   = parameters.get("mode", "by_type")
            result = organize_desktop(mode)

        elif action == "clean":
            result = clean_desktop()

        elif action == "list":
            result = list_desktop()

        elif action == "stats":
            result = get_desktop_stats()

        elif action == "task" or task:
            actual_task = task or parameters.get("description", "")
            if not actual_task:
                return "Please describe what you want to do on the desktop, sir."

            print(f"[Desktop] 🤖 Asking Gemini: {actual_task}")
            if player:
                player.write_log("[Desktop] Generating action...")

            code = _ask_gemini_for_desktop_action(actual_task)

            if code == "UNSAFE":
                result = "I cannot perform that desktop action safely, sir."
            elif code.startswith("ERROR:"):
                result = f"Could not generate action: {code}"
            else:
                print(f"[Desktop] ✅ Generated code:\n{code[:200]}")
                result = _execute_generated_code(code)

        else:
            full_task = task or action
            if full_task:
                code   = _ask_gemini_for_desktop_action(full_task)
                result = _execute_generated_code(code) if code not in ("UNSAFE",) else "Cannot do that safely."
            else:
                result = "No action or task specified."

    except Exception as e:
        result = f"Desktop control error: {e}"

    print(f"[Desktop] {result[:100]}")
    if player:
        player.write_log(f"[desktop] {result[:60]}")

    return result