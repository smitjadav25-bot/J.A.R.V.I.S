import json
import os

import httpx

from services.command_router import route_command
from services.system_tools import TOOL_DEFINITIONS, execute_tool_async

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
CEREBRAS_CHAT_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_CHAT_MODEL = "gpt-oss-120b"
MAX_TOOL_ROUNDS = 10

SYSTEM_PROMPT = """You are J.A.R.V.I.S., an advanced AI assistant on the user's Mac.
You can control the computer using tools: open websites, open/close Mac apps, close Chrome tabs, read Desktop info, send WhatsApp messages, send/read Gmail, fetch weather/news, search the web, monitor system stats, control volume, manage clipboard, take screenshots, set timers, save notes, and manage your own voice state.

SYSTEM STATS — Call get_system_stats when the user asks about CPU, memory, disk usage, battery, or uptime.

VOLUME CONTROL — Use set_volume(level 0-100) to set volume to a specific level. Use mute_volume / unmute_volume to toggle sound. Use get_volume to report current volume.

CLIPBOARD — Use read_clipboard to show what's currently copied. Use write_clipboard(text) to copy new text to the clipboard.

SCREENSHOT — Use take_screenshot(delay, interactive) to capture the screen. Set interactive=true if the user wants to select an area or region.

TIMERS — Use set_timer(seconds, label) to set a countdown. The timer will announce when done. Use list_timers to check active timers, cancel_timers to stop all.

NOTES — Use save_note(text) to save a quick note to JarvisNotes.md in Documents. Use read_notes(count) to review recent notes.

SHUTDOWN SEQUENCE — When the user says "kill power", "begin emergency shut down sequence", or "emergency shutdown", call initiate_shutdown to begin the sequence. The user must then confirm with "affirmative" or "yes" (call confirm_shutdown), or cancel with "negative" or "abort" (call abort_shutdown). Always ask for confirmation before shutting down.

SILENCE / WAKE — When the user says "stop talking", "stop voice", "shut up", or "silence", call silence_jarvis to disable voice control. When silenced, only wake phrases will be accepted. To reactivate, the user can say "Jarvis come back online", "wake up", or "resume" — call wake_jarvis.

YOU HAVE WEB RESEARCH CAPABILITIES — use web_search and web_fetch to find up-to-date information on any topic. Never redirect users to open a browser themselves; you do the research inline.

WHEN THE USER ASKS TO RESEARCH A TOPIC, FIND A BIOGRAPHY, GET NEWS, OR LOOK UP INFORMATION:
1. Use web_search to gather information from multiple sources.
2. Use web_fetch to read full articles or Wikipedia pages for depth.
3. Compile the results into a rich, structured response.

BIOGRAPHY REQUESTS — Return data in this JSON structure (no markdown, no backticks, no preamble):
{
  "type": "biography",
  "name": "Full Name",
  "image_query": "Full Name official portrait photo",
  "born": "Date, Place",
  "died": "Date or null",
  "nationality": "Country",
  "known_for": ["achievement 1", "achievement 2"],
  "summary": "3-5 sentence engaging overview",
  "early_life": "paragraph",
  "career": "paragraph",
  "legacy": "paragraph",
  "notable_works": ["work1", "work2"],
  "quotes": ["quote1", "quote2"],
  "image_searches": ["name professional photo", "name historical image"],
  "video_searches": ["name documentary", "name speech or interview"]
}

GENERAL TOPIC RESEARCH — Return data in this JSON structure (no markdown, no backticks, no preamble):
{
  "type": "research",
  "topic": "Topic Name",
  "banner_query": "relevant banner image search term",
  "summary": "2-3 sentence TL;DR",
  "sections": [
    {
      "title": "Section Title",
      "content": "detailed paragraph",
      "image_query": "relevant image search term for this section"
    }
  ],
  "key_facts": ["fact 1", "fact 2", "fact 3"],
  "related_topics": ["topic1", "topic2"],
  "video_searches": ["topic explainer video", "topic documentary"]
}

RESEARCH RULES:
- Use real, verified information from web search. Cross-reference sources.
- Include image_query fields so the UI can fetch and display relevant visuals.
- Include video_searches so YouTube embeds can be shown.
- Keep content engaging, clear, and well-structured.
- Respond ONLY in valid JSON for research/biography — no markdown, no preamble, no backticks.
- You are JARVIS — precise, intelligent, slightly formal but personable.

SYSTEM CONTROL RULES:
- When the user asks to open a website (YouTube, Instagram, etc.), call open_url or open_urls with correct https URLs.
- When they ask to open a Mac app (CapCut, Safari, etc.), call open_application.
- When they ask to close a Mac app, call close_application.
- When they ask to close Chrome tab(s), call close_chrome_tabs with the exact count they requested.
- When they ask how many folders are on the Desktop, call count_desktop_folders or get_desktop_summary.
- When they ask to send a WhatsApp message, call send_whatsapp_message with a recipient and message.
- When they ask to make a WhatsApp audio or video call, call make_whatsapp_call with the recipient and call_type.
- When they ask to send an email, call send_email with to, subject, and body.
- When they ask to read or check emails, call read_latest_emails.
- When they ask about weather, call get_weather.
- When they ask for news, call get_news.
- When they ask to create LinkedIn content about a topic, call create_linkedin_content with the subject and optional content type.
- After tools run, give a short spoken confirmation (1-2 sentences).
- If no tool is needed, answer normally and concisely.
- NOTE: When you return structured JSON (biography/research), the frontend renders it as a rich card with images and video embeds."""


async def _groq_chat(messages: list, tools: list | None = None) -> dict:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in Backend/.env")

    payload = {
        "model": os.getenv("GROQ_CHAT_MODEL", "").strip() or GROQ_CHAT_MODEL,
        "messages": messages[-20:],
        "temperature": 0.4,
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "450")),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(detail or "Groq chat failed")

    return response.json()["choices"][0]["message"]


async def _cerebras_chat(messages: list, tools: list | None = None) -> dict:
    api_key = os.getenv("CEREBRAS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY is not set in Backend/.env")

    payload = {
        "model": os.getenv("CEREBRAS_CHAT_MODEL", "").strip() or CEREBRAS_CHAT_MODEL,
        "messages": messages[-20:],
        "temperature": 0.4,
        "max_tokens": 700,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            CEREBRAS_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(detail or "Cerebras chat failed")

    return response.json()["choices"][0]["message"]


async def chat_completion(user_text: str, history: list | None = None) -> str:
    try:
        routed = await route_command(user_text)
        if routed:
            return routed

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in history or []:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})

        groq_available = bool(os.getenv("GROQ_API_KEY", "").strip())
        cerebras_available = bool(os.getenv("CEREBRAS_API_KEY", "").strip())
        preferred = (os.getenv("LLM_PROVIDER") or "").strip().lower()
        if preferred in ("groq", "cerebras"):
            provider = preferred
        else:
            provider = "groq" if groq_available else "cerebras"
        if provider == "groq" and not groq_available:
            provider = "cerebras"
        if provider == "cerebras" and not cerebras_available:
            provider = "groq"

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                message = await (
                    _cerebras_chat(messages, tools=TOOL_DEFINITIONS)
                    if provider == "cerebras"
                    else _groq_chat(messages, tools=TOOL_DEFINITIONS)
                )
            except Exception as exc:
                detail = str(exc or "")
                is_rate_limited = (
                    "rate limit" in detail.lower()
                    or "tokens per day" in detail.lower()
                    or "tpm" in detail.lower()
                    or "tpd" in detail.lower()
                )
                if provider == "groq" and cerebras_available:
                    provider = "cerebras"
                    message = await _cerebras_chat(messages, tools=TOOL_DEFINITIONS)
                elif provider == "cerebras" and groq_available and not is_rate_limited:
                    provider = "groq"
                    message = await _groq_chat(messages, tools=TOOL_DEFINITIONS)
                else:
                    raise exc

            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                reply = (message.get("content") or "").strip()
                return reply or "Done, sir."

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                fn = tool_call.get("function") or {}
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", "{}")
                tool_result = await execute_tool_async(tool_name, tool_args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": tool_result,
                    }
                )

        return "I completed your requests."
    except Exception as exc:
        detail = str(exc or "")
        if (
            "Rate limit reached" in detail
            or "tokens per day" in detail
            or "TPD" in detail
        ):
            return "Your Groq daily limit is reached. Wait a bit or add CEREBRAS_API_KEY in Backend/.env so Jarvis can continue without stopping."
        trace = str(exc or "")[:200]
        if "api_key" in trace.lower() or "API key" in trace or "not set" in trace.lower():
            return f"Missing API key: {trace}. Check your Backend/.env file."
        if "Connection refused" in trace or "connect" in trace.lower():
            return "Could not reach the AI provider. Check your internet connection."
        return f"I encountered an error while processing that: {trace}"


def parse_history(raw_history: str | None) -> list:
    if not raw_history:
        return []
    try:
        parsed = json.loads(raw_history)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []
