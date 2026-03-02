# actions/flight_finder.py
# MARK XXV — Flight Finder
#
# Searches for flights using Google Flights via browser_control.
# Results are spoken by JARVIS. Optionally saved to Notepad or opened in browser.
#
# Flow:
#   1. Parse origin, destination, date, passengers from parameters
#   2. Open Google Flights via browser_control
#   3. Fill in search fields
#   4. Scrape results via get_text
#   5. Parse with Gemini → structured flight data
#   6. Speak top results
#   7. Optionally save to Notepad or keep browser open
#
# Cross-platform: Windows, macOS, Linux
# No API key required — Google Flights is free to access

import json
import re
import sys
import subprocess
import platform
from datetime import datetime, timedelta
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _parse_date(raw: str) -> str:
    """
    Converts natural language date to YYYY-MM-DD.
    Handles: '15 Mart', 'March 15', '2025-03-15', 'next friday', etc.
    Falls back to Gemini for ambiguous inputs.
    """
    raw = raw.strip()

    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass


    today = datetime.now()
    lower = raw.lower()
    relative_map = {
        "today":     today,
        "tomorrow":  today + timedelta(days=1),
        "bugün":     today,
        "yarın":     today + timedelta(days=1),
    }
    for key, val in relative_map.items():
        if key in lower:
            return val.strftime("%Y-%m-%d")

    try:
        import google.generativeai as genai
        genai.configure(api_key=_get_api_key())
        model    = genai.GenerativeModel("gemini-2.5-flash-lite")
        today_str = today.strftime("%Y-%m-%d")
        response = model.generate_content(
            f"Today is {today_str}. Convert this date to YYYY-MM-DD format: '{raw}'. "
            f"Return ONLY the date string, nothing else."
        )
        result = response.text.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", result):
            return result
    except Exception:
        pass

    month_map = {
        "january": 1,  "february": 2,  "march": 3,     "april": 4,
        "may": 5,      "june": 6,      "july": 7,       "august": 8,
        "september": 9,"october": 10,  "november": 11,  "december": 12,
        "january": 1,  "ocak": 1,      "şubat": 2,      "mart": 3,
        "nisan": 4,    "mayıs": 5,     "haziran": 6,    "temmuz": 7,
        "ağustos": 8,  "eylül": 9,     "ekim": 10,      "kasım": 11,
        "aralık": 12,
    }
    for month_name, month_num in month_map.items():
        if month_name in lower:
            day_match = re.search(r"\d{1,2}", raw)
            if day_match:
                day  = int(day_match.group())
                year = today.year if month_num >= today.month else today.year + 1
                return f"{year}-{month_num:02d}-{day:02d}"

    return today.strftime("%Y-%m-%d")



def _build_google_flights_url(
    origin:      str,
    destination: str,
    date:        str,
    return_date: str | None = None,
    passengers:  int        = 1,
    cabin:       str        = "economy",
) -> str:
    """
    Builds a Google Flights URL with pre-filled search parameters.
    Uses the direct search URL format.
    """
    cabin_map = {
        "economy":  "1",
        "premium":  "2",
        "business": "3",
        "first":    "4",
    }
    cabin_code = cabin_map.get(cabin.lower(), "1")

    base = "https://www.google.com/travel/flights"

    if return_date:
        url = (
            f"{base}?q=Flights+from+{origin}+to+{destination}"
            f"+on+{date}+returning+{return_date}"
            f"&curr=TRY"
        )
    else:
        url = (
            f"{base}?q=Flights+from+{origin}+to+{destination}+on+{date}"
            f"&curr=TRY"
        )

    return url



def _search_flights_browser(
    origin:      str,
    destination: str,
    date:        str,
    return_date: str | None,
    passengers:  int,
    cabin:       str,
) -> tuple[str, str]:
    """
    Opens Google Flights in browser, waits for results, scrapes text.
    Returns (raw_text, page_url).
    """
    from actions.browser_control import browser_control
    import time

    url = _build_google_flights_url(
        origin, destination, date, return_date, passengers, cabin
    )

    print(f"[FlightFinder] 🌐 Opening: {url}")
    browser_control({"action": "go_to", "url": url})
    time.sleep(5)  

    result = browser_control({"action": "get_text"})
    return result or "", url


def _parse_flights_with_gemini(
    raw_text:    str,
    origin:      str,
    destination: str,
    date:        str,
) -> list[dict]:
    """
    Sends raw page text to Gemini and extracts structured flight data.
    Returns list of flight dicts.
    """
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=(
            "You are a flight data extraction expert. "
            "Extract flight information from raw webpage text. "
            "Return ONLY valid JSON array. No explanation, no markdown."
        )
    )

    truncated = raw_text[:12000]

    prompt = (
        f"Extract flight options from {origin} to {destination} on {date} "
        f"from this Google Flights page text:\n\n{truncated}\n\n"
        f"Return a JSON array of up to 5 flights:\n"
        f'[{{"airline": "...", "departure": "HH:MM", "arrival": "HH:MM", '
        f'"duration": "Xh Ym", "stops": 0, "price": "...", "currency": "..."}}]\n'
        f"If no flights found, return: []"
    )

    try:
        response = model.generate_content(prompt)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        flights  = json.loads(text)
        return flights if isinstance(flights, list) else []
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Parse failed: {e}")
        return []



def _format_spoken(
    flights:     list[dict],
    origin:      str,
    destination: str,
    date:        str,
) -> str:
    """Formats flights for spoken output — concise and natural."""
    if not flights:
        return (
            f"I couldn't find any flights from {origin} to {destination} "
            f"on {date}, sir. The page may not have loaded correctly."
        )

    lines = [f"Here are the flights from {origin} to {destination} on {date}, sir."]

    for i, f in enumerate(flights[:5], 1):
        airline   = f.get("airline",   "Unknown airline")
        departure = f.get("departure", "--:--")
        arrival   = f.get("arrival",   "--:--")
        duration  = f.get("duration",  "")
        stops     = f.get("stops",     0)
        price     = f.get("price",     "")
        currency  = f.get("currency",  "")

        stop_str  = "non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
        price_str = f"{price} {currency}".strip() if price else "price unavailable"
        dur_str   = f", {duration}" if duration else ""

        lines.append(
            f"Option {i}: {airline}, departing {departure}, arriving {arrival}"
            f"{dur_str}, {stop_str}, {price_str}."
        )

    cheapest = min(
        (f for f in flights if f.get("price")),
        key=lambda x: re.sub(r"[^\d]", "", str(x.get("price", "99999"))) or "99999",
        default=None,
    )
    if cheapest:
        lines.append(
            f"The cheapest option is {cheapest.get('airline')} "
            f"at {cheapest.get('price')} {cheapest.get('currency', '')}."
        )

    return " ".join(lines)


def _format_notepad(
    flights:     list[dict],
    origin:      str,
    destination: str,
    date:        str,
    return_date: str | None,
    page_url:    str,
) -> str:
    """Formats flights for Notepad — detailed and readable."""
    from datetime import datetime as dt

    lines = [
        "JARVIS — Flight Search Results",
        "─" * 50,
        f"Route     : {origin} → {destination}",
        f"Date      : {date}",
    ]
    if return_date:
        lines.append(f"Return    : {return_date}")
    lines += [
        f"Searched  : {dt.now().strftime('%Y-%m-%d %H:%M')}",
        f"Source    : {page_url}",
        "─" * 50,
        "",
    ]

    if not flights:
        lines.append("No flights found.")
    else:
        for i, f in enumerate(flights, 1):
            stops    = f.get("stops", 0)
            stop_str = "Non-stop" if stops == 0 else f"{stops} stop(s)"
            lines += [
                f"Flight {i}:",
                f"  Airline   : {f.get('airline', 'N/A')}",
                f"  Departure : {f.get('departure', 'N/A')}",
                f"  Arrival   : {f.get('arrival', 'N/A')}",
                f"  Duration  : {f.get('duration', 'N/A')}",
                f"  Stops     : {stop_str}",
                f"  Price     : {f.get('price', 'N/A')} {f.get('currency', '')}",
                "",
            ]

    return "\n".join(lines)


def _save_to_notepad(content: str, origin: str, destination: str) -> str:
    """Saves flight results to Desktop and opens in default text editor."""
    from datetime import datetime

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"flights_{origin}_{destination}_{ts}.txt".replace(" ", "_")
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    filepath.write_text(content, encoding="utf-8")
    print(f"[FlightFinder] 💾 Saved: {filepath}")

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

def flight_finder(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    """
    Flight Finder — searches Google Flights and speaks results.

    Parameters:
        origin       (str, required) — departure city or airport (e.g. "Istanbul", "IST")
        destination  (str, required) — arrival city or airport (e.g. "London", "LHR")
        date         (str, required) — departure date (any format: "15 Mart", "March 15", "2025-03-15")
        return_date  (str, optional) — return date for round trips
        passengers   (int, optional) — number of passengers (default: 1)
        cabin        (str, optional) — economy | premium | business | first (default: economy)
        save         (bool, optional) — save results to Notepad (default: False)
        show_browser (bool, optional) — keep browser open after search (default: True)

    Examples:
        flight_finder({"origin": "Istanbul", "destination": "London", "date": "15 Mart"})
        flight_finder({"origin": "IST", "destination": "JFK", "date": "2025-04-01",
                       "return_date": "2025-04-15", "cabin": "business", "save": True})
    """
    params = parameters or {}

    origin      = params.get("origin",      "").strip()
    destination = params.get("destination", "").strip()
    date_raw    = params.get("date",        "").strip()
    return_raw  = params.get("return_date", "").strip()
    passengers  = int(params.get("passengers", 1))
    cabin       = params.get("cabin", "economy").strip()
    save        = params.get("save", False)

    if not origin or not destination:
        return "Please provide both origin and destination, sir."
    if not date_raw:
        return "Please provide a departure date, sir."

    date        = _parse_date(date_raw)
    return_date = _parse_date(return_raw) if return_raw else None

    if player:
        player.write_log(f"[FlightFinder] {origin} → {destination} on {date}")

    if speak:
        speak(f"Searching flights from {origin} to {destination} on {date}, sir.")

    print(f"[FlightFinder] ▶️ {origin} → {destination} | {date} | {cabin} | {passengers} pax")

    try:
   
        raw_text, page_url = _search_flights_browser(
            origin, destination, date, return_date, passengers, cabin
        )

        if not raw_text:
            return "Could not retrieve flight data, sir. The page may not have loaded."

        if speak:
            speak("Analysing the results now.")

        flights = _parse_flights_with_gemini(raw_text, origin, destination, date)

        spoken = _format_spoken(flights, origin, destination, date)
        if speak:
            speak(spoken)

        result = spoken

        if save and flights:
            notepad_content = _format_notepad(
                flights, origin, destination, date, return_date, page_url
            )
            saved_path = _save_to_notepad(notepad_content, origin, destination)
            result += f" Results saved to Desktop: {saved_path}"

        return result

    except Exception as e:
        print(f"[FlightFinder] ❌ Error: {e}")
        return f"Flight search failed, sir: {e}"