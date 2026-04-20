from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import sys
import subprocess
import tempfile
import uuid
import shutil
import select
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

from google import genai
from google.genai import types as gtypes

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")


def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found in config.")
    return key


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()

_LIVE_MODEL         = "models/gemini-3.1-flash-live-preview"
_CHANNELS           = 1
_RECEIVE_SAMPLE_RATE = 24_000
_CHUNK_SIZE         = 1_024

_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q    = 60

_SYSTEM_PROMPT = (
    "You are JARVIS, an advanced AI assistant. "
    "Analyze the provided image with precision and intelligence. "
    "Be concise and direct — maximum two sentences unless the user's question "
    "requires more detail. "
    "Address the user respectfully. "
    "Always call the appropriate tool; never simulate results."
)


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"


# === LINUX WAYLAND COMPATIBLE SCREEN CAPTURE ===
def _encode_screen_image(image) -> bytes:
    import io

    from PIL import Image

    if image.mode != "RGB":
        image = image.convert("RGB")

    image.thumbnail((1280, 720), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def _capture_screen_with_mss() -> bytes:
    import mss
    from PIL import Image

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        grabbed = sct.grab(monitor)
        image = Image.frombytes("RGB", grabbed.size, grabbed.bgra, "raw", "BGRX")
        return _encode_screen_image(image)


def _capture_screen_with_file_backend(command: list[str]) -> bytes:
    from PIL import Image

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        completed = subprocess.run(
            [*command, tmp_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        _ = completed

        with Image.open(tmp_path) as image:
            return _encode_screen_image(image)
    except FileNotFoundError as exc:
        raise RuntimeError(f"{command[0]} is not installed") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if stderr:
            raise RuntimeError(f"{command[0]} failed: {stderr}") from exc
        raise RuntimeError(f"{command[0]} failed with exit code {exc.returncode}") from exc
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass


def _capture_screen_with_wayland() -> bytes:
    errors = []

    try:
        return _capture_screen_with_portal_system_python()
    except Exception as exc:
        errors.append(f"portal: {exc}")

    if shutil.which("grim"):
        try:
            return _capture_screen_with_file_backend(["grim"])
        except Exception as exc:
            errors.append(f"grim: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))

    raise RuntimeError(
        "Wayland session detected, but no supported screenshot backend is installed. "
        "Install 'xdg-desktop-portal' and, on GNOME, 'xdg-desktop-portal-gnome'; "
        "or use 'grim'."
    )


def _find_system_python() -> str | None:
    candidates = [
        "/usr/bin/python3",
        "/usr/bin/python",
        os.path.join(sys.base_prefix, "bin", "python3"),
        os.path.join(sys.base_prefix, "bin", "python"),
        shutil.which("python3"),
        shutil.which("python"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.exists(candidate):
            probe = subprocess.run(
                [
                    candidate,
                    "-c",
                    "import dbus, gi; print('ok')",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if probe.returncode == 0:
                return candidate
    return None


def _capture_screen_with_portal_system_python() -> bytes:
    helper_python = _find_system_python()
    if not helper_python:
        raise RuntimeError("could not find a system Python with portal support")

    helper_script = r'''
import dbus
import dbus.mainloop.glib
import json
import sys
import subprocess
import tempfile
import uuid
import shutil
import select
import uuid
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
token = "jarvis_" + uuid.uuid4().hex
unique_name = bus.get_unique_name().replace(":", "").replace(".", "_")
handle_path = f"/org/freedesktop/portal/desktop/request/{unique_name}/{token}"
result = {}

def on_response(response, results):
    result["response"] = int(response)
    try:
        result["results"] = dict(results)
    except Exception:
        result["results"] = {"_raw": str(results)}
    loop.quit()

bus.add_signal_receiver(
    on_response,
    signal_name="Response",
    dbus_interface="org.freedesktop.portal.Request",
    path=handle_path,
)

proxy = bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
iface = dbus.Interface(proxy, "org.freedesktop.portal.Screenshot")
options = dbus.Dictionary(
    {
        "handle_token": token,
        "modal": dbus.Boolean(True),
        "interactive": dbus.Boolean(False),
    },
    signature="sv",
)

loop = GLib.MainLoop()
iface.Screenshot("", options, timeout=5000)

def on_timeout():
    if "response" not in result:
        result["error"] = "timed out waiting for portal response"
        loop.quit()
    return False

GLib.timeout_add_seconds(12, on_timeout)
loop.run()

print(json.dumps(result))
'''

    completed = subprocess.run(
        [helper_python, "-c", helper_script],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"portal helper failed: {detail}")

    payload = (completed.stdout or "").strip()
    if not payload:
        raise RuntimeError("portal helper returned no data")

    try:
        result = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"portal helper returned invalid JSON: {payload!r}") from exc

    if "error" in result:
        raise RuntimeError(result["error"])

    if int(result.get("response", -1)) != 0:
        raise RuntimeError("portal screenshot was denied or cancelled")

    uri = str((result.get("results") or {}).get("uri", ""))
    if not uri:
        raise RuntimeError("portal screenshot did not return an image URI")

    from urllib.parse import unquote, urlparse
    from PIL import Image

    file_path = unquote(urlparse(uri).path)
    if not file_path:
        raise RuntimeError(f"portal returned a non-local URI: {uri}")

    with Image.open(file_path) as image:
        image.load()
        return _encode_screen_image(image)


def _capture_screen_with_portal_qtdbus() -> bytes:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise RuntimeError("cannot access session D-Bus")

    token = f"jarvis_{uuid.uuid4().hex}"
    options = {
        "handle_token": token,
        "modal": True,
        "interactive": False,
    }

    request = QDBusMessage.createMethodCall(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot",
        "Screenshot",
    )
    request.setArguments(["", options])

    reply = bus.call(request, QDBus.CallMode.Block, 5000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        detail = reply.errorMessage() or reply.errorName() or "unknown error"
        raise RuntimeError(f"portal call failed: {detail}")

    reply_args = reply.arguments()
    if not reply_args:
        raise RuntimeError("portal call did not return a request handle")

    handle_path = str(reply_args[0])
    if not handle_path:
        raise RuntimeError("portal call returned an empty request handle")

    class _PortalResponseReceiver(QObject):
        def __init__(self):
            super().__init__()
            self.response_code = None
            self.results = None
            self.loop = None

        @pyqtSlot(int, "QVariantMap")
        def on_response(self, response_code, results):
            if self.response_code is not None:
                return
            self.response_code = int(response_code)
            if isinstance(results, dict):
                self.results = results
            else:
                try:
                    self.results = dict(results)
                except Exception:
                    self.results = {"_raw": results}
            if self.loop is not None and self.loop.isRunning():
                self.loop.quit()

    receiver = _PortalResponseReceiver()
    connected = bus.connect(
        "org.freedesktop.portal.Desktop",
        handle_path,
        "org.freedesktop.portal.Request",
        "Response",
        "ua{sv}",
        receiver.on_response,
    )
    if not connected:
        raise RuntimeError("could not subscribe to portal response")

    loop = QEventLoop()
    receiver.loop = loop
    timeout_ms = 12000
    QTimer.singleShot(timeout_ms, loop.quit)

    try:
        loop.exec()
    finally:
        try:
            bus.disconnect(
                "org.freedesktop.portal.Desktop",
                handle_path,
                "org.freedesktop.portal.Request",
                "Response",
                "ua{sv}",
                receiver.on_response,
            )
        except Exception:
            pass

    if receiver.response_code is None:
        raise RuntimeError(f"timed out waiting for portal response after {timeout_ms // 1000}s")

    if receiver.response_code != 0:
        raise RuntimeError("portal screenshot was denied or cancelled")

    uri = str((receiver.results or {}).get("uri", ""))
    if not uri:
        raise RuntimeError("portal response did not include a screenshot URI")

    from urllib.parse import unquote, urlparse
    from PIL import Image

    file_path = unquote(urlparse(uri).path)
    if not file_path:
        raise RuntimeError(f"portal returned a non-local URI: {uri}")

    with Image.open(file_path) as image:
        image.load()
        return _encode_screen_image(image)


def _capture_screen_with_portal_via_gdbus() -> bytes:
    token = f"jarvis_{uuid.uuid4().hex}"
    options = "{'handle_token': <'%s'>, 'modal': <true>, 'interactive': <false>}" % token
    monitor_cmd = [
        "dbus-monitor",
        "--session",
        "type='signal',interface='org.freedesktop.portal.Request',member='Response'",
    ]
    monitor = subprocess.Popen(
        monitor_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    time.sleep(0.2)

    call_cmd = [
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.freedesktop.portal.Desktop",
        "--object-path",
        "/org/freedesktop/portal/desktop",
        "--method",
        "org.freedesktop.portal.Screenshot.Screenshot",
        "",
        options,
    ]

    completed = subprocess.run(
        call_cmd,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"gdbus portal call failed: {detail}")

    handle_match = re.search(
        r"(/org/freedesktop/portal/desktop/request/[^\s'\"()]+)",
        completed.stdout or "",
    )
    if not handle_match:
        raise RuntimeError(f"could not parse portal request handle from: {completed.stdout!r}")
    handle_path = handle_match.group(1)

    lines = []
    uri = None
    response_code = None
    deadline = time.time() + 30.0

    try:
        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            ready, _, _ = select.select([monitor.stdout], [], [], min(0.5, remaining))
            if not ready:
                if monitor.poll() is not None:
                    break
                continue

            line = monitor.stdout.readline()
            if not line:
                if monitor.poll() is not None:
                    break
                continue

            lines.append(line.rstrip())

            if response_code is None:
                match = re.search(r"uint32\s+(\d+)", line)
                if match:
                    response_code = int(match.group(1))

            if uri is None:
                match = re.search(r"file://[^\s'\"<>]+", line)
                if match:
                    uri = match.group(0)

            if handle_path not in "".join(lines):
                continue

            if response_code is not None and uri is not None:
                break
    finally:
        try:
            monitor.terminate()
        except Exception:
            pass
        try:
            monitor.wait(timeout=3)
        except Exception:
            try:
                monitor.kill()
            except Exception:
                pass

    if response_code is None:
        raise RuntimeError(
            "timed out waiting for portal response; monitor output: "
            + " | ".join(lines[-5:])
        )
    if response_code != 0:
        raise RuntimeError("portal screenshot was denied or cancelled")
    if not uri:
        raise RuntimeError(
            "portal response did not include a screenshot URI; monitor output: "
            + " | ".join(lines[-5:])
        )

    from urllib.parse import urlparse, unquote
    from PIL import Image

    file_path = unquote(urlparse(uri).path)
    if not file_path:
        raise RuntimeError(f"portal returned a non-local URI: {uri}")

    with Image.open(file_path) as image:
        image.load()
        return _encode_screen_image(image)


def _capture_screen_with_portal() -> bytes:
    try:
        from gi.repository import Gio, GLib
    except Exception as exc:
        raise RuntimeError(f"portal backend unavailable: {exc}") from exc

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception as exc:
        raise RuntimeError(f"cannot access session bus: {exc}") from exc

    token = f"jarvis_{uuid.uuid4().hex}"
    unique_name = bus.get_unique_name().replace(":", "").replace(".", "_")
    handle_path = f"/org/freedesktop/portal/desktop/request/{unique_name}/{token}"

    options = GLib.Variant(
        "a{sv}",
        {
            "modal": GLib.Variant("b", True),
            "interactive": GLib.Variant("b", False),
            "handle_token": GLib.Variant("s", token),
        },
    )

    subscription_id = None
    result = {}
    loop = GLib.MainLoop()

    def on_response(
        connection, sender_name, object_path, interface_name, signal_name, parameters
    ):
        try:
            response_code, results = parameters.unpack()
        except Exception as exc:
            result["error"] = f"invalid portal response: {exc}"
        else:
            result["response"] = int(response_code)
            result["results"] = results
        loop.quit()

    subscription_id = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        handle_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )

    portal = Gio.DBusProxy.new_sync(
        bus,
        Gio.DBusProxyFlags.NONE,
        None,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot",
        None,
    )

    try:
        response = portal.call_sync(
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            Gio.DBusCallFlags.NONE,
            20000,
            None,
        )
    except Exception as exc:
        raise RuntimeError(f"portal request failed: {exc}") from exc

    handle = response.unpack()[0]
    if handle != handle_path:
        try:
            bus.signal_unsubscribe(subscription_id)
        except Exception:
            pass
        handle_path = handle
        subscription_id = bus.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Request",
            "Response",
            handle_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
        )

    def on_timeout():
        result["error"] = "timed out waiting for portal response"
        loop.quit()
        return False

    timeout_id = GLib.timeout_add_seconds(20, on_timeout)
    try:
        loop.run()
    finally:
        try:
            GLib.source_remove(timeout_id)
        except Exception:
            pass
        try:
            bus.signal_unsubscribe(subscription_id)
        except Exception:
            pass

    if "error" in result:
        raise RuntimeError(result["error"])

    if result["response"] != 0:
        raise RuntimeError("portal screenshot was denied or cancelled")

    uri = str(result["results"].get("uri", ""))
    if not uri:
        raise RuntimeError("portal screenshot did not return an image URI")

    from PIL import Image
    file = Gio.File.new_for_uri(uri)
    path = file.get_path()
    if not path:
        raise RuntimeError(f"portal returned a non-local URI: {uri}")

    with Image.open(path) as image:
        image.load()
        return _encode_screen_image(image)


def capture_screen() -> bytes | str:
    """Capture the full desktop, downscale to 1280x720, and return JPEG bytes."""
    try:
        wayland_session = bool(
            os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE") == "wayland"
        )

        backends = (
            (_capture_screen_with_wayland, _capture_screen_with_mss)
            if wayland_session
            else (_capture_screen_with_mss, _capture_screen_with_wayland)
        )

        errors = []
        for backend in backends:
            try:
                return backend()
            except Exception as exc:
                errors.append(str(exc))

        if errors:
            return f"ERROR: {'; '.join(errors)}"
        return "ERROR: No screenshot backend is available."
    except Exception as exc:
        return f"ERROR: {exc}"



# ===============================================

def _capture_screen() -> tuple[bytes, str]:
    result = capture_screen()
    if isinstance(result, str) and result.startswith("ERROR"):
        raise RuntimeError(result)
    elif isinstance(result, str):
        # some other string?
        raise RuntimeError(result)
    return result, "image/jpeg"



def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW    
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION  
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")

    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"

class _VisionSession:
    def __init__(self):
        self._loop:       Optional[asyncio.AbstractEventLoop] = None
        self._thread:     Optional[threading.Thread]          = None
        self._session                                          = None
        self._out_queue:  Optional[asyncio.Queue]             = None
        self._audio_in:   Optional[asyncio.Queue]             = None
        self._ready_evt:  threading.Event                     = threading.Event()
        self._player                                           = None
        self._lock:       threading.Lock                       = threading.Lock()

    def start(self, player=None, timeout: float = 25.0) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if player is not None:
                    self._player = player
                return
            self._player = player
            self._thread = threading.Thread(
                target=self._run_event_loop,
                daemon=True,
                name="VisionSessionThread",
            )
            self._thread.start()

        if not self._ready_evt.wait(timeout=timeout):
            raise RuntimeError(f"Vision session did not connect within {timeout}s.")
        print("[Vision] ✅ Session ready")

    def analyze(self, image_bytes: bytes, mime_type: str, user_text: str) -> None:
        if not self._loop or not self._out_queue:
            print("[Vision] ⚠️  Session not started — dropping request")
            return
        asyncio.run_coroutine_threadsafe(
            self._out_queue.put((image_bytes, mime_type, user_text)),
            self._loop,
        )

    def is_ready(self) -> bool:
        return self._session is not None

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._session_loop())

    async def _session_loop(self) -> None:
        self._out_queue = asyncio.Queue(maxsize=30)
        self._audio_in  = asyncio.Queue()

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )
        config = gtypes.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            system_instruction=_SYSTEM_PROMPT,
            speech_config=gtypes.SpeechConfig(
                voice_config=gtypes.VoiceConfig(
                    prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

        backoff = 2.0
        while True:
            try:
                print("[Vision] 🔌 Connecting...")
                async with client.aio.live.connect(
                    model=_LIVE_MODEL, config=config
                ) as session:
                    self._session = session
                    self._ready_evt.set()
                    backoff = 2.0  
                    print("[Vision] ✅ Connected")

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_loop())
                        tg.create_task(self._recv_loop())
                        tg.create_task(self._play_loop())

            except Exception as eg:
                for exc in eg.exceptions:
                    print(f"[Vision] ⚠️  Session error: {exc}")
            finally:
                self._session = None
                self._ready_evt.clear()

            print(f"[Vision] 🔄 Reconnecting in {backoff:.0f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)
            self._ready_evt.set()  

    async def _send_loop(self) -> None:
        while True:
            image_bytes, mime_type, user_text = await self._out_queue.get()
            if not self._session:
                print("[Vision] ⚠️  No session — dropping image")
                continue
            try:
                b64 = base64.b64encode(image_bytes).decode("ascii")
                await self._session.send_client_content(
                    turns={
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": b64}},
                            {"text": user_text},
                        ]
                    },
                    turn_complete=True,
                )
                print(f"[Vision] 📤 Sent {len(image_bytes):,} bytes — '{user_text[:60]}'")
            except Exception as e:
                print(f"[Vision] ⚠️  Send error: {e}")

    async def _recv_loop(self) -> None:
        transcript: list[str] = []
        try:
            async for response in self._session.receive():
                if response.data:
                    await self._audio_in.put(response.data)

                sc = response.server_content
                if not sc:
                    continue

                if sc.output_transcription and sc.output_transcription.text:
                    chunk = sc.output_transcription.text.strip()
                    if chunk:
                        transcript.append(chunk)

                if sc.turn_complete:
                    if transcript and self._player:
                        full = re.sub(r"\s+", " ", " ".join(transcript)).strip()
                        if full:
                            self._player.write_log(f"Jarvis: {full}")
                            print(f"[Vision] 💬 {full}")
                    transcript = []

        except Exception as e:
            print(f"[Vision] ⚠️  Recv error: {e}")
            raise  

    async def _play_loop(self) -> None:
        stream = sd.RawOutputStream(
            samplerate=_RECEIVE_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            blocksize=_CHUNK_SIZE,
        )
        stream.start()
        try:
            while True:
                chunk = await self._audio_in.get()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[Vision] ❌ Play error: {e}")
            raise
        finally:
            stream.stop()
            stream.close()

_session      = _VisionSession()
_session_lock = threading.Lock()
_session_up   = False


def _ensure_session(player=None) -> None:
    global _session_up
    with _session_lock:
        if not _session_up:
            _session.start(player=player)
            _session_up = True
        elif player is not None:
            _session._player = player


def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> bool:

    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        print("[Vision] ⚠️  No question provided — aborting")
        return False

    print(f"[Vision] ▶ angle={angle!r}  question='{user_text[:80]}'")

    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ❌ Could not start session: {e}")
        return False

    try:
        if angle == "camera":
            image_bytes, mime_type = _capture_camera()
            print(f"[Vision] 📷 Camera: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Screen: {len(image_bytes):,} bytes")
    except Exception as e:
        print(f"[Vision] ❌ Capture error: {e}")
        return False

    _session.analyze(image_bytes, mime_type, user_text)
    return True


def warmup_session(player=None) -> None:
    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ⚠️  Warmup failed: {e}")

if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (default: screen): ").strip().lower() or "screen"
    q    = input("Question (Enter = default): ").strip() or "What do you see? Be brief."

    t0 = time.perf_counter()
    warmup_session()
    print(f"Session ready in {time.perf_counter()-t0:.2f}s\n")

    t1 = time.perf_counter()
    ok = screen_process({"angle": mode, "text": q})
    print(f"Queued in {time.perf_counter()-t1:.3f}s — waiting for audio...")
    time.sleep(10)
    print("Done." if ok else "Failed.")
