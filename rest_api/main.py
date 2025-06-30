from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import google.generativeai as genai
import os

# Initialize FastAPI app
app = FastAPI(title="Gemini API Service")

# Configure Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")
genai.configure(api_key=GEMINI_API_KEY)

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = []
    model: str = "gemini-1.5-flash"

@app.post("/gemini-chat")
async def gemini_chat(request: ChatRequest):
    try:
        model = genai.GenerativeModel(request.model)
        chat = model.start_chat(history=request.history)
        response = chat.send_message(request.message)
        return {"response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
