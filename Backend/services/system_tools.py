import asyncio
import json
import os
import platform
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import primp
from ddgs import DDGS

from services.gmail_api import (
    format_latest_emails_summary,
    read_latest_emails as _read_latest_emails,
)
from services.gmail_api import send_email as _send_email

KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://www.twitter.com",
    "x": "https://www.x.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "github": "https://www.github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chat.openai.com",
    "whatsapp": "https://web.whatsapp.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "amazonin": "https://www.amazon.in",
    "amazonindia": "https://www.amazon.in",
    "tiktok": "https://www.tiktok.com",
}

APP_NAME_ALIASES = {
    "capcut": "CapCut",
    "google chrome": "Google Chrome",
    "chrome": "Google Chrome",
    "safari": "Safari",
    "finder": "Finder",
    "notes": "Notes",
    "music": "Music",
    "photos": "Photos",
    "calendar": "Calendar",
    "messages": "Messages",
    "mail": "Mail",
    "terminal": "Terminal",
    "cursor": "Cursor",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
}

MAX_TABS_TO_CLOSE = 20
APP_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 .&'_-]{1,80}$")

_SHUTDOWN_STATE = {"pending": False}
_JARVIS_STATE = {"silenced": False}


def is_shutdown_pending() -> bool:
    return _SHUTDOWN_STATE["pending"]


def is_silenced() -> bool:
    return _JARVIS_STATE["silenced"]


def initiate_shutdown() -> str:
    _SHUTDOWN_STATE["pending"] = True
    return "Are you sure you want to shut down your Mac? Say affirmative to proceed, or negative to cancel."


def confirm_shutdown() -> str:
    if not _SHUTDOWN_STATE["pending"]:
        return "No shutdown sequence is currently active."
    _SHUTDOWN_STATE["pending"] = False
    _require_macos()
    subprocess.run(
        ["osascript", "-e", 'tell app "System Events" to shut down'],
        check=False,
        timeout=10,
    )
    return "Shutting down your Mac now. Goodbye, sir."


def abort_shutdown() -> str:
    if not _SHUTDOWN_STATE["pending"]:
        return "No shutdown sequence to abort."
    _SHUTDOWN_STATE["pending"] = False
    return "Shutdown sequence aborted. Standing by."


def silence_jarvis() -> str:
    _JARVIS_STATE["silenced"] = True
    _SHUTDOWN_STATE["pending"] = False
    return "Voice control silenced. Say Jarvis come back online to reactivate."


def wake_jarvis() -> str:
    _JARVIS_STATE["silenced"] = False
    return "Welcome back, sir. I'm listening."


def _require_macos() -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("System control tools only work on macOS.")


# ─── System Monitoring ────────────────────────────────────────────────


def get_system_stats() -> str:
    _require_macos()
    parts = []

    uptime_s = subprocess.run(
        ["sysctl", "-n", "kern.boottime"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    m = re.search(r"sec = (\d+)", uptime_s)
    if m:
        boot_sec = int(m.group(1))
        elapsed = datetime.now().timestamp() - boot_sec
        days, rem = divmod(int(elapsed), 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts.append(f"Uptime: {days}d {hours}h {minutes}m")

    cpu_out = subprocess.run(
        ["ps", "-A", "-o", "%cpu="],
        capture_output=True, text=True, timeout=5,
    ).stdout
    cpus = [float(x) for x in cpu_out.strip().splitlines() if x.strip()]
    avg_cpu = sum(cpus) / len(cpus) if cpus else 0
    parts.append(f"CPU: {avg_cpu:.1f}% overall")

    mem_out = subprocess.run(
        ["vm_stat"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    mem_lines = mem_out.strip().splitlines()
    pages_used = 0
    pages_free = 0
    for line in mem_lines:
        if line.startswith("Pages active"):
            pages_used += int(line.split(":")[1].strip().rstrip("."))
        elif line.startswith("Pages wired"):
            pages_used += int(line.split(":")[1].strip().rstrip("."))
        elif line.startswith("Pages free"):
            pages_free += int(line.split(":")[1].strip().rstrip("."))
    total_pages = pages_used + pages_free
    if total_pages > 0:
        mem_pct = round(pages_used / total_pages * 100)
        parts.append(f"Memory: {mem_pct}% used")

    disk_out = subprocess.run(
        ["df", "-h", "/"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    disk_lines = disk_out.strip().splitlines()
    if len(disk_lines) >= 2:
        disk_cols = disk_lines[1].split()
        if len(disk_cols) >= 5:
            parts.append(f"Disk: {disk_cols[4]} used of {disk_cols[1]}")

    batt_out = subprocess.run(
        ["pmset", "-g", "batt"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    if "InternalBattery" in batt_out:
        batt_lines = batt_out.strip().splitlines()
        for line in batt_lines:
            if "%" in line:
                m2 = re.search(r"(\d+)%", line)
                status = "charging" if "charging" in line.lower() else "on battery"
                if m2:
                    parts.append(f"Battery: {m2.group(1)}% ({status})")
                break

    return ". ".join(parts) + "." if parts else "Could not retrieve system stats."


# ─── Volume Control ───────────────────────────────────────────────────


def set_volume(level: int) -> str:
    _require_macos()
    level = max(0, min(100, int(level)))
    subprocess.run(
        ["osascript", "-e", f"set volume output volume {level}"],
        check=True, timeout=5,
    )
    return f"Volume set to {level}%."


def get_volume() -> str:
    _require_macos()
    result = subprocess.run(
        ["osascript", "-e", "output volume of (get volume settings)"],
        capture_output=True, text=True, timeout=5,
    )
    vol = result.stdout.strip()
    return f"Current volume is {vol}%." if vol else "Could not read volume."


def mute_volume() -> str:
    _require_macos()
    subprocess.run(
        ["osascript", "-e", "set volume output muted true"],
        check=True, timeout=5,
    )
    return "Volume muted."


def unmute_volume() -> str:
    _require_macos()
    subprocess.run(
        ["osascript", "-e", "set volume output muted false"],
        check=True, timeout=5,
    )
    return "Volume unmuted."


# ─── Clipboard ────────────────────────────────────────────────────────


def read_clipboard() -> str:
    _require_macos()
    result = subprocess.run(
        ["pbpaste"], capture_output=True, text=True, timeout=5,
    )
    text = result.stdout.strip()
    if not text:
        return "Clipboard is empty."
    preview = text[:500]
    if len(text) > 500:
        preview += "..."
    return f"Clipboard: {preview}"


def write_clipboard(text: str) -> str:
    _require_macos()
    subprocess.run(
        ["pbcopy"], input=text, text=True, timeout=5,
    )
    return "Copied to clipboard."


# ─── Screenshot ───────────────────────────────────────────────────────


def take_screenshot(delay: int = 0, interactive: bool = False) -> str:
    _require_macos()
    desktop = Path.home() / "Desktop"
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = desktop / f"Screenshot_{ts}.png"

    args = ["screencapture"]
    if interactive:
        args.append("-i")
    if delay > 0:
        args.extend(["-T", str(int(delay))])
    args.append(str(path))

    subprocess.run(args, check=True, timeout=30)
    return f"Screenshot saved to Desktop as Screenshot_{ts}.png."


# ─── Timer / Alarm ────────────────────────────────────────────────────


_ACTIVE_TIMERS: list[threading.Timer] = []


def set_timer(seconds: int, label: str = "") -> str:
    _require_macos()
    secs = max(1, int(seconds))
    name = label.strip() or f"{secs}-second timer"

    from services.local_speaker import speak

    def _on_timer():
        announce = f"Sir, your {name} is up."
        speak(announce)

    timer = threading.Timer(secs, _on_timer)
    timer.daemon = True
    timer.start()
    _ACTIVE_TIMERS.append(timer)

    if secs < 60:
        display = f"{secs} seconds"
    else:
        mins = secs // 60
        rem_s = secs % 60
        display = f"{mins} minutes" + (f" {rem_s} seconds" if rem_s else "")
    return f"Timer set for {display}."


def list_timers() -> str:
    active = [t for t in _ACTIVE_TIMERS if t.is_alive()]
    if not active:
        return "No active timers."
    return f"You have {len(active)} active timer(s)."


def cancel_timers() -> str:
    global _ACTIVE_TIMERS
    for t in _ACTIVE_TIMERS:
        t.cancel()
    _ACTIVE_TIMERS = []
    return "All timers cancelled."


# ─── Notes ────────────────────────────────────────────────────────────


_NOTES_FILE = Path.home() / "Documents" / "JarvisNotes.md"


def _ensure_notes_file():
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _NOTES_FILE.exists():
        _NOTES_FILE.write_text("# Jarvis Notes\n\n", encoding="utf-8")


def save_note(text: str) -> str:
    content = (text or "").strip()
    if not content:
        return "Nothing to save."
    _ensure_notes_file()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- **{ts}**: {content}\n")
    preview = content[:80]
    if len(content) > 80:
        preview += "..."
    return f"Note saved: {preview}"


def read_notes(count: int = 5) -> str:
    _ensure_notes_file()
    lines = _NOTES_FILE.read_text(encoding="utf-8").strip().splitlines()
    notes = [ln for ln in lines if ln.startswith("- **")]
    if not notes:
        return "No notes found."
    recent = notes[-min(count, len(notes)):]
    return "Recent notes: " + " | ".join(recent)


def _clean_site_phrase(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = cleaned.strip("`'\"")
    cleaned = re.sub(r"^[\s,;:.-]+", "", cleaned)
    cleaned = re.sub(r"[\s,;:.-]+$", "", cleaned)
    cleaned = re.sub(
        r"^(open|go to|goto|visit|launch|start)\s+", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\s+(website|site|page)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _split_site_list(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    normalized = raw.replace("&", " and ")
    normalized = re.sub(r"\bopen\s+", ", ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bthen\b", ",", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\band\b", ",", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace(";", ",")
    parts = [p for p in (x.strip() for x in normalized.split(",")) if p]
    return [_clean_site_phrase(p) for p in parts if _clean_site_phrase(p)]


def _normalize_url(url_or_name: str) -> str:
    raw = _clean_site_phrase(url_or_name)
    if not raw:
        raise ValueError("URL or site name is required.")

    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    if key in KNOWN_SITES:
        return KNOWN_SITES[key]

    if not raw.startswith(("http://", "https://")):
        if "." in raw and " " not in raw:
            raw = f"https://{raw}"
        else:
            raise ValueError(
                f"Unknown site '{url_or_name}'. Provide a full https:// URL."
            )

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url_or_name}")

    return raw


def _sanitize_app_name(app_name: str) -> str:
    cleaned = (app_name or "").strip()
    alias = APP_NAME_ALIASES.get(cleaned.lower())
    if alias:
        return alias
    if not APP_NAME_PATTERN.fullmatch(cleaned):
        raise ValueError(f"Invalid application name: {app_name}")
    return cleaned


def open_url(url: str) -> str:
    _require_macos()
    parts = _split_site_list(url)
    if len(parts) > 1:
        return open_urls(parts)

    target = _normalize_url(url)
    subprocess.run(["open", target], check=True, timeout=15)
    return f"Opened {target} in your default browser."


def open_urls(urls: list | str) -> str:
    _require_macos()
    if isinstance(urls, str):
        urls = _split_site_list(urls)
    if not urls:
        raise ValueError("At least one URL is required.")

    opened = []
    for item in urls[:10]:
        target = _normalize_url(str(item))
        subprocess.run(["open", target], check=True, timeout=15)
        opened.append(target)

    if len(urls) > 10:
        return f"Opened {len(opened)} sites (limited to 10): {', '.join(opened)}"
    return f"Opened {len(opened)} site(s): {', '.join(opened)}"


def open_application(app_name: str) -> str:
    _require_macos()
    app = _sanitize_app_name(app_name)
    subprocess.run(["open", "-a", app], check=True, timeout=15)
    return f"Opened {app} on your Mac."


def close_application(app_name: str) -> str:
    _require_macos()
    app = _sanitize_app_name(app_name)
    script = f'tell application "{app}" to quit'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode == 0:
        return f"Closed {app} on your Mac."
    subprocess.run(["pkill", "-x", app], check=False, timeout=10)
    return f"Attempted to close {app} on your Mac."


def close_chrome_tabs(count: int = 1) -> str:
    _require_macos()
    tabs = max(1, min(int(count), MAX_TABS_TO_CLOSE))

    script = f"""
    tell application "Google Chrome"
      if not running then
        return "Chrome is not running."
      end if
      if (count of windows) is 0 then
        return "Chrome has no open windows."
      end if
      set closedCount to 0
      repeat {tabs} times
        if (count of tabs of front window) > 0 then
          tell front window to close active tab
          set closedCount to closedCount + 1
        end if
      end repeat
      return "Closed " & closedCount & " tab(s) in Chrome."
    end tell
    """

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "AppleScript failed").strip()
        raise RuntimeError(detail)

    return (result.stdout or "").strip() or f"Closed {tabs} Chrome tab(s)."


def count_desktop_folders() -> str:
    _require_macos()
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return "Desktop folder was not found."

    folders = [
        p.name for p in desktop.iterdir() if p.is_dir() and not p.name.startswith(".")
    ]
    count = len(folders)
    preview = ", ".join(folders[:8])
    suffix = f" Names include: {preview}." if preview else ""
    return f"There are {count} folders on your Desktop.{suffix}"


def get_desktop_summary() -> str:
    _require_macos()
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return "Desktop folder was not found."

    folders = []
    files = []
    for p in desktop.iterdir():
        if p.name.startswith("."):
            continue
        if p.is_dir():
            folders.append(p.name)
        else:
            files.append(p.name)

    return (
        f"Desktop summary: {len(folders)} folders and {len(files)} files. "
        f"Folders: {', '.join(folders[:12]) or 'none'}. "
        f"Files: {', '.join(files[:12]) or 'none'}."
    )


def _load_contacts() -> dict:
    backend_dir = Path(__file__).resolve().parents[1]
    configured = (os.getenv("CONTACTS_PATH") or "").strip()
    path = Path(configured) if configured else (backend_dir / "contacts.json")
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _resolve_contact(recipient: str) -> str:
    cleaned = (recipient or "").strip()
    if not cleaned:
        raise ValueError("Recipient is required.")
    contacts = _load_contacts()
    key = re.sub(r"[^a-z0-9]", "", cleaned.lower())
    for name, value in contacts.items():
        stored_key = re.sub(r"[^a-z0-9]", "", str(name).lower())
        if stored_key == key:
            return str(value)
    return cleaned


def send_whatsapp_message(recipient: str, message: str) -> str:
    bridge = (os.getenv("WHATSAPP_BRIDGE_URL") or "").strip()
    if not bridge:
        raise RuntimeError("WHATSAPP_BRIDGE_URL is not set in Backend/.env")
    to = _resolve_contact(recipient)
    text = (message or "").strip()
    if not text:
        raise ValueError("Message is required.")

    url = f"{bridge.rstrip('/')}/send-message"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json={"to": to, "message": text})

    if response.status_code >= 400:
        raise RuntimeError(response.text or "WhatsApp bridge request failed")
    return f"Sent WhatsApp message to {recipient}."


def send_email(to: str, subject: str, body: str) -> str:
    return _send_email(to, subject, body)


def read_latest_emails(count: int = 5) -> str:
    items = _read_latest_emails(count=count)
    return format_latest_emails_summary(items)


WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather(city: str | None = None) -> str:
    target_city = (
        (city or "").strip()
        or (os.getenv("DEFAULT_WEATHER_CITY") or "").strip()
        or "Botad"
    )

    with httpx.Client(timeout=20.0) as client:
        geo_resp = client.get(
            GEOCODING_URL,
            params={"name": target_city, "count": 1, "language": "en", "format": "json"},
        )
    if geo_resp.status_code >= 400 or not geo_resp.json().get("results"):
        return f"Could not find coordinates for {target_city}."

    loc = geo_resp.json()["results"][0]
    lat, lon, name = loc["latitude"], loc["longitude"], loc.get("name", target_city)

    with httpx.Client(timeout=20.0) as client:
        wx_resp = client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code",
                "timezone": "auto",
            },
        )
    if wx_resp.status_code >= 400:
        raise RuntimeError(wx_resp.text or "Open-Meteo request failed")

    data = wx_resp.json().get("current", {})
    temp = data.get("temperature_2m")
    code = data.get("weather_code")
    desc = WMO_CODES.get(code, "unknown") if code is not None else "unknown"

    if temp is not None:
        return f"The weather in {name} is {desc} with a temperature of {temp}°C."
    return f"Weather fetched for {name}."


def get_news(query: str | None = None) -> str:
    api_key = (os.getenv("NEWSAPI_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("NEWSAPI_KEY is not set in Backend/.env")
    q = (
        (query or "").strip()
        or (os.getenv("DEFAULT_NEWS_QUERY") or "").strip()
        or "India"
    )

    url = "https://newsapi.org/v2/everything"
    with httpx.Client(timeout=25.0) as client:
        response = client.get(
            url,
            params={
                "q": q,
                "apiKey": api_key,
                "pageSize": 5,
                "sortBy": "publishedAt",
                "language": "en",
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(response.text or "NewsAPI request failed")
    data = response.json()
    articles = data.get("articles") or []
    titles = [str(a.get("title") or "").strip() for a in articles][:3]
    titles = [t for t in titles if t]
    if not titles:
        return f"No news found for {q}."
    joined = " ".join([f"News {i + 1}: {t}." for i, t in enumerate(titles)])
    return joined


def create_linkedin_content(subject: str, content_type: str = "post") -> str:
    from services.linkedin_content import generate_and_save_to_sheets

    return generate_and_save_to_sheets(subject, content_type)


def search_images(query: str, count: int = 4) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    results = []
    with DDGS() as ddgs:
        for r in ddgs.images(q, max_results=min(count, 8)):
            url = (r.get("image") or "").strip()
            title = (r.get("title") or "").strip()
            if url:
                results.append({"url": url, "title": title})
    return results


def web_search(query: str, num_results: int = 5) -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError("Search query is required.")
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, max_results=min(num_results, 10)):
            title = (r.get("title") or "").strip()
            snippet = (r.get("body") or "").strip()
            url = (r.get("href") or "").strip()
            if title or snippet:
                results.append({"title": title, "snippet": snippet, "url": url})
    if not results:
        return f"No search results found for '{q}'."
    return json.dumps(results, indent=2, ensure_ascii=False)


def web_fetch(url: str) -> str:
    target = (url or "").strip()
    if not target:
        raise ValueError("URL is required.")
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"
    client = primp.Client(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
        timeout=30,
        follow_redirects=True,
    )
    resp = client.get(target)
    if resp.status_code >= 400:
        raise RuntimeError(f"Failed to fetch {target}: HTTP {resp.status_code}")
    text = resp.text
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:5000]
    if len(text) < 100:
        raise RuntimeError(f"Fetched page at {target} has insufficient readable text.")
    return text


def make_whatsapp_call(recipient: str, call_type: str = "audio") -> str:
    _require_macos()
    to = _resolve_contact(recipient)
    digits = re.sub(r"[^\d]", "", to)
    if not digits:
        raise ValueError(f"Could not resolve phone number for {recipient}.")
    wa_url = f"https://wa.me/{digits}"
    subprocess.run(["open", wa_url], check=True, timeout=10)
    call_label = "video" if call_type == "video" else "audio"
    return f"Opened WhatsApp chat with {recipient} in your browser. Click the {call_label} call button to start the {call_label} call."


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open one website in the default browser. Use full https URL or known site names like youtube, instagram, facebook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Website URL or known site name (e.g. youtube, https://www.instagram.com)",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_urls",
            "description": "Open multiple websites at once in the browser. Use when user asks to open several sites in one command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs or site names",
                    }
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open a macOS application by name (e.g. CapCut, Safari, Finder, Chrome).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Application name as shown on Mac",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_application",
            "description": "Close a macOS application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Application name as shown on Mac",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_chrome_tabs",
            "description": "Close one or more tabs in Google Chrome. Use when user asks to close tab(s) in Chrome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of tabs to close (default 1)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_desktop_folders",
            "description": "Count how many folders are on the user's Desktop.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_desktop_summary",
            "description": "Get folder count, file count, and names on the Desktop.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": "Send a WhatsApp message via the local WhatsApp bridge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Phone number or contact name",
                    },
                    "message": {"type": "string", "description": "Message text"},
                },
                "required": ["recipient", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email using the authenticated Gmail account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_latest_emails",
            "description": "Read the latest emails (metadata only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "How many emails to read (default 5, max 10)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name (optional)"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Get latest news headlines for a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query/topic (optional)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_linkedin_content",
            "description": "Generate LinkedIn content (posts/articles/carousels) about a topic using AI, and save it to the Google Sheet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "The topic or subject to create content about",
                    },
                    "content_type": {
                        "type": "string",
                        "enum": ["post", "article", "carousel"],
                        "description": "Type of LinkedIn content to generate (default: post)",
                    },
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information on any topic. Returns relevant results with titles, snippets, and URLs. Use this for research, biographies, news, facts, or any question requiring up-to-date information from the internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'Albert Einstein biography', 'latest AI news 2026')",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of search results to return (default 5, max 10)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and extract readable text content from a specific URL. Use this after web_search to read full articles, Wikipedia pages, or any detailed webpage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch content from (e.g. https://en.wikipedia.org/wiki/Albert_Einstein)",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_whatsapp_call",
            "description": "Make a WhatsApp audio or video call to a contact. Opens WhatsApp chat in the browser so the user can click the call button.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Contact name or phone number",
                    },
                    "call_type": {
                        "type": "string",
                        "enum": ["audio", "video"],
                        "description": "Type of call: audio or video (default: audio)",
                    },
                },
                "required": ["recipient"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_shutdown",
            "description": "Begin emergency shutdown sequence or kill power. Asks for confirmation before shutting down the Mac.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_shutdown",
            "description": "Confirm and execute a pending Mac shutdown. Only works after initiate_shutdown has been called.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abort_shutdown",
            "description": "Abort or cancel a pending shutdown sequence.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "silence_jarvis",
            "description": "Silence voice control. Stops listening and requires a wake phrase to reactivate.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wake_jarvis",
            "description": "Reactivate voice control after being silenced. Welcome back message.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Get Mac system statistics: CPU usage, memory usage, disk usage, battery level, and uptime.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set the system volume to a specific level (0-100).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Volume level 0-100",
                    }
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_volume",
            "description": "Get the current system volume level.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mute_volume",
            "description": "Mute system audio output.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unmute_volume",
            "description": "Unmute system audio output.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "Read the current text content from the Mac clipboard.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_clipboard",
            "description": "Copy text to the Mac clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to copy to clipboard",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture a screenshot. Use interactive=true for area selection, delay for countdown in seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "delay": {
                        "type": "integer",
                        "description": "Delay in seconds before capture (default 0)",
                    },
                    "interactive": {
                        "type": "boolean",
                        "description": "Let user select area (default false, captures full screen)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a countdown timer. Jarvis will announce when time is up.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Number of seconds for the timer",
                    },
                    "label": {
                        "type": "string",
                        "description": "Optional label/name for the timer",
                    },
                },
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_timers",
            "description": "Check how many active timers are currently running.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timers",
            "description": "Cancel all active timers.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Save a quick note to JarvisNotes.md in Documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The note text to save",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_notes",
            "description": "Read the most recent saved notes from JarvisNotes.md.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of recent notes to return (default 5)",
                    }
                },
                "required": [],
            },
        },
    },
]

TOOL_HANDLERS = {
    "open_url": lambda args: open_url(args.get("url", "")),
    "open_urls": lambda args: open_urls(args.get("urls", [])),
    "open_application": lambda args: open_application(args.get("app_name", "")),
    "close_application": lambda args: close_application(args.get("app_name", "")),
    "close_chrome_tabs": lambda args: close_chrome_tabs(args.get("count", 1)),
    "count_desktop_folders": lambda _args: count_desktop_folders(),
    "get_desktop_summary": lambda _args: get_desktop_summary(),
    "send_whatsapp_message": lambda args: send_whatsapp_message(
        args.get("recipient", ""), args.get("message", "")
    ),
    "send_email": lambda args: send_email(
        args.get("to", ""), args.get("subject", ""), args.get("body", "")
    ),
    "read_latest_emails": lambda args: read_latest_emails(args.get("count", 5)),
    "get_weather": lambda args: get_weather(args.get("city")),
    "get_news": lambda args: get_news(args.get("query")),
    "create_linkedin_content": lambda args: create_linkedin_content(
        args.get("subject", ""), args.get("content_type", "post")
    ),
    "web_search": lambda args: web_search(
        args.get("query", ""), args.get("num_results", 5)
    ),
    "web_fetch": lambda args: web_fetch(args.get("url", "")),
    "make_whatsapp_call": lambda args: make_whatsapp_call(
        args.get("recipient", ""), args.get("call_type", "audio")
    ),
    "initiate_shutdown": lambda _args: initiate_shutdown(),
    "confirm_shutdown": lambda _args: confirm_shutdown(),
    "abort_shutdown": lambda _args: abort_shutdown(),
    "silence_jarvis": lambda _args: silence_jarvis(),
    "wake_jarvis": lambda _args: wake_jarvis(),
    "get_system_stats": lambda _args: get_system_stats(),
    "set_volume": lambda args: set_volume(args.get("level", 50)),
    "get_volume": lambda _args: get_volume(),
    "mute_volume": lambda _args: mute_volume(),
    "unmute_volume": lambda _args: unmute_volume(),
    "read_clipboard": lambda _args: read_clipboard(),
    "write_clipboard": lambda args: write_clipboard(args.get("text", "")),
    "take_screenshot": lambda args: take_screenshot(
        args.get("delay", 0), args.get("interactive", False)
    ),
    "set_timer": lambda args: set_timer(
        args.get("seconds", 60), args.get("label", "")
    ),
    "list_timers": lambda _args: list_timers(),
    "cancel_timers": lambda _args: cancel_timers(),
    "save_note": lambda args: save_note(args.get("text", "")),
    "read_notes": lambda args: read_notes(args.get("count", 5)),
}


def execute_tool(name: str, arguments: str | dict) -> str:
    if name not in TOOL_HANDLERS:
        return f"Unknown tool: {name}"

    try:
        parsed_args = (
            json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        )
        if not isinstance(parsed_args, dict):
            parsed_args = {}
        return TOOL_HANDLERS[name](parsed_args)
    except Exception as exc:
        return f"Tool '{name}' failed: {exc}"


async def execute_tool_async(name: str, arguments: str | dict) -> str:
    if name not in TOOL_HANDLERS:
        return f"Unknown tool: {name}"

    try:
        parsed_args = (
            json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        )
        if not isinstance(parsed_args, dict):
            parsed_args = {}
        return await asyncio.to_thread(TOOL_HANDLERS[name], parsed_args)
    except Exception as exc:
        return f"Tool '{name}' failed: {exc}"
