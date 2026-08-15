import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from services.llm import _cerebras_chat, _groq_chat


def _load_config() -> dict:
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "linkedin_content.json"
    if not config_path.exists():
        return {}
    raw = config_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _pick_content_type(config: dict, content_type: str | None) -> dict:
    types = config.get("content_types") or {}
    if content_type and content_type in types:
        return {"key": content_type, **types[content_type]}
    default = config.get("generation_settings", {}).get("default_content_type", "post")
    return {"key": default, **types.get(default, types.get("post", {}))}


def _build_structure_text(structure: list) -> str:
    return "\n".join(f"- {s}" for s in structure)


def _build_hashtag_instruction(config: dict) -> str:
    hs = config.get("hashtag_strategy") or {}
    count = hs.get("count_per_post", 5)
    ratio = hs.get("mix_ratio") or {}
    return (
        f"Include exactly {count} hashtags at the end of the post. "
        f"Mix: {ratio.get('broad_hashtags', 2)} broad, "
        f"{ratio.get('niche_hashtags', 2)} niche, "
        f"{ratio.get('trending_hashtags', 1)} trending."
    )


def _build_system_prompt(config: dict) -> str:
    prompts = config.get("prompts") or {}
    brand = config.get("brand_voice") or {}
    return (
        (prompts.get("system_prompt") or "")
        + f"\n\nTone: {brand.get('tone', 'professional')}"
        + f"\nPersonality: {brand.get('personality', 'thought leader')}"
        + f"\nPerspective: {brand.get('perspective', 'first-person')}"
        + f"\nAudience: {brand.get('audience', 'professionals')}"
        + f"\nEmotion: {brand.get('emotion', 'insightful')}"
    )


def _call_llm(messages: list) -> str:
    groq_available = bool(os.getenv("GROQ_API_KEY", "").strip())
    cerebras_available = bool(os.getenv("CEREBRAS_API_KEY", "").strip())
    preferred = (os.getenv("LLM_PROVIDER") or "").strip().lower()

    if preferred == "cerebras" and cerebras_available:
        provider = "cerebras"
    elif preferred == "groq" and groq_available:
        provider = "groq"
    else:
        provider = "groq" if groq_available else "cerebras"

    import asyncio

    async def _call():
        if provider == "cerebras":
            result = await _cerebras_chat(messages)
        else:
            result = await _groq_chat(messages)
        return (result.get("content") or "").strip()

    return asyncio.run(_call())


def generate_content(subject: str, content_type: str | None = None) -> list[dict[str, Any]]:
    config = _load_config()
    if not config:
        raise RuntimeError(
            "linkedin_content.json not found. Ensure it exists in the Backend directory."
        )

    type_info = _pick_content_type(config, content_type)
    gen_settings = config.get("generation_settings") or {}
    prompts = config.get("prompts") or {}
    brand = config.get("brand_voice") or {}

    system_prompt = _build_system_prompt(config)

    structure_text = _build_structure_text(type_info.get("structure", []))
    hashtag_instruction = _build_hashtag_instruction(config)

    user_prompt = (
        prompts.get("user_prompt_template", "")
        .replace("{content_type}", type_info.get("label", "post"))
        .replace("{subject}", subject)
        .replace("{tone}", brand.get("tone", "professional"))
        .replace("{personality}", brand.get("personality", "thought leader"))
        .replace("{perspective}", brand.get("perspective", "first-person"))
        .replace("{structure}", structure_text)
        .replace("{hashtag_instruction}", hashtag_instruction)
    )

    variations = gen_settings.get("variations_per_topic", 3)
    results = []

    for i in range(variations):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw = _call_llm(messages)

        headline = ""
        body = raw
        hashtags = ""

        lines = raw.strip().split("\n")
        if lines and not lines[0].startswith(("#", "http")):
            headline = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

        hashtag_lines = [
            l.strip()
            for l in body.split("\n")
            if l.strip().startswith("#")
        ]
        if hashtag_lines:
            hashtags = " ".join(hashtag_lines)
            body_lines = [
                l for l in body.split("\n") if not l.strip().startswith("#")
            ]
            body = "\n".join(body_lines).strip()

        results.append(
            {
                "variation": i + 1,
                "subject": subject,
                "content_type": type_info.get("label", "Post"),
                "headline": headline,
                "body": body,
                "hashtags": hashtags,
                "character_count": len(raw),
            }
        )

    return results


def generate_and_save_to_sheets(
    subject: str, content_type: str | None = None
) -> str:
    from services.google_sheets import append_row

    contents = generate_content(subject, content_type)
    today = date.today().isoformat()

    saved = 0
    for item in contents:
        row = [
            today,
            item["subject"],
            item["content_type"],
            item["headline"],
            item["body"],
            item["hashtags"],
            str(item["character_count"]),
            "Draft",
            f"Variation {item['variation']}",
        ]
        try:
            append_row(row)
            saved += 1
        except Exception as exc:
            raise RuntimeError(
                f"Generated content but failed to save to sheet: {exc}"
            )

    return (
        f"Created {saved} LinkedIn {content_type or 'post'} variation(s) "
        f"about '{subject}' and saved them to your sheet."
    )
