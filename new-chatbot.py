import gradio as gr
import requests
import torch
import logging
import os
import time
import soundfile as sf
import re
from transformers import pipeline
from chatterbox.tts import ChatterboxTTS, punc_norm
from browser import execute_nlp_browser_command  # Import the new NLP command function

# NOTE: This application requires the 'ffmpeg' command-line tool for audio processing.
# Please install it using your system's package manager (e.g., `sudo apt install ffmpeg`).

# ─── Set up logging ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = "mistral"
DEVICE        = "cuda" if torch.cuda.is_available() else "cpu"

# ─── VRAM Management ────────────────────────────────────────────────────────────
# Set a more flexible VRAM threshold (in bytes) based on available GPU memory
def get_vram_threshold():
    if not torch.cuda.is_available():
        return float('inf')  # No threshold if no CUDA

    total_mem = torch.cuda.get_device_properties(0).total_memory
    # Use 80% of total VRAM as a default threshold, with a minimum of 10GB
    return max(int(total_mem * 0.8), 10 * 1024**3)

THRESHOLD_BYTES = get_vram_threshold()
logger.info(f"VRAM threshold set to {THRESHOLD_BYTES/1024**3:.1f} GiB")

def wait_for_vram(threshold=THRESHOLD_BYTES, interval=0.5):
    """Pause until GPU VRAM usage falls below threshold, then clear cache."""
    if not torch.cuda.is_available():
        return
    used = torch.cuda.memory_allocated()
    while used > threshold:
        logger.info(f"VRAM {used/1024**3:.1f} GiB > {threshold/1024**3:.1f} GiB. Waiting…")
        time.sleep(interval)
        used = torch.cuda.memory_allocated()
    torch.cuda.empty_cache()
    logger.info("VRAM is now below threshold. Proceeding with TTS.")

# ─── Global Model Variables ─────────────────────────────────────────────────────
tts_model    = None
stt_pipeline = None

# ─── Ollama Status & Model Fetching ─────────────────────────────────────────────
def check_ollama_status():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags")
        return r.ok
    except requests.exceptions.RequestException:
        return False

def fetch_ollama_models():
    if not check_ollama_status():
        logger.error("Ollama server is not running or accessible")
        return [], "⚠️ Ollama server is not running. Please start Ollama first."
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags")
        if not r.ok:
            msg = f"Error fetching models: {r.status_code} - {r.text}"
            logger.error(msg)
            return [], msg
        data = r.json().get("models", [])
        if not data:
            return [], "No models found. Pull some via `ollama pull <model>`"
        names = [m["name"] for m in data]
        logger.info(f"Available models: {names}")
        return names, None
    except requests.exceptions.RequestException as e:
        msg = f"Failed to connect to Ollama: {e}"
        logger.error(msg)
        return [], msg

# ─── Load STT Model (Whisper) ───────────────────────────────────────────────────
def load_stt_model(force_cpu=False):
    global stt_pipeline
    stt_device = "cpu"  # Always CPU to save GPU for TTS
    if stt_pipeline is None:
        try:
            logger.info(f"Loading STT (Whisper) model on {stt_device}")
            stt_pipeline = pipeline(
                "automatic-speech-recognition",
                model="openai/whisper-base.en",
                device=stt_device
            )
        except Exception as e:
            logger.error(f"Error loading STT model: {e}")
            raise
    return stt_pipeline

# ─── Load TTS Model (Chatterbox) ────────────────────────────────────────────────
def load_tts_model(force_cpu=False):
    global tts_model
    # Determine device based on availability and configuration
    if force_cpu or not torch.cuda.is_available():
        tts_device = "cpu"
    else:
        try:
            # Check if we can allocate a small tensor to test CUDA
            torch.ones(1).cuda()
            tts_device = DEVICE
        except RuntimeError as e:
            logger.warning(f"CUDA availability check failed: {e}")
            logger.info("Falling back to CPU for TTS model")
            tts_device = "cpu"

    if tts_model is None:
        try:
            logger.info(f"Loading TTS model on {tts_device}")
            tts_model = ChatterboxTTS.from_pretrained(device=tts_device)
        except Exception as e:
            # If CUDA fails, fall back to CPU
            if "cuda" in str(e).lower():
                logger.warning(f"CUDA loading failed: {e}. Trying CPU...")
                try:
                    tts_model = ChatterboxTTS.from_pretrained(device="cpu")
                    logger.info("Successfully loaded TTS model on CPU")
                except Exception as e2:
                    logger.error(f"FATAL: Could not load TTS model on CPU either: {e2}")
                    raise
            else:
                logger.error(f"FATAL: Could not load TTS model: {e}")
                raise
    return tts_model

# ─── Generate Speech ────────────────────────────────────────────────────────────
def generate_speech(text, model, audio_prompt=None, exaggeration=0.5, temperature=0.8, cfg_weight=0.5):
    try:
        normalized = punc_norm(text)
        # Check for CUDA availability and handle errors gracefully
        if torch.cuda.is_available():
            try:
                wav = model.generate(
                    normalized,
                    audio_prompt_path=audio_prompt,
                    exaggeration=exaggeration,
                    temperature=temperature,
                    cfg_weight=cfg_weight
                )
            except RuntimeError as e:
                # Handle CUDA errors specifically
                if "CUDA" in str(e):
                    logger.error(f"CUDA Error: {e}")
                    # Try to clear CUDA cache and retry once
                    torch.cuda.empty_cache()
                    try:
                        wav = model.generate(
                            normalized,
                            audio_prompt_path=audio_prompt,
                            exaggeration=exaggeration,
                            temperature=temperature,
                            cfg_weight=cfg_weight
                        )
                    except RuntimeError as e2:
                        logger.error(f"CUDA Retry Failed: {e2}")
                        raise ValueError("CUDA error persisted after cache clear") from e2
                else:
                    raise
        else:
            # Fall back to CPU if CUDA is not available or fails
            wav = model.generate(
                normalized,
                audio_prompt_path=audio_prompt,
                exaggeration=exaggeration,
                temperature=temperature,
                cfg_weight=cfg_weight,
                device="cpu"
            )
        return (model.sr, wav.squeeze(0).numpy())
    except Exception as e:
        logger.error(f"TTS Error: {e}")
        raise

def extract_url(text):
    """Extract URL from text using improved pattern matching."""
    url_pattern = r'(?:https?:\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)'
    matches = re.findall(url_pattern, text)
    if matches:
        url = matches[0]
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url
    return None

def is_browser_command(message):
    """Determine if the message is actually a browser command."""
    message_lower = message.lower().strip()

    # Common browser command patterns
    browser_patterns = [
        r'^(?:please\s+)?(?:can\s+you\s+)?(?:open|launch|start)\s+(?:a\s+)?(?:new\s+)?(?:browser\s+)?(?:tab|window)',
        r'^(?:please\s+)?(?:can\s+you\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(?:information\s+about\s+)?',
        r'^(?:please\s+)?(?:can\s+you\s+)?(?:go\s+to|navigate\s+to|visit|open)\s+(?:the\s+)?(?:website\s+)?(?:at\s+)?',
    ]

    # Check if the message matches any browser command pattern
    for pattern in browser_patterns:
        if re.match(pattern, message_lower):
            return True

    # Check for URL presence
    if extract_url(message):
        return True

    return False

def extract_search_query(message):
    """Extract search query from message using improved pattern matching."""
    message_lower = message.lower().strip()

    # Common search patterns
    search_patterns = [
        r'(?:search|look\s+up|find)\s+(?:for\s+)?(?:information\s+about\s+)?(.+)',
        r'(?:what\s+is|who\s+is|where\s+is|how\s+to)\s+(.+)',
        r'(?:tell\s+me\s+about|show\s+me\s+information\s+about)\s+(.+)',
    ]

    for pattern in search_patterns:
        match = re.search(pattern, message_lower)
        if match:
            query = match.group(1).strip()
            # Remove common question words and phrases
            query = re.sub(r'^(?:please|can you|could you|would you|will you)\s+', '', query)
            return query

    return None

# ─── Chat with Voice ────────────────────────────────────────────────────────────
def chat_with_voice(message, history, selected_model,
                    audio_prompt=None, exaggeration=0.5,
                    temperature=0.8, cfg_weight=0.5):
    if not message.strip():
        return history, None

    # First, check if this is actually a browser command
    if is_browser_command(message):
        try:
            response = execute_nlp_browser_command(message)
            response_msg = f"I'll perform that action for you: {response}"
            history.append({"role": "assistant", "content": response_msg})
            return history, generate_speech(response_msg, load_tts_model(),
                                         audio_prompt, exaggeration, temperature, cfg_weight)
        except Exception as e:
            error_msg = f"I'm sorry, I couldn't perform that action. Please try again with a different command."
            history.append({"role": "assistant", "content": error_msg})
            return history, generate_speech(error_msg, load_tts_model(),
                                         audio_prompt, exaggeration, temperature, cfg_weight)

    # If not a browser command, proceed with normal chat
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": selected_model,
                "prompt": message,
                "stream": False
            }
        )
        if response.ok:
            response_text = response.json().get("response", "").strip()
            history.append({"role": "assistant", "content": response_text})
            return history, generate_speech(response_text, load_tts_model(),
                                         audio_prompt, exaggeration, temperature, cfg_weight)
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        error_msg = "I'm having trouble processing your request. Could you please try again?"
        history.append({"role": "assistant", "content": error_msg})
        return history, generate_speech(error_msg, load_tts_model(),
                                     audio_prompt, exaggeration, temperature, cfg_weight)

# ─── Transcribe & Chat (Voice) ──────────────────────────────────────────────────
def transcribe_and_chat(audio_path, history,
                        selected_model, audio_prompt,
                        exaggeration, temperature,
                        cfg_weight, force_cpu):
    if audio_path is None:
        return history, None, "Please record your voice first.", None

    logger.info(f"Received audio file: {audio_path}")
    try:
        stt = load_stt_model(force_cpu=force_cpu)
        transcription = stt(audio_path)["text"]
        logger.info(f"Transcription: {transcription}")

        # Check for browser commands in voice input
        if is_browser_command(transcription):
            try:
                response = execute_nlp_browser_command(transcription)
                history.append({"role": "assistant", "content": response})
                return history, None, response, None
            except Exception as e:
                error_msg = f"I'm sorry, I couldn't perform that action. Please try again with a different command."
                history.append({"role": "assistant", "content": error_msg})
                return history, None, error_msg, None

    except Exception as e:
        logger.error(f"STT Error: {e}")
        if "ffmpeg" in str(e).lower():
            err = "[STT Error: `ffmpeg` not found; install it.]"
        else:
            err = f"[STT Error: {e}]"
        return history, None, err, None

    new_history, audio_resp = chat_with_voice(
        transcription, history, selected_model,
        audio_prompt, exaggeration, temperature, cfg_weight
    )
    return new_history, audio_resp, transcription, None

# ─── Gradio App Definition ─────────────────────────────────────────────────────
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🗣️ Voice Chat with Ollama
    Talk to an LLM with voice or text! Ensure Ollama is running and models are pulled.
    """)

    initial_models, error_msg = fetch_ollama_models()

    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(height=400, label="Conversation", type="messages")
        with gr.Column(scale=1):
            gr.Markdown("### Model Selection")
            model_status = gr.Markdown("" if not error_msg else f"⚠️ {error_msg}")
            model_selector = gr.Dropdown(
                choices=initial_models,
                value=initial_models[0] if initial_models else None,
                label="Select AI Model",
                interactive=True,
            )
            refresh = gr.Button("🔄 Refresh Models")
            def update_models():
                models, err = fetch_ollama_models()
                status = "" if not err else f"⚠️ {err}"
                return models, models[0] if models else None, status
            refresh.click(update_models,
                          outputs=[model_selector, model_selector, model_status])

            with gr.Accordion("Advanced Voice Settings", open=False):
                audio_prompt = gr.Audio(sources=["upload"],
                                        type="filepath",
                                        label="Voice Reference (Optional)")
                force_cpu = gr.Checkbox(label="Force CPU Mode", value=False)
                exaggeration = gr.Slider(0.25, 2, value=0.5, step=0.05,
                                        label="Voice Exaggeration")
                temperature = gr.Slider(0.05, 5, value=0.8, step=0.05,
                                       label="Temperature")
                cfg_weight = gr.Slider(0.0, 1, value=0.5, step=0.05,
                                       label="CFG/Pace Weight")

    gr.Markdown("---")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🎤 Voice Input")
            voice_input = gr.Audio(sources=["microphone"],
                                   type="filepath",
                                   label="Record Your Message")
        with gr.Column():
            gr.Markdown("### ⌨️ Text Input")
            msg = gr.Textbox(placeholder="Type here or use voice...",
                             label="Type your message")

    audio_output = gr.Audio(label="AI Voice Response", autoplay=True)
    clear = gr.ClearButton(components=[chatbot, msg, audio_output, voice_input],
                           value="Clear Conversation")

    voice_input.stop_recording(
        fn=transcribe_and_chat,
        inputs=[voice_input, chatbot,
                model_selector, audio_prompt,
                exaggeration, temperature,
                cfg_weight, force_cpu],
        outputs=[chatbot, audio_output, msg, voice_input]
    )

    def text_submit(message, history, *args):
        new_hist, audio_out = chat_with_voice(message, history, *args)
        return "", new_hist, audio_out

    msg.submit(text_submit,
               inputs=[msg, chatbot,
                       model_selector, audio_prompt,
                       exaggeration, temperature,
                       cfg_weight],
               outputs=[msg, chatbot, audio_output])

if __name__ == "__main__":
    if os.environ.get("CUDA_LAUNCH_BLOCKING") != "1":
        logger.info("Run with CUDA_LAUNCH_BLOCKING=1 for detailed CUDA errors.")
    demo.queue().launch(debug=True)
