# J.A.R.V.I.S. Backend

Voice pipeline:

1. **Speech-to-text** — Groq Whisper (`whisper-large-v3-turbo`)
2. **LLM + Mac control** — Groq (`llama-3.3-70b-versatile`) with tools:
   - Open websites (YouTube, Instagram, etc.)
   - Open Mac apps (CapCut, Chrome, etc.)
   - Close Chrome tabs (1, 3, or more)
   - Count/list Desktop folders and files
3. **Text-to-speech** — Microsoft Edge neural voices via `edge-tts` (free)

**macOS permissions:** Allow **Automation** for Terminal/Python to control **Google Chrome** when closing tabs (System Settings → Privacy & Security → Automation).

## Setup

```bash
cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY
```

## Run

```bash
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check: `http://localhost:8000/api/health`
