import os

import edge_tts

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"


async def synthesize_speech(text: str) -> bytes:
    voice = os.getenv("EDGE_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE
    communicate = edge_tts.Communicate(text, voice)

    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    if not audio_chunks:
        raise RuntimeError("Edge TTS returned no audio data")

    return b"".join(audio_chunks)
