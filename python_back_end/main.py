from fastapi import FastAPI, HTTPException, Request, UploadFile, File, WebSocket, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.websockets import WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn, os, sys, tempfile, uuid, base64, io, logging, re, requests, random
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import asyncpg
from gemini_api import query_gemini, is_gemini_configured
from typing import List, Optional, Dict, Any
from vison_models.llm_connector import query_qwen, query_llm, load_qwen_model, unload_qwen_model

from pydantic import BaseModel
import torch, soundfile as sf
import whisper  # Import Whisper

# ─── Authentication Setup ──────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", "key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pguser:pgpassword@pgsql:5432/database")

class AuthRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar: Optional[str] = None

# ─── Authentication Utilities ───────────────────────────────────────────────────
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_db_connection():
    return await asyncpg.connect(DATABASE_URL)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info(f"JWT payload: {payload}")
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id: int = int(user_id_str)
        logger.info(f"User ID from token: {user_id}")
    except (JWTError, ValueError) as e:
        logger.error(f"JWT decode error: {e}")
        raise credentials_exception
    
    conn = await get_db_connection()
    try:
        user = await conn.fetchrow("SELECT id, username, email, avatar FROM users WHERE id = $1", user_id)
        if user is None:
            logger.error(f"User not found for ID: {user_id}")
            raise credentials_exception
        logger.info(f"User found: {dict(user)}")
        return UserResponse(**dict(user))
    finally:
        await conn.close()

# ─── Model Management -----------------------------------------------------------
from model_manager import (
    unload_models, unload_all_models, reload_models_if_needed, log_gpu_memory,
    get_tts_model, get_whisper_model, generate_speech, wait_for_vram
)
import logging
import time

# Add the ollama_cli directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'ollama_cli'))
from vibe_agent import VibeAgent

# ─── Set up logging ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Initialize vibe agent ─────────────────────────────────────────────────────
# Note: Import VibeAgent after all model_manager imports to avoid circular imports
try:
    vibe_agent = VibeAgent(project_dir=os.getcwd())
    logger.info("✅ VibeAgent initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize VibeAgent: {e}")
    vibe_agent = None

# ─── Additional logging setup ──────────────────────────────────────────────────
if 'logger' not in locals():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# ─── Paths ---------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "front_end")
JARVIS_VOICE_PATH = os.path.abspath(
    "jarvis_voice.mp3"
)  # Point to the file in project root

# ─── FastAPI init --------------------------------------------------------------
app = FastAPI(title="Jarves-TTS API")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    logger.info("Frontend directory mounted at %s", FRONTEND_DIR)

# ─── Device & models -----------------------------------------------------------
device = 0 if torch.cuda.is_available() else -1
logger.info("Using device: %s", "cuda" if device == 0 else "cpu")



# ─── Config --------------------------------------------------------------------
OLLAMA_URL = "http://ollama:11434"
DEFAULT_MODEL = "mistral"

# ─── Pydantic schemas ----------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = []
    model: str = DEFAULT_MODEL
    audio_prompt: Optional[str] = None  # overrides JARVIS_VOICE_PATH if provided
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class ResearchChatRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = []
    model: str = DEFAULT_MODEL
    enableWebSearch: bool = True
    audio_prompt: Optional[str] = None  # overrides JARVIS_VOICE_PATH if provided
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class ScreenAnalysisRequest(BaseModel):
    image: str  # base-64 image (data-URI or raw)

class SynthesizeSpeechRequest(BaseModel):
    text: str
    audio_prompt: Optional[str] = None
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class VibeCommandRequest(BaseModel):
    command: str
    mode: str = "assistant"

class AnalyzeAndRespondRequest(BaseModel):
    image: str  # base-64 image (data-URI or raw)
    model: str = DEFAULT_MODEL
    system_prompt: Optional[str] = None

class ScreenAnalysisWithTTSRequest(BaseModel):
    image: str  # base-64 image (data-URI or raw)
    model: str = DEFAULT_MODEL
    system_prompt: Optional[str] = None
    audio_prompt: Optional[str] = None
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class VibeCodingRequest(BaseModel):
    message: str
    files: List[Dict[str, Any]] = []
    terminalHistory: List[str] = []
    model: str = DEFAULT_MODEL
    audio_prompt: Optional[str] = None
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class VoiceTranscribeRequest(BaseModel):
    model: str = DEFAULT_MODEL

class RunCommandRequest(BaseModel):
    command: str

class SaveFileRequest(BaseModel):
    filename: str
    content: str

# ─── Helpers -------------------------------------------------------------------
BROWSER_PATTERNS = [
    r"^(?:open|launch|go\s+to|navigate\s+to|take\s+me\s+to|visit)\s+",
    r"^(?:abre|abrír|navega\s+a|llévame\s+a|visita)\s+",
    r"^(?:search|look\s+up|google|find)\s+(?:for\s+)?",
    r"^(?:busca|buscar|encuentra|investigar?)\s+(?:sobre\s+)?",
    r"^(?:open|create)\s+(?:\d+\s+)?(?:new\s+)?tabs?",
    r"^(?:abre|crea)\s+(?:\d+\s+)?(?:nueva[s]?\s+)?pestaña[s]?",
]
is_browser_command = lambda txt: any(
    re.match(p, txt.lower().strip()) for p in BROWSER_PATTERNS
)

# ─── Routes --------------------------------------------------------------------
@app.get("/", tags=["frontend"])
async def root() -> FileResponse:
    index_html = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_html):
        return FileResponse(index_html)
    raise HTTPException(404, "Frontend not found")

# ─── Authentication Endpoints ─────────────────────────────────────────────────────
@app.post("/api/auth/signup", response_model=TokenResponse, tags=["auth"])
async def signup(request: SignupRequest):
    conn = await get_db_connection()
    try:
        # Check if user already exists
        existing_user = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1 OR username = $2",
            request.email, request.username
        )
        if existing_user:
            raise HTTPException(status_code=409, detail="User with this email or username already exists")
        
        # Hash password and create user
        hashed_password = get_password_hash(request.password)
        user_id = await conn.fetchval(
            "INSERT INTO users (username, email, password) VALUES ($1, $2, $3) RETURNING id",
            request.username, request.email, hashed_password
        )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user_id)}, expires_delta=access_token_expires
        )
        
        return TokenResponse(access_token=access_token, token_type="bearer")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        await conn.close()

@app.post("/api/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(request: AuthRequest):
    conn = await get_db_connection()
    try:
        user = await conn.fetchrow(
            "SELECT id, password FROM users WHERE email = $1",
            request.email
        )
        if not user or not verify_password(request.password, user["password"]):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user["id"])}, expires_delta=access_token_expires
        )
        
        return TokenResponse(access_token=access_token, token_type="bearer")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        await conn.close()

@app.get("/api/auth/me", response_model=UserResponse, tags=["auth"])
async def get_current_user_info(current_user: UserResponse = Depends(get_current_user)):
    return current_user

# Import new modules




@app.post("/api/chat", tags=["chat"])
async def chat(req: ChatRequest, request: Request):
    """
    Main conversational endpoint.
    Produces: JSON {history, audio_path}
    """
    try:
        # ── 1. Update dialogue history with the latest user turn
        history = req.history + [{"role": "user", "content": req.message}]
        response_text: str

        # ── 2. Browser automation branch -------------------------------------------------
        if is_browser_command(req.message):
            try:
                from trash.browser import smart_url_handler, search_google, open_new_tab

                result = smart_url_handler(req.message)
                response_text = (
                    search_google(result["query"])
                    if isinstance(result, dict) and result.get("type") == "search"
                    else open_new_tab(result)
                )
            except Exception as e:
                logger.error("Browser cmd failed: %s", e)
                response_text = "¡Ay! Hubo un problema con esa acción del navegador."
        # ── 3. LLM generation branch ------------------------------------------------------
        elif req.model == "gemini-1.5-flash":
            response_text = query_gemini(req.message, req.history)
        else:
            # Load system prompt from file
            system_prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
            try:
                with open(system_prompt_path, 'r', encoding='utf-8') as f:
                    system_prompt = f.read().strip()
            except FileNotFoundError:
                logger.warning("system_prompt.txt not found, using default prompt")
                system_prompt = (
                    'You are "Jarves", a voice-first local assistant. '
                    "Reply in ≤25 spoken-style words, sprinkling brief Spanish when natural, Be bilangual about 80 percent english and 20 percent spanish"
                    'Begin each answer with a short verbal acknowledgment (e.g., "Claro,", "¡Por supuesto!", "Right away").'
                )
            OLLAMA_ENDPOINT = "/api/chat"  # single source of truth

            payload = {
                "model": req.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.message},
                ],
                "stream": False,
            }

            logger.info("→ Asking Ollama %s with model %s", OLLAMA_ENDPOINT, req.model)

            resp = requests.post(
                f"{OLLAMA_URL}{OLLAMA_ENDPOINT}", json=payload, timeout=90
            )

            if resp.status_code != 200:
                logger.error("Ollama error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()

            response_text = resp.json().get("message", {}).get("content", "").strip()

        # ── 4. Update history with assistant reply
        new_history = history + [{"role": "assistant", "content": response_text}]

        # ── 5. Text-to-speech -----------------------------------------------------------
        reload_models_if_needed()
        tts = get_tts_model()  # Get TTS model from model_manager

        # Handle audio prompt path
        audio_prompt_path = req.audio_prompt or JARVIS_VOICE_PATH
        if not os.path.isfile(audio_prompt_path):
            logger.warning(
                "Audio prompt %s not found, falling back to default voice.",
                audio_prompt_path,
            )
            audio_prompt_path = None

        # Debug logging for the audio prompt path
        if audio_prompt_path:
            if not os.path.exists(audio_prompt_path):
                logger.warning(f"JARVIS voice prompt missing at: {audio_prompt_path}")
            else:
                logger.info(f"Cloning voice using prompt: {audio_prompt_path}")

        sr, wav = generate_speech(
            text=response_text,
            model=tts,
            audio_prompt=audio_prompt_path,
            exaggeration=req.exaggeration,
            temperature=req.temperature,
            cfg_weight=req.cfg_weight,
        )

        # ── 6. Persist WAV to /tmp so nginx (or FastAPI fallback) can serve it ------------
        filename = f"response_{uuid.uuid4()}.wav"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        sf.write(filepath, wav, sr)
        logger.info("Audio written to %s", filepath)

        return {
            "history": new_history,
            "audio_path": f"/api/audio/{filename}",  # FastAPI route below (or nginx alias /audio/)
        }

    except Exception as e:
        logger.exception("Chat endpoint crashed")
        raise HTTPException(500, str(e)) from e

@app.get("/api/audio/{filename}", tags=["audio"])
async def serve_audio(filename: str):
    """
    FastAPI static audio fallback (use nginx /audio alias in production for speed).
    """
    full_path = os.path.join(tempfile.gettempdir(), filename)
    if not os.path.exists(full_path):
        raise HTTPException(404, f"Audio file not found: {filename}")
    return FileResponse(full_path, media_type="audio/wav")

@app.post("/api/analyze-screen", tags=["vision"])
async def analyze_screen(req: ScreenAnalysisRequest):
    try:
        # Unload ALL models to free maximum GPU memory for Qwen2VL
        logger.info("🖼️ Starting screen analysis - clearing ALL GPU memory")
        unload_all_models()  # Unload everything for maximum memory
        
        # Decode base64 image and save to a temporary file
        image_data = base64.b64decode(req.image.split(",")[1])
        temp_image_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.png")
        with open(temp_image_path, "wb") as f:
            f.write(image_data)

        # Use Qwen to caption the image
        qwen_prompt = "Describe this image in detail."
        qwen_caption = query_qwen(temp_image_path, qwen_prompt)
        os.remove(temp_image_path) # Clean up temp file

        if "[Qwen error]" in qwen_caption:
            raise HTTPException(status_code=500, detail=qwen_caption)

        # Unload Qwen2VL immediately after use to free memory
        logger.info("🔄 Unloading Qwen2VL after screen analysis")
        unload_qwen_model()
        
        # Use LLM to get a response based on the caption
        llm_system_prompt = "You are an AI assistant that helps users understand what's on their screen. Provide a concise and helpful response based on the screen content."
        llm_user_prompt = f"Here's what's on the user's screen: {qwen_caption}\nWhat should they do next?"
        llm_response = query_llm(llm_user_prompt, system_prompt=llm_system_prompt)
        
        # Reload TTS/Whisper models for future use
        logger.info("🔄 Reloading TTS/Whisper models after screen analysis")
        reload_models_if_needed()
        
        logger.info("✅ Screen analysis complete - all models restored")
        return {"commentary": qwen_caption, "llm_response": llm_response}

    except Exception as e:
        logger.error("Screen analysis failed: %s", e)
        # Ensure models are reloaded even on error
        logger.info("🔄 Reloading models after error")
        reload_models_if_needed()
        raise HTTPException(500, str(e)) from e

@app.post("/api/analyze-and-respond", tags=["vision"])
async def analyze_and_respond(req: AnalyzeAndRespondRequest):
    """
    Analyze screen with Qwen vision model and get LLM response using selected model.
    Features intelligent model management to optimize GPU memory usage.
    """
    try:
        # Unload ALL models to free maximum GPU memory for Qwen2VL
        logger.info("🖼️ Starting enhanced screen analysis - clearing ALL GPU memory")
        unload_all_models()  # Unload everything for maximum memory
        
        # Decode base64 image and save to a temporary file
        image_data = base64.b64decode(req.image.split(",")[1])
        temp_image_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.png")
        with open(temp_image_path, "wb") as f:
            f.write(image_data)

        # Use Qwen to analyze the image
        qwen_prompt = "Analyze this screen in detail. Describe what you see, including any text, UI elements, applications, and content visible."
        logger.info("🔍 Analyzing screen with Qwen2VL...")
        qwen_analysis = query_qwen(temp_image_path, qwen_prompt)
        os.remove(temp_image_path)  # Clean up temp file

        if "[Qwen error]" in qwen_analysis:
            raise HTTPException(status_code=500, detail=qwen_analysis)

        # Unload Qwen2VL immediately after analysis to free memory for LLM
        logger.info("🔄 Unloading Qwen2VL after analysis, preparing for LLM")
        unload_qwen_model()
        
        # Use the selected LLM model to generate a response based on Qwen's analysis
        # Use custom system prompt if provided, otherwise use default
        system_prompt = req.system_prompt or "You are Jarvis, an AI assistant analyzing what the user is seeing on their screen. Provide helpful insights, suggestions, or commentary about what you observe. Be conversational and helpful."
        
        logger.info(f"🤖 Generating response with {req.model}")
        if req.model == "gemini-1.5-flash":
            # Use Gemini for response
            llm_response = query_gemini(f"Screen analysis: {qwen_analysis}\n\nPlease provide helpful insights about this screen.", [])
        else:
            # Use Ollama for response
            payload = {
                "model": req.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Screen analysis: {qwen_analysis}\n\nPlease provide helpful insights about this screen."},
                ],
                "stream": False,
            }

            logger.info(f"→ Asking Ollama with model {req.model}")
            resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=90)
            
            if resp.status_code != 200:
                logger.error("Ollama error %s: %s", resp.status_code, resp.text)
                raise HTTPException(status_code=500, detail="LLM request failed")
            
            llm_response = resp.json().get("message", {}).get("content", "").strip()

        # Reload TTS/Whisper models for future use
        logger.info("🔄 Reloading TTS/Whisper models after enhanced screen analysis")
        reload_models_if_needed()

        logger.info("✅ Enhanced screen analysis complete - all models restored")
        return {
            "response": llm_response,
            "screen_analysis": qwen_analysis,
            "model_used": req.model
        }

    except Exception as e:
        logger.error("Analyze and respond failed: %s", e)
        # Ensure models are reloaded even on error
        logger.info("🔄 Reloading models after error")
        reload_models_if_needed()
        raise HTTPException(500, str(e)) from e

@app.post("/api/analyze-screen-with-tts", tags=["vision"])
async def analyze_screen_with_tts(req: ScreenAnalysisWithTTSRequest):
    """
    Complete screen analysis with Qwen2VL + LLM response + TTS audio output.
    Implements intelligent model management: Qwen2VL -> LLM -> TTS pipeline.
    """
    try:
        # Phase 1: Unload ALL models for maximum memory for Qwen2VL processing
        logger.info("🖼️ Phase 1: Starting screen analysis - clearing ALL GPU memory for Qwen2VL")
        unload_all_models()
        
        # Decode base64 image and save to a temporary file
        image_data = base64.b64decode(req.image.split(",")[1])
        temp_image_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.png")
        with open(temp_image_path, "wb") as f:
            f.write(image_data)

        # Use Qwen2VL to analyze the image
        qwen_prompt = "Analyze this screen comprehensively. Describe what you see, including any text, UI elements, applications, and content. Focus on what the user might need help with."
        logger.info("🔍 Analyzing screen with Qwen2VL...")
        qwen_analysis = query_qwen(temp_image_path, qwen_prompt)
        os.remove(temp_image_path)

        if "[Qwen error]" in qwen_analysis:
            raise HTTPException(status_code=500, detail=qwen_analysis)

        # Phase 2: Unload Qwen2VL to free memory for LLM processing
        logger.info("🤖 Phase 2: Unloading Qwen2VL, generating LLM response")
        unload_qwen_model()
        
        # Generate LLM response
        system_prompt = req.system_prompt or "You are Jarvis, an AI assistant. Based on the screen analysis, provide helpful, conversational insights. Keep responses under 100 words for voice output."
        
        if req.model == "gemini-1.5-flash":
            llm_response = query_gemini(f"Screen analysis: {qwen_analysis}\n\nProvide helpful insights about this screen.", [])
        else:
            payload = {
                "model": req.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Screen analysis: {qwen_analysis}\n\nProvide helpful insights about this screen."},
                ],
                "stream": False,
            }
            resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=90)
            resp.raise_for_status()
            llm_response = resp.json().get("message", {}).get("content", "").strip()

        # Phase 3: Reload TTS for audio generation
        logger.info("🔊 Phase 3: Reloading TTS for audio generation")
        reload_models_if_needed()
        
        # Generate TTS audio
        audio_prompt_path = req.audio_prompt or JARVIS_VOICE_PATH
        if not os.path.isfile(audio_prompt_path):
            logger.warning(f"Audio prompt {audio_prompt_path} not found, using default voice")
            audio_prompt_path = None

        sr, wav = generate_speech(
            text=llm_response,
            model=get_tts_model(),
            audio_prompt=audio_prompt_path,
            exaggeration=req.exaggeration,
            temperature=req.temperature,
            cfg_weight=req.cfg_weight,
        )

        # Save audio file
        filename = f"screen_analysis_{uuid.uuid4()}.wav"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        sf.write(filepath, wav, sr)
        
        logger.info("✅ Complete screen analysis with TTS finished")
        return {
            "response": llm_response,
            "screen_analysis": qwen_analysis,
            "model_used": req.model,
            "audio_path": f"/api/audio/{filename}",
            "processing_stages": {
                "qwen_analysis": "✅ Completed",
                "llm_response": "✅ Completed", 
                "tts_generation": "✅ Completed"
            }
        }

    except Exception as e:
        logger.error("Screen analysis with TTS failed: %s", e)
        # Ensure models are reloaded on error
        reload_models_if_needed()
        raise HTTPException(500, str(e)) from e

# Whisper model will be loaded on demand

@app.post("/api/mic-chat", tags=["voice"])
async def mic_chat(file: UploadFile = File(...)):
    try:
        # Ensure Whisper model is loaded
        reload_models_if_needed()
        
        # Save uploaded file to temp
        contents = await file.read()
        tmp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.wav")
        with open(tmp_path, "wb") as f:
            f.write(contents)

        # Transcribe it
        result = get_whisper_model().transcribe(tmp_path)
        message = result.get("text", "").strip()
        logger.info(f"MIC input transcribed: {message}")

        if not message:
            raise HTTPException(400, "Could not transcribe anything.")

        # Now use existing chat logic
        chat_req = ChatRequest(message=message)
        return await chat(chat_req, request=None)

    except Exception as e:
        logger.exception("Mic chat failed")
        raise HTTPException(500, str(e))

# Research endpoints using the new research module with LangChain
from agent_research import research_agent, fact_check_agent, comparative_research_agent
from research.web_search import WebSearchAgent
# from research.research_agent import ResearchAgent  # Not used directly

@app.post("/api/research-chat", tags=["research"])
async def research_chat(req: ResearchChatRequest):
    """
    Enhanced research chat endpoint with comprehensive web search and analysis
    """
    try:
        if not req.message:
            return {"error": "Message is required"}, 400

        # Unload models to free GPU memory for research processing
        logger.info("🔍 Starting research - unloading models to free GPU memory")
        unload_models()

        # Call the enhanced research agent
        response_data = research_agent(req.message, req.model)

        # Format response for chat interface
        if "error" in response_data:
            response_content = f"Research Error: {response_data['error']}"
        else:
            # Format the comprehensive research response
            analysis = response_data.get("analysis", "No analysis available")
            sources = response_data.get("sources", [])
            sources_found = response_data.get("sources_found", 0)
            
            response_content = f"{analysis}\n\n"
            
            if sources:
                response_content += f"**Sources ({sources_found} found):**\n"
                logger.info(f"Formatting {len(sources)} sources for display")
                for i, source in enumerate(sources[:5], 1):  # Limit to top 5 sources
                    title = source.get('title', 'Unknown Title')
                    url = source.get('url', 'No URL')
                    logger.info(f"Source {i}: title='{title}', url='{url}'")
                    response_content += f"{i}. [{title}]({url})\n"

        # Update history with assistant reply
        new_history = req.history + [{"role": "assistant", "content": response_content}]

        # ── Generate TTS for research response ──────────────────────────────────────────
        logger.info("🔊 Research complete - reloading models for TTS generation")
        reload_models_if_needed()
        tts = get_tts_model()  # Get TTS model from model_manager

        # Handle audio prompt path
        audio_prompt_path = req.audio_prompt or JARVIS_VOICE_PATH
        if not os.path.isfile(audio_prompt_path):
            logger.warning(
                "Audio prompt %s not found, falling back to default voice.",
                audio_prompt_path,
            )
            audio_prompt_path = None

        # Debug logging for the audio prompt path
        if audio_prompt_path:
            if not os.path.exists(audio_prompt_path):
                logger.warning(f"JARVIS voice prompt missing at: {audio_prompt_path}")
            else:
                logger.info(f"Cloning voice using prompt: {audio_prompt_path}")

        # Create a more conversational version of the research response for TTS
        # Remove markdown formatting and make it more speech-friendly
        tts_text = response_content.replace("**", "").replace("*", "").replace("#", "")
        # Replace numbered lists with more natural speech
        import re
        tts_text = re.sub(r'^\d+\.\s*', '', tts_text, flags=re.MULTILINE)
        # Replace markdown links with just the title
        tts_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', tts_text)
        # Limit length for TTS (keep it conversational)
        if len(tts_text) > 800:
            tts_text = tts_text[:800] + "... and more details are available in the sources."

        sr, wav = generate_speech(
            text=tts_text,
            model=tts,
            audio_prompt=audio_prompt_path,
            exaggeration=req.exaggeration,
            temperature=req.temperature,
            cfg_weight=req.cfg_weight,
        )

        # ── Persist WAV to /tmp so it can be served ──────────────────────────────────────
        filename = f"research_{uuid.uuid4()}.wav"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        sf.write(filepath, wav, sr)
        logger.info("Research TTS audio written to %s", filepath)

        return {
            "history": new_history, 
            "response": response_content,
            "audio_path": f"/api/audio/{filename}"
        }

    except Exception as e:
        logger.exception("Research chat endpoint crashed")
        raise HTTPException(500, str(e))

class FactCheckRequest(BaseModel):
    claim: str
    model: str = DEFAULT_MODEL

class ComparativeResearchRequest(BaseModel):
    topics: List[str]
    model: str = DEFAULT_MODEL

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5
    extract_content: bool = False

@app.post("/api/fact-check", tags=["research"])
async def fact_check(req: FactCheckRequest):
    """
    Fact-check a claim using web search and analysis
    """
    try:
        result = fact_check_agent(req.claim, req.model)
        return result
    except Exception as e:
        logger.exception("Fact-check endpoint crashed")
        raise HTTPException(500, str(e))

@app.post("/api/comparative-research", tags=["research"])
async def comparative_research(req: ComparativeResearchRequest):
    """
    Compare multiple topics using web research
    """
    try:
        if len(req.topics) < 2:
            raise HTTPException(400, "At least 2 topics are required for comparison")
        
        result = comparative_research_agent(req.topics, req.model)
        return result
    except Exception as e:
        logger.exception("Comparative research endpoint crashed")
        raise HTTPException(500, str(e))

@app.post("/api/web-search", tags=["research"])
async def web_search(req: WebSearchRequest):
    """
    Perform web search using LangChain search agents
    """
    try:
        logger.info(f"Web search request: query='{req.query}', max_results={req.max_results}, extract_content={req.extract_content}")
        
        # Initialize the web search agent
        search_agent = WebSearchAgent(max_results=req.max_results)
        
        if req.extract_content:
            # Search and extract content from URLs
            logger.info("Performing search with content extraction...")
            result = search_agent.search_and_extract(req.query, extract_content=True)
        else:
            # Just search without content extraction
            logger.info("Performing basic search...")
            search_results = search_agent.search_web(req.query, req.max_results)
            result = {
                "query": req.query,
                "search_results": search_results,
                "extracted_content": []
            }
        
        logger.info(f"Search completed: found {len(result.get('search_results', []))} results")
        return result
    except Exception as e:
        logger.exception(f"Web search endpoint crashed for query '{req.query}': {str(e)}")
        raise HTTPException(500, f"Search failed: {str(e)}")

# ─── Warmup ────────────────────────────────────────────────────────
# Models will be loaded on demand to manage GPU memory efficiently
logger.info("Models will be loaded on demand for optimal memory management")

# ─── Dev entry-point -----------------------------------------------------------
@app.get("/api/ollama-models", tags=["models"])
async def get_ollama_models():
    """
    Fetches the list of available models from the Ollama server.
    """
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        response.raise_for_status()
        models = response.json().get("models", [])
        ollama_model_names = [model["name"] for model in models]

        if is_gemini_configured():
            ollama_model_names.insert(
                0, "gemini-1.5-flash"
            )  # Add Gemini to the beginning

        return ollama_model_names
    except requests.exceptions.RequestException as e:
        logger.error(f"Could not connect to Ollama: {e}")
        raise HTTPException(
            status_code=503, detail="Could not connect to Ollama server"
        )

@app.post("/api/vibe/command")
async def vibe_command(req: VibeCommandRequest):
    vibe_agent.mode = req.mode
    response_text, _ = vibe_agent.process_command(req.command)
    return {"response": response_text}

@app.websocket("/api/ws/vibe")
async def websocket_vibe_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")
            mode = data.get("mode", "assistant")

            if command:
                vibe_agent.mode = mode
                await vibe_agent.process_command(command, websocket)
            else:
                await websocket.send_json({"type": "error", "content": "No command received"})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"type": "error", "content": f"WebSocket error: {e}"})

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
# huh2.0

@app.post("/api/synthesize-speech", tags=["tts"])
async def synthesize_speech(req: SynthesizeSpeechRequest):
    """
    Synthesizes speech from text using the TTS model.
    This endpoint is called by worker nodes.
    """
    try:
        reload_models_if_needed()
        tts = get_tts_model()

        audio_prompt_path = req.audio_prompt or JARVIS_VOICE_PATH
        if not os.path.isfile(audio_prompt_path):
            logger.warning(
                "Audio prompt %s not found, falling back to default voice.",
                audio_prompt_path,
            )
            audio_prompt_path = None

        sr, wav = generate_speech(
            text=req.text,
            model=tts,
            audio_prompt=audio_prompt_path,
            exaggeration=req.exaggeration,
            temperature=req.temperature,
            cfg_weight=req.cfg_weight,
        )

        filename = f"response_{uuid.uuid4()}.wav"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        sf.write(filepath, wav, sr)
        logger.info("Audio written to %s", filepath)

        return {"audio_path": f"/api/audio/{filename}"}

    except Exception as e:
        logger.exception("TTS synthesis endpoint crashed")
        raise HTTPException(500, str(e)) from e

# ─── Vibe Coding Endpoints ─────────────────────────────────────────────────────

@app.post("/api/vibe-coding", tags=["vibe-coding"])
async def vibe_coding(req: VibeCodingRequest):
    """
    Voice-enabled vibe coding with intelligent model management.
    Unloads models → Executes vibe agent → Generates TTS response → Reloads models.
    """
    try:
        # Phase 1: Unload models to free GPU memory for vibe agent processing
        logger.info("🤖 Phase 1: Starting vibe coding - clearing GPU memory for vibe agent")
        unload_all_models()
        
        # Phase 2: Execute vibe agent processing
        logger.info("⚡ Phase 2: Executing vibe agent with Mistral")
        
        # Use the existing vibe agent for processing
        vibe_response, steps = await process_vibe_command_with_context(req.message, req.files, req.terminalHistory, req.model)
        
        # Phase 4: Unload vibe processing, reload models for TTS
        logger.info("🔊 Phase 3: Reloading models for TTS generation")
        reload_models_if_needed()
        
        # Generate TTS response
        audio_prompt_path = req.audio_prompt or JARVIS_VOICE_PATH
        if not os.path.isfile(audio_prompt_path):
            audio_prompt_path = None

        # Create speech-friendly version of response
        tts_text = vibe_response
        if len(tts_text) > 200:
            tts_text = tts_text[:200] + "... I'm ready to help you code this!"

        sr, wav = generate_speech(
            text=tts_text,
            model=get_tts_model(),
            audio_prompt=audio_prompt_path,
            exaggeration=req.exaggeration,
            temperature=req.temperature,
            cfg_weight=req.cfg_weight,
        )

        # Save audio file
        filename = f"vibe_coding_{uuid.uuid4()}.wav"
        filepath = os.path.join(tempfile.gettempdir(), filename)
        sf.write(filepath, wav, sr)
        
        logger.info("✅ Vibe coding complete - all models restored")
        return {
            "response": vibe_response,
            "steps": steps,
            "audio_path": f"/api/audio/{filename}",
            "model_used": req.model,
            "processing_stages": {
                "vibe_agent": "✅ Completed",
                "tts_generation": "✅ Completed"
            }
        }

    except Exception as e:
        logger.error("Vibe coding failed: %s", e)
        # Ensure models are reloaded even on error
        logger.info("🔄 Reloading models after vibe coding error")
        reload_models_if_needed()
        raise HTTPException(500, str(e)) from e

@app.post("/api/voice-transcribe", tags=["vibe-coding"])
async def voice_transcribe(file: UploadFile = File(...), model: str = DEFAULT_MODEL):
    """
    Transcribe voice input for vibe coding with model management.
    """
    try:
        # Ensure Whisper model is loaded
        reload_models_if_needed()
        
        # Save uploaded file to temp
        contents = await file.read()
        tmp_path = os.path.join(tempfile.gettempdir(), f"vibe_{uuid.uuid4()}.wav")
        with open(tmp_path, "wb") as f:
            f.write(contents)

        # Transcribe with Whisper
        result = get_whisper_model().transcribe(tmp_path)
        transcription = result.get("text", "").strip()
        
        # Clean up temp file
        os.remove(tmp_path)
        
        logger.info(f"🎤 Voice transcribed for vibe coding: {transcription}")
        return {"transcription": transcription, "model_used": "whisper-base"}

    except Exception as e:
        logger.error("Voice transcription failed: %s", e)
        raise HTTPException(500, str(e)) from e

@app.post("/api/run-command", tags=["vibe-coding"])
async def run_command(req: RunCommandRequest):
    """
    Execute terminal commands for vibe coding.
    """
    try:
        logger.info(f"🔧 Executing command: {req.command}")
        
        # Security: Basic command filtering
        dangerous_commands = ["rm -rf", "sudo", "format", "del", "shutdown"]
        if any(dangerous in req.command.lower() for dangerous in dangerous_commands):
            return {"output": "❌ Command rejected for security reasons", "error": True}
        
        # Import and use existing command execution
        from os_ops import execute_command
        result = execute_command(req.command)
        
        return {"output": result, "error": False}
        
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return {"output": f"❌ Error: {str(e)}", "error": True}

@app.post("/api/save-file", tags=["vibe-coding"])
async def save_file(req: SaveFileRequest):
    """
    Save file content for vibe coding.
    """
    try:
        logger.info(f"💾 Saving file: {req.filename}")
        
        # Security: Basic path validation
        if ".." in req.filename or req.filename.startswith("/"):
            return {"success": False, "error": "Invalid filename"}
        
        # Save to project directory
        filepath = os.path.join(os.getcwd(), req.filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.content)
        
        return {"success": True, "message": f"File {req.filename} saved successfully"}
        
    except Exception as e:
        logger.error(f"File save failed: {e}")
        return {"success": False, "error": str(e)}

# ─── Vibe Agent Helper Functions ─────────────────────────────────────────────

async def process_vibe_command_with_context(message: str, files: List[Dict], terminal_history: List[str], model: str) -> tuple[str, List[Dict]]:
    """
    Process vibe coding command with full context using the vibe agent logic
    """
    # Create context from files and terminal history
    context = ""
    if files:
        context += "CURRENT FILES:\n"
        for file in files:
            context += f"=== {file.get('name', 'unknown')} ===\n{file.get('content', '')}\n\n"
    
    if terminal_history:
        context += "TERMINAL HISTORY:\n"
        context += "\n".join(terminal_history[-5:])  # Last 5 lines
        context += "\n\n"
    
    # Generate vibe agent response using Ollama
    system_prompt = """You are a Vibe Coding AI assistant. You help users build projects through natural conversation and voice commands.

GUIDELINES:
- Generate practical, executable coding steps
- Be conversational and encouraging  
- Focus on what the user wants to build
- Provide clear, actionable steps
- Keep responses under 100 words for voice output

RESPONSE FORMAT:
Provide your response as conversational text, followed by specific coding steps if needed."""

    user_prompt = f"""
User request: {message}

Context:
{context}

Please provide a helpful, conversational response about how to implement this request. If specific code changes are needed, describe them clearly.
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }

    logger.info(f"→ Asking Ollama with model {model} for vibe coding")
    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    
    vibe_response = resp.json().get("message", {}).get("content", "").strip()
    
    # Generate coding steps based on the message
    steps = generate_vibe_steps(message, vibe_response)
    
    return vibe_response, steps

def generate_vibe_steps(message: str, response: str) -> List[Dict]:
    """
    Generate coding steps based on the user message and AI response
    """
    steps = []
    message_lower = message.lower()
    
    # File creation
    if "create" in message_lower and "file" in message_lower:
        filename = "new_file.py"  # Default
        # Try to extract filename from message
        words = message.split()
        for i, word in enumerate(words):
            if word.lower() in ["file", "create"] and i + 1 < len(words):
                potential_filename = words[i + 1]
                if "." in potential_filename:
                    filename = potential_filename
                break
        
        steps.append({
            "id": "1",
            "description": f"Creating file: {filename}",
            "action": "create_file",
            "target": filename,
            "content": f"# Generated by Vibe Coding AI\n# {message}\n\nprint('Hello from {filename}!')",
            "completed": False
        })
    
    # Web app/API creation
    elif "api" in message_lower or "web" in message_lower or "flask" in message_lower or "fastapi" in message_lower:
        steps.extend([
            {
                "id": "1",
                "description": "Creating main API file",
                "action": "create_file", 
                "target": "app.py",
                "content": "# FastAPI/Flask Web Application\nfrom fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef hello():\n    return {'message': 'Hello from Vibe Coding!'}",
                "completed": False
            },
            {
                "id": "2", 
                "description": "Installing dependencies",
                "action": "install_package",
                "target": "fastapi uvicorn",
                "command": "pip install fastapi uvicorn",
                "completed": False
            }
        ])
    
    # Data analysis/ML
    elif "data" in message_lower or "pandas" in message_lower or "analysis" in message_lower:
        steps.append({
            "id": "1",
            "description": "Creating data analysis script",
            "action": "create_file",
            "target": "analysis.py",
            "content": "# Data Analysis Script\nimport pandas as pd\nimport numpy as np\n\n# Load your data here\ndf = pd.DataFrame({'example': [1, 2, 3]})\nprint(df.head())",
            "completed": False
        })
    
    # Package installation
    elif "install" in message_lower:
        # Extract package names
        packages = []
        common_packages = ["numpy", "pandas", "requests", "flask", "fastapi", "django", "matplotlib", "seaborn"]
        for pkg in common_packages:
            if pkg in message_lower:
                packages.append(pkg)
        
        if packages:
            steps.append({
                "id": "1",
                "description": f"Installing packages: {', '.join(packages)}",
                "action": "install_package",
                "target": " ".join(packages),
                "command": f"pip install {' '.join(packages)}",
                "completed": False
            })
    
    # Default: create a simple script
    if not steps:
        steps.append({
            "id": "1", 
            "description": "Creating script based on your request",
            "action": "create_file",
            "target": "vibe_script.py",
            "content": f"# Script for: {message}\n# Generated by Vibe Coding AI\n\nprint('Starting your vibe coding project!')\n# Add your code here",
            "completed": False
        })
    
    return steps

