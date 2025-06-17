from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
import os
import tempfile
import uuid
from pydantic import BaseModel
from typing import List, Optional
import base64
import io
from PIL import Image
import torch
from transformers import pipeline
from chatbot import (
    chat_with_voice,
    transcribe_and_chat,
    load_tts_model,
    generate_speech
)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="front_end"), name="static")

# Initialize the image analysis model
try:
    image_to_text = pipeline("image-to-text", model="Salesforce/blip-image-captioning-base")
    print("Image analysis model loaded successfully")
except Exception as e:
    print(f"Error loading image analysis model: {e}")
    image_to_text = None

# Pydantic models for request validation
class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []
    model: str = "mistral"
    audio_prompt: Optional[str] = None
    exaggeration: float = 0.5
    temperature: float = 0.8
    cfg_weight: float = 0.5

class ScreenAnalysisRequest(BaseModel):
    image: str

# Routes
@app.get("/")
async def root():
    return FileResponse("front_end/index.html")

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        updated_history, wav = chat_with_voice(
            request.message,
            request.history,
            request.model,
            request.audio_prompt,
            request.exaggeration,
            request.temperature,
            request.cfg_weight
        )

        # Save audio
        sr, samples = wav
        temp_file = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.wav")
        from soundfile import write
        write(temp_file, samples, sr)

        return {
            "history": updated_history,
            "audio_path": os.path.basename(temp_file)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    full_path = os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(full_path):
        return FileResponse(full_path, media_type="audio/wav")
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/analyze-screen")
async def analyze_screen(request: ScreenAnalysisRequest):
    try:
        # Remove the data URL prefix if present
        if ',' in request.image:
            image_data = request.image.split(',')[1]
        else:
            image_data = request.image
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        
        # Generate caption
        if image_to_text:
            result = image_to_text(image)
            caption = result[0]['generated_text']
            
            # Add some context to make it more conversational
            commentary = f"I see {caption.lower()}"
            
            # Add some variety to the commentary
            prefixes = [
                "Looking at your screen, ",
                "I notice that ",
                "On your screen, ",
                "I can see that ",
                "Currently, "
            ]
            
            import random
            commentary = random.choice(prefixes) + commentary
            
            return {"commentary": commentary}
        else:
            return {"commentary": "I'm having trouble analyzing the screen content right now."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 