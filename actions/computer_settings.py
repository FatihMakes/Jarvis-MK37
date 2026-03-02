# actions/computer_settings.py
# MARK XXV — Computer Settings & UI Controls
#
# Kullanıcı "sesi aç", "uygulamayı kapat", "tam ekran yap", "şunu yaz" gibi
# bilgisayar kontrol komutları verdiğinde bu dosya devreye girer.
#
# - Intent detection: Gemini ile (multi-language, hardcoded keyword yok)
# - Cross-platform: Windows / macOS / Linux
# - pyautogui + platform-specific API'ler

import time
import subprocess
import sys
import platform
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_OS = platform.system() 

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

import json
def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def volume_up():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) + 10)"])
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"])

def volume_down():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume output volume (output volume of (get volume settings) - 10)"])
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"])

def volume_mute():
    if _OS == "Windows":
        pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume with output muted"])
    else:
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

def volume_set(value: int):
    value = max(0, min(100, value))
    if _OS == "Windows":
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            import math
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            print(f"[Settings] 🔊 Volume → {value}%")
            return
        except Exception as e:
            print(f"[Settings] ⚠️ pycaw failed: {e}")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"])
        return
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"])
        return

def brightness_up():
    if _OS == "Windows":
        pyautogui.hotkey("win", "a")
        time.sleep(0.3)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "tell application \"System Events\" to key code 144"])
    else:
        subprocess.run(["brightnessctl", "set", "+10%"])

def brightness_down():
    if _OS == "Windows":
        pyautogui.hotkey("win", "a")
        time.sleep(0.3)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "tell application \"System Events\" to key code 145"])
    else:
        subprocess.run(["brightnessctl", "set", "10%-"])


def close_app():
    if _OS == "Darwin":
        pyautogui.hotkey("command", "q")
    else:
        pyautogui.hotkey("alt", "f4")

def close_window():
    if _OS == "Darwin":
        pyautogui.hotkey("command", "w")
    else:
        pyautogui.hotkey("ctrl", "w")

def full_screen():
    if _OS == "Darwin":
        pyautogui.hotkey("ctrl", "command", "f")
    else:
        pyautogui.press("f11")

def minimize_window():
    if _OS == "Darwin":
        pyautogui.hotkey("command", "m")
    else:
        pyautogui.hotkey("win", "down")

def maximize_window():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "f" using {control down, command down}'])
    else:
        pyautogui.hotkey("win", "up")

def snap_left():
    if _OS == "Windows": pyautogui.hotkey("win", "left")

def snap_right():
    if _OS == "Windows": pyautogui.hotkey("win", "right")

def switch_window():
    if _OS == "Darwin":
        pyautogui.hotkey("command", "tab")
    else:
        pyautogui.hotkey("alt", "tab")

def show_desktop():
    if _OS == "Darwin":
        pyautogui.hotkey("fn", "f11")
    elif _OS == "Windows":
        pyautogui.hotkey("win", "d")
    else:
        pyautogui.hotkey("super", "d")

def open_task_manager():
    if _OS == "Windows":
        pyautogui.hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Activity Monitor"])
    else:
        subprocess.Popen(["gnome-system-monitor"])

def open_task_view():
    if _OS == "Windows":
        pyautogui.hotkey("win", "tab")


def focus_search():
    if _OS == "Darwin": pyautogui.hotkey("command", "l")
    else:               pyautogui.hotkey("ctrl", "l")

def pause_video():      pyautogui.press("space")
def refresh_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "r")
    else:               pyautogui.press("f5")

def close_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def new_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "t")
    else:               pyautogui.hotkey("ctrl", "t")

def next_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketright")
    else:               pyautogui.hotkey("ctrl", "tab")

def prev_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketleft")
    else:               pyautogui.hotkey("ctrl", "shift", "tab")

def go_back():
    if _OS == "Darwin": pyautogui.hotkey("command", "left")
    else:               pyautogui.hotkey("alt", "left")

def go_forward():
    if _OS == "Darwin": pyautogui.hotkey("command", "right")
    else:               pyautogui.hotkey("alt", "right")

def zoom_in():
    if _OS == "Darwin": pyautogui.hotkey("command", "equal")
    else:               pyautogui.hotkey("ctrl", "equal")

def zoom_out():
    if _OS == "Darwin": pyautogui.hotkey("command", "minus")
    else:               pyautogui.hotkey("ctrl", "minus")

def zoom_reset():
    if _OS == "Darwin": pyautogui.hotkey("command", "0")
    else:               pyautogui.hotkey("ctrl", "0")

def find_on_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "f")
    else:               pyautogui.hotkey("ctrl", "f")

def reload_page_n(n: int):
    for _ in range(n):
        refresh_page()
        time.sleep(0.8)


def scroll_up(amount: int = 500):   pyautogui.scroll(amount)
def scroll_down(amount: int = 500): pyautogui.scroll(-amount)
def scroll_top():    pyautogui.hotkey("ctrl", "home") if _OS != "Darwin" else pyautogui.hotkey("command", "up")
def scroll_bottom(): pyautogui.hotkey("ctrl", "end")  if _OS != "Darwin" else pyautogui.hotkey("command", "down")
def page_up():       pyautogui.press("pageup")
def page_down():     pyautogui.press("pagedown")


def copy():
    if _OS == "Darwin": pyautogui.hotkey("command", "c")
    else:               pyautogui.hotkey("ctrl", "c")

def paste():
    if _OS == "Darwin": pyautogui.hotkey("command", "v")
    else:               pyautogui.hotkey("ctrl", "v")

def cut():
    if _OS == "Darwin": pyautogui.hotkey("command", "x")
    else:               pyautogui.hotkey("ctrl", "x")

def undo():
    if _OS == "Darwin": pyautogui.hotkey("command", "z")
    else:               pyautogui.hotkey("ctrl", "z")

def redo():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "z")
    else:               pyautogui.hotkey("ctrl", "y")

def select_all():
    if _OS == "Darwin": pyautogui.hotkey("command", "a")
    else:               pyautogui.hotkey("ctrl", "a")

def save_file():
    if _OS == "Darwin": pyautogui.hotkey("command", "s")
    else:               pyautogui.hotkey("ctrl", "s")

def press_enter():  pyautogui.press("enter")
def press_escape(): pyautogui.press("escape")
def press_key(key: str): pyautogui.press(key)

def type_text(text: str, press_enter_after: bool = False):
    if not text:
        return
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        paste()
    else:
        pyautogui.write(str(text), interval=0.03)
    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")

def write_on_screen(text: str):
    type_text(text)

def take_screenshot():
    if _OS == "Windows":
        pyautogui.hotkey("win", "shift", "s")
    elif _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "3")
    else:
        pyautogui.hotkey("ctrl", "print_screen")

def lock_screen():
    if _OS == "Windows":
        pyautogui.hotkey("win", "l")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"])
    else:
        subprocess.run(["gnome-screensaver-command", "-l"])

def open_system_settings():
    if _OS == "Windows":
        pyautogui.hotkey("win", "i")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "System Preferences"])
    else:
        subprocess.Popen(["gnome-control-center"])

def open_file_explorer():
    if _OS == "Windows":
        pyautogui.hotkey("win", "e")
    elif _OS == "Darwin":
        subprocess.Popen(["open", Path.home()])
    else:
        subprocess.Popen(["xdg-open", Path.home()])

def open_run():
    if _OS == "Windows":
        pyautogui.hotkey("win", "r")

def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception:
            pass
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"])
    else:
        subprocess.run(["xset", "dpms", "force", "off"])

def restart_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/r", "/t", "5"])
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to restart'])
    else:
        subprocess.run(["sudo", "reboot"])

def shutdown_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/s", "/t", "5"])
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", 'tell application "System Events" to shut down'])
    else:
        subprocess.run(["sudo", "shutdown", "-h", "now"])

def dark_mode():
    if _OS == "Windows":
        pyautogui.hotkey("win", "a")
        time.sleep(0.3)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'])

def toggle_wifi():
    if _OS == "Windows":
        pyautogui.hotkey("win", "a")
        time.sleep(0.3)
    elif _OS == "Darwin":
        subprocess.run(["networksetup", "-setairportpower", "en0", "toggle"])
    else:
        subprocess.run(["nmcli", "radio", "wifi"])

ACTION_MAP = {
    "volume_up":               volume_up,
    "volume_down":             volume_down,
    "mute":                    volume_mute,
    "unmute":                  volume_mute,
    "volume_increase":         volume_up,
    "volume_decrease":         volume_down,
    "increase_volume":         volume_up,
    "decrease_volume":         volume_down,
    "turn_up_volume":          volume_up,
    "turn_down_volume":        volume_down,
    "louder":                  volume_up,
    "quieter":                 volume_down,
    "silence":                 volume_mute,
    "toggle_mute":             volume_mute,
    "brightness_up":           brightness_up,
    "brightness_down":         brightness_down,
    "increase_brightness":     brightness_up,
    "decrease_brightness":     brightness_down,
    "brighter":                brightness_up,
    "dimmer":                  brightness_down,
    "dim_screen":              brightness_down,
    "brighten_screen":         brightness_up,
    "sleep_display":           sleep_display,
    "turn_off_screen":         sleep_display,
    "screen_off":              sleep_display,
    "display_off":             sleep_display,
    "change_screen":           sleep_display,
    "screen_sleep":            sleep_display,
    "monitor_off":             sleep_display,
    "turn_off_monitor":        sleep_display,
    "pause_video":             pause_video,
    "play_video":              pause_video,
    "pause":                   pause_video,
    "play":                    pause_video,
    "toggle_play":             pause_video,
    "stop_video":              pause_video,
    "resume_video":            pause_video,
    "close_app":               close_app,
    "close_window":            close_window,
    "quit_app":                close_app,
    "exit_app":                close_app,
    "kill_app":                close_app,
    "full_screen":             full_screen,
    "fullscreen":              full_screen,
    "toggle_fullscreen":       full_screen,
    "minimize":                minimize_window,
    "minimize_window":         minimize_window,
    "maximize":                maximize_window,
    "maximize_window":         maximize_window,
    "restore_window":          maximize_window,
    "snap_left":               snap_left,
    "snap_right":              snap_right,
    "window_left":             snap_left,
    "window_right":            snap_right,
    "switch_window":           switch_window,
    "alt_tab":                 switch_window,
    "next_window":             switch_window,
    "show_desktop":            show_desktop,
    "desktop":                 show_desktop,
    "hide_windows":            show_desktop,
    "task_manager":            open_task_manager,
    "open_task_manager":       open_task_manager,
    "task_view":               open_task_view,
    "screenshot":              take_screenshot,
    "take_screenshot":         take_screenshot,
    "capture_screen":          take_screenshot,
    "lock_screen":             lock_screen,
    "lock":                    lock_screen,
    "open_settings":           open_system_settings,
    "system_settings":         open_system_settings,
    "settings":                open_system_settings,
    "preferences":             open_system_settings,
    "file_explorer":           open_file_explorer,
    "open_explorer":           open_file_explorer,
    "explorer":                open_file_explorer,
    "open_files":              open_file_explorer,
    "run":                     open_run,
    "open_run":                open_run,
    "restart":                 restart_computer,
    "restart_computer":        restart_computer,
    "reboot":                  restart_computer,
    "reboot_computer":         restart_computer,
    "shutdown":                shutdown_computer,
    "shut_down":               shutdown_computer,
    "power_off":               shutdown_computer,
    "turn_off_computer":       shutdown_computer,
    "dark_mode":               dark_mode,
    "toggle_dark_mode":        dark_mode,
    "night_mode":              dark_mode,
    "toggle_wifi":             toggle_wifi,
    "wifi":                    toggle_wifi,
    "wifi_toggle":             toggle_wifi,
    "focus_search":            focus_search,
    "address_bar":             focus_search,
    "url_bar":                 focus_search,
    "refresh_page":            refresh_page,
    "reload_page":             refresh_page,
    "reload":                  refresh_page,
    "refresh":                 refresh_page,
    "close_tab":               close_tab,
    "new_tab":                 new_tab,
    "open_tab":                new_tab,
    "next_tab":                next_tab,
    "prev_tab":                prev_tab,
    "previous_tab":            prev_tab,
    "go_back":                 go_back,
    "back":                    go_back,
    "go_forward":              go_forward,
    "forward":                 go_forward,
    "zoom_in":                 zoom_in,
    "zoom_out":                zoom_out,
    "zoom_reset":              zoom_reset,
    "reset_zoom":              zoom_reset,
    "find_on_page":            find_on_page,
    "search_page":             find_on_page,
    "scroll_up":               scroll_up,
    "scroll_down":             scroll_down,
    "scroll_top":              scroll_top,
    "scroll_bottom":           scroll_bottom,
    "top_of_page":             scroll_top,
    "bottom_of_page":          scroll_bottom,
    "page_up":                 page_up,
    "page_down":               page_down,
    "copy":                    copy,
    "paste":                   paste,
    "cut":                     cut,
    "undo":                    undo,
    "redo":                    redo,
    "select_all":              select_all,
    "save":                    save_file,
    "save_file":               save_file,
    "enter":                   press_enter,
    "press_enter":             press_enter,
    "escape":                  press_escape,
    "press_escape":            press_escape,
    "cancel":                  press_escape,
}

def _detect_action(description: str) -> dict:
    """
    Gemini ile kullanıcının ne yapmak istediğini anlar.
    Herhangi bir dilde çalışır.
    Döner: {"action": str, "value": optional}
    """
    import google.generativeai as genai
    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    available = ", ".join(sorted(ACTION_MAP.keys())) + ", volume_set, type_text, write_on_screen, reload_n, press_key"

    prompt = f"""The user wants to control their computer. Detect their intent.

User said (in any language): "{description}"

Available actions: {available}

Return ONLY valid JSON:
{{"action": "action_name", "value": null_or_value}}

Examples:
- "turn up the volume" → {{"action": "volume_up", "value": null}}
- "set volume to 60" → {{"action": "volume_set", "value": 60}}
- "sesi 80 yap" → {{"action": "volume_set", "value": 80}}
- "close the app" → {{"action": "close_app", "value": null}}
- "uygulamayı kapat" → {{"action": "close_app", "value": null}}
- "type hello world" → {{"action": "type_text", "value": "hello world"}}
- "write good morning on screen" → {{"action": "write_on_screen", "value": "good morning"}}
- "reload page 3 times" → {{"action": "reload_n", "value": 3}}
- "tam ekran yap" → {{"action": "full_screen", "value": null}}
- "sesi kıs" → {{"action": "volume_down", "value": null}}
- "sesi aç" → {{"action": "volume_up", "value": null}}
- "sustur" → {{"action": "mute", "value": null}}
- "monte le son" → {{"action": "volume_up", "value": null}}
- "ekranı kapat" → {{"action": "sleep_display", "value": null}}
- "monitörü kapat" → {{"action": "sleep_display", "value": null}}
- "turn off screen" → {{"action": "sleep_display", "value": null}}
- "turn off monitor" → {{"action": "sleep_display", "value": null}}
- "bilgisayarı yeniden başlat" → {{"action": "restart", "value": null}}
- "restart the computer" → {{"action": "restart", "value": null}}
- "bilgisayarı kapat" → {{"action": "shutdown", "value": null}}
- "shut down" → {{"action": "shutdown", "value": null}}
- "ekranı kilitle" → {{"action": "lock_screen", "value": null}}
- "lock the screen" → {{"action": "lock_screen", "value": null}}
- "küçült" → {{"action": "minimize", "value": null}}
- "minimize the window" → {{"action": "minimize", "value": null}}
- "büyüt" → {{"action": "maximize", "value": null}}
- "parlaklığı artır" → {{"action": "brightness_up", "value": null}}
- "parlaklığı azalt" → {{"action": "brightness_down", "value": null}}
- "increase brightness" → {{"action": "brightness_up", "value": null}}
- "wifi'yi aç" → {{"action": "toggle_wifi", "value": null}}
- "toggle wifi" → {{"action": "toggle_wifi", "value": null}}
- "masaüstünü göster" → {{"action": "show_desktop", "value": null}}
- "show desktop" → {{"action": "show_desktop", "value": null}}
- "yeni sekme aç" → {{"action": "new_tab", "value": null}}
- "sekmeyi kapat" → {{"action": "close_tab", "value": null}}
- "geri git" → {{"action": "go_back", "value": null}}
- "ileri git" → {{"action": "go_forward", "value": null}}
- "sayfayı yenile" → {{"action": "refresh_page", "value": null}}
- "yakınlaştır" → {{"action": "zoom_in", "value": null}}
- "uzaklaştır" → {{"action": "zoom_out", "value": null}}
- "kaydet" → {{"action": "save", "value": null}}
- "geri al" → {{"action": "undo", "value": null}}
- "screenshot al" → {{"action": "screenshot", "value": null}}
- "ekran görüntüsü al" → {{"action": "screenshot", "value": null}}
- "aşağı kaydır" → {{"action": "scroll_down", "value": null}}
- "yukarı kaydır" → {{"action": "scroll_up", "value": null}}
- "karanlık mod" → {{"action": "dark_mode", "value": null}}
- "press f5" → {{"action": "press_key", "value": "f5"}}
- "enter'a bas" → {{"action": "enter", "value": null}}
- "escape'e bas" → {{"action": "escape", "value": null}}

IMPORTANT:
- Always return one of the available actions listed above.
- If the user's intent is clear but uses different wording, map it to the closest action.
- Never invent new action names not in the available list.
- Return ONLY the JSON object, no explanation, no markdown."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        text = __import__("re").sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Settings] ⚠️ Intent detection failed: {e}")
        return {"action": description.lower().replace(" ", "_"), "value": None}

def computer_settings(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Bilgisayar ayarları ve UI kontrolleri.

    parameters:
        action      : İşlem adı (verilmezse description'dan Gemini ile tespit edilir)
        description : Kullanıcının doğal dil komutu (herhangi bir dilde)
        value       : İşleme özgü değer (ses seviyesi, yazılacak metin, tekrar sayısı vb.)
    """
    if not _PYAUTOGUI:
        return "pyautogui is not installed. Run: pip install pyautogui"

    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)

    if not raw_action and description:
        detected   = _detect_action(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "No action could be determined, sir."

    print(f"[Settings] ⚙️ Action: {action}  Value: {value}")


    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"Volume set to {value}%."
        except Exception as e:
            return f"Could not set volume: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", ""))
        if not text:
            return "No text provided to type, sir."
        enter_after = bool(params.get("press_enter", False))
        type_text(text, press_enter_after=enter_after)
        return f"Typed: {text[:60]}"

    if action == "press_key":
        key = str(value or params.get("key", ""))
        if not key:
            return "No key specified, sir."
        press_key(key)
        return f"Pressed: {key}"

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            n = int(value or 1)
            reload_page_n(n)
            return f"Reloaded page {n} time{'s' if n > 1 else ''}."
        except Exception as e:
            return f"Could not reload: {e}"

    if action in ("scroll_up", "scroll_down"):
        try:
            amount = int(value or 500)
            scroll_up(amount) if action == "scroll_up" else scroll_down(amount)
            return f"Scrolled {'up' if action == 'scroll_up' else 'down'}."
        except Exception as e:
            return f"Scroll failed: {e}"

    func = ACTION_MAP.get(action)
    if not func:
        return f"Unknown action: '{raw_action}', sir."

    try:
        func()
        return f"Done: {action}."
    except Exception as e:
        return f"Action failed ({action}): {e}"