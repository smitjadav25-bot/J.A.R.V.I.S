import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.llm import chat_completion, parse_history
from services.local_speaker import speak
from services.stt import transcribe_audio
from services.system_tools import search_images as _search_images
from services.tts import synthesize_speech

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

app = FastAPI(title="J.A.R.V.I.S. Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_AUDIO_BYTES = 1200


@app.get("/api/search-images")
async def search_images_endpoint(q: str = "", count: int = 4):
    if not q.strip():
        return {"images": []}
    results = _search_images(q, count)
    return {"images": results}


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "groq": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "cerebras": bool(os.getenv("CEREBRAS_API_KEY", "").strip()),
        "systemControl": True,
        "platform": "macOS",
        "tts": "edge-tts",
        "voice": os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural"),
    }


@app.post("/api/voice-turn")
async def voice_turn(
    audio: UploadFile = File(...),
    history: str = Form(default="[]"),
):
    audio_bytes = await audio.read()
    if len(audio_bytes) < MIN_AUDIO_BYTES:
        raise HTTPException(
            status_code=400, detail="Audio too short. Please speak a bit longer."
        )

    try:
        transcript = await transcribe_audio(
            audio_bytes, audio.filename or "speech.webm"
        )
        if not transcript:
            raise HTTPException(
                status_code=400, detail="No speech detected in the recording."
            )

        conversation = parse_history(history)
        reply = await chat_completion(transcript, conversation)
        audio_out = await synthesize_speech(reply)
        audio_base64 = base64.b64encode(audio_out).decode("ascii")

        return JSONResponse(
            {
                "transcript": transcript,
                "reply": reply,
                "audioBase64": audio_base64,
                "audioMimeType": "audio/mpeg",
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class WhatsAppIncoming(BaseModel):
    sender: str
    message: str


@app.post("/api/incoming-whatsapp")
async def incoming_whatsapp(payload: WhatsAppIncoming):
    speak(
        f"Sir, you have a new message from {payload.sender}. They said: {payload.message}"
    )
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_excludes=[".venv/*", "*.pyc"],
    )
