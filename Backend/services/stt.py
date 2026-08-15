import os

import httpx

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_WHISPER_MODEL = "whisper-large-v3-turbo"


def _guess_mime(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".webm"):
        return "audio/webm"
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".mp3"):
        return "audio/mpeg"
    if name.endswith(".m4a"):
        return "audio/mp4"
    return "application/octet-stream"


async def transcribe_audio(audio_bytes: bytes, filename: str = "speech.webm") -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in Backend/.env")

    model = (os.getenv("GROQ_WHISPER_MODEL", "").strip() or DEFAULT_WHISPER_MODEL)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, audio_bytes, _guess_mime(filename))},
            data={
                "model": model,
                "language": "en",
                "response_format": "json",
                "temperature": 0,
            },
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(detail or "Groq transcription failed")

    payload = response.json()
    return (payload.get("text") or "").strip()
