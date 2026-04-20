import asyncio
import re
import threading
import json
import sys
import traceback
import platform
from pathlib import Path
from datetime import datetime

import sounddevice as sd
from google import genai
from google.genai import types
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings, get_system_status as from_settings_get_status, media_control as from_settings_media_control
from actions.screen_processor  import screen_process, capture_screen
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from agent.tool_registry       import tool_registry

def get_os() -> str:
    s = platform.system().lower()
    if s == "darwin": return "mac"
    if s == "windows": return "windows"
    return "linux"

BASE_DIR        = Path(__file__).resolve().parent
CONFIG_DIR      = BASE_DIR / "config"
API_CONFIG_PATH = CONFIG_DIR / "api_keys.json"

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1024

LIVE_MODEL          = "models/gemini-3.1-flash-live-preview"

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for information using DuckDuckGo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a message via various platforms (WhatsApp, Telegram, etc.)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver": {"type": "STRING", "description": "Name of the person or group"},
                "message_text": {"type": "STRING", "description": "Content of the message"},
                "platform": {"type": "STRING", "description": "Platform to use (e.g. 'whatsapp', 'telegram')"}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a reminder for the user.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {"type": "STRING", "description": "Date (YYYY-MM-DD)"},
                "time": {"type": "STRING", "description": "Time (HH:MM)"},
                "message": {"type": "STRING", "description": "Reminder content"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "computer_settings",
        "description": "Manages computer settings (volume, brightness, wifi, dark mode, etc.)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Action to perform (e.g. 'volume_up', 'brightness_down', 'toggle_wifi', 'dark_mode')"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, I will automatically receive the current image and will be able to describe it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "youtube_video",
        "description": "Searches for and plays a video on YouTube.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The search query for YouTube"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop (mouse, keyboard, shortcuts).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Action to perform (e.g. 'maximize_window', 'minimize_window', 'press_enter', 'scroll_down')"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "browser_control",
        "description": "Controls the web browser for advanced tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "URL to navigate to"},
                "task": {"type": "STRING", "description": "Task to perform on the page"}
            },
            "required": []
        }
    },
    {
        "name": "file_controller",
        "description": "Manages local files and directories.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Action to perform (e.g. 'list_files', 'read_file', 'create_dir', 'delete_file')"},
                "path": {"type": "STRING", "description": "Target path"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Assists with coding tasks, debugging, and analysis.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {"type": "STRING", "description": "Coding task or question"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "dev_agent",
        "description": "An advanced developer agent for complex software engineering tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "Comprehensive engineering goal"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "agent_task",
        "description": "Submits a long-running goal to the Jarvis background agent queue.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "The background task goal"},
                "priority": {"type": "STRING", "description": "Priority: low, normal, high"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "save_memory",
        "description": "Saves a piece of information to long-term memory for future reference.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "Memory category"},
                "key": {"type": "STRING", "description": "Unique identifier"},
                "value": {"type": "STRING", "description": "Information to remember"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "flight_finder",
        "description": "Finds flights for given criteria.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "from": {"type": "STRING", "description": "Departure city"},
                "to": {"type": "STRING", "description": "Arrival city"},
                "date": {"type": "STRING", "description": "Date"}
            },
            "required": ["from", "to", "date"]
        }
    },
    {
        "name": "game_updater",
        "description": "Checks for and manages game updates.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "game": {"type": "STRING", "description": "Game name"}
            },
            "required": ["game"]
        }
    },
    {
        "name": "media_control",
        "description": "Controls media playback such as play/pause, next track, or previous track.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Playback action: 'play_pause', 'next', or 'prev'"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "get_system_status",
        "description": "Returns information about the current system status including CPU and RAM usage.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "shutdown_jarvis",
        "description": "Safely shuts down the Jarvis system.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    }
]

def _get_api_key():
    if not API_CONFIG_PATH.exists():
        raise FileNotFoundError(f"API config not found at {API_CONFIG_PATH}")
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

def _clean_transcript(text: str) -> str:
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    return text.strip()

class JarvisLive:
    def __init__(self, ui):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

        # Cache system prompt
        sys_prompt_path = BASE_DIR / "core" / "prompt.txt"
        self._sys_prompt = sys_prompt_path.read_text(encoding="utf-8") if sys_prompt_path.exists() else "You are JARVIS."

        self.TOOL_MAP = {
            "open_app":          open_app,
            "web_search":        web_search_action,
            "weather_report":    weather_action,
            "send_message":      send_message,
            "reminder":          reminder,
            "computer_settings": computer_settings,
            "youtube_video":     youtube_video,
            "desktop_control":   desktop_control,
            "browser_control":   browser_control,
            "file_controller":   file_controller,
            "code_helper":       code_helper,
            "dev_agent":         dev_agent,
            "game_updater":      game_updater,
            "get_system_status": from_settings_get_status,
            "media_control":     from_settings_media_control,
        }

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_realtime_input(text=text or "."),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        else:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        print(f"[Jarvis] 🗣 {text}")
        self.ui.write_log(f"Jarvis: {text}")

    def speak_error(self, tool_name: str, error: Exception):
        msg = f"Sir, the {tool_name} tool encountered an error: {error}"
        self.speak(msg)

    def _build_config(self):
        mem      = load_memory()
        mem_str  = format_memory_for_prompt(mem)
        
        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(self._sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        arg_str = ", ".join(f"{k}={v}" for k, v in args.items()) if args else "no params"
        self.ui.write_log(f"SYS: Running {name} ({arg_str})")
        self.ui.set_state("THINKING")

        # Core tools that need direct session access or simple memory updates
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop = asyncio.get_running_loop()
        result = "Done."

        try:
            # Registry-based dispatch
            if name == "screen_process":
                # Special handling for 2-frame capture
                angle = args.get("angle", "screen").lower().strip()
                user_query = args.get("text", "Analyze the image and answer briefly.")
                print(f"[Vision] 📸 Capturing sequence for {angle}...")
                
                frames = []
                for _ in range(2):
                    try:
                        if angle == "camera":
                            from actions.screen_processor import _capture_camera
                            p, m = _capture_camera()
                        else:
                            from actions.screen_processor import _capture_screen
                            p, m = _capture_screen()
                        if isinstance(p, bytes): frames.append(p)
                    except Exception as e: print(f"[Vision] ⚠️ {e}")
                    await asyncio.sleep(0.4)

                if frames:
                    for f_data in frames:
                        await self.session.send_realtime_input(video=types.Blob(data=f_data, mime_type="image/jpeg"))
                    await self.session.send_realtime_input(text=user_query)
                    result = f"Video sequence sent. Analyzing {angle}..."
                else:
                    result = f"Failed to capture {angle}."

            elif name in self.TOOL_MAP:
                handler = self.TOOL_MAP[name]
                # Check if it needs extra params
                if name in ["send_message"]:
                    r = await loop.run_in_executor(None, lambda: handler(parameters=args, response=None, player=self.ui, session_memory=None))
                elif name in ["code_helper", "dev_agent", "game_updater"]:
                    r = await loop.run_in_executor(None, lambda: handler(parameters=args, player=self.ui, speak=self.speak))
                else:
                    r = await loop.run_in_executor(None, lambda: handler(parameters=args, player=self.ui))
                result = r or "Done."
            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            if "mime_type" in msg and msg["mime_type"].startswith("audio/"):
                await self.session.send_realtime_input(
                    audio=types.Blob(
                        data=msg["data"], mime_type="audio/pcm;rate=16000"
                    )
                )
            elif "mime_type" in msg and msg["mime_type"].startswith("image/"):
                await self.session.send_realtime_input(
                    video=types.Blob(
                        data=msg["data"], mime_type=msg["mime_type"]
                    )
                )
            elif "text" in msg:
                await self.session.send_realtime_input(text=msg["text"])
            else:
                await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                def _safe_put():
                    try:
                        self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                    except asyncio.QueueFull:
                        pass
                loop.call_soon_threadsafe(_safe_put)

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():
                    
                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                        
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.text:
                                    in_buf.append(part.text)
                        
                        if sc.turn_complete:
                            full_out = " ".join(out_buf).strip()
                            full_in  = " ".join(in_buf).strip()
                            if full_out:
                                print(f"[You] {full_out}")
                            if full_in:
                                print(f"[Jarvis] {full_in}")
                                self.ui.write_log(f"Jarvis: {full_in}")
                            out_buf, in_buf = [], []
                            self._turn_done_event.set()

                    if response.tool_call:
                        for fc in response.tool_call.function_calls:
                            res = await self._execute_tool(fc)
                            await self.session.send_tool_response(function_responses=[res])

        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                    continue

                self.set_speaking(True)
                stream.write(chunk)

        except Exception as e:
            print(f"[JARVIS] 🔊 Play Error: {e}")
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1alpha"}
        )
        config = self._build_config()

        backoff = 3
        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=100)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")
                    backoff = 3

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()

            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print(f"[JARVIS] 🔄 Reconnecting in {int(backoff)}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 60)

def main():
    from ui import JarvisUI
    ui = JarvisUI("logo.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()

