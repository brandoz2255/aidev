"""
FastAPI back-end  – fixed audio-path + minor tidy-ups
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os, tempfile, uuid, base64, io, logging, re, requests
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from PIL import Image
import torch, soundfile as sf
from transformers import pipeline

from chatterbox_tts import load_tts_model, generate_speech

# ─── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "front_end")

# ─── FastAPI init ──────────────────────────────────────────────────────────────
app = FastAPI()

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    logger.info(f"Frontend directory mounted at {FRONTEND_DIR}")

# ─── Device & models ───────────────────────────────────────────────────────────
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info("Using device: %s", device)

try:
    logger.info("Loading image analysis model …")
    image_to_text = pipeline("image-to-text",
                             model="Salesforce/blip-image-captioning-base",
                             device=device)
except Exception as e:
    logger.error("Image model load failed: %s", e)
    image_to_text = None

# ─── Config ────────────────────────────────────────────────────────────────────
OLLAMA_URL     = "http://ollama:11434"
DEFAULT_MODEL  = "mistral"

# ─── Pydantic models ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = []
    model: str = DEFAULT_MODEL
    audio_prompt: Optional[str] = None
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class ScreenAnalysisRequest(BaseModel):
    image: str

# ─── Helpers ───────────────────────────────────────────────────────────────────
BROWSER_PATTERNS = [
    r'^(?:open|launch|go\s+to|navigate\s+to|take\s+me\s+to|visit)\s+',
    r'^(?:abre|abrír|navega\s+a|llévame\s+a|visita)\s+',
    r'^(?:search|look\s+up|google|find)\s+(?:for\s+)?',
    r'^(?:busca|buscar|encuentra|investigar?)\s+(?:sobre\s+)?',
    r'^(?:open|create)\s+(?:\d+\s+)?(?:new\s+)?tabs?',
    r'^(?:abre|crea)\s+(?:\d+\s+)?(?:nueva[s]?\s+)?pestaña[s]?'
]
def is_browser_command(text: str) -> bool:
    return any(re.match(p, text.lower().strip()) for p in BROWSER_PATTERNS)

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    index_html = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_html):
        return FileResponse(index_html)
    raise HTTPException(404, "Frontend not found")

@app.post("/chat")
async def chat_legacy(req: ChatRequest):
    return await chat(req)         # backward-compat shim

@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """
    Main chat endpoint
    """
    try:
        history = req.history + [{"role": "user", "content": req.message}]

        # A) Browser commands delegated to helper (if present)
        if is_browser_command(req.message):
            try:
                from trash.browser import smart_url_handler, search_google, open_new_tab
                result = smart_url_handler(req.message)
                response_text = (search_google(result["query"])
                                 if isinstance(result, dict) and result.get("type") == "search"
                                 else open_new_tab(result))
            except Exception as e:
                logger.error("Browser command error: %s", e)
                response_text = "¡Ay! Hubo un problema con esa acción de navegador."
        # B) Normal LLM call
        else:
            system_prompt = (
                'You are "Jarves", a voice-first local assistant. Reply in ≤25 spoken-style words, '
                'sprinkling brief Spanish when natural. Begin each answer with a short verbal '
                'acknowledgment (e.g., "Claro," "¡Por supuesto!", "Right away").'
            )
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": req.model,
                    "prompt": req.message,
                    "system": system_prompt,
                    "stream": False
                },
                timeout=60
            )
            resp.raise_for_status()
            response_text = resp.json().get("response", "").strip()

        # ── Update history
        new_history = history + [{"role": "assistant", "content": response_text}]

        # ── TTS synthesis
        tts = load_tts_model()
        sr, wav = generate_speech(
            response_text, tts,
            req.audio_prompt, req.exaggeration,
            req.temperature, req.cfg_weight
        )

        # ── Save to /tmp so nginx alias can serve it
        filename   = f"response_{uuid.uuid4()}.wav"
        filepath   = os.path.join(tempfile.gettempdir(), filename)
        sf.write(filepath, wav, sr)

        logger.info(f"Generated audio file: {filepath}")
        if not os.path.exists(filepath):
            logger.error(f"ERROR: Audio file was not created at expected path: {filepath}")

        # NOTE: leading slash makes it absolute for the browser
        return {"history": new_history,
                "audio_path": f"/audio/{filename}"}

    except Exception as e:
        logger.exception("Chat endpoint failed")
        raise HTTPException(500, str(e)) from e

@app.get("/api/audio/{filename}")
async def serve_audio(filename: str):
    """
    Direct FastAPI fallback (not used when nginx /audio alias is active)
    """
    full_path = os.path.join(tempfile.gettempdir(), filename)
    logger.info(f"Serving audio file: {full_path}")
    if not os.path.exists(full_path):
        logger.error(f"ERROR: Audio file not found at: {full_path}")
        raise HTTPException(404, f"Audio file not found: {filename}")
    if os.path.exists(full_path):
        return FileResponse(full_path, media_type="audio/wav")
    raise HTTPException(404, "Audio not found")

@app.post("/api/analyze-screen")
async def analyze_screen(req: ScreenAnalysisRequest):
    try:
        # Decode base-64 image
        img_data = req.image.split(",", 1)[-1]
        image    = Image.open(io.BytesIO(base64.b64decode(img_data)))

        if image_to_text:
            result = image_to_text(image)
            caption = result[0].get("generated_text", "") if result else ""
            if caption:
                prefixes = [
                    "Looking at your screen, ",
                    "I notice that ",
                    "On your screen, ",
                    "I can see that ",
                    "Currently, "
                ]
                import random
                return {"commentary": random.choice(prefixes) + caption.lower()}

        return {"commentary": "I'm having trouble analyzing the screen content right now."}
    except Exception as e:
        logger.error("Screen analysis failed: %s", e)
        raise HTTPException(500, str(e))

# ─── Main (dev) ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
