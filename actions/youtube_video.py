# actions/youtube_video.py
# MARK XXV — YouTube Controller
#
# Features:
#   - play      : Search and play a YouTube video (original feature, preserved)
#   - summarize : Get transcript → Gemini summary → speak + optional Notepad
#   - get_info  : Video title, channel, views, duration (scraping)
#   - trending  : Fetch trending videos for a region

import json
import re
import sys
import time
import threading
from pathlib import Path

import pyautogui
import numpy as np
import cv2
from PIL import ImageGrab

try:
    import requests
    from bs4 import BeautifulSoup
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def open_browser():
    pyautogui.press("win")
    time.sleep(0.4)
    pyautogui.write("browser", interval=0.05)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(2.0)


def find_video_thumbnails() -> list[tuple[int, int]]:

    try:
        screenshot = ImageGrab.grab()
        img        = np.array(screenshot)
        screen_h, screen_w = img.shape[:2]

        roi_top    = int(screen_h * 0.10)
        roi_bottom = int(screen_h * 0.75)
        roi_left   = int(screen_w * 0.20)
        roi_right  = int(screen_w * 0.80)
        roi        = img[roi_top:roi_bottom, roi_left:roi_right]

        gray   = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        edges  = cv2.Canny(gray, 30, 100)
        kernel = np.ones((3, 3), np.uint8)
        edges  = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            area  = w * h
            ratio = w / h if h > 0 else 0
            if area < 15000:
                continue
            if not (1.4 < ratio < 2.2):
                continue
            center_x = x + w // 2 + roi_left
            center_y = y + h // 2 + roi_top
            candidates.append((center_x, center_y, area))

        filtered = []
        for cx, cy, area in sorted(candidates, key=lambda c: c[1]):
            if not any(abs(cx - fx) < 80 and abs(cy - fy) < 80 for fx, fy in filtered):
                filtered.append((cx, cy))

        return filtered

    except Exception as e:
        print(f"[YouTube] ⚠️ Thumbnail detection failed: {e}")
        return []


def _extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _ask_for_url(prompt_text: str = "YouTube video URL:") -> str | None:

    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk._default_root 
        if root is None:
            root = tk.Tk()
            root.withdraw()

        url = simpledialog.askstring(
            "J.A.R.V.I.S",
            prompt_text,
            parent=root
        )
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] ⚠️ URL dialog failed: {e}")
        return None


def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))

def _get_transcript(video_id: str) -> str | None:

    if not _TRANSCRIPT_OK:
        print("[YouTube] ⚠️ youtube-transcript-api not installed.")
        return None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(
                ["en", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]
            )
        except Exception:
            pass

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(
                    ["en", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]
                )
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript is None:
            return None

        fetched = transcript.fetch()
        text    = " ".join(entry["text"] for entry in fetched)
        print(f"[YouTube] 📝 Transcript: {len(text)} chars")
        return text

    except Exception as e:
        print(f"[YouTube] ⚠️ Transcript fetch failed: {e}")
        return None

def _summarize_with_gemini(transcript: str, video_url: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-3.0-flash",
        system_instruction=(
            "You are JARVIS, Tony Stark's AI assistant. "
            "Summarize YouTube video transcripts clearly and concisely. "
            "Structure: 1-sentence overview, then 3-5 key points. "
            "Be direct. Address the user as 'sir'. "
            "Match the language of the transcript."
        )
    )

    max_chars = 80000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")

    response = model.generate_content(
        f"Please summarize this YouTube video transcript:\n\n{truncated}"
    )
    return response.text.strip()

def _save_to_notepad(content: str, video_url: str) -> str:
    import subprocess
    import platform
    from datetime import datetime

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_summary_{ts}.txt"
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    header = (
        f"JARVIS — YouTube Summary\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )

    filepath.write_text(header + content, encoding="utf-8")
    print(f"[YouTube] 💾 Summary saved: {filepath}")

    system  = platform.system()
    open_fn = {
        "Windows": lambda p: subprocess.Popen(["notepad.exe", str(p)]),
        "Darwin":  lambda p: subprocess.Popen(["open", "-t", str(p)]),
        "Linux":   lambda p: subprocess.Popen(["xdg-open", str(p)]),
    }
    opener = open_fn.get(system)
    if opener:
        opener(filepath)

    return str(filepath)

def _scrape_video_info(video_id: str) -> dict:

    if not _REQUESTS_OK:
        return {}

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text

        info = {}

        title_match = re.search(r'"title":\{"runs":\[\{"text":"([^"]+)"', html)
        if title_match:
            info["title"] = title_match.group(1)

        channel_match = re.search(r'"ownerChannelName":"([^"]+)"', html)
        if channel_match:
            info["channel"] = channel_match.group(1)

        views_match = re.search(r'"viewCount":"(\d+)"', html)
        if views_match:
            views = int(views_match.group(1))
            info["views"] = f"{views:,}"

        duration_match = re.search(r'"lengthSeconds":"(\d+)"', html)
        if duration_match:
            secs = int(duration_match.group(1))
            info["duration"] = f"{secs // 60}:{secs % 60:02d}"

        likes_match = re.search(r'"label":"([0-9,]+ likes)"', html)
        if likes_match:
            info["likes"] = likes_match.group(1)

        return info

    except Exception as e:
        print(f"[YouTube] ⚠️ Info scrape failed: {e}")
        return {}

def _scrape_trending(region: str = "TR", max_results: int = 8) -> list[dict]:

    if not _REQUESTS_OK:
        return []

    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text

        titles   = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)

        results = []
        seen    = set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "Unknown"
            results.append({"rank": len(results) + 1, "title": title, "channel": channel})
            if len(results) >= max_results:
                break

        return results

    except Exception as e:
        print(f"[YouTube] ⚠️ Trending scrape failed: {e}")
        return []

def _handle_play(parameters: dict, player) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Please tell me what you'd like to watch, sir."

    if player:
        player.write_log(f"[YouTube] Searching: {query}")

    open_browser()

    search_query = query.replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={search_query}"

    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyautogui.write(url, interval=0.02)
    pyautogui.press("enter")
    time.sleep(3.5)

    thumbnails = find_video_thumbnails()

    if len(thumbnails) >= 2:
        x, y = thumbnails[1]
        print(f"[YouTube] 🎯 Clicking 2nd thumbnail at ({x}, {y})")
        pyautogui.click(x, y)
        return f"Playing YouTube video for: {query}"

    elif len(thumbnails) == 1:
        x, y = thumbnails[0]
        print(f"[YouTube] ⚠️ One thumbnail found, clicking at ({x}, {y})")
        pyautogui.click(x, y)
        return f"Playing YouTube video for: {query}"

    else:
        print("[YouTube] ⚠️ No thumbnails found, using fallback position")
        screen_w, screen_h = pyautogui.size()
        pyautogui.click(screen_w // 2, int(screen_h * 0.45))
        return f"Attempted to play YouTube video for: {query}"


def _handle_summarize(parameters: dict, player, speak) -> str:

    if not _TRANSCRIPT_OK:
        return (
            "youtube-transcript-api is not installed, sir. "
            "Please run: pip install youtube-transcript-api"
        )

    url = _ask_for_url("Please paste the YouTube video URL:")
    if not url:
        return "No URL provided, sir. Summary cancelled."

    if not _is_valid_youtube_url(url):
        return "That doesn't appear to be a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID from that URL, sir."

    if player:
        player.write_log(f"[YouTube] Summarizing: {url}")

    if speak:
        speak("Fetching the transcript now, sir. One moment.")

    transcript = _get_transcript(video_id)
    if not transcript:
        return (
            "I couldn't retrieve a transcript for that video, sir. "
            "It may not have subtitles available."
        )

    if speak:
        speak("Transcript retrieved. Generating summary now.")

    try:
        summary = _summarize_with_gemini(transcript, url)
    except Exception as e:
        return f"Summary generation failed, sir: {e}"

    if speak:
        speak(summary)

    save = parameters.get("save", False)
    if save:
        saved_path = _save_to_notepad(summary, url)
        return f"Summary complete and saved to Desktop: {saved_path}"

    return summary


def _handle_get_info(parameters: dict, player, speak) -> str:
    url = parameters.get("url", "").strip()

    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID, sir."

    if player:
        player.write_log(f"[YouTube] Getting info: {url}")

    info = _scrape_video_info(video_id)
    if not info:
        return "Could not retrieve video information, sir."

    lines = []
    for key in ("title", "channel", "views", "duration", "likes"):
        if key in info:
            lines.append(f"{key.capitalize()}: {info[key]}")

    result = "\n".join(lines)
    if speak:
        speak(f"Here's the video info, sir. {result.replace(chr(10), '. ')}")

    return result


def _handle_trending(parameters: dict, player, speak) -> str:
    region = parameters.get("region", "TR").upper()

    if player:
        player.write_log(f"[YouTube] Trending: {region}")

    trending = _scrape_trending(region=region, max_results=8)

    if not trending:
        return f"Could not fetch trending videos for region {region}, sir."

    lines = [f"Top trending videos in {region}:"]
    for item in trending:
        lines.append(f"{item['rank']}. {item['title']} — {item['channel']}")

    result = "\n".join(lines)

    if speak:
        top3 = trending[:3]
        spoken = "Here are the top trending videos, sir. " + ". ".join(
            f"Number {v['rank']}: {v['title']} by {v['channel']}"
            for v in top3
        )
        speak(spoken)

    return result


_ACTION_MAP = {
    "play":      _handle_play,
    "summarize": _handle_summarize,
    "get_info":  _handle_get_info,
    "trending":  _handle_trending,
}

def youtube_video(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    """
    YouTube controller.

    Actions:
        play      : Search and play a video (default if no action given)
                    parameters: query(str)
        summarize : Summarize a video via transcript + Gemini
                    parameters: save(bool, optional) — save summary to Notepad
        get_info  : Get video metadata (title, channel, views, duration)
                    parameters: url(str, optional — dialog if omitted)
        trending  : Show trending videos
                    parameters: region(str, default "TR") — ISO country code

    Agent chain:
        summarize can be chained after any action that produces a YouTube URL.
    """
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player:
        player.write_log(f"[YouTube] Action: {action}")

    print(f"[YouTube] ▶️ Action: {action}  Params: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        return f"Unknown YouTube action: '{action}'. Available: play, summarize, get_info, trending."

    try:
        if action == "play":
            return handler(params, player) or "Done."
        return handler(params, player, speak) or "Done."

    except Exception as e:
        print(f"[YouTube] ❌ Error in {action}: {e}")
        return f"YouTube {action} failed, sir: {e}"