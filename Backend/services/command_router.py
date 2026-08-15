import asyncio
import re
import subprocess

from services import system_tools


def _parse_count(text: str) -> int | None:
    m = re.search(r"\b(\d+)\b", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    if "one" in text:
        return 1
    if "two" in text:
        return 2
    if "three" in text:
        return 3
    if "four" in text:
        return 4
    if "five" in text:
        return 5
    return None


def _parse_duration(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(minute|minutes|min|m|second|seconds|sec|s|hour|hours|hr|h)", text.lower().strip())
    if not m:
        m = re.search(r"\b(\d+)\b", text)
        if m:
            return int(m.group(1))
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit in ("minute", "minutes", "min", "m"):
        return val * 60
    if unit in ("hour", "hours", "hr", "h"):
        return val * 3600
    return val


def _get_current_volume() -> int:
    try:
        result = subprocess.run(
            ["osascript", "-e", "output volume of (get volume settings)"],
            capture_output=True, text=True, timeout=5,
        )
        return int(result.stdout.strip())
    except Exception:
        return 50


def _extract_after(text: str, marker: str) -> str:
    idx = text.lower().find(marker.lower())
    if idx < 0:
        return ""
    return text[idx + len(marker) :].strip()


def _split_items(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    normalized = raw.replace("&", " and ")
    normalized = re.sub(r"\band\b", ",", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace(";", ",")
    parts = [p.strip() for p in normalized.split(",")]
    return [p for p in parts if p]


SHUTDOWN_TRIGGERS = [
    "kill power",
    "begin emergency shut down sequence",
    "initiate emergency shutdown",
    "emergency shutdown",
]


def _triggered(text: str, triggers: list[str]) -> bool:
    t = text.lower().strip()
    return any(phrase in t for phrase in triggers)


async def route_command(user_text: str) -> str | None:
    text = (user_text or "").strip()
    if not text:
        return None
    lower = text.lower().strip()

    if _triggered(lower, SHUTDOWN_TRIGGERS):
        return await asyncio.to_thread(system_tools.initiate_shutdown)

    if system_tools.is_shutdown_pending():
        if _triggered(lower, ["affirmative", "yes", "do it", "proceed", "confirm"]):
            return await asyncio.to_thread(system_tools.confirm_shutdown)
        if _triggered(
            lower, ["negative", "abort", "cancel", "stop", "no", "stand down"]
        ):
            return await asyncio.to_thread(system_tools.abort_shutdown)

    if _triggered(lower, ["stop talking", "stop voice", "shut up", "silence"]):
        return await asyncio.to_thread(system_tools.silence_jarvis)

    if system_tools.is_silenced():
        if _triggered(
            lower,
            [
                "jarvis come back online",
                "come back online",
                "wake up",
                "resume",
                "jarvis wake up",
            ],
        ):
            return await asyncio.to_thread(system_tools.wake_jarvis)
        return "Voice control is currently silenced. Say Jarvis come back online to reactivate."

    if _triggered(
        lower, ["system stats", "system status", "how is my mac", "system info"]
    ):
        return await asyncio.to_thread(system_tools.get_system_stats)

    if _triggered(lower, ["mute volume", "mute sound", "mute audio"]):
        return await asyncio.to_thread(system_tools.mute_volume)
    if _triggered(lower, ["unmute volume", "unmute sound", "unmute audio"]):
        return await asyncio.to_thread(system_tools.unmute_volume)
    if "volume" in lower:
        m = re.search(r"(\d+)", lower)
        if _triggered(lower, ["set volume", "volume to"]):
            level = int(m.group(1)) if m else 50
            return await asyncio.to_thread(system_tools.set_volume, level)
        if _triggered(lower, ["turn up", "volume up", "increase volume"]):
            current = _get_current_volume()
            step = int(m.group(1)) if m else 10
            return await asyncio.to_thread(system_tools.set_volume, min(100, current + step))
        if _triggered(lower, ["turn down", "volume down", "decrease volume"]):
            current = _get_current_volume()
            step = int(m.group(1)) if m else 10
            return await asyncio.to_thread(system_tools.set_volume, max(0, current - step))
        if _triggered(lower, ["current volume", "what is the volume"]):
            return await asyncio.to_thread(system_tools.get_volume)

    if "clipboard" in lower or "clip board" in lower:
        if _triggered(lower, ["read", "what", "show", "get"]):
            return await asyncio.to_thread(system_tools.read_clipboard)
        if _triggered(lower, ["copy", "save"]):
            text = re.sub(
                r"^(copy|save)\s+(to\s+)?(clipboard|clip board)\s*",
                "", text, flags=re.IGNORECASE
            ).strip()
            if text:
                return await asyncio.to_thread(system_tools.write_clipboard, text)

    if "screenshot" in lower or "capture screen" in lower or "screen shot" in lower:
        delay = 0
        m = re.search(r"(\d+)\s*second", lower)
        if m:
            delay = int(m.group(1))
        interactive = "area" in lower or "region" in lower or "selection" in lower
        return await asyncio.to_thread(system_tools.take_screenshot, delay, interactive)

    if "timer" in lower or "alarm" in lower:
        if _triggered(lower, ["cancel", "stop", "clear"]):
            return await asyncio.to_thread(system_tools.cancel_timers)
        if _triggered(lower, ["list", "active", "check", "how many"]):
            return await asyncio.to_thread(system_tools.list_timers)
        if _triggered(lower, ["set", "create", "start"]):
            seconds = _parse_duration(lower) or 60
            label = _extract_after(text, "called") or _extract_after(text, "named") or _extract_after(text, "for")
            return await asyncio.to_thread(system_tools.set_timer, seconds, label)

    if "note" in lower:
        if _triggered(lower, ["save", "write", "take", "make", "create", "add"]):
            content = re.sub(
                r"^(save|write|take|make|create|add)\s+(a\s+)?note\s*(:\s*)?(\s*that\s+)?",
                "", text, flags=re.IGNORECASE
            ).strip()
            if content:
                return await asyncio.to_thread(system_tools.save_note, content)
        if _triggered(lower, ["read", "get", "show", "what", "my notes", "list"]):
            count = _parse_count(lower) or 5
            return await asyncio.to_thread(system_tools.read_notes, count)

    if "close" in lower and "chrome" in lower and "tab" in lower:
        count = _parse_count(lower) or 1
        return await asyncio.to_thread(system_tools.close_chrome_tabs, count)

    if lower.startswith("close "):
        app = re.sub(r"^close\s+", "", text, flags=re.IGNORECASE).strip()
        if app:
            return await asyncio.to_thread(system_tools.close_application, app)

    if "open" in lower:
        normalized = re.sub(r"[^a-z0-9]+", " ", lower)
        matches: list[tuple[int, str]] = []
        for key in system_tools.KNOWN_SITES.keys():
            idx = normalized.find(key)
            if idx >= 0:
                matches.append((idx, key))
        matches.sort(key=lambda item: item[0])

        sites: list[str] = []
        for _idx, key in matches:
            if key not in sites:
                sites.append(key)

        if sites:
            if len(sites) == 1:
                return await asyncio.to_thread(system_tools.open_url, sites[0])
            return await asyncio.to_thread(system_tools.open_urls, sites)

        target = re.sub(r"^.*?\bopen\b\s+", "", text, flags=re.IGNORECASE).strip()
        if not target:
            return None

        try:
            return await asyncio.to_thread(system_tools.open_url, target)
        except Exception:
            pass

        apps = _split_items(target)
        if not apps:
            return None
        opened = 0
        for app in apps[:5]:
            try:
                await asyncio.to_thread(system_tools.open_application, app)
                opened += 1
            except Exception:
                continue
        if opened == 1:
            return f"Opened {apps[0]} on your Mac."
        if opened > 1:
            return f"Opened {opened} apps on your Mac."
        return None

    if "weather" in lower:
        city = ""
        m = re.search(r"\bweather\s+in\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            city = m.group(1).strip()
        return await asyncio.to_thread(system_tools.get_weather, city or None)

    if "news" in lower or "headlines" in lower:
        query = ""
        for marker in (
            "news about",
            "news on",
            "news for",
            "headlines about",
            "headlines on",
        ):
            if marker in lower:
                query = _extract_after(text, marker)
                break
        return await asyncio.to_thread(system_tools.get_news, query or None)

    if (
        "read email" in lower
        or "check email" in lower
        or "check gmail" in lower
        or "read gmail" in lower
    ):
        count = _parse_count(lower) or 5
        return await asyncio.to_thread(system_tools.read_latest_emails, count)

    if ("send email" in lower or "send gmail" in lower) and "to" in lower:
        to = _extract_after(text, "to")
        subject = ""
        body = ""
        subject_markers = [" subject ", " title "]
        body_markers = [" body ", " message ", " content "]

        for m in subject_markers:
            if m in lower:
                before, after = re.split(
                    m.strip(), text, maxsplit=1, flags=re.IGNORECASE
                )
                to = before.split("to", 1)[-1].strip()
                rest = after.strip()
                subject = rest
                break

        for m in body_markers:
            if m in lower:
                before, after = re.split(
                    m.strip(), text, maxsplit=1, flags=re.IGNORECASE
                )
                if not subject:
                    subject = "Jarvis Email"
                body = after.strip()
                break

        to = to.split()[0].strip()
        if not to or not body:
            return "Say: send email to someone@example.com subject Hello body Your message."
        if not subject:
            subject = "Jarvis Email"
        return await asyncio.to_thread(system_tools.send_email, to, subject, body)

    if "linkedin" in lower and ("content" in lower or "post" in lower):
        content_type = "post"
        if "article" in lower:
            content_type = "article"
        elif "carousel" in lower:
            content_type = "carousel"
        subject = _extract_after(text, "about") or _extract_after(text, "on")
        if not subject:
            return "Say: create linkedin content about [subject]."
        return await asyncio.to_thread(
            system_tools.create_linkedin_content, subject, content_type
        )

    if "whatsapp" in lower:
        if "send" in lower or "message" in lower:
            recipient = ""
            message = ""
            if "to" in lower:
                recipient = _extract_after(text, "to").split()[0]
            if "message" in lower:
                message = _extract_after(text, "message")
            if recipient and message:
                return await asyncio.to_thread(
                    system_tools.send_whatsapp_message, recipient, message
                )
            return "Say: send whatsapp message to mom message Hi."

        if "call" in lower or "video" in lower:
            recipient = _extract_after(text, "to").split()[0]
            if not recipient:
                return "Say: call mom on whatsapp"
            call_type = "video" if "video" in lower else "audio"
            return await asyncio.to_thread(
                system_tools.make_whatsapp_call, recipient, call_type
            )

    return None
