import os, json, time, math, random, threading, platform
import tkinter as tk
from collections import deque
from PIL import Image, ImageTk, ImageDraw
import sys
from pathlib import Path
import psutil

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "A . L . I"
MODEL_BADGE = "NEXUS PRIME"
SUBTITLE    = "Autonomous Linked Intelligence"

# ── Space theme palette ──────────────────────────────────────────────────────
C_BG      = "#00000a"          # near-black with blue tint
C_SPACE   = "#02000f"          # deep space purple-black
C_PRI     = "#bf5fff"          # electric violet
C_MID     = "#6a2fa0"          # medium purple
C_DIM     = "#2a0a45"          # dark purple
C_DIMMER  = "#0d0020"          # very dark purple
C_ACC     = "#ff2d9b"          # hot pink / magenta
C_ACC2    = "#ffe066"          # star yellow
C_TEXT    = "#d4b4ff"          # lavender text
C_PANEL   = "#06000f"          # panel background
C_GREEN   = "#39ff14"          # neon green
C_RED     = "#ff3333"          # red
C_MUTED   = "#ff2d9b"          # muted = magenta
C_NEBULA  = "#ff6b9d"          # nebula pink
C_STAR    = "#ffffff"          # star white
C_TEAL    = "#00f5d4"          # teal accent


class JarvisUI:
    def __init__(self, face_path, size=None):
        self.root = tk.Tk()
        self.root.title("A.L.I — NEXUS PRIME")
        self.root.configure(bg=C_BG)

        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.root.bind("<F11>",    lambda e: self.root.attributes("-fullscreen", True))

        self.root.update_idletasks()
        W = self.root.winfo_screenwidth()
        H = self.root.winfo_screenheight()
        self.W = W
        self.H = H

        # Layout
        self.HDR_H   = 68
        self.FTR_H   = 34
        self.LEFT_W  = max(260, int(W * 0.18))
        self.RIGHT_W = max(320, int(W * 0.24))
        self.CTR_W   = W - self.LEFT_W - self.RIGHT_W
        self.CTR_X   = self.LEFT_W + self.CTR_W // 2
        self.CTR_Y   = self.HDR_H + (H - self.HDR_H - self.FTR_H) // 2

        orb_space    = H - self.HDR_H - self.FTR_H
        self.FACE_SZ = min(int(orb_space * 0.58), int(self.CTR_W * 0.72), 520)
        self.FCX     = self.CTR_X
        self.FCY     = self.HDR_H + int(orb_space * 0.46)

        # Animation state
        self.speaking     = False
        self.muted        = False
        self.scale        = 1.0
        self.target_scale = 1.0
        self.halo_a       = 60.0
        self.target_halo  = 60.0
        self.last_t       = time.time()
        self.tick         = 0
        self.scan_angle   = 0.0
        self.scan2_angle  = 180.0
        self.rings_spin   = [0.0, 120.0, 240.0, 60.0]
        self.pulse_r      = [0.0, self.FACE_SZ * 0.26, self.FACE_SZ * 0.52]
        self.status_text  = "INITIALISING"
        self.status_blink = True
        self._jarvis_state = "INITIALISING"
        self._start_time   = time.time()

        # Stars: (x, y, radius, brightness, twinkle_phase)
        random.seed(42)
        self._stars = [
            (random.randint(0, W), random.randint(0, H),
             random.choice([1, 1, 1, 2]),
             random.uniform(0.3, 1.0),
             random.uniform(0, math.pi * 2))
            for _ in range(280)
        ]
        # Nebula clouds: (cx, cy, rx, ry, color, alpha)
        self._nebulae = [
            (int(W * 0.12), int(H * 0.35), 110, 70,  "#3a0060", 28),
            (int(W * 0.85), int(H * 0.25), 140, 90,  "#60003a", 22),
            (int(W * 0.50), int(H * 0.82), 180, 80,  "#002060", 20),
            (int(W * 0.70), int(H * 0.65), 100, 60,  "#3a0060", 18),
            (int(W * 0.25), int(H * 0.75), 120, 55,  "#600020", 15),
        ]

        # Data streams
        self._data_streams = [[random.random() for _ in range(20)] for _ in range(4)]

        # Typing
        self.typing_queue    = deque()
        self.is_typing       = False
        self.on_text_command = None

        # Face
        self._face_pil         = None
        self._has_face         = False
        self._face_scale_cache = None
        self._load_face(face_path)

        # Canvas
        self.bg = tk.Canvas(self.root, width=W, height=H,
                            bg=C_BG, highlightthickness=0)
        self.bg.place(x=0, y=0)

        # Conversation log (right panel)
        LOG_X = W - self.RIGHT_W + 8
        LOG_Y = self.HDR_H + 116
        LOG_H = H - self.HDR_H - self.FTR_H - 176
        LOG_W = self.RIGHT_W - 16

        self.log_frame = tk.Frame(self.root, bg=C_PANEL,
                                  highlightbackground=C_DIM,
                                  highlightthickness=1)
        self.log_frame.place(x=LOG_X, y=LOG_Y, width=LOG_W, height=LOG_H)
        self.log_text = tk.Text(self.log_frame, fg=C_TEXT, bg=C_PANEL,
                                insertbackground=C_TEXT, borderwidth=0,
                                wrap="word", font=("Courier", 10), padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("you", foreground="#e8e8e8")
        self.log_text.tag_config("ai",  foreground=C_PRI)
        self.log_text.tag_config("sys", foreground=C_ACC2)
        self.log_text.tag_config("err", foreground=C_RED)

        INPUT_Y = LOG_Y + LOG_H + 8
        self._build_input_bar(LOG_W, LOG_X, INPUT_Y)
        self._build_mute_button()

        self.root.bind("<F4>", lambda e: self._toggle_mute())

        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    # ── Mute ───────────────────────────────────────────────────────────────────

    def _build_mute_button(self):
        BTN_W, BTN_H = 130, 34
        BTN_X = self.W - self.RIGHT_W + 8
        BTN_Y = self.H - self.FTR_H - BTN_H - 8
        self._mute_canvas = tk.Canvas(self.root, width=BTN_W, height=BTN_H,
                                      bg=C_BG, highlightthickness=0, cursor="hand2")
        self._mute_canvas.place(x=BTN_X, y=BTN_Y)
        self._mute_canvas.bind("<Button-1>", lambda e: self._toggle_mute())
        self._draw_mute_button()

    def _draw_mute_button(self):
        c = self._mute_canvas
        c.delete("all")
        if self.muted:
            border, fill, icon, label, fg = C_MUTED, "#1a0010", "🔇", " MUTED", C_MUTED
        else:
            border, fill, icon, label, fg = C_MID, C_PANEL, "🎙", " LIVE", C_GREEN
        c.create_rectangle(0, 0, 130, 34, outline=border, fill=fill, width=1)
        c.create_text(65, 17, text=f"{icon}{label}", fill=fg, font=("Courier", 11, "bold"))

    def _toggle_mute(self):
        self.muted = not self.muted
        self._draw_mute_button()
        if self.muted:
            self.set_state("MUTED")
            self.write_log("SYS: Microphone muted.")
        else:
            self.set_state("LISTENING")
            self.write_log("SYS: Microphone active.")

    # ── Input bar ──────────────────────────────────────────────────────────────

    def _build_input_bar(self, lw, lx, y):
        BTN_W = 80
        INP_W = lw - BTN_W - 4
        self._input_var   = tk.StringVar()
        self._input_entry = tk.Entry(
            self.root, textvariable=self._input_var,
            fg=C_TEXT, bg="#0a0018", insertbackground=C_TEXT,
            borderwidth=0, font=("Courier", 11),
            highlightthickness=1, highlightbackground=C_DIM, highlightcolor=C_PRI)
        self._input_entry.place(x=lx, y=y, width=INP_W, height=30)
        self._input_entry.bind("<Return>",   self._on_input_submit)
        self._input_entry.bind("<KP_Enter>", self._on_input_submit)
        self._send_btn = tk.Button(
            self.root, text="SEND ▸", command=self._on_input_submit,
            fg=C_PRI, bg=C_PANEL,
            activeforeground=C_BG, activebackground=C_PRI,
            font=("Courier", 10, "bold"), borderwidth=0, cursor="hand2",
            highlightthickness=1, highlightbackground=C_MID)
        self._send_btn.place(x=lx + INP_W + 4, y=y, width=BTN_W, height=30)

    def _on_input_submit(self, event=None):
        text = self._input_var.get().strip()
        if not text:
            return
        self._input_var.set("")
        self.write_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    # ── State ──────────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        self._jarvis_state = state
        state_map = {
            "MUTED":      ("MUTED",      False),
            "SPEAKING":   ("SPEAKING",   True),
            "THINKING":   ("THINKING",   False),
            "LISTENING":  ("LISTENING",  False),
            "PROCESSING": ("PROCESSING", False),
        }
        txt, spk = state_map.get(state, ("ONLINE", False))
        self.status_text = txt
        self.speaking    = spk

    # ── Face ───────────────────────────────────────────────────────────────────

    def _load_face(self, path):
        FW = self.FACE_SZ
        try:
            img  = Image.open(path).convert("RGBA").resize((FW, FW), Image.LANCZOS)
            mask = Image.new("L", (FW, FW), 0)
            ImageDraw.Draw(mask).ellipse((2, 2, FW - 2, FW - 2), fill=255)
            img.putalpha(mask)
            self._face_pil = img
            self._has_face = True
        except Exception:
            self._has_face = False

    @staticmethod
    def _ac(r, g, b, a):
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    @staticmethod
    def _hex_alpha(hex_col, alpha):
        r = int(hex_col[1:3], 16)
        g = int(hex_col[3:5], 16)
        b = int(hex_col[5:7], 16)
        f = alpha / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    # ── Animation ──────────────────────────────────────────────────────────────

    def _animate(self):
        self.tick += 1
        t   = self.tick
        now = time.time()

        if now - self.last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self.target_scale = random.uniform(1.06, 1.14)
                self.target_halo  = random.uniform(160, 220)
            elif self.muted:
                self.target_scale = random.uniform(0.998, 1.001)
                self.target_halo  = random.uniform(18, 30)
            else:
                self.target_scale = random.uniform(1.001, 1.008)
                self.target_halo  = random.uniform(55, 80)
            self.last_t = now

        sp = 0.35 if self.speaking else 0.16
        self.scale  += (self.target_scale - self.scale) * sp
        self.halo_a += (self.target_halo  - self.halo_a) * sp

        speeds = [1.5, -1.0, 2.2, -0.6] if self.speaking else [0.6, -0.38, 0.95, -0.25]
        for i, spd in enumerate(speeds):
            self.rings_spin[i] = (self.rings_spin[i] + spd) % 360

        self.scan_angle  = (self.scan_angle  + (3.5 if self.speaking else 1.5)) % 360
        self.scan2_angle = (self.scan2_angle + (-2.2 if self.speaking else -0.9)) % 360

        pspd  = 4.5 if self.speaking else 2.2
        limit = self.FACE_SZ * 0.82
        new_p = [r + pspd for r in self.pulse_r if r + pspd < limit]
        if len(new_p) < 4 and random.random() < (0.09 if self.speaking else 0.028):
            new_p.append(0.0)
        self.pulse_r = new_p

        if t % 36 == 0:
            self.status_blink = not self.status_blink

        if t % 3 == 0:
            for stream in self._data_streams:
                stream.pop(0)
                stream.append(random.random())

        self._draw()
        self.root.after(16, self._animate)

    # ── Draw ───────────────────────────────────────────────────────────────────

    def _draw(self):
        c    = self.bg
        W, H = self.W, self.H
        t    = self.tick
        FCX  = self.FCX
        FCY  = self.FCY
        FW   = self.FACE_SZ
        LW   = self.LEFT_W
        RW   = self.RIGHT_W
        HDR  = self.HDR_H
        FTR  = self.FTR_H
        c.delete("all")

        # ── Deep space background ────────────────────────────────────────────
        c.create_rectangle(0, 0, W, H, fill=C_BG, outline="")

        # Nebula clouds
        for nx, ny, rx, ry, ncol, na in self._nebulae:
            for layer in range(5, 0, -1):
                lrx = int(rx * layer / 5)
                lry = int(ry * layer / 5)
                la  = int(na * layer / 5)
                c.create_oval(nx - lrx, ny - lry, nx + lrx, ny + lry,
                              fill=self._hex_alpha(ncol, la), outline="")

        # Stars (twinkling)
        for sx, sy, sr, bright, phase in self._stars:
            twinkle = bright * (0.6 + 0.4 * math.sin(t * 0.04 + phase))
            av = int(twinkle * 255)
            star_col = self._ac(255, 255, 255, av)
            if sr > 1:
                c.create_oval(sx-sr, sy-sr, sx+sr, sy+sr, fill=star_col, outline="")
            else:
                c.create_rectangle(sx, sy, sx+1, sy+1, fill=star_col, outline="")

        # Subtle grid lines (space grid)
        for x in range(0, W, 60):
            c.create_line(x, 0, x, H, fill="#0d0030", width=1)
        for y in range(0, H, 60):
            c.create_line(0, y, W, y, fill="#0d0030", width=1)

        # Slow scanline
        sl_y = (t * 2) % H
        c.create_rectangle(0, sl_y, W, sl_y + 1, fill="#1a0040", outline="")

        # ── Panel backgrounds ────────────────────────────────────────────────
        c.create_rectangle(0, HDR, LW, H - FTR, fill="#03000d", outline="")
        c.create_line(LW, HDR, LW, H - FTR, fill=C_DIM, width=1)
        c.create_rectangle(W - RW, HDR, W, H - FTR, fill="#03000d", outline="")
        c.create_line(W - RW, HDR, W - RW, H - FTR, fill=C_DIM, width=1)

        # ── Header ───────────────────────────────────────────────────────────
        c.create_rectangle(0, 0, W, HDR, fill="#05000f", outline="")
        c.create_line(0, HDR, W, HDR, fill=C_PRI, width=1)
        # Header glow line
        c.create_line(0, HDR - 1, W, HDR - 1, fill=self._ac(191, 95, 255, 60), width=2)

        c.create_text(18, HDR // 2 - 9, text=MODEL_BADGE,
                      fill=C_MID, font=("Courier", 10, "bold"), anchor="w")
        c.create_text(18, HDR // 2 + 9, text="DEEP SPACE CONSTRUCT · CLASS-Ω",
                      fill=C_DIM, font=("Courier", 8), anchor="w")

        c.create_text(W // 2, HDR // 2 - 11, text=SYSTEM_NAME,
                      fill=C_PRI, font=("Courier", 24, "bold"))
        c.create_text(W // 2, HDR // 2 + 13, text=SUBTITLE,
                      fill=C_MID, font=("Courier", 9))

        c.create_text(W - 16, HDR // 2 - 10, text=time.strftime("%H:%M:%S"),
                      fill=C_PRI, font=("Courier", 18, "bold"), anchor="e")
        c.create_text(W - 16, HDR // 2 + 10, text=time.strftime("%a %d %b %Y"),
                      fill=C_MID, font=("Courier", 9), anchor="e")

        for i, (col, lbl) in enumerate([(C_GREEN, "NET"), (C_ACC2, "API"), (C_PRI, "AI")]):
            bx = W // 2 + 230 + i * 68
            by = HDR // 2
            dot = "●" if self.status_blink else "○"
            c.create_text(bx, by, text=f"{dot} {lbl}", fill=col, font=("Courier", 9, "bold"))

        # ── Left panel ───────────────────────────────────────────────────────
        self._draw_left_panel(c, LW, HDR, H - FTR, t)

        # ── Right panel label ────────────────────────────────────────────────
        px = W - RW + 10
        c.create_text(px, HDR + 14, text="── TRANSMISSION LOG ──",
                      fill=C_MID, font=("Courier", 9, "bold"), anchor="w")
        c.create_text(px, HDR + 30, text=f"SESSION  {time.strftime('%H:%M')}",
                      fill=C_DIM, font=("Courier", 8), anchor="w")

        # ── Orb ──────────────────────────────────────────────────────────────
        self._draw_orb(c, FCX, FCY, FW, t)

        # ── Status + waveform ─────────────────────────────────────────────────
        self._draw_status_waveform(c, FCX, FCY, FW, W, H, t)

        # ── Footer ───────────────────────────────────────────────────────────
        c.create_rectangle(0, H - FTR, W, H, fill="#05000f", outline="")
        c.create_line(0, H - FTR, W, H - FTR, fill=C_DIM, width=1)
        uptime = int(time.time() - self._start_time)
        up_str = f"UPTIME  {uptime // 3600:02d}:{(uptime % 3600) // 60:02d}:{uptime % 60:02d}"
        c.create_text(W // 2, H - FTR // 2, text=up_str, fill=C_DIM, font=("Courier", 9))
        c.create_text(16, H - FTR // 2, text="[ESC] WINDOW  [F4] MUTE  [F11] FULLSCREEN",
                      fill=C_DIM, font=("Courier", 8), anchor="w")
        c.create_text(W - 16, H - FTR // 2, text="NEXUS SYSTEMS  ·  DEEP SPACE DIVISION",
                      fill=C_DIM, font=("Courier", 8), anchor="e")

    def _draw_left_panel(self, c, lw, y0, y1, t):
        px = 14
        py = y0 + 14

        def section(title, y):
            c.create_text(px, y, text=f"── {title} ──",
                          fill=C_MID, font=("Courier", 9, "bold"), anchor="w")
            return y + 18

        def row(label, val, col, y):
            c.create_text(px, y, text=label, fill=C_DIM, font=("Courier", 8), anchor="w")
            c.create_text(lw - px, y, text=val, fill=col, font=("Courier", 9, "bold"), anchor="e")
            return y + 15

        def bar(val, y, col=C_PRI):
            bw = lw - px * 2
            c.create_rectangle(px, y, px + bw, y + 6, fill="#0d0030", outline=C_DIM)
            c.create_rectangle(px, y, px + int(bw * val), y + 6, fill=col, outline="")
            return y + 12

        py = section("SYSTEM", py)
        try:
            cpu     = psutil.cpu_percent(interval=None) / 100
            mem     = psutil.virtual_memory()
            mem_pct = mem.percent / 100
            disk    = psutil.disk_usage("/").percent / 100
        except Exception:
            cpu = mem_pct = disk = 0.0

        py = row("CPU", f"{int(cpu*100)}%", C_GREEN if cpu < 0.7 else C_ACC, py)
        py = bar(cpu, py, C_GREEN if cpu < 0.7 else C_ACC)
        py = row("MEMORY", f"{int(mem_pct*100)}%", C_PRI, py)
        py = bar(mem_pct, py, C_PRI)
        py = row("DISK", f"{int(disk*100)}%", C_TEAL if disk < 0.8 else C_ACC2, py)
        py = bar(disk, py, C_TEAL)
        py += 8

        py = section("NETWORK", py)
        try:
            nc      = psutil.net_io_counters()
            sent_mb = nc.bytes_sent / 1_000_000
            recv_mb = nc.bytes_recv / 1_000_000
        except Exception:
            sent_mb = recv_mb = 0.0
        py = row("SENT",     f"{sent_mb:.1f} MB", C_MID, py)
        py = row("RECEIVED", f"{recv_mb:.1f} MB", C_MID, py)
        py = row("STATUS",   "ONLINE", C_GREEN, py)
        py += 8

        py = section("QUANTUM SIGNAL", py)
        for stream in self._data_streams[:2]:
            sw = lw - px * 2
            sh = 20
            c.create_rectangle(px, py, px + sw, py + sh, fill="#0a0020", outline=C_DIM)
            pts = []
            for i, v in enumerate(stream):
                sx = px + int(i / len(stream) * sw)
                sy = py + sh - int(v * (sh - 2)) - 1
                pts.extend([sx, sy])
            if len(pts) >= 4:
                c.create_line(pts, fill=C_PRI, width=1, smooth=True)
            py += sh + 4

        py += 6
        py = section("MODULES ONLINE", py)
        modules = [
            ("VOICE ENGINE",  C_GREEN),
            ("BROWSER CTRL",  C_GREEN),
            ("FILE SYSTEM",   C_GREEN),
            ("VISION PROC",   C_GREEN),
            ("WEB CRAWLER",   C_GREEN),
            ("MEMORY CORE",   C_GREEN),
            ("SPACE NAV",     C_TEAL),
        ]
        for name, col in modules:
            if py + 14 > y1 - 10:
                break
            dot = "●" if self.status_blink else "○"
            c.create_text(px, py, text=f"{dot}  {name}", fill=col, font=("Courier", 8), anchor="w")
            py += 14

    def _draw_orb(self, c, FCX, FCY, FW, t):
        # Outer cosmic glow
        for r in range(int(FW * 0.68), int(FW * 0.30), -18):
            frac = 1.0 - (r - FW * 0.30) / (FW * 0.38)
            ga   = max(0, min(255, int(self.halo_a * 0.07 * frac)))
            if self.muted:
                c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r,
                              outline=self._ac(255, 45, 155, ga), width=2)
            else:
                c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r,
                              outline=self._ac(191, 95, 255, ga), width=2)

        # Pulse rings
        for pr in self.pulse_r:
            pa  = max(0, int(250 * (1.0 - pr / (FW * 0.82))))
            r   = int(pr)
            col = self._ac(255, 45, 155, pa // 3) if self.muted else self._ac(191, 95, 255, pa)
            c.create_oval(FCX-r, FCY-r, FCX+r, FCY+r, outline=col, width=2)

        # Spinning orbital rings (4 layers, alternating purple/pink/teal)
        ring_colors = [
            (0, 212, 255),    # teal-ish (outer)
            (255, 45, 155),   # hot pink
            (191, 95, 255),   # violet
            (255, 230, 102),  # star yellow (inner)
        ]
        ring_defs = [(0.54, 3, 125, 82), (0.46, 2, 88, 62),
                     (0.38, 2, 62, 44), (0.30, 1, 42, 30)]
        for idx, ((r_frac, w_ring, arc_l, gap), rgb) in enumerate(zip(ring_defs, ring_colors)):
            ring_r = int(FW * r_frac)
            base_a = self.rings_spin[idx]
            a_val  = max(0, min(255, int(self.halo_a * (1.0 - idx * 0.14))))
            col    = self._ac(*rgb, a_val)
            steps  = 360 // max(1, arc_l + gap)
            for s in range(steps):
                start = (base_a + s * (arc_l + gap)) % 360
                c.create_arc(FCX-ring_r, FCY-ring_r, FCX+ring_r, FCY+ring_r,
                             start=start, extent=arc_l,
                             outline=col, width=w_ring, style="arc")

        # Scanning arcs
        sr       = int(FW * 0.56)
        scan_a   = min(255, int(self.halo_a * 1.5))
        arc_ext  = 85 if self.speaking else 50
        scan_col = self._ac(255, 45, 155, scan_a) if self.muted else self._ac(191, 95, 255, scan_a)
        c.create_arc(FCX-sr, FCY-sr, FCX+sr, FCY+sr,
                     start=self.scan_angle, extent=arc_ext,
                     outline=scan_col, width=3, style="arc")
        c.create_arc(FCX-sr, FCY-sr, FCX+sr, FCY+sr,
                     start=self.scan2_angle, extent=arc_ext,
                     outline=self._ac(255, 230, 102, scan_a // 2), width=2, style="arc")

        # Tick marks
        t_out = int(FW * 0.565)
        t_in  = int(FW * 0.540)
        a_mk  = self._ac(191, 95, 255, 150)
        for deg in range(0, 360, 6):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            c.create_line(FCX + t_out * math.cos(rad), FCY - t_out * math.sin(rad),
                          FCX + inn   * math.cos(rad), FCY - inn   * math.sin(rad),
                          fill=a_mk, width=1 if deg % 30 != 0 else 2)

        # Crosshair
        ch_r = int(FW * 0.58)
        gap  = int(FW * 0.13)
        ch_a = self._ac(0, 245, 212, int(self.halo_a * 0.45))
        for x1, y1, x2, y2 in [
                (FCX - ch_r, FCY, FCX - gap, FCY), (FCX + gap, FCY, FCX + ch_r, FCY),
                (FCX, FCY - ch_r, FCX, FCY - gap), (FCX, FCY + gap, FCX, FCY + ch_r)]:
            c.create_line(x1, y1, x2, y2, fill=ch_a, width=1)

        # Corner brackets
        blen = 30
        bc   = self._ac(191, 95, 255, 220)
        hl = FCX - FW // 2; hr = FCX + FW // 2
        ht = FCY - FW // 2; hb = FCY + FW // 2
        for bx, by, sdx, sdy in [(hl, ht, 1, 1), (hr, ht, -1, 1),
                                   (hl, hb, 1, -1), (hr, hb, -1, -1)]:
            c.create_line(bx, by, bx + sdx * blen, by,              fill=bc, width=2)
            c.create_line(bx, by, bx,               by + sdy * blen, fill=bc, width=2)

        # Face / orb
        if self._has_face:
            fw = int(FW * self.scale)
            if (self._face_scale_cache is None or
                    abs(self._face_scale_cache[0] - self.scale) > 0.004):
                scaled = self._face_pil.resize((fw, fw), Image.BILINEAR)
                tk_img = ImageTk.PhotoImage(scaled)
                self._face_scale_cache = (self.scale, tk_img)
            c.create_image(FCX, FCY, image=self._face_scale_cache[1])
        else:
            # Cosmic orb
            orb_r   = int(FW * 0.28 * self.scale)
            orb_col = (255, 45, 155) if self.muted else (80, 0, 160)
            for i in range(10, 0, -1):
                r2   = int(orb_r * i / 10)
                frac = i / 10
                ga   = max(0, min(255, int(self.halo_a * 1.3 * frac)))
                c.create_oval(FCX-r2, FCY-r2, FCX+r2, FCY+r2,
                              fill=self._ac(int(orb_col[0]*frac),
                                            int(orb_col[1]*frac),
                                            int(orb_col[2]*frac), ga),
                              outline="")
            # Planet ring
            ring_w = int(orb_r * 1.7)
            ring_h = int(orb_r * 0.28)
            ra     = int(self.halo_a * 1.2)
            c.create_oval(FCX - ring_w, FCY - ring_h,
                          FCX + ring_w, FCY + ring_h,
                          outline=self._ac(191, 95, 255, min(255, ra)), width=2)
            c.create_text(FCX, FCY, text=SYSTEM_NAME,
                          fill=self._ac(191, 95, 255, min(255, int(self.halo_a * 2.2))),
                          font=("Courier", 18, "bold"))

    def _draw_status_waveform(self, c, FCX, FCY, FW, W, H, t):
        sy = FCY + FW // 2 + 28

        if self.muted:
            stat, sc = "⊘  MUTED", C_MUTED
        elif self.speaking:
            stat, sc = "●  TRANSMITTING", C_ACC
        elif self._jarvis_state == "THINKING":
            sym  = "◈" if self.status_blink else "◇"
            stat, sc = f"{sym}  PROCESSING", C_ACC2
        elif self._jarvis_state == "PROCESSING":
            sym  = "▷" if self.status_blink else "▶"
            stat, sc = f"{sym}  COMPUTING", C_ACC2
        elif self._jarvis_state == "LISTENING":
            sym  = "●" if self.status_blink else "○"
            stat, sc = f"{sym}  LISTENING", C_GREEN
        else:
            sym  = "●" if self.status_blink else "○"
            stat, sc = f"{sym}  {self.status_text}", C_PRI

        c.create_text(FCX, sy, text=stat, fill=sc, font=("Courier", 13, "bold"))

        # Waveform
        wy  = sy + 26
        N   = 52
        BH  = 30
        bw  = 9
        tw  = N * bw
        wx0 = FCX - tw // 2
        for i in range(N):
            if self.muted:
                hb, col = 2, C_MUTED
            elif self.speaking:
                hb  = random.randint(4, BH)
                col = C_PRI if hb > BH * 0.55 else C_ACC
            else:
                hb  = int(4 + 3 * math.sin(t * 0.09 + i * 0.52))
                col = C_DIM
            bx = wx0 + i * bw
            c.create_rectangle(bx, wy + BH - hb, bx + bw - 2, wy + BH,
                                fill=col, outline="")

        # Full-screen corner brackets
        blen = 44
        bc   = self._ac(191, 95, 255, 70)
        for bx, by, sdx, sdy in [
                (0, self.HDR_H, 1, 1), (W, self.HDR_H, -1, 1),
                (0, H - self.FTR_H, 1, -1), (W, H - self.FTR_H, -1, -1)]:
            c.create_line(bx, by, bx + sdx * blen, by,              fill=bc, width=2)
            c.create_line(bx, by, bx,               by + sdy * blen, fill=bc, width=2)

    # ── Log ────────────────────────────────────────────────────────────────────

    def write_log(self, text: str):
        self.typing_queue.append(text)
        tl = text.lower()
        if tl.startswith("you:"):
            self.set_state("PROCESSING")
        elif tl.startswith("jarvis:") or tl.startswith("ai:") or tl.startswith("ali:"):
            self.set_state("SPEAKING")
        if not self.is_typing:
            self._start_typing()

    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking and not self.muted:
                self.set_state("LISTENING")
            return
        self.is_typing = True
        text = self.typing_queue.popleft()
        tl   = text.lower()
        if tl.startswith("you:"):
            tag = "you"
        elif tl.startswith("jarvis:") or tl.startswith("ai:") or tl.startswith("ali:"):
            tag = "ai"
        elif "error" in tl or "failed" in tl or tl.startswith("err:"):
            tag = "err"
        else:
            tag = "sys"
        self.log_text.configure(state="normal")
        self._type_char(text, 0, tag)

    def _type_char(self, text, i, tag):
        if i < len(text):
            self.log_text.insert(tk.END, text[i], tag)
            self.log_text.see(tk.END)
            self.root.after(7, self._type_char, text, i + 1, tag)
        else:
            self.log_text.insert(tk.END, "\n")
            self.log_text.configure(state="disabled")
            self.root.after(20, self._start_typing)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    # ── API key setup ──────────────────────────────────────────────────────────

    def _api_keys_exist(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(data.get("gemini_api_key")) and bool(data.get("os_system"))
        except Exception:
            return False

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    @staticmethod
    def _detect_os() -> str:
        s = platform.system().lower()
        if s == "darwin":  return "mac"
        if s == "windows": return "windows"
        return "linux"

    def _show_setup_ui(self):
        detected      = self._detect_os()
        self._selected_os = tk.StringVar(value=detected)
        self.setup_frame  = tk.Frame(self.root, bg="#05000f",
                                     highlightbackground=C_PRI, highlightthickness=1)
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED",
                 fg=C_PRI, bg="#05000f", font=("Courier", 13, "bold")).pack(pady=(18, 2))
        tk.Label(self.setup_frame, text="Configure A.L.I before first boot.",
                 fg=C_MID, bg="#05000f", font=("Courier", 9)).pack(pady=(0, 14))
        tk.Label(self.setup_frame, text="GEMINI API KEY",
                 fg=C_DIM, bg="#05000f", font=("Courier", 9)).pack(pady=(0, 2))
        self.gemini_entry = tk.Entry(self.setup_frame, width=52,
                                     fg=C_TEXT, bg="#0a0020", insertbackground=C_TEXT,
                                     borderwidth=0, font=("Courier", 10), show="*")
        self.gemini_entry.pack(pady=(0, 18))
        tk.Frame(self.setup_frame, bg=C_DIM, height=1).pack(fill="x", padx=24, pady=(0, 12))
        tk.Label(self.setup_frame, text="SELECT OPERATING SYSTEM",
                 fg=C_DIM, bg="#05000f", font=("Courier", 9)).pack(pady=(0, 4))
        detect_label = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}.get(
            detected, detected.capitalize())
        tk.Label(self.setup_frame, text=f"AUTO-DETECTED: {detect_label}",
                 fg=C_ACC2, bg="#05000f", font=("Courier", 8)).pack(pady=(0, 8))
        os_btn_frame = tk.Frame(self.setup_frame, bg="#05000f")
        os_btn_frame.pack(pady=(0, 18))
        self._os_buttons = {}
        for os_key, os_label in [("windows", "⊞ WINDOWS"), ("mac", " macOS"), ("linux", "🐧 LINUX")]:
            btn = tk.Button(os_btn_frame, text=os_label, width=13,
                            font=("Courier", 10, "bold"), borderwidth=0, cursor="hand2", pady=7,
                            command=lambda k=os_key: self._select_os(k))
            btn.pack(side="left", padx=6)
            self._os_buttons[os_key] = btn
        self._select_os(detected)
        tk.Frame(self.setup_frame, bg=C_DIM, height=1).pack(fill="x", padx=24, pady=(0, 14))
        tk.Button(self.setup_frame, text="▸  INITIALISE SYSTEMS",
                  command=self._save_api_keys, bg=C_BG, fg=C_PRI,
                  activebackground="#1a0040", font=("Courier", 10),
                  borderwidth=0, pady=8).pack(pady=(0, 18))

    def _select_os(self, os_key: str):
        self._selected_os.set(os_key)
        styles = {"windows": (C_PRI, "#0d0030"), "mac": (C_ACC2, "#1a1500"), "linux": (C_GREEN, "#001a0d")}
        for key, btn in self._os_buttons.items():
            fg, bg = styles[key]
            if key == os_key:
                btn.configure(fg=bg, bg=fg, activeforeground=bg, activebackground=fg, relief="flat")
            else:
                btn.configure(fg=C_DIM, bg="#0a0020", activeforeground=C_TEXT,
                              activebackground="#1a0040", relief="flat")

    def _save_api_keys(self):
        gemini = self.gemini_entry.get().strip()
        if not gemini:
            self.gemini_entry.configure(highlightthickness=1,
                                        highlightbackground=C_RED, highlightcolor=C_RED)
            return
        os_system = self._selected_os.get()
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_key": gemini, "os_system": os_system}, f, indent=4)
        self.setup_frame.destroy()
        self._api_key_ready = True
        self.set_state("LISTENING")
        self.write_log(f"SYS: Systems initialised. OS → {os_system.upper()}. A.L.I online.")
