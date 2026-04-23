"""
Wake word listener — say "Hey Ali" to launch or wake Ali.
Uses sounddevice (no pyaudio) + Google speech recognition.

If main.py is already running (passive mode), writes a signal file instead
of launching a new process — main.py watches that file and wakes up.
"""
import subprocess, sys, time, io, wave, threading, queue
from pathlib import Path
import numpy as np
import sounddevice as sd
import speech_recognition as sr

SAMPLE_RATE  = 16000
WAKE_WORDS   = [
    "hey ali", "ali", "hi ali", "hello ali",
    "okay ali", "ok ali", "hey aly", "hey al",
    "hey ally", "ali please", "hey there", "ali open",
    "hey", "open ali",
]
MAIN_SCRIPT  = "main.py"
BASE_DIR     = Path(__file__).resolve().parent
WAKE_SIGNAL  = BASE_DIR / ".wake_signal"   # watched by main.py passive mode

recognizer   = sr.Recognizer()
audio_q      = queue.Queue(maxsize=4)
ali_process  = None


def is_ali_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", MAIN_SCRIPT],
                           capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def wake_ali():
    """Either signal a running Ali to wake, or launch a fresh process."""
    global ali_process
    if is_ali_running():
        # Ali is already open but may be in passive mode — send wake signal
        WAKE_SIGNAL.touch()
        print("  [Wake signal sent to running Ali]")
        return
    print("🚀 Launching Ali...")
    ali_process = subprocess.Popen(
        [sys.executable, str(BASE_DIR / MAIN_SCRIPT)],
        cwd=str(BASE_DIR),
    )


def to_wav_bytes(samples: np.ndarray) -> bytes:
    pcm = (samples * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def recognize_worker():
    while True:
        samples = audio_q.get()
        if samples is None:
            break
        try:
            wav   = to_wav_bytes(samples)
            adata = sr.AudioData(wav, SAMPLE_RATE, 2)
            text  = recognizer.recognize_google(adata, language="en-US").lower().strip()
            print(f'  Heard: "{text}"')
            if any(w in text for w in WAKE_WORDS):
                print("✅ Wake word detected!")
                wake_ali()
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            print(f"  [API error: {e}]")
        except Exception as e:
            print(f"  [Recognize error: {e}]")
        finally:
            audio_q.task_done()


def listen_loop():
    # Calibrate energy threshold from 1 second of silence
    print("🎙  Calibrating microphone (stay quiet for 1s)...")
    cal = sd.rec(SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    rms = float(np.sqrt(np.mean(cal ** 2)))
    # 3.5x ambient noise — sensitive enough to catch "Hey Ali" from normal distance
    threshold = max(rms * 3.5, 0.004)
    print(f"✅ Threshold: {threshold:.4f}  (ambient RMS: {rms:.4f})")
    print(f"👂 Listening for: {WAKE_WORDS[:5]} ...")
    print("   Just say 'Hey Ali' (or 'Ali') to open the assistant.\n")

    worker = threading.Thread(target=recognize_worker, daemon=True)
    worker.start()

    BLOCK       = int(0.05 * SAMPLE_RATE)   # 50ms blocks
    SPEECH_SEC  = 1.5                        # collect up to 1.5s — faster for short phrases
    PRE_ROLL    = int(0.25 * SAMPLE_RATE)    # 250ms pre-roll
    ring        = np.zeros(PRE_ROLL, dtype="float32")
    collecting  = False
    collected   = []
    silence_n   = 0
    SILENCE_MAX = int(0.6 * SAMPLE_RATE / BLOCK)   # 0.6s silence ends phrase

    def callback(indata, frames, t, status):
        nonlocal collecting, collected, silence_n, ring
        chunk = indata[:, 0].copy()
        ring  = np.concatenate([ring, chunk])[-PRE_ROLL:]
        level = float(np.sqrt(np.mean(chunk ** 2)))

        if not collecting:
            if level > threshold:
                print(f"  🔊 Speech detected (level={level:.4f})")
                collecting = True
                collected  = [ring.copy(), chunk]
                silence_n  = 0
        else:
            collected.append(chunk)
            if level < threshold * 0.35:
                silence_n += 1
            else:
                silence_n = 0

            total_samples = sum(len(c) for c in collected)
            if silence_n >= SILENCE_MAX or total_samples >= int(SPEECH_SEC * SAMPLE_RATE):
                phrase     = np.concatenate(collected)
                collected  = []
                collecting = False
                silence_n  = 0
                if not audio_q.full():
                    audio_q.put(phrase)

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", blocksize=BLOCK,
                            callback=callback):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[Wake] Stopped.")
        audio_q.put(None)


if __name__ == "__main__":
    while True:
        try:
            listen_loop()
        except Exception as e:
            print(f"[Wake] Crashed: {e} — restarting in 3s...")
            time.sleep(3)
